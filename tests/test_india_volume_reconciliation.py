"""OFFLINE SYNTHETIC verified-volume conversion and immutable-version tests."""
import hashlib
import json

import pytest

from src.india_data import NSE_STOCKS,BENCHMARK
from src.india_volume_reconciliation import (RECOVERED_DATES,AFFECTED_SYMBOLS,
    audit_volume_conversion,patch_volume_csv,write_volume_dataset)


def arguments(session='2024-01-20',multiplier=2):
    subject='Bonus 1:1' if multiplier==2 else 'Face Value Split - From Rs 5 Per Share To Re 1 Per Share'
    return dict(session=session,nominal_volume=100,events=[{'date':'2025-08-26','subject':subject}],
        anchors=[{'date':'2023-11-10','nominal_volume':500,'vendor_volume':500*multiplier},
                 {'date':'2024-05-21','nominal_volume':600,'vendor_volume':600*multiplier}])


@pytest.mark.parametrize('session',RECOVERED_DATES)
@pytest.mark.parametrize('symbol,multiplier',[('RELIANCE.NS',2),('HDFCBANK.NS',2),('KOTAKBANK.NS',5)])
def test_each_recovered_stock_date_requires_action_and_two_exact_anchors(session,symbol,multiplier):
    result=audit_volume_conversion(**arguments(session,multiplier))
    assert result['verified'],symbol
    assert result['share_multiplier']==multiplier
    assert result['converted_volume']==100*multiplier
    assert len(result['anchor_checks'])==2 and all(a['exact_match'] for a in result['anchor_checks'])


def test_empirical_ratio_does_not_become_an_invented_multiplier():
    args=arguments();args['events']=[]
    row=audit_volume_conversion(**args)
    assert not row['verified'] and row['converted_volume'] is None


def test_near_match_is_not_silently_rounded_into_verification():
    args=arguments(multiplier=5);args['anchors'][0]['vendor_volume']-=5
    row=audit_volume_conversion(**args)
    assert not row['verified'] and row['converted_volume'] is None
    assert row['anchor_checks'][0]['expected_vendor_volume']==2500


def test_cash_dividend_does_not_adjust_quantity():
    args=arguments();args['events'].append({'date':'2024-02-01','subject':'Dividend - Rs 10 Per Share'})
    row=audit_volume_conversion(**args)
    assert row['verified'] and row['converted_volume']==200


def test_share_event_inside_bracket_prevents_constant_multiplier():
    args=arguments();args['events'].append({'date':'2024-02-01','subject':'Bonus 1:1'})
    row=audit_volume_conversion(**args)
    assert not row['verified'] and 'bracket' in row['unresolved_reason']


@pytest.mark.parametrize('mutation', ['postcutoff_anchor','missing_anchor','unknown_action','duplicate_action','bad_quantity'])
def test_incomplete_or_invalid_evidence_stays_unresolved(mutation):
    args=arguments()
    if mutation=='postcutoff_anchor':args['anchors'][1]['date']='2025-10-01'
    elif mutation=='missing_anchor':args['anchors']=args['anchors'][:1]
    elif mutation=='unknown_action':args['events'].append({'date':'2024-08-01','subject':'Unknown distribution'})
    elif mutation=='duplicate_action':args['events']*=2
    else:args['nominal_volume']=0
    row=audit_volume_conversion(**args)
    assert not row['verified'] and row['converted_volume'] is None


def test_patch_changes_only_volume_token_preserving_all_price_bytes():
    source=b'Date,open,high,low,close,volume\r\n2024-01-19,1.000000000000001,2,1,1.5,100.0\r\n2024-01-20,1,2,1,1.5,200.0\r\n'
    result=patch_volume_csv(source,{'2024-01-20':400})
    assert result==source.replace(b'1.5,200.0\r\n',b'1.5,400\r\n')
    assert source.endswith(b'1.5,200.0\r\n')


def test_patch_rejects_missing_or_duplicate_session_and_noninteger():
    with pytest.raises(ValueError,match='absent'):
        patch_volume_csv(b'Date,volume\n2024-01-19,100\n',{'2024-01-20':200})
    with pytest.raises(ValueError,match='Duplicate'):
        patch_volume_csv(b'Date,volume\n2024-01-20,100\n2024-01-20,100\n',{'2024-01-20':200})
    with pytest.raises(ValueError,match='integral'):
        patch_volume_csv(b'Date,volume\n2024-01-20,100\n',{'2024-01-20':200.5})


def test_version_requires_all_twelve_and_never_overwrites(tmp_path):
    parent=tmp_path/'parent';(parent/'derived').mkdir(parents=True)
    hashes={}
    for symbol in (*NSE_STOCKS,BENCHMARK):
        path=parent/f'derived/{symbol}.csv'
        path.write_text('Date,open,high,low,close,volume\n'+''.join(f'{d},1.001,2,1,1.5,100\n' for d in RECOVERED_DATES))
        hashes[str(path.relative_to(parent))]=hashlib.sha256(path.read_bytes()).hexdigest()
    (parent/'research_manifest.json').write_text(json.dumps({'files_sha256':hashes,'calendar_rules_sha256':'0'*64}))
    ledger=[]
    for s,m in zip(AFFECTED_SYMBOLS,[2,2,5]):
        for date in RECOVERED_DATES:
            row=audit_volume_conversion(**arguments(date,m));row['symbol']=s;ledger.append(row)
    with pytest.raises(ValueError,match='twelve'):
        write_volume_dataset(parent,tmp_path/'incomplete',ledger[:11],provenance={})
    assert not (tmp_path/'incomplete').exists()
    manifest=write_volume_dataset(parent,tmp_path/'v4',ledger,provenance={'fixtures':'SYNTHETIC'})
    data=json.loads(manifest.read_text())
    assert data['verified_volume_conversions']==12 and not data['backtest_ready']
    assert data['modified_columns']==['volume']
    for symbol in (*NSE_STOCKS,BENCHMARK):
        if symbol not in AFFECTED_SYMBOLS:
            assert (parent/f'derived/{symbol}.csv').read_bytes()==(manifest.parent/f'derived/{symbol}.csv').read_bytes()
    for relative,h in hashes.items():assert hashlib.sha256((parent/relative).read_bytes()).hexdigest()==h
    with pytest.raises(FileExistsError):write_volume_dataset(parent,tmp_path/'v4',ledger,provenance={})


def test_order_only_change_does_not_change_equal_weight_membership():
    import pandas as pd
    from src.india_factor_readiness import compare_scores
    dates=pd.bdate_range('2021-01-04',periods=5)
    baseline=pd.DataFrame([[8,7,6,5,4,3,2,1]]*5,index=dates,columns=NSE_STOCKS)
    alternative=baseline.copy()
    alternative.loc[:,NSE_STOCKS[0]]=7
    alternative.loc[:,NSE_STOCKS[1]]=8
    summary,_=compare_scores(baseline,alternative)
    assert summary['ranks_changed_on_common_names']==5
    assert summary['weekly_top_two_changed']==0
