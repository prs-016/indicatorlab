"""Network-denied Dhan tests; all prices, IDs and credentials are synthetic."""

import json
import logging
import socket
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.live.dhan import QUOTE_URL, DhanQuoteProvider, DhanRateLimitError
from src.live.india import COLUMNS, IndiaLiveService, RetryPolicy, SessionCalendar

FIXTURE = Path(__file__).parent / "fixtures/live_india/dhan_bulk.synthetic.json"
SYMBOLS = ("RELIANCE.NS", "TCS.NS", "INFY.NS")
INSTRUMENTS = {
    s: {"security_id": str(1001 + i), "exchange_segment": "NSE_EQ"}
    for i, s in enumerate(SYMBOLS)
}
ENV = {"DHAN_CLIENT_ID": "synthetic-client", "DHAN_ACCESS_TOKEN": "synthetic-token"}
NOW = datetime(2024, 1, 2, 3, 45, 5, tzinfo=UTC)
SECRET_MARKER = "PRIVATE_TOKEN_/private/home/user?password=SECRET"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def deny(*args, **kwargs):
        pytest.fail("Network forbidden")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket, "getaddrinfo", deny)


class Session:
    def __init__(self, payload=None, status=200, headers=None):
        self.payload = json.loads(FIXTURE.read_text()) if payload is None else payload
        self.status = status
        self.headers = headers or {}
        self.calls = []
        self.error = None

    def post(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.error:
            raise self.error
        return SimpleNamespace(
            status_code=self.status, headers=self.headers, json=lambda: self.payload
        )


def provider(session=None, **kwargs):
    return DhanQuoteProvider.from_env(
        INSTRUMENTS,
        environ=ENV,
        session=session or Session(),
        clock=lambda: NOW,
        **kwargs,
    )


def test_bulk_schema_and_units():
    session = Session()
    quotes = provider(session).fetch(SYMBOLS)
    assert len(session.calls) == 1
    args, kw = session.calls[0]
    assert args == (QUOTE_URL,)
    assert kw["json"] == {"NSE_EQ": [1001, 1002, 1003]}
    assert kw["allow_redirects"] is False and kw["timeout"] == 5
    assert kw["headers"]["access-token"] == ENV["DHAN_ACCESS_TOKEN"]
    assert session.trust_env is False
    for symbol, row in quotes.items():
        assert tuple(row) == COLUMNS
        assert row["symbol"] == symbol and row["source"] == "dhan"
        assert row["ts_received"] == NOW.isoformat()
    assert quotes[SYMBOLS[0]]["change_pct"] == pytest.approx(100 * 25 / 2475)
    assert quotes[SYMBOLS[1]]["change_pct"] == pytest.approx(-100 * 35 / 3535)
    assert quotes[SYMBOLS[2]]["volume"] == 0
    assert quotes[SYMBOLS[0]]["ts_exchange"] == "2024-01-02T03:45:00+00:00"


def test_hundred_in_one_request():
    mapping = {
        f"SYN{i}.NS": {"security_id": i + 1, "exchange_segment": "NSE_EQ"}
        for i in range(100)
    }
    raw = json.loads(FIXTURE.read_text())["data"]["NSE_EQ"]["1001"]
    session = Session(
        {"status": "success", "data": {"NSE_EQ": {str(i + 1): raw for i in range(100)}}}
    )
    p = DhanQuoteProvider(mapping, environ=ENV, session=session, clock=lambda: NOW)
    assert len(p.fetch(tuple(mapping))) == 100
    assert len(session.calls) == 1
    with pytest.raises(ValueError):
        p.fetch(tuple(mapping) + ("EXTRA.NS",))


@pytest.mark.parametrize(
    "field,value",
    [
        ("last_price", None),
        ("last_price", 0),
        ("last_price", True),
        ("last_price", "nan"),
        ("volume", None),
        ("volume", -1),
        ("volume", 1.5),
        ("volume", True),
        ("volume", 2**63),
        ("net_change", "inf"),
        ("net_change", True),
        ("net_change", 2500),
        ("last_trade_time", None),
        ("last_trade_time", "01/01/1980 00:00:00"),
        ("last_trade_time", "02/01/2024 09:16:00"),
        ("last_trade_time", "09:15:00"),
        ("last_trade_time", "SECRET"),
    ],
)
def test_invalid_data_isolated(field, value):
    s = Session()
    s.payload["data"]["NSE_EQ"]["1001"][field] = value
    result = provider(s).fetch(SYMBOLS)
    assert isinstance(result[SYMBOLS[0]], ValueError)
    assert isinstance(result[SYMBOLS[1]], dict)


@pytest.mark.parametrize(
    "field", ["last_price", "volume", "net_change", "last_trade_time"]
)
def test_missing_required_field(field):
    s = Session()
    del s.payload["data"]["NSE_EQ"]["1001"][field]
    assert isinstance(provider(s).fetch(SYMBOLS)[SYMBOLS[0]], ValueError)


def test_partial_response():
    s = Session()
    del s.payload["data"]["NSE_EQ"]["1002"]
    rows = provider(s).fetch(SYMBOLS)
    assert isinstance(rows[SYMBOLS[1]], ValueError)
    assert isinstance(rows[SYMBOLS[0]], dict)


@pytest.mark.parametrize(
    "status,code",
    [
        (401, ""),
        (403, ""),
        (200, "806"),
        (200, "807"),
        (200, "808"),
        (200, "809"),
        (200, "810"),
        (200, "DH-901"),
        (200, "DH-902"),
    ],
)
def test_denial_stops_retries(status, code):
    s = Session(
        {"status": "failure", "errorCode": code, "errorMessage": SECRET_MARKER}, status
    )
    p = provider(s)
    for _ in range(2):
        with pytest.raises(PermissionError) as error:
            p.fetch(SYMBOLS)
        assert SECRET_MARKER not in str(error.value)
    assert len(s.calls) == 1


@pytest.mark.parametrize("status,code", [(429, ""), (200, "805"), (200, "DH-904")])
def test_rate_limit_cooldown(status, code):
    now = [0.0]
    s = Session({"status": "failure", "errorCode": code}, status, {"Retry-After": "10"})
    p = provider(s, monotonic=lambda: now[0])
    with pytest.raises(DhanRateLimitError):
        p.fetch(SYMBOLS)
    now[0] = 9.9
    with pytest.raises(DhanRateLimitError):
        p.fetch(SYMBOLS)
    assert len(s.calls) == 1
    now[0] = 10
    s.status, s.payload = 200, json.loads(FIXTURE.read_text())
    assert isinstance(p.fetch(SYMBOLS)[SYMBOLS[0]], dict)


def test_spacing_success_and_transport_errors():
    now = [0.0]
    s = Session()
    p = provider(s, monotonic=lambda: now[0])
    p.fetch(SYMBOLS)
    with pytest.raises(DhanRateLimitError):
        p.fetch(SYMBOLS)
    now[0] = 1
    s.error = RuntimeError(SECRET_MARKER)
    with pytest.raises(OSError) as error:
        p.fetch(SYMBOLS)
    assert SECRET_MARKER not in str(error.value)
    with pytest.raises(DhanRateLimitError):
        p.fetch(SYMBOLS)
    assert len(s.calls) == 2


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"status": "success", "data": []},
        {"status": "success", "data": {"BSE_EQ": {}}},
        {"status": "success", "data": {"NSE_EQ": {"999": {}}}},
        {"status": "failure", "errorMessage": SECRET_MARKER},
    ],
)
def test_malformed_envelopes(payload):
    with pytest.raises(ValueError) as error:
        provider(Session(payload)).fetch(SYMBOLS)
    assert SECRET_MARKER not in str(error.value)


@pytest.mark.parametrize(
    "status,error_type", [(302, ValueError), (400, ValueError), (500, OSError)]
)
def test_http_errors(status, error_type):
    with pytest.raises(error_type):
        provider(Session(status=status)).fetch(SYMBOLS)


@pytest.mark.parametrize(
    "mapping",
    [
        {},
        {"RELIANCE": {"security_id": "1", "exchange_segment": "NSE_EQ"}},
        {"RELIANCE.NS": {"security_id": "01", "exchange_segment": "NSE_EQ"}},
        {"RELIANCE.NS": {"security_id": True, "exchange_segment": "NSE_EQ"}},
        {"RELIANCE.NS": {"security_id": "1", "exchange_segment": "BSE_EQ"}},
        {
            "RELIANCE.NS": {"security_id": "1", "exchange_segment": "NSE_EQ"},
            "TCS.NS": {"security_id": "1", "exchange_segment": "NSE_EQ"},
        },
    ],
)
def test_bad_mapping(mapping):
    with pytest.raises(ValueError):
        DhanQuoteProvider(mapping, environ=ENV, session=Session())


def test_no_credentials_no_network(monkeypatch):
    monkeypatch.delenv("DHAN_CLIENT_ID", raising=False)
    monkeypatch.delenv("DHAN_ACCESS_TOKEN", raising=False)
    with pytest.raises(PermissionError):
        DhanQuoteProvider.from_env(INSTRUMENTS)


def test_unconfigured_and_duplicate_symbols():
    p = provider()
    for symbols in [("UNKNOWN.NS",), (SYMBOLS[0], SYMBOLS[0])]:
        with pytest.raises(ValueError):
            p.fetch(symbols)


def test_service_integration_and_permission_logging(caplog):
    s = Session()
    p = provider(s)
    store = SimpleNamespace(write=lambda *args: None)
    service = IndiaLiveService(
        SYMBOLS,
        p,
        SessionCalendar({"2024-01-02": [["09:15", "15:30"]]}, source="synthetic"),
        store,
        store,
        clock=lambda: NOW,
        retry=RetryPolicy(attempts=1),
    )
    with caplog.at_level(logging.INFO):
        result = service.step()
    assert len(result) == 3 and all(tuple(row) == COLUMNS for row in result)
    # A new provider simulates an expired token, with hostile broker details.
    s = Session({"errorMessage": SECRET_MARKER}, 401)
    service.provider = provider(s)
    assert service.step() == []
    assert service.step() == []
    assert len(s.calls) == 1
    assert SECRET_MARKER not in caplog.text


def test_retry_after_http_date():
    s = Session(status=429, headers={"Retry-After": "Tue, 02 Jan 2024 03:46:05 GMT"})
    p = provider(s, monotonic=lambda: 0)
    with pytest.raises(DhanRateLimitError):
        p.fetch(SYMBOLS)
    assert p._next_request == 60


def test_old_trade_is_preserved():
    s = Session()
    s.payload["data"]["NSE_EQ"]["1001"]["last_trade_time"] = "01/01/2024 15:30:00"
    assert (
        provider(s).fetch(SYMBOLS)[SYMBOLS[0]]["ts_exchange"]
        == "2024-01-01T10:00:00+00:00"
    )


def test_invalid_json_sanitized():
    class InvalidJsonSession(Session):
        def post(self, *args, **kwargs):
            def invalid():
                raise ValueError(SECRET_MARKER)

            return SimpleNamespace(status_code=200, json=invalid)

    with pytest.raises(ValueError) as error:
        provider(InvalidJsonSession()).fetch(SYMBOLS)
    assert SECRET_MARKER not in str(error.value)


@pytest.mark.parametrize("raw", ["", "invalid", "nan", "-5"])
def test_bad_retry_after_keeps_minimum(raw):
    p = provider(Session(status=429, headers={"Retry-After": raw}), monotonic=lambda: 0)
    with pytest.raises(DhanRateLimitError):
        p.fetch(SYMBOLS)
    assert p._next_request >= 1


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan"), True])
def test_invalid_timeout(timeout):
    with pytest.raises(ValueError):
        provider(timeout_seconds=timeout)


def test_unknown_missing_exchange_returns_explicit_errors():
    quotes = provider(Session({"status": "success", "data": {}})).fetch(SYMBOLS)
    assert all(isinstance(row, ValueError) for row in quotes.values())


def test_credentials_absent_from_repr_and_transport_traceback():
    import traceback

    s = Session()
    s.error = RuntimeError(SECRET_MARKER)
    p = provider(s)
    assert ENV["DHAN_ACCESS_TOKEN"] not in repr(p)
    try:
        p.fetch(SYMBOLS)
    except OSError:
        assert SECRET_MARKER not in traceback.format_exc()
