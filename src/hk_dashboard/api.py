"""Explicit HK routes for the existing dashboard, isolated from US execution."""

from functools import lru_cache

import requests

from src.hk_dashboard.data import HKData


@lru_cache(maxsize=1)
def dataset():
    """Construct one cached read-only HK data adapter on first HK request."""
    return HKData()


def dispatch(path, query):
    """Return (payload, HTTP status) for an explicitly selected HK GET route."""
    if path == "/api/health":
        from src.hk_dashboard.launch import identity

        return {"app": "indicatorlab-hk-dashboard", "checkout": identity()}, 200
    data = dataset()
    params = {key: values[0] for key, values in query.items() if values}
    try:
        routes = {
            "/api/now": data.now,
            "/api/status": data.status,
            "/api/spike_weeks": data.spikes,
            "/api/strategy_log": data.strategies,
            "/api/live": data.live.snapshot,
        }
        if path in routes:
            return routes[path](), 200
        if path == "/api/stock":
            return data.stock(params.get("ticker", "0700.HK")), 200
        if path == "/api/order_estimate":
            try:
                return data.live.estimate(params), 200
            except (
                requests.RequestException,
                ValueError,
                KeyError,
                TypeError,
                RuntimeError,
            ):
                return {
                    "error": "Cost service unavailable or invalid order. Check shares and fee inputs; start the existing HK API for dated taxes, FX and lots."
                }, 503
        return {
            "error": "No HK endpoint at this path; HK research execution is disabled."
        }, 404
    except (ValueError, KeyError):
        return {"error": "Choose a valid stock from the configured HK universe."}, 400
    except (OSError, TypeError, RuntimeError):
        return {
            "error": "HK source unavailable. Check HK data status and configured source paths."
        }, 503
