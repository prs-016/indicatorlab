"""Offline fault, calendar and retained-state checks for the shared live loop."""

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pandas as pd
import pytest

from src.live.base import AwsSink, LocalSink, PollLoop
from src.live.hk import TencentSource, session_gate

NOW = datetime(2026, 11, 16, 2, 0, tzinfo=UTC)


def quote(symbol="0700.HK", at=NOW):
    return {
        "symbol": symbol,
        "price": 100,
        "change_pct": 1,
        "volume": 50,
        "ts_exchange": (at - timedelta(seconds=2)).isoformat(),
        "ts_received": at.isoformat(),
        "source": "tencent",
    }


def open_gate(now):
    return "open", now


def test_partial_poll_keeps_other_symbols_and_complete_minute_view(tmp_path):
    source = Mock()
    source.fetch.side_effect = [
        ([quote(), quote("0005.HK")], []),
        (
            [quote(at=NOW + timedelta(minutes=1))],
            [{"symbol": "0005.HK", "error": "bad"}],
        ),
    ]
    sink = LocalSink(tmp_path)
    loop = PollLoop(["0700.HK", "0005.HK"], source, sink, open_gate)
    loop.step(NOW)
    loop.step(NOW + timedelta(minutes=1))
    frame = pd.read_parquet(tmp_path / "snapshots/date=2026-11-16/0201.parquet")
    assert set(frame.symbol) == {"0700.HK", "0005.HK"}
    assert loop.latest["0005.HK"]["ts_received"] == NOW.isoformat()


def test_sink_retry_retains_pending_updates():
    source, sink = Mock(), Mock()
    source.fetch.side_effect = [([quote()], []), ([], [])]
    sink.write.side_effect = [OSError("transient"), None]
    loop = PollLoop(["0700.HK"], source, sink, open_gate)
    assert loop.step(NOW) == 1
    assert len(loop.pending) == 1
    loop.step(NOW + timedelta(seconds=1))
    assert len(sink.write.call_args.args[0]) == 1
    assert loop.pending == {}


def test_source_outage_still_snapshots_retained_quotes(tmp_path):
    source = Mock()
    source.fetch.side_effect = [([quote()], []), ConnectionError("outage")]
    loop = PollLoop(["0700.HK"], source, LocalSink(tmp_path), open_gate)
    loop.step(NOW)
    assert loop.step(NOW + timedelta(minutes=1)) == 1
    frame = pd.read_parquet(tmp_path / "snapshots/date=2026-11-16/0201.parquet")
    assert frame.symbol.tolist() == ["0700.HK"]


def test_post_fetch_clock_accepts_quotes_received_after_slow_batch(monkeypatch):
    source, sink = Mock(), Mock()
    source.fetch.return_value = ([quote(at=NOW + timedelta(seconds=7))], [])
    clock = Mock(wraps=datetime)
    clock.now.side_effect = [NOW, NOW + timedelta(seconds=8)]
    monkeypatch.setattr("src.live.base.datetime", clock)
    loop = PollLoop(["0700.HK"], source, sink, open_gate)
    loop.step()
    assert len(loop.latest) == 1
    assert sink.write.call_args.args[2] == NOW + timedelta(seconds=8)


def test_exponential_backoff_is_capped():
    source, sink = Mock(), Mock()
    source.fetch.side_effect = ConnectionError("temporary")
    loop = PollLoop(["0700.HK"], source, sink, open_gate)
    assert [loop.step(NOW) for _ in range(8)] == [1, 2, 4, 8, 16, 30, 30, 30]


def test_invalid_unknown_and_older_quotes_do_not_replace_latest():
    source, sink = Mock(), Mock()
    source.fetch.side_effect = [
        ([quote()], []),
        (
            [
                quote(at=NOW - timedelta(minutes=1)),
                quote("9999.HK"),
                dict(quote(), price=float("nan")),
            ],
            [],
        ),
    ]
    loop = PollLoop(["0700.HK"], source, sink, open_gate)
    loop.step(NOW)
    loop.step(NOW + timedelta(seconds=5))
    assert list(loop.latest) == ["0700.HK"]
    assert loop.latest["0700.HK"]["ts_received"] == NOW.isoformat()


@pytest.mark.parametrize(
    "at,state,next_at",
    [
        ("2026-11-16T04:15:00+00:00", "lunch", "2026-11-16T05:00:00+00:00"),
        ("2026-10-01T02:00:00+00:00", "closed", "2026-10-02T01:30:00+00:00"),
        ("2023-10-09T02:00:00+00:00", "closed", "2023-10-09T06:00:00+00:00"),
    ],
)
def test_calendar_gates_polling(at, state, next_at):
    now = datetime.fromisoformat(at)
    assert session_gate(now) == (state, datetime.fromisoformat(next_at))
    source = Mock()
    loop = PollLoop(["0700.HK"], source, Mock(), session_gate)
    assert loop.step(now) == (datetime.fromisoformat(next_at) - now).total_seconds()
    source.fetch.assert_not_called()


def test_aws_snapshot_uses_all_latest_and_batch_writer():
    table, s3, cw = Mock(), Mock(), Mock()
    batch = Mock()
    table.batch_writer.return_value.__enter__ = Mock(return_value=batch)
    table.batch_writer.return_value.__exit__ = Mock(return_value=False)
    sink = AwsSink("hk", table, s3, cw, "example")
    sink.write([quote()], [quote(), quote("0005.HK", NOW - timedelta(seconds=90))], NOW)
    table.batch_writer.assert_called_once_with(overwrite_by_pkeys=["symbol"])
    batch.put_item.assert_called_once()
    import io

    saved = pd.read_parquet(io.BytesIO(s3.put_object.call_args.kwargs["Body"]))
    assert len(saved) == 2
    assert (
        s3.put_object.call_args.kwargs["Key"]
        == "raw/live/hk/date=2026-11-16/0200.parquet"
    )
    assert cw.put_metric_data.call_args.kwargs["MetricData"][0]["Value"] == 90


def test_tencent_request_timeout_and_batching():
    session = Mock()
    session.get.return_value.text = ""
    source = TencentSource(session)
    source.fetch([f"{i:04d}.HK" for i in range(1, 102)])
    assert session.get.call_count == 2
    assert all(call.kwargs["timeout"] == 3 for call in session.get.call_args_list)
