"""The shared Indicator Lab API. Each source adds its own router.

    .venv/bin/uvicorn src.api.main:app --reload --port 8000     # from the repo root
    open http://localhost:8000/docs

CORS_ORIGINS (comma-separated) lists the dashboard origins allowed to call it; every route is read-only.
"""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api import dashboard, wikipedia

app = FastAPI(title="Indicator Lab API", version="0.3.0",
              description="Weekly attention, sentiment and spikes for the tracked stocks (weeks labelled by Monday).")
app.add_middleware(CORSMiddleware, allow_origins=[o for o in os.getenv("CORS_ORIGINS", "").split(",") if o],
                   allow_methods=["GET"], allow_headers=["*"])
app.include_router(wikipedia.router)
app.include_router(dashboard.router)
