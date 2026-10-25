"""The shared Indicator Lab API. Each source adds its own router.

    .venv/bin/uvicorn src.api.main:app --reload --port 8000     # from the repo root
    open http://localhost:8000/docs
"""
from fastapi import FastAPI

from src.api import reddit

app = FastAPI(title="Indicator Lab API", version="0.2.0",
              description="Weekly attention, sentiment and spikes for the tracked stocks (weeks labelled by Monday).")
app.include_router(reddit.router)
