"""The daily AWS job (src/wiki_daily.py) on fake Wikimedia answers: no network, no AWS."""
import pandas as pd
import pytest

from src import wiki_daily
from src.wiki_edits import REV_COLS

DAY = pd.Timestamp("2026-11-18")


def fake_views(title, start, end, lang="en"):
    """100 views a day, except the job's own day, which Wikimedia has not published yet (zeros)."""
    days = pd.date_range(start, end, freq="D")
    return pd.Series([0 if d == DAY else 100 for d in days], index=days, dtype="int64")


def fake_revisions(title, start, end, lang="en"):
    if title == "Missing_page":
        raise ValueError("no Wikipedia page 'Missing_page'")
    rows = [{"revid": 1, "timestamp": start - pd.Timedelta(days=3), "user": "a", "size": 900,
             "comment": "old", "before_start": True},
            {"revid": 2, "timestamp": start + pd.Timedelta(hours=9), "user": "b", "size": 950,
             "comment": "Q3 earnings", "before_start": False}]
    return pd.DataFrame(rows, columns=[*REV_COLS, "before_start"])


@pytest.fixture
def fake_wikimedia(monkeypatch):
    monkeypatch.setattr(wiki_daily, "pageviews", fake_views)
    monkeypatch.setattr(wiki_daily, "revisions", fake_revisions)
    maps = {"US": {"AAPL": [("en", "Apple_Inc.")], "ZZZZ": [("en", "Missing_page")]},
            "IN": {}, "HK": {"0700.HK": [("en", "Tencent"), ("zh", "腾讯")]}}
    monkeypatch.setattr(wiki_daily, "map_titles", lambda m: maps[m])


def test_history_covers_the_baseline_and_the_rz_history():
    assert wiki_daily.history_days() == (8 + 26 + 2) * 7


def test_title_map_keeps_each_articles_newest_title(tmp_path, monkeypatch):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "hk_wiki_titles.csv").write_text(
        "symbol,title,lang,valid_from\n"
        "2331.HK,李宁公司,zh,2017-10-14T09:37:31Z\n"
        "2331.HK,Li-Ning,en,2007-07-27T15:09:40Z\n"
        "2331.HK,李宁有限公司,zh,2018-01-24T02:05:27Z\n"
        '2338.HK,"Weichai_Power_Co.,_Ltd.",en,2015-07-09T01:38:36Z\n')
    monkeypatch.setattr(wiki_daily, "ROOT", tmp_path)
    assert wiki_daily.map_titles("HK") == {"2331.HK": [("en", "Li-Ning"), ("zh", "李宁有限公司")],
                                           "2338.HK": [("en", "Weichai_Power_Co.,_Ltd.")]}
    assert wiki_daily.map_titles("IN") == {}          # India's map is not in the repo yet


def test_run_writes_raw_and_current_and_skips_a_bad_stock(tmp_path, fake_wikimedia):
    out = wiki_daily.run(DAY, str(tmp_path))
    assert out == {"day": "2026-11-18", "published_to": "2026-11-17", "rows": 2, "failed": ["ZZZZ"]}
    cur = pd.read_parquet(tmp_path / "processed" / "wiki_current.parquet")
    assert set(zip(cur["ticker"], cur["market"])) == {("AAPL", "us"), ("0700.HK", "hk")}
    # the unpublished day is left out, so the trailing week is 7 full days, not 6 plus a zero
    assert cur.set_index("ticker").loc["AAPL", "value"] == 700
    assert cur.set_index("ticker").loc["0700.HK", "value"] == 1400    # both languages summed
    assert (cur["as_of"] == pd.Timestamp("2026-11-17")).all() and (cur["ratio"] == 1).all()
    raw = tmp_path / "raw" / "wikipedia" / "date=2026-11-18"
    views = pd.read_parquet(raw / "views.parquet")
    assert len(views) == 3 and set(views["lang"]) == {"en", "zh"} and not views["complete"].any()
    revs = pd.read_parquet(raw / "revisions.parquet")
    assert list(revs["revid"]) == [2, 2, 2]                  # the day's edit only, once per article
    assert "user" not in revs and "before_start" not in revs


def test_run_with_nothing_pulled_raises(tmp_path, monkeypatch, fake_wikimedia):
    monkeypatch.setattr(wiki_daily, "map_titles", lambda m: {"ZZZZ": [("en", "Missing_page")]} if m == "US" else {})
    with pytest.raises(RuntimeError, match="no stock"):
        wiki_daily.run(DAY, str(tmp_path))
    assert not (tmp_path / "processed").exists()


def test_lambda_handler_runs_the_named_day_and_skips_the_metric_locally(tmp_path, monkeypatch, fake_wikimedia):
    monkeypatch.setenv("INDICATORLAB_DATA", str(tmp_path))
    monkeypatch.setattr(wiki_daily, "publish_metric", lambda rows: pytest.fail("no metric off AWS"))
    assert wiki_daily.lambda_handler({"day": "2026-11-18"}, None)["rows"] == 2
    seen = []
    monkeypatch.setenv("INDICATORLAB_DATA", "s3://bucket")
    monkeypatch.setattr(wiki_daily, "run", lambda day, root: {"rows": 5, "root": root})
    monkeypatch.setattr(wiki_daily, "publish_metric", seen.append)
    assert wiki_daily.lambda_handler(None, None)["root"] == "s3://bucket" and seen == [5]


def test_a_half_published_day_is_left_out_but_a_quiet_one_is_kept():
    days = pd.date_range("2026-11-01", "2026-11-18", freq="D")
    steady = pd.Series(1000.0, index=days)
    partial = steady.copy()
    partial.iloc[-1] = 300                                     # Wikimedia still filling in the day
    assert wiki_daily.published_end({"A": partial, "B": steady * 0}) == pd.Timestamp("2026-11-17")
    quiet = steady.copy()
    quiet.iloc[-1] = 700                                       # a slow day, still most of the usual traffic
    assert wiki_daily.published_end({"A": quiet}) == pd.Timestamp("2026-11-18")


def test_a_stock_still_waiting_for_its_newest_day_ends_a_day_earlier():
    days = pd.date_range("2026-11-10", "2026-11-19", freq="D")
    waiting = pd.Series([100] * 9 + [0], index=days)
    assert wiki_daily.own_end(waiting).index.max() == pd.Timestamp("2026-11-18")
    assert wiki_daily.own_end(pd.Series(100, index=days)).index.max() == pd.Timestamp("2026-11-19")
    assert len(wiki_daily.own_end(pd.Series(0, index=days))) == len(days)    # never read: zeros kept
