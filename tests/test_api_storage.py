"""S3 and DynamoDB reads of src/api/storage.py, with boto3 and botocore replaced by fakes (no AWS)."""
import io
import sys
import types
from datetime import datetime
from decimal import Decimal

import pandas as pd
import pytest

from src.api.storage import Storage


class ClientError(Exception):
    pass


class BotoCoreError(Exception):
    pass


class FakeS3:
    def __init__(self, objects):
        self.objects = objects     # full key -> bytes

    def get_paginator(self, name):
        objects = self.objects

        class Pages:
            def paginate(self, Bucket, Prefix, Delimiter=None):
                keys = [k for k in objects if k.startswith(Prefix)
                        and not (Delimiter and Delimiter in k[len(Prefix):])]   # S3 leaves subfolders out
                return [{"Contents": [{"Key": k} for k in keys[:1]]}, {"Contents": [{"Key": k} for k in keys[1:]]}]
        return Pages()

    def get_object(self, Bucket, Key):
        if Key not in self.objects:
            raise ClientError("NoSuchKey")
        return {"Body": io.BytesIO(self.objects[Key])}

    def head_object(self, Bucket, Key):
        if Key not in self.objects:
            raise ClientError("404")
        return {"LastModified": datetime(2026, 11, 10)}


class FakeTable:
    def __init__(self, pages, error=None):
        self.pages, self.error = pages, error

    def scan(self, **kw):
        if self.error:
            raise self.error
        i = kw.get("ExclusiveStartKey", 0)
        page = {"Items": self.pages[i]}
        if i + 1 < len(self.pages):
            page["LastEvaluatedKey"] = i + 1
        return page


@pytest.fixture
def aws(monkeypatch):
    """Install fake boto3/botocore modules; returns the dict the fakes read from."""
    state = {"objects": {}, "tables": {}, "s3_calls": 0}

    def client(name, region_name=None):
        state["s3_calls"] += 1
        return FakeS3(state["objects"])

    def resource(name, region_name=None):
        return types.SimpleNamespace(Table=lambda n: state["tables"].get(n, FakeTable([], ClientError("ResourceNotFound"))))

    monkeypatch.setitem(sys.modules, "boto3", types.SimpleNamespace(client=client, resource=resource))
    monkeypatch.setitem(sys.modules, "botocore", types.ModuleType("botocore"))
    monkeypatch.setitem(sys.modules, "botocore.exceptions",
                        types.SimpleNamespace(ClientError=ClientError, BotoCoreError=BotoCoreError))
    return state


def _parquet(df):
    buf = io.BytesIO()
    df.to_parquet(buf, index=False)
    return buf.getvalue()


def test_s3_keys_tables_and_freshness_under_a_prefix(aws):
    aws["objects"]["v1/processed/wiki_weekly.parquet"] = _parquet(pd.DataFrame({"ticker": ["AAPL"]}))
    aws["objects"]["v1/processed/wiki_current.parquet"] = _parquet(pd.DataFrame({"ticker": ["MSFT"]}))
    aws["objects"]["v1/processed/reddit_hourly/date=2026-11-19/0100.parquet"] = b"x"   # a folder, not a table
    s = Storage("s3://indicatorlab-data/v1/", ttl=600)
    assert s.keys("processed/") == ["processed/wiki_current.parquet", "processed/wiki_weekly.parquet"]
    assert s.table("processed/wiki_weekly.parquet")["ticker"].tolist() == ["AAPL"]
    assert s.table("processed/missing.parquet").empty                     # missing object: empty table
    assert s.modified("processed/wiki_weekly.parquet") == datetime(2026, 11, 10)
    assert s.modified("processed/missing.parquet") is None


def test_s3_tables_are_cached_for_the_ttl(aws):
    aws["objects"]["processed/wiki_weekly.parquet"] = _parquet(pd.DataFrame({"ticker": ["AAPL"]}))
    s = Storage("s3://indicatorlab-data", ttl=600)
    s.table("processed/wiki_weekly.parquet")
    calls = aws["s3_calls"]
    s.table("processed/wiki_weekly.parquet")
    assert aws["s3_calls"] == calls
    Storage("s3://indicatorlab-data", ttl=0).table("processed/wiki_weekly.parquet")
    assert aws["s3_calls"] == calls + 1


def test_live_reads_every_dynamodb_page_and_converts_decimals(aws):
    aws["tables"]["indicatorlab-live-india"] = FakeTable([
        [{"symbol": "TCS.NS", "price": Decimal("4100.5"), "volume": Decimal(12)}],
        [{"symbol": "INFY.NS", "price": Decimal(1500), "source": "yahoo"}]])
    quotes = Storage("s3://indicatorlab-data").live("india")
    assert [q["symbol"] for q in quotes] == ["TCS.NS", "INFY.NS"]
    assert quotes[0]["price"] == 4100.5 and isinstance(quotes[0]["volume"], float)


def test_live_without_a_table_has_no_quotes_instead_of_an_error(aws):
    s = Storage("s3://indicatorlab-data")
    assert s.live("hk") == []                                              # table not created yet
    aws["tables"]["indicatorlab-live-hk"] = FakeTable([], BotoCoreError("no credentials"))
    assert s.live("hk") == []
    assert s.live("us") == []                                              # no live table configured
