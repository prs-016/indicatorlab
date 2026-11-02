from datetime import date

import numpy as np
import pandas as pd

from src import trends_compare, wiki_attention
from src.trends_compare import cached_series, gdelt_daily, tracking_correlation
from src.wiki_attention import redirects
from src.wiki_pipeline import (
    SHARED_COLS,
    attention_rows,
    last_complete_sunday,
    split_period,
    universe,
    windows,
)


def test_windows_split_at_the_holdout():
    w = windows(pd.Timestamp("2026-10-25"))
    assert w["research"] == (pd.Timestamp("2015-07-01"), pd.Timestamp("2025-09-30"))
    assert w["recent"] == (pd.Timestamp("2025-10-01"), pd.Timestamp("2026-10-25"))


def test_last_complete_sunday():
    assert last_complete_sunday(date(2026, 10, 30)) == pd.Timestamp("2026-10-25")   # Friday
    assert last_complete_sunday(date(2026, 10, 26)) == pd.Timestamp("2026-10-25")   # Monday
    assert last_complete_sunday(date(2026, 10, 25)) == pd.Timestamp("2026-10-18")   # Sunday itself is not over


def test_universe_has_tracked_stocks_and_strategy_extras():
    tracked = universe("US", strategy=False)
    assert len(tracked) == 10 and tracked["AAPL"] == {"en": "Apple_Inc."}
    assert len(universe("US")) >= 30 and universe("US")["HD"] == {"en": "Home_Depot"}


def test_attention_rows_are_in_the_shared_format():
    weeks = pd.date_range("2024-01-01", periods=40, freq="7D")
    views = pd.Series(1000.0, index=weeks)
    edits = pd.Series(3.0, index=weeks)
    rows = attention_rows(views, edits, "AAPL", "US")
    assert list(rows.columns[: len(SHARED_COLS)]) == SHARED_COLS
    assert set(rows["source"]) == {"wikipedia_views", "wikipedia_edits"} and (rows["market"] == "US").all()
    assert rows.loc[rows["source"] == "wikipedia_views", "edits"].isna().all()
    assert rows.loc[rows["source"] == "wikipedia_edits", "edits"].eq(3).all()


def test_split_period_puts_the_straddling_week_in_recent():
    df = pd.DataFrame({"week": pd.to_datetime(["2025-09-22", "2025-09-29", "2025-10-06"])})
    parts = split_period(df)
    assert parts["research"]["week"].tolist() == [pd.Timestamp("2025-09-22")]
    assert len(parts["recent"]) == 2


def test_tracking_correlation_of_a_scaled_copy_is_one():
    days = pd.date_range("2024-01-01", periods=7 * 30)
    v = pd.Series(np.random.default_rng(0).integers(100, 200, len(days)), index=days, dtype=float)
    weekly = v.groupby(wiki_attention.week_start(v.index)).sum() * 3
    r = tracking_correlation(weekly, v)
    assert r["weeks"] == 30 and np.isclose(r["corr_level"], 1) and np.isclose(r["corr_change"], 1)


def test_cached_series_pulls_once(tmp_path):
    calls = []

    def pull():
        calls.append(1)
        return pd.Series([1.0, 2.0], index=pd.date_range("2024-01-01", periods=2))

    f = tmp_path / "x.csv"
    assert cached_series(f, pull).tolist() == [1.0, 2.0]
    assert cached_series(f, pull).tolist() == [1.0, 2.0] and len(calls) == 1


class _Resp:
    def __init__(self, status, text, payload=None):
        self.status_code, self.text, self._payload = status, text, payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


def test_gdelt_backs_off_then_fills_missing_days(monkeypatch):
    monkeypatch.setenv("WIKIMEDIA_CONTACT", "test@example.org")
    monkeypatch.setattr(trends_compare.time, "sleep", lambda s: None)
    payload = {"timeline": [{"data": [{"date": "20240102T000000Z", "value": 7}]}]}
    answers = iter([_Resp(429, "Please limit requests"), _Resp(200, '{"timeline": []}', payload)])
    monkeypatch.setattr(trends_compare.requests, "get", lambda *a, **k: next(answers))
    s = gdelt_daily("x", pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-03"))
    assert s.tolist() == [0.0, 7.0, 0.0]


def test_redirects_follow_continue(monkeypatch):
    monkeypatch.setenv("WIKIMEDIA_CONTACT", "test@example.org")
    pages = iter([
        {"continue": {"rdcontinue": "2"}, "query": {"pages": [{"title": "A", "redirects": [{"title": "Old A"}]}]}},
        {"query": {"pages": [{"title": "A", "redirects": [{"title": "A Inc"}]}]}},
    ])
    monkeypatch.setattr(wiki_attention.SESSION, "get", lambda *a, **k: _Resp(200, "", next(pages)))
    assert redirects("A") == ["Old_A", "A_Inc"]


def test_load_views_splits_periods_and_refreshes_a_stale_recent_file(tmp_path, monkeypatch):
    from src import wiki_pipeline
    pulls = []

    def fake_views(title, start, end, lang):
        pulls.append(end)
        days = pd.date_range(start, end)
        return pd.Series(1, index=days)

    monkeypatch.setattr(wiki_pipeline, "article_views", fake_views)
    win = {"research": (pd.Timestamp("2025-09-01"), pd.Timestamp("2025-09-30")),
           "recent": (pd.Timestamp("2025-10-01"), pd.Timestamp("2025-10-12"))}
    v = wiki_pipeline.load_views("X", {"en": "X"}, win, raw=tmp_path)
    assert len(v) == 42 and v.index.is_monotonic_increasing
    research = pd.read_csv(tmp_path / "views_research" / "X.csv", index_col=0, parse_dates=True)
    assert research.index.max() == pd.Timestamp("2025-09-30")
    wiki_pipeline.load_views("X", {"en": "X"}, win, raw=tmp_path)                 # cached: no new pull
    later = {**win, "recent": (win["recent"][0], pd.Timestamp("2025-10-19"))}
    assert wiki_pipeline.load_views("X", {"en": "X"}, later, raw=tmp_path).index.max() == pd.Timestamp("2025-10-19")
    assert pulls == [pd.Timestamp("2025-10-12"), pd.Timestamp("2025-10-19")]


def test_load_edits_keeps_one_copy_of_the_boundary_revision(tmp_path):
    from src.wiki_pipeline import load_edits
    cols = "revid,timestamp,user,size,comment,before_start\n"
    research = cols + "1,2025-08-31 10:00:00,a,100,,True\n2,2025-09-10 10:00:00,b,150,earnings,False\n"
    recent = cols + "2,2025-09-10 10:00:00,b,150,earnings,True\n3,2025-10-02 10:00:00,c,120,rv,False\n"
    for p, text in (("research", research), ("recent", recent)):
        d = tmp_path / f"revisions_{p}" / "en"
        d.mkdir(parents=True)
        (d / "X.csv").write_text(text)
        (tmp_path / f"views_{p}").mkdir()
    (tmp_path / "views_recent" / "X.csv").write_text("date,X\n2025-10-12,1\n")
    win = {"research": (pd.Timestamp("2025-09-01"), pd.Timestamp("2025-09-30")),
           "recent": (pd.Timestamp("2025-10-01"), pd.Timestamp("2025-10-12"))}
    e = load_edits("X", {"en": "X"}, win, raw=tmp_path)
    assert e["revid"].tolist() == [2, 3] and e["delta"].tolist() == [50, -30]
    assert e["revert"].tolist() == [False, True] and e["tag_earnings"].tolist() == [True, False]
