import numpy as np
import pandas as pd
from src.wiki_attention import flag_spikes, BASELINE_WEEKS


def _weekly(values):
    idx = pd.date_range("2026-01-04", periods=len(values), freq="W-SUN")
    return pd.Series(values, index=idx, dtype=float)


def test_abnormal_is_log2_after_flat_baseline():
    out = flag_spikes(_weekly([1000] * BASELINE_WEEKS + [2000]))
    assert np.isclose(out["abnormal"].iloc[-1], np.log(2))


def test_week_not_in_own_baseline():
    out = flag_spikes(_weekly([1000] * BASELINE_WEEKS + [5000]))
    assert out["baseline"].iloc[-1] == 1000


def test_first_weeks_not_flagged():
    out = flag_spikes(_weekly([1000] * 3 + [9000] + [1000] * 10))
    assert not out["spike"].iloc[:BASELINE_WEEKS].any()