#!/bin/zsh
set -eu
dashboard_root="${0:A:h}"
cd "$dashboard_root"
dashboard_python="${INDICATORLAB_PYTHON:-$dashboard_root/.venv/bin/python}"
if [[ ! -x "$dashboard_python" ]]; then
  dashboard_python="$dashboard_root/../../indicatorlab-clean/.venv/bin/python"
fi
if [[ ! -x "$dashboard_python" ]]; then
  print -r -- "Create this repo's .venv and install requirements.txt, or set INDICATORLAB_PYTHON."
  exit 1
fi
exec "$dashboard_python" -B -m src.hk_dashboard.launch --port "${INDICATORLAB_DASHBOARD_PORT:-8879}"
