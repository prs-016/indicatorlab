"""Offline synthetic Phase 4D boundary and source-integrity regressions."""
import hashlib
import json

import pytest

from src.india_adjustments import audit_conversion
from src.india_phase4d import _sources, reconcile


@pytest.mark.parametrize('symbol', ['RELIANCE.NS','TCS.NS','INFY.NS','HDFCBANK.NS',
                                   'ICICIBANK.NS','SBIN.NS','KOTAKBANK.NS','AXISBANK.NS'])
def test_january20_post_dividend_bracket(symbol):
    # SYNTHETIC prices, not actual NSE evidence: an ex-dividend left anchor
    # excludes that day's cash step from January 20's adjustment product.
    result = audit_conversion('2024-01-20',100.,terminal_date='2024-12-31',
        terminal_close=100.,terminal_adjusted_close=80.,
        events=[{'date':'2024-01-19','subject':'Dividend - Rs 27 Per Share'}],
        previous_nominal_closes={}, anchors=[
            {'date':d,'nominal_close':100.,'yahoo_close':100.,'yahoo_adjusted_close':80.}
            for d in ['2024-01-19','2024-01-23']])
    assert result['verified'], symbol
    assert result['adjusted_close'] == pytest.approx(80.)
    assert result['dividend_steps'] == []


def test_pre_dividend_left_anchor_cannot_be_carried_across_jan19():
    result = audit_conversion('2024-01-20',100.,terminal_date='2024-12-31',
        terminal_close=100.,terminal_adjusted_close=80.,
        events=[{'date':'2024-01-19','subject':'Dividend - Rs 27 Per Share'}],
        previous_nominal_closes={},anchors=[
            {'date':d,'nominal_close':100.,'yahoo_close':100.,'yahoo_adjusted_close':80.}
            for d in ['2024-01-18','2024-01-23']])
    assert not result['verified']
    assert result['adjusted_close'] is None
    assert 'inside anchor' in result['unresolved_reason']


def test_sources_reject_tampered_evidence(tmp_path):
    path = tmp_path/'synthetic.zip'
    path.write_bytes(b'SYNTHETIC original archive')
    record = {'status':200,'file':path.name,'url':'https://nsearchives.nseindia.com/synthetic.zip',
              'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    (tmp_path/'retrieval_manifest.json').write_text(json.dumps([record]))
    assert path.name in _sources(tmp_path)
    path.write_bytes(b'SYNTHETIC altered archive')
    with pytest.raises(ValueError,match='checksum'):
        _sources(tmp_path)


def test_research_version_cannot_be_overwritten(tmp_path):
    (tmp_path/'research_v3').mkdir()
    with pytest.raises(FileExistsError):
        reconcile(tmp_path)
