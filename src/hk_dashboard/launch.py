"""Start the integrated site locally without replacing an unrelated server."""

import argparse
import hashlib
import json
from http.server import ThreadingHTTPServer
from urllib.error import URLError
from urllib.request import urlopen

from src.hk_dashboard.paths import ROOT
from src.reddit.dashboard_server import Handler


def identity():
    """Identify this checkout without exposing its filesystem path to the UI."""
    return hashlib.sha256(str(ROOT).encode()).hexdigest()[:20]


def main():
    """Run until Ctrl+C; an occupied port is reused only for this exact checkout."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8879)
    args = parser.parse_args()
    address = f"http://127.0.0.1:{args.port}"
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    except OSError as exc:
        try:
            with urlopen(address + "/api/health?market=hk", timeout=2) as response:
                existing = json.load(response)
            if existing.get("checkout") == identity():
                print(f"Already running: {address}/?market=hk#home", flush=True)
                return
        except (OSError, ValueError, URLError):
            pass
        parser.exit(
            1,
            f"Port {args.port} is occupied; no process was changed. Choose --port ANOTHER_PORT. ({exc})\n",
        )
    print(
        f"Open {address}/?market=hk#home\nKeep this terminal open. Press Ctrl+C to stop.",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
