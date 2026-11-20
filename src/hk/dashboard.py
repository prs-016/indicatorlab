"""Serve the HK display locally or build its static assets for S3/CloudFront."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend/live_markets"
ASSETS = ("index.html", "styles.css", "app.mjs", "model.mjs", "config.js")


def public_config(api_base_url: str | None = None) -> str:
    """Serialize the public API origin; browser assets never receive AWS/API secrets."""
    base = (
        api_base_url
        if api_base_url is not None
        else os.getenv("INDICATORLAB_API_BASE_URL", "")
    ).rstrip("/")
    if base:
        parsed = urlparse(base)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "API base must be a plain http(s) URL without credentials/query/fragment"
            )
    return (
        "window.INDICATORLAB_CONFIG = Object.freeze("
        + json.dumps(
            {
                "apiBaseUrl": base,
                "refreshIntervalMs": 5000,
                "attentionIntervalMs": 300000,
                "attentionEnabled": os.getenv(
                    "INDICATORLAB_ATTENTION_ENABLED", ""
                ).lower()
                in {"1", "true"},
            }
        )
        + ");\n"
    )


def build(output: Path, api_base_url: str | None = None) -> None:
    """Copy a small deterministic asset allowlist; no prices or credentials enter a build."""
    output = output.expanduser().resolve()
    if output == FRONTEND.resolve() or FRONTEND.resolve().is_relative_to(output):
        raise ValueError("Build into a separate output directory")
    config = public_config(api_base_url)
    output.mkdir(parents=True, exist_ok=True)
    for name in ASSETS:
        if name != "config.js":
            shutil.copy2(FRONTEND / name, output / name)
    (output / "config.js").write_text(config, encoding="utf-8")


def main() -> None:
    """Use existing local quotes; this command never starts a second polling worker."""
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    server = sub.add_parser(
        "serve", help="Serve the frontend and read-only API together"
    )
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8765)
    server.add_argument("--data-dir", type=Path)
    server.add_argument("--instance-id", help=argparse.SUPPRESS)
    starter = sub.add_parser(
        "start", help="Start or reuse the local dashboard in the background"
    )
    starter.add_argument("--port", type=int, default=8765)
    starter.add_argument(
        "--with-feed",
        action="store_true",
        help="Ensure the existing local collector is running",
    )
    starter.add_argument("--open-browser", action="store_true")
    inspect = sub.add_parser("status", help="Check the local dashboard API")
    inspect.add_argument("--port", type=int, default=8765)
    sub.add_parser("stop", help="Stop only the dashboard API")
    assets = sub.add_parser("build", help="Build static files for later AWS hosting")
    assets.add_argument("--output", type=Path, default=FRONTEND / "dist")
    assets.add_argument("--api-base-url")
    args = parser.parse_args()
    if args.action in {"start", "status", "stop"}:
        from src.hk import dashboard_runtime

        try:
            if args.action == "start":
                result = dashboard_runtime.start(
                    port=args.port, with_feed=args.with_feed
                )
                print(f"Dashboard ready: {result['url']}")
                print("The local API keeps running after this window closes.")
                print("Stop with: python -B -m src.hk.dashboard stop")
                if args.open_browser:
                    import webbrowser

                    webbrowser.open(result["url"])
            elif args.action == "status":
                result = dashboard_runtime.status(port=args.port)
            else:
                result = dashboard_runtime.stop()
            print(json.dumps(result, indent=2))
        except (OSError, RuntimeError, ValueError, TimeoutError) as exc:
            parser.exit(1, f"{exc}\n")
        return
    if args.action == "build":
        build(args.output, args.api_base_url)
        print(f"Static frontend built in {args.output.resolve()}")
        return
    if args.data_dir:
        os.environ["INDICATORLAB_LIVE_HK_DIR"] = str(
            args.data_dir.expanduser().resolve()
        )
    if args.instance_id:
        os.environ["INDICATORLAB_DASHBOARD_INSTANCE"] = args.instance_id
    import uvicorn

    uvicorn.run("src.api.main:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
