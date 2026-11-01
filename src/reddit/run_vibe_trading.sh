#!/usr/bin/env bash
# Run the five Alpha101 benchmark strategies with Vibe-Trading and capture full logs.
#
# Why PYTHONPATH: macOS sets the "hidden" file flag on the uv venv's .pth files, and
# Python >= 3.11.8 skips hidden .pth files, so the editable install's `cli` package
# is not importable via the `vibe-trading` entry point. Pointing PYTHONPATH at
# Vibe-Trading/agent reproduces exactly what the entry point would import.
# (Permanent fix, not applied here: chflags nohidden .venv/lib/python3.11/site-packages/*.pth)
set -uo pipefail

HERE="$(cd "$(dirname "$0")/../.." && pwd)"   # repo root
VT="${VIBE_TRADING_DIR:-$HERE/../Vibe-Trading}"
OUT="$HERE/results/reddit/strategy_logs"
mkdir -p "$OUT"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$OUT/alpha_compare_${TS}.log"

ALPHAS=(alpha101_002 alpha101_003 alpha101_006 alpha101_012 alpha101_013)
ARGS=(alpha compare "${ALPHAS[@]}" --universe sp500 --period 2021-2024)

{
  echo "# started_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "# equivalent command: vibe-trading ${ARGS[*]}"
  echo "# actual invocation: cd $VT && PYTHONPATH=agent .venv/bin/python -m cli ${ARGS[*]}"
  echo "# vibe-trading git commit: $(git -C "$VT" rev-parse --short HEAD 2>/dev/null)"
} > "$LOG"

cd "$VT" || exit 1
PYTHONPATH=agent COLUMNS=200 .venv/bin/python -m cli "${ARGS[@]}" >> "$LOG" 2>&1
RC=$?
{
  echo "exit=$RC"
  echo "# finished_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
} >> "$LOG"
ln -sf "$(basename "$LOG")" "$OUT/alpha_compare_latest.log"
echo "log: $LOG (exit=$RC)"
exit $RC
