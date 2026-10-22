"""
Streamlit frontend for the configurable newsroom assistant.

Run with:
    streamlit run app.py

The backend address and app name are read from the project configuration.
"""

import html
import json
import sys
from pathlib import Path

import requests
import streamlit as st
import streamlit.components.v1 as components

PROJECT_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from config import (  # noqa: E402
    API_URL,
    APP_NAME,
    AUTO_REFRESH_ENABLED,
    FEED_REFRESH_INTERVAL_SECONDS,
    OUTLET_METADATA,
    STATUS_REFRESH_INTERVAL_SECONDS,
    DEFAULT_FEEDS,
    SOURCE_TERMS,
)

API = API_URL

st.set_page_config(
    page_title=f"{APP_NAME} — Newsroom",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    #MainMenu, header, footer, [data-testid="stHeader"], [data-testid="stToolbar"] { display: none !important; }
    .block-container { padding: 0 !important; margin: 0 !important; max-width: 100% !important; }
    iframe { border: none !important; width: 100% !important; }
    </style>
    """,
    unsafe_allow_html=True,
)


def _fetch_initial_state() -> dict:
    """Fetch initial state from FastAPI, or fall back to reading the backend modules directly."""
    try:
        stats_r = requests.get(f"{API}/stats", timeout=4)
        arts_r = requests.get(f"{API}/articles", params={"limit": 150}, timeout=6)
        clust_r = requests.get(f"{API}/clusters", timeout=6)
        eval_r = requests.get(f"{API}/evaluate", timeout=10)
        if stats_r.ok and arts_r.ok:
            return {
                "online": True,
                "stats": stats_r.json(),
                "articles": arts_r.json(),
                "clusters": clust_r.json() if clust_r.ok else [],
                "evaluation": eval_r.json() if eval_r.ok else {},
            }
    except Exception:
        pass

    try:
        import db
        import eval_suite
        import llm
        import search as search_module

        db.init_db()
        stats = db.get_stats()
        stats["configured_feeds"] = DEFAULT_FEEDS
        stats["source_terms"] = SOURCE_TERMS
        stats["outlet_metadata"] = OUTLET_METADATA
        stats["categories"] = llm.CATEGORIES
        stats["api_key_configured"] = llm.is_api_key_configured()
        stats["live_feed"] = {
            "enabled": AUTO_REFRESH_ENABLED,
            "interval_seconds": FEED_REFRESH_INTERVAL_SECONDS,
        }
        stats["status_refresh_seconds"] = STATUS_REFRESH_INTERVAL_SECONDS
        stats["app_name"] = APP_NAME
        return {
            "online": False,
            "stats": stats,
            "articles": [dict(r) for r in db.get_all_articles(limit=150)],
            "clusters": search_module.cluster_related_stories(limit_clusters=8),
            "evaluation": eval_suite.run_evaluation(),
        }
    except Exception as exc:
        return {
            "online": False,
            "error": str(exc),
            "stats": {
                "app_name": APP_NAME,
                "configured_feeds": DEFAULT_FEEDS,
                "source_terms": SOURCE_TERMS,
                "outlet_metadata": OUTLET_METADATA,
                "categories": [],
                "live_feed": {
                    "enabled": AUTO_REFRESH_ENABLED,
                    "interval_seconds": FEED_REFRESH_INTERVAL_SECONDS,
                },
                "status_refresh_seconds": STATUS_REFRESH_INTERVAL_SECONDS,
            },
            "articles": [],
            "clusters": [],
            "evaluation": {},
        }


initial_state = _fetch_initial_state()
logos_path = Path(__file__).resolve().parent / "assets" / "logos_data.json"
if logos_path.is_file():
    try:
        initial_state["logos"] = json.loads(logos_path.read_text(encoding="utf-8"))
    except Exception:
        initial_state["logos"] = {}
initial_json = json.dumps(initial_state).replace("</", "<\\/")

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter+Tight:wght@400;500;600;700&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root {
    --page: #D6DDF1;
    --shell: #FFFFFF;
    --soft: #EEF2F8;
    --soft-2: #F5F7FB;
    --ink: #0F1115;
    --body: #5B6170;
    --muted: #9AA1B1;
    --src: #5C7CA6;
    --line: #E6EAF2;
    --purple: #7B5CF5;
    --purple-deep: #5F43D9;
    --lav: #ECE7FF;
    --r-xl: 26px;
    --r-lg: 18px;
    --r-md: 12px;
}

* { box-sizing: border-box; margin: 0; padding: 0; }
html { scroll-behavior: smooth; }

body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    color: var(--ink);
    background: linear-gradient(160deg, #D2DAF0 0%, #DCE2F4 50%, #D5DBF2 100%);
    padding: 22px 24px 40px;
    -webkit-font-smoothing: antialiased;
}

h1, h2, h3, h4, .display { font-family: 'Inter Tight', 'Inter', sans-serif; letter-spacing: -0.02em; }
button { font-family: inherit; }
a { color: inherit; }

.shell {
    max-width: 1280px;
    margin: 0 auto;
    background: var(--shell);
    border-radius: 30px;
    box-shadow: 0 30px 80px rgba(60, 72, 130, 0.12);
    overflow: clip;
}

.inner { padding: 0 30px; }

/* ---------- Navbar ---------- */
.nav {
    position: sticky;
    top: 0;
    z-index: 50;
    background: rgba(255, 255, 255, 0.94);
    backdrop-filter: blur(10px);
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    padding: 16px 30px;
}

.nav-left { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }

.logo-pill {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    padding: 8px 14px;
    border-radius: 999px;
    background: #fff;
    box-shadow: 0 2px 10px rgba(30, 40, 90, 0.08);
    border: none;
    font-weight: 600;
    font-size: 0.84rem;
    cursor: pointer;
    color: var(--ink);
}

.nav-pill {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    padding: 8px 13px;
    border-radius: 999px;
    background: var(--soft);
    border: none;
    color: var(--ink);
    font-weight: 500;
    font-size: 0.8rem;
    cursor: pointer;
    transition: background 0.15s, color 0.15s;
}
.nav-pill .plus { color: var(--muted); font-size: 0.85rem; line-height: 1; }
.nav-pill:hover { background: #E3E9F3; }
.nav-pill.active { background: var(--ink); color: #fff; }
.nav-pill.active .plus { color: rgba(255,255,255,0.6); }

.nav-right { display: flex; align-items: center; gap: 14px; }

.live {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    font-size: 0.78rem;
    font-weight: 500;
    color: var(--ink);
    background: none;
    border: none;
    cursor: pointer;
    white-space: nowrap;
}
.live-dot { width: 7px; height: 7px; border-radius: 50%; background: #22C55E; box-shadow: 0 0 0 3px rgba(34,197,94,0.18); animation: blink 1.8s infinite; }
@keyframes blink { 50% { opacity: 0.35; } }

.search {
    position: relative;
    width: 300px;
}
.search input {
    width: 100%;
    padding: 12px 42px 12px 18px;
    border-radius: 999px;
    border: 1px solid transparent;
    background: var(--soft);
    font-family: inherit;
    font-size: 0.8rem;
    color: var(--ink);
    outline: none;
    transition: border-color 0.15s, background 0.15s;
}
.search input::placeholder { color: var(--muted); }
.search input:focus { background: #fff; border-color: #CBD5E6; }
.search svg { position: absolute; right: 16px; top: 50%; transform: translateY(-50%); color: var(--ink); }

/* ---------- Shared bits ---------- */
.label {
    display: inline-flex;
    align-items: center;
    padding: 6px 12px 6px 10px;
    border-left: 3px solid var(--purple);
    background: linear-gradient(90deg, var(--lav) 0%, rgba(236,231,255,0) 100%);
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--ink);
}

.meta { display: flex; align-items: center; gap: 6px; font-size: 0.72rem; color: var(--ink); flex-wrap: wrap; }
.meta .src { display: inline-flex; align-items: center; gap: 6px; color: var(--src); font-weight: 500; }
.meta .sep { color: var(--muted); }
.on-dark .meta, .on-dark .meta .src { color: rgba(255,255,255,0.88); }

/* Outlet inline logos & thumbnail emblems */
.outlet-logo {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
    border-radius: 4px;
    overflow: hidden;
    vertical-align: middle;
    background: #fff;
    box-shadow: 0 1px 3px rgba(15, 17, 21, 0.12);
}
.outlet-logo img { display: block; width: 100%; height: 100%; object-fit: contain; }
.on-dark .outlet-logo { box-shadow: 0 0 0 1px rgba(255,255,255,0.22); }

.hashtags { display: flex; gap: 14px; flex-wrap: wrap; margin-top: 10px; }
.hashtags span { font-size: 0.72rem; color: var(--muted); cursor: pointer; }
.hashtags span:hover { color: var(--purple); }
.on-dark .hashtags span { color: rgba(255,255,255,0.7); }

.excerpt-chip {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 3px 9px;
    border-radius: 999px;
    background: var(--soft);
    color: var(--body);
    font-size: 0.68rem;
    font-weight: 500;
}
.excerpt-chip::before { content: ''; width: 5px; height: 5px; border-radius: 50%; background: #F59E0B; }

.read-btn {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    padding: 9px 9px 9px 16px;
    border-radius: 999px;
    background: #fff;
    border: none;
    box-shadow: 0 2px 10px rgba(30, 40, 90, 0.08);
    font-size: 0.82rem;
    font-weight: 500;
    color: var(--ink);
    cursor: pointer;
    text-decoration: none;
    transition: box-shadow 0.15s, transform 0.15s;
}
.read-btn:hover { box-shadow: 0 6px 18px rgba(30, 40, 90, 0.14); transform: translateY(-1px); }
.read-btn .arr { display: inline-flex; width: 22px; height: 22px; align-items: center; justify-content: center; }
.read-btn.soft { background: var(--soft); box-shadow: none; }
.read-btn.dark { background: var(--ink); color: #fff; }

.chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 8px 13px;
    border-radius: 999px;
    background: #fff;
    border: 1px solid var(--line);
    font-size: 0.76rem;
    font-weight: 500;
    color: var(--ink);
    cursor: pointer;
    text-decoration: none;
    white-space: nowrap;
}
.chip:hover { border-color: #C9D2E3; }
.chip.on { background: var(--ink); color: #fff; border-color: var(--ink); }

.link-btn { background: none; border: none; font-size: 0.82rem; font-weight: 500; color: var(--ink); cursor: pointer; display: inline-flex; align-items: center; gap: 6px; }
.link-btn:hover { color: var(--purple); }

.circle {
    width: 34px;
    height: 34px;
    border-radius: 50%;
    border: none;
    background: var(--soft);
    color: var(--ink);
    display: inline-flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition: background 0.15s;
}
.circle.dark { background: var(--ink); color: #fff; }
.circle:disabled { opacity: 0.35; cursor: default; }
.arrows { display: flex; justify-content: center; gap: 10px; margin-top: 22px; }

.sec { padding: 34px 30px; }
.sec-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; gap: 12px; }

/* Images & branded outlet covers */
.fill { width: 100%; height: 100%; object-fit: cover; object-position: center 22%; display: block; }
.cover {
    position: relative;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 5px;
    padding: 8px;
    color: var(--ink);
    font-family: 'Inter Tight', sans-serif;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-align: center;
    overflow: hidden;
    background: #F1F4F9;
    border: 1px solid var(--line);
}
.cover .cov-mark { display: flex; align-items: center; justify-content: center; }
.cover .cov-name { font-size: 0.62rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: var(--body); line-height: 1.1; }
.cover.fill { width: 100%; height: 100%; gap: 10px; }
.cover.fill .cov-name { font-size: 0.8rem; letter-spacing: 0.08em; }
.li-thumb { width: 58px; height: 58px; border-radius: 12px; object-fit: cover; object-position: center 22%; flex-shrink: 0; }
.cover.li-thumb { padding: 6px; border-radius: 12px; }

.clickable { cursor: pointer; }

/* ---------- 1. Hero ---------- */
.hero {
    display: grid;
    grid-template-columns: 1.12fr 330px;
    gap: 20px;
    padding: 8px 30px 24px;
    align-items: start;
}

.hero-main {
    border-radius: var(--r-xl);
    padding: 24px 22px 18px;
    display: flex;
    flex-direction: column;
    justify-content: flex-start;
    gap: 14px;
    min-height: auto;
    background: radial-gradient(circle at 75% 35%, rgba(196, 181, 253, 0.32) 0%, rgba(255,255,255,0) 65%), #fff;
    border: 1px solid var(--line);
}

.hero-top { display: grid; grid-template-columns: 1.08fr 1fr; gap: 24px; align-items: center; }

.hero-title {
    font-size: 1.95rem;
    font-weight: 600;
    line-height: 1.18;
    margin: 10px 0 6px;
    cursor: pointer;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
}
.hero-title:hover { color: var(--purple-deep); }

.hero-desc {
    font-size: 0.88rem;
    line-height: 1.55;
    color: var(--body);
    margin: 8px 0 12px;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
}

.hero-strip {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 16px;
    margin-top: 4px;
    padding-top: 14px;
    border-top: 1px solid var(--line);
}
.hero-strip .item { position: relative; padding-top: 14px; cursor: pointer; opacity: 0.45; transition: opacity 0.2s; }
.hero-strip .item.active, .hero-strip .item:hover { opacity: 1; }
.hero-strip .item h4 {
    font-size: 0.95rem;
    font-weight: 500;
    line-height: 1.3;
    margin-top: 6px;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
}
.hero-strip .dash { position: absolute; top: 0; left: 0; width: 24px; height: 2px; background: var(--line); border-radius: 2px; overflow: hidden; }
.hero-strip .item.active .dash::after { content: ''; display: block; height: 100%; background: var(--ink); animation: grow 8s linear forwards; }
.hero-main:hover .hero-strip .item.active .dash::after { animation-play-state: paused; }
@keyframes grow { from { width: 0; } to { width: 100%; } }

/* Photo stack — matches 16:9 news wire geometry so images fill edge-to-edge with zero top/bottom bars */
.photo-stack {
    position: relative;
    width: 100%;
    aspect-ratio: 16 / 9.2;
    min-height: 224px;
    max-height: 256px;
}
.photo-card {
    position: absolute;
    inset: 0;
    border-radius: 20px;
    overflow: hidden;
    background: #1E1B4B;
    box-shadow: 0 22px 46px rgba(40, 32, 110, 0.18);
    transition: transform 0.45s cubic-bezier(.2,.8,.2,1), opacity 0.3s;
    cursor: pointer;
}
.photo-card.back-1 { transform: rotate(5.5deg) translate(14px, 5px) scale(0.94); opacity: 0.82; }
.photo-card.back-2 { transform: rotate(-4.5deg) translate(-12px, 8px) scale(0.9); opacity: 0.56; }
.photo-card.back-1:hover { transform: rotate(7.5deg) translate(22px, 2px) scale(0.95); opacity: 1; }
.photo-card.back-2:hover { transform: rotate(-6.5deg) translate(-20px, 5px) scale(0.91); opacity: 0.9; }
.photo-card.front { transform: rotate(-1.2deg); z-index: 3; animation: dealIn 0.5s cubic-bezier(.2,.8,.2,1); }
.photo-card.front:hover { transform: rotate(0deg) scale(1.015); }
@keyframes dealIn { from { transform: rotate(4deg) translateY(14px) scale(0.96); opacity: 0; } to { transform: rotate(-1.2deg); opacity: 1; } }

.ph { position: relative; width: 100%; height: 100%; overflow: hidden; background: #0F172A; }
.ph-fg { width: 100%; height: 100%; object-fit: cover; object-position: center 20%; display: block; }

.photo-fallback {
    width: 100%;
    height: 100%;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    padding: 22px;
    color: #fff;
    background: radial-gradient(circle at 85% 15%, rgba(255,255,255,0.18), transparent 45%), linear-gradient(140deg, #312E81 0%, #6D28D9 55%, #A78BFA 100%);
}
.photo-fallback .pf-source { font-size: 0.7rem; font-weight: 700; letter-spacing: 0.14em; text-transform: uppercase; opacity: 0.85; }
.photo-fallback .pf-quote { font-family: 'Inter Tight', sans-serif; font-size: 1.1rem; font-weight: 600; line-height: 1.3; display: -webkit-box; -webkit-line-clamp: 4; -webkit-box-orient: vertical; overflow: hidden; }

.photo-chip {
    position: absolute;
    left: 12px;
    bottom: 12px;
    display: inline-flex;
    align-items: center;
    gap: 7px;
    padding: 6px 11px;
    border-radius: 999px;
    background: rgba(255,255,255,0.92);
    backdrop-filter: blur(6px);
    font-size: 0.7rem;
    font-weight: 600;
    color: var(--ink);
}
.photo-count { position: absolute; right: 12px; top: 12px; padding: 4px 9px; border-radius: 999px; background: rgba(15,17,21,0.7); color: #fff; font-size: 0.68rem; font-weight: 600; }

/* Recommended panel */
.panel { background: var(--soft); border-radius: var(--r-xl); padding: 18px; }
.panel-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
.panel-head h3 { font-size: 1rem; font-weight: 500; }

.rec-feature { position: relative; height: 168px; border-radius: var(--r-lg); overflow: hidden; cursor: pointer; margin-bottom: 8px; }
.rec-feature .shade { position: absolute; inset: 0; background: linear-gradient(180deg, rgba(15,17,21,0) 30%, rgba(108, 80, 230, 0.92) 100%); }
.rec-feature .txt { position: absolute; left: 16px; right: 16px; bottom: 14px; color: #fff; }
.rec-feature h4 { font-size: 0.86rem; font-weight: 500; line-height: 1.3; margin-top: 4px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }

.li { display: flex; align-items: center; justify-content: space-between; gap: 14px; padding: 13px 4px; border-bottom: 1px solid rgba(15,17,21,0.06); cursor: pointer; }
.li:last-child { border-bottom: none; }
.li h4 { font-size: 0.8rem; font-weight: 500; line-height: 1.32; margin-top: 5px; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.li:hover h4 { color: var(--purple-deep); }

/* ---------- 2. Trending ---------- */
.trending { display: grid; grid-template-columns: 380px 1fr; border-top: 1px solid var(--line); }
.trend-left { padding: 30px; display: flex; flex-direction: column; }
.trend-title { font-size: 1.85rem; font-weight: 500; line-height: 1.18; margin: 14px 0 4px; cursor: pointer; }
.trend-title:hover { color: var(--purple-deep); }
.trend-banner { margin-top: auto; height: 190px; border-radius: var(--r-lg); overflow: hidden; cursor: pointer; position: relative; }
.trend-banner::after { content: ''; position: absolute; inset: 0; background: linear-gradient(140deg, rgba(91,67,217,0.0) 30%, rgba(123,92,245,0.55) 100%); }
.trend-right { background: linear-gradient(180deg, var(--soft) 0%, var(--soft-2) 100%); padding: 26px 26px 24px; }

.grid3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 22px; }
.card { cursor: pointer; }
.card-img { height: 128px; border-radius: 14px; overflow: hidden; margin-bottom: 12px; background: #fff; }
.card-img img { transition: transform 0.35s; }
.card:hover .card-img img { transform: scale(1.04); }
.card h4 { font-size: 0.86rem; font-weight: 500; line-height: 1.32; margin-top: 6px; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
.card:hover h4 { color: var(--purple-deep); }

/* ---------- 3. Featured ---------- */
.featured { position: relative; height: 400px; margin: 0 30px; }
.feat-media { position: absolute; inset: 0 0 0 26%; border-radius: var(--r-xl); overflow: hidden; cursor: pointer; }
.feat-media .shade { position: absolute; inset: 0; background: linear-gradient(90deg, rgba(15,17,21,0) 35%, rgba(108,80,230,0.88) 72%, rgba(95,67,217,0.96) 100%); }
.feat-side { position: absolute; right: 0; top: 0; bottom: 0; width: 34%; padding: 26px; display: flex; flex-direction: column; justify-content: center; gap: 16px; color: #fff; }
.feat-side .it { cursor: pointer; padding-bottom: 14px; border-bottom: 1px solid rgba(255,255,255,0.16); }
.feat-side .it:last-child { border-bottom: none; }
.feat-side h4 { font-size: 0.92rem; font-weight: 500; line-height: 1.3; margin-top: 4px; }
.feat-side .it:hover h4 { text-decoration: underline; }
.feat-panel {
    position: absolute;
    left: 0;
    top: 46px;
    width: 40%;
    background: #fff;
    border-radius: 0 28px 28px 0;
    padding: 26px 30px 30px 0;
    z-index: 2;
}
.feat-tab { position: absolute; left: 0; top: 0; background: #fff; border-radius: 0 0 22px 0; padding: 0 22px 12px 0; z-index: 2; }
.feat-title { font-size: 1.85rem; font-weight: 500; line-height: 1.18; margin: 12px 0 4px; cursor: pointer; }
.feat-title:hover { color: var(--purple-deep); }

/* ---------- 4. Row of 5 ---------- */
.row5 { display: grid; grid-template-columns: repeat(5, 1fr); gap: 20px; }
.row5 .card-img { height: 120px; }

/* ---------- 5. Editor's picks ---------- */
.picks { display: grid; grid-template-columns: 1fr 1.25fr; gap: 26px; }
.big-card { position: relative; height: 380px; border-radius: var(--r-xl); overflow: hidden; cursor: pointer; }
.big-card .shade { position: absolute; inset: 0; background: linear-gradient(180deg, rgba(15,17,21,0.25) 0%, rgba(15,17,21,0) 30%, rgba(108,80,230,0.9) 100%); }
.big-card .top { position: absolute; left: 20px; top: 18px; }
.big-card .bottom { position: absolute; left: 22px; right: 22px; bottom: 22px; color: #fff; }
.big-card h3 { font-size: 1.85rem; font-weight: 500; line-height: 1.15; }
.picks-list { display: grid; grid-template-columns: 1fr 1fr; column-gap: 26px; align-content: start; }

/* ---------- Category / news page ---------- */
.page { display: grid; grid-template-columns: 1fr 340px; gap: 0; }
.page-main { padding: 22px 30px 40px; }
.page-side { padding: 22px 26px 40px; background: var(--soft-2); border-radius: 26px 0 0 0; }
.crumb { display: flex; align-items: center; gap: 8px; font-size: 0.76rem; color: var(--muted); }
.crumb span.lnk { color: var(--src); cursor: pointer; }
.page-title { font-size: 2.8rem; font-weight: 500; margin: 14px 0 18px; line-height: 1.05; }
.page-desc { font-size: 0.9rem; color: var(--body); max-width: 640px; line-height: 1.6; margin: -6px 0 20px; }
.toolbar { display: flex; align-items: center; justify-content: space-between; gap: 14px; flex-wrap: wrap; margin-bottom: 14px; }
.pills { display: flex; gap: 6px; flex-wrap: wrap; }
.pill { padding: 8px 14px; border-radius: 999px; border: none; background: transparent; font-size: 0.8rem; font-weight: 500; color: var(--ink); cursor: pointer; }
.pill:hover { background: var(--soft); }
.pill.on { background: var(--ink); color: #fff; }
.search-in { display: flex; align-items: center; gap: 8px; font-size: 0.8rem; color: var(--muted); }
.search-in input { border: none; outline: none; background: transparent; font-family: inherit; font-size: 0.8rem; color: var(--ink); width: 200px; text-align: right; }
.subfilters { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; padding: 12px 0 18px; border-bottom: 1px solid var(--line); margin-bottom: 22px; }
.select {
    appearance: none;
    padding: 8px 30px 8px 13px;
    border-radius: 999px;
    border: none;
    background: var(--soft) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 24 24' fill='none' stroke='%230F1115' stroke-width='2.5'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E") no-repeat right 12px center;
    font-family: inherit;
    font-size: 0.76rem;
    font-weight: 500;
    color: var(--ink);
    cursor: pointer;
    outline: none;
}
.count { margin-left: auto; font-size: 0.74rem; color: var(--muted); }

.top-block { display: grid; grid-template-columns: 1.45fr 1fr; gap: 22px; margin-bottom: 28px; }
.top-block .big-card { height: 420px; }
.top-block .stack { display: flex; flex-direction: column; gap: 22px; }
.top-block .card-img { height: 140px; }

.feed { display: flex; flex-direction: column; gap: 18px; }
.feed-card { background: var(--soft-2); border-radius: var(--r-xl); padding: 24px 28px; }
.feed-card .top-row { display: flex; justify-content: space-between; align-items: center; gap: 10px; }
.feed-card h3 { font-size: 1.3rem; font-weight: 500; line-height: 1.25; margin: 10px 0 12px; cursor: pointer; }
.feed-card h3:hover { color: var(--purple-deep); }
.feed-card p { font-size: 0.86rem; line-height: 1.65; color: var(--body); }
.feed-actions { display: flex; justify-content: space-between; align-items: center; margin-top: 18px; gap: 10px; flex-wrap: wrap; }
.feed-actions .left { display: flex; gap: 8px; flex-wrap: wrap; }

.ai-note { margin-top: 12px; padding: 12px 14px; background: #fff; border-radius: var(--r-md); font-size: 0.84rem; line-height: 1.55; color: var(--ink); border-left: 3px solid var(--purple); }
.ai-note b { display: block; font-size: 0.68rem; letter-spacing: 0.06em; text-transform: uppercase; color: var(--purple-deep); margin-bottom: 3px; }

.tag-cloud { display: flex; gap: 8px; flex-wrap: wrap; }
.tag-cloud button { padding: 8px 14px; border-radius: 999px; border: none; background: var(--soft); font-size: 0.78rem; font-weight: 500; color: var(--ink); cursor: pointer; }
.page-side .tag-cloud button { background: #fff; }
.tag-cloud button:hover { color: var(--purple-deep); }

.pager { display: flex; justify-content: center; align-items: center; gap: 12px; margin-top: 26px; font-size: 0.78rem; color: var(--muted); }

.empty { padding: 40px; text-align: center; color: var(--body); background: var(--soft-2); border-radius: var(--r-xl); font-size: 0.9rem; }

/* ---------- Reader ---------- */
.reader-bar {
    position: sticky;
    top: 74px;
    z-index: 40;
    display: grid;
    grid-template-columns: 140px 1fr auto;
    align-items: center;
    gap: 16px;
    padding: 12px 30px;
    background: var(--soft-2);
}
.reader-bar .back { background: none; border: none; display: inline-flex; align-items: center; gap: 8px; font-size: 0.84rem; font-weight: 500; cursor: pointer; color: var(--ink); }
.reader-bar .rb-title { font-size: 0.84rem; font-weight: 500; text-align: center; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.reader-bar .rb-actions { display: flex; gap: 8px; }
.rb-progress { position: absolute; left: 0; bottom: 0; height: 2px; width: 0; background: var(--purple); transition: width 0.1s linear; }

.reader { display: grid; grid-template-columns: 1fr 340px; gap: 0; }
.reader-main { padding: 26px 30px 40px; }
.reader-main h1 { font-size: 2.3rem; font-weight: 500; line-height: 1.14; margin: 12px 0 4px; }
.reader-img { width: 100%; aspect-ratio: 16 / 9; max-height: 420px; border-radius: var(--r-xl); overflow: hidden; margin: 22px 0; }
.notice { display: flex; justify-content: space-between; align-items: center; gap: 14px; padding: 14px 18px; border-radius: var(--r-lg); background: var(--soft-2); font-size: 0.8rem; color: var(--body); line-height: 1.5; margin-bottom: 22px; flex-wrap: wrap; }
.notice b { color: var(--ink); font-weight: 600; }
.notice .terms { display: block; font-size: 0.72rem; color: var(--muted); margin-top: 2px; }
.reader-body { font-size: 1rem; line-height: 1.75; color: var(--body); }
.quote { display: grid; grid-template-columns: 36px 1fr; gap: 10px; margin: 26px 0; }
.quote .mark { font-family: 'Inter Tight', sans-serif; font-size: 3rem; line-height: 0.8; color: var(--purple); font-weight: 700; }
.quote .q-label { font-size: 0.68rem; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; color: var(--purple-deep); margin-bottom: 4px; }
.quote .q-text { font-family: 'Inter Tight', sans-serif; font-size: 1.12rem; font-weight: 500; line-height: 1.5; color: var(--ink); }
.reader-actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px; }
.prevnext { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-top: 34px; padding-top: 22px; border-top: 1px solid var(--line); }
.prevnext .pn { cursor: pointer; }
.prevnext .pn.r { text-align: right; }
.prevnext .pn small { font-size: 0.74rem; color: var(--muted); }
.prevnext .pn div { font-size: 0.9rem; font-weight: 500; margin-top: 4px; line-height: 1.35; }
.prevnext .pn:hover div { color: var(--purple-deep); }

/* ---------- Tools ---------- */
.stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 22px; }
.stat { background: var(--soft-2); border-radius: var(--r-lg); padding: 16px 18px; }
.stat small { font-size: 0.72rem; color: var(--muted); }
.stat div { font-family: 'Inter Tight', sans-serif; font-size: 1.6rem; font-weight: 500; margin-top: 4px; }

.cluster-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 18px; }
.cluster { background: var(--soft-2); border-radius: var(--r-xl); padding: 22px; display: flex; flex-direction: column; gap: 12px; }
.cluster .head { display: flex; justify-content: space-between; align-items: center; font-size: 0.74rem; color: var(--muted); gap: 8px; }
.cluster h4 { font-size: 1.05rem; font-weight: 500; line-height: 1.3; }
.cluster .row { display: flex; gap: 10px; align-items: baseline; font-size: 0.8rem; line-height: 1.4; padding: 8px 0; border-top: 1px solid var(--line); cursor: pointer; }
.cluster .row b { color: var(--src); font-weight: 500; white-space: nowrap; }
.cluster .row:hover span { color: var(--purple-deep); }

.tray { display: flex; justify-content: space-between; align-items: center; gap: 14px; flex-wrap: wrap; padding: 16px 18px; border-radius: var(--r-lg); background: var(--soft-2); margin-bottom: 22px; }
.tray .sel { display: flex; gap: 6px; flex-wrap: wrap; }

.result { border-radius: var(--r-xl); padding: 24px 26px; background: #fff; border: 1px solid var(--line); margin-bottom: 24px; box-shadow: 0 8px 28px rgba(30, 40, 90, 0.05); }
.result.warn { background: #FFFBF0; border-color: #F5D9A0; }
.result .status { display: inline-flex; align-items: center; gap: 8px; font-size: 0.72rem; font-weight: 600; letter-spacing: 0.05em; text-transform: uppercase; margin-bottom: 12px; }
.result .status i { width: 7px; height: 7px; border-radius: 50%; background: #22C55E; }
.result.warn .status i { background: #F59E0B; }
.result .answer { font-size: 0.94rem; line-height: 1.72; color: var(--ink); }
.result .answer p { margin: 0 0 12px; }
.result .answer .synth-bullet { display: flex; gap: 10px; align-items: baseline; padding: 8px 12px; margin: 6px 0; border-radius: 12px; background: var(--soft-2); font-size: 0.87rem; line-height: 1.58; }
.result .answer .synth-note { font-size: 0.78rem; color: var(--muted); margin-top: 10px; font-style: italic; }
.result h5 { font-size: 0.72rem; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); margin: 20px 0 10px; }

/* Inline clickable citation badge inside AI synthesis */
.inline-cite {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 2px 8px 2px 5px;
    margin: 0 2px;
    border-radius: 999px;
    border: 1px solid #D9E0EE;
    background: #fff;
    font-family: 'Inter', sans-serif;
    font-size: 0.71rem;
    font-weight: 600;
    color: var(--ink);
    cursor: pointer;
    vertical-align: baseline;
    transition: border-color 0.15s, transform 0.12s, background 0.15s;
}
.inline-cite:hover { border-color: var(--purple); background: var(--lav); color: var(--purple-deep); transform: translateY(-1px); }

.outlet-strip { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 14px; padding-bottom: 12px; border-bottom: 1px solid var(--line); }
.outlet-strip .os-label { font-size: 0.7rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); margin-right: 4px; }
.outlet-pill { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px 4px 6px; border-radius: 999px; background: var(--soft); font-size: 0.73rem; font-weight: 500; color: var(--ink); }

/* Home & Search Multi-Source AI Briefing Bar */
.briefing-bar {
    margin: 0 30px 26px;
    padding: 20px 24px;
    border-radius: var(--r-xl);
    background: radial-gradient(circle at 90% 10%, rgba(196, 181, 253, 0.32), transparent 55%), var(--soft-2);
    border: 1px solid var(--line);
}
.briefing-top { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; margin-bottom: 12px; }
.briefing-top .b-title { display: flex; align-items: center; gap: 10px; }
.briefing-top h3 { font-size: 1.05rem; font-weight: 500; }
.briefing-top p { font-size: 0.78rem; color: var(--body); }
.briefing-controls { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.briefing-controls input { flex: 1; min-width: 240px; padding: 12px 18px; border-radius: 999px; border: 1px solid var(--line); background: #fff; font-family: inherit; font-size: 0.86rem; color: var(--ink); outline: none; }
.briefing-controls input:focus { border-color: var(--purple); }
.briefing-topics { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 10px; }
.briefing-topics span { font-size: 0.72rem; color: var(--muted); font-weight: 500; }
.briefing-topics button { padding: 5px 12px; border-radius: 999px; border: 1px solid var(--line); background: #fff; font-size: 0.74rem; font-weight: 500; color: var(--ink); cursor: pointer; transition: all 0.15s; }
.briefing-topics button:hover { border-color: var(--purple); color: var(--purple-deep); background: var(--lav); }

.cite { border-radius: var(--r-lg); background: var(--soft-2); padding: 16px 18px; margin-bottom: 10px; }
.cite .c-top { display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap; }
.cite .c-title { font-size: 0.92rem; font-weight: 500; margin: 8px 0 6px; cursor: pointer; }
.cite .c-title:hover { color: var(--purple-deep); }
.cite .c-ex { display: grid; grid-template-columns: 20px 1fr; gap: 6px; font-size: 0.82rem; line-height: 1.55; color: var(--body); }
.cite .c-ex span:first-child { font-family: 'Inter Tight', sans-serif; font-size: 1.5rem; line-height: 1; color: var(--purple); font-weight: 700; }
.cite .c-foot { display: flex; justify-content: space-between; align-items: center; gap: 10px; margin-top: 10px; flex-wrap: wrap; }

.ask-box { display: flex; gap: 10px; margin-bottom: 14px; }
.ask-box input { flex: 1; padding: 15px 22px; border-radius: 999px; border: 1px solid transparent; background: var(--soft); font-family: inherit; font-size: 0.92rem; outline: none; }
.ask-box input:focus { background: #fff; border-color: #CBD5E6; }

.table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
.table th { text-align: left; font-size: 0.7rem; font-weight: 600; letter-spacing: 0.05em; text-transform: uppercase; color: var(--muted); padding: 10px 14px; border-bottom: 1px solid var(--line); }
.table td { padding: 14px; border-bottom: 1px solid var(--line); vertical-align: top; }
.table td small { display: block; font-size: 0.7rem; color: var(--muted); margin-top: 3px; word-break: break-all; }
.ok { display: inline-flex; align-items: center; gap: 6px; font-size: 0.74rem; font-weight: 500; color: #15803D; }
.ok::before { content: ''; width: 6px; height: 6px; border-radius: 50%; background: #22C55E; }
.bad { display: inline-flex; align-items: center; gap: 6px; font-size: 0.74rem; font-weight: 500; color: #B91C1C; }
.bad::before { content: ''; width: 6px; height: 6px; border-radius: 50%; background: #EF4444; }

.eval-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; }
.eval { background: var(--soft-2); border-radius: var(--r-xl); padding: 20px 22px; }
.eval .head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.eval .q { font-family: 'Inter Tight', sans-serif; font-size: 0.98rem; font-weight: 500; line-height: 1.35; }
.eval .exp { font-size: 0.74rem; color: var(--muted); margin: 8px 0; }
.eval .prev { font-size: 0.8rem; line-height: 1.55; color: var(--body); background: #fff; padding: 10px 12px; border-radius: var(--r-md); }
.eval .checks { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 12px; font-size: 0.72rem; color: var(--body); }

/* ---------- Footer ---------- */
.footer { margin: 30px; padding: 34px 34px 26px; background: var(--soft-2); border-radius: var(--r-xl); }
.f-cols { display: grid; grid-template-columns: repeat(4, 1fr) 1.4fr; gap: 24px; }
.f-col h5 { font-size: 0.78rem; font-weight: 600; margin-bottom: 14px; }
.f-col ul { list-style: none; display: flex; flex-direction: column; gap: 10px; }
.f-col li { font-size: 0.78rem; color: var(--body); cursor: pointer; }
.f-col li:hover { color: var(--purple-deep); }
.f-ask { display: flex; align-items: center; gap: 8px; background: #fff; border-radius: var(--r-lg); padding: 8px 8px 8px 16px; }
.f-ask input { flex: 1; border: none; outline: none; font-family: inherit; font-size: 0.8rem; background: transparent; }
.f-note { font-size: 0.74rem; color: var(--muted); margin-top: 14px; line-height: 1.5; }
.f-bottom { display: flex; justify-content: space-between; align-items: center; margin-top: 34px; padding-top: 20px; border-top: 1px solid var(--line); font-size: 0.74rem; color: var(--muted); gap: 12px; flex-wrap: wrap; }
.f-logo { display: inline-flex; align-items: center; gap: 8px; font-family: 'Inter Tight', sans-serif; font-weight: 600; font-size: 1.05rem; color: var(--ink); }

.tray-fab { position: fixed; right: 30px; bottom: 26px; z-index: 60; display: none; align-items: center; gap: 10px; padding: 11px 18px; border-radius: 999px; background: var(--ink); color: #fff; font-size: 0.8rem; font-weight: 500; cursor: pointer; box-shadow: 0 12px 30px rgba(15,17,21,0.25); border: none; }
.tray-fab b { background: var(--purple); padding: 2px 8px; border-radius: 999px; font-size: 0.72rem; }

@media (max-width: 1080px) {
    .hero, .trending, .page, .reader, .picks, .top-block { grid-template-columns: 1fr; }
    .hero-top { grid-template-columns: 1fr; }
    .grid3, .row5 { grid-template-columns: repeat(2, 1fr); }
    .featured { height: auto; }
    .feat-media, .feat-panel, .feat-tab { position: relative; inset: auto; width: auto; }
    .feat-media { height: 320px; }
    .f-cols, .stats, .cluster-grid, .eval-grid { grid-template-columns: 1fr 1fr; }
    .search { width: 200px; }
}
</style>
</head>
<body>

<div class="shell">
    <nav class="nav">
        <div class="nav-left">
            <button class="logo-pill" onclick="setView('home')">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 16V8l-9-5-9 5v8l9 5 9-5z"/><path d="M3.3 7L12 12l8.7-5M12 22V12"/></svg>
                __APP_NAME__
            </button>
            <button class="nav-pill" data-view="home" onclick="setView('home')">All <span class="plus">+</span></button>
            <button class="nav-pill" data-view="news" onclick="openCategory('All')">News <span class="plus">+</span></button>
            <button class="nav-pill" data-view="clusters" onclick="setView('clusters')">Clusters <span class="plus">+</span></button>
            <button class="nav-pill" data-view="ask" onclick="setView('ask')">Ask the archive <span class="plus">+</span></button>
            <button class="nav-pill" data-view="feeds" onclick="setView('feeds')">Feeds <span class="plus">+</span></button>
            <button class="nav-pill" data-view="eval" onclick="setView('eval')">Evaluation <span class="plus">+</span></button>
        </div>
        <div class="nav-right">
            <button class="live" onclick="triggerLiveSync()" title="Click to refresh feeds now.">
                <span class="live-dot"></span><span id="live-text">Live</span>
            </button>
            <div class="search">
                <input id="global-search" type="text" placeholder="Article name, tag, category..." oninput="handleGlobalSearch(this.value)" />
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>
            </div>
        </div>
    </nav>

    <main id="main-view"></main>
    <footer id="footer"></footer>
</div>

<button class="tray-fab" id="tray-fab" onclick="setView('clusters')">Compare coverage <b id="tray-count">0</b></button>

<script>
const API = __API_URL_JSON__;
const INITIAL = __INITIAL_DATA__;
const APP_NAME = (INITIAL.stats && INITIAL.stats.app_name) || "Newsroom";
document.title = `${APP_NAME} — Newsroom`;

const ICON_ARROW = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M13 6l6 6-6 6"/></svg>';
const ICON_LEFT = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 12H5M11 6l-6 6 6 6"/></svg>';
const ICON_EXT = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M7 17L17 7M8 7h9v9"/></svg>';
const ICON_SEARCH = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>';

let state = {
    view: "home",
    prevView: "home",
    articles: INITIAL.articles || [],
    stats: INITIAL.stats || {},
    clusters: INITIAL.clusters || [],
    evaluation: INITIAL.evaluation || {},
    heroList: [],
    heroIndex: 0,
    trendPage: 0,
    rowPage: 0,
    page: 0,
    filterSource: "All",
    filterCategory: "All",
    filterTag: "All",
    filterDate: "All",
    searchQuery: "",
    searchResults: null,
    currentArticleId: null,
    compareIds: [],
    analyzeResult: null,
    askResult: null,
    lastQuestion: "",
    logos: INITIAL.logos || {},
    homeBriefingQuery: "",
    homeBriefingResult: null,
    homeBriefingShowCites: false,
    searchBriefingResult: null,
    searchBriefingShowCites: false,
};

/* ---------- helpers ---------- */
function esc(s) {
    if (s === null || s === undefined) return "";
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}
function jsq(s) { return esc(JSON.stringify(String(s))); }
function hasPhoto(a) {
    if (!a || !a.image_url || !a.image_url.startsWith("http")) return false;
    if (a.image_url.includes("/ALUVA") || a.image_url.includes("default_thumb")) return false;
    return true;
}
function findArt(id) { return state.articles.find(a => a.id === id) || (state.searchResults || []).find(a => a.id === id); }

function getOutletMeta(src) {
    if (!src) return { short: "Source", slug: "" };
    const meta = (state.stats.outlet_metadata || {})[src] || {};
    return { short: meta.short || src, slug: meta.slug || "" };
}

function shortSource(src) {
    return getOutletMeta(src).short;
}

/* Use a bundled publisher logo when available, with initials for any other source. */
function outletLogo(src, size) {
    const s = size || 16;
    const meta = getOutletMeta(src);
    const b64 = (state.logos || {})[meta.slug];
    const imgSrc = b64 || "";
    if (imgSrc) {
        return `<span class="outlet-logo" style="width:${s}px;height:${s}px;" title="${esc(src)}"><img src="${imgSrc}" alt="${esc(src)}" width="${s}" height="${s}" onerror="this.style.display='none'" /></span>`;
    }
    return `<span class="outlet-logo" style="width:${s}px;height:${s}px;background:var(--soft);" title="${esc(src)}"><span style="font-size:0.6rem;font-weight:700;">${esc(src.slice(0, 2))}</span></span>`;
}

function relTime(v) {
    const ts = Date.parse(v || "");
    if (isNaN(ts)) return "Just in";
    const min = Math.max(1, Math.round((Date.now() - ts) / 60000));
    if (min < 60) return min + " min ago";
    const hr = Math.round(min / 60);
    if (hr < 24) return hr + (hr === 1 ? " hour ago" : " hours ago");
    const d = Math.round(hr / 24);
    return d + (d === 1 ? " day ago" : " days ago");
}

function fmtTime(v) {
    const d = new Date(v || "");
    if (isNaN(d.getTime())) return v ? String(v).slice(0, 18) : "Unknown";
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" }) + ", " + d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });
}

function getTags(a) {
    const list = [];
    if (a.category) list.push(a.category);
    (a.tags || "").split(",").forEach(t => { const c = t.trim(); if (c && !list.includes(c)) list.push(c); });
    return list.slice(0, 3);
}

function meta(a) {
    return `<div class="meta"><span class="src">${outletLogo(a.source, 15)}${esc(a.source)}</span><span class="sep">•</span><span>${esc(relTime(a.published_iso || a.published))}</span></div>`;
}

function hashtags(a, n) {
    return `<div class="hashtags">${getTags(a).slice(0, n || 2).map(t => `<span onclick="event.stopPropagation(); filterTag(${jsq(t)})">#${esc(t.replace(/ /g, ""))}</span>`).join("")}</div>`;
}

function excerptChip(a) {
    return a.is_excerpt ? `<span class="excerpt-chip" title="The RSS feed only provides a short excerpt. Open the publisher for the full story.">Excerpt · ${a.word_count || 0} words</span>` : "";
}

function coverHtml(a, cls) {
    const src = a.source || "Wire";
    return `<div class="${cls} cover"><div class="cov-mark">${outletLogo(src, 28)}</div><div class="cov-name">${esc(shortSource(src))}</div></div>`;
}
function coverById(id, cls) { return coverHtml(findArt(id) || {}, cls); }

function thumb(a, cls) {
    if (hasPhoto(a)) {
        return `<img class="${cls}" src="${esc(a.image_url)}" alt="" loading="lazy" onerror="this.outerHTML=coverById(${a.id}, '${cls}')" />`;
    }
    return coverHtml(a, cls);
}

/* Edge-to-edge 16:9 photo renderer with zero top/bottom letterbox space */
function photoInner(a) {
    if (hasPhoto(a)) {
        const src = esc(a.image_url);
        return `<div class="ph"><img class="ph-fg" src="${src}" alt="" onerror="this.parentNode.outerHTML=fallbackCover(${a.id})" /></div>`;
    }
    return fallbackCoverHtml(a);
}
function fallbackCoverHtml(a) {
    return `<div class="photo-fallback"><span class="pf-source" style="display:inline-flex;align-items:center;gap:8px;">${outletLogo(a.source, 20)}${esc(a.source)}</span><span class="pf-quote">${esc(a.title)}</span></div>`;
}
function fallbackCover(id) { return fallbackCoverHtml(findArt(id) || {}); }

function listItem(a) {
    return `<div class="li" onclick="openArticle(${a.id})"><div>${meta(a)}<h4>${esc(a.title)}</h4></div>${thumb(a, "li-thumb")}</div>`;
}

function card(a) {
    return `<article class="card" onclick="openArticle(${a.id})"><div class="card-img">${thumb(a, "fill")}</div>${meta(a)}<h4>${esc(a.title)}</h4>${hashtags(a)}</article>`;
}

function bigCard(a) {
    return `<div class="big-card" onclick="openArticle(${a.id})">
        ${thumb(a, "fill")}<div class="shade"></div>
        <div class="top on-dark">${meta(a)}</div>
        <div class="bottom on-dark"><h3>${esc(a.title)}</h3>${hashtags(a)}</div>
    </div>`;
}

function readBtn(id, label, cls) {
    return `<button class="read-btn ${cls || ""}" onclick="event.stopPropagation(); openArticle(${id})">${label || "Read article"} <span class="arr">${ICON_ARROW}</span></button>`;
}

function compareChip(id) {
    const on = state.compareIds.includes(id);
    return `<button class="chip ${on ? "on" : ""}" onclick="toggleCompare(${id}, event)">${on ? "✓ Comparing" : "+ Compare"}</button>`;
}

/* ---------- navigation ---------- */
function setView(v, articleId) {
    if (v === "reader" && state.view !== "reader") state.prevView = state.view;
    state.view = v;
    if (articleId !== undefined && articleId !== null) state.currentArticleId = articleId;
    document.querySelectorAll(".nav-pill").forEach(b => b.classList.toggle("active", b.dataset.view === v));
    render();
    window.scrollTo({ top: 0, behavior: "auto" });
    if (v === "feeds") {
        refreshLiveStats();
    }
}
function openArticle(id) { setView("reader", id); }
function goBack() { setView(state.prevView && state.prevView !== "reader" ? state.prevView : "home"); }

function openCategory(c) {
    state.filterCategory = c; state.page = 0;
    setView("news");
}
function openSource(s) { state.filterSource = s; state.filterCategory = "All"; state.page = 0; setView("news"); }
function filterTag(t) { state.filterTag = t; state.page = 0; setView("news"); }
function resetFilters() {
    Object.assign(state, { filterSource: "All", filterCategory: "All", filterTag: "All", filterDate: "All", searchQuery: "", searchResults: null, searchBriefingResult: null, searchBriefingShowCites: false, page: 0 });
    const g = document.getElementById("global-search"); if (g) g.value = "";
    render();
}

function toggleCompare(id, ev) {
    if (ev) ev.stopPropagation();
    const i = state.compareIds.indexOf(id);
    if (i >= 0) state.compareIds.splice(i, 1); else state.compareIds.push(id);
    render();
}

/* Format AI synthesis text with bolding, bullets, and clickable inline [Source, #ID] badges */
function formatCitedAnswer(raw) {
    if (!raw) return "";
    let safe = esc(raw);
    safe = safe.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    safe = safe.replace(/\*([^*\n]+)\*/g, "<em>$1</em>");
    safe = safe.replace(/\[([^\],#]+?)(?:,\s*|\s+)#(\d+)\]/g, (_, src, id) => {
        const sClean = src.trim();
        return `<button class="inline-cite" onclick="event.stopPropagation(); openArticle(${Number(id)})" title="Open ${esc(sClean)} article #${id}">${outletLogo(sClean, 12)}<span>${esc(shortSource(sClean))} #${id}</span></button>`;
    });
    const blocks = safe.split(/\n\n+/);
    return blocks.map(b => {
        const trimmed = b.trim();
        if (trimmed.startsWith("•")) {
            return trimmed.split(/\n+/).map(line => `<div class="synth-bullet">${line.replace(/^•\s*/, "<span>•</span><div>")}</div></div>`).join("");
        }
        if (trimmed.startsWith("<em>Verification Note")) {
            return `<div class="synth-note">${trimmed}</div>`;
        }
        return `<p>${trimmed.replace(/\n/g, "<br/>")}</p>`;
    }).join("");
}

/* Client-side multi-outlet synthesis fallback when FastAPI backend is offline */
function synthesizeLocally(query) {
    const stop = new Set(["the","and","for","with","what","how","why","who","are","about","from","into","that","this","have","has","was","were","tell","summarize","summary","all","sources","latest","reports","happening","happened"]);
    const qTerms = String(query || "").toLowerCase().match(/[a-z0-9]{3,}/g)?.filter(w => !stop.has(w)).map(w => w.replace(/(?:ing|es|s)$/, "")) || [];
    if (!qTerms.length) {
        return { insufficient_evidence: true, answer: "Please enter a few topic keywords so the archive can find matching stories.", outlets_synthesized: [], citations: [] };
    }
    const scored = [];
    for (const a of state.articles) {
        const hay = `${a.title || ""} ${a.content || ""} ${a.tags || ""} ${a.source || ""}`.toLowerCase();
        const hits = qTerms.filter(t => hay.includes(t));
        if (hits.length > 0) scored.push({ a, hits: hits.length });
    }
    scored.sort((x, y) => y.hits - x.hits || y.a.id - x.a.id);
    const maxHits = scored.length ? scored[0].hits : 0;
    if (!scored.length || (qTerms.length >= 2 && maxHits < Math.min(2, qTerms.length))) {
        return {
            insufficient_evidence: true,
            answer: `Insufficient evidence in the local archive: None of the stored articles contain verified reporting on '${query}'. The newsroom assistant will not speculate beyond stored sources.`,
            outlets_synthesized: [],
            citations: [],
        };
    }
    /* Diversify across outlets first */
    const firstPass = [], remainder = [], seen = new Set();
    for (const item of scored) {
        if (!seen.has(item.a.source)) { seen.add(item.a.source); firstPass.push(item.a); }
        else remainder.push(item.a);
    }
    const top = firstPass.concat(remainder).slice(0, 8);
    const outlets = Array.from(new Set(top.map(a => a.source)));
    const clauses = top.slice(0, outlets.length || 4).map(a => {
        const t = (a.title || "").trim().replace(/\.$/, "");
        const c = (a.content || "").trim().split(/(?<=[.!?])\s+/)[0] || "";
        return c && c.toLowerCase() !== t.toLowerCase()
            ? `${a.source} reports that ${t} (${c}) [${a.source}, #${a.id}].`
            : `${a.source} highlights "${t}" [${a.source}, #${a.id}].`;
    });
    const answer = `**Multi-Source Synthesis (${top.length} dispatches across ${outlets.length} ${outlets.length === 1 ? "outlet" : "outlets"}: ${outlets.join(", ")}):** ${clauses.join(" ")}\n\n**Supporting Dispatches by Outlet:**\n` +
        top.slice(0, 6).map(a => `• [${a.source}, #${a.id}] **${a.title}** — ${(a.content || a.title || "").trim()}`).join("\n\n") +
        `\n\n*Verification Note: Stored records are RSS feed excerpts. Click any inline citation or open the original publisher links below to verify full context.*`;
    const citations = top.map(a => ({
        id: a.id, title: a.title, source: a.source, url: a.url,
        published_iso: a.published_iso || a.published, retrieved_at: a.retrieved_at,
        excerpt: (a.content || a.title || "").slice(0, 240),
        completeness_note: `RSS Excerpt (${a.word_count || 0} words) — Verify full text at ${a.source}`,
    }));
    return { answer, insufficient_evidence: false, outlets_synthesized: outlets, citations };
}

async function fetchTopicSynthesis(q) {
    try {
        const r = await fetch(`${API}/ask`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: q.trim(), limit: 12 }) });
        if (!r.ok) throw new Error();
        return await r.json();
    } catch (e) {
        return synthesizeLocally(q.trim());
    }
}

function renderBriefingCard(res, queryLabel, showCites, toggleExpr, closeExpr) {
    if (!res) return "";
    const outlets = res.outlets_synthesized && res.outlets_synthesized.length
        ? res.outlets_synthesized
        : Array.from(new Set((res.citations || []).map(c => c.source)));
    return `
    <div class="result ${res.insufficient_evidence ? "warn" : ""}" style="margin-top:14px;">
        <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;">
            <div class="status" style="margin-bottom:0;"><i></i>${res.insufficient_evidence ? "Not enough evidence in the archive" : `AI Multi-Source Synthesis · ${res.citations ? res.citations.length : 0} cited dispatches across ${outlets.length} ${outlets.length === 1 ? "outlet" : "outlets"}`}</div>
            <div style="display:flex;gap:8px;align-items:center;">
                ${!res.insufficient_evidence && res.citations && res.citations.length && toggleExpr ? `<button class="chip" onclick="${toggleExpr}">${showCites ? "Hide source excerpts ▴" : `Inspect ${res.citations.length} source excerpts ▾`}</button>` : ""}
                ${closeExpr ? `<button class="chip" onclick="${closeExpr}">✕</button>` : ""}
            </div>
        </div>
        ${outlets.length ? `
        <div class="outlet-strip" style="margin-top:12px;">
            <span class="os-label">Synthesized from:</span>
            ${outlets.map(o => `<span class="outlet-pill">${outletLogo(o, 14)}${esc(o)}</span>`).join("")}
        </div>` : `<div style="margin-top:12px;"></div>`}
        <div class="answer">${formatCitedAnswer(res.answer)}</div>
        ${showCites && res.citations && res.citations.length ? `<h5>Verified Supporting Excerpts & Publisher Links</h5>${res.citations.map(citeCard).join("")}` : ""}
    </div>`;
}

async function runHomeBriefing(q) {
    const query = (q || "").trim();
    if (!query) return;
    state.homeBriefingQuery = query;
    const inp = document.getElementById("home-brief-in");
    if (inp) inp.value = query;
    const btn = document.getElementById("home-brief-btn");
    if (btn) btn.firstChild.textContent = "Synthesizing... ";
    state.homeBriefingResult = await fetchTopicSynthesis(query);
    render();
}

let searchTimer = null;
function handleGlobalSearch(val) {
    state.searchQuery = val; state.page = 0;
    clearTimeout(searchTimer);
    searchTimer = setTimeout(async () => {
        const clean = val.trim();
        if (!clean) { state.searchResults = null; state.searchBriefingResult = null; if (state.view === "news") render(); return; }
        const synthPromise = fetchTopicSynthesis(clean);
        try {
            const r = await fetch(`${API}/search`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query: clean, limit: 60 }) });
            if (r.ok) state.searchResults = await r.json();
        } catch (e) {
            const q = clean.toLowerCase();
            state.searchResults = state.articles.filter(a => (a.title + " " + a.content + " " + (a.tags || "")).toLowerCase().includes(q));
        }
        state.searchBriefingResult = await synthPromise;
        if (state.view !== "news") setView("news"); else render();
    }, 250);
}

async function refreshLiveStats() {
    try {
        const s = await fetch(`${API}/stats`);
        if (s.ok) {
            state.stats = await s.json();
            if (state.view === "feeds") render();
        }
    } catch (e) {}
}

async function triggerLiveSync(silent) {
    const el = document.getElementById("live-text");
    if (!silent && el) el.textContent = "Refreshing...";
    try {
        const r = await fetch(`${API}/ingest`, { method: "POST" });
        if (!r.ok) throw new Error();
        const d = await r.json();
        const [s, a, c] = await Promise.all([fetch(`${API}/stats`), fetch(`${API}/articles?limit=150`), fetch(`${API}/clusters`)]);
        if (s.ok) state.stats = await s.json();
        if (a.ok) state.articles = await a.json();
        if (c.ok) state.clusters = await c.json();
        if (el) el.textContent = d.total ? `Live · +${d.total} new` : "Live · up to date";
        renderFooter(); render();
    } catch (e) {
        if (!silent && el) el.textContent = "Backend offline";
    }
}

// Use refresh settings returned by the backend.
const STATUS_REFRESH_MS = Math.max(1000, Number(state.stats.status_refresh_seconds || 25) * 1000);
const liveFeed = state.stats.live_feed || {};
setInterval(refreshLiveStats, STATUS_REFRESH_MS);
if (liveFeed.enabled !== false) {
    const FEED_REFRESH_MS = Math.max(1000, Number(liveFeed.interval_seconds || 180) * 1000);
    setInterval(() => triggerLiveSync(true), FEED_REFRESH_MS);
}

async function summarizeArticle(id, btn) {
    if (btn) btn.textContent = "Summarizing...";
    try {
        const r = await fetch(`${API}/articles/${id}/summarize`, { method: "POST" });
        const d = await r.json();
        if (!r.ok) throw new Error(d.detail || "Failed");
        const a = findArt(id); if (a) a.summary = d.summary;
        render();
    } catch (e) {
        if (btn) btn.textContent = "Start the backend to summarize";
    }
}

function getFiltered() {
    let list = state.searchResults !== null ? state.searchResults : state.articles;
    if (state.filterSource !== "All") list = list.filter(a => a.source === state.filterSource);
    if (state.filterCategory !== "All") list = list.filter(a => (a.category || "").toLowerCase() === state.filterCategory.toLowerCase());
    if (state.filterTag !== "All") list = list.filter(a => ((a.tags || "") + " " + (a.category || "") + " " + a.title).toLowerCase().includes(state.filterTag.toLowerCase()));
    if (state.filterDate !== "All") {
        const span = { "24h": 864e5, "7d": 7 * 864e5, "30d": 30 * 864e5 }[state.filterDate];
        list = list.filter(a => { const t = Date.parse(a.published_iso || a.retrieved_at || ""); return !isNaN(t) && Date.now() - t <= span; });
    }
    return list;
}

/* ---------- HOME ---------- */
let heroHover = false;

function renderHeroCard() {
    const list = state.heroList;
    if (!list.length) return "";
    const idx = state.heroIndex % list.length;
    const h = list[idx], b1 = list[(idx + 1) % list.length], b2 = list[(idx + 2) % list.length];
    const desc = (h.content || "").trim();
    return `
    <div class="hero-top">
        <div>
            <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
                <span class="label">Top story</span>${excerptChip(h)}
            </div>
            <div style="margin-top:14px;">${meta(h)}</div>
            <h1 class="hero-title" onclick="openArticle(${h.id})">${esc(h.title)}</h1>
            ${desc ? `<p class="hero-desc">${esc(desc)}</p>` : ""}
            ${hashtags(h)}
            <div style="margin-top:16px; display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
                ${readBtn(h.id)}
                ${compareChip(h.id)}
            </div>
        </div>
        <div class="photo-stack">
            ${list.length > 2 ? `<div class="photo-card back-2" onclick="setHero(${(idx + 2) % list.length})" title="${esc(b2.title)}">${photoInner(b2)}</div>` : ""}
            ${list.length > 1 ? `<div class="photo-card back-1" onclick="setHero(${(idx + 1) % list.length})" title="${esc(b1.title)}">${photoInner(b1)}</div>` : ""}
            <div class="photo-card front" onclick="openArticle(${h.id})">
                ${photoInner(h)}
                <span class="photo-count">${idx + 1} / ${list.length}</span>
                <span class="photo-chip">${outletLogo(h.source, 14)}${esc(shortSource(h.source))} · ${esc(relTime(h.published_iso || h.published))}</span>
            </div>
        </div>
    </div>
    <div class="hero-strip">
        ${list.map((s, i) => `
            <div class="item ${i === idx ? "active" : ""}" onclick="setHero(${i})">
                <span class="dash"></span>${meta(s)}<h4>${esc(s.title)}</h4>
            </div>`).join("")}
    </div>`;
}

function setHero(i) {
    state.heroIndex = i;
    const slot = document.getElementById("hero-slot");
    if (slot) slot.innerHTML = renderHeroCard();
}

setInterval(() => {
    if (state.view !== "home" || heroHover || !state.heroList.length) return;
    setHero((state.heroIndex + 1) % state.heroList.length);
}, 8000);

function buildHomeSlots() {
    const arts = state.articles;
    const photos = arts.filter(hasPhoto);
    const used = new Set();
    /* Pick Hero stories from distinct configured sources first so one feed doesn't dominate the top stack. */
    const heroOut = [];
    const seenSources = new Set();
    for (const a of photos) {
        if (heroOut.length >= 3) break;
        if (!used.has(a.id) && !seenSources.has(a.source)) { used.add(a.id); seenSources.add(a.source); heroOut.push(a); }
    }
    const take = (n, preferPhoto) => {
        const out = [];
        for (const a of (preferPhoto ? photos : arts)) { if (out.length >= n) break; if (!used.has(a.id)) { used.add(a.id); out.push(a); } }
        for (const a of arts) { if (out.length >= n) break; if (!used.has(a.id)) { used.add(a.id); out.push(a); } }
        return out;
    };
    while (heroOut.length < 3 && arts.length > heroOut.length) {
        const next = take(1, true)[0];
        if (!next) break;
        heroOut.push(next);
    }
    return {
        hero: heroOut,
        recFeature: take(1, true)[0],
        recList: take(3, false),
        trendLead: take(1, true)[0],
        trendPool: take(18, true),
        featured: take(1, true)[0],
        featuredSide: take(3, false),
        rowPool: take(15, true),
        pickLead: take(1, true)[0],
        pickList: take(8, false),
    };
}

function renderHome() {
    if (!state.articles.length) {
        return `<div class="sec"><div class="empty">No stories yet. <button class="link-btn" onclick="triggerLiveSync()">Refresh the feeds ${ICON_ARROW}</button></div></div>`;
    }
    const topicCategories = (state.stats.categories || []).filter(c => c.toLowerCase() !== "other").slice(0, 4);
    const s = buildHomeSlots();
    state.heroList = s.hero;
    if (state.heroIndex >= s.hero.length) state.heroIndex = 0;

    const tPages = Math.max(1, Math.ceil(s.trendPool.length / 6));
    const tp = Math.min(state.trendPage, tPages - 1);
    const rPages = Math.max(1, Math.ceil(s.rowPool.length / 5));
    const rp = Math.min(state.rowPage, rPages - 1);

    return `
    <section class="hero">
        <div class="hero-main" id="hero-slot" onmouseenter="heroHover=true" onmouseleave="heroHover=false">${renderHeroCard()}</div>
        <aside class="panel">
            <div class="panel-head"><h3>Recommended</h3><button class="link-btn" onclick="openCategory('All')">View all ›</button></div>
            ${s.recFeature ? `<div class="rec-feature" onclick="openArticle(${s.recFeature.id})">${thumb(s.recFeature, "fill")}<div class="shade"></div><div class="txt on-dark">${meta(s.recFeature)}<h4>${esc(s.recFeature.title)}</h4></div></div>` : ""}
            ${s.recList.map(listItem).join("")}
        </aside>
    </section>

    <section class="briefing-bar">
        <div class="briefing-top">
            <div class="b-title">
                <span class="label">AI Multi-Source Briefing</span>
                <p>Ask about any event — AI synthesizes every matching outlet and cites each source inline.</p>
            </div>
            <button class="link-btn" onclick="setView('ask')">Open full Q&amp;A workspace ${ICON_ARROW}</button>
        </div>
        <div class="briefing-controls">
            <input id="home-brief-in" type="text" value="${esc(state.homeBriefingQuery)}" placeholder="Ask AI to summarize a topic across all sources..." onkeydown="if(event.key==='Enter') runHomeBriefing(this.value)" />
            <button class="read-btn dark" id="home-brief-btn" onclick="runHomeBriefing(document.getElementById('home-brief-in').value)">Synthesize &amp; cite <span class="arr">${ICON_ARROW}</span></button>
        </div>
        <div class="briefing-topics">
            <span>Try a live topic:</span>
            ${topicCategories.map(c => `<button onclick="runHomeBriefing(${jsq(`Recent ${c.toLowerCase()} coverage`)})">${esc(c)}</button>`).join("")}
        </div>
        ${state.homeBriefingResult ? renderBriefingCard(
            state.homeBriefingResult,
            state.homeBriefingQuery,
            state.homeBriefingShowCites,
            "state.homeBriefingShowCites = !state.homeBriefingShowCites; render();",
            "state.homeBriefingResult = null; state.homeBriefingQuery = ''; render();"
        ) : ""}
    </section>

    <section class="trending">
        <div class="trend-left">
            <div class="sec-head" style="margin-bottom:22px;"><span class="label">Trending now</span><button class="link-btn" onclick="openCategory('All')">View more ${ICON_ARROW}</button></div>
            ${s.trendLead ? `
                ${meta(s.trendLead)}
                <h2 class="trend-title" onclick="openArticle(${s.trendLead.id})">${esc(s.trendLead.title)}</h2>
                ${hashtags(s.trendLead)}
                <div style="margin:24px 0 26px;">${readBtn(s.trendLead.id, "Read article", "soft")}</div>
                <div class="trend-banner" onclick="openArticle(${s.trendLead.id})">${thumb(s.trendLead, "fill")}</div>` : ""}
        </div>
        <div class="trend-right">
            <div class="grid3">${s.trendPool.slice(tp * 6, tp * 6 + 6).map(card).join("")}</div>
            <div class="arrows">
                <button class="circle" ${tp <= 0 ? "disabled" : ""} onclick="state.trendPage=${tp - 1}; render();">${ICON_LEFT}</button>
                <button class="circle dark" ${tp >= tPages - 1 ? "disabled" : ""} onclick="state.trendPage=${tp + 1}; render();">${ICON_ARROW}</button>
            </div>
        </div>
    </section>

    ${s.featured ? `
    <section style="padding-top:34px;">
        <div class="featured">
            <div class="feat-media" onclick="openArticle(${s.featured.id})">
                ${thumb(s.featured, "fill")}<div class="shade"></div>
                <div class="feat-side on-dark">
                    ${s.featuredSide.map(f => `<div class="it" onclick="event.stopPropagation(); openArticle(${f.id})">${meta(f)}<h4>${esc(f.title)}</h4></div>`).join("")}
                </div>
            </div>
            <div class="feat-tab"><span class="label">Featured news</span></div>
            <div class="feat-panel">
                ${meta(s.featured)}
                <h2 class="feat-title" onclick="openArticle(${s.featured.id})">${esc(s.featured.title)}</h2>
                ${hashtags(s.featured)}
                <div style="margin-top:22px;">${readBtn(s.featured.id)}</div>
            </div>
        </div>
    </section>` : ""}

    <section class="sec">
        <div class="sec-head"><span class="label">More from the wire</span><button class="link-btn" onclick="openCategory('All')">View more ${ICON_ARROW}</button></div>
        <div class="row5">${s.rowPool.slice(rp * 5, rp * 5 + 5).map(card).join("")}</div>
        <div class="arrows">
            <button class="circle" ${rp <= 0 ? "disabled" : ""} onclick="state.rowPage=${rp - 1}; render();">${ICON_LEFT}</button>
            <button class="circle dark" ${rp >= rPages - 1 ? "disabled" : ""} onclick="state.rowPage=${rp + 1}; render();">${ICON_ARROW}</button>
        </div>
    </section>

    ${s.pickLead ? `
    <section class="sec" style="padding-top:6px;">
        <div class="sec-head"><span class="label">Editor's picks</span><button class="link-btn" onclick="openCategory('All')">View more ${ICON_ARROW}</button></div>
        <div class="picks">
            ${bigCard(s.pickLead)}
            <div class="picks-list">${s.pickList.map(listItem).join("")}</div>
        </div>
    </section>` : ""}
    `;
}

/* ---------- NEWS (category page) ---------- */
function sidePanel(excludeId) {
    const rec = state.articles.filter(a => a.id !== excludeId && hasPhoto(a)).slice(0, 4);
    const tags = (state.stats.top_tags || []).slice(0, 14);
    return `
        <span class="label">Recommended</span>
        <div style="margin:14px 0 30px;">${rec.map(listItem).join("")}</div>
        <span class="label">More news</span>
        <div class="tag-cloud" style="margin-top:16px;">${tags.map(t => `<button onclick="filterTag(${jsq(t)})">${esc(t)}</button>`).join("")}</div>`;
}

function renderNews() {
    const list = getFiltered();
    const cats = Object.keys(state.stats.by_category || {});
    const sources = Object.keys(state.stats.by_source || {});
    const tags = (state.stats.top_tags || []).slice(0, 20);
    if (state.filterTag !== "All" && !tags.includes(state.filterTag)) tags.unshift(state.filterTag);

    let title = state.filterCategory !== "All" ? `${state.filterCategory} News` : "All News";
    if (state.filterSource !== "All") title = state.filterSource;
    if (state.searchQuery.trim()) title = `“${state.searchQuery.trim()}”`;
    const anyFilter = state.filterSource !== "All" || state.filterCategory !== "All" || state.filterTag !== "All" || state.filterDate !== "All" || state.searchQuery.trim();

    const perPage = 8;
    const pages = Math.max(1, Math.ceil(Math.max(0, list.length - 3) / perPage));
    const p = Math.min(state.page, pages - 1);
    const top = p === 0 ? list.slice(0, 3) : [];
    const feed = list.slice(3 + p * perPage, 3 + (p + 1) * perPage);

    return `
    <div class="page">
        <div class="page-main">
            <div class="crumb"><span class="lnk" onclick="resetFilters()">News</span> → <span>${esc(title)}</span></div>
            <h1 class="page-title">${esc(title)}</h1>
            <div class="toolbar">
                <div class="pills">
                    ${["All", ...cats].map(c => `<button class="pill ${state.filterCategory === c ? "on" : ""}" onclick="state.filterCategory=${jsq(c)}; state.page=0; render();">${esc(c)}</button>`).join("")}
                </div>
                <label class="search-in">
                    <input type="text" placeholder="Search in ${esc(title)}" value="${esc(state.searchQuery)}" onkeydown="if(event.key==='Enter'){ document.getElementById('global-search').value=this.value; handleGlobalSearch(this.value); }" />
                    ${ICON_SEARCH}
                </label>
            </div>
            <div class="subfilters">
                <select class="select" onchange="state.filterSource=this.value; state.page=0; render();">
                    <option value="All">All sources</option>
                    ${sources.map(s => `<option value="${esc(s)}" ${state.filterSource === s ? "selected" : ""}>${esc(s)}</option>`).join("")}
                </select>
                <select class="select" onchange="state.filterDate=this.value; state.page=0; render();">
                    ${[["All", "Any time"], ["24h", "Last 24 hours"], ["7d", "Last 7 days"], ["30d", "Last 30 days"]].map(([v, l]) => `<option value="${v}" ${state.filterDate === v ? "selected" : ""}>${l}</option>`).join("")}
                </select>
                <select class="select" onchange="state.filterTag=this.value; state.page=0; render();">
                    <option value="All">All tags</option>
                    ${tags.map(t => `<option value="${esc(t)}" ${state.filterTag === t ? "selected" : ""}>#${esc(t)}</option>`).join("")}
                </select>
                ${anyFilter ? `<button class="chip" onclick="resetFilters()">Clear filters ✕</button>` : ""}
                <span class="count">${list.length} ${list.length === 1 ? "story" : "stories"}</span>
            </div>

            ${state.searchQuery.trim() && state.searchBriefingResult ? renderBriefingCard(
                state.searchBriefingResult,
                state.searchQuery.trim(),
                state.searchBriefingShowCites,
                "state.searchBriefingShowCites = !state.searchBriefingShowCites; render();",
                ""
            ) : ""}

            ${!list.length ? `<div class="empty">No stories match these filters. <button class="link-btn" onclick="resetFilters()">Clear filters</button></div>` : ""}

            ${top.length ? `
            <div class="top-block">
                ${bigCard(top[0])}
                <div class="stack">${top.slice(1).map(card).join("")}</div>
            </div>` : ""}

            <div class="feed">
                ${feed.map(a => `
                <article class="feed-card">
                    <div class="top-row">${meta(a)}${excerptChip(a)}</div>
                    <h3 onclick="openArticle(${a.id})">${esc(a.title)}</h3>
                    <p>${esc(a.content)}</p>
                    ${a.summary ? `<div class="ai-note"><b>AI summary</b>${esc(a.summary)}</div>` : ""}
                    ${hashtags(a, 3)}
                    <div class="feed-actions">
                        <div class="left">
                            ${compareChip(a.id)}
                            <a class="chip" href="${esc(a.url)}" target="_blank" rel="noopener">${outletLogo(a.source, 14)} ${esc(shortSource(a.source))} ${ICON_EXT}</a>
                        </div>
                        ${readBtn(a.id, "Read article", "soft")}
                    </div>
                </article>`).join("")}
            </div>

            ${pages > 1 ? `
            <div class="pager">
                <button class="circle" ${p <= 0 ? "disabled" : ""} onclick="state.page=${p - 1}; render(); window.scrollTo(0,0);">${ICON_LEFT}</button>
                <span>Page ${p + 1} of ${pages}</span>
                <button class="circle dark" ${p >= pages - 1 ? "disabled" : ""} onclick="state.page=${p + 1}; render(); window.scrollTo(0,0);">${ICON_ARROW}</button>
            </div>` : ""}
        </div>
        <aside class="page-side">${sidePanel(null)}</aside>
    </div>`;
}

/* ---------- READER ---------- */
function renderReader() {
    const a = findArt(state.currentArticleId) || state.articles[0];
    if (!a) return renderHome();
    const idx = state.articles.findIndex(x => x.id === a.id);
    const prev = idx > 0 ? state.articles[idx - 1] : null;
    const next = idx >= 0 && idx < state.articles.length - 1 ? state.articles[idx + 1] : null;
    const terms = (state.stats.source_terms || {})[a.source] || "Headline and short excerpt from the publisher's RSS feed.";

    return `
    <div class="reader-bar">
        <button class="back" onclick="goBack()">${ICON_LEFT} Back</button>
        <div class="rb-title">${esc(a.title)}</div>
        <div class="rb-actions">
            ${compareChip(a.id)}
            <a class="chip" href="${esc(a.url)}" target="_blank" rel="noopener">${outletLogo(a.source, 14)} ${esc(shortSource(a.source))} ${ICON_EXT}</a>
        </div>
        <span class="rb-progress" id="rb-progress"></span>
    </div>

    <div class="reader">
        <div class="reader-main">
            <div class="meta">
                <span class="src">${outletLogo(a.source, 16)}${esc(a.source)}</span><span class="sep">•</span>
                <span>Published ${esc(fmtTime(a.published_iso || a.published))}</span><span class="sep">•</span>
                <span style="color:var(--muted);">Retrieved ${esc(fmtTime(a.retrieved_at))}</span>
            </div>
            <h1>${esc(a.title)}</h1>
            ${hashtags(a, 3)}

            <div class="reader-img">${photoInner(a)}</div>

            ${a.is_excerpt ? `
            <div class="notice">
                <div><b>This is an excerpt (${a.word_count || 0} words).</b> The feed only provides a summary, so the full story isn't stored here.
                    <span class="terms">${esc(terms)}</span></div>
                <a class="read-btn" href="${esc(a.url)}" target="_blank" rel="noopener">${outletLogo(a.source, 15)} Full story at ${esc(shortSource(a.source))} <span class="arr">${ICON_EXT}</span></a>
            </div>` : ""}

            <p class="reader-body">${esc(a.content)}</p>

            ${a.summary ? `
            <div class="quote">
                <span class="mark">”</span>
                <div><div class="q-label">AI summary · based only on the excerpt above</div><div class="q-text">${esc(a.summary)}</div></div>
            </div>` : ""}

            <div class="reader-actions">
                <button class="chip" onclick="summarizeArticle(${a.id}, this)">${a.summary ? "Refresh AI summary" : "Summarize with AI"}</button>
                <button class="chip" onclick="state.lastQuestion=${jsq(a.title)}; setView('ask'); executeAsk(${jsq(a.title)});">Ask about this story</button>
            </div>

            <div class="prevnext">
                <div class="pn" ${prev ? `onclick="openArticle(${prev.id})"` : ""}>${prev ? `<small>← Previous</small><div>${esc(prev.title)}</div>` : ""}</div>
                <div class="pn r" ${next ? `onclick="openArticle(${next.id})"` : ""}>${next ? `<small>Next →</small><div>${esc(next.title)}</div>` : ""}</div>
            </div>
        </div>
        <aside class="page-side">${sidePanel(a.id)}</aside>
    </div>`;
}

window.addEventListener("scroll", () => {
    const el = document.getElementById("rb-progress");
    if (!el) return;
    const h = document.documentElement;
    const p = h.scrollTop / Math.max(1, h.scrollHeight - h.clientHeight);
    el.style.width = Math.min(100, Math.max(0, p * 100)) + "%";
});

/* ---------- TOOLS ---------- */
function toolHead(crumb, title, desc) {
    return `<div class="crumb"><span class="lnk" onclick="setView('home')">Home</span> → <span>${esc(crumb)}</span></div>
            <h1 class="page-title">${esc(title)}</h1>
            <p class="page-desc">${desc}</p>`;
}

function citeCard(c) {
    return `
    <div class="cite">
        <div class="c-top">
            <div class="meta"><span class="src">${outletLogo(c.source, 15)}${esc(c.source)}</span><span class="sep">•</span><span>Published ${esc(fmtTime(c.published_iso || c.published))}</span><span class="sep">•</span><span style="color:var(--muted)">Retrieved ${esc(fmtTime(c.retrieved_at))}</span></div>
            <span style="font-size:0.72rem; color:var(--muted);">#${c.id}</span>
        </div>
        <div class="c-title" onclick="openArticle(${c.id})">${esc(c.title)}</div>
        <div class="c-ex"><span>“</span><span>${esc(c.excerpt)}</span></div>
        <div class="c-foot">
            <span class="excerpt-chip">${esc(c.completeness_note || "Excerpt")}</span>
            <a class="read-btn" href="${esc(c.url)}" target="_blank" rel="noopener">${outletLogo(c.source, 14)} Original article <span class="arr">${ICON_EXT}</span></a>
        </div>
    </div>`;
}

function renderClusters() {
    const res = state.analyzeResult;
    const sel = state.compareIds.map(findArt).filter(Boolean);
    return `
    <div class="sec">
        ${toolHead("Clusters", "Same story, different outlets", "Stories are grouped automatically when several outlets cover the same event. Compare a cluster to see where coverage agrees, where framing differs, and what one outlet mentions that others leave out. Every point links back to its source.")}

        <div class="tray">
            <div>
                <div style="font-size:0.8rem; font-weight:500; margin-bottom:8px;">${sel.length ? `${sel.length} selected for comparison` : "Pick stories with “+ Compare”, or use a cluster below."}</div>
                <div class="sel">${sel.map(a => `<button class="chip" onclick="toggleCompare(${a.id})">${outletLogo(a.source, 14)} ${esc(shortSource(a.source))}: ${esc(a.title.slice(0, 38))}${a.title.length > 38 ? "…" : ""} ✕</button>`).join("")}</div>
            </div>
            <div style="display:flex; gap:8px;">
                ${sel.length ? `<button class="chip" onclick="state.compareIds=[]; state.analyzeResult=null; render();">Clear</button>` : ""}
                <button class="read-btn dark" onclick="runCompare(this)">Compare coverage <span class="arr">${ICON_ARROW}</span></button>
            </div>
        </div>

        ${res ? `
        <div class="result">
            <div class="status"><i></i>Comparison · ${res.citations.length} sources</div>
            <div class="answer">${formatCitedAnswer(res.analysis)}</div>
            <h5>Sources</h5>
            ${res.citations.map(citeCard).join("")}
        </div>` : ""}

        <div class="cluster-grid">
            ${(state.clusters || []).map(cl => `
            <div class="cluster">
                <div class="head"><span class="label">${esc(cl.topic_label)}</span><span>${cl.outlet_count} outlets · ${cl.article_count} stories</span></div>
                <h4>${esc(cl.lead_title)}</h4>
                <div>${cl.articles.map(a => `<div class="row" onclick="openArticle(${a.id})"><b style="display:inline-flex;align-items:center;gap:6px;">${outletLogo(a.source, 15)}${esc(shortSource(a.source))}</b><span>${esc(a.title)}</span></div>`).join("")}</div>
                <div><button class="read-btn" onclick="state.compareIds=${esc(JSON.stringify(cl.article_ids.slice(0, 4)))}; runCompare(this);">Compare this cluster <span class="arr">${ICON_ARROW}</span></button></div>
            </div>`).join("") || `<div class="empty">No multi-outlet clusters yet. Refresh the feeds to pull in more coverage.</div>`}
        </div>
    </div>`;
}

async function runCompare(btn) {
    if (state.compareIds.length < 2) { render(); alert("Pick at least two stories to compare."); return; }
    if (btn) btn.firstChild.textContent = "Comparing... ";
    try {
        const r = await fetch(`${API}/analyze`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ article_ids: state.compareIds }) });
        const d = await r.json();
        if (!r.ok) throw new Error(d.detail || "Failed");
        state.analyzeResult = d;
        if (state.view !== "clusters") setView("clusters"); else render();
    } catch (e) {
        alert("Couldn't reach the backend. Start it with: python backend\\run.py");
        render();
    }
}

function renderAsk() {
    const res = state.askResult;
    const examples = (state.stats.categories || [])
        .filter(category => category.toLowerCase() !== "other")
        .slice(0, 5)
        .map(category => `Summarize recent ${category.toLowerCase()} coverage across sources`);
    return `
    <div class="sec">
        ${toolHead("Ask the archive", "Multi-source synthesis you can verify", "Ask about any topic or event. The assistant gathers every matching dispatch across all news outlets, synthesizes a single summary with inline clickable citations [Outlet, #ID], and shows the exact supporting excerpts below. If the archive lacks evidence, it says so instead of guessing.")}
        <div class="ask-box">
            <input id="ask-input" type="text" value="${esc(state.lastQuestion)}" placeholder="Ask about a topic in the archive..." onkeydown="if(event.key==='Enter') executeAsk(this.value)" />
            <button class="read-btn dark" id="ask-btn" onclick="executeAsk(document.getElementById('ask-input').value)">Synthesize &amp; cite <span class="arr">${ICON_ARROW}</span></button>
        </div>
        <div class="tag-cloud" style="margin-bottom:26px;">${examples.map(q => `<button onclick="executeAsk(${jsq(q)})">${esc(q)}</button>`).join("")}</div>

        ${res ? renderBriefingCard(res, state.lastQuestion, true, "", "") : ""}
    </div>`;
}

async function executeAsk(q) {
    if (!q || !q.trim()) return;
    state.lastQuestion = q.trim();
    if (state.view !== "ask") setView("ask");
    const btn = document.getElementById("ask-btn");
    if (btn) btn.firstChild.textContent = "Synthesizing... ";
    state.askResult = await fetchTopicSynthesis(q.trim());
    render();
}

function renderFeeds() {
    const statuses = state.stats.feed_statuses || [];
    const bySource = state.stats.by_source || {};
    const healthy = statuses.filter(s => !s.last_error).length;
    const lastOk = statuses.map(s => s.last_success_at).filter(Boolean).sort().pop();
    const lf = state.stats.live_feed || {};
    return `
    <div class="sec">
        ${toolHead("Feeds", "Sources & refresh status", `${lf.enabled === false ? "Automatic feed refresh is disabled." : `Feeds refresh automatically every ${Math.max(1, Math.round((lf.interval_seconds || 180) / 60))} minutes.`} Each story keeps two times: when the publisher published it, and when this app retrieved it. Only headlines and feed excerpts are stored, with a link back to the publisher.`)}
        <div class="stats">
            <div class="stat"><small>Stories stored</small><div>${state.stats.total_articles || 0}</div></div>
            <div class="stat"><small>Sources healthy</small><div>${healthy} / ${statuses.length}</div></div>
            <div class="stat"><small>Excerpt-only stories</small><div>${state.stats.excerpt_only_count || 0}</div></div>
            <div class="stat"><small>Last successful refresh</small><div style="font-size:1.05rem; margin-top:10px;">${esc(lastOk ? relTime(lastOk) : "Not yet")}</div></div>
        </div>
        <div style="display:flex; justify-content:flex-end; margin-bottom:10px;"><button class="read-btn dark" onclick="triggerLiveSync()">Refresh now <span class="arr">${ICON_ARROW}</span></button></div>
        <table class="table">
            <thead><tr><th>Source</th><th>Stories</th><th>Last successful refresh</th><th>Status</th><th>Content policy</th></tr></thead>
            <tbody>
            ${statuses.map(st => `
                <tr>
                    <td><div style="display:inline-flex;align-items:center;gap:8px;"><b style="font-weight:500;display:inline-flex;align-items:center;gap:7px;">${outletLogo(st.source, 16)}${esc(st.source)}</b></div><small>${esc(st.feed_url)}</small></td>
                    <td>${bySource[st.source] || 0}</td>
                    <td>${esc(st.last_success_at ? fmtTime(st.last_success_at) : "Never")}<small>Last attempt ${esc(fmtTime(st.last_attempt_at))}</small></td>
                    <td>${st.last_error ? `<span class="bad">Error</span><small>${esc(st.last_error)}</small>` : `<span class="ok">Healthy</span><small>+${st.last_inserted_count || 0} new last run</small>`}</td>
                    <td style="max-width:320px; color:var(--body); font-size:0.76rem; line-height:1.5;">${esc(st.terms_note)}</td>
                </tr>`).join("") || `<tr><td colspan="5" style="color:var(--muted);">No refresh has run yet.</td></tr>`}
            </tbody>
        </table>
    </div>`;
}

function renderEval() {
    const ev = state.evaluation || {};
    const cases = ev.cases || [];
    return `
    <div class="sec">
        ${toolHead("Evaluation", `${ev.passed_cases || 0} of ${ev.total_cases || 0} test questions passing`, `Realistic newsroom questions with known correct sources. Each answer is checked for the right article, working links and excerpts, the expected facts, and a refusal when the archive has no evidence. Mode: ${esc(ev.llm_mode || "unknown")}.`)}
        <div style="display:flex; justify-content:flex-end; margin-bottom:14px;"><button class="read-btn dark" onclick="rerunEval(this)">Run again <span class="arr">${ICON_ARROW}</span></button></div>
        <div class="eval-grid">
            ${cases.map(c => `
            <div class="eval">
                <div class="head"><span class="label">${esc(c.category)}</span>${c.passed ? `<span class="ok">Pass</span>` : `<span class="bad">Fail</span>`}</div>
                <div class="q">${esc(c.question)}</div>
                <div class="exp">Expected: ${esc((c.expected_sources || []).join(", ") || "a refusal")} · Cited: ${esc((c.retrieved_sources || []).join(", ") || "none")}</div>
                <div class="prev">${esc(c.answer_preview)}</div>
                <div class="checks">${Object.entries(c.checks || {}).map(([k, v]) => `<span>${v ? "✓" : "✕"} ${esc(k.replace(/_/g, " "))}</span>`).join("")}</div>
            </div>`).join("") || `<div class="empty">Evaluation hasn't run yet.</div>`}
        </div>
    </div>`;
}

async function rerunEval(btn) {
    if (btn) btn.firstChild.textContent = "Running... ";
    try {
        const r = await fetch(`${API}/evaluate`);
        if (r.ok) state.evaluation = await r.json();
    } catch (e) { alert("Start the backend to re-run the evaluation."); }
    render();
}

/* ---------- FOOTER ---------- */
function renderFooter() {
    const cats = Object.keys(state.stats.by_category || {}).slice(0, 8);
    const sources = Object.keys(state.stats.by_source || {});
    const tags = (state.stats.top_tags || []).slice(0, 8);
    document.getElementById("footer").innerHTML = `
    <div class="footer">
        <div class="f-cols">
            <div class="f-col"><h5>Sections</h5><ul>${cats.map(c => `<li onclick="openCategory(${jsq(c)})">${esc(c)}</li>`).join("")}</ul></div>
            <div class="f-col"><h5>Outlets</h5><ul>${sources.map(s => `<li onclick="openSource(${jsq(s)})" style="display:flex;align-items:center;gap:7px;">${outletLogo(s, 14)}${esc(s)}</li>`).join("")}</ul></div>
            <div class="f-col"><h5>Tools</h5><ul>
                <li onclick="setView('clusters')">Story clusters</li>
                <li onclick="setView('ask')">Ask the archive</li>
                <li onclick="setView('feeds')">Feed health</li>
                <li onclick="setView('eval')">Evaluation</li>
            </ul></div>
            <div class="f-col"><h5>Popular tags</h5><ul>${tags.map(t => `<li onclick="filterTag(${jsq(t)})">#${esc(t)}</li>`).join("")}</ul></div>
            <div class="f-col">
                <h5>Ask the archive</h5>
                <div class="f-ask">
                    <input id="footer-ask" type="text" placeholder="Your question" onkeydown="if(event.key==='Enter') executeAsk(this.value)" />
                    <button class="circle dark" onclick="executeAsk(document.getElementById('footer-ask').value)">${ICON_ARROW}</button>
                </div>
                <p class="f-note">${state.stats.total_articles || 0} stories from ${sources.length} outlets. Headlines and excerpts come from publisher RSS feeds; full stories belong to their publishers.</p>
            </div>
        </div>
        <div class="f-bottom">
            <span class="f-logo"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 16V8l-9-5-9 5v8l9 5 9-5z"/><path d="M3.3 7L12 12l8.7-5M12 22V12"/></svg>${esc(APP_NAME)}</span>
            <span>© ${new Date().getFullYear()} ${esc(APP_NAME)} newsroom assistant</span>
        </div>
    </div>`;
}

/* ---------- render ---------- */
function render() {
    const root = document.getElementById("main-view");
    const views = { home: renderHome, news: renderNews, reader: renderReader, clusters: renderClusters, ask: renderAsk, feeds: renderFeeds, eval: renderEval };
    root.innerHTML = (views[state.view] || renderHome)();
    const fab = document.getElementById("tray-fab");
    fab.style.display = state.compareIds.length && state.view !== "clusters" ? "inline-flex" : "none";
    document.getElementById("tray-count").textContent = state.compareIds.length;
}

document.querySelector('.nav-pill[data-view="home"]').classList.add("active");
renderFooter();
render();
</script>
</body>
</html>
"""

components.html(
    HTML_TEMPLATE
        .replace("__APP_NAME__", html.escape(APP_NAME))
        .replace("__API_URL_JSON__", json.dumps(API))
        .replace("__INITIAL_DATA__", initial_json),
    height=920,
    scrolling=True,
)
