# Where to Find the Hong Kong Week 2 Work

Repository root: `/Users/jackgui/Desktop/hk/indicatorlab-Jack`

## Step 2 - Maximum History

- Equity daily CSVs: `research/hk_market_history/prices/`
- HSI benchmark: `research/hk_market_history/benchmark/Hang_Seng_Index__HSI__daily__1986-12-31_to_2026-11-04.csv`
- Ticker-to-file lookup: `research/hk_market_history/price_file_index.csv`
- Coverage and first/last date for every ticker: `research/hk_market_history/coverage.csv`
- Archive summary: `research/hk_market_history/summary.json`
- Data-quality result: `research/hk_market_history/validation_summary.json`
- Per-file validation: `research/hk_market_history/validation_checks.csv`
- Five-stock history/split/gap checks: `research/hk_week2/outputs/max_history_splits_summary.csv`
- Split events: `research/hk_week2/outputs/split_events.csv`
- Downloader: `research/hk_market_history/download_hsi_history.py`
- Validator: `research/hk_market_history/validate_hsi_history.py`

The large `prices/` and `benchmark/` data files are local and intentionally ignored by Git. The manifests, validation results and scripts are tracked.

## Step 3 - Live Data

- Five repeated readings for Yahoo, Tencent and Eastmoney: `research/hk_week2/outputs/live_source_readings.csv`
- Source capability/delay/key/rate-limit table: `research/hk_week2/outputs/live_source_capabilities.csv`
- Google Finance close cross-check: `research/hk_week2/outputs/google_finance_close_check.csv`
- Latest completed one-minute session bars: `research/hk_week2/outputs/latest_session_1m_bars.csv`
- Latest-session gap summary: `research/hk_week2/outputs/latest_session_1m_summary.csv`
- Repeat-reading script: `research/hk_week2/compare_live_sources.py`
- Full-session one-minute poller: `research/hk_week2/live_poller.py`
- Completed-session replay audit: `research/hk_week2/analyze_latest_intraday_session.py`

The comparison and latest-session audit exist. A literal live 09:30-16:05 HKT observation is still pending. Start the poller before the Hong Kong open and leave it running through the close:

```bash
python3 research/hk_week2/live_poller.py
```

## Step 4 - Hang Seng Lists and Past Members

- Current official 95-company list: `research/hk_week2/outputs/hsi_current_constituents.csv`
- Effective-dated point-in-time membership: `research/hk_week2/outputs/hsi_membership_intervals.csv`
- Official quarterly review-count reconciliation: `research/hk_week2/outputs/hsi_review_count_checks.csv`
- History checks for all reconstructed members: `research/hk_week2/outputs/all_hsi_history_checks.csv`
- Construction code and source URLs: `research/hk_week2/build_week2_evidence.py`

The effective-dated history starts in late 2014. It is enough for the honest 2015-2019 train and 2020-September 2025 holdout, but it is not a licensed complete history back to the HSI's 1969 launch.

## Step 5 - Hong Kong Attention Configuration

- English and Chinese company names, Wikipedia titles and subreddit targets: `research/hk_week2/hk_attention_config.json`

## Step 6 - HSI Universe in IndicatorLab

- `hsi` universe alias and point-in-time loader: `agent/src/tools/alpha_bench_tool.py`
- API readiness and `hsi` to `equity_hk` mapping: `agent/src/api/alpha_routes.py`
- Hong Kong enum: `agent/src/factors/base.py`
- Loader and reliability tests: `agent/tests/test_alpha_bench_universe_metadata.py`, `agent/tests/test_analysis_reliability.py`, `agent/tests/test_bench_universe_selection.py`

The code exists and tests locally. It is currently on the repository's `Jack` branch. The assignment's separate GitHub workflow - personal fork, `hsi-universe` branch, issue, pull request and requested review - has not been completed.

## Step 7 - Strategies

Original diagnostics and TGQM:

- Runner: `research/hk_week2/backtest_hsi_strategies.py`
- Results: `research/hk_week2/outputs/strategy_results.csv`
- Short result table: `research/hk_week2/outputs/strategy_log.md`

Five advanced, eight-requirement-compliant candidates:

- Runner: `research/hk_week2/backtest_advanced_hsi_strategies.py`
- IC, Sharpe and decisions: `research/hk_week2/outputs/advanced_strategy_results.csv`
- Short result table: `research/hk_week2/outputs/advanced_strategy_log.md`
- All eight requirements by strategy: `research/hk_week2/outputs/advanced_strategy_requirements.csv`
- 200 matched random portfolios per strategy: `research/hk_week2/outputs/advanced_strategy_random_baselines.csv`
- Daily net returns: `research/hk_week2/outputs/advanced_strategy_daily_returns.csv`
- Rebalance selections: `research/hk_week2/outputs/advanced_strategy_rebalances.csv`

Reproduce the advanced results with:

```bash
python3 research/hk_week2/backtest_advanced_hsi_strategies.py
```

Five non-momentum, eight-requirement-compliant candidates:

- Runner: `research/hk_week2/backtest_non_momentum_hsi_strategies.py`
- IC, Sharpe and decisions: `research/hk_week2/outputs/non_momentum_strategy_results.csv`
- Short result table: `research/hk_week2/outputs/non_momentum_strategy_log.md`
- All eight requirements by strategy: `research/hk_week2/outputs/non_momentum_strategy_requirements.csv`
- 200 matched random portfolios per strategy: `research/hk_week2/outputs/non_momentum_strategy_random_baselines.csv`
- Daily net returns: `research/hk_week2/outputs/non_momentum_strategy_daily_returns.csv`
- Rebalance selections: `research/hk_week2/outputs/non_momentum_strategy_rebalances.csv`

Reproduce the non-momentum results with:

```bash
python3 research/hk_week2/backtest_non_momentum_hsi_strategies.py
```

## One-File Summaries

- Main written report: `research/hk_week2/WEEK2_REPORT.md`
- Meeting workbook: `research/hk_week2/outputs/HK_Week2_Checklist_and_Strategies.xlsx`
