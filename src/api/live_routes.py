"""Read-only HK live/health endpoints, ready to mount in James's shared API."""

import os
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response

from src.api.live_data import LiveDataUnavailable, LiveSettings, LiveStore
from src.hk.live_paths import dashboard_profile

router = APIRouter(tags=["live"])


@lru_cache(maxsize=1)
def get_live_store() -> LiveStore:
    """Configure one reader; no collector, network fetch or AWS call starts on import."""
    return LiveStore(LiveSettings.from_env())


@router.get("/live/{market}")
def live_market(
    market: str,
    response: Response,
    store: Annotated[LiveStore, Depends(get_live_store)],
):
    """Supply the shared latest-quote contract; unsupported feeds remain explicit."""
    response.headers["Cache-Control"] = "no-store"
    if market.lower() != "hk":
        raise HTTPException(
            404,
            detail="This live feed is not connected",
            headers={"Cache-Control": "no-store"},
        )
    try:
        return store.snapshot()
    except LiveDataUnavailable as exc:
        raise HTTPException(
            503, detail=str(exc), headers={"Cache-Control": "no-store"}
        ) from None


@router.get("/health")
def health(response: Response, store: Annotated[LiveStore, Depends(get_live_store)]):
    """Report only the live source this extension actually reads, without invented services."""
    response.headers["Cache-Control"] = "no-store"
    try:
        value = store.snapshot()
        source = {
            "as_of": value["as_of"],
            "market_open": value["market_open"],
            "is_stale": value["is_stale"],
            "received_count": value["received_count"],
            "requested_count": value["requested_count"],
            "invalid_rows": value["invalid_rows"],
        }
        return {
            "application": "indicatorlab",
            "dashboard_profile": dashboard_profile(),
            "dashboard_instance": os.getenv("INDICATORLAB_DASHBOARD_INSTANCE"),
            "status": "ok"
            if value["quotes"]
            and not value["is_stale"]
            and not value["missing_symbols"]
            and not value["invalid_rows"]
            else "degraded",
            "sources": {"live_hk": source},
        }
    except LiveDataUnavailable:
        return {
            "application": "indicatorlab",
            "dashboard_profile": dashboard_profile(),
            "dashboard_instance": os.getenv("INDICATORLAB_DASHBOARD_INSTANCE"),
            "status": "degraded",
            "sources": {"live_hk": {"as_of": None, "available": False}},
        }
