"""Export the Reddit dashboard (frontend/reddit_dashboard + dashboard_server) as a static site for AWS.

The local dashboard is a Python server; hosted on S3 + CloudFront it must be plain files. This writes
every read-only endpoint the page calls as JSON (`api/<name>.json`, `api/weekly/<TICKER>.json`,
`api/strategy_run/<run>.json`), copies the charts, and rewrites the page to read those files. The two
buttons that rerun the pipeline only work locally, so the hosted copy shows them disabled.
Sentiment is not on this page yet; it is added when the FinBERT rescore is finished.

    .venv/bin/python -m src.reddit.dashboard_export          # -> build/reddit_dashboard/
    infra/dashboard/deploy.sh                                # export, upload, invalidate the CDN
"""
from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

from src.reddit import dashboard_server as ds
from src.reddit import settings
from src.reddit.utils import get_logger

log = get_logger("dashboard_export", "pipeline.log")

OUT = settings.ROOT / "build" / "reddit_dashboard"
LATEST_RUN = "latest"
CSV_ENDPOINTS = {"coverage": settings.TABLES / "subreddit_coverage.csv",
                 "strategy": settings.STRATEGY_LOGS / "alpha101_comparison.csv",
                 "events": settings.TABLES / "apple_event_study.csv",
                 "spikes": settings.TABLES / "top_chatter_spikes.csv",
                 "matches": settings.TABLES / "match_method_summary.csv",
                 "strategy_log": settings.STRATEGY_LOGS / "strategy_log.csv"}
LOCAL_ONLY = {"running": False, "started": None, "finished": None, "error": None, "step": None}

# Exact snippets of frontend/reddit_dashboard/index.html and their static replacements. Each must be
# found, so a change to the page fails the export instead of silently shipping a broken site.
STATIC_GET = """const get = (u) => {
  const [p, q] = u.split("?"), k = new URLSearchParams(q || "");
  let f = p.replace(/^\\/api\\//, "api/");
  if (p === "/api/weekly") f = `api/weekly/${k.get("ticker")}`;
  else if (p === "/api/strategy_run") f = `api/strategy_run/${k.get("run_id") || "latest"}`;
  return fetch(f + ".json", { cache: "no-store" }).then(r => r.json());
};"""
REWRITES = [
    ('const get = (u) => fetch(u, { cache: "no-store" }).then(r => r.json());', STATIC_GET),
    ('"/charts/aapl_chatter_vs_price.png"', '"charts/aapl_chatter_vs_price.png"'),
    ('"/charts/aapl_event_windows.png"', '"charts/aapl_event_windows.png"'),
    ('$("runStrategies").disabled = s.running;', '$("runStrategies").disabled = true;'),
    ("btn.disabled = s.running;", "btn.disabled = true;"),
    ('"Reruns posts → matching → weekly → event study → charts"',
     '"Runs on a laptop only (python -m src.reddit.dashboard_server); this hosted copy is a snapshot"'),
    ('"Refreshes signals from collected data, then backtests and logs S1–S5 + benchmark"',
     '"Runs on a laptop only; this hosted copy shows the logged runs"'),
]


def static_page(html: str, as_of: str) -> str:
    """The dashboard page rewritten to read static JSON, with a snapshot note under <body>."""
    for old, new in REWRITES:
        if old not in html:
            raise ValueError(f"dashboard page changed; update REWRITES (missing: {old[:60]!r})")
        html = html.replace(old, new)
    note = ('<div style="padding:6px 16px;font-size:13px;background:var(--surface-2,#eee);'
            f'color:var(--text-secondary,#444)">Hosted snapshot · data as of {as_of} · sentiment coming soon</div>')
    return html.replace("<body>", "<body>\n" + note, 1)


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, default=str))


def export(out: Path = OUT) -> list[Path]:
    """Write the static site to `out` (replacing it) and return the files written."""
    if out.exists():
        shutil.rmtree(out)
    api = out / "api"
    _write(api / "status.json", ds.status())
    for name, path in CSV_ENDPOINTS.items():
        _write(api / f"{name}.json", ds._csv(path))
    for ticker in settings.TICKERS:
        _write(api / "weekly" / f"{ticker}.json", ds.weekly(ticker))
    latest = ds.strategy_run("")
    _write(api / "strategy_run" / f"{LATEST_RUN}.json", latest)
    for run_id in latest.get("runs", []):
        _write(api / "strategy_run" / f"{run_id}.json", ds.strategy_run(run_id))
    _write(api / "rebuild.json", LOCAL_ONLY)
    _write(api / "run_strategies.json", LOCAL_ONLY)
    (out / "charts").mkdir(parents=True, exist_ok=True)
    for png in settings.CHARTS.glob("*.png"):
        shutil.copy2(png, out / "charts" / png.name)
    as_of = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    (out / "index.html").write_text(static_page((settings.DASHBOARD / "index.html").read_text(), as_of))
    files = sorted(p for p in out.rglob("*") if p.is_file())
    log.info("static dashboard: %d files in %s", len(files), out)
    return files


if __name__ == "__main__":
    export()
    print(f"wrote {OUT}")
