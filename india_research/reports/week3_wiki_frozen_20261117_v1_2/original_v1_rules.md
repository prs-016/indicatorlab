# Original WATM_v1 / WVB_v1 / WCR_v1 trade-rule proposal

Preserved from the earlier user-visible proposal in this session; no standalone
repository copy was found. This is not a ChatGPT handoff document. No existing
AGM/SCB/AER file is replaced. This excerpt preserves the original trading rules.

Shared: exact ten-US/eight-India universes; SPY/^NSEI; train 2016-06-01–2021-12-31;
test 2022-01-01–2025-09-30; warm-up from 2015-07-01. Prior-eight-week Wikipedia
ratio and past-only robust z (26 preceding values, MAD 1.4826). Tuesday 00:00 UTC
decisions, guide one-day Wikipedia lag, next eligible positive-volume close,
entry expiry after two sessions. Long only, two positions, no leverage.
d=max(0.02,2*ATR20/close); reject d>0.10; weight=min(0.50,0.01/d).
Initial stop fill*(1-d), raised to highest completed close minus 2*entry ATR.
Missing observations are never filled or converted to zero.

WATM_v1: regime benchmark close>SMA200. Valid Wikipedia ratios/z for at least
seven Indian/eight US companies; median robust z>=2 halves all targets, otherwise
full targets. Insufficient coverage targets cash. Attention does not select names.
Weekly select positive close[t-21]/close[t-126]-1 momentum and close>SMA50,
rank by momentum descending then ticker ascending, take top two. Remove names
losing eligibility/membership; resize retained names. Daily protective stops.

WVB_v1: benchmark close>SMA200 entry regime. At weekly decision require
close>highest high of preceding 20 sessions, volume>=1.2*mean preceding20 volume,
Wikipedia ratio>=1.2 and complete ratio/z warm-up. Fill vacant slots ranked by
(close-prior20_high)/ATR20 descending, ticker ascending. Exit on protective stop,
close<preceding10 low or twentieth eligible close including entry. Do not replace
holdings merely for a higher-ranked candidate.

WCR_v1: benchmark close>SMA200 entry regime. Previous-week Wikipedia ratio>=1.5
and z>=2; current ratio>=1 and strictly below previous ratio; close<SMA20;
30<=Wilder RSI14<=45; one-session return>0. Vacant slots ranked by return1/(ATR20/close),
ticker ascending. Exit on protective stop, close>=SMA20, RSI14>=60 or tenth eligible
close including entry. Four completed weekly decisions after exit before re-entry.
