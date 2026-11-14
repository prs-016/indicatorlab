"""Start, inspect or stop only this repository's local HSI quote worker."""

from __future__ import annotations

import argparse
import json
import os
import signal
import statistics
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from src.hk.live import write_json

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "data/live_hk/current"
PID_FILE = OUTPUT / "worker.json"


def worker_pid() -> int | None:
    """Verify a saved PID still belongs to this collector before signalling it."""
    if not PID_FILE.exists():
        return None
    try:
        pid = int(json.loads(PID_FILE.read_text())["pid"])
        command = subprocess.check_output(
            ["ps", "-p", str(pid), "-o", "command="], text=True
        )
        if "src.hk.live" in command and str(OUTPUT) in command:
            return pid
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError):
        pass
    return None


def status() -> dict:
    """Return worker identity and freshness recomputed at inspection time."""
    data = {"pid": worker_pid(), "output": str(OUTPUT)}
    if (OUTPUT / "status.json").exists():
        data.update(json.loads((OUTPUT / "status.json").read_text()))
    if (OUTPUT / "latest.json").exists():
        rows = json.loads((OUTPUT / "latest.json").read_text())
        now = datetime.now(UTC)
        ages = [
            (now - datetime.fromisoformat(row["ts_exchange"])).total_seconds()
            for row in rows
        ]
        data.update(
            {
                "symbols_on_disk": len(rows),
                "currently_under_60s": sum(age < 60 for age in ages),
                "current_median_quote_age_seconds": (
                    statistics.median(ages) if ages else None
                ),
            }
        )
    data["running"] = data["pid"] is not None
    return data


def main() -> None:
    """Control the local process; never enable AWS or open a network listener."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["start", "status", "stop"])
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    pid = worker_pid()
    if args.action == "start" and pid is None:
        with (OUTPUT / "collector.log").open("a") as log:
            child = subprocess.Popen(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "src.hk.live",
                    "--symbols-file",
                    str(ROOT / "config/hsi_constituents_2026-11-04.csv"),
                    "--output",
                    str(OUTPUT),
                    "--duration-seconds",
                    "0",
                    "--interval-seconds",
                    "5",
                ],
                cwd=ROOT,
                stdout=log,
                stderr=log,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                env=os.environ | {"PYTHONDONTWRITEBYTECODE": "1"},
            )
        write_json(
            PID_FILE,
            {"pid": child.pid, "started_at": datetime.now(UTC).isoformat()},
        )
    elif args.action == "stop" and pid is not None:
        os.kill(pid, signal.SIGTERM)
    print(json.dumps(status(), indent=2))


if __name__ == "__main__":
    main()
