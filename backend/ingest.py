"""
ingest.py — Pulls articles from RSS feeds and stores them in the database.

Tracks publication time separately from retrieval time, records per-source
refresh timestamps and feed errors in `feed_status`, and enforces publisher
RSS terms (storing only syndicate-provided headlines & excerpts with direct
links back to the original publisher rather than scraping full text).
"""

from datetime import datetime, timezone
import html
from pathlib import Path
import re
from typing import Optional
import feedparser
import requests

from db import init_db, insert_article, record_feed_status

DEFAULT_FEEDS = {
    "BBC World": "http://feeds.bbci.co.uk/news/world/rss.xml",
    "The Guardian World": "https://www.theguardian.com/world/rss",
    "NYT World": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "The Hindu": "https://www.thehindu.com/news/national/feeder/default.rss",
    "CNN World": "http://rss.cnn.com/rss/edition_world.rss",
    "NPR News": "https://feeds.npr.org/1001/rss.xml",
    "CNBC World": "https://www.cnbc.com/id/100727362/device/rss/rss.html",
    "DW News": "https://rss.dw.com/xml/rss-en-world",
    "France 24": "https://www.france24.com/en/rss",
    "ABC News": "https://abcnews.go.com/abcnews/internationalheadlines",
}

SOURCE_TERMS = {
    "BBC World": (
        "BBC RSS Terms: Personal/research syndication of headlines and short summaries "
        "is permitted with attribution and direct link back to BBC News. Full-text scraping is prohibited."
    ),
    "The Guardian World": (
        "Guardian Open Platform / RSS Terms: Excerpts and headlines may be indexed with attribution "
        "and unaltered links to theguardian.com. Full-article reproduction requires an API/syndication license."
    ),
    "NYT World": (
        "NYT RSS Terms: Feeds provide headlines and short standfirst excerpts for reader discovery "
        "with direct links to nytimes.com. Full article text sits behind publisher access rules."
    ),
    "Al Jazeera": (
        "Al Jazeera RSS Policy: Headlines and summary descriptions are provided for syndication with "
        "direct attribution and link to aljazeera.com."
    ),
    "The Hindu": (
        "The Hindu RSS Policy: Provides national news headlines and lead summaries for non-commercial "
        "reader aggregation with mandatory link back to thehindu.com."
    ),
    "CNN World": (
        "CNN RSS Terms: Feeds provide headlines and brief lead text for syndication with direct "
        "links to cnn.com. Unaltered attribution required."
    ),
    "NPR News": (
        "NPR Terms of Use: Syndicated headlines and story summaries for non-commercial reader indexing "
        "with direct attribution to NPR."
    ),
    "CNBC World": (
        "CNBC RSS Policy: Provides international business and world headlines with excerpts linking "
        "back to cnbc.com."
    ),
    "DW News": (
        "Deutsche Welle RSS Terms: Syndication feeds offer global news headlines and teaser summaries "
        "under DW distribution guidelines."
    ),
    "France 24": (
        "France 24 RSS Terms: International broadcast headlines and lead summaries available for reader "
        "aggregation with links to france24.com."
    ),
    "ABC News": (
        "ABC News RSS Terms: RSS feed offers headlines and brief story excerpts linking to abcnews.go.com."
    ),
}


def _clean_text(raw: str) -> str:
    """Strip HTML tags, unescape entities, and normalize whitespace."""
    if not raw or not isinstance(raw, str):
        return ""
    no_tags = re.sub(r"<[^>]+>", " ", raw)
    unescaped = html.unescape(no_tags)
    return re.sub(r"\s+", " ", unescaped).strip()


def _extract_image_url(entry: dict) -> str:
    """Extract the highest-quality thumbnail or media image URL from an RSS entry."""
    media_content = entry.get("media_content")
    if isinstance(media_content, list) and media_content:
        for item in reversed(media_content):
            if isinstance(item, dict) and item.get("url"):
                return item["url"]

    media_thumb = entry.get("media_thumbnail")
    if isinstance(media_thumb, list) and media_thumb:
        last_thumb = media_thumb[-1]
        if isinstance(last_thumb, dict) and last_thumb.get("url"):
            return last_thumb["url"].replace("/standard/240/", "/standard/800/")

    for link in entry.get("links", []):
        if isinstance(link, dict) and str(link.get("type", "")).startswith("image/") and link.get("href"):
            return link["href"]

    raw_html = entry.get("summary", "") or entry.get("description", "")
    if isinstance(raw_html, str):
        img_match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', raw_html)
        if img_match:
            return img_match.group(1)

    return ""


def ingest_feeds(
    feeds: Optional[dict[str, str]] = None,
    db_path: Optional[Path] = None,
) -> dict[str, int]:
    """
    Fetch and store articles from the given {source_name: feed_url} dict.
    Records per-source refresh status and errors in `feed_status`.
    Returns {source_name: number_of_new_articles_inserted}.
    """
    feeds = feeds if feeds is not None else DEFAULT_FEEDS
    init_db(db_path)
    results: dict[str, int] = {}

    for source_name, feed_url in feeds.items():
        inserted = 0
        error_msg = None
        terms_note = SOURCE_TERMS.get(
            source_name,
            "Standard RSS syndication: stores headline & feed excerpt only; links to publisher for full text.",
        )

        try:
            try:
                resp = requests.get(
                    feed_url,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/124.0.0.0 Safari/537.36 Newsroom/1.0"
                        ),
                        "Accept": "application/rss+xml, application/xml, text/xml, */*",
                    },
                    timeout=14,
                )
                if resp.status_code >= 400:
                    raise RuntimeError(f"HTTP {resp.status_code} when fetching feed")
                parsed = feedparser.parse(resp.content)
            except Exception as req_err:
                # Fallback to feedparser direct fetch if requests fails
                parsed = feedparser.parse(
                    feed_url,
                    agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) NewsroomAssistant/1.0",
                )
                status_code = getattr(parsed, "status", 200)
                if status_code and int(status_code) >= 400:
                    raise RuntimeError(f"HTTP {status_code} when fetching feed")

            entries = getattr(parsed, "entries", []) or []
            if getattr(parsed, "bozo", False) and not entries:
                bozo_exc = getattr(parsed, "bozo_exception", "Malformed XML/RSS feed")
                raise RuntimeError(f"Malformed feed: {bozo_exc}")

            retrieved_now = datetime.now(timezone.utc).isoformat()
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                url = str(entry.get("link") or "").strip()
                if not url:
                    continue

                raw_title = _clean_text(str(entry.get("title") or ""))
                raw_summary = _clean_text(
                    str(entry.get("summary") or entry.get("description") or "")
                )
                title = raw_title or (raw_summary[:80] + "..." if raw_summary else "Untitled")
                content = raw_summary or title
                published = str(
                    entry.get("published") or entry.get("updated") or ""
                ).strip()
                image_url = _extract_image_url(entry)

                row_id = insert_article(
                    title=title,
                    source=source_name,
                    url=url,
                    published=published,
                    content=content,
                    image_url=image_url,
                    retrieved_at=retrieved_now,
                    db_path=db_path,
                )
                if row_id is not None:
                    inserted += 1

            record_feed_status(
                source=source_name,
                feed_url=feed_url,
                success=True,
                inserted_count=inserted,
                error_msg=None,
                terms_note=terms_note,
                db_path=db_path,
            )
        except Exception as exc:
            error_msg = str(exc)
            print(f"[ingest] Failed to fetch {source_name}: {error_msg}")
            record_feed_status(
                source=source_name,
                feed_url=feed_url,
                success=False,
                inserted_count=0,
                error_msg=error_msg,
                terms_note=terms_note,
                db_path=db_path,
            )

        results[source_name] = inserted

    return results


if __name__ == "__main__":
    summary = ingest_feeds()
    total = sum(summary.values())
    print(f"Ingested {total} new articles:")
    for source, count in summary.items():
        print(f"  {source}: {count}")
