"""Selection-oriented IC scores preserve the strategy's actual preference order."""

import pandas as pd

from src.hk.ic_diagnostic import oriented_score


def test_negative_priority_selected_names_outrank_rejected_names():
    priority = pd.Series({"low_vol": -0.1, "higher_vol": -0.2, "rejected": -0.01})
    mask = pd.Series({"low_vol": True, "higher_vol": True, "rejected": False})
    result = oriented_score(mask, priority, priority.notna())
    assert result.low_vol > result.higher_vol > result.rejected == 0


def test_zero_priority_ablation_retains_selection_and_missing_history():
    priority = pd.Series({"selected": 0.0, "rejected": 0.0, "missing": 0.0})
    mask = pd.Series({"selected": True, "rejected": False, "missing": False})
    observed = pd.Series({"selected": True, "rejected": True, "missing": False})
    result = oriented_score(mask, priority, observed)
    assert result.selected > result.rejected == 0
    assert pd.isna(result["missing"])
