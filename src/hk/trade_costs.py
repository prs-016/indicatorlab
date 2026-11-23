"""Indicative ordinary-share HK order costs and dated HKD-per-USD conversion.

This display calculator is separate from frozen strategy evaluation. Unknown
broker charges remain unknown and the result is labelled a known-cost subtotal.
"""

from __future__ import annotations

import argparse
import csv
import json
import threading
import time
import warnings
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
HKMA_URL = "https://api.hkma.gov.hk/public/market-data-and-statistics/monthly-statistical-bulletin/er-ir/er-eeri-daily"
YAHOO_FX_URL = "https://query1.finance.yahoo.com/v8/finance/chart/HKD%3DX"
LOT_FILE = ROOT / "config/hk_board_lots_2026-11-12.csv"
CENT = Decimal("0.01")
BASIS_POINTS = Decimal(10000)
FX_CACHE_SECONDS = 3600
MAX_FX_AGE_DAYS = 7  # Allows weekends/holidays, rejects materially old display FX.
SOURCES = {
    "stamp_duty": "https://www.ird.gov.hk/eng/pdf/sd_stock_rates.pdf",
    "trading_fee": "https://www.hkex.com.hk/News/Market-Communications/2022/221101news?sc_lang=en",
    "exchange_fees": "https://www.hkex.com.hk/Services/Rules-and-Forms-and-Fees/Fees/Securities-(Hong-Kong)/Trading/Transaction?sc_lang=en",
    "settlement": "https://www.hkex.com.hk/-/media/HKEX-Market/Services/Circulars-and-Notices/Participant-and-Members-Circulars/HKSCC/2025/ce_HKSCC_SET_022_2025.pdf",
    "fx": "https://apidocs.hkma.gov.hk/documentation/market-data-and-statistics/monthly-statistical-bulletin/er-ir/er-eeri-daily/",
}


class FxUnavailable(RuntimeError):
    """No dated FX observation is available; an explicit manual rate may be used."""


def _number(value, name: str, *, positive=False) -> Decimal:
    try:
        result = Decimal(str(value))
    except (ArithmeticError, ValueError, TypeError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if (
        isinstance(value, bool)
        or not result.is_finite()
        or result < 0
        or (positive and result == 0)
    ):
        raise ValueError(f"Invalid {name}")
    return result


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def stamp_duty_rate(trade_date: date) -> Decimal:
    """Return the per-side ordinary-HK-share duty rate for a 2016+ trade date."""
    if trade_date < date(2016, 1, 1):
        raise ValueError("This fee schedule covers trade dates from 2016 onward")
    return (
        Decimal("0.0013")
        if date(2021, 8, 1) <= trade_date < date(2023, 11, 17)
        else Decimal("0.001")
    )


def board_lot(symbol: str) -> tuple[int, dict]:
    """Read the existing dated lot reference; a missing stock falls back to one share."""
    from src.markets.hk_symbols import canonical_hk

    symbol = canonical_hk(symbol)
    with LOT_FILE.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["symbol"] == symbol:
                lot = int(row["board_lot"])
                if lot < 1:
                    raise ValueError("Invalid board lot")
                return lot, {
                    "source": row["source"],
                    "as_of": row["pulled_at"],
                    "fallback": False,
                }
    warnings.warn(
        f"No lot reference for {symbol}; using one share", RuntimeWarning, stacklevel=2
    )
    return 1, {"source": None, "as_of": None, "fallback": True}


@dataclass(frozen=True)
class FxObservation:
    """An explicitly dated HKD-per-USD observation, not an executable broker quote."""

    hkd_per_usd: Decimal
    observed_date: date
    source: str
    retrieved_at: datetime
    kind: str = "daily_reference"
    observed_at: datetime | None = None

    def metadata(self, now: datetime | None = None) -> dict:
        """Return public provenance and the direction of the exchange rate."""
        now = now or datetime.now(UTC)
        return {
            "hkd_per_usd": float(self.hkd_per_usd),
            "observed_date": self.observed_date.isoformat(),
            "source": self.source,
            "retrieved_at": self.retrieved_at.isoformat(),
            "kind": self.kind if self.source != "manual" else "manual",
            "observed_at": self.observed_at.isoformat() if self.observed_at else None,
            "display_only": True,
            "evaluated_at": now.isoformat(),
            "calendar_age_days": (now.date() - self.observed_date).days,
        }


class FxProvider:
    """Read HKMA's latest dated daily reference, cached for an hour.

    Args:
        session: Injectable requests-compatible client.
        clock: Aware current-time callable.
        timer: Monotonic cache-expiry callable.
    """

    def __init__(
        self,
        *,
        session=None,
        yahoo_metadata=None,
        clock=lambda: datetime.now(UTC),
        timer=time.monotonic,
    ):
        self.session, self.clock, self.timer = (
            session or requests.Session(),
            clock,
            timer,
        )
        self.yahoo_metadata = yahoo_metadata or self._yfinance_metadata
        self.cached = None
        self.lock = threading.Lock()

    @staticmethod
    def _yfinance_metadata() -> dict:
        # Keep Yahoo's existing client transport rather than inventing request
        # cookies or silently substituting a fixed peg when HTTP is limited.
        import yfinance as yf

        ticker = yf.Ticker("HKD=X")
        history = ticker.history(
            period="5d", interval="1d", auto_adjust=False, timeout=5
        )
        if history.empty:
            raise FxUnavailable("Yahoo supplied no FX observation")
        return ticker.get_history_metadata()

    def _yahoo(self, now: datetime) -> FxObservation:
        try:
            meta = self.yahoo_metadata()
        except Exception as exc:
            # Normalize client-specific transport errors without exposing them
            # or substituting an unobserved rate.
            raise FxUnavailable("Yahoo FX is unavailable") from exc
        if meta["symbol"] != "HKD=X" or meta["currency"] != "HKD":
            raise ValueError("Unexpected FX identity or rate units")
        stamp = datetime.fromtimestamp(meta["regularMarketTime"], UTC)
        age = (now - stamp).total_seconds()
        if age < -5 or age > MAX_FX_AGE_DAYS * 86400:
            raise ValueError("No recent paired FX price and timestamp")
        return FxObservation(
            _number(meta["regularMarketPrice"], "FX rate", positive=True),
            stamp.date(),
            YAHOO_FX_URL,
            now,
            "market_reference",
            stamp,
        )

    def get(self) -> FxObservation:
        """Return recent dated FX, falling back to paired Yahoo market metadata.

        HKMA remains the primary daily reference. A stale/outage response may
        use a recent HKD=X price with its own exact provider timestamp instead;
        the result identifies this as a market reference rather than daily FX.
        """
        with self.lock:
            if self.cached and self.timer() - self.cached[0] < FX_CACHE_SECONDS:
                candidate = self.cached[1]
                now = self.clock()
                age = (
                    (now - candidate.observed_at).total_seconds()
                    if candidate.observed_at
                    else (now.date() - candidate.observed_date).days * 86400
                )
                if -5 <= age <= MAX_FX_AGE_DAYS * 86400:
                    return candidate
                self.cached = None
            try:
                response = self.session.get(
                    HKMA_URL,
                    params={
                        "pagesize": 5,
                        "sortby": "end_of_day",
                        "sortorder": "desc",
                        "fields": "end_of_day,usd",
                    },
                    timeout=5,
                )
                response.raise_for_status()
                if len(response.content) > 100_000:
                    raise ValueError("Oversized FX response")
                records = response.json()["result"]["records"]
                now = self.clock()
                if now.tzinfo is None:
                    raise ValueError("FX clock must be timezone-aware")
                available = []
                for row in records:
                    observed = date.fromisoformat(row["end_of_day"])
                    # A future-labelled daily observation cannot fund today's order.
                    if observed <= now.date():
                        available.append(
                            FxObservation(
                                _number(row["usd"], "FX rate", positive=True),
                                observed,
                                HKMA_URL,
                                now,
                            )
                        )
                if not available:
                    raise ValueError("No usable dated FX observation")
                result = max(available, key=lambda row: row.observed_date)
                if (now.date() - result.observed_date).days > MAX_FX_AGE_DAYS:
                    raise ValueError("HKMA daily observation is stale")
                self.cached = (self.timer(), result)
                return result
            except (requests.RequestException, ValueError, KeyError, TypeError):
                try:
                    result = self._yahoo(self.clock())
                    self.cached = (self.timer(), result)
                    return result
                except (
                    FxUnavailable,
                    requests.RequestException,
                    ValueError,
                    KeyError,
                    TypeError,
                    IndexError,
                ) as fallback:
                    raise FxUnavailable(
                        "Recent FX is unavailable; enter an explicit HKD-per-USD rate"
                    ) from fallback


def estimate_order(
    *,
    symbol: str,
    shares: int,
    price_hkd,
    fx: FxObservation,
    trade_date: date,
    lot_size: int,
    side="buy",
    commission_hkd=None,
    platform_fee_hkd=None,
    fx_spread_bps=None,
    fx_fee_usd=None,
    transfer_fee_usd=None,
    settlement_pass_through: bool | None = None,
    legacy_trading_tariff_pass_through: bool | None = None,
) -> dict:
    """Estimate ordinary HKD share purchase cash or sale proceeds in USD.

    Args:
        symbol: Identifier for the HKD counter, supplied by the caller.
        shares: Requested shares, rounded down to whole board lots.
        price_hkd: Indicative HKD price per share; not an executable order price.
        fx: Explicit daily reference or manual HKD-per-USD rate.
        trade_date: Date used to select statutory fee schedules.
        lot_size: Positive known lot size, or an explicitly warned fallback of one.
        side: Buy cash required or sell cash proceeds.
        commission_hkd: Broker commission; None means unknown.
        platform_fee_hkd: Separate broker platform charge; None means unknown.
        fx_spread_bps: Conversion spread in basis points; None means unknown.
        fx_fee_usd: Fixed FX fee; None means unknown.
        transfer_fee_usd: Transfer charge; None means unknown.
        settlement_pass_through: Whether the broker passes HKSCC fees through.
        legacy_trading_tariff_pass_through: Separate pre-2023 HKEX tariff choice.

    Returns:
        Rounded shares, dated fees, FX provenance and a labelled USD estimate.
    """
    if side not in {"buy", "sell"}:
        raise ValueError("side must be buy or sell")
    if isinstance(shares, bool) or not isinstance(shares, int) or shares <= 0:
        raise ValueError("shares must be a positive integer")
    if isinstance(lot_size, bool) or not isinstance(lot_size, int) or lot_size < 1:
        raise ValueError("lot_size must be a positive integer")
    if settlement_pass_through is not None and not isinstance(
        settlement_pass_through, bool
    ):
        raise ValueError("settlement_pass_through must be true, false or unknown")
    rate = _number(fx.hkd_per_usd, "FX rate", positive=True)
    if fx.observed_date > trade_date:
        raise ValueError("The FX observation is later than the trade date")
    price = _number(price_hkd, "share price", positive=True)
    executed = (shares // lot_size) * lot_size
    if executed == 0:
        raise ValueError(
            f"The requested shares do not reach one board lot ({lot_size})"
        )
    gross = _money(price * executed)
    duty_rate = stamp_duty_rate(trade_date)
    duty = (gross * duty_rate).quantize(Decimal(1), rounding=ROUND_CEILING)
    trading_rate = (
        Decimal("0.0000565") if trade_date >= date(2023, 1, 1) else Decimal("0.00005")
    )
    afrc_rate = Decimal("0.0000015") if trade_date >= date(2022, 1, 1) else Decimal(0)
    fees = {
        "stamp_duty": duty,
        "sfc_levy": _money(gross * Decimal("0.000027")),
        "afrc_levy": _money(gross * afrc_rate),
        "hkex_trading_fee": _money(gross * trading_rate),
    }
    # These are participant-level charges; a broker may absorb rather than pass
    # them to the retail client. Unknown remains explicit in the estimate.
    if settlement_pass_through:
        settlement = (
            _money(gross * Decimal("0.000042"))
            if trade_date >= date(2025, 6, 30)
            else min(Decimal(100), max(Decimal(2), _money(gross * Decimal("0.00002"))))
        )
        fees["settlement_pass_through"] = settlement
    if trade_date < date(2023, 1, 1) and legacy_trading_tariff_pass_through:
        fees["legacy_trading_tariff_pass_through"] = Decimal("0.50")
    assumptions = {
        "commission_hkd": commission_hkd,
        "platform_fee_hkd": platform_fee_hkd,
        "fx_spread_bps": fx_spread_bps,
        "fx_fee_usd": fx_fee_usd,
        "transfer_fee_usd": transfer_fee_usd,
        "settlement_pass_through": settlement_pass_through,
    }
    if trade_date < date(2023, 1, 1):
        if legacy_trading_tariff_pass_through is not None and not isinstance(
            legacy_trading_tariff_pass_through, bool
        ):
            raise ValueError(
                "legacy trading tariff pass-through must be true, false or unknown"
            )
        assumptions["legacy_trading_tariff_pass_through"] = (
            legacy_trading_tariff_pass_through
        )
    missing = [name for name, value in assumptions.items() if value is None]
    commission = _number(0 if commission_hkd is None else commission_hkd, "commission")
    spread = (
        _number(0 if fx_spread_bps is None else fx_spread_bps, "FX spread")
        / BASIS_POINTS
    )
    if spread >= 1:
        raise ValueError("FX spread must be below 10000 basis points")
    fixed_usd = _number(0 if fx_fee_usd is None else fx_fee_usd, "FX fee") + _number(
        0 if transfer_fee_usd is None else transfer_fee_usd, "transfer fee"
    )
    fees["broker_commission"] = _money(commission)
    fees["platform_fee"] = _money(
        _number(0 if platform_fee_hkd is None else platform_fee_hkd, "platform fee")
    )
    total_fees = sum(fees.values())
    if side == "sell" and total_fees > gross:
        raise ValueError("Fees exceed sale proceeds")
    local_cash = gross + total_fees if side == "buy" else gross - total_fees
    effective_rate = rate * (1 - spread if side == "buy" else 1 + spread)
    usd = local_cash / effective_rate + (fixed_usd if side == "buy" else -fixed_usd)
    if usd < 0:
        raise ValueError("USD fees exceed sale proceeds")
    return {
        "symbol": symbol,
        "side": side,
        "trade_date": trade_date.isoformat(),
        "requested_shares": shares,
        "executed_shares": executed,
        "board_lot": lot_size,
        "unfilled_requested_shares": shares - executed,
        "unfilled_requested_notional_hkd": float(_money((shares - executed) * price)),
        "price_hkd": float(price),
        "gross_hkd": float(gross),
        "stamp_duty_rate": float(duty_rate),
        "fees_hkd": {key: float(value) for key, value in fees.items()},
        "total_fees_hkd": float(total_fees),
        "cash_hkd": float(local_cash),
        "cash_usd": float(_money(usd)),
        "fx": fx.metadata(),
        "effective_hkd_per_usd": float(effective_rate),
        "assumptions": assumptions,
        "complete": not missing,
        "unknown_charges": missing,
        "label": "Estimated USD required"
        if not missing and side == "buy"
        else "Estimated USD proceeds"
        if not missing
        else "Known-cost USD subtotal",
        "excluded": [
            "slippage",
            "custody and account charges",
            "personal US income, dividend and capital-gains taxes",
        ],
        "sources": SOURCES,
    }


def main() -> None:
    """Print a standalone cost estimate, requiring explicit broker-fee assumptions."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--shares", type=int, required=True)
    parser.add_argument("--price-hkd", required=True)
    parser.add_argument("--hkd-per-usd")
    parser.add_argument(
        "--trade-date", type=date.fromisoformat, default=datetime.now(UTC).date()
    )
    parser.add_argument("--side", choices=["buy", "sell"], default="buy")
    for name in [
        "commission-hkd",
        "platform-fee-hkd",
        "fx-spread-bps",
        "fx-fee-usd",
        "transfer-fee-usd",
    ]:
        parser.add_argument("--" + name, type=float)
    parser.add_argument("--settlement-pass-through", choices=["yes", "no"])
    parser.add_argument("--legacy-trading-tariff-pass-through", choices=["yes", "no"])
    args = parser.parse_args()
    fx = (
        FxObservation(
            _number(args.hkd_per_usd, "FX rate", positive=True),
            args.trade_date,
            "manual",
            datetime.now(UTC),
        )
        if args.hkd_per_usd
        else FxProvider().get()
    )
    lot, provenance = board_lot(args.symbol)
    result = estimate_order(
        symbol=args.symbol,
        shares=args.shares,
        price_hkd=args.price_hkd,
        fx=fx,
        trade_date=args.trade_date,
        lot_size=lot,
        side=args.side,
        commission_hkd=args.commission_hkd,
        platform_fee_hkd=args.platform_fee_hkd,
        fx_spread_bps=args.fx_spread_bps,
        fx_fee_usd=args.fx_fee_usd,
        transfer_fee_usd=args.transfer_fee_usd,
        settlement_pass_through=None
        if args.settlement_pass_through is None
        else args.settlement_pass_through == "yes",
        legacy_trading_tariff_pass_through=None
        if args.legacy_trading_tariff_pass_through is None
        else args.legacy_trading_tariff_pass_through == "yes",
    )
    result["lot_reference"] = provenance
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
