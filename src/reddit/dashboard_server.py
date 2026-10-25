"""Local dashboard for the project's outputs (stdlib HTTP server + pandas).

    .venv/bin/python -m src.reddit.dashboard_server --port 8765   # from the repo root
    open http://localhost:8765

Read-only views of the files the pipeline writes, plus POST /api/rebuild which reruns
the analysis steps (build_posts -> match -> weekly -> event study -> charts) on whatever
days have been collected so far. Collection itself is never started from here.
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd

from src.reddit import settings
from src.reddit.collect_reddit import load_manifest_latest
from src.reddit.utils import daterange

DASH = settings.DASHBOARD
REBUILD_STEPS = ["build_posts", "match_tickers", "weekly_metrics", "apple_event_study", "visualization"]
strategy_state = {"running": False, "started": None, "finished": None, "error": None}
rebuild_state = {"running": False, "step": None, "started": None, "finished": None, "error": None}
_lock = threading.Lock()


def _mtime(p: Path):
    return datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC") if p.exists() else None


def _csv(p: Path, **kw):
    if not p.exists():
        return {"rows": [], "updated": None}
    df = pd.read_csv(p, **kw)
    return {"rows": json.loads(df.to_json(orient="records")), "updated": _mtime(p)}


def status():
    end = settings.default_end_date()
    days = [d.isoformat() for d in daterange(settings.START_DATE, end)]
    latest = load_manifest_latest()
    subs = []
    for s in settings.SUBREDDITS:
        st = [latest.get((s, d), {}).get("status", "missing") for d in days]
        done = [d for d in days if latest.get((s, d), {}).get("status") == "complete"]
        subs.append({
            "subreddit": s, "expected": len(days), "complete": st.count("complete"), "partial": st.count("partial"),
            "failed": st.count("failed"), "missing": st.count("missing"),
            "posts": sum(int(latest[(s, d)]["n_posts"]) for d in done),
            "contiguous_through": next((days[i - 1] for i, x in enumerate(st) if x != "complete"), days[-1])
                                  if st and st[0] == "complete" else None,
            "problem_dates": [d for d, x in zip(days, st) if x in ("failed", "partial")][:20],
        })
    # throughput over the last 30 minutes of manifest rows -> ETA
    eta = None
    rows = [v for v in latest.values() if v.get("last_retrieved_utc")]
    if rows:
        ts = pd.to_datetime(pd.Series([r["last_retrieved_utc"] for r in rows]), utc=True, errors="coerce").dropna()
        now = pd.Timestamp.now(tz="UTC")
        recent = ts[ts > now - pd.Timedelta(minutes=30)]
        remaining = sum(x["expected"] - x["complete"] for x in subs)
        if len(recent) > 5:
            per_min = len(recent) / max((now - recent.min()).total_seconds() / 60, 1)
            eta = {"per_minute": round(per_min, 1), "remaining_pairs": remaining,
                   "eta_utc": (now + pd.Timedelta(minutes=remaining / per_min)).strftime("%Y-%m-%d %H:%M UTC"),
                   "active": bool((now - ts.max()).total_seconds() < 300)}
        else:
            eta = {"per_minute": 0, "remaining_pairs": remaining, "eta_utc": None,
                   "active": bool(len(ts) and (now - ts.max()).total_seconds() < 300)}
    log = settings.LOGS / "collect_reddit.log"
    tail = log.read_text(errors="replace").splitlines()[-6:] if log.exists() else []
    return {"range": [days[0], days[-1]], "subreddits": subs, "eta": eta, "log_tail": tail,
            "processed_updated": _mtime(settings.PROCESSED / "reddit_weekly.csv")}


def weekly(ticker: str):
    p = settings.PROCESSED / "reddit_weekly.csv"
    if not p.exists():
        return {"rows": []}
    df = pd.read_csv(p)
    df = df[df["ticker"] == ticker][["week_start", "posts", "posts_observed", "posts_median_4w", "posts_spike_ratio",
                                     "posts_spike_flag", "comments", "upvotes", "coverage_complete"]]
    return {"rows": json.loads(df.to_json(orient="records")), "updated": _mtime(p)}


def _run_rebuild():
    try:
        for step in REBUILD_STEPS:
            rebuild_state["step"] = step
            p = subprocess.run([sys.executable, "-m", f"src.reddit.{step}"], cwd=settings.ROOT,
                               capture_output=True, text=True)
            if p.returncode != 0:
                rebuild_state["error"] = f"{step} failed: {(p.stderr or p.stdout)[-600:]}"
                return
        rebuild_state["error"] = None
    finally:
        rebuild_state.update(running=False, step=None, finished=time.strftime("%H:%M:%S UTC", time.gmtime()))


def strategy_run(run_id: str):
    """Weekly net returns of one logged Reddit backtest run (cumulative growth of $1)."""
    base = settings.STRATEGY_LOGS / "runs"
    runs = sorted([d.name for d in base.glob("reddit_*") if d.is_dir()]) if base.exists() else []
    if not runs:
        return {"runs": [], "series": {}}
    run_id = run_id if run_id in runs else runs[-1]
    series = {}
    for f in sorted((base / run_id).glob("*_weekly.csv")):
        df = pd.read_csv(f)
        sid = f.name.split("_")[0]
        series[sid] = {"name": f.name[len(sid) + 1:-len("_weekly.csv")], "weeks": df["signal_week"].tolist(),
                       "growth": (1 + df["net"]).cumprod().round(5).tolist(),
                       "net": df["net"].round(5).tolist(), "positions": df["positions"].fillna("cash").tolist()}
    return {"runs": runs, "run_id": run_id, "series": series}


def _run_strategies():
    """Refresh the weekly signals from collected data, then run and log all five strategies."""
    try:
        for step in ["build_posts", "match_tickers", "weekly_metrics", "backtest_strategies"]:
            args = [sys.executable, "-m", f"src.reddit.{step}"] + (["--note", "run from dashboard"] if step.startswith("backtest") else [])
            p = subprocess.run(args, cwd=settings.ROOT, capture_output=True, text=True)
            if p.returncode != 0:
                strategy_state["error"] = f"{step} failed: {(p.stderr or p.stdout)[-600:]}"
                return
    finally:
        strategy_state.update(running=False, finished=time.strftime("%H:%M:%S UTC", time.gmtime()))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body: bytes, ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, default=str).encode())

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            if u.path in ("/", "/index.html"):
                return self._send(200, (DASH / "index.html").read_bytes(), "text/html; charset=utf-8")
            if u.path == "/api/status":
                return self._json(status())
            if u.path == "/api/coverage":
                return self._json(_csv(settings.TABLES / "subreddit_coverage.csv"))
            if u.path == "/api/strategy":
                return self._json(_csv(settings.STRATEGY_LOGS / "alpha101_comparison.csv"))
            if u.path == "/api/events":
                return self._json(_csv(settings.TABLES / "apple_event_study.csv"))
            if u.path == "/api/spikes":
                return self._json(_csv(settings.TABLES / "top_chatter_spikes.csv"))
            if u.path == "/api/matches":
                return self._json(_csv(settings.TABLES / "match_method_summary.csv"))
            if u.path == "/api/weekly":
                return self._json(weekly(q.get("ticker", [next(iter(settings.TICKERS))])[0].upper()))
            if u.path == "/api/rebuild":
                return self._json(rebuild_state)
            if u.path == "/api/strategy_log":
                return self._json(_csv(settings.STRATEGY_LOGS / "strategy_log.csv"))
            if u.path == "/api/strategy_run":
                return self._json(strategy_run(q.get("run_id", [""])[0]))
            if u.path == "/api/run_strategies":
                return self._json(strategy_state)
            if u.path.startswith("/charts/"):
                f = (settings.CHARTS / Path(u.path).name)
                if f.exists() and f.parent == settings.CHARTS:
                    return self._send(200, f.read_bytes(), mimetypes.guess_type(f.name)[0] or "application/octet-stream")
            self._json({"error": "not found"}, 404)
        except Exception as e:  # noqa: BLE001 - surface errors to the page
            self._json({"error": f"{type(e).__name__}: {e}"}, 500)

    def do_POST(self):
        if urlparse(self.path).path == "/api/run_strategies":
            with _lock:
                if strategy_state["running"] or rebuild_state["running"]:
                    return self._json(strategy_state, 409)
                strategy_state.update(running=True, error=None, finished=None,
                                      started=time.strftime("%H:%M:%S UTC", time.gmtime()))
                threading.Thread(target=_run_strategies, daemon=True).start()
            return self._json(strategy_state, 202)
        if urlparse(self.path).path != "/api/rebuild":
            return self._json({"error": "not found"}, 404)
        with _lock:
            if rebuild_state["running"]:
                return self._json(rebuild_state, 409)
            rebuild_state.update(running=True, step=REBUILD_STEPS[0], error=None,
                                 started=time.strftime("%H:%M:%S UTC", time.gmtime()), finished=None)
            threading.Thread(target=_run_rebuild, daemon=True).start()
        self._json(rebuild_state, 202)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args()
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    print(f"dashboard on http://localhost:{a.port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
