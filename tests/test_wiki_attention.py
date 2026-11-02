import numpy as np
import pandas as pd
import pytest

from src import config, wiki_attention
from src.wiki_attention import article_views, flag_spikes, pageviews, weekly

RULE = config.spike_rule()
BASELINE_WEEKS = RULE["baseline_weeks"]
MIN_HISTORY = RULE["rz_min_history"]


def _weekly(values):
    idx = pd.date_range("2026-01-05", periods=len(values), freq="W-MON")
    return pd.Series(values, index=idx, dtype=float)


def _noisy(n, seed=0):
    return _weekly(1000 + np.random.default_rng(seed).integers(-100, 101, n))


# --- the three week-1 tests (offset 0 so 1000 -> 2000 is exactly log 2)

def test_abnormal_is_log2_after_flat_baseline():
    out = flag_spikes(_weekly([1000] * BASELINE_WEEKS + [2000]), {"offset": 0})
    assert np.isclose(out["abnormal"].iloc[-1], np.log(2))


def test_week_not_in_own_baseline():
    out = flag_spikes(_weekly([1000] * BASELINE_WEEKS + [5000]))
    assert out["baseline"].iloc[-1] == 1000


def test_first_weeks_not_flagged():
    out = flag_spikes(_weekly([1000] * 3 + [9000] + [1000] * 10))
    assert not out["spike"].iloc[:BASELINE_WEEKS].any()


# --- week 2: the rule fires, handles zeros, and never looks ahead

def test_clear_spike_is_flagged():
    x = _noisy(60)
    x.iloc[50] = 4000
    out = flag_spikes(x)
    assert out["spike"].iloc[50] and out["spike"].sum() == 1


def test_no_flag_before_rz_history():
    x = _noisy(60)
    x.iloc[20] = 9000   # huge, but only 12 abnormal values exist before it
    assert not flag_spikes(x)["spike"].iloc[: BASELINE_WEEKS + MIN_HISTORY].any()


def test_zero_baseline_stays_finite():
    # sparse counts (e.g. Reddit posts): the offset keeps log(x / baseline) finite
    x = _weekly([0, 1] * 20 + [0] * 8 + [3])
    out = flag_spikes(x)
    assert np.isfinite(out["abnormal"].iloc[BASELINE_WEEKS:]).all()
    assert np.isclose(out["abnormal"].iloc[-1], np.log(4))


def test_zero_mad_gives_no_rz_and_no_spike():
    # a flat history has MAD 0: rz is undefined (NaN), never +-inf, and nothing is flagged
    out = flag_spikes(_weekly([1000] * 45 + [3000]))
    assert np.isnan(out["rz"].iloc[-1]) and not np.isinf(out["rz"]).any()
    assert not out["spike"].any()


def test_changing_future_weeks_leaves_past_flags_unchanged():
    x = _noisy(80, seed=3)
    x.iloc[45] = 3500
    t = 55
    before = flag_spikes(x)
    y = x.copy()
    y.iloc[t + 1:] = y.iloc[t + 1:] * 10 + 5000   # only weeks after t change
    after = flag_spikes(y)
    cols = ["baseline", "abnormal", "rz", "spike"]
    pd.testing.assert_frame_equal(before[cols].iloc[: t + 1], after[cols].iloc[: t + 1])


def test_weekly_labels_by_monday_and_drops_partial_weeks():
    days = pd.date_range("2026-01-07", "2026-01-25", freq="D")   # Wed .. Sun
    wk = weekly(pd.Series(1, index=days))
    assert list(wk.index) == [pd.Timestamp("2026-01-12"), pd.Timestamp("2026-01-19")]
    assert (wk.index.dayofweek == 0).all() and (wk == 7).all()


# --- pageviews() and article_views() without the network

class _Resp:
    def __init__(self, status, payload=None):
        self.status_code, self._payload = status, payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise wiki_attention.requests.HTTPError(str(self.status_code))


@pytest.fixture
def contact(monkeypatch):
    monkeypatch.setenv("WIKIMEDIA_CONTACT", "test@example.org")


def test_pageviews_fills_missing_days_and_sends_contact(monkeypatch, contact):
    calls = []

    def fake_get(url, headers, timeout, **kw):
        calls.append((url, headers))
        return _Resp(200, {"items": [{"timestamp": "2026010100", "views": 5},
                                     {"timestamp": "2026010300", "views": 7}]})

    monkeypatch.setattr(wiki_attention.SESSION, "get", fake_get)
    v = pageviews("Tesla,_Inc.", pd.Timestamp("2026-01-01"), pd.Timestamp("2026-01-04"))
    assert v.tolist() == [5, 0, 7, 0]
    assert v.index[0] == pd.Timestamp("2026-01-01") and len(v) == 4
    url, headers = calls[0]
    assert "/en.wikipedia/all-access/user/Tesla%2C_Inc./daily/20260101/20260104" in url
    assert "test@example.org" in headers["User-Agent"]


def test_pageviews_404_raises_unless_missing_ok(monkeypatch, contact):
    monkeypatch.setattr(wiki_attention.SESSION, "get", lambda *a, **k: _Resp(404))
    a, b = pd.Timestamp("2026-01-01"), pd.Timestamp("2026-01-02")
    with pytest.raises(wiki_attention.requests.HTTPError):
        pageviews("No_such_page", a, b)
    assert pageviews("No_such_page", a, b, missing_ok=True).tolist() == [0, 0]


def test_missing_contact_raises(monkeypatch):
    monkeypatch.setattr(wiki_attention, "load_dotenv", lambda: None)
    monkeypatch.delenv("WIKIMEDIA_CONTACT", raising=False)
    with pytest.raises(RuntimeError, match="WIKIMEDIA_CONTACT"):
        wiki_attention.user_agent()


def test_article_views_sums_redirects(monkeypatch, contact):
    days = pd.date_range("2026-01-01", periods=2)
    views = {"New_name": [0, 0], "Old_name": [10, 20], "Typo": [1, 0]}   # renamed article
    monkeypatch.setattr(wiki_attention, "redirects", lambda title, lang: ["Old_name", "Typo"])
    monkeypatch.setattr(wiki_attention, "pageviews",
                        lambda t, a, b, lang, missing_ok: pd.Series(views[t], index=days))
    assert article_views("New_name", days[0], days[-1]).tolist() == [11, 20]
