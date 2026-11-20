"""The shared Indicator Lab API. Each source adds its own router.

.venv/bin/uvicorn src.api.main:app --reload --port 8000     # from the repo root
open http://localhost:8000/docs
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from src.api import live_routes, reddit
from src.hk.dashboard import FRONTEND, public_config

app = FastAPI(
    title="Indicator Lab API",
    version="0.3.0",
    description="Weekly attention, sentiment and spikes, plus read-only live stock quotes.",
)
app.include_router(reddit.router)
app.include_router(live_routes.router)

origins = [
    value.strip()
    for value in os.getenv("INDICATORLAB_CORS_ORIGINS", "").split(",")
    if value.strip()
]
if "*" in origins:
    raise ValueError("Configure explicit dashboard CORS origins")
if origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["GET"],
        allow_headers=["Accept"],
        allow_credentials=False,
    )


@app.get("/", include_in_schema=False)
def home():
    """Open the HK live panel while preserving the shared API routes."""
    return RedirectResponse("/live-markets/")


@app.get("/live-markets/config.js", include_in_schema=False)
def frontend_config():
    """Supply environment-based browser configuration for same-process serving."""
    return Response(
        public_config(),
        media_type="application/javascript",
        headers={"Cache-Control": "no-store"},
    )


if FRONTEND.is_dir():
    app.mount(
        "/live-markets", StaticFiles(directory=FRONTEND, html=True), name="live-markets"
    )
