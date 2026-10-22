# Newsroom Assistant

A small, configurable newsroom app. It collects headlines and excerpts from RSS feeds, supports search and story comparison, and can answer questions with links to the stored sources. The original project name is PulseWire; you can change it in the settings.

## Requirements

- Python 3.10 or newer
- Internet access to retrieve RSS feeds
- An Anthropic API key for online AI answers (optional)

Without an API key, the app uses its built-in offline answer mode.

## Install

Open PowerShell in the project folder and run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

If PowerShell blocks environment activation, run `Set-ExecutionPolicy -Scope Process Bypass` in that window and activate again.

## Run

Open two PowerShell windows in the project folder. Activate the virtual environment in each.

In the first window, start the API:

```powershell
python backend\run.py
```

In the second window, start the web app:

```powershell
streamlit run frontend\app.py
```

Open the local address shown by Streamlit. Keep both windows open while using the app.

## Set up online AI (optional)

Open `.env` and add your own API key to `ANTHROPIC_API_KEY`. Keep `.env` private. Each person who uses online AI needs their own key.

## Change the app

The main settings are in `.env`. The editable JSON files are:

- `backend/feeds.json` — source names, RSS URLs, and optional display names and bundled logo keys
- `backend/categories.json` — categories and their keyword lists
- `backend/search_config.json` — search synonyms
- `backend/evaluation_cases.json` — sample questions and expected results

You can change the app name, API host and port, database location, refresh intervals, model, and clustering settings in `.env` (use `.env.example` as a guide). If the browser-facing API address differs from the host and port, set `NEWSROOM_API_URL` too. Relative file paths start from the project folder. When you change feeds or replace the sample archive, update the evaluation cases to match your articles.

The included `backend/newsroom.db` is a sample archive. The app creates its database automatically if the configured database file does not exist.
