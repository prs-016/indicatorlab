"""Offline January 20 reconciliation using frozen Phase 4B/4C evidence.

Run with ``python -m src.india_phase4d NEW_EVIDENCE_DIRECTORY`` after preserving
its January 23 retrieval manifest. No downloads or portfolio evaluation occur.
"""
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

from src.india_adjustments import audit_conversion
from src.india_calendar import audit_calendar, reconstruct_calendar
from src.india_data import BENCHMARK, NSE_STOCKS
from src.india_reconciliation import read_bhavcopy, verify_equities, verify_nifty50

ROOT = Path(__file__).resolve().parents[1]
PHASE4B = ROOT / 'results/india_adjustment_phase4b_20261029T012512Z_d2f07a95'
PHASE4C = ROOT / 'results/india_calendar_phase4c_20261029T015149Z_53a60385'
YAHOO = ROOT / 'results/india_history_phase2_a6f29fdafeeb'


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path, value):
    path.write_text(json.dumps(value, indent=2, default=str, allow_nan=False) + '\n')


def _sources(base):
    sources = {}
    for manifest in base.glob('*retrieval_manifest.json'):
        for record in json.loads(manifest.read_text()):
            if record.get('status') == 200:
                path = base / record['file']
                if _digest(path) != record['sha256']:
                    raise ValueError(f'Source checksum mismatch: {path}')
                if urlparse(record['url']).hostname not in {
                    'nsearchives.nseindia.com', 'archives.nseindia.com', 'www.nseindia.com',
                    'www.ril.com', 'www.sec.gov'}:
                    raise ValueError('Unexpected evidence host')
                sources[path.name] = (path, record)
    return sources


def reconcile(destination: Path) -> Path:
    """Write a new research version and full audit from checksum-verified sources.

    Parameters: destination contains the preserved January 23 archive and its
    retrieval manifest. Returns the new manifest path. Existing research_v3 is
    never overwritten; incomplete calendar evidence always retains the gate.
    """
    destination = Path(destination)
    out = destination / 'research_v3'
    if out.exists():
        raise FileExistsError(out)
    parent = PHASE4B / 'research_v2'
    manifests = [parent/'research_manifest.json', YAHOO/'manifest.json']
    preserved = {}
    for path in manifests:
        preserved[str(path)] = _digest(path)
        for relative, sha in json.loads(path.read_text())['files_sha256'].items():
            target = path.parent / relative
            if _digest(target) != sha:
                raise ValueError(f'Parent checksum mismatch: {target}')
            preserved[str(target)] = sha
    sources = {**_sources(PHASE4B), **_sources(PHASE4C), **_sources(destination)}
    records, equities = {}, {}
    for date, name in [('2024-01-19','cm19JAN2024bhav.csv.zip'),
                       ('2024-01-20','cm20JAN2024bhav.csv.zip'),
                       ('2024-01-23','cm23JAN2024bhav.csv.zip')]:
        path, record = sources[name]
        expected = 'https://nsearchives.nseindia.com/content/historical/EQUITIES/2024/JAN/' + name
        if record['url'] != expected or record.get('final_url', expected) != expected:
            raise ValueError('Unexpected equity archive URL')
        verified, issues = verify_equities(read_bhavcopy(path.read_bytes()), date, allowed_sessions=(date,))
        if issues or len(verified) != 8:
            raise ValueError(f'Invalid official anchor/session records: {date}: {issues}')
        equities[date] = verified.set_index('symbol')
        records[date] = record
    path, index_source = sources['ind_close_all_20012024.csv']
    if index_source['url'] != 'https://nsearchives.nseindia.com/content/indices/ind_close_all_20012024.csv':
        raise ValueError('Unexpected index source')
    index = verify_nifty50(pd.read_csv(path), '2024-01-20', allowed_sessions=('2024-01-20',))
    actions = pd.read_csv(parent/'official_corporate_actions.csv')
    dividends = pd.read_csv(parent/'independent_dividend_checks.csv')
    # Revalidate every inherited independent cash-step evidence file.
    for row in dividends.itertuples():
        if not row.step_pass or _digest(PHASE4B/row.source_file) != row.source_sha256:
            raise ValueError('Invalid inherited dividend evidence')
    histories = {s: pd.read_csv(parent/f'derived/{s}.csv', index_col=0, parse_dates=True)
                 for s in (*NSE_STOCKS, BENCHMARK)}
    ledger = []
    day = pd.Timestamp('2024-01-20')
    for symbol in NSE_STOCKS:
        raw = pd.read_csv(YAHOO/f'raw/{symbol}.csv', index_col=0)
        raw.index = pd.to_datetime(raw.index, utc=True).tz_convert('Asia/Kolkata').tz_localize(None).normalize()
        events = actions.loc[actions.symbol.eq(symbol), ['date','subject']].to_dict('records')
        cash = dividends[dividends.symbol.eq(symbol)]
        previous = dict(zip(cash.ex_date, cash.previous_nominal_close))
        anchors = []
        for date in ['2024-01-19','2024-01-23']:
            official = equities[date].loc[symbol]
            if official['isin'] != equities['2024-01-20'].loc[symbol,'isin']:
                raise ValueError('Anchor ISIN mismatch')
            anchors.append({'date':date, 'nominal_close':float(official.close),
                            'yahoo_close':float(raw.loc[date,'Close']),
                            'yahoo_adjusted_close':float(raw.loc[date,'Adj Close']),
                            'source_url':records[date]['url'], 'source_sha256':records[date]['sha256']})
        official = equities['2024-01-20'].loc[symbol]
        end = raw.loc['2024-12-31']
        row = audit_conversion('2024-01-20',float(official.close), terminal_date='2024-12-31',
                               terminal_close=float(end.Close), terminal_adjusted_close=float(end['Adj Close']),
                               events=events, previous_nominal_closes=previous, anchors=anchors)
        row.update(symbol=symbol, volume=int(official.volume), trades=int(official.trades),
                   official_source_url=records['2024-01-20']['url'],
                   official_source_sha256=records['2024-01-20']['sha256'])
        ledger.append(row)
        frame = histories[symbol]
        if day in frame.index:
            raise ValueError('Recovered date already present')
        original = frame.copy()
        frame = frame.reindex(frame.index.union(pd.DatetimeIndex([day])))
        if row['verified']:
            for field in ['open','high','low','close']:
                frame.loc[day,field] = float(official[field])*row['total_conversion_factor']
            frame.loc[day,'volume'] = official.volume
            frame.loc[day,'adjustment_ratio'] = row['reconstructed_dividend_factor']
            frame.loc[day,'adjustment_valid'] = True
            for field in ['dividends','stock_splits','capital_gains']:
                if field in frame:
                    frame.loc[day,field] = 0.
        frame.index.name = original.index.name
        pd.testing.assert_frame_equal(frame.loc[original.index], original, check_dtype=False)
        histories[symbol] = frame
    benchmark = histories[BENCHMARK]
    original = benchmark.copy()
    if day in benchmark.index:
        raise ValueError('Index date already present')
    benchmark = benchmark.reindex(benchmark.index.union(pd.DatetimeIndex([day])))
    for field in ['open','high','low','close','volume']:
        benchmark.loc[day,field] = index[field]
    benchmark.loc[day,'adjustment_ratio'] = 1.
    benchmark.loc[day,'adjustment_valid'] = True
    benchmark.index.name = original.index.name
    pd.testing.assert_frame_equal(benchmark.loc[original.index], original, check_dtype=False)
    histories[BENCHMARK] = benchmark
    rules_path = PHASE4C/'audit_v1/calendar_rules.json'
    rules = json.loads(rules_path.read_text())
    # Validate every cited calendar source against preserved bytes, not just URLs.
    for rule in [*rules['annual_rules'].values(), *rules['overrides']]:
        if not any(r['sha256']==rule['source_sha256'] and r['url']==rule['source_url']
                   for _,r in sources.values()):
            raise ValueError('Calendar evidence missing')
    calendar = reconstruct_calendar('2020-12-01','2024-12-31',
        annual_rules={int(y):r for y,r in rules['annual_rules'].items()}, overrides=rules['overrides'])
    audit = audit_calendar(calendar,histories,amendment_coverage_confirmed=False)
    out.mkdir()
    (out/'derived').mkdir()
    for symbol, frame in histories.items():
        frame.sort_index().to_csv(out/f'derived/{symbol}.csv',index_label='Date')
    _write(out/'conversion_ledger.json',ledger)
    pd.DataFrame([{k:v for k,v in row.items() if not isinstance(v,(list,dict))} for row in ledger]).to_csv(out/'conversion_ledger.csv',index=False)
    official = equities['2024-01-20'].reset_index()
    official['source_url']=records['2024-01-20']['url']
    official['source_sha256']=records['2024-01-20']['sha256']
    pd.concat([official,pd.DataFrame([{**index,'source_url':index_source['url'],'source_sha256':index_source['sha256']}])]).to_csv(out/'official_quotes.csv',index=False)
    calendar.to_csv(out/'expected_calendar.csv',index_label='date')
    audit.discrepancies.to_csv(out/'discrepancies.csv',index=False)
    audit.lookbacks.to_csv(out/'strev_21_session_lookbacks.csv',index=False)
    audit.schedule.to_csv(out/'weekly_execution_candidates.csv',index=False)
    _write(out/'readiness.json',audit.summary)
    if any(_digest(Path(path)) != sha for path,sha in preserved.items()):
        raise ValueError('Original files changed')
    manifest = {'schema_version':3,'phase':'4D','backtest_ready':False,'calendar_certified':False,
        'verified_stock_conversions':sum(r['verified'] for r in ledger),'expected_stock_conversions':8,
        'unresolved':[r['symbol'] for r in ledger if not r['verified']],
        'parent_manifest':str(manifests[0]),'parent_manifest_sha256':_digest(manifests[0]),
        'calendar_rules_sha256':_digest(rules_path), 'amendment_coverage_confirmed':False,
        'remaining_gate':'Non-exhaustive calendar amendment evidence; user review. No automatic certification from vendor/calendar agreement.',
        'adjustment_convention':json.loads(manifests[0].read_text())['calculation'],
        'normalization_limitation':'Frozen Yahoo terminal dividend ratio inherited; post-2024 adjustments not independently reconstructed; not point-in-time prices.',
        'volume_basis':'Official nominal shares actually traded; no volume rescaling.',
        'original_files_sha256':preserved,
        'evidence_files_sha256':{str(p):r['sha256'] for p,r in sources.values()},
        'source_code_sha256':{str(ROOT/f):_digest(ROOT/f) for f in ['src/india_phase4d.py','src/india_adjustments.py','src/india_reconciliation.py','src/india_calendar.py']},
        'no_portfolio_backtest_executed':True,'no_holdout_prices_retrieved':True,
        'files_sha256':{str(p.relative_to(out)):_digest(p) for p in out.rglob('*') if p.is_file()}}
    _write(out/'research_manifest.json',manifest)
    return out/'research_manifest.json'


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination',type=Path)
    print(reconcile(parser.parse_args().destination))
