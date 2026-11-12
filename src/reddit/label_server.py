"""Local labelling page for the Week 2 hand labels (sentiment ground truth and match precision).

    .venv/bin/python -m src.reddit.label_server --rater joshua            # then open http://localhost:8766
    .venv/bin/python -m src.reddit.label_server --rater james --double-only   # second rater: the 50 overlap posts

Tasks (switch on the page):
  sentiment  data/reddit/validation/sentiment_sample.csv       positive / negative / neutral / skip
  match      data/reddit/validation/match_precision_sample.csv correct / incorrect / unsure

Every click is appended to data/reddit/validation/labels/<task>_<rater>.csv with a UTC timestamp;
the latest label per item wins, so relabelling is safe and nothing is ever overwritten. The page
only shows the current rater's own labels, never another rater's or any scorer's output.
Binds to 127.0.0.1 only.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd

from src.reddit import settings
from src.reddit.utils import utc_now_iso

PAGE = settings.ROOT / "frontend" / "reddit_labeling" / "index.html"
LABEL_DIR = settings.VALIDATION / "labels"
TASKS = {
    "sentiment": {"items": settings.VALIDATION / "sentiment_sample.csv",
                  "labels": ["positive", "negative", "neutral", "skip"]},
    "match": {"items": settings.VALIDATION / "match_precision_sample.csv",
              "labels": ["correct", "incorrect", "unsure"]},
}
LABEL_FIELDS = ["item_id", "post_id", "ticker", "label", "note", "rater", "labeled_at_utc"]
RATER_RE = re.compile(r"^[a-z0-9_-]{1,32}$")
ITEM_FIELDS = ["item_id", "post_id", "ticker", "subreddit", "subreddit_type", "source", "created_utc_iso",
               "title", "body", "url", "matched_text", "match_method", "context", "double", "core"]
_write_lock = threading.Lock()


def label_path(task: str, rater: str) -> Path:
    """CSV that holds one rater's labels for one task."""
    return LABEL_DIR / f"{task}_{rater}.csv"


def latest_labels(task: str, rater: str) -> dict[str, dict]:
    """item_id -> the rater's most recent label row."""
    p = label_path(task, rater)
    if not p.exists():
        return {}
    with open(p, newline="", encoding="utf-8") as f:
        return {r["item_id"]: r for r in csv.DictReader(f)}


def append_label(task: str, rater: str, row: dict) -> dict:
    """Validate and append one label; returns the stored row."""
    if row.get("label") not in TASKS[task]["labels"]:
        raise ValueError(f"label must be one of {TASKS[task]['labels']}")
    out = {k: str(row.get(k, "")) for k in LABEL_FIELDS}
    out.update(rater=rater, labeled_at_utc=utc_now_iso())
    p = label_path(task, rater)
    with _write_lock:
        p.parent.mkdir(parents=True, exist_ok=True)
        new = not p.exists()
        with open(p, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=LABEL_FIELDS)
            if new:
                w.writeheader()
            w.writerow(out)
    return out


def load_items(task: str, double_only: bool) -> list[dict]:
    """Items of a task in labelling order (core items first, then reserves)."""
    p = TASKS[task]["items"]
    if not p.exists():
        return []
    df = pd.read_csv(p, dtype=str, keep_default_na=False)
    if double_only and "double" in df:
        df = df[df["double"] == "True"]
    return df[[c for c in ITEM_FIELDS if c in df.columns]].to_dict(orient="records")


def make_handler(rater: str, double_only: bool):
    """Request handler bound to one rater."""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):   # keep the terminal quiet
            pass

        def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code: int = 200) -> None:
            self._send(code, json.dumps(obj).encode())

        def do_GET(self):
            u = urlparse(self.path)
            if u.path in ("/", "/index.html"):
                return self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            if u.path == "/api/items":
                task = parse_qs(u.query).get("task", ["sentiment"])[0]
                if task not in TASKS:
                    return self._json({"error": f"unknown task {task}"}, 400)
                return self._json({"task": task, "rater": rater, "double_only": double_only,
                                   "choices": TASKS[task]["labels"], "items": load_items(task, double_only),
                                   "labels": latest_labels(task, rater)})
            self._json({"error": "not found"}, 404)

        def do_POST(self):
            if urlparse(self.path).path != "/api/label":
                return self._json({"error": "not found"}, 404)
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                task = body.get("task")
                if task not in TASKS:
                    raise ValueError(f"unknown task {task}")
                self._json(append_label(task, rater, body))
            except (ValueError, json.JSONDecodeError) as e:
                self._json({"error": str(e)}, 400)

    return Handler


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rater", required=True, help="lower-case name, e.g. joshua")
    ap.add_argument("--double-only", action="store_true", help="show only the 50 double-labelled posts")
    ap.add_argument("--port", type=int, default=8766)
    a = ap.parse_args()
    if not RATER_RE.match(a.rater):
        ap.error("rater must be 1-32 characters of a-z, 0-9, _ or -")
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(a.rater, a.double_only))
    print(f"labelling as {a.rater} on http://localhost:{a.port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
