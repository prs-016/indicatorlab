import numpy as np
import pandas as pd

from src.wiki_export import EDIT_COLS, RECORD_COLS, current_record, weekly_records


def test_weekly_records_put_views_edits_and_sentiment_in_one_row():
    att = pd.DataFrame({"week": ["2024-01-08", "2024-01-08", "2024-01-15", "2024-01-15"], "ticker": "AAPL",
                        "market": "US", "source": ["wikipedia_views", "wikipedia_edits"] * 2,
                        "views": [100.0, np.nan, 300.0, np.nan], "edits": [np.nan, 4.0, np.nan, 9.0],
                        "baseline": [90.0, 3.0, 95.0, 3.0], "ratio": [1.1, 1.25, 3.1, 2.5],
                        "spike": [False, False, True, True]})
    sent = pd.DataFrame({"ticker": ["AAPL"], "week": ["2024-01-15"], "sentiment_pos": [0.2],
                         "sentiment_neg": [0.5], "sentiment_neu": [0.3], "n_scored": [6]})
    out = weekly_records(att, sent)
    assert list(out.columns) == RECORD_COLS + EDIT_COLS and len(out) == 2
    assert (out["market"] == "us").all() and (out["source"] == "wikipedia").all()
    assert out["value"].tolist() == [100.0, 300.0] and out["edits"].tolist() == [4.0, 9.0]
    assert out["spike"].tolist() == [False, True] and out["edits_ratio"].tolist() == [1.25, 2.5]
    assert out["n_scored"].tolist() == [0, 6] and np.isnan(out.loc[0, "sentiment_neg"])


def test_current_record_compares_the_trailing_week_with_the_8_full_weeks_before_it():
    days = pd.date_range("2024-01-01", "2024-09-25")              # ends on a Wednesday
    daily = pd.Series(100.0 + 10 * np.sin(np.arange(len(days)) / 3), index=days)
    daily[days >= "2024-09-16"] = 400.0                           # Mon 16th onwards; trailing 7 days = 19th-25th
    r = current_record(daily, "AAPL", "US")
    assert r["value"] == 2800.0 and r["as_of"] == pd.Timestamp("2024-09-25")
    assert r["week"] == pd.Timestamp("2024-09-23") and r["market"] == "us"
    # baseline: the 8 full weeks ending before Thu 19th (Jul 22 to Sep 15), not the overlapping week of the 16th
    weeks = daily["2024-07-22":"2024-09-15"].groupby(np.arange(56) // 7).sum()
    assert np.isclose(r["baseline"], weeks.median()) and np.isclose(r["ratio"], 2801 / (weeks.median() + 1))
    assert r["spike"]


def test_current_record_with_a_missing_day_has_no_value():
    daily = pd.Series(100.0, index=pd.date_range("2024-01-01", "2024-09-25")).drop(pd.Timestamp("2024-09-22"))
    r = current_record(daily, "AAPL", "US")
    assert np.isnan(r["value"]) and not r["spike"]


def test_edit_summaries_keep_whole_research_weeks_and_drop_usernames():
    from src.wiki_export import edit_summaries
    revs = pd.DataFrame({"revid": [1, 2, 3, 4], "user": "someone", "size": [100, 150, 140, 160],
                         "timestamp": pd.to_datetime(["2025-09-14", "2025-09-16", "2025-09-24", "2025-09-30"]),
                         "comment": [None, "Q3 earnings", "Reverted vandalism", "late"],
                         "before_start": [True, False, False, False], "title": "Apple_Inc."})
    e = edit_summaries(revs, "AAPL", "US", pd.Timestamp("2025-10-01"))
    assert e["comment"].tolist() == ["Q3 earnings", "Reverted vandalism"]   # Sep 30 is in the Sep 29 week
    assert e["delta"].tolist() == [50, -10] and e["revert"].tolist() == [False, True]
    assert e["tag_earnings"].tolist() == [True, False] and "user" not in e
    assert (e["market"] == "us").all()
