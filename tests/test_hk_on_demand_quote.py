"""On-demand source routing, parser parity, timing and cache contracts."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

from src.hk.live import parse_quotes
from src.live.quote import (
    QuoteService,
    QuoteUnavailable,
    get_quote,
    parse_tencent_quote,
)
from src.markets.errors import UnknownTicker

NOW = datetime(2026, 11, 23, 2, tzinfo=UTC)


def payload(code="00700", stamp="2026/11/23 10:00:00", price="400"):
    fields = [""] * 40
    for index, value in {2: code, 3: price, 6: "12500", 30: stamp, 32: "1.25"}.items():
        fields[index] = value
    return f'v_r_hk{code}="' + "~".join(fields) + '";'


def row(symbol="0700.HK", age=10):
    return {
        "symbol": symbol,
        "price": Decimal(400),
        "volume": Decimal(12500),
        "change_pct": Decimal("1.25"),
        "ts_exchange": (NOW - timedelta(seconds=age)).isoformat(),
        "ts_received": NOW.isoformat(),
        "source": "tencent",
    }


def test_standard_counter_reuses_frozen_collector_parser():
    wire = payload()
    assert parse_tencent_quote(wire, "700", NOW) == parse_quotes(wire, NOW)[0][0]


def test_five_digit_counter_extension_preserves_identity():
    value = parse_tencent_quote(payload("80737"), "80737", NOW)
    assert value["symbol"] == "80737.HK"


def test_hsi_default_uses_single_getitem_not_tencent_or_scan():
    calls = []
    service = QuoteService(symbols=["700"], clock=lambda: NOW)
    service.table = SimpleNamespace(
        get_item=lambda **kw: calls.append(kw) or {"Item": row()}
    )
    value = service.get("00700")
    assert value["store"] == "dynamodb" and value["label"] == "live"
    assert calls == [{"Key": {"symbol": "0700.HK"}, "ConsistentRead": True}]


def test_five_second_cache_deduplicates_aliases_and_returns_copies():
    calls = []
    tick = [0]
    service = QuoteService(
        hsi_reader=lambda symbol: calls.append(symbol) or row(),
        symbols=["700"],
        clock=lambda: NOW,
        timer=lambda: tick[0],
    )
    value = service.get("700")
    value["price"] = 1
    assert service.get("0700.HK")["price"] == 400
    assert len(calls) == 1
    tick[0] = 5
    service.get("700")
    assert len(calls) == 2


def test_cache_relabels_at_lunch_boundary_without_new_quote_request():
    times = [datetime(2026, 11, 23, 3, 59, 59, tzinfo=UTC)]
    data = row()
    data["ts_exchange"] = data["ts_received"] = times[0].isoformat()
    calls = []
    service = QuoteService(
        hsi_reader=lambda _: calls.append(1) or data,
        symbols=["700"],
        clock=lambda: times[0],
        timer=lambda: 0,
    )
    assert service.get("700")["label"] == "live"
    times[0] += timedelta(seconds=1)
    value = service.get("700")
    assert value["label"] == "lunch break" and value["market_open"] is False
    assert len(calls) == 1


@pytest.mark.parametrize(
    "stamp,label",
    [
        ("2026-11-23T08:00:00+00:00", "market closed"),
        ("2026-12-24T05:00:00+00:00", "market closed"),
        ("2026-12-25T02:00:00+00:00", "market closed"),
    ],
)
def test_closed_half_day_and_holiday(stamp, label):
    now = datetime.fromisoformat(stamp)
    service = QuoteService(
        hsi_reader=lambda _: row(), symbols=["700"], clock=lambda: now
    )
    value = service.get("700")
    assert value["label"] == label and not value["market_open"]


def test_old_exchange_timestamp_marks_delayed_even_with_fresh_receipt():
    service = QuoteService(
        hsi_reader=lambda _: row(age=125), symbols=["700"], clock=lambda: NOW
    )
    assert service.get("700")["label"] == "delayed ~2 min"


def test_non_hsi_fetches_faster_tencent_endpoint():
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        return SimpleNamespace(
            content=b"quote",
            encoding=None,
            text=payload("00100"),
            raise_for_status=lambda: None,
        )

    service = QuoteService(
        symbols=["700"], session=SimpleNamespace(get=get), clock=lambda: NOW
    )
    assert service.get("100")["symbol"] == "0100.HK"
    assert calls == ["https://qt.gtimg.cn/q=r_hk00100"]


def test_provider_unknown_and_network_outage_remain_distinct():
    session = SimpleNamespace(
        get=lambda *a, **kw: SimpleNamespace(
            content=b"none",
            encoding=None,
            text='v_pv_none_match="1";',
            raise_for_status=lambda: None,
        )
    )
    service = QuoteService(symbols=[], session=session, clock=lambda: NOW)
    with pytest.raises(UnknownTicker):
        service.get("99999")

    def timeout(*args, **kwargs):
        raise requests.Timeout()

    service.session = SimpleNamespace(get=timeout)
    with pytest.raises(QuoteUnavailable):
        service.get("100")


def test_missing_hsi_quote_does_not_silently_switch_source():
    service = QuoteService(
        hsi_reader=lambda _: None, symbols=["700"], clock=lambda: NOW
    )
    with pytest.raises(QuoteUnavailable, match="stored quote"):
        service.get("700")


def test_mismatched_identity_and_future_timestamps_rejected():
    service = QuoteService(
        hsi_reader=lambda _: row("0005.HK"), symbols=["700"], clock=lambda: NOW
    )
    with pytest.raises(QuoteUnavailable):
        service.get("700")
    with pytest.raises(QuoteUnavailable):
        parse_tencent_quote(payload(stamp="2026/11/24 10:00:00"), "700", NOW)


def test_other_owners_branches_remain_explicit():
    with pytest.raises(NotImplementedError):
        get_quote("AAPL", "us")


def test_recorded_tencent_response_and_capture_provenance():
    root = Path(__file__).parent / "fixtures/hk_on_demand"
    captures = json.loads((root / "CAPTURE.json").read_text())
    record = next(row for row in captures if row["file"] == "tencent_quotes.txt")
    text = (root / "tencent_quotes.txt").read_text()
    assert hashlib.sha256(text.encode()).hexdigest() == record["sha256"]
    now = datetime.fromisoformat(record["captured_at_utc"])
    for symbol in ["0700.HK", "0100.HK", "80737.HK"]:
        quote = parse_tencent_quote(text, symbol, now)
        assert quote["symbol"] == symbol and quote["price"] > 0
        assert datetime.fromisoformat(quote["ts_exchange"]) <= now


def test_recorded_provider_not_found_is_unknown():
    text = (
        Path(__file__).parent / "fixtures/hk_on_demand/tencent_unknown.txt"
    ).read_text()
    session = SimpleNamespace(
        get=lambda *a, **kw: SimpleNamespace(
            content=text.encode(),
            encoding=None,
            text=text,
            raise_for_status=lambda: None,
        )
    )
    with pytest.raises(UnknownTicker):
        QuoteService(symbols=[], session=session, clock=lambda: NOW).get("99999")
