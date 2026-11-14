"""Offline causal-rule, engine-accounting and timing-control regressions."""

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from src.hk.week3.features import Bundle, monday, strategy_week
from src.hk.week3.public_data import added_text
from src.hk.week3.wiki_history import reconstruct

ROOT = Path(__file__).resolve().parents[1]
VIBE = ROOT.parent / "Vibe-Trading-upstream"


def fixture_bundle(attention=2.0):
    week = pd.Timestamp("2021-01-04")
    codes = ["a", "b"]
    values = {
        "shock": [-2, 1],
        "return": [-0.05, 0.01],
        "rv20": [0.02, 0.02],
        "rv63": [0.02, 0.03],
        "turnover": [100, 200],
        "volume_ratio": [2, 2],
        "residual": [-2, 2],
        "compression": [0.7, 0.9],
        "view_ratio": [2, 2],
        "edit_ratio": [2, 2],
        "views": [100, 100],
        "sentiment": [0.2, 0.2],
        "index_vol": [0.2, 0.2],
        "index_vol_q90": [0.3, 0.3],
        "index_downside": [0.1, 0.1],
        "index_downside_q75": [0.2, 0.2],
        "attention_z": [attention, attention],
    }
    weekly = {
        key: pd.DataFrame([value], index=[week], columns=codes)
        for key, value in values.items()
    }
    return (
        Bundle(
            "HK",
            pd.date_range(week, periods=2),
            codes,
            {},
            weekly,
            pd.DataFrame(),
            pd.Series(dtype=float),
            {},
        ),
        week,
    )


def test_monday_labels_weekend_information_before_next_market_open():
    assert monday(
        pd.to_datetime(["2021-01-04", "2021-01-08", "2021-01-10"])
    ).unique().tolist() == [pd.Timestamp("2021-01-04")]


def test_drop_one_removes_selection_and_rank_use():
    bundle, week = fixture_bundle()
    strategy = {"id": "liquidity_repair"}
    params = {"shock": 1.0, "volume": 1.5, "views": 1.2, "sentiment": 0.1}
    mask, _, _ = strategy_week(bundle, strategy, params, week)
    dropped, rank, _ = strategy_week(
        bundle, strategy, params, week, "negative_volatility_scaled_return"
    )
    assert mask.to_dict() == {"a": True, "b": False}
    assert dropped.all() and rank.eq(0).all()


def test_attention_gate_halves_whole_book_without_changing_selection():
    bundle, week = fixture_bundle()
    strategy = {"id": "defensive_attention_gate"}
    params = {"liquidity_quantile": 0, "sentiment": 0}
    mask, rank, exposure = strategy_week(bundle, strategy, params, week)
    other_mask, other_rank, ungated = strategy_week(
        bundle, strategy, params, week, "market_attention_risk_gate"
    )
    pd.testing.assert_series_equal(mask, other_mask)
    pd.testing.assert_series_equal(rank, other_rank)
    assert exposure == ungated / 2


def test_added_text_uses_historical_changes_only():
    text = added_text(
        "Unchanged sentence.\nOld facts.",
        "Unchanged sentence.\nNew profits grew.<ref>citation</ref>",
    )
    assert "New profits grew" in text
    assert (
        "Unchanged sentence" not in text
        and "Old facts" not in text
        and "citation" not in text
    )


def test_title_history_uses_stable_logpage_not_current_redirect_pageid():
    page = {
        "pageid": 1,
        "title": "New Name",
        "created": "2010-01-01T00:00:00Z",
        "lang": "en",
    }
    logs = [
        {
            "logid": 4,
            "logpage": 1,
            "pageid": 99,
            "title": "Old Name",
            "timestamp": "2020-01-01T12:00:00Z",
            "params": {"target_ns": 0, "target_title": "New Name"},
        }
    ]
    intervals, gaps = reconstruct(page, logs)
    assert not gaps
    assert intervals[0]["title"] == "Old_Name"
    assert (
        intervals[0]["valid_to"] == intervals[1]["valid_from"] == "2020-01-01T12:00:00Z"
    )


def isolated(code, tmp_path):
    if not VIBE.exists():
        pytest.skip("External Vibe checkout required for actual engine integration")
    script = tmp_path / "probe.py"
    script.write_text(
        "import sys\nsys.path.insert(0,"
        + repr(str(VIBE / "agent"))
        + ")\nsys.path.insert(0,"
        + repr(str(ROOT / "src/hk/week3"))
        + ")\n"
        + code
    )
    result = subprocess.run(
        [sys.executable, "-B", str(script)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout.splitlines()[-1])


@pytest.mark.parametrize("market", ["US", "HK"])
def test_event_scheduler_matches_actual_vibe_bar_engine(tmp_path, market):
    code = """
import numpy as np,pandas as pd,json
from engine_adapter import ResearchEquityEngine,simulate
dates=pd.bdate_range('2021-01-04',periods=12)
code='0700.HK' if MARKET=='HK' else 'AAPL.US'
opens=np.arange(100.0,112.0)[:,None]
closes=opens+0.2
data={'codes':[code],'dates':dates,'open':opens,'close':closes,'volume':np.ones((12,1))*10000,'dividend':np.zeros((12,1))}
frame=pd.DataFrame({'open':opens[:,0],'close':closes[:,0],'volume':10000},index=dates)
data['frames']={code:frame}
plans=[{'symbol':code,'entry':1,'exit':5,'weight':0.1}]
fast=simulate(data,plans,MARKET,1000000,{code:100},0,11)
native=ResearchEquityEngine({'initial_cash':1000000,'slippage_us':0.001,'hk_lot_sizes':{code:100}},market='hk' if MARKET=='HK' else 'us')
target=pd.DataFrame(0.0,index=dates,columns=[code]);target.iloc[1:5,0]=0.1
native._execute_bars(dates,{code:frame},pd.DataFrame({code:closes[:,0]},index=dates),target,[code])
expected=np.array([row.equity for row in native.equity_snapshots])
assert np.allclose(expected,fast['equity'],atol=1e-8), (expected,fast['equity'])
assert len(native.trades)==fast['entries']==1
print(json.dumps({'equal':True,'commission':fast['commission']}))
""".replace("MARKET", repr(market))
    assert isolated(code, tmp_path)["equal"]


def test_dense_random_schedule_preserves_all_entries_and_durations(tmp_path):
    code = """
import numpy as np,json
from engine_adapter import random_schedule
plans=[{'symbol':'a','entry':2+i*3,'exit':5+i*3,'weight':0.1} for i in range(8)]
data={'codes':['a'],'open':np.ones((32,1))*100,'volume':np.ones((32,1))}
data['volume'][:2]=0
sample=random_schedule(plans,data,0,31,np.random.default_rng(42))
assert len(sample)==8 and all(p['entry']>=2 and p['exit']-p['entry']==3 for p in sample)
ordered=sorted(sample,key=lambda p:p['entry'])
assert all(a['exit']<=b['entry'] for a,b in zip(ordered,ordered[1:]))
print(json.dumps({'preserved':True}))
"""
    assert isolated(code, tmp_path)["preserved"]


def test_hk_duty_date_switch_and_whole_dollar_rounding(tmp_path):
    code = """
import pandas as pd,json
from engine_adapter import ResearchEquityEngine
engine=ResearchEquityEngine({},market='hk')
engine._bar_ts=pd.Timestamp('2021-07-30');old=engine.calc_commission(100,100,1,True)
engine._bar_ts=pd.Timestamp('2021-08-02');new=engine.calc_commission(100,100,1,True)
assert abs(new-old-3)<1e-8
engine._bar_ts=pd.Timestamp('2024-01-02');small=engine.calc_commission(1,1,1,True)
assert small>=1
print(json.dumps({'dated':True}))
"""
    assert isolated(code, tmp_path)["dated"]
