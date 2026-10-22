"""
test_newsroom.py — Unit and integration tests for the AI Newsroom Assistant.

Covers:
1. Duplicate URL deduplication
2. Malformed RSS feeds & error reporting in `feed_status`
3. Missing RSS fields (missing link, missing title, missing summary, missing published date)
4. Separate tracking of publication time (`published_iso`) vs retrieval time (`retrieved_at`)
5. Incomplete RSS excerpt detection (`is_excerpt`, `word_count`)
6. Discovery filters (source, date range, category, tags)
7. Verifiable AI Q&A benchmark evaluation (expected sources, supporting excerpts, links, and insufficient-evidence guardrails)
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import db
import eval_suite
import ingest
import llm
import search


class NewsroomTests(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp_dir.name) / "test_newsroom.db"
        db.init_db(self.db_path)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_duplicate_urls_deduplicated(self):
        """Duplicate URLs must be rejected without raising an unhandled exception."""
        id1 = db.insert_article(
            title="First Headline",
            source="BBC World",
            url="https://example.com/story-1",
            published="Mon, 31 Aug 2026 17:30:47 GMT",
            content="Short summary of story one.",
            db_path=self.db_path,
        )
        id2 = db.insert_article(
            title="Duplicate Headline With Same URL",
            source="BBC World",
            url="https://example.com/story-1",
            published="Mon, 31 Aug 2026 18:00:00 GMT",
            content="Updated text that should not duplicate the row.",
            db_path=self.db_path,
        )
        self.assertIsNotNone(id1)
        self.assertIsNone(id2)
        all_rows = db.get_all_articles(db_path=self.db_path)
        self.assertEqual(len(all_rows), 1)
        self.assertEqual(all_rows[0]["title"], "First Headline")

    def test_malformed_feed_recorded_in_feed_status(self):
        """Malformed feeds must not crash ingestion and must record an error in feed_status."""
        fake_parsed = MagicMock()
        fake_parsed.status = 200
        fake_parsed.bozo = True
        fake_parsed.bozo_exception = Exception("SAXParseException: unclosed XML tag")
        fake_parsed.entries = []

        with patch("ingest.feedparser.parse", return_value=fake_parsed):
            res = ingest.ingest_feeds(
                feeds={"Broken Feed": "https://broken.example.com/rss.xml"},
                db_path=self.db_path,
            )

        self.assertEqual(res["Broken Feed"], 0)
        statuses = db.get_feed_statuses(self.db_path)
        self.assertEqual(len(statuses), 1)
        self.assertEqual(statuses[0]["source"], "Broken Feed")
        self.assertIsNone(statuses[0]["last_success_at"])
        self.assertIn("Malformed feed", statuses[0]["last_error"])

    def test_missing_fields_handled_safely(self):
        """Entries missing link are skipped; entries missing title, summary, or published are safely defaulted."""
        fake_parsed = MagicMock()
        fake_parsed.status = 200
        fake_parsed.bozo = False
        fake_parsed.entries = [
            # 1. Missing link -> must be skipped
            {"title": "No Link Story", "summary": "Should be skipped"},
            # 2. Missing title -> should derive title from summary
            {"link": "https://example.com/no-title", "summary": "Fallback summary text used for title"},
            # 3. Missing summary and published -> should fall back to title and still record retrieved_at
            {"title": "Headline Only Entry", "link": "https://example.com/headline-only"},
        ]

        with patch("ingest.feedparser.parse", return_value=fake_parsed):
            res = ingest.ingest_feeds(
                feeds={"Test Bureau": "https://example.com/rss"},
                db_path=self.db_path,
            )

        self.assertEqual(res["Test Bureau"], 2)
        rows = db.get_all_articles(db_path=self.db_path)
        self.assertEqual(len(rows), 2)
        by_url = {r["url"]: dict(r) for r in rows}

        no_title_row = by_url["https://example.com/no-title"]
        self.assertTrue(no_title_row["title"].startswith("Fallback summary text"))
        self.assertEqual(no_title_row["is_excerpt"], 1)

        headline_only_row = by_url["https://example.com/headline-only"]
        self.assertEqual(headline_only_row["content"], "Headline Only Entry")
        self.assertEqual(headline_only_row["is_excerpt"], 1)
        self.assertIsNotNone(headline_only_row["retrieved_at"])

    def test_separate_publication_and_retrieval_timestamps(self):
        """Publication time and retrieval time must be stored and tracked separately."""
        aid = db.insert_article(
            title="Timestamp Test Story",
            source="NYT World",
            url="https://example.com/time-test",
            published="Mon, 31 Aug 2026 09:00:40 +0000",
            content="Article body excerpt.",
            retrieved_at="2026-10-21T19:30:00+00:00",
            db_path=self.db_path,
        )
        row = db.get_article(aid, db_path=self.db_path)
        self.assertEqual(row["published_iso"], "2026-08-31T09:00:40+00:00")
        self.assertEqual(row["retrieved_at"], "2026-10-21T19:30:00+00:00")
        self.assertNotEqual(row["published_iso"], row["retrieved_at"])

    def test_discovery_filters_source_date_category_tags(self):
        """Filtering by source, date range, category, and tags must return exact matches."""
        id1 = db.insert_article(
            title="Solar power expansion in India",
            source="The Hindu",
            url="https://example.com/solar-india",
            published="2026-09-01T10:00:00+00:00",
            content="India expands renewable solar grid capacity.",
            db_path=self.db_path,
        )
        db.update_article_ai_fields(id1, category="Environment", tags="India, Solar, Climate", db_path=self.db_path)

        id2 = db.insert_article(
            title="European central bank policy meeting",
            source="BBC World",
            url="https://example.com/ecb-policy",
            published="2026-10-15T14:00:00+00:00",
            content="Officials discuss inflation and interest rates.",
            db_path=self.db_path,
        )
        db.update_article_ai_fields(id2, category="Business", tags="Europe, Banking, Inflation", db_path=self.db_path)

        by_src = db.get_all_articles(source="The Hindu", db_path=self.db_path)
        self.assertEqual([r["id"] for r in by_src], [id1])

        by_cat = db.get_all_articles(category="Business", db_path=self.db_path)
        self.assertEqual([r["id"] for r in by_cat], [id2])

        by_tag = db.get_all_articles(tag="Solar", db_path=self.db_path)
        self.assertEqual([r["id"] for r in by_tag], [id1])

        by_date = db.get_all_articles(date_from="2026-10-01", db_path=self.db_path)
        self.assertEqual([r["id"] for r in by_date], [id2])

    def test_verifiable_answers_and_eval_suite_on_production_archive(self):
        """Run the newsroom evaluation benchmark against the real archive and verify 100% pass rate."""
        prod_db = Path(__file__).resolve().parent / "newsroom.db"
        if not prod_db.exists():
            self.skipTest("Production newsroom.db not found")

        db.init_db(prod_db)
        eval_report = eval_suite.run_evaluation(db_path=prod_db)
        self.assertEqual(
            eval_report["failed_cases"],
            0,
            f"Evaluation had failures: {eval_report['failures_tracked']}",
        )
        self.assertEqual(eval_report["pass_rate_pct"], 100.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
