"""Auditable volume-unit conversion into the frozen vendor share basis.

Only supported share events and exact independent quantity anchors authorize a
conversion. No price/factor changes, estimated ratios, fills or portfolio code.
"""
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.india_adjustments import parse_action
from src.india_data import BACKTEST_END

RECOVERED_DATES=('2023-11-12','2024-01-20','2024-03-02','2024-05-18')
AFFECTED_SYMBOLS=('RELIANCE.NS','HDFCBANK.NS','KOTAKBANK.NS')


def audit_volume_conversion(session: str, nominal_volume: float, *,
                             events: list[dict], anchors: list[dict],
                             vintage_end: str = '2026-10-28') -> dict:
    """Derive a share-unit multiplier and verify two official/vendor anchors.

    Parameters: missing session, positive integer official quantity, complete
    official corporate-action date/subject records through the frozen vintage,
    two bracketing nominal_volume/vendor_volume/date records, and metadata cutoff.
    Returns a ledger record; converted_volume stays None unless every check passes.
    Source extraction/hash validation is the caller's responsibility. Cash
    dividends do not scale volume. No empirical anchor ratio becomes a multiplier.
    """
    result={'date':session,'official_nominal_volume':nominal_volume,
            'verified':False,'converted_volume':None,'vintage_end':vintage_end}
    try:
        day=pd.Timestamp(session);vintage=pd.Timestamp(vintage_end)
        if session not in RECOVERED_DATES or not day<=BACKTEST_END<=vintage:
            raise ValueError('Conversion outside recovered-date/cutoff scope')
        if not np.isfinite(nominal_volume) or nominal_volume<=0 or not float(nominal_volume).is_integer():
            raise ValueError('Official quantity must be positive and integral')
        if len(anchors)!=2:raise ValueError('Two independent quantity anchors required')
        anchors=sorted(anchors,key=lambda a:a['date'])
        left,right=[pd.Timestamp(a['date']) for a in anchors]
        if not left<day<right<=BACKTEST_END:raise ValueError('Anchors must bracket session within cutoff')
        multiplier=1.;shares=[];seen=set()
        for event in events:
            date=pd.Timestamp(event['date']);key=(event['date'],event['subject'])
            if key in seen:raise ValueError('Duplicate corporate action')
            seen.add(key);kind,value=parse_action(event['subject'])
            if date>vintage:raise ValueError('Action metadata beyond frozen vintage')
            if kind=='shares':
                if left<date<=right:raise ValueError('Share action inside quantity bracket')
                if day<date:
                    multiplier*=value;shares.append({**event,'share_multiplier':value})
        converted=nominal_volume*multiplier
        if not np.isfinite(converted) or converted<=0 or not float(converted).is_integer():
            raise ValueError('Conversion is not a positive integral quantity; no rounding allowed')
        checks=[]
        for anchor in anchors:
            n,y=float(anchor['nominal_volume']),float(anchor['vendor_volume'])
            if not np.isfinite([n,y]).all() or min(n,y)<=0 or not n.is_integer() or not y.is_integer():
                raise ValueError('Invalid independent anchor quantities')
            checks.append({**anchor,'expected_vendor_volume':n*multiplier,
                           'observed_vendor_to_nominal_ratio':y/n,
                           'exact_match':y==n*multiplier})
        result.update(share_multiplier=multiplier,share_events=shares,anchor_checks=checks)
        if not all(a['exact_match'] for a in checks):
            raise ValueError('Independent quantities do not exactly support share-event multiplier')
        result.update(verified=True,converted_volume=int(converted),
            basis='Frozen Yahoo share-adjusted volume units, verified locally; not actual historical nominal shares')
    except (ValueError,TypeError,OverflowError) as exc:
        result['unresolved_reason']=str(exc)
    return result


def patch_volume_csv(content: bytes, changes: dict[str,int]) -> bytes:
    """Replace only specified CSV volume tokens, preserving every other byte.

    Parameters: simple numeric dated research CSV bytes and date->verified integer
    quantity mapping. Returns new bytes; absent/duplicate dates, quoted fields,
    nonpositive quantities or unsupported structure raise rather than rewriting
    unrelated fields or rounding. This function does not verify source evidence.
    """
    lines=content.decode('utf-8').splitlines(keepends=True)
    if not lines:raise ValueError('Empty research CSV')
    header=next(csv.reader([lines[0]]))
    if header.count('volume')!=1:raise ValueError('Unique volume column required')
    column=header.index('volume');seen=set();output=[lines[0]]
    for line in lines[1:]:
        body=line.rstrip('\r\n');ending=line[len(body):]
        tokens=next(csv.reader([body]))
        if tokens!=body.split(',') or len(tokens)!=len(header):
            raise ValueError('Expected simple unquoted research CSV')
        day=tokens[0]
        if day in changes:
            if day in seen:raise ValueError('Duplicate research session')
            quantity=changes[day]
            if not np.isfinite(quantity) or quantity<=0 or int(quantity)!=quantity:
                raise ValueError('Verified replacement must be positive and integral')
            tokens[column]=str(int(quantity));seen.add(day)
            output.append(','.join(tokens)+ending)
        else:output.append(line)
    if seen!=set(changes):raise ValueError('Recovered date absent from research CSV')
    return ''.join(output).encode('utf-8')


def write_volume_dataset(parent: Path, destination: Path, ledger: list[dict],
                          *, provenance: dict) -> Path:
    """Create an immutable nine-series version with exactly 12 verified changes.

    Parameters: parent research version, new destination, source-verified ledger
    and evidence provenance. Returns manifest path. All old prices/other values
    stay byte-for-byte intact; original files are hash-checked and never changed.
    Incomplete/duplicate/extra conversions fail before creating a directory.
    """
    parent,destination=Path(parent),Path(destination)
    if destination.exists():raise FileExistsError(destination)
    expected={(s,d) for s in AFFECTED_SYMBOLS for d in RECOVERED_DATES}
    actual={(r['symbol'],r['date']) for r in ledger}
    if len(ledger)!=12 or actual!=expected or not all(r['verified'] for r in ledger):
        raise ValueError('Exactly twelve independently verified conversions required')
    for r in ledger:
        if (not r.get('anchor_checks') or not all(a['exact_match'] for a in r['anchor_checks'])
                or r['converted_volume']!=r['official_nominal_volume']*r['share_multiplier']):
            raise ValueError('Invalid conversion ledger')
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    manifest_path=parent/'research_manifest.json';manifest=json.loads(manifest_path.read_text())
    for rel,h in manifest['files_sha256'].items():
        if digest(parent/rel)!=h:raise ValueError('Parent checksum mismatch')
    payload={}
    for rel in manifest['files_sha256']:
        if rel.startswith('derived/'):
            source=(parent/rel).read_bytes();symbol=Path(rel).stem
            changes={r['date']:r['converted_volume'] for r in ledger if r['symbol']==symbol}
            if changes:
                frame=pd.read_csv(parent/rel,index_col=0)
                for r in ledger:
                    if r['symbol']==symbol and float(frame.loc[r['date'],'volume'])!=r['official_nominal_volume']:
                        raise ValueError('Parent quantity differs from verified official record')
                payload[rel]=patch_volume_csv(source,changes)
            else:payload[rel]=source
    if len(payload)!=9:raise ValueError('Require nine derived histories')
    destination.mkdir(parents=True,exist_ok=False)
    (destination/'derived').mkdir()
    for rel,data in payload.items():(destination/rel).write_bytes(data)
    (destination/'volume_adjustment_ledger.json').write_text(json.dumps(ledger,indent=2,allow_nan=False)+'\n')
    pd.DataFrame([{k:v for k,v in r.items() if not isinstance(v,(list,dict))} for r in ledger]).to_csv(destination/'volume_adjustment_ledger.csv',index=False)
    result={'schema_version':4,'status':'twelve_verified_volume_unit_conversions_pending_user_review',
        'parent_manifest':str(manifest_path.resolve()),'parent_manifest_sha256':digest(manifest_path),
        'verified_volume_conversions':12,'unresolved_target_volume_conversions':[],
        'volume_basis':'Frozen vendor share units on recovered rows; all other vendor observations preserved',
        'modified_columns':['volume'],'modified_observations':12,'prices_unchanged':True,
        'calendar_rules_sha256':manifest['calendar_rules_sha256'],'calendar_certified':False,
        'backtest_ready':False,'portfolio_backtest_authorized':False,
        'provenance':provenance,
        'remaining_limitations':['Unresolved pre-July-2023 Reliance vendor non-split normalization; not changed.',
            'Five-vendor-share Kotak March 1 discrepancy retained, not explained or repaired.',
            'Full historical vendor quantity convention not independently verified on every session.',
            'Frozen adjustment vintage is not historically point-in-time; calendar inventory is not exhaustive.'],
        'files_sha256':{str(p.relative_to(destination)):digest(p) for p in destination.rglob('*') if p.is_file()}}
    (destination/'research_manifest.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    return destination/'research_manifest.json'
