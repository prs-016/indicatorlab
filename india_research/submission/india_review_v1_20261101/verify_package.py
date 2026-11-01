"""Verify the selected portable evidence, without market data or strategy execution.

Run with standard-library Python. Files may be in a checkout or a standalone copy.
"""
import csv
import hashlib
import json
import math
from pathlib import Path
import re
import statistics

BASE = Path(__file__).resolve().parent
PREFIX = 'india_research/submission/india_review_v1_20261101/'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def local_reference(value):
    if value.startswith(PREFIX):
        return BASE / value[len(PREFIX):]
    raise AssertionError('Not a portable package reference: ' + value)


def main():
    """Check hashes, links, units and recorded metric identities; return no files."""
    manifest = json.loads((BASE / 'bundle_manifest.json').read_text())
    declared = manifest['files']
    actual = {str(p.relative_to(BASE)) for p in BASE.rglob('*') if p.is_file()}
    assert actual == set(declared) | {'bundle_manifest.json'}, 'File inventory differs'
    for name, entry in declared.items():
        p = BASE / name
        assert sha(p) == entry['sha256'], name
        assert p.stat().st_size == entry['bytes'], name
        assert p.stat().st_size < 1024 * 1024, 'Oversize review file: ' + name
    links = 0
    for p in BASE.rglob('*.md'):
        for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)', p.read_text()):
            if '://' in target or target.startswith('#'):
                continue
            dest = (p.parent / target.split('#')[0]).resolve()
            assert dest.is_relative_to(BASE) and dest.is_file(), (p.name, target)
            links += 1
    rows = list(csv.DictReader((BASE / 'strategy_log.csv').open(newline='')))
    assert len(rows) == len({r['registry_id'] for r in rows}) == 10
    assert not any(None in r or any(v is None for v in r.values()) for r in rows)
    completed = 0
    for row in rows:
        assert 'Pending PM review' in row['final_pm_decision']
        assert local_reference(row['signal_evidence_directory']).is_dir()
        assert local_reference(row['source_report']).is_file()
        assert local_reference(row['methodology_reference']).is_file()
        if row['mean_execution_aligned_rank_ic'] == 'N/A':
            assert row['registry_id'] in {'alpha101_003', 'alpha101_004'}
            assert row['net_annualized_daily_sharpe'] == row['net_cumulative_return'] == 'N/A'
            continue
        completed += 1
        run = local_reference(row['result_directory'])
        metrics = json.loads((run / 'metrics.json').read_text())
        for col, key in [('mean_execution_aligned_rank_ic', 'execution_aligned_mean_rank_ic'),
                         ('net_annualized_daily_sharpe', 'net_daily_annualized_sharpe'),
                         ('net_cumulative_return', 'net_cumulative_return')]:
            assert float(row[col]) == metrics[key]
        daily = list(csv.DictReader((run / 'daily_returns_nav.csv').open()))
        assert len(daily) == metrics['evaluation_observations'] == 990
        assert daily[0]['date'][:10] == '2021-01-04'
        assert daily[-1]['date'][:10] == '2024-12-31'
        net = [float(r['net_return']) for r in daily]
        assert math.isclose(statistics.mean(net) / statistics.stdev(net) * math.sqrt(252),
                            metrics['net_daily_annualized_sharpe'], abs_tol=1e-11)
        assert math.isclose(math.prod(1 + r for r in net) - 1,
                            metrics['net_cumulative_return'], abs_tol=1e-11)
        for d in daily:
            assert math.isclose(float(d['net_return']),
                (1 + float(d['gross_return'])) * (1 - float(d['cost_fraction'])) - 1, abs_tol=1e-13)
            assert math.isclose(float(d['cost_fraction']), float(d['turnover']) * .001, abs_tol=1e-13)
        icrows = list(csv.reader((run / 'execution_aligned_ic.csv').open()))
        ics = [float(r[1]) for r in icrows[1:] if r[1] and math.isfinite(float(r[1]))]
        assert len(ics) == metrics['valid_ic_intervals']
        assert math.isclose(statistics.mean(ics), metrics['execution_aligned_mean_rank_ic'], abs_tol=1e-13)
        trades = list(csv.DictReader((run / 'trades.csv').open()))
        assert len(trades) == metrics['stock_trade_legs']
        assert all(t['signal_date'] < t['execution_date'] <= '2024-12-31' for t in trades)
        assert math.isclose(sum(float(t['cost_fraction']) for t in trades),
                            sum(float(d['cost_fraction']) for d in daily), abs_tol=1e-11)
        assert math.isclose(sum(abs(float(t['signed_nav_weight_change'])) for t in trades),
                            sum(float(d['turnover']) for d in daily), abs_tol=1e-10)
    assert completed == 8
    patterns = [r'/(?:home|Users)/[A-Za-z0-9_.-]+/', r'/tmp/[A-Za-z0-9_.-]+',
                r'file:[/][/]', r'\bgh[pousr]_[A-Za-z0-9]{30,}',
                r'\bgithub_pat_[A-Za-z0-9_]{40,}',
                r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b',
                r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----']
    for p in BASE.rglob('*'):
        if not p.is_file():
            continue
        text = p.read_text()
        for pattern in patterns:
            assert not re.search(pattern, text), ('Sensitive or machine-local reference', p.name)
    print(f'PASS: {len(declared)} hashed files, {links} local links, 10 entries, '
          '8 saved portfolio metric checks, 2 non-evaluable cases; no scoring/backtests.')


if __name__ == '__main__':
    main()
