# Manual code review

Date: 4 November 2026

The requested specialized code-review skill is not installed in this Codex session, so the review was performed manually and backed by focused tests.

## Reviewed

- `agent/src/tools/alpha_bench_tool.py`
- `agent/src/api/alpha_routes.py`
- `agent/tests/test_alpha_bench_universe_metadata.py`
- `research/hk_week2/*.py`
- `research/hk_market_history/download_hsi_history.py`
- `research/hk_market_history/validate_hsi_history.py`

## Findings resolved

1. The old end-2024 roster inferred membership from price-file coverage. It now uses the exact 83-name official roster; `0011.HK` is explicitly documented as unavailable rather than silently omitted.
2. Five stale reconstructed membership intervals understated official quarterly counts. Their official HSI re-admission dates are now explicit; all 19 count checks pass.
3. API readiness initially reported HSI as always ready. It now verifies the local coverage manifest and point-in-time membership file.
4. The HSI loader adjusts all OHLC fields by `Adj Close / Close`, applies effective-dated membership masks and reports missing instruments in metadata.
5. Strategy timing is next-close, costs are applied to one-way turnover, and the test period is not used to tune parameters or decisions.

## Verification

- Archive validator: `pass_with_source_warnings`; every critical assertion passed.
- Workbook formula scan: zero matches for `#REF!`, `#DIV/0!`, `#VALUE!`, `#NAME?`, or `#N/A`.
- Pytest: 40 passed, one pre-existing Python 3.14/Pydantic compatibility warning.

## Open limitation

The full-session live poller is implemented but has not yet been observed during an entire live Hong Kong session. The completed-session replay is clearly labeled as a replay.
