"""Offline local archive -> posts -> matching checks for configured markets."""

import gzip
import hashlib
import json
import socket
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import pytest

from src import config
from src.reddit import build_posts as builder
from src.reddit import match_tickers as matcher
from src.reddit import settings


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Market propagation test attempted network access")

    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket, "getaddrinfo", denied)


@pytest.fixture
def archives(tmp_path, monkeypatch):
    # HK has no active company/subreddit config yet: this explicitly synthetic
    # product community tests generic propagation without changing Jack's config.
    original_map = config.subreddit_map
    hk = {"hk_fixture": {"market": "HK", "type": "product", "ticker": "0700.HK"}}
    monkeypatch.setattr(
        config,
        "subreddit_map",
        lambda market: hk if market == "HK" else original_map(market),
    )
    monkeypatch.setattr(settings, "ROOT", tmp_path)
    monkeypatch.setattr(settings, "PROCESSED", tmp_path / "processed")
    monkeypatch.setattr(settings, "POSTS", tmp_path / "processed/posts")
    monkeypatch.setattr(settings, "TABLES", tmp_path / "tables")
    settings.TABLES.mkdir()
    monkeypatch.setattr(builder, "ProcessPoolExecutor", ThreadPoolExecutor)
    manifest = {}
    for sub, title in [
        ("IndiaInvestments", "NSE:TCS and Tata Consultancy Services"),
        ("stocks", "AAPL Apple earnings"),
        ("hk_fixture", "synthetic HK product discussion"),
    ]:
        path = tmp_path / f"{sub}.json.gz"
        post = {
            "id": sub + "-post",
            "subreddit": sub,
            "created_utc": 1704153600,
            "title": title,
            "selftext": "",
            "score": 1,
            "num_comments": 0,
        }
        payload = {
            "date": "2024-01-02",
            "pages": [
                {
                    "retrieved_at_utc": "2024-01-03T00:00:00Z",
                    "response": {"data": [post]},
                }
            ],
        }
        with gzip.open(path, "wt") as stream:
            json.dump(payload, stream)
        manifest[(sub, "2024-01-02")] = {
            "status": "complete",
            "n_posts": 1,
            "file": path.name,
            "last_retrieved_utc": "2024-01-03T00:00:00Z",
        }
    monkeypatch.setattr(builder, "load_manifest_latest", lambda: manifest)
    return manifest


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_india_archive_through_existing_matcher_output_preserves_other_markets(
    archives,
):
    builder.build(workers=1)  # existing default remains US
    us_path = settings.POSTS / "stocks.parquet"
    us_hash = digest(us_path)
    assert list(settings.POSTS.glob("*.parquet")) == [us_path]
    builder.build(workers=1, market="HK")
    hk_path = settings.POSTS / "hk_fixture.parquet"
    hk_hash = digest(hk_path)
    status = builder.build(workers=1, market="IN")
    assert digest(us_path) == us_hash and digest(hk_path) == hk_hash
    india = pd.read_parquet(settings.POSTS / "indiainvestments.parquet")
    assert india["market"].tolist() == ["IN"]
    assert india["subreddit_type"].tolist() == ["general"]
    assert india["owner_ticker"].isna().all()
    assert india["period"].tolist() == ["research"]
    assert india["day_status"].tolist() == ["complete"]
    assert len(status) == 3  # shared coverage retains US/HK entries
    output = matcher.run()
    assert set(zip(output["market"], output["ticker"])) == {
        ("US", "AAPL"),
        ("IN", "TCS.NS"),
        ("HK", "0700.HK"),
    }
    saved = pd.read_parquet(settings.PROCESSED / "post_ticker_matches.parquet")
    pd.testing.assert_frame_equal(
        output.reset_index(drop=True), saved.reset_index(drop=True)
    )
    assert not saved.duplicated(["post_id", "ticker"]).any()


def test_wrong_market_cache_is_rebuilt_and_correct_cache_is_reused(
    archives, monkeypatch
):
    builder.build(workers=1, market="IN")
    path = settings.POSTS / "indiainvestments.parquet"
    stale = pd.read_parquet(path).assign(market="US")
    stale.to_parquet(path, index=False)
    builder.build(workers=1, market="IN")
    assert pd.read_parquet(path)["market"].tolist() == ["IN"]
    previous = digest(path)

    def unexpected_read(path):
        pytest.fail("Correct fresh cache should not reread raw archive")

    monkeypatch.setattr(builder, "_read_day", unexpected_read)
    builder.build(workers=1, market="IN")
    assert digest(path) == previous


def test_unknown_market_fails_before_reading_archives(monkeypatch):
    def unexpected_read():
        pytest.fail("Invalid market must fail before reading archives")

    monkeypatch.setattr(builder, "load_manifest_latest", unexpected_read)
    with pytest.raises(KeyError):
        builder.build(market="UNKNOWN")


@pytest.mark.parametrize("market", ["US", "IN", "HK"])
def test_cli_routes_configured_market_without_running_acquisition(monkeypatch, market):
    calls = []
    monkeypatch.setattr(
        builder, "build", lambda *args, **kwargs: calls.append((args, kwargs))
    )
    builder.main(["--market", market, "--workers", "1", "--force"])
    assert calls == [((1, True), {"market": market})]


def test_cli_default_and_invalid_market(monkeypatch):
    calls = []
    monkeypatch.setattr(
        builder, "build", lambda *args, **kwargs: calls.append((args, kwargs))
    )
    builder.main([])
    assert calls == [((4, False), {"market": "US"})]
    with pytest.raises(SystemExit):
        builder.main(["--market", "UNKNOWN"])
    assert len(calls) == 1


def test_empty_manifest_produces_empty_coverage_without_error(archives, monkeypatch):
    monkeypatch.setattr(builder, "load_manifest_latest", dict)
    status = builder.build(workers=1, market="IN")
    assert status.empty
    assert pd.read_csv(settings.PROCESSED / "day_status.csv").empty
