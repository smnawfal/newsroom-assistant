"""Start the API using host and port values from the project configuration."""

from pathlib import Path

import uvicorn

from config import API_HOST, API_PORT


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=API_HOST,
        port=API_PORT,
        reload=True,
        app_dir=str(Path(__file__).resolve().parent),
    )
