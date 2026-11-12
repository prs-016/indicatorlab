"""Signal-only readiness diagnostics; no portfolio returns or trading simulation."""
import numpy as np
import pandas as pd


def signal_coverage(scores: pd.DataFrame, *, start='2021-01-04', end='2024-12-31') -> tuple[dict, pd.DataFrame]:
    """Describe finite coverage and exact/tolerant rank ties in an evaluation slice.

    Parameters: original factor scores and bounds. Returns summary and daily
    diagnostics. A cutoff tie means equal scores in sorted positions two/three;
    tolerance 1e-10 separately exposes numerical near-ties, without altering scores.
    """
    selected=scores.loc[start:end]
    rows=[]
    for date,row in selected.iterrows():
        valid=row.dropna().sort_values(ascending=False)
        vals=valid.to_numpy()
        rows.append({'date':date,'valid_names':len(valid),'missing_names':int(row.isna().sum()),
            'unique_exact_scores':valid.nunique(),
            'exact_tie':len(valid)>valid.nunique(),
            'all_eight_tied':len(valid)==8 and valid.nunique()==1,
            'top_two_boundary_exact_tie':len(valid)>=3 and vals[1]==vals[2],
            'top_two_boundary_near_tie':len(valid)>=3 and bool(np.isclose(vals[1],vals[2],rtol=0,atol=1e-10))})
    daily=pd.DataFrame(rows).set_index('date')
    weekly=selected.groupby(selected.index.to_period('W-FRI')).tail(1).index
    summary={'sessions':len(selected),'finite_cells':int(np.isfinite(selected.to_numpy()).sum()),
        'total_cells':selected.size,'missing_cells':int(selected.isna().sum().sum()),
        'all_eight_finite_sessions':int(daily.valid_names.eq(8).sum()),
        'all_missing_sessions':int(daily.valid_names.eq(0).sum()),
        'weekly_signal_dates':len(weekly),
        'weekly_all_eight_finite':int(daily.loc[weekly].valid_names.eq(8).sum()),
        'sessions_with_exact_ties':int(daily.exact_tie.sum()),
        'sessions_all_eight_tied':int(daily.all_eight_tied.sum()),
        'weekly_top_two_boundary_exact_ties':int(daily.loc[weekly].top_two_boundary_exact_tie.sum()),
        'weekly_top_two_boundary_near_ties':int(daily.loc[weekly].top_two_boundary_near_tie.sum()),
        'missing_by_symbol':selected.isna().sum().to_dict()}
    return summary,daily


def missing_causes(fields: dict, factor: str, scores: pd.DataFrame) -> pd.DataFrame:
    """Attribute original score NaNs to warm-up, incomplete or constant windows.

    Inputs are original factor fields/scores; output is one cause per missing cell.
    Correlation masks diagnose inputs, never replace production factor calculations.
    Any residual cause stays explicitly unexplained.
    """
    first={'alpha101_001':24,'alpha101_002':7,'alpha101_003':9,'alpha101_004':8}[factor]
    constant=None; incomplete=None
    if factor in {'alpha101_002','alpha101_003'}:
        rank=lambda x:x.rank(axis=1,method='average',pct=True)
        if factor=='alpha101_002':
            with np.errstate(divide='ignore',invalid='ignore'):
                x=rank(np.log(fields['volume']).diff(2))
            y=rank((fields['close']-fields['open'])/fields['open']);n=6
        else:
            x=rank(fields['open']);y=rank(fields['volume']);n=10
        constant=(x.rolling(n).max().eq(x.rolling(n).min()) | y.rolling(n).max().eq(y.rolling(n).min()))
        incomplete=x.rolling(n).count().lt(n) | y.rolling(n).count().lt(n)
    rows=[]
    for s in scores:
        for i,d in enumerate(scores.index):
            if pd.isna(scores.loc[d,s]):
                cause='unexplained_original_output'
                if i<first:cause='warmup'
                elif incomplete is not None and incomplete.loc[d,s]:cause='incomplete_rank_window'
                elif constant is not None and constant.loc[d,s]:cause='constant_rank_window'
                rows.append({'date':d,'symbol':s,'cause':cause})
    return pd.DataFrame(rows,columns=['date','symbol','cause'])


def compare_scores(baseline: pd.DataFrame, alternative: pd.DataFrame, *, start='2021-01-04',end='2024-12-31') -> tuple[dict,pd.DataFrame]:
    """Compare diagnostic scores and top-two ranks without holdings or returns.

    Matrices must align; NaN availability, rank/tie changes and weekly eligibility
    are counted separately. Top-two uses the existing descending/ticker tie rule.
    """
    if not baseline.index.equals(alternative.index) or not baseline.columns.equals(alternative.columns):
        raise ValueError('Comparison matrices must align')
    b,a=baseline.loc[start:end],alternative.loc[start:end]
    rows=[]
    for date in b.index:
        x,y=b.loc[date],a.loc[date];both=x.notna()&y.notna()
        eligible=x.notna().all() and y.notna().all()
        top=lambda row:tuple(sorted(row.index,key=lambda s:(-row[s],s))[:2])
        rows.append({'date':date,'availability_changed':bool(x.isna().ne(y.isna()).any()),
            'common_values_changed':bool((~np.isclose(x[both],y[both],rtol=0,atol=1e-10)).any()),
            'ranks_changed_on_common_names':not x[both].rank().equals(y[both].rank()),
            'both_all_eight_finite':bool(eligible),
            'top_two_changed':bool(eligible and set(top(x))!=set(top(y)))})
    daily=pd.DataFrame(rows).set_index('date');weekly=b.groupby(b.index.to_period('W-FRI')).tail(1).index
    summary={k:int(daily[k].sum()) for k in daily}
    summary.update(weekly_dates=len(weekly),weekly_both_all_eight_finite=int(daily.loc[weekly].both_all_eight_finite.sum()),
        weekly_top_two_changed=int(daily.loc[weekly].top_two_changed.sum()),
        weekly_availability_changed=int(daily.loc[weekly].availability_changed.sum()))
    return summary,daily


def classify_volume_ratio(yahoo: float, official: float, later_share_multiplier: float) -> dict:
    """Compare recorded volume to actual nominal shares and later split scaling.

    Return numerical ratios and evidence labels only; never rescale observations.
    One-share absolute tolerance handles reported integer rounding.
    """
    if not np.isfinite([yahoo,official,later_share_multiplier]).all() or min(yahoo,official,later_share_multiplier)<=0:
        raise ValueError('Positive finite trading quantities/multiplier required')
    nominal=bool(np.isclose(yahoo,official,rtol=0,atol=1))
    scaled=bool(np.isclose(yahoo,official*later_share_multiplier,rtol=0,atol=1))
    return {'vendor_to_official_ratio':yahoo/official,'nominal_match':nominal,'later_share_scaled_match':scaled,
        'classification':'nominal_and_scaled_identical' if nominal and scaled else 'nominal' if nominal else 'later_share_scaled' if scaled else 'unexplained_volume_difference'}
