"""Check that Reddit API credentials work: prints the 5 newest r/stocks titles.

Usage:  python -m src.reddit.check_praw_connection   (from the repo root)
Exit codes: 0 ok, 2 credentials missing, 1 connection/auth failure. Secrets are never printed.
"""
from __future__ import annotations

import sys

from src.reddit import settings
from src.reddit.praw_client import fetch_new, missing_credentials


def main() -> int:
    missing = missing_credentials()
    if missing:
        print("Reddit credentials not configured. Missing: " + ", ".join(missing))
        print("Copy .env.example to .env and fill it in (see README 'Reddit API (PRAW) setup').")
        return 2
    try:
        posts = fetch_new(settings.SUBREDDITS[0], limit=5)
    except Exception as e:  # noqa: BLE001 - report any auth/network failure without secrets
        msg = str(e)
        print(f"Connection failed: {type(e).__name__}: {msg[:200]}")
        return 1
    print(f"OK - authenticated, fetched {len(posts)} posts from r/{settings.SUBREDDITS[0]}:")
    for p in posts:
        print(f"  {p['id']}  {p['title'][:90]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
