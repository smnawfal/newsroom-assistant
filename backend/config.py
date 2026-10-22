"""Runtime configuration shared by the backend and Streamlit frontend."""

import json
import os
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BACKEND_DIR.parent


def _load_env_file() -> None:
    """Read simple KEY=VALUE settings from .env; real environment values win."""
    for env_path in (PROJECT_DIR / ".env", BACKEND_DIR / ".env"):
        if not env_path.is_file():
            continue
        for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def _path_setting(name: str, default: Path) -> Path:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    path = Path(raw).expanduser()
    return path if path.is_absolute() else PROJECT_DIR / path


def _int_setting(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name, "").strip()
    try:
        return max(minimum, int(raw)) if raw else default
    except ValueError:
        return default


def _bool_setting(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _float_setting(name: str, default: float, minimum: float = 0.0) -> float:
    raw = os.getenv(name, "").strip()
    try:
        return max(minimum, float(raw)) if raw else default
    except ValueError:
        return default


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"{label} file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON in {label} file {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} file must contain a JSON object: {path}")
    return value


_load_env_file()

APP_NAME = os.getenv("NEWSROOM_APP_NAME", "PulseWire").strip() or "Newsroom"
API_HOST = os.getenv("NEWSROOM_API_HOST", "127.0.0.1")
API_PORT = _int_setting("NEWSROOM_API_PORT", 8000)
API_URL = os.getenv("NEWSROOM_API_URL", "").strip().rstrip("/")
if not API_URL:
    API_URL = f"http://{API_HOST}:{API_PORT}"
DATABASE_PATH = _path_setting("NEWSROOM_DATABASE_PATH", BACKEND_DIR / "newsroom.db")
FEEDS_CONFIG_PATH = _path_setting("NEWSROOM_FEEDS_FILE", BACKEND_DIR / "feeds.json")
CATEGORIES_CONFIG_PATH = _path_setting("NEWSROOM_CATEGORIES_FILE", BACKEND_DIR / "categories.json")
EVALUATION_CASES_PATH = _path_setting(
    "NEWSROOM_EVALUATION_FILE", BACKEND_DIR / "evaluation_cases.json"
)
SEARCH_CONFIG_PATH = _path_setting("NEWSROOM_SEARCH_FILE", BACKEND_DIR / "search_config.json")

FEED_REFRESH_INTERVAL_SECONDS = _int_setting("NEWSROOM_FEED_REFRESH_SECONDS", 180)
STATUS_REFRESH_INTERVAL_SECONDS = _int_setting("NEWSROOM_STATUS_REFRESH_SECONDS", 25)
FEED_REQUEST_TIMEOUT_SECONDS = _int_setting("NEWSROOM_FEED_TIMEOUT_SECONDS", 14)
AUTO_REFRESH_ENABLED = _bool_setting("NEWSROOM_AUTO_REFRESH", True)
MAX_CLUSTER_ARTICLES = _int_setting("NEWSROOM_CLUSTER_MAX_ARTICLES", 250)
CLUSTER_SIMILARITY_THRESHOLD = _float_setting("NEWSROOM_CLUSTER_SIMILARITY_THRESHOLD", 0.24)
CLUSTER_MIN_SHARED_TERMS = _int_setting("NEWSROOM_CLUSTER_MIN_SHARED_TERMS", 2)
EXCERPT_WORD_LIMIT = _int_setting("NEWSROOM_EXCERPT_WORD_LIMIT", 120, minimum=0)
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6").strip() or "claude-sonnet-4-6"
FEED_USER_AGENT = os.getenv(
    "NEWSROOM_USER_AGENT", f"{APP_NAME.replace(' ', '')}/1.0 (RSS reader)"
).strip()

_cors_raw = os.getenv(
    "NEWSROOM_CORS_ORIGINS", "http://localhost:8501,http://127.0.0.1:8501"
)
CORS_ORIGINS = [origin.strip() for origin in _cors_raw.split(",") if origin.strip()]

_feed_config = _read_json(FEEDS_CONFIG_PATH, "Feed configuration")
_feed_entries = _feed_config.get("feeds", {})
if not isinstance(_feed_entries, dict):
    raise RuntimeError("The 'feeds' field in the feed configuration must be an object")

DEFAULT_FEEDS: dict[str, str] = {}
SOURCE_TERMS: dict[str, str] = {}
OUTLET_METADATA: dict[str, dict[str, str]] = {}
_generic_terms_note = (
    "Review this publisher's RSS terms before use. Keep attribution and the original link, "
    "and store only feed-provided excerpts unless separately authorized."
)
for _source, _entry in _feed_entries.items():
    if isinstance(_entry, str):
        _url = _entry
        _metadata: dict[str, Any] = {}
    elif isinstance(_entry, dict):
        _url = str(_entry.get("url", "")).strip()
        _metadata = _entry
    else:
        continue
    if not _url.startswith(("http://", "https://")):
        continue
    DEFAULT_FEEDS[str(_source)] = _url
    SOURCE_TERMS[str(_source)] = str(
        _metadata.get("terms_note", _generic_terms_note)
    ).strip()
    OUTLET_METADATA[str(_source)] = {
        "short": str(_metadata.get("short_name", _source)),
        "slug": str(_metadata.get("logo_key", "")),
    }

if not DEFAULT_FEEDS:
    raise RuntimeError(f"No valid RSS feeds were found in {FEEDS_CONFIG_PATH}")

_category_config = _read_json(CATEGORIES_CONFIG_PATH, "Category configuration")
CATEGORIES = _category_config.get("categories", ["Other"])
CATEGORY_KEYWORDS = _category_config.get("keywords", {})
if not isinstance(CATEGORIES, list) or not CATEGORIES or not all(
    isinstance(item, str) and item.strip() for item in CATEGORIES
):
    raise RuntimeError("The 'categories' field must be a non-empty list of strings")
if not isinstance(CATEGORY_KEYWORDS, dict) or not all(
    isinstance(category, str)
    and isinstance(words, list)
    and all(isinstance(word, str) for word in words)
    for category, words in CATEGORY_KEYWORDS.items()
):
    raise RuntimeError("The 'keywords' field must be an object of string lists")

_search_config = _read_json(SEARCH_CONFIG_PATH, "Search configuration")
SYNONYM_MAP = _search_config.get("synonyms", {})
if not isinstance(SYNONYM_MAP, dict) or not all(
    isinstance(key, str)
    and isinstance(values, list)
    and all(isinstance(value, str) for value in values)
    for key, values in SYNONYM_MAP.items()
):
    raise RuntimeError("The 'synonyms' field must be an object of string lists")
