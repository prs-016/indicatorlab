"""Session-aware ingestion alarm and historical weather exceptions, offline."""

from datetime import datetime
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace

import boto3
import pandas as pd
import pytest

from src.hk.calendar import market_state, sessions
from src.hk.cloud.watchdog import health
from src.hk.live import AwsSink


@pytest.mark.parametrize(
    "stamp,state",
    [
        ("2023-09-01T02:00:00+00:00", "closed"),
        ("2023-09-08T06:00:00+00:00", "closed"),
        ("2023-10-09T05:59:00+00:00", "closed"),
        ("2023-10-09T06:00:00+00:00", "open"),
    ],
)
def test_evidenced_weather_exceptions(stamp, state):
    assert market_state(datetime.fromisoformat(stamp)) == state


def test_daily_calendar_excludes_both_2023_full_closures():
    days = sessions("2023-09-01", "2023-09-08")
    assert "2023-09-01" not in days and "2023-09-08" not in days


def test_ingestion_alarm_measures_receipt_not_last_trade():
    now = datetime.fromisoformat("2026-11-12T02:00:00+00:00")
    assert health(now, "open", ["2026-11-12T01:59:30+00:00"])["healthy"]
    assert not health(now, "open", ["2026-11-12T01:58:59+00:00"])["healthy"]
    assert not health(now, "open", [])["healthy"]


def test_alarm_pauses_at_lunch_and_respects_reopening_grace():
    assert health(datetime.fromisoformat("2026-11-12T04:30:00+00:00"), "lunch", [])[
        "healthy"
    ]
    assert health(datetime.fromisoformat("2026-11-12T05:00:30+00:00"), "open", [])[
        "healthy"
    ]
    assert not health(datetime.fromisoformat("2026-11-12T05:01:01+00:00"), "open", [])[
        "healthy"
    ]


def test_aws_sink_contract_and_one_snapshot_per_minute(monkeypatch):
    """Exercise Decimal upserts and real Parquet bytes without any AWS request."""
    items, snapshots, metrics = [], [], []

    class Batch:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def put_item(self, *, Item):
            items.append(Item)

    class Table:
        def batch_writer(self, *, overwrite_by_pkeys):
            assert overwrite_by_pkeys == ["symbol"]
            return Batch()

    def resource(name, *, region_name):
        assert name == "dynamodb" and region_name == "us-west-2"

        def table(name):
            assert name == "test-hk-quotes"
            return Table()

        return SimpleNamespace(Table=table)

    def client(name, *, region_name):
        assert region_name == "us-west-2"
        if name == "s3":
            return SimpleNamespace(put_object=lambda **kw: snapshots.append(kw))
        assert name == "cloudwatch"
        return SimpleNamespace(put_metric_data=lambda **kw: metrics.append(kw))

    monkeypatch.setenv("HK_QUOTE_TABLE", "test-hk-quotes")
    monkeypatch.setenv("HK_DATA_BUCKET", "test-hk-data")
    monkeypatch.setattr(boto3, "resource", resource)
    monkeypatch.setattr(boto3, "client", client)
    sink = AwsSink()
    now = datetime.fromisoformat("2026-11-12T02:00:00+00:00")
    rows = [
        {
            "symbol": f"{i:04d}.HK",
            "price": 123.45,
            "change_pct": -0.5,
            "volume": 12345.0,
            "ts_exchange": now.isoformat(),
            "ts_received": now.isoformat(),
            "source": "tencent",
        }
        for i in range(1, 96)
    ]
    sink.write(rows, now)
    sink.write(rows, now.replace(second=5))
    sink.write(rows, now.replace(minute=1))
    assert len(items) == 285 and isinstance(items[0]["price"], Decimal)
    assert len(metrics) == 3 and len(snapshots) == 2
    assert snapshots[0]["Bucket"] == "test-hk-data"
    assert snapshots[0]["Key"] == "raw/live/hk/date=2026-11-12/1000.parquet"
    frame = pd.read_parquet(BytesIO(snapshots[0]["Body"]))
    assert frame.to_dict("records") == rows
