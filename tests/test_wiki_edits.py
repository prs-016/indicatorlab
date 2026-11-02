import pandas as pd

from src import wiki_edits
from src.wiki_edits import edit_table, revisions, tag_summaries, weekly_edits


def _revs():
    return pd.DataFrame({
        "revid": [1, 2, 3, 4],
        "timestamp": pd.to_datetime(["2025-12-31 23:00", "2026-01-05 10:00", "2026-01-06 12:00", "2026-01-13 09:00"]),
        "user": ["a", "b", "b", "c"],
        "size": [1000, 1300, 1250, 1250],
        "comment": ["old", "Added Q3 earnings", "Reverted edits by X", "server migration note"],
        "before_start": [True, False, False, False],
    })


def test_tags_and_reverts_match_whole_words():
    t = tag_summaries(pd.Series(["rv vandalism", "server fix", "Undid revision 5", "new CEO named",
                                 "acquired Beats", "stock split"]))
    assert t["revert"].tolist() == [True, False, True, False, False, False]   # "server" is not "rv"
    assert t["tag_ceo_executive"].tolist() == [False, False, False, True, False, False]
    assert t.loc[4, "tag_acquisition_merger"] and t.loc[5, "tag_stock_shares"]


def test_edit_table_uses_the_revision_before_the_window_for_size_change():
    e = edit_table(_revs())
    assert e["revid"].tolist() == [2, 3, 4]
    assert e["delta"].tolist() == [300, -50, 0]
    assert e["tag_earnings"].tolist() == [True, False, False]


def test_weekly_edits_counts_and_zero_weeks():
    weeks = pd.DatetimeIndex(["2026-01-05", "2026-01-12", "2026-01-19"])
    w = weekly_edits(edit_table(_revs()), weeks)
    assert w["edits"].tolist() == [2, 1, 0]
    assert w["editors"].tolist() == [1, 1, 0]
    assert w.loc["2026-01-05", "bytes_added"] == 300 and w.loc["2026-01-05", "bytes_removed"] == 50
    assert w["reverts"].tolist() == [1, 0, 0]


def test_revisions_follows_rvcontinue(monkeypatch):
    pages = [
        {"query": {"pages": [{"title": "X", "revisions": [
            {"revid": 1, "timestamp": "2015-06-30T00:00:00Z", "user": "a", "size": 10, "comment": ""}]}]}},
        {"continue": {"rvcontinue": "next"}, "query": {"pages": [{"title": "X", "revisions": [
            {"revid": 2, "timestamp": "2015-07-01T01:00:00Z", "user": "b", "size": 12, "comment": "c"}]}]}},
        {"query": {"pages": [{"title": "X", "revisions": [
            {"revid": 3, "timestamp": "2015-07-02T01:00:00Z", "user": "c", "size": 9}]}]}},
    ]
    seen = []

    def fake_query(title, lang, **extra):
        seen.append(extra.get("rvcontinue"))
        return pages[len(seen) - 1]

    monkeypatch.setattr(wiki_edits, "_rev_query", fake_query)
    df = revisions("X", pd.Timestamp("2015-07-01"), pd.Timestamp("2015-07-31"))
    assert df["revid"].tolist() == [1, 2, 3] and seen == [None, None, "next"]
    assert df["before_start"].tolist() == [True, False, False]
    assert df.loc[2, "comment"] == ""   # hidden summary
