"""Offline quote parsing, session scheduling and local publication regressions."""

import json
from datetime import UTC, datetime

import pytest
import requests

from src.hk import live
from src.hk.calendar import market_state


def payload(code="00700", price="400.0", stamp="2026/11/12 10:00:00"):
    values = [""] * 40
    for index, value in {2: code, 3: price, 6: "12500", 30: stamp, 32: "1.25"}.items():
        values[index] = value
    return f'v_r_hk{code}="' + "~".join(values) + '";'


@pytest.mark.parametrize("value", ["700", "0700", "0700.HK", "HK.00700"])
def test_aliases(value):
    assert live.symbol(value) == "0700.HK"


@pytest.mark.parametrize("value", ["0", "-1", "700.US", "10000", "７００"])
def test_bad_aliases(value):
    with pytest.raises(ValueError):
        live.symbol(value)


def test_parse_contract_and_timestamp():
    received = datetime(2026, 11, 12, 2, 0, 10, tzinfo=UTC)
    rows, errors = live.parse_quotes(payload(), received)
    assert not errors
    assert rows == [
        {
            "symbol": "0700.HK",
            "price": 400.0,
            "volume": 12500.0,
            "change_pct": 1.25,
            "ts_exchange": "2026-11-12T02:00:00+00:00",
            "ts_received": received.isoformat(),
            "source": "tencent",
        }
    ]


@pytest.mark.parametrize(
    "bad",
    [
        payload(price="nan"),
        payload(price="-1"),
        'v_r_hk00700="short";',
        payload(stamp="2026/11/13 10:00:00"),
    ],
)
def test_bad_symbol_does_not_discard_valid_symbol(bad):
    rows, errors = live.parse_quotes(
        bad + "\n" + payload("00005"),
        datetime(2026, 11, 12, 2, 0, 10, tzinfo=UTC),
    )
    assert [row["symbol"] for row in rows] == ["0005.HK"]
    assert len(errors) == 1


def test_batch_uses_faster_endpoint_and_deduplicates():
    class Response:
        text = payload() + "\n" + payload()

        def raise_for_status(self):
            pass

    class Session:
        def get(self, url, timeout):
            assert url == "https://qt.gtimg.cn/q=r_hk00700,r_hk00005"
            assert timeout == 4
            return Response()

    rows, errors = live.fetch_quotes(["700", "0700.HK", "5"], Session())
    assert len(rows) == 1
    assert {error["symbol"] for error in errors} == {"0005.HK"}


def test_network_failure_is_reported_per_symbol():
    class Session:
        def get(self, *args, **kwargs):
            raise requests.Timeout()

    rows, errors = live.fetch_quotes(["700", "5"], Session())
    assert not rows
    assert {error["symbol"] for error in errors} == {"0700.HK", "0005.HK"}


@pytest.mark.parametrize(
    "stamp,state",
    [
        ("2026-11-12T01:29:59+00:00", "closed"),
        ("2026-11-12T01:30:00+00:00", "open"),
        ("2026-11-12T04:00:00+00:00", "lunch"),
        ("2026-11-12T05:00:00+00:00", "open"),
        ("2026-11-12T08:00:00+00:00", "closed"),
        ("2026-11-14T02:00:00+00:00", "closed"),
        ("2026-10-01T02:00:00+00:00", "closed"),
        ("2026-12-24T05:00:00+00:00", "closed"),
    ],
)
def test_calendar(stamp, state):
    assert market_state(datetime.fromisoformat(stamp)) == state


def test_continuous_publishes_latest_before_shutdown(tmp_path, monkeypatch):
    calls = []
    now = datetime.now(UTC)
    row = {
        "symbol": "0700.HK",
        "price": 400.0,
        "volume": 1.0,
        "change_pct": 0.0,
        "ts_exchange": now.isoformat(),
        "ts_received": now.isoformat(),
        "source": "tencent",
    }

    def fetch(*args):
        calls.append(True)
        return [row], []

    def sleep(_seconds):
        # Readers can consume these while the continuous loop is still active.
        assert (
            json.loads((tmp_path / "latest.json").read_text())[0]["symbol"] == "0700.HK"
        )
        assert (
            json.loads((tmp_path / "status.json").read_text())["fresh_under_60s"] == 1
        )

    monkeypatch.setattr(live, "market_state", lambda _: "open")
    monkeypatch.setattr(live, "fetch_quotes", fetch)
    monkeypatch.setattr(live.time, "sleep", sleep)
    summary = live.run(
        ["700"], tmp_path, duration_seconds=0, should_stop=lambda: bool(calls)
    )
    assert summary["observations"] == 1
    assert len(list((tmp_path / "snapshots").rglob("*.parquet"))) == 1
    assert len(list((tmp_path / "daily").rglob("observations.jsonl"))) == 1


def test_finite_audit_refuses_existing_evidence(tmp_path):
    (tmp_path / "observations.jsonl").write_text("previous\n")
    with pytest.raises(FileExistsError):
        live.run(["700"], tmp_path, duration_seconds=1)
