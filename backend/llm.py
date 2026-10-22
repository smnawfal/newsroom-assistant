"""
llm.py — Wraps all calls to the Claude API for the newsroom assistant:
summarization, categorization/tagging, cross-article framing analysis,
and verifiable source-grounded Q&A with evidence-sufficiency guardrails.
"""

import json
import os
import re
from typing import Optional

import anthropic

from config import ANTHROPIC_MODEL, CATEGORIES, CATEGORY_KEYWORDS
from db import STOPWORDS, extract_keywords

MODEL = ANTHROPIC_MODEL

_client = None


def is_api_key_configured() -> bool:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    return bool(key and key != "your_key_here")


def get_client() -> anthropic.Anthropic:
    global _client
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key or api_key == "your_key_here":
        raise RuntimeError(
            "ANTHROPIC_API_KEY environment variable is not set. "
            "Set it in your terminal or add ANTHROPIC_API_KEY=your_key to a .env file."
        )
    if _client is None:
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


def _ask(prompt: str, max_tokens: int = 500) -> str:
    client = get_client()
    response = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return "".join(block.text for block in response.content if block.type == "text").strip()


def _word_matches(term: str, text_lower: str) -> bool:
    if len(term) <= 4:
        return bool(re.search(rf"\b{re.escape(term)}s?\b", text_lower))
    stem = term[:-1] if term.endswith("e") else (term[:-1] if term.endswith("s") else term)
    return bool(re.search(rf"\b{re.escape(stem)}(?:e|s|es|ed|ing)?\b", text_lower))


def build_verifiable_citations(articles: list[dict], query: Optional[str] = None) -> list[dict]:
    """
    Build structured citation records with direct publisher links, short supporting
    excerpts, publication vs. retrieval timestamps, and incomplete-excerpt warnings.
    """
    citations = []
    q_terms = extract_keywords(query) if query else []
    for a in articles:
        content = (a.get("content") or a.get("title") or "").strip()
        doc_lower = f"{a.get('title', '')} {content} {a.get('tags', '')} {a.get('source', '')}".lower()
        matched_terms = [t for t in q_terms if _word_matches(t, doc_lower)]
        if q_terms and not matched_terms:
            continue
        excerpt = content[:240] + ("…" if len(content) > 240 else "")
        word_count = a.get("word_count") or len(content.split())
        is_excerpt = bool(a.get("is_excerpt", 1))
        citations.append(
            {
                "id": a.get("id"),
                "title": a.get("title", "Untitled"),
                "source": a.get("source", "Wire"),
                "url": a.get("url", ""),
                "published": a.get("published") or a.get("published_iso") or "",
                "published_iso": a.get("published_iso") or "",
                "retrieved_at": a.get("retrieved_at") or "",
                "excerpt": excerpt,
                "word_count": word_count,
                "is_excerpt": is_excerpt,
                "completeness_note": (
                    f"RSS Excerpt only ({word_count} words) — Read full article at {a.get('source', 'publisher')}"
                    if is_excerpt
                    else f"Full syndication text ({word_count} words)"
                ),
                "matched_terms": matched_terms,
                "relevance_score": a.get("relevance_score", 0),
            }
        )
    return citations


def check_evidence_sufficiency(query: str, articles: list[dict]) -> tuple[bool, str]:
    """
    Verify whether retrieved articles actually contain sufficient whole-word evidence
    to answer `query`. Prevents hallucination when the archive lacks relevant stories.
    """
    if not articles:
        return (
            False,
            "Insufficient evidence in the local archive: No stored RSS articles matched your query. "
            "Try refreshing the feeds or searching for broader terms.",
        )

    q_terms = extract_keywords(query)
    if not q_terms:
        return False, "Insufficient evidence: Please provide specific topic keywords in your question."

    # Measure whole-word keyword overlap on each candidate article individually
    per_doc_matches = []
    all_matched_terms = set()
    for a in articles[:6]:
        doc_lower = f"{a.get('title', '')} {a.get('content', '')} {a.get('tags', '')} {a.get('source', '')}".lower()
        m = [t for t in q_terms if _word_matches(t, doc_lower)]
        per_doc_matches.append(len(m))
        all_matched_terms.update(m)

    best_doc_hit_count = max(per_doc_matches, default=0)
    best_doc_ratio = best_doc_hit_count / len(q_terms)
    coverage_ratio = len(all_matched_terms) / len(q_terms)

    if (
        best_doc_hit_count == 0
        or best_doc_ratio < 0.38
        or (len(q_terms) >= 2 and best_doc_hit_count < 2)
    ):
        return (
            False,
            f"Insufficient evidence in the local archive: None of the stored articles contain verified "
            f"reporting on '{query}'. The newsroom assistant will not speculate beyond stored sources.",
        )

    if len(q_terms) >= 4 and coverage_ratio < 0.5:
        missing = [t for t in q_terms if t not in all_matched_terms]
        return (
            False,
            f"Insufficient evidence in the local archive: The archive does not contain verified articles "
            f"covering {', '.join(missing)}.",
        )

    return True, "Sufficient archive evidence found."


def summarize(title: str, content: str) -> str:
    """Return a concise 2-3 sentence summary of an article."""
    if is_api_key_configured():
        prompt = f"""Summarize this news article in 2-3 concise, neutral sentences.
Do not add opinions or information not in the article. If the content is only a short RSS excerpt, summarize only what is stated.

Title: {title}

Content: {content}

Summary:"""
        return _ask(prompt, max_tokens=200)

    # Extractive fallback when ANTHROPIC_API_KEY is not set
    clean_c = (content or "").strip()
    if not clean_c or clean_c == title.strip():
        return f"{title.strip()} (Note: RSS feed provided headline only; open publisher link for full text.)"
    sentences = re.split(r"(?<=[.!?])\s+", clean_c)
    lead = " ".join(sentences[:2]).strip()
    return f"{title.strip()}. {lead}" if title.strip() not in lead else lead


_CATEGORY_KEYWORDS = CATEGORY_KEYWORDS


def categorize_and_tag(title: str, content: str) -> dict:
    """
    Classify an article into one of CATEGORIES and generate 3-5 keyword tags.
    Returns {"category": str, "tags": list[str]}.
    """
    if is_api_key_configured():
        categories_str = ", ".join(CATEGORIES)
        prompt = f"""Classify this news article and generate tags.

Title: {title}
Content: {content}

Respond with ONLY a JSON object, no other text, in this exact format:
{{"category": "<one of: {categories_str}>", "tags": ["tag1", "tag2", "tag3"]}}"""

        raw = _ask(prompt, max_tokens=150)
        raw = raw.replace("```json", "").replace("```", "").strip()
        try:
            parsed = json.loads(raw)
            category = parsed.get("category", "Other")
            if category not in CATEGORIES:
                category = "Other"
            tags = [str(t).strip() for t in parsed.get("tags", []) if str(t).strip()]
            return {"category": category, "tags": tags[:5]}
        except json.JSONDecodeError:
            pass

    # Deterministic keyword classification fallback
    text_lower = f"{title} {content}".lower()
    best_cat = "World"
    best_hits = 0
    for cat, kws in _CATEGORY_KEYWORDS.items():
        hits = sum(1 for kw in kws if re.search(rf"\b{re.escape(kw)}\b", text_lower))
        if hits > best_hits:
            best_hits = hits
            best_cat = cat

    # Extract capitalized entities / top keywords as tags
    cap_words = re.findall(r"\b[A-Z][a-zA-Z]{2,}\b", f"{title} {content}")
    stop_caps = {"The", "And", "For", "With", "From", "After", "Over", "Into", "Says", "Said", "New", "How", "Why", "What", "Who", "Are", "Now", "These", "Their", "More"}
    tags = []
    for w in cap_words:
        if w not in stop_caps and w.lower() not in STOPWORDS and w not in tags:
            tags.append(w)
        if len(tags) >= 4:
            break
    if not tags:
        tags = extract_keywords(title)[:3]
    return {"category": best_cat, "tags": tags}


def analyze_coverage(articles: list[dict]) -> str:
    """
    Given a list of article dicts on the same topic, produce a comparative
    analysis of how outlets are covering it (agreements, framing differences,
    omitted facts, and excerpt-completeness caveats).
    """
    if not articles:
        return "Insufficient evidence: No articles provided to analyze."

    if is_api_key_configured():
        formatted = "\n\n".join(
            f"Article #{a.get('id', '?')} — Source: {a['source']} (URL: {a.get('url', '')})\n"
            f"Published: {a.get('published', 'Unknown')} | Excerpt only: {bool(a.get('is_excerpt', 1))}\n"
            f"Title: {a['title']}\nContent: {a['content']}"
            for a in articles
        )
        prompt = f"""You are a media analyst helping a journalist understand how
different outlets are covering the same story. Below are articles from
different sources.

{formatted}

In 4-6 sentences, describe:
- Where the coverage agrees
- Where framing, headline tone, or emphasis differs between outlets
- Any notable facts or angles one source includes that others omit
- Note clearly if the comparison is based on RSS summaries/excerpts rather than full article text.

Be specific and reference sources and article IDs by name (for example, [Source Name, #2]). Avoid speculation beyond what's in the text."""

        return _ask(prompt, max_tokens=550)

    # Structured comparative synthesis fallback when ANTHROPIC_API_KEY is not set
    outlets = list(dict.fromkeys(a.get("source", "Unknown") for a in articles))
    lines = [
        f"Comparative Coverage across {len(articles)} dispatches from {', '.join(outlets)}:"
    ]
    for a in articles:
        snippet = (a.get("content") or "")[:180].strip()
        lines.append(
            f"• [{a.get('source')} #{a.get('id')}] frames the story through the headline "
            f"\"{a.get('title')}\", emphasizing: {snippet}"
        )
    lines.append(
        "Note: Stored items are publisher RSS excerpts; consult the linked original articles below to verify full-text context before publication."
    )
    return "\n\n".join(lines)


def _diversify_by_outlet(articles: list[dict], max_items: int = 8) -> list[dict]:
    """
    Order candidate articles so the top match from each distinct news outlet
    appears first, followed by remaining high-relevance matches. Ensures
    multi-source synthesis covers all reporting outlets rather than a single feed.
    """
    first_pass = []
    remainder = []
    seen_sources = set()
    for a in articles:
        src = a.get("source", "Wire")
        if src not in seen_sources:
            seen_sources.add(src)
            first_pass.append(a)
        else:
            remainder.append(a)
    return (first_pass + remainder)[:max_items]


def answer_query(query: str, articles: list[dict]) -> dict:
    """
    Verifiable Q&A grounded in retrieved articles.
    Returns a dict with:
      - answer: str
      - insufficient_evidence: bool
      - evidence_note: str
      - outlets_synthesized: list[str]
      - citations: list[dict] (links, supporting excerpts, timestamps, completeness flags)
    """
    sufficient, evidence_note = check_evidence_sufficiency(query, articles)
    if not sufficient:
        return {
            "answer": evidence_note,
            "insufficient_evidence": True,
            "evidence_note": evidence_note,
            "outlets_synthesized": [],
            "citations": [],
        }

    # Filter to articles that match query keywords and diversify across outlets
    q_terms = extract_keywords(query)
    matched_articles = []
    for a in articles:
        doc_lower = f"{a.get('title', '')} {a.get('content', '')} {a.get('tags', '')} {a.get('source', '')}".lower()
        if not q_terms or any(_word_matches(t, doc_lower) for t in q_terms):
            matched_articles.append(a)
    if not matched_articles:
        matched_articles = articles

    top_articles = _diversify_by_outlet(matched_articles, max_items=8)
    citations = build_verifiable_citations(top_articles, query=query)
    outlets_list = list(dict.fromkeys(a.get("source", "Wire") for a in top_articles))

    if is_api_key_configured():
        formatted = "\n\n".join(
            f"[#{a.get('id', '?')} · {a['source']} · {a.get('published', '')} · URL: {a.get('url', '')}]\n"
            f"Headline: {a['title']}\n"
            f"RSS Excerpt ({a.get('word_count', 0)} words): {a['content'][:450]}"
            for a in top_articles
        )
        prompt = f"""You are a verifiable newsroom research assistant. A journalist asked:

"{query}"

Here are the matching RSS dispatches across {len(outlets_list)} outlets ({', '.join(outlets_list)}) from the local archive:

{formatted}

Strict Verification Rules:
1. Start with a cohesive 3-4 sentence **Multi-Source Synthesis** that combines the key facts across all reporting outlets, citing every claim inline with `[Source, #ID]`.
2. Follow with bullet points showing key specifics or angles from each outlet (`• [Source, #ID] ...`).
3. Use ONLY the facts explicitly stated in the dispatches above.
4. If different outlets report different numbers or angles, note both perspectives fairly.
5. State clearly if any detail cannot be verified from these RSS excerpts and advise checking the linked full articles."""

        answer_text = _ask(prompt, max_tokens=650)
    else:
        # Cohesive multi-outlet synthesis + per-source breakdown when ANTHROPIC_API_KEY is not set
        synth_clauses = []
        for a in top_articles[: len(outlets_list) or 4]:
            title_clean = (a.get("title") or "").strip().rstrip(".")
            content_clean = (a.get("content") or "").strip()
            first_sent = re.split(r"(?<=[.!?])\s+", content_clean)[0].strip() if content_clean else ""
            if first_sent and first_sent.lower() != title_clean.lower():
                synth_clauses.append(
                    f"{a.get('source')} reports that {title_clean} ({first_sent}) [{a.get('source')}, #{a.get('id')}]"
                )
            else:
                synth_clauses.append(
                    f"{a.get('source')} highlights \"{title_clean}\" [{a.get('source')}, #{a.get('id')}]"
                )

        synthesis_para = (
            f"**Multi-Source Synthesis ({len(top_articles)} dispatches across {len(outlets_list)} "
            f"{'outlet' if len(outlets_list) == 1 else 'outlets'}: {', '.join(outlets_list)}):** "
            + " ".join(s if s.endswith(".") else s + "." for s in synth_clauses)
        )

        bullets = []
        for a in top_articles[:6]:
            snippet = (a.get("content") or a.get("title") or "").strip()
            bullets.append(
                f"• [{a.get('source')}, #{a.get('id')}] **{a.get('title')}** — {snippet}"
            )
        answer_text = (
            synthesis_para
            + "\n\n**Supporting Dispatches by Outlet:**\n"
            + "\n\n".join(bullets)
            + "\n\n*Verification Note: Stored records are RSS feed excerpts. Click any inline citation or open the original publisher links below to verify full context.*"
        )

    return {
        "answer": answer_text,
        "insufficient_evidence": False,
        "evidence_note": evidence_note,
        "outlets_synthesized": outlets_list,
        "citations": citations[:8],
    }
