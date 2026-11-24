"""Offline bootstrap tests: synthetic review records, instruments and AWS clients."""

import hashlib
import json
import logging
import signal
import socket
import sys
from datetime import UTC, datetime
from io import BytesIO
from types import SimpleNamespace

import pandas as pd
import pytest

from src.live import india_app as app
from src.live.india import COLUMNS

NOW = datetime(2024, 1, 2, 3, 45, 5, tzinfo=UTC)
ENV = {"DHAN_CLIENT_ID": "synthetic-id", "DHAN_ACCESS_TOKEN": "synthetic-token"}
MARKER = "PRIVATE_SECRET_/home/private?token=SECRET"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def deny(*args, **kwargs):
        pytest.fail("Network forbidden in bootstrap tests")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)


@pytest.fixture
def config(tmp_path):
    names = [f"SYN{i}.NS" for i in range(100)]
    roster = tmp_path / "roster.csv"
    roster.write_text("Symbol,Series\n" + "".join(f"{s[:-3]},EQ\n" for s in names))
    instruments = tmp_path / "instruments.json"
    instruments.write_text(
        json.dumps(
            {
                s: {"security_id": i + 1, "exchange_segment": "NSE_EQ"}
                for i, s in enumerate(names)
            }
        )
    )
    calendar = tmp_path / "calendar.json"
    calendar.write_text(
        json.dumps(
            {
                "timezone": "Asia/Kolkata",
                "source": "SYNTHETIC TEST ONLY",
                "sessions": {"2024-01-02": [["09:15", "15:30"]]},
            }
        )
    )
    document = {
        "review": {
            "approved": True,
            "reviewed_by": "synthetic reviewer",
            "source": "synthetic verification only, not operational approval",
            "reviewed_at": "2024-01-01T00:00:00+00:00",
            "valid_from": "2024-01-02",
            "valid_until": "2024-01-02",
        }
    }
    for name, path in [
        ("roster", roster),
        ("instruments", instruments),
        ("calendar", calendar),
    ]:
        document[name] = {
            "path": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    path = tmp_path / "runtime.json"
    path.write_text(json.dumps(document))
    return path


def update(config, change):
    doc = json.loads(config.read_text())
    change(doc)
    config.write_text(json.dumps(doc))


def rehash(config, key):
    doc = json.loads(config.read_text())
    doc[key]["sha256"] = hashlib.sha256(
        (config.parent / doc[key]["path"]).read_bytes()
    ).hexdigest()
    config.write_text(json.dumps(doc))


def prepare(config, **kwargs):
    return app.prepare_runtime(config, environ=ENV, clock=lambda: NOW, **kwargs)


class Client:
    meta = SimpleNamespace(region_name="us-east-2")

    def __init__(self):
        self.writes = []

    def batch_write_item(self, **kw):
        self.writes.append(kw)
        return {"UnprocessedItems": {}}

    def put_object(self, **kw):
        self.writes.append(kw)
        return {}


def test_full_bootstrap_hundred_quotes_to_real_sinks(config, monkeypatch):
    runtime = prepare(config)
    calls = []
    raw = {
        "status": "success",
        "data": {
            "NSE_EQ": {
                str(i + 1): {
                    "last_price": 100,
                    "net_change": 1,
                    "volume": 1000,
                    "last_trade_time": "02/01/2024 09:15:00",
                }
                for i in range(100)
            }
        },
    }

    def post(*args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(status_code=200, json=lambda: raw)

    monkeypatch.setattr(runtime.provider._session, "post", post)
    clients = {key: Client() for key in ["dynamodb", "s3"]}
    service = app.build_service(
        runtime, client_factory=clients.__getitem__, clock=lambda: NOW
    )
    assert calls == [] and all(c.writes == [] for c in clients.values())
    quotes = service.step()
    assert len(quotes) == 100 and len(calls) == 1
    assert tuple(quotes[0]) == COLUMNS
    batches = clients["dynamodb"].writes
    assert len(batches) == 4
    assert all(len(b["RequestItems"]["indicatorlab-live-india"]) == 25 for b in batches)
    service.flush(force=True)
    upload = clients["s3"].writes[0]
    assert upload["Bucket"] == "indicatorlab-data"
    assert upload["Key"] == "raw/live/india/date=2024-01-02/0345.parquet"
    frame = pd.read_parquet(BytesIO(upload["Body"]))
    assert len(frame) == 100 and list(frame.columns) == list(COLUMNS)


@pytest.mark.parametrize(
    "field,value",
    [
        ("approved", False),
        ("approved", "true"),
        ("reviewed_by", ""),
        ("source", ""),
        ("reviewed_at", "2024-01-03T00:00:00+00:00"),
        ("reviewed_at", "2024-01-01T00:00:00"),
        ("valid_until", "2024-01-01"),
        ("valid_from", "2024-01-03"),
    ],
)
def test_review_gate(config, field, value):
    update(config, lambda d: d["review"].update({field: value}))
    with pytest.raises(ValueError):
        prepare(config)


@pytest.mark.parametrize("key", ["roster", "instruments", "calendar"])
def test_tampered_file(config, key):
    doc = json.loads(config.read_text())
    path = config.parent / doc[key]["path"]
    path.write_text(path.read_text() + "\n")
    with pytest.raises(ValueError, match="checksum"):
        prepare(config)


@pytest.mark.parametrize("key", ["roster", "instruments", "calendar"])
def test_unbound_absolute_paths(config, key):
    update(config, lambda d: d[key].update(path="/private/file"))
    with pytest.raises(ValueError, match="relative"):
        prepare(config)


def test_incomplete_instruments(config):
    path = config.parent / "instruments.json"
    mapping = json.loads(path.read_text())
    del mapping["SYN0.NS"]
    path.write_text(json.dumps(mapping))
    rehash(config, "instruments")
    with pytest.raises(ValueError, match="exactly match"):
        prepare(config)


def test_bad_instrument_identity(config):
    path = config.parent / "instruments.json"
    mapping = json.loads(path.read_text())
    mapping["SYN0.NS"]["exchange_segment"] = "BSE_EQ"
    path.write_text(json.dumps(mapping))
    rehash(config, "instruments")
    with pytest.raises(ValueError, match="NSE_EQ"):
        prepare(config)


def test_incomplete_calendar(config):
    update(config, lambda d: d["review"].update(valid_until="2024-01-03"))
    with pytest.raises(ValueError, match="uncovered"):
        prepare(config)


def test_explicit_closure_is_covered(config):
    path = config.parent / "calendar.json"
    d = json.loads(path.read_text())
    d["sessions"]["2024-01-02"] = []
    path.write_text(json.dumps(d))
    rehash(config, "calendar")
    runtime = prepare(config)
    service = app.build_service(
        runtime, client_factory=lambda _: Client(), clock=lambda: NOW
    )
    assert service.step() == []


def test_runtime_expiry_stops_quotes(config, monkeypatch):
    runtime = prepare(config)

    def denied(*args, **kwargs):
        pytest.fail("Expired review contacted broker")

    monkeypatch.setattr(runtime.provider, "fetch", denied)
    service = app.build_service(
        runtime,
        client_factory=lambda _: Client(),
        clock=lambda: datetime(2024, 1, 3, 4, tzinfo=UTC),
    )
    with pytest.raises(ValueError, match="expired"):
        service.step()


@pytest.mark.parametrize(
    "interval,fallback,valid",
    [
        (5, False, True),
        (60, True, True),
        (60, False, False),
        (5, "true", False),
        (True, False, False),
        (1, False, False),
    ],
)
def test_cadence(config, interval, fallback, valid):
    update(
        config,
        lambda d: d.update(
            poll_interval_seconds=interval, fallback_authorized=fallback
        ),
    )
    if valid:
        assert prepare(config).interval == interval
    else:
        with pytest.raises(ValueError):
            prepare(config)


def test_missing_credentials_before_aws(config):
    with pytest.raises(PermissionError):
        app.prepare_runtime(config, environ={}, clock=lambda: NOW)


def test_validate_cli_never_builds_aws(config, monkeypatch):
    runtime = prepare(config)
    monkeypatch.setenv("INDIA_LIVE_CONFIG", str(config))
    monkeypatch.setattr(app, "prepare_runtime", lambda _: runtime)

    def denied(*args):
        pytest.fail("Validation created AWS clients")

    monkeypatch.setattr(app, "build_service", denied)
    assert app.main([]) == 0
    assert ENV["DHAN_ACCESS_TOKEN"] not in repr(runtime)


def test_run_cli_signals_and_graceful_run(config, monkeypatch):
    runtime = prepare(config)
    handlers = {}
    runs = []
    monkeypatch.setenv("INDIA_LIVE_CONFIG", str(config))
    monkeypatch.setattr(app, "prepare_runtime", lambda _: runtime)

    def run(*, stop_event):
        handlers[signal.SIGTERM](signal.SIGTERM, None)
        assert stop_event.is_set()
        runs.append(True)

    monkeypatch.setattr(app, "build_service", lambda _: SimpleNamespace(run=run))

    def set_signal(sig, handler):
        previous = handlers.get(sig, "original")
        handlers[sig] = handler
        return previous

    monkeypatch.setattr(app.signal, "signal", set_signal)
    assert app.main(["--run"]) == 0 and runs == [True]
    assert all(v == "original" for v in handlers.values())


def test_safe_failure_cli(monkeypatch, caplog):
    monkeypatch.setenv("INDIA_LIVE_CONFIG", MARKER)
    with caplog.at_level(logging.ERROR):
        assert app.main(["--run"]) == 1
    assert MARKER not in caplog.text and "FileNotFoundError" in caplog.text


def test_missing_config_cli(monkeypatch):
    monkeypatch.delenv("INDIA_LIVE_CONFIG", raising=False)
    assert app.main(["--run"]) == 1


def test_missing_sdk_is_explicit(monkeypatch):
    monkeypatch.setitem(sys.modules, "boto3", None)
    with pytest.raises(RuntimeError, match="boto3"):
        app.aws_client_factory()


def test_aws_factory_uses_role_chain_and_bounded_timeouts(monkeypatch):
    seen = {}

    def config(**kwargs):
        seen["config"] = kwargs
        return "bounded-config"

    def session(**kwargs):
        seen["session"] = kwargs

        def client(name, **kw):
            seen[name] = kw
            return name

        return SimpleNamespace(client=client)

    monkeypatch.setitem(
        sys.modules, "boto3", SimpleNamespace(session=SimpleNamespace(Session=session))
    )
    monkeypatch.setitem(sys.modules, "botocore.config", SimpleNamespace(Config=config))
    factory = app.aws_client_factory()
    assert factory("dynamodb") == "dynamodb"
    assert seen["session"] == {"region_name": "us-east-2"}
    assert seen["config"] == {
        "connect_timeout": 3,
        "read_timeout": 5,
        "retries": {"mode": "standard", "total_max_attempts": 3},
    }
    assert seen["dynamodb"] == {"region_name": "us-east-2", "config": "bounded-config"}


def test_yahoo_bootstrap_writes_reviewed_quotes_without_dhan(config, monkeypatch):
    from src.live.yahoo import YahooQuoteProvider

    symbols_loaded = []
    writes_at = []

    class TimedClient(Client):
        def batch_write_item(self, **kw):
            writes_at.append(len(symbols_loaded))
            return super().batch_write_item(**kw)

    def load(symbol, modules):
        symbols_loaded.append(symbol)
        assert modules == ["price"]
        return {
            "price": {
                "symbol": symbol,
                "currency": "INR",
                "regularMarketPrice": {"raw": 100},
                "regularMarketChangePercent": {"raw": 0.0125, "fmt": "1.25%"},
                "regularMarketVolume": {"raw": 1000},
                "regularMarketTime": {"raw": int(NOW.timestamp())},
            },
        }

    update(config, lambda d: (d.update(provider="yahoo"), d.pop("instruments")))
    monkeypatch.setattr(app, "YahooQuoteProvider", lambda: YahooQuoteProvider(load))
    runtime = app.prepare_runtime(config, environ={}, clock=lambda: NOW)
    clients = {"s3": Client(), "dynamodb": TimedClient()}
    service = app.build_service(
        runtime, client_factory=clients.__getitem__, clock=lambda: NOW
    )
    quotes = service.step()
    assert runtime.region == "us-east-2" and service.interval == 60
    assert len(quotes) == 100 and quotes[0]["change_pct"] == 1.25
    assert quotes[0]["source"] == "yahoo" and tuple(quotes[0]) == COLUMNS
    assert writes_at == [25, 50, 75, 100]
    assert service.flush(force=True)
    assert (
        clients["s3"].writes[0]["Key"] == "raw/live/india/date=2024-01-02/0345.parquet"
    )


@pytest.mark.parametrize("status", [401, 403, 429, 503])
def test_yahoo_http_errors_preserve_retry_contract(status):
    import requests

    from src.live.yahoo import YahooQuoteProvider

    def fail(*_):
        response = requests.Response()
        response.status_code = status
        raise requests.HTTPError(response=response)

    error = PermissionError if status < 500 else requests.HTTPError
    with pytest.raises(error):
        YahooQuoteProvider(fail).fetch(("SYN0.NS",))


@pytest.mark.parametrize(
    "change",
    [{"provider": "yahoo", "poll_interval_seconds": 5}, {"provider": "unknown"}],
)
def test_invalid_provider_configuration_is_rejected(config, change):
    update(config, lambda document: document.update(change))
    with pytest.raises(ValueError):
        app.prepare_runtime(config, environ={}, clock=lambda: NOW)


def test_deployment_provider_must_match_reviewed_config(config):
    with pytest.raises(ValueError, match="Deployment provider"):
        app.prepare_runtime(
            config, environ={"INDIA_LIVE_PROVIDER": "yahoo"}, clock=lambda: NOW
        )
