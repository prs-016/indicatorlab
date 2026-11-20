#!/bin/zsh
# Stop only the dashboard API; keep the independent quote collector running.
set -eu
dashboard_root="${0:A:h}"
cd "$dashboard_root"
if [[ -x "$dashboard_root/.venv/bin/python" ]]; then
  dashboard_python="$dashboard_root/.venv/bin/python"
elif [[ -x "$dashboard_root/../indicatorlab-clean/.venv/bin/python" ]]; then
  dashboard_python="$dashboard_root/../indicatorlab-clean/.venv/bin/python"
else
  dashboard_python="python3"
fi
exec "$dashboard_python" -B -m src.hk.dashboard stop
