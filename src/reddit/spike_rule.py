"""The team's weekly spike rule, computed from past weeks only.

Same rule as James's Wikipedia `flag_spikes` (src/wiki_attention.py on the `wikipedia` branch),
with the Week 2 look-ahead fix: the robust z-score's median and MAD come from earlier weeks
only, never from the whole series. Parameters live in config.yaml (`spike`):

    baseline = median of the previous `baseline_weeks` weeks (week t excluded)
    abnormal = log((x + offset) / (baseline + offset))
    rz       = (abnormal - med) / (mad_scale * mad), med and mad over abnormal values of weeks < t,
               defined once `rz_min_history` of them exist
    spike    = abnormal >= log(ratio) and rz >= rz_threshold

`offset` (1) keeps zero-count weeks finite for small Reddit series; for page views in the
thousands it changes nothing. Replace this module with the shared `spikes.py` once it is on main.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src import config


def past_median_mad(a: pd.Series, min_history: int) -> tuple[pd.Series, pd.Series]:
    """Median and MAD of the non-missing values strictly before each position."""
    vals = a.to_numpy(dtype=float)
    med = np.full(len(vals), np.nan)
    mad = np.full(len(vals), np.nan)
    for t in range(len(vals)):
        past = vals[:t][~np.isnan(vals[:t])]
        if len(past) >= min_history:
            med[t] = np.median(past)
            mad[t] = np.median(np.abs(past - med[t]))
    return pd.Series(med, index=a.index), pd.Series(mad, index=a.index)


def flag_spikes(x: pd.Series, rule: dict | None = None) -> pd.DataFrame:
    """Spike columns for ONE weekly series (one ticker and source), sorted by week, one row per week.

    Missing weeks must be present as NaN rows, so `shift` and `rolling` count weeks, not rows.
    Returns baseline, ratio, abnormal, rz and spike (False wherever any input is undefined).
    """
    r = {**config.spike_rule(), **(rule or {})}
    off = r.get("offset", 1.0)
    base = x.shift(1).rolling(r["baseline_weeks"], min_periods=r["baseline_weeks"]).median()
    ratio = (x + off) / (base + off)
    abnormal = np.log(ratio)
    med, mad = past_median_mad(abnormal, r["rz_min_history"])
    rz = (abnormal - med) / (r["mad_scale"] * mad.where(mad > 0))
    spike = (abnormal >= np.log(r["ratio"])) & (rz >= r["rz_threshold"])
    return pd.DataFrame({"baseline": base, "ratio": ratio, "abnormal": abnormal, "rz": rz,
                         "spike": spike.fillna(False).astype(bool)}, index=x.index)


def add_spikes(df: pd.DataFrame, group_cols: list[str], value_col: str, week_col: str = "week",
               rule: dict | None = None) -> pd.DataFrame:
    """Apply `flag_spikes` to `value_col` within each group of a long weekly table."""
    parts = []
    for _, g in df.sort_values([*group_cols, week_col]).groupby(group_cols, sort=False):
        flags = flag_spikes(g[value_col].astype(float), rule)
        parts.append(pd.concat([g, flags], axis=1))
    return pd.concat(parts) if parts else df.assign(baseline=np.nan, ratio=np.nan, abnormal=np.nan, rz=np.nan,
                                                    spike=False)
