"""
search.py — Hybrid search (Ranked Keyword + TF-IDF / Character N-Gram similarity)
and Related-Story Clustering over stored newsroom articles.
"""

from collections import Counter
import math
from pathlib import Path
import re
from typing import Optional

from db import (
    STOPWORDS,
    extract_keywords,
    get_all_articles,
    search_articles as _keyword_search,
)

# Common lightweight stem/synonym expansions for journalism queries
SYNONYM_MAP = {
    "strike": ["strikes", "striking", "attack", "attacks", "military", "missile"],
    "strikes": ["strike", "attack", "attacks", "missile", "bombing"],
    "election": ["elections", "electoral", "vote", "voting", "ballot", "polls", "campaign"],
    "voting": ["vote", "election", "elections", "ballot", "polls"],
    "economy": ["economic", "inflation", "gdp", "markets", "trade", "financial", "bank"],
    "climate": ["environment", "warming", "emissions", "flood", "flooding", "weather"],
    "flood": ["flooding", "floods", "rain", "monsoon", "rescue", "landslide"],
    "rescue": ["rescuers", "trapped", "search", "blast", "workers", "relief"],
    "usa": ["us", "united", "states", "american", "washington", "biden", "trump"],
    "us": ["usa", "united", "states", "american", "washington"],
    "uk": ["britain", "british", "london", "england"],
    "ai": ["artificial", "intelligence", "tech", "technology", "model", "models"],
}


def _tokenize_with_stems(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]{2,}", (text or "").lower())
    out = []
    for t in tokens:
        if t in STOPWORDS:
            continue
        out.append(t)
        # Simple suffix stripping for plural/gerund matching
        if len(t) > 4 and t.endswith("ing"):
            out.append(t[:-3])
        elif len(t) > 4 and t.endswith("ies"):
            out.append(t[:-3] + "y")
        elif len(t) > 3 and t.endswith("es"):
            out.append(t[:-2])
        elif len(t) > 3 and t.endswith("s"):
            out.append(t[:-1])
    return out


def _tfidf_similarity(query_tokens: list[str], doc_tokens: list[str], idf: dict[str, float]) -> float:
    if not query_tokens or not doc_tokens:
        return 0.0
    q_counts = Counter(query_tokens)
    d_counts = Counter(doc_tokens)
    shared = set(q_counts.keys()) & set(d_counts.keys())
    if not shared:
        return 0.0

    dot = sum(q_counts[w] * d_counts[w] * (idf.get(w, 1.0) ** 2) for w in shared)
    q_norm = math.sqrt(sum((c * idf.get(w, 1.0)) ** 2 for w, c in q_counts.items()))
    d_norm = math.sqrt(sum((c * idf.get(w, 1.0)) ** 2 for w, c in d_counts.items()))
    if q_norm == 0 or d_norm == 0:
        return 0.0
    return dot / (q_norm * d_norm)


def search(
    query: str,
    limit: int = 20,
    source: Optional[str] = None,
    category: Optional[str] = None,
    tag: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> list[dict]:
    """
    Hybrid keyword + TF-IDF similarity search across stored articles with
    support for source, date, category, and tag filters.
    """
    query_clean = (query or "").strip()
    if not query_clean:
        rows = get_all_articles(
            limit=limit,
            source=source,
            category=category,
            tag=tag,
            date_from=date_from,
            date_to=date_to,
            db_path=db_path,
        )
        return [dict(r) for r in rows]

    # 1. Direct SQL keyword search
    sql_rows = _keyword_search(
        query=query_clean,
        limit=max(limit * 2, 40),
        source=source,
        category=category,
        tag=tag,
        date_from=date_from,
        date_to=date_to,
        db_path=db_path,
    )
    by_id: dict[int, dict] = {r["id"]: dict(r) for r in sql_rows}

    # 2. Hybrid TF-IDF + stem/synonym expansion across candidate pool
    pool_rows = get_all_articles(
        limit=400,
        source=source,
        category=category,
        tag=tag,
        date_from=date_from,
        date_to=date_to,
        db_path=db_path,
    )
    pool = [dict(r) for r in pool_rows]

    q_base = extract_keywords(query_clean)
    q_expanded = list(q_base)
    for w in q_base:
        if w in SYNONYM_MAP:
            q_expanded.extend(SYNONYM_MAP[w])
    q_stems = _tokenize_with_stems(" ".join(q_expanded))

    if pool and q_stems:
        doc_tokens_map: dict[int, list[str]] = {}
        df: Counter = Counter()
        for art in pool:
            text_blob = f"{art.get('title', '')} {art.get('title', '')} {art.get('tags', '')} {art.get('category', '')} {art.get('content', '')}"
            dtoks = _tokenize_with_stems(text_blob)
            doc_tokens_map[art["id"]] = dtoks
            for ut in set(dtoks):
                df[ut] += 1

        n_docs = len(pool)
        idf = {w: math.log((n_docs + 1) / (df[w] + 1)) + 1.0 for w in df}

        for art in pool:
            aid = art["id"]
            sim = _tfidf_similarity(q_stems, doc_tokens_map[aid], idf)
            sql_score = float(by_id[aid].get("relevance_score", 0)) if aid in by_id else 0.0
            combined = round(sql_score + (sim * 20.0), 2)
            if combined >= 2.0 or sql_score > 0:
                entry = by_id.get(aid, art)
                entry["relevance_score"] = combined
                entry["semantic_similarity"] = round(sim, 3)
                by_id[aid] = entry

    ranked = sorted(
        by_id.values(),
        key=lambda x: (x.get("relevance_score", 0), x.get("published_iso") or "", x.get("id", 0)),
        reverse=True,
    )
    return ranked[:limit]


def cluster_related_stories(
    limit_clusters: int = 8,
    db_path: Optional[Path] = None,
) -> list[dict]:
    """
    Group stored articles into related-story clusters based on shared
    high-IDF terms in titles & lead excerpts, prioritizing stories covered
    by 2+ different news outlets.
    """
    rows = get_all_articles(limit=250, db_path=db_path)
    articles = [dict(r) for r in rows]
    if not articles:
        return []

    doc_tokens: dict[int, list[str]] = {}
    df: Counter = Counter()
    for a in articles:
        toks = _tokenize_with_stems(f"{a.get('title', '')} {a.get('title', '')} {a.get('content', '')[:180]}")
        doc_tokens[a["id"]] = toks
        for t in set(toks):
            df[t] += 1

    n_docs = len(articles)
    idf = {w: math.log((n_docs + 1) / (df[w] + 1)) + 1.0 for w in df if df[w] < n_docs * 0.35}

    assigned: set[int] = set()
    clusters: list[dict] = []

    for i, seed in enumerate(articles):
        sid = seed["id"]
        if sid in assigned:
            continue
        seed_toks = doc_tokens[sid]
        if len(seed_toks) < 3:
            continue

        members = [seed]
        outlets = {seed.get("source", "")}

        for other in articles[i + 1 :]:
            oid = other["id"]
            if oid in assigned:
                continue
            sim = _tfidf_similarity(seed_toks, doc_tokens[oid], idf)
            shared_terms = set(seed_toks) & set(doc_tokens[oid])
            if sim >= 0.24 and len(shared_terms) >= 2:
                members.append(other)
                outlets.add(other.get("source", ""))

        # Keep clusters that span at least 2 articles (especially multi-outlet coverage)
        if len(members) >= 2:
            for m in members:
                assigned.add(m["id"])
            # Extract top shared topic keywords for the cluster label
            term_freq = Counter()
            for m in members:
                for t in set(doc_tokens[m["id"]]):
                    if len(t) > 3:
                        term_freq[t] += idf.get(t, 1.0)
            top_keywords = [w.capitalize() for w, _ in term_freq.most_common(4)]
            clusters.append(
                {
                    "topic_label": " · ".join(top_keywords[:3]) or seed["title"][:45],
                    "lead_title": seed["title"],
                    "article_count": len(members),
                    "outlet_count": len(outlets),
                    "outlets": sorted(list(outlets)),
                    "article_ids": [m["id"] for m in members],
                    "articles": members[:6],
                }
            )

    # Sort clusters so multi-outlet stories come first
    clusters.sort(key=lambda c: (c["outlet_count"], c["article_count"]), reverse=True)
    return clusters[:limit_clusters]
