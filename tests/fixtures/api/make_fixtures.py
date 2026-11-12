"""Writes the small tables the API tests read (rerun after changing the attention record):

    .venv/bin/python tests/fixtures/api/make_fixtures.py
"""
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
weeks = pd.to_datetime(["2025-09-01", "2025-09-08", "2025-09-15", "2025-09-22", "2025-09-29", "2025-10-06"])
#                                                                 last research week ^   ^ ends Oct 5: holdout


def wiki(ticker, spikes, net):
    return pd.DataFrame({"ticker": ticker, "market": "us", "source": "wikipedia", "week": weeks,
                         "value": [100.0, 110, 400, 120, 500, 600], "baseline": 100.0,
                         "ratio": [1.0, 1.1, 4.0, 1.2, 5.0, 6.0], "spike": spikes,
                         "sentiment_pos": 0.2, "sentiment_neg": 0.2 - net, "sentiment_neu": 0.6 + net,
                         "n_scored": [0, 3, 5, 2, 4, 4], "edits": 3.0, "edits_ratio": 1.0, "edits_spike": False})


pd.concat([wiki("AAPL", [False, False, True, True, True, True], -0.1),
           wiki("MSFT", [False, False, True, False, False, False], 0.3)]).to_parquet(
    HERE / "processed" / "wiki_weekly.parquet", index=False)
pd.DataFrame({"ticker": "AAPL", "market": "us", "source": "reddit", "week": weeks, "value": 50.0,
              "baseline": 25.0, "ratio": 2.0, "spike": pd.array([None, False, True, False, False, True], "boolean"),
              "group": "investor", "sentiment_pos": 0.5, "sentiment_neg": 0.1, "sentiment_neu": 0.4,
              "n_scored": 10}).to_parquet(HERE / "processed" / "reddit_weekly.parquet", index=False)
pd.DataFrame({"ticker": ["AAPL", "MSFT", "RELIANCE.NS"], "market": ["us", "us", "india"], "source": "wikipedia",
              "week": pd.Timestamp("2026-11-09"), "value": [900.0, 80, 300], "baseline": [300.0, 100, 200],
              "ratio": [3.0, 0.8, 1.5], "spike": pd.array([True, False, None], "boolean"), "sentiment_pos": None,
              "sentiment_neg": None, "sentiment_neu": None, "n_scored": 0,
              "as_of": pd.Timestamp("2026-11-10")}).to_parquet(HERE / "processed" / "wiki_current.parquet", index=False)
pd.DataFrame({"ticker": ["AAPL", "MSFT"], "market": "us", "week": pd.Timestamp("2025-09-15"),
              "abn_ret": [0.01, -0.05], "abn_ret_next1": [-0.03, 0.01]}).to_parquet(
    HERE / "processed" / "prices_weekly.parquet", index=False)
(HERE / "live" / "india.json").write_text(json.dumps([
    {"symbol": "TCS.NS", "price": 4100.5, "change_pct": -0.4, "volume": 120000, "ts_exchange": "2026-11-10T15:29:58+05:30",
     "ts_received": "2026-11-10T09:59:59Z", "source": "yahoo"},
    {"symbol": "RELIANCE.NS", "price": 2950.0, "change_pct": 1.2, "volume": 900000,
     "ts_exchange": "2026-11-10T15:29:59+05:30", "ts_received": "2026-11-10T10:00:00Z", "source": "yahoo"}], indent=1))
