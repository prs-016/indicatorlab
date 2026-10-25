"""Reddit API (PRAW) client for *future/recent* collection. Historical data comes from Arctic Shift.

Credentials are read from environment variables (optionally loaded from a local,
git-ignored `.env`). Nothing secret is ever logged or printed.

Required: REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT
Optional: REDDIT_USERNAME, REDDIT_PASSWORD (only for user-context auth; read-only
application auth is enough for reading public subreddits).
"""
from __future__ import annotations

import os

from src.reddit import settings
from src.reddit.utils import get_logger, utc_now_iso

log = get_logger("praw_client", "praw.log")

REQUIRED = ["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT"]


def load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(settings.ROOT / ".env", override=False)


def missing_credentials() -> list[str]:
    load_env()
    return [k for k in REQUIRED if not os.environ.get(k)]


def get_reddit():
    import praw

    missing = missing_credentials()
    if missing:
        raise RuntimeError(f"missing environment variables: {', '.join(missing)} (see .env.example / README)")
    kwargs = dict(client_id=os.environ["REDDIT_CLIENT_ID"], client_secret=os.environ["REDDIT_CLIENT_SECRET"],
                  user_agent=os.environ["REDDIT_USER_AGENT"])
    if os.environ.get("REDDIT_USERNAME") and os.environ.get("REDDIT_PASSWORD"):
        kwargs.update(username=os.environ["REDDIT_USERNAME"], password=os.environ["REDDIT_PASSWORD"])
    reddit = praw.Reddit(**kwargs)
    if "username" not in kwargs:
        reddit.read_only = True
    return reddit


def fetch_new(subreddit: str, limit: int = 100) -> list[dict]:
    """Newest submissions in the same shape as the Arctic Shift fields used downstream."""
    reddit = get_reddit()
    out = []
    for s in reddit.subreddit(subreddit).new(limit=limit):
        out.append({"id": s.id, "subreddit": s.subreddit.display_name.lower(), "created_utc": int(s.created_utc),
                    "title": s.title, "selftext": s.selftext, "score": s.score, "num_comments": s.num_comments,
                    "permalink": s.permalink, "retrieved_at_utc": utc_now_iso()})
    log.info("fetched %d posts from r/%s", len(out), subreddit)
    return out
