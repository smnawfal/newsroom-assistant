"""
db.py — SQLite setup and data access helpers for the AI Newsroom Assistant.

Tracks publication time (`published`, `published_iso`) separately from retrieval
time (`retrieved_at`), marks incomplete RSS excerpts (`is_excerpt`, `word_count`),
and stores per-source ingestion health and errors (`feed_status`).
"""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import re
import sqlite3
from pathlib import Path
from typing import Optional

from config import CATEGORY_KEYWORDS, DATABASE_PATH, EXCERPT_WORD_LIMIT

DB_PATH = DATABASE_PATH

STOPWORDS = {
    "a", "about", "an", "and", "are", "as", "at", "be", "by", "can", "did",
    "do", "does", "for", "from", "give", "happened", "happening", "has",
    "have", "how", "i", "in", "into", "is", "it", "its", "latest", "me",
    "news", "of", "on", "or", "recent", "stories", "story", "summarize",
    "tell", "that", "the", "their", "them", "there", "these", "they", "this",
    "to", "today", "update", "updates", "was", "were", "what", "whats",
    "when", "where", "which", "who", "why", "with", "articles", "article",
}


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def parse_published_iso(published_raw: str) -> Optional[str]:
    """Parse an RSS RFC-2822 or ISO date string into a normalized UTC ISO-8601 timestamp."""
    if not published_raw or not published_raw.strip():
        return None
    raw = published_raw.strip()
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        pass
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:
        return None


def compute_content_metrics(title: str, content: str) -> tuple[int, int]:
    """
    Return (word_count, is_excerpt).
    RSS feeds almost always provide a headline or short summary excerpt (<120 words).
    """
    clean_content = (content or "").strip()
    clean_title = (title or "").strip()
    words = re.findall(r"\S+", clean_content)
    word_count = len(words)
    is_excerpt = 1 if (word_count < EXCERPT_WORD_LIMIT or clean_content == clean_title) else 0
    return word_count, is_excerpt


_AUTO_CATEGORIES = CATEGORY_KEYWORDS


def _infer_category_and_tags(title: str, content: str) -> tuple[str, str]:
    text_lower = f"{title} {content}".lower()
    best_cat = "World"
    best_hits = 0
    for cat, kws in _AUTO_CATEGORIES.items():
        hits = sum(1 for kw in kws if re.search(rf"\b{re.escape(kw)}\b", text_lower))
        if hits > best_hits:
            best_hits = hits
            best_cat = cat

    cap_words = re.findall(r"\b[A-Z][a-zA-Z]{2,}\b", f"{title} {content}")
    stop_caps = {"The", "And", "For", "With", "From", "After", "Over", "Into", "Says", "Said", "New", "How", "Why", "What", "Who", "Are", "Now", "These", "Their", "More", "This", "That"}
    tags = []
    for w in cap_words:
        if w not in stop_caps and w.lower() not in STOPWORDS and w not in tags:
            tags.append(w)
        if len(tags) >= 4:
            break
    return best_cat, ", ".join(tags)


def init_db(db_path: Optional[Path] = None) -> None:
    """Create tables if they don't exist and apply non-destructive column migrations."""
    conn = get_connection(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            source TEXT,
            url TEXT UNIQUE,
            published TEXT,
            published_iso TEXT,
            retrieved_at TEXT,
            content TEXT,
            word_count INTEGER DEFAULT 0,
            is_excerpt INTEGER DEFAULT 1,
            summary TEXT,
            category TEXT,
            tags TEXT,
            image_url TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS feed_status (
            source TEXT PRIMARY KEY,
            feed_url TEXT,
            last_success_at TEXT,
            last_attempt_at TEXT,
            last_error TEXT,
            last_inserted_count INTEGER DEFAULT 0,
            terms_note TEXT
        )
        """
    )

    cols = {r[1] for r in conn.execute("PRAGMA table_info(articles)").fetchall()}
    migrations = {
        "image_url": "ALTER TABLE articles ADD COLUMN image_url TEXT",
        "published_iso": "ALTER TABLE articles ADD COLUMN published_iso TEXT",
        "retrieved_at": "ALTER TABLE articles ADD COLUMN retrieved_at TEXT",
        "word_count": "ALTER TABLE articles ADD COLUMN word_count INTEGER DEFAULT 0",
        "is_excerpt": "ALTER TABLE articles ADD COLUMN is_excerpt INTEGER DEFAULT 1",
    }
    for col, sql in migrations.items():
        if col not in cols:
            conn.execute(sql)

    # Backfill any existing rows missing retrieved_at, published_iso, word_count, or category/tags
    rows = conn.execute(
        "SELECT id, title, content, published, published_iso, retrieved_at, word_count, category, tags FROM articles"
    ).fetchall()
    now_iso = datetime.now(timezone.utc).isoformat()
    for r in rows:
        if (
            not r["retrieved_at"]
            or not r["word_count"]
            or (r["published"] and not r["published_iso"])
            or not r["category"]
            or not r["tags"]
        ):
            p_iso = r["published_iso"] or parse_published_iso(r["published"] or "")
            wc, is_exc = compute_content_metrics(r["title"] or "", r["content"] or "")
            ret_at = r["retrieved_at"] or p_iso or now_iso
            auto_cat, auto_tags = _infer_category_and_tags(r["title"] or "", r["content"] or "")
            cat_val = r["category"] or auto_cat
            tags_val = r["tags"] or auto_tags
            conn.execute(
                """
                UPDATE articles
                SET published_iso = ?, retrieved_at = ?, word_count = ?, is_excerpt = ?, category = ?, tags = ?
                WHERE id = ?
                """,
                (p_iso, ret_at, wc, is_exc, cat_val, tags_val, r["id"]),
            )

    conn.commit()
    conn.close()


def insert_article(
    title: str,
    source: str,
    url: str,
    published: str,
    content: str,
    image_url: Optional[str] = None,
    retrieved_at: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> Optional[int]:
    """Insert an article. Returns its row id, or None if the URL is empty or already exists."""
    if not url or not url.strip():
        return None
    title_clean = (title or "Untitled").strip() or "Untitled"
    content_clean = (content or title_clean).strip() or title_clean
    pub_iso = parse_published_iso(published or "")
    ret_iso = retrieved_at or datetime.now(timezone.utc).isoformat()
    word_count, is_excerpt = compute_content_metrics(title_clean, content_clean)

    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            """
            INSERT INTO articles (
                title, source, url, published, published_iso, retrieved_at,
                content, word_count, is_excerpt, image_url
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                title_clean,
                source,
                url.strip(),
                published,
                pub_iso,
                ret_iso,
                content_clean,
                word_count,
                is_excerpt,
                image_url,
            ),
        )
        conn.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError:
        if image_url:
            conn.execute(
                "UPDATE articles SET image_url = ? WHERE url = ? AND (image_url IS NULL OR image_url = '')",
                (image_url, url.strip()),
            )
            conn.commit()
        return None
    finally:
        conn.close()


def record_feed_status(
    source: str,
    feed_url: str,
    success: bool,
    inserted_count: int = 0,
    error_msg: Optional[str] = None,
    terms_note: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> None:
    """Record the outcome of a feed refresh attempt per source."""
    now_iso = datetime.now(timezone.utc).isoformat()
    conn = get_connection(db_path)
    existing = conn.execute(
        "SELECT last_success_at, terms_note FROM feed_status WHERE source = ?",
        (source,),
    ).fetchone()
    last_success = now_iso if success else (existing["last_success_at"] if existing else None)
    terms = terms_note or (existing["terms_note"] if existing else "RSS headline & excerpt syndication only; full text requires visiting publisher.")

    conn.execute(
        """
        INSERT INTO feed_status (
            source, feed_url, last_success_at, last_attempt_at,
            last_error, last_inserted_count, terms_note
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source) DO UPDATE SET
            feed_url = excluded.feed_url,
            last_success_at = excluded.last_success_at,
            last_attempt_at = excluded.last_attempt_at,
            last_error = excluded.last_error,
            last_inserted_count = excluded.last_inserted_count,
            terms_note = excluded.terms_note
        """,
        (source, feed_url, last_success, now_iso, error_msg, inserted_count, terms),
    )
    conn.commit()
    conn.close()


def get_feed_statuses(db_path: Optional[Path] = None) -> list[dict]:
    conn = get_connection(db_path)
    rows = conn.execute("SELECT * FROM feed_status ORDER BY source ASC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_article_ai_fields(
    article_id: int,
    summary: Optional[str] = None,
    category: Optional[str] = None,
    tags: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> None:
    conn = get_connection(db_path)
    fields, values = [], []
    if summary is not None:
        fields.append("summary = ?")
        values.append(summary)
    if category is not None:
        fields.append("category = ?")
        values.append(category)
    if tags is not None:
        fields.append("tags = ?")
        values.append(tags)
    if fields:
        values.append(article_id)
        conn.execute(f"UPDATE articles SET {', '.join(fields)} WHERE id = ?", values)
        conn.commit()
    conn.close()


def get_all_articles(
    limit: int = 100,
    source: Optional[str] = None,
    category: Optional[str] = None,
    tag: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> list[sqlite3.Row]:
    conn = get_connection(db_path)
    clauses, params = [], []
    if source and source != "All":
        clauses.append("source = ?")
        params.append(source)
    if category and category != "All":
        clauses.append("LOWER(IFNULL(category, '')) = LOWER(?)")
        params.append(category)
    if tag and tag != "All":
        clauses.append("(LOWER(IFNULL(tags, '')) LIKE LOWER(?) OR LOWER(title) LIKE LOWER(?))")
        params.extend([f"%{tag}%", f"%{tag}%"])
    if date_from:
        clauses.append("COALESCE(published_iso, retrieved_at, '') >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("COALESCE(published_iso, retrieved_at, '') <= ?")
        params.append(date_to)

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)
    rows = conn.execute(
        f"SELECT * FROM articles {where_sql} ORDER BY COALESCE(published_iso, retrieved_at) DESC, id DESC LIMIT ?",
        params,
    ).fetchall()
    conn.close()
    return rows


def get_article(article_id: int, db_path: Optional[Path] = None) -> Optional[sqlite3.Row]:
    conn = get_connection(db_path)
    row = conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
    conn.close()
    return row


def extract_keywords(query: str) -> list[str]:
    """Extract meaningful search terms from a keyword query or natural-language question."""
    tokens = re.findall(r"[A-Za-z0-9]{2,}", query.lower())
    filtered = [t for t in tokens if t not in STOPWORDS]
    return filtered or tokens


def search_articles(
    query: str,
    limit: int = 20,
    source: Optional[str] = None,
    category: Optional[str] = None,
    tag: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> list[sqlite3.Row]:
    """
    Ranked multi-keyword search with optional filters for source, category, tag, and date range.
    """
    query_clean = (query or "").strip()
    if not query_clean:
        return get_all_articles(
            limit=limit,
            source=source,
            category=category,
            tag=tag,
            date_from=date_from,
            date_to=date_to,
            db_path=db_path,
        )

    conn = get_connection(db_path)
    keywords = extract_keywords(query_clean)

    where_parts = []
    score_parts = []
    where_params = []
    score_params = []

    exact_like = f"%{query_clean}%"
    score_parts.append("(CASE WHEN title LIKE ? THEN 10 ELSE 0 END)")
    score_params.append(exact_like)
    score_parts.append("(CASE WHEN content LIKE ? THEN 5 ELSE 0 END)")
    score_params.append(exact_like)

    for kw in keywords:
        kw_like = f"%{kw}%"
        where_parts.append(
            "(title LIKE ? OR content LIKE ? OR IFNULL(tags, '') LIKE ? OR IFNULL(category, '') LIKE ? OR IFNULL(source, '') LIKE ?)"
        )
        where_params.extend([kw_like, kw_like, kw_like, kw_like, kw_like])

        score_parts.append("(CASE WHEN title LIKE ? THEN 4 ELSE 0 END)")
        score_params.append(kw_like)
        score_parts.append("(CASE WHEN IFNULL(tags, '') LIKE ? THEN 3 ELSE 0 END)")
        score_params.append(kw_like)
        score_parts.append("(CASE WHEN content LIKE ? THEN 2 ELSE 0 END)")
        score_params.append(kw_like)
        score_parts.append("(CASE WHEN IFNULL(source, '') LIKE ? THEN 1 ELSE 0 END)")
        score_params.append(kw_like)

    filter_clauses = []
    filter_params = []
    if source and source != "All":
        filter_clauses.append("source = ?")
        filter_params.append(source)
    if category and category != "All":
        filter_clauses.append("LOWER(IFNULL(category, '')) = LOWER(?)")
        filter_params.append(category)
    if tag and tag != "All":
        filter_clauses.append("LOWER(IFNULL(tags, '')) LIKE LOWER(?)")
        filter_params.append(f"%{tag}%")
    if date_from:
        filter_clauses.append("COALESCE(published_iso, retrieved_at, '') >= ?")
        filter_params.append(date_from)
    if date_to:
        filter_clauses.append("COALESCE(published_iso, retrieved_at, '') <= ?")
        filter_params.append(date_to)

    kw_where = f"({' OR '.join(where_parts)})" if where_parts else "1=1"
    full_where = " AND ".join([kw_where] + filter_clauses)

    sql = f"""
        SELECT *, ({' + '.join(score_parts)}) AS relevance_score
        FROM articles
        WHERE {full_where}
        ORDER BY relevance_score DESC, COALESCE(published_iso, retrieved_at) DESC, id DESC
        LIMIT ?
    """
    params = score_params + where_params + filter_params + [limit]
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return rows


def get_articles_by_category(category: str, limit: int = 50, db_path: Optional[Path] = None) -> list[sqlite3.Row]:
    return get_all_articles(limit=limit, category=category, db_path=db_path)


def get_stats(db_path: Optional[Path] = None) -> dict:
    """Return summary counts, tag frequencies, and feed health for the newsroom archive."""
    conn = get_connection(db_path)
    total = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    summarized = conn.execute(
        "SELECT COUNT(*) FROM articles WHERE summary IS NOT NULL AND summary != ''"
    ).fetchone()[0]
    categorized = conn.execute(
        "SELECT COUNT(*) FROM articles WHERE category IS NOT NULL AND category != ''"
    ).fetchone()[0]
    excerpt_count = conn.execute(
        "SELECT COUNT(*) FROM articles WHERE is_excerpt = 1"
    ).fetchone()[0]
    by_source = {
        row["source"]: row["cnt"]
        for row in conn.execute(
            "SELECT source, COUNT(*) AS cnt FROM articles GROUP BY source ORDER BY cnt DESC"
        ).fetchall()
    }
    by_category = {
        row["category"]: row["cnt"]
        for row in conn.execute(
            "SELECT category, COUNT(*) AS cnt FROM articles WHERE category IS NOT NULL AND category != '' GROUP BY category ORDER BY cnt DESC"
        ).fetchall()
    }
    # Collect top tags
    tag_counts: dict[str, int] = {}
    for row in conn.execute("SELECT tags FROM articles WHERE tags IS NOT NULL AND tags != ''").fetchall():
        for t in str(row["tags"]).split(","):
            t_clean = t.strip()
            if t_clean:
                tag_counts[t_clean] = tag_counts.get(t_clean, 0) + 1
    top_tags = [k for k, _ in sorted(tag_counts.items(), key=lambda x: -x[1])[:25]]

    feed_statuses = [dict(r) for r in conn.execute("SELECT * FROM feed_status ORDER BY source ASC").fetchall()]
    conn.close()
    return {
        "total_articles": total,
        "summarized_count": summarized,
        "categorized_count": categorized,
        "excerpt_only_count": excerpt_count,
        "by_source": by_source,
        "by_category": by_category,
        "top_tags": top_tags,
        "feed_statuses": feed_statuses,
    }
