# PulseWire

PulseWire is a small AI newsroom assistant. It collects news headlines from RSS feeds, lets you search and compare stories, and can answer questions with links to its sources.

## What you need

- Python 3
- An internet connection to refresh RSS feeds
- An Anthropic API key only if you want to use online AI features

The project can run without an API key using its built-in offline answer mode.

## Install

Open PowerShell in the project folder and run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run

Open two PowerShell windows in the project folder.

In the first window, start the backend:

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn --app-dir backend main:app --reload
```

In the second window, start the website:

```powershell
.\.venv\Scripts\Activate.ps1
streamlit run frontend\app.py
```

Open the local web address shown by Streamlit. Keep both windows open while using the app.

## Optional AI setup

Copy `.env.example` to `.env` and add your own API key to `.env` if you want online AI answers. Do not share your `.env` file. Each person should use their own key.
