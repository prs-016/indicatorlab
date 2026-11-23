"""Financial arithmetic, dated fees, missing assumptions and FX provenance."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.hk.trade_costs import (
    FxObservation,
    FxProvider,
    FxUnavailable,
    estimate_order,
    stamp_duty_rate,
)

TODAY = date(2026, 11, 23)
NOW = datetime(2026, 11, 23, 10, tzinfo=UTC)


def estimate(**overrides):
    args = {
        "symbol": "0700.HK",
        "shares": 100,
        "price_hkd": "400",
        "lot_size": 100,
        "trade_date": TODAY,
        "fx": FxObservation(Decimal("7.8"), TODAY, "manual", NOW),
    }
    return estimate_order(**(args | overrides))


def test_known_subtotal_preserves_unknown_broker_charges():
    value = estimate()
    assert value["complete"] is False
    assert value["label"] == "Known-cost USD subtotal"
    assert value["cash_hkd"] == 40043.4
    assert value["cash_usd"] == 5133.77
    assert set(value["unknown_charges"]) == {
        "commission_hkd",
        "platform_fee_hkd",
        "fx_spread_bps",
        "fx_fee_usd",
        "transfer_fee_usd",
        "settlement_pass_through",
    }
    assert value["fees_hkd"]["stamp_duty"] == 40
    assert value["fees_hkd"]["sfc_levy"] == 1.08
    assert value["fees_hkd"]["afrc_levy"] == 0.06
    assert value["fees_hkd"]["hkex_trading_fee"] == 2.26


def test_explicit_spread_and_fixed_charges_increase_buy_cost():
    value = estimate(
        commission_hkd=50,
        platform_fee_hkd=0,
        fx_spread_bps=10,
        fx_fee_usd=2,
        transfer_fee_usd=5,
        settlement_pass_through=True,
    )
    assert value["complete"] is True
    assert value["cash_hkd"] == 40095.08
    assert value["cash_usd"] == 5152.54
    assert value["effective_hkd_per_usd"] == pytest.approx(7.7922)
    assert value["fees_hkd"]["settlement_pass_through"] == 1.68


def test_sell_deducts_fees_and_adverse_fx_spread():
    base = estimate(
        side="sell",
        commission_hkd=0,
        platform_fee_hkd=0,
        fx_spread_bps=0,
        fx_fee_usd=0,
        transfer_fee_usd=0,
        settlement_pass_through=False,
    )
    value = estimate(
        side="sell",
        commission_hkd=50,
        fx_spread_bps=10,
        fx_fee_usd=2,
        transfer_fee_usd=5,
        settlement_pass_through=True,
    )
    assert value["cash_usd"] < base["cash_usd"]
    assert value["effective_hkd_per_usd"] == pytest.approx(7.8078)
    assert value["fees_hkd"]["stamp_duty"] == 40


def test_lots_round_down_and_keep_unfilled_notional_explicit():
    value = estimate(shares=250)
    assert value["executed_shares"] == 200
    assert value["unfilled_requested_shares"] == 50
    assert value["unfilled_requested_notional_hkd"] == 20000


@pytest.mark.parametrize(
    "day,rate",
    [
        ("2021-07-31", "0.001"),
        ("2021-08-01", "0.0013"),
        ("2023-11-16", "0.0013"),
        ("2023-11-17", "0.001"),
        ("2024-03-01", "0.001"),
    ],
)
def test_duty_effective_dates(day, rate):
    assert stamp_duty_rate(date.fromisoformat(day)) == Decimal(rate)


def test_whole_dollar_duty_rounds_up_and_other_fees_round_to_cent():
    value = estimate(price_hkd="400.01")
    assert value["fees_hkd"]["stamp_duty"] == 41


def test_old_fees_select_tariff_and_settlement_minimum():
    day = date(2021, 7, 1)
    value = estimate(
        shares=1,
        lot_size=1,
        price_hkd=100,
        trade_date=day,
        fx=FxObservation(Decimal("7.8"), day, "manual", NOW),
        settlement_pass_through=True,
        legacy_trading_tariff_pass_through=True,
    )
    assert value["fees_hkd"]["afrc_levy"] == 0
    assert value["fees_hkd"]["hkex_trading_fee"] == 0.01
    assert value["fees_hkd"]["settlement_pass_through"] == 2
    assert value["fees_hkd"]["legacy_trading_tariff_pass_through"] == 0.5


@pytest.mark.parametrize(
    "patch",
    [
        {"shares": 99},
        {"shares": True},
        {"lot_size": 0},
        {"price_hkd": "nan"},
        {"commission_hkd": True},
        {"fx_spread_bps": 10000},
        {"fx_fee_usd": -1},
        {"side": "hold"},
    ],
)
def test_invalid_financial_inputs_rejected(patch):
    with pytest.raises(ValueError):
        estimate(**patch)


def test_future_fx_cannot_fund_an_earlier_trade():
    with pytest.raises(ValueError, match="later than"):
        estimate(fx=FxObservation(Decimal("7.8"), date(2026, 11, 24), "manual", NOW))


def test_hkma_uses_dated_usd_field_and_caches_no_future_backfill():
    calls = []
    ticks = [0]

    def get(url, **kwargs):
        calls.append((url, kwargs))
        return SimpleNamespace(
            content=b"{}",
            raise_for_status=lambda: None,
            json=lambda: {
                "result": {
                    "records": [
                        {"end_of_day": "2026-11-24", "usd": 7.7},
                        {"end_of_day": "2026-11-20", "usd": 7.8},
                    ]
                }
            },
        )

    provider = FxProvider(
        session=SimpleNamespace(get=get), clock=lambda: NOW, timer=lambda: ticks[0]
    )
    first = provider.get()
    assert first.observed_date == date(2026, 11, 20)
    assert first.hkd_per_usd == Decimal("7.8")
    assert first.metadata()["kind"] == "daily_reference"
    provider.get()
    assert len(calls) == 1
    ticks[0] = 3600
    provider.get()
    assert len(calls) == 2


def test_unavailable_fx_never_fabricates_a_peg_rate():
    def no_yahoo():
        raise ValueError("No FX observations")

    provider = FxProvider(
        yahoo_metadata=no_yahoo,
        session=SimpleNamespace(
            get=lambda *a, **k: SimpleNamespace(
                content=b"{}",
                raise_for_status=lambda: None,
                json=lambda: {"result": {"records": []}},
            )
        ),
        clock=lambda: NOW,
    )
    with pytest.raises(FxUnavailable):
        provider.get()


def test_stale_hkma_may_use_recent_paired_yahoo_metadata():
    stamp = int(NOW.timestamp()) - 30
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        payload = (
            {"result": {"records": [{"end_of_day": "2026-10-31", "usd": 7.8}]}}
            if "hkma" in url
            else {
                "chart": {
                    "result": [
                        {
                            "meta": {
                                "symbol": "HKD=X",
                                "currency": "HKD",
                                "regularMarketPrice": 7.81,
                                "regularMarketTime": stamp,
                            }
                        }
                    ]
                }
            }
        )
        return SimpleNamespace(
            content=b"{}", raise_for_status=lambda: None, json=lambda: payload
        )

    def metadata():
        calls.append("yfinance")
        return {
            "symbol": "HKD=X",
            "currency": "HKD",
            "regularMarketPrice": 7.81,
            "regularMarketTime": stamp,
        }

    provider = FxProvider(
        session=SimpleNamespace(get=get), yahoo_metadata=metadata, clock=lambda: NOW
    )
    value = provider.get()
    assert value.kind == "market_reference"
    assert value.observed_at == datetime.fromtimestamp(stamp, UTC)
    assert value.hkd_per_usd == Decimal("7.81")
    assert len(calls) == 2


def test_cached_fx_is_rechecked_after_wall_clock_jump():
    times = [NOW]
    ticks = [0]

    def fail():
        raise ValueError("No recent quote")

    response = SimpleNamespace(
        content=b"{}",
        raise_for_status=lambda: None,
        json=lambda: {
            "result": {"records": [{"end_of_day": NOW.date().isoformat(), "usd": 7.8}]}
        },
    )
    provider = FxProvider(
        session=SimpleNamespace(get=lambda *a, **kw: response),
        yahoo_metadata=fail,
        clock=lambda: times[0],
        timer=lambda: ticks[0],
    )
    first = provider.get()
    times[0] += timedelta(days=8)
    ticks[0] = 1
    assert first.metadata(times[0])["calendar_age_days"] == 8
    with pytest.raises(FxUnavailable):
        provider.get()


def test_stale_hkma_and_stale_yahoo_never_return_old_fx():
    def get(url, **kwargs):
        payload = (
            {"result": {"records": [{"end_of_day": "2026-10-31", "usd": 7.8}]}}
            if "hkma" in url
            else {
                "chart": {
                    "result": [
                        {
                            "meta": {
                                "symbol": "HKD=X",
                                "currency": "HKD",
                                "regularMarketPrice": 7.8,
                                "regularMarketTime": int(NOW.timestamp()) - 10 * 86400,
                            }
                        }
                    ]
                }
            }
        )
        return SimpleNamespace(
            content=b"{}", raise_for_status=lambda: None, json=lambda: payload
        )

    with pytest.raises(FxUnavailable):
        FxProvider(
            session=SimpleNamespace(get=get),
            yahoo_metadata=lambda: {
                "symbol": "HKD=X",
                "currency": "HKD",
                "regularMarketPrice": 7.8,
                "regularMarketTime": int(NOW.timestamp()) - 10 * 86400,
            },
            clock=lambda: NOW,
        ).get()
