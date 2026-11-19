"""S&P 500 expansion: list parsing, title resolution, holdout split and the per-stock weekly table (offline)."""
import pandas as pd

from src import wiki_sp500 as sp

WIKITEXT = """intro
{| class="wikitable sortable" id="constituents"
|-
! Symbol !! Security !! Sector !! Sub-Industry !! HQ !! Date added !! CIK !! Founded
|-
|{{NyseSymbol|MMM}}
|[[3M]]|| Industrials || Industrial Conglomerates || [[Saint Paul, Minnesota]] || 1957-03-04 || 0000066740 || 1902
|-
|{{NyseSymbol|BRK.B}} <!-- DO NOT CHANGE THIS TICKER -->
|[[Berkshire Hathaway]]|| Financials || Multi-Sector Holdings || [[Omaha, Nebraska]] || 2010-02-16 || 0001067983 || 1839
|-
|{{NasdaqSymbol|GOOGL}}
|[[Alphabet Inc.]] (Class A)|| Communication Services || Interactive Media || [[Mountain View, California]] || 2006-04-03 || 0001652044 || 1998
|-
|{{NasdaqSymbol|GOOG}}
|[[Alphabet Inc.]] (Class C)|| Communication Services || Interactive Media || [[Mountain View, California]] || 2014-04-03 || 0001652044 || 1998
|-
|{{NasdaqSymbol|AMD}}
|[[AMD|Advanced Micro Devices]]|| Information Technology || Semiconductors || [[Santa Clara, California]] || 2017-03-20 || 0000002488 || 1969
|}
{| class="wikitable" id="changes"
|-
|{{NyseSymbol|OLD}}
|[[Old Co]]|| Removed || x || y || 2020-01-01 || 1 || 1
|}
"""


def test_parse_reads_every_constituent_row_and_ignores_the_changes_table():
    df = sp.parse_constituents(WIKITEXT)

    assert df["ticker"].tolist() == ["MMM", "BRK.B", "GOOGL", "GOOG", "AMD"]
    assert df.set_index("ticker").loc["BRK.B", "yahoo"] == "BRK-B"
    assert df.set_index("ticker").loc["AMD", "title"] == "AMD"           # the link target, not its label
    assert df.set_index("ticker").loc["GOOG", "title"] == "Alphabet_Inc."
    assert df.set_index("ticker").loc["MMM", "date_added"] == "1957-03-04"


def test_resolve_follows_redirects_and_marks_shared_and_missing_articles(monkeypatch):
    info = {"3M": {"exists": True, "redirect_to": None, "disambiguation": False},
            "Berkshire Hathaway": {"exists": False, "redirect_to": None, "disambiguation": False},
            "Alphabet Inc.": {"exists": True, "redirect_to": None, "disambiguation": False},
            "AMD": {"exists": True, "redirect_to": "Advanced Micro Devices", "disambiguation": False}}
    monkeypatch.setattr(sp, "page_info", lambda titles, lang: {t: info[t] for t in titles})

    out = sp.resolve_titles(sp.parse_constituents(WIKITEXT)).set_index("ticker")

    assert out.loc["AMD", "title"] == "Advanced_Micro_Devices"
    assert out.loc["BRK.B", "status"] == "missing"
    assert out.loc["GOOG", "duplicate_of"] == "GOOGL" and out.loc["GOOGL", "duplicate_of"] == ""


def test_window_is_the_configured_years_up_to_end(monkeypatch):
    monkeypatch.setattr(sp, "params", lambda: {"end": "2026-10-31", "years": 5})

    assert sp.window() == (pd.Timestamp("2021-11-01"), pd.Timestamp("2026-10-31"))


def test_weeks_reaching_the_holdout_go_to_recent(monkeypatch):
    monkeypatch.setattr(sp.config, "holdout_start", lambda: pd.Timestamp("2025-10-01").date())
    rows = pd.DataFrame({"week": pd.to_datetime(["2025-09-15", "2025-09-22", "2025-09-29", "2025-10-06"])})

    parts = sp.split_holdout(rows)

    assert parts["research"]["week"].dt.strftime("%m-%d").tolist() == ["09-15", "09-22"]
    assert parts["recent"]["week"].dt.strftime("%m-%d").tolist() == ["09-29", "10-06"]   # Sep 29 week ends Oct 5


def test_stock_weekly_counts_full_weeks_from_the_article_start_and_caches_views(monkeypatch, tmp_path):
    revs = pd.DataFrame({"revid": [1, 2, 3], "timestamp": pd.to_datetime(["2021-10-20", "2021-11-03", "2021-11-09"]),
                         "user": ["a", "b", "b"], "size": [5000, 5100, 5050], "comment": ["", "", "rv vandalism"],
                         "before_start": [True, False, False]})
    monkeypatch.setattr(sp, "load_revisions", lambda *a, **k: revs)
    calls = []

    def views(title, start, end):
        calls.append(title)
        return pd.Series(10, index=pd.date_range(start, end, freq="D"))

    monkeypatch.setattr(sp, "article_views", views)
    start, end = pd.Timestamp("2021-11-01"), pd.Timestamp("2021-11-17")   # ends on a Wednesday

    wk = sp.stock_weekly("XYZ", "Xyz_Corp", start, end, raw=tmp_path)
    sp.stock_weekly("XYZ", "Xyz_Corp", start, end, raw=tmp_path)

    assert wk["week"].dt.strftime("%Y-%m-%d").tolist() == ["2021-11-01", "2021-11-08"]   # partial week dropped
    assert wk["views"].tolist() == [70, 70]
    assert wk["edits"].tolist() == [1, 1] and wk["reverts"].tolist() == [0, 1]
    assert calls == ["Xyz_Corp"]                                                          # second call read the cache
    assert set(wk[["ticker", "market", "source"]].iloc[0]) == {"XYZ", "US", "wikipedia"}
