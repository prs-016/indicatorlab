"""Read-only HK live/health endpoints, ready to mount in James's shared API."""

import os
import threading
from datetime import UTC, datetime
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response

from src.api.live_data import LiveDataUnavailable, LiveSettings, LiveStore
from src.hk.live_paths import dashboard_profile
from src.hk.trade_costs import (
    FxObservation,
    FxProvider,
    FxUnavailable,
    board_lot,
    estimate_order,
)
from src.live.quote import QuoteService, QuoteUnavailable
from src.markets.errors import UnknownTicker

router = APIRouter(tags=["live"])
_QUOTE_SERVICE_LOCK = threading.Lock()


@lru_cache(maxsize=1)
def get_live_store() -> LiveStore:
    """Configure one reader; no collector, network fetch or AWS call starts on import."""
    return LiveStore(LiveSettings.from_env())


@lru_cache(maxsize=1)
def get_fx_provider() -> FxProvider:
    """Keep dated display FX references on the server, independently of quotes."""
    return FxProvider()


def _on_demand(store: LiveStore) -> QuoteService:
    with _QUOTE_SERVICE_LOCK:
        if not hasattr(store, "_quote_service"):
            names, _ = store.roster()
            reader = None
            if store.settings.mode == "local":

                def reader(symbol):
                    # Share the list adapter's alias and newest-valid-row rules.
                    return next(
                        (
                            row
                            for row in store.snapshot()["quotes"]
                            if row["symbol"] == symbol
                        ),
                        None,
                    )

            store._quote_service = QuoteService(
                hsi_reader=reader, hsi_store=store.settings.mode, symbols=names
            )
    return store._quote_service


@router.get("/live/{market}")
def live_market(
    market: str,
    response: Response,
    store: Annotated[LiveStore, Depends(get_live_store)],
    symbol: str | None = None,
    shares: int | None = None,
    hkd_per_usd: float | None = None,
    commission_hkd: float | None = None,
    platform_fee_hkd: float | None = None,
    fx_spread_bps: float | None = None,
    fx_fee_usd: float | None = None,
    transfer_fee_usd: float | None = None,
    settlement_pass_through: bool | None = None,
    side: str = "buy",
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
        if shares is not None and symbol is None:
            raise ValueError("A symbol is required for an order-cost estimate")
        if symbol is not None:
            quote = _on_demand(store).get(symbol)
            if shares is None:
                return quote
            if quote["currency"] != "HKD":
                raise ValueError("This calculator supports HKD share counters only")
            now = datetime.now(UTC)
            fx = (
                FxObservation(hkd_per_usd, now.date(), "manual", now)
                if hkd_per_usd is not None
                else get_fx_provider().get()
            )
            lot, provenance = board_lot(quote["symbol"])
            estimate = estimate_order(
                symbol=quote["symbol"],
                shares=shares,
                price_hkd=quote["price"],
                fx=fx,
                trade_date=now.date(),
                lot_size=lot,
                side=side,
                commission_hkd=commission_hkd,
                platform_fee_hkd=platform_fee_hkd,
                fx_spread_bps=fx_spread_bps,
                fx_fee_usd=fx_fee_usd,
                transfer_fee_usd=transfer_fee_usd,
                settlement_pass_through=settlement_pass_through,
            )
            estimate["lot_reference"] = provenance
            return {"quote": quote, "estimate": estimate}
        return store.snapshot()
    except UnknownTicker as exc:
        raise HTTPException(
            404, detail={"error": "unknown_ticker", "message": str(exc)}
        ) from None
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from None
    except (QuoteUnavailable, FxUnavailable) as exc:
        raise HTTPException(
            503, detail=str(exc), headers={"Cache-Control": "no-store"}
        ) from None
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
