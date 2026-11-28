"""Offline live-service tests using synthetic quotes/calendar and fake AWS clients."""

import copy
import csv
import logging
import socket
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from src.live.india import (
    BUCKET,
    COLUMNS,
    TABLE,
    CalendarCoverageError,
    DynamoLatestStore,
    IndiaLiveService,
    MockQuoteProvider,
    RetryPolicy,
    S3MinuteStore,
    SessionCalendar,
    load_nifty100_symbols,
    normalize_quote,
)

FIXTURES = Path(__file__).parent / "fixtures/live_india"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Live test attempted network/AWS access")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)


class Clock:
    def __init__(self, start="2024-01-02T03:45:00+00:00"):
        self.start = datetime.fromisoformat(start)
        self.elapsed = 0.0
        self.sleeps = []

    def now(self):
        return self.start + timedelta(seconds=self.elapsed)

    def monotonic(self):
        return self.elapsed

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.elapsed += seconds


class MemoryStore:
    def __init__(self):
        self.calls = []
        self.fail = False

    def write(self, *args):
        if self.fail:
            raise RuntimeError("SYNTHETIC_PRIVATE_STORAGE_MARKER")
        self.calls.append(copy.deepcopy(args))


@pytest.fixture
def setup():
    clock = Clock()
    provider = MockQuoteProvider.from_file(FIXTURES / "quotes.json")
    calendar = SessionCalendar.from_file(FIXTURES / "calendar.json")
    latest, snapshots = MemoryStore(), MemoryStore()
    service = IndiaLiveService(
        list(provider.quotes),
        provider,
        calendar,
        latest,
        snapshots,
        clock=clock.now,
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    )
    return SimpleNamespace(
        clock=clock,
        provider=provider,
        calendar=calendar,
        latest=latest,
        snapshots=snapshots,
        service=service,
    )


def test_schema_exchange_and_receipt_times_and_zero_volume(setup, caplog):
    caplog.set_level(logging.INFO)
    quotes = setup.service.step()
    assert len(quotes) == 3
    assert all(tuple(q) == COLUMNS for q in quotes)
    assert quotes[0]["ts_exchange"] == "2024-01-02T03:44:59+00:00"
    assert quotes[0]["ts_received"] == "2024-01-02T03:45:00+00:00"
    assert quotes[-1]["volume"] == 0
    assert setup.latest.calls[0][0] == quotes
    poll = next(r for r in caplog.records if r.message.startswith("india_live_poll "))
    assert poll.poll_latency_seconds == 0 and poll.max_exchange_age_seconds == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("price", float("nan")),
        ("price", -1),
        ("price", True),
        ("change_pct", float("inf")),
        ("volume", -1),
        ("volume", 1.5),
        ("volume", True),
        ("volume", "NaN"),
        ("volume", "9223372036854775808"),
        ("source", "unauthorized"),
        ("symbol", "^NSEI"),
        ("ts_exchange", "2024-01-02T09:15:00"),
        ("ts_exchange", "2024-01-02T03:45:01+00:00"),
    ],
)
def test_bad_symbol_does_not_block_other_quotes(setup, field, value):
    setup.provider.quotes["TCS.NS"][field] = value
    quotes = setup.service.step()
    assert {q["symbol"] for q in quotes} == {"RELIANCE.NS", "INFY.NS"}


def test_large_integral_volume_is_not_rounded(setup):
    row = dict(setup.provider.quotes["TCS.NS"], volume="9007199254740993")
    q = normalize_quote(row, "TCS.NS", setup.clock.now(), "mock_fixture")
    assert q["volume"] == 9007199254740993


def test_missing_and_explicit_symbol_errors_are_isolated(setup):
    del setup.provider.quotes["TCS.NS"]
    setup.provider.errors["INFY.NS"] = "synthetic"
    assert [q["symbol"] for q in setup.service.step()] == ["RELIANCE.NS"]


@pytest.mark.parametrize(
    "stamp,expected",
    [
        ("2024-01-02T03:44:59+00:00", False),
        ("2024-01-02T03:45:00+00:00", True),
        ("2024-01-02T09:59:59+00:00", True),
        ("2024-01-02T10:00:00+00:00", False),
        ("2024-01-03T04:00:00+00:00", False),
        ("2024-01-06T12:30:00+00:00", True),
        ("2024-01-07T04:00:00+00:00", False),
    ],
)
def test_explicit_session_holiday_and_special_session_gates(setup, stamp, expected):
    assert setup.calendar.is_open(datetime.fromisoformat(stamp)) is expected


def test_closed_and_uncovered_dates_make_no_provider_or_storage_calls(setup):
    setup.clock.start = datetime.fromisoformat("2024-01-03T04:00:00+00:00")
    assert setup.service.step() == []
    setup.clock.start = datetime.fromisoformat("2024-01-04T04:00:00+00:00")
    with pytest.raises(CalendarCoverageError):
        setup.calendar.is_open(setup.clock.now())
    assert setup.service.step() == []
    assert (
        not setup.provider.calls
        and not setup.latest.calls
        and not setup.snapshots.calls
    )


def test_calendar_rejects_missing_evidence_and_overlapping_sessions():
    with pytest.raises(ValueError):
        SessionCalendar({}, source="")
    with pytest.raises(ValueError):
        SessionCalendar(
            {"2024-01-02": [["09:15", "15:30"], ["10:00", "12:00"]]}, source="synthetic"
        )


def test_provider_batch_limit_and_transient_retry(setup):
    setup.provider.max_batch_size = 2
    original = setup.provider.fetch
    attempts = []

    def fetch(symbols):
        attempts.append(tuple(symbols))
        if len(attempts) < 3:
            raise RuntimeError("SYNTHETIC_PRIVATE_PROVIDER_MARKER")
        return original(symbols)

    setup.provider.fetch = fetch
    assert len(setup.service.step()) == 3
    assert len(attempts) == 4
    assert setup.clock.sleeps == [0.5, 1.0]
    assert all(len(b) <= 2 for b in attempts)


def test_exhausted_batch_does_not_block_later_batch_or_leak_errors(setup, caplog):
    setup.provider.max_batch_size = 2
    original = setup.provider.fetch

    def fetch(symbols):
        if "RELIANCE.NS" in symbols:
            raise RuntimeError("SECRET_PRIVATE_PATH_MARKER")
        return original(symbols)

    setup.provider.fetch = fetch
    assert [q["symbol"] for q in setup.service.step()] == ["INFY.NS"]
    assert "SECRET_PRIVATE_PATH_MARKER" not in caplog.text


def test_permission_denial_blocks_subsequent_polls_without_retry(setup):
    calls = []

    def deny(symbols):
        calls.append(symbols)
        raise PermissionError("synthetic access denied")

    setup.provider.fetch = deny
    assert setup.service.step() == setup.service.step() == []
    assert len(calls) == 1 and not setup.clock.sleeps


def test_no_retry_after_session_closes(setup):
    setup.clock.start = datetime.fromisoformat("2024-01-02T09:59:59.800000+00:00")
    calls = []

    def fail(symbols):
        calls.append(symbols)
        raise RuntimeError("synthetic timeout")

    setup.provider.fetch = fail
    assert setup.service.step() == []
    assert len(calls) == 1


def test_unexpected_response_symbol_is_rejected(setup):
    setup.provider.fetch = lambda symbols: {"OTHER.NS": {}}
    assert setup.service.step() == [] and not setup.latest.calls


def test_minute_snapshot_last_quote_and_no_previous_minute_forward_fill(setup):
    setup.service.step()
    setup.clock.sleep(5)
    setup.provider.quotes["RELIANCE.NS"]["price"] = 101.5
    setup.service.step()
    setup.clock.sleep(55)
    del setup.provider.quotes["INFY.NS"]
    setup.service.step()
    first_minute, rows = setup.snapshots.calls[0]
    assert first_minute.minute == 45 and len(rows) == 3
    assert next(r for r in rows if r["symbol"] == "RELIANCE.NS")["price"] == 101.5
    setup.service.flush(force=True)
    assert len(setup.snapshots.calls[1][1]) == 2


def test_close_flushes_last_minute_without_polling(setup):
    setup.clock.start = datetime.fromisoformat("2024-01-02T09:59:55+00:00")
    setup.service.step()
    setup.clock.sleep(5)
    assert setup.service.step() == []
    assert len(setup.provider.calls) == 1 and len(setup.snapshots.calls) == 1


def test_snapshot_failure_retains_buffer_and_pauses_polling_until_recovery(setup):
    setup.service.step()
    setup.clock.sleep(60)
    setup.snapshots.fail = True
    assert setup.service.step() == []
    assert len(setup.provider.calls) == 1
    setup.snapshots.fail = False
    assert len(setup.service.step()) == 3
    assert len(setup.snapshots.calls) == 1


def test_latest_store_failure_does_not_discard_snapshot(setup):
    setup.latest.fail = True
    assert len(setup.service.step()) == 3
    setup.service.flush(force=True)
    assert len(setup.snapshots.calls[0][1]) == 3


@pytest.mark.parametrize("interval,authorized", [(5, False), (60, True)])
def test_run_cadence_and_graceful_partial_minute_flush(setup, interval, authorized):
    setup.service.interval = interval
    if interval == 60:
        setup.service = IndiaLiveService(
            list(setup.provider.quotes),
            setup.provider,
            setup.calendar,
            setup.latest,
            setup.snapshots,
            poll_interval_seconds=60,
            fallback_authorized=authorized,
            clock=setup.clock.now,
            monotonic=setup.clock.monotonic,
            sleep=setup.clock.sleep,
        )
    setup.service.run(max_cycles=2)
    assert setup.clock.sleeps == [interval] and len(setup.provider.calls) == 2
    assert setup.snapshots.calls


@pytest.mark.parametrize("interval", [1, 10, 60])
def test_disallowed_poll_cadence(setup, interval):
    with pytest.raises(ValueError):
        IndiaLiveService(
            list(setup.provider.quotes),
            setup.provider,
            setup.calendar,
            setup.latest,
            setup.snapshots,
            poll_interval_seconds=interval,
        )


def test_poll_latency_includes_work_and_avoids_overlapping_catchup(setup, caplog):
    original = setup.provider.fetch

    def slow(symbols):
        setup.clock.sleep(7)
        return original(symbols)

    setup.provider.fetch = slow
    caplog.set_level(logging.INFO)
    setup.service.run(max_cycles=2)
    polls = [r for r in caplog.records if r.message.startswith("india_live_poll ")]
    assert all(r.poll_latency_seconds == 7 for r in polls)
    assert setup.clock.sleeps == [7, 0, 7]


class FakeDynamo:
    meta = SimpleNamespace(region_name="us-east-2")

    def __init__(self, responses=()):
        self.calls, self.responses = [], list(responses)

    def batch_write_item(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        return self.responses.pop(0)(kwargs) if self.responses else {}


class FakeS3:
    meta = SimpleNamespace(region_name="us-east-2")

    def __init__(self, failures=0):
        self.calls, self.failures = [], failures

    def put_object(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) <= self.failures:
            raise RuntimeError("synthetic S3 timeout")


def test_dynamodb_100_names_batches_25_and_retries_only_unprocessed(setup):
    q = setup.service.step()[0]
    quotes = [dict(q, symbol=f"S{i:03d}.NS") for i in range(100)]

    def unprocessed(request):
        return {"UnprocessedItems": {TABLE: request["RequestItems"][TABLE][:1]}}

    client = FakeDynamo([unprocessed])
    DynamoLatestStore(client, sleep=setup.clock.sleep).write(quotes)
    assert [len(c["RequestItems"][TABLE]) for c in client.calls] == [25, 1, 25, 25, 25]
    item = client.calls[0]["RequestItems"][TABLE][0]["PutRequest"]["Item"]
    assert set(item) == set(COLUMNS)
    assert item["price"] == {"N": "100.5"} and item["volume"] == {"N": "1000"}


def test_unprocessed_write_exhaustion_and_injected_item_rejection(setup):
    q = setup.service.step()
    client = FakeDynamo([lambda req: {"UnprocessedItems": req["RequestItems"]}] * 3)
    with pytest.raises(RuntimeError):
        DynamoLatestStore(client, sleep=setup.clock.sleep).write(q)
    assert len(client.calls) == 3
    client = FakeDynamo([lambda req: {"UnprocessedItems": {"wrong-table": []}}])
    with pytest.raises(ValueError):
        DynamoLatestStore(client, sleep=setup.clock.sleep).write(q)
    assert len(client.calls) == 1


def test_real_parquet_roundtrip_official_columns_utc_key_and_retry(setup):
    quotes = setup.service.step()
    client = FakeS3(failures=2)
    store = S3MinuteStore(client, sleep=setup.clock.sleep)
    store.write(setup.clock.now(), quotes)
    assert len(client.calls) == 3
    call = client.calls[-1]
    assert call["Bucket"] == BUCKET
    assert call["Key"] == "raw/live/india/date=2024-01-02/0345.parquet"
    assert all(c["Body"] == call["Body"] for c in client.calls)
    restored = pd.read_parquet(BytesIO(call["Body"]))
    assert tuple(restored.columns) == COLUMNS
    assert restored.to_dict("records") == quotes


def test_no_empty_snapshot_and_wrong_aws_region_rejected(setup):
    client = FakeS3()
    S3MinuteStore(client).write(setup.clock.now(), [])
    assert not client.calls
    wrong = SimpleNamespace(meta=SimpleNamespace(region_name="us-east-1"))
    with pytest.raises(ValueError):
        S3MinuteStore(wrong)
    with pytest.raises(ValueError):
        DynamoLatestStore(wrong)


def test_end_to_end_100_names_mock_provider_dynamodb_and_real_parquet(setup):
    template = setup.provider.quotes["RELIANCE.NS"]
    provider = MockQuoteProvider(
        {f"S{i:03d}.NS": dict(template, symbol=f"S{i:03d}.NS") for i in range(100)}
    )
    dynamo, s3 = FakeDynamo(), FakeS3()
    service = IndiaLiveService(
        list(provider.quotes),
        provider,
        setup.calendar,
        DynamoLatestStore(dynamo, sleep=setup.clock.sleep),
        S3MinuteStore(s3, sleep=setup.clock.sleep),
        clock=setup.clock.now,
        monotonic=setup.clock.monotonic,
        sleep=setup.clock.sleep,
    )
    service.run(max_cycles=1)
    assert len(provider.calls) == 1 and len(provider.calls[0]) == 100
    assert len(dynamo.calls) == 4
    assert all(len(c["RequestItems"][TABLE]) == 25 for c in dynamo.calls)
    frame = pd.read_parquet(BytesIO(s3.calls[0]["Body"]))
    assert len(frame) == 100 and frame.symbol.nunique() == 100
    assert tuple(frame.columns) == COLUMNS


def test_stop_event_interrupts_loop_and_flushes_without_extra_poll(setup):
    class Stop:
        def __init__(self):
            self.stopped = False
            self.delays = []

        def is_set(self):
            return self.stopped

        def wait(self, delay):
            self.delays.append(delay)
            self.stopped = True

    event = Stop()
    setup.service.run(stop_event=event)
    assert len(setup.provider.calls) == 1 and event.delays == [5]
    assert len(setup.snapshots.calls) == 1


@pytest.mark.parametrize("kind", ["valid", "duplicate", "missing", "wrong_series"])
def test_local_official_style_nifty100_roster(tmp_path, kind):
    rows = [{"Symbol": f"S{i:03d}", "Series": "EQ"} for i in range(100)]
    if kind == "duplicate":
        rows[-1] = rows[0].copy()
    elif kind == "missing":
        rows.pop()
    elif kind == "wrong_series":
        rows[0]["Series"] = "BE"
    path = tmp_path / "synthetic_constituents.csv"
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["Symbol", "Series"])
        writer.writeheader()
        writer.writerows(rows)
    if kind == "valid":
        assert len(load_nifty100_symbols(path)) == 100
    else:
        with pytest.raises(ValueError):
            load_nifty100_symbols(path)


@pytest.mark.parametrize(
    "policy",
    [
        {"attempts": 0},
        {"attempts": True},
        {"base_seconds": -1},
        {"cap_seconds": float("inf")},
    ],
)
def test_invalid_retry_policy_rejected(policy):
    with pytest.raises(ValueError):
        RetryPolicy(**policy)
