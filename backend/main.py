"""
main.py — FastAPI backend for the AI Newsroom Assistant.

Run with:
    uvicorn main:app --reload

Then visit http://127.0.0.1:8000/docs for interactive API docs.
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Optional

import anthropic
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import db
import eval_suite
import llm
import search as search_module
from ingest import DEFAULT_FEEDS, SOURCE_TERMS, ingest_feeds

LIVE_FEED_INTERVAL_SECONDS = 180  # Auto-poll live RSS feeds every 3 minutes

_live_state = {
    "enabled": True,
    "interval_seconds": LIVE_FEED_INTERVAL_SECONDS,
    "last_sync_at": None,
    "last_sync_added": 0,
    "sync_count": 0,
}


def _run_sync(custom_feeds: Optional[dict[str, str]] = None) -> dict[str, int]:
    results = ingest_feeds(custom_feeds)
    total_added = sum(results.values())
    _live_state["last_sync_at"] = datetime.now(timezone.utc).isoformat()
    _live_state["last_sync_added"] = total_added
    _live_state["sync_count"] += 1
    return results


async def _live_feed_loop():
    """Background task that keeps the SQLite database continuously updated from live RSS feeds."""
    while True:
        try:
            await asyncio.to_thread(_run_sync)
        except Exception as exc:
            print(f"[live-feed] Background sync error: {exc}")
        await asyncio.sleep(LIVE_FEED_INTERVAL_SECONDS)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init_db()
    task = asyncio.create_task(_live_feed_loop())
    yield
    task.cancel()


app = FastAPI(title="AI Newsroom Assistant", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class IngestRequest(BaseModel):
    feeds: Optional[dict[str, str]] = None


class SearchRequest(BaseModel):
    query: str
    limit: int = 20
    source: Optional[str] = None
    category: Optional[str] = None
    tag: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None


class AnalyzeRequest(BaseModel):
    article_ids: list[int]


class AskRequest(BaseModel):
    question: str
    limit: int = 8
    source: Optional[str] = None
    category: Optional[str] = None


def _handle_llm_error(exc: Exception):
    if isinstance(exc, RuntimeError):
        raise HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, anthropic.APIError):
        raise HTTPException(status_code=502, detail=f"Anthropic API error: {exc}")
    raise HTTPException(status_code=500, detail=str(exc))


@app.post("/ingest")
def ingest(req: Optional[IngestRequest] = None):
    """Pull new articles from all configured RSS feeds (or custom feeds if provided)."""
    custom_feeds = req.feeds if req and req.feeds else None
    results = _run_sync(custom_feeds)
    return {
        "ingested": results,
        "total": sum(results.values()),
        "live_feed": _live_state,
        "feed_statuses": db.get_feed_statuses(),
    }


@app.get("/stats")
def stats():
    """Return archive counts, per-source refresh status & errors, publisher terms, and API key status."""
    data = db.get_stats()
    data["configured_feeds"] = DEFAULT_FEEDS
    data["source_terms"] = SOURCE_TERMS
    data["categories"] = llm.CATEGORIES
    data["api_key_configured"] = llm.is_api_key_configured()
    data["live_feed"] = _live_state
    return data


@app.get("/clusters")
def get_story_clusters(limit: int = 8):
    """Return related-story clusters covered across multiple outlets."""
    return search_module.cluster_related_stories(limit_clusters=limit)


@app.get("/evaluate")
def evaluate_assistant():
    """Run the newsroom benchmark evaluation suite and return detailed verification metrics."""
    return eval_suite.run_evaluation()


@app.get("/articles")
def list_articles(
    limit: int = 50,
    source: Optional[str] = None,
    category: Optional[str] = None,
    tag: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
):
    rows = db.get_all_articles(
        limit=limit,
        source=source,
        category=category,
        tag=tag,
        date_from=date_from,
        date_to=date_to,
    )
    return [dict(r) for r in rows]


@app.get("/articles/category/{category}")
def articles_by_category(category: str, limit: int = 50):
    rows = db.get_articles_by_category(category, limit=limit)
    return [dict(r) for r in rows]


@app.get("/articles/{article_id}")
def get_article(article_id: int):
    row = db.get_article(article_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return dict(row)


@app.post("/articles/{article_id}/summarize")
def summarize_article(article_id: int):
    row = db.get_article(article_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Article not found")
    art = dict(row)
    try:
        summary = llm.summarize(art["title"], art["content"])
    except Exception as exc:
        _handle_llm_error(exc)
    db.update_article_ai_fields(article_id, summary=summary)
    return {
        "id": article_id,
        "summary": summary,
        "citation": llm.build_verifiable_citations([art])[0],
    }


@app.post("/articles/{article_id}/categorize")
def categorize_article(article_id: int):
    row = db.get_article(article_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Article not found")
    try:
        result = llm.categorize_and_tag(row["title"], row["content"])
    except Exception as exc:
        _handle_llm_error(exc)
    db.update_article_ai_fields(
        article_id, category=result["category"], tags=", ".join(result["tags"])
    )
    return {"id": article_id, **result}


@app.post("/search")
def search_articles(req: SearchRequest):
    return search_module.search(
        req.query,
        limit=req.limit,
        source=req.source,
        category=req.category,
        tag=req.tag,
        date_from=req.date_from,
        date_to=req.date_to,
    )


@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    """Compare coverage across a specific set of article IDs with verifiable excerpts & publisher links."""
    articles = []
    for aid in req.article_ids:
        row = db.get_article(aid)
        if row:
            articles.append(dict(row))
    if not articles:
        raise HTTPException(status_code=404, detail="No matching articles found")
    try:
        analysis = llm.analyze_coverage(articles)
    except Exception as exc:
        _handle_llm_error(exc)
    citations = llm.build_verifiable_citations(articles)
    return {
        "analysis": analysis,
        "articles_used": [a["id"] for a in articles],
        "articles": articles,
        "citations": citations,
    }


@app.post("/ask")
def ask(req: AskRequest):
    """Verifiable question answering grounded in stored articles with evidence-sufficiency guardrails."""
    matches = search_module.search(
        req.question,
        limit=max(req.limit, 16),
        source=req.source,
        category=req.category,
    )
    try:
        qa_result = llm.answer_query(req.question, matches)
    except Exception as exc:
        _handle_llm_error(exc)
    citations = qa_result.get("citations", [])
    return {
        "answer": qa_result["answer"],
        "insufficient_evidence": qa_result["insufficient_evidence"],
        "evidence_note": qa_result["evidence_note"],
        "outlets_synthesized": qa_result.get("outlets_synthesized", []),
        "sources_used": [c["id"] for c in citations],
        "citations": citations,
        "articles": matches[: req.limit] if not qa_result["insufficient_evidence"] else [],
    }


@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "AI Newsroom Assistant API. Visit /docs for endpoints.",
        "configured_feeds": list(DEFAULT_FEEDS.keys()),
        "api_key_configured": llm.is_api_key_configured(),
        "live_feed": _live_state,
    }
