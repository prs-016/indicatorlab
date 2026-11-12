"""Signal-only Alpha #4 tie and input-convention decision diagnostics."""
from itertools import combinations
import numpy as np
import pandas as pd


def membership_profile(row: pd.Series) -> dict:
    """Enumerate top-two memberships permitted by original scores before tie-break.

    Input is one eight-name original score row. Returns the original ascending-
    ticker pair, a descending-ticker diagnostic pair, strict winners and all
    equally admissible memberships. Missing scores are not filled. No actual
    orders, holdings or returns are calculated, and no tie rule is adopted.
    """
    if len(row)!=8 or not row.index.is_unique:
        raise ValueError('Require exactly eight unique names')
    if row.isna().any() or np.isinf(row.to_numpy()).any():
        return {'eligible':False,'admissible_pairs':[]}
    selected=sorted(row.index,key=lambda s:(-row[s],s))[:2]
    # Sort scores first, and reverse ticker order only within exactly equal scores.
    reverse=sorted(row.index,reverse=True)
    reverse=sorted(reverse,key=lambda s:-row[s])[:2]
    cutoff=row[selected[-1]]
    strict=sorted(row.index[row.gt(cutoff)])
    pool=sorted(row.index[row.eq(cutoff)])
    slots=2-len(strict)
    pairs=sorted(tuple(sorted([*strict,*tied])) for tied in combinations(pool,slots))
    return {'eligible':True,'selected_pair':tuple(sorted(selected)),
        'reverse_ticker_pair':tuple(sorted(reverse)),
        'strict_winners':strict,'cutoff_pool':pool,'slots':slots,
        'admissible_pairs':pairs,'admissible_pair_count':len(pairs),
        'membership_depends_on_ticker':len(pairs)>1,'all_eight_tied':row.nunique()==1}


def weekly_profiles(scores: pd.DataFrame) -> list[dict]:
    """Return profiles at each baseline W-FRI candidate close, without trading.

    Input is original score history. Output includes the non-executable terminal
    candidate separately; no different weekly schedule or eligibility is chosen.
    """
    selected=scores.loc['2021-01-04':'2024-12-31']
    weekly=selected.groupby(selected.index.to_period('W-FRI')).tail(1)
    return [{'signal_date':str(d.date()),'has_later_evaluation_session':d<selected.index[-1],
             **membership_profile(row)} for d,row in weekly.iterrows()]


def compare_memberships(baseline: pd.DataFrame, alternative: pd.DataFrame) -> pd.DataFrame:
    """Separate ticker-selected pair changes from unavoidable preference changes.

    Inputs are aligned original scores under labelled price conventions. Output
    compares weekly candidate membership sets. Disjoint admissible sets imply a
    change under every tie rule; overlapping sets expose an ambiguous comparison,
    without pretending that the observed deterministic selections were unchanged.
    """
    if not baseline.index.equals(alternative.index) or not baseline.columns.equals(alternative.columns):
        raise ValueError('Diagnostic score matrices must align')
    a,b=weekly_profiles(baseline),weekly_profiles(alternative)
    rows=[]
    for x,y in zip(a,b):
        assert x['signal_date']==y['signal_date']
        if not x['eligible'] or not y['eligible']:
            rows.append({'signal_date':x['signal_date'],'both_eligible':False});continue
        left,right=set(x['admissible_pairs']),set(y['admissible_pairs'])
        rows.append({'signal_date':x['signal_date'],'both_eligible':True,
            'has_later_evaluation_session':x['has_later_evaluation_session'],
            'selected_pair_changed':x['selected_pair']!=y['selected_pair'],
            'baseline_tie_ambiguous':len(left)>1,'alternative_tie_ambiguous':len(right)>1,
            'admissible_pairs_disjoint':not bool(left&right),
            'baseline_selected_admissible_in_alternative':x['selected_pair'] in right,
            'alternative_selected_admissible_in_baseline':y['selected_pair'] in left,
            'admissible_pair_sets_equal':left==right,
            'overlap_pair_count':len(left&right)})
    return pd.DataFrame(rows)


def low_rank_window_audit(lows: pd.DataFrame, scores: pd.DataFrame) -> pd.DataFrame:
    """Describe constant nine-session low-rank windows and their unranked prices.

    Inputs are aligned original lows/scores. Returns per stock/date cause evidence;
    this diagnostic neither computes replacement scores nor identifies bad prices.
    A constant nine-rank window has the original tied percentile 5/9 and score -5/9.
    """
    if not lows.index.equals(scores.index) or not lows.columns.equals(scores.columns):
        raise ValueError('Lows and scores must align')
    rank=lows.rank(axis=1,pct=True,method='average')
    rank_range=rank.rolling(9).max()-rank.rolling(9).min()
    price_range=lows.rolling(9).max()-lows.rolling(9).min()
    records=[]
    for s in lows:
        for d in lows.loc['2021-01-04':'2024-12-31'].index:
            records.append({'date':d,'symbol':s,'original_score':scores.loc[d,s],
                'constant_low_rank_window':bool(rank_range.loc[d,s]==0),
                'unranked_low_varies':bool(price_range.loc[d,s]>0),
                'low_rank_range_9':rank_range.loc[d,s]})
    return pd.DataFrame(records)
