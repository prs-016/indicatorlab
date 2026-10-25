"""Offline tests for the collector's pagination and retry logic using a fake API."""
from datetime import date

import pytest

from src.reddit.arctic_client import ApiResult, ArcticShiftClient, ArcticShiftError
from src.reddit.collect_reddit import collect_day
from src.reddit.utils import day_bounds_epoch

DAY = date(2024, 1, 2)
START, END = day_bounds_epoch(DAY)


class FakeClient:
    """Mimics the API: sort=asc, exclusive `after`, exclusive `before`, fixed page size."""

    base_url = "fake"

    def __init__(self, posts, page_size=3, fail_at_call=None):
        self.posts = sorted(posts, key=lambda p: p["created_utc"])
        self.page_size = page_size
        self.calls = 0
        self.fail_at_call = fail_at_call

    def get(self, path, params):
        self.calls += 1
        if self.fail_at_call == self.calls:
            raise ArcticShiftError("boom", [{"attempt": 1}])
        sel = [p for p in self.posts if params["after"] < p["created_utc"] < params["before"]]
        return ApiResult("url", dict(params), 200, "t", {"data": sel[: self.page_size]}, [{"attempt": 1}])


def mk(i, ts):
    return {"id": f"p{i}", "created_utc": ts}


def test_pages_until_no_new_ids_and_keeps_ties():
    # Posts 3,4 share a timestamp across a page boundary; an exclusive after=last_ts would lose p4.
    ts = [START + 1, START + 2, START + 10, START + 10, START + 20, START + 30, START + 40]
    posts = [mk(i, t) for i, t in enumerate(ts)]
    r = collect_day(FakeClient(posts, page_size=3), "x", DAY, min_page_size=3)
    assert r["status"] == "complete"
    assert r["n_posts_unique"] == len(posts)


def test_excludes_posts_outside_day():
    posts = [mk(0, START - 1), mk(1, START + 5), mk(2, END)]
    r = collect_day(FakeClient(posts), "x", DAY)
    assert r["n_posts_unique"] == 1


def test_empty_day_is_complete_with_zero_posts():
    r = collect_day(FakeClient([]), "x", DAY)
    assert r["status"] == "complete" and r["n_posts_unique"] == 0 and r["n_pages"] == 1


def test_failure_is_failed_not_zero():
    posts = [mk(i, START + i * 10) for i in range(1, 10)]
    r = collect_day(FakeClient(posts, page_size=3, fail_at_call=2), "x", DAY, min_page_size=3)
    assert r["status"] == "failed"
    assert r["errors"]


def test_short_page_ends_day_without_extra_request():
    posts = [mk(i, START + i * 10) for i in range(1, 6)]
    fake = FakeClient(posts, page_size=10)
    r = collect_day(fake, "x", DAY, min_page_size=10)
    assert r["status"] == "complete" and r["n_posts_unique"] == 5 and fake.calls == 1


def test_tie_overflow_marked_partial():
    posts = [mk(i, START + 5) for i in range(5)]
    r = collect_day(FakeClient(posts, page_size=3), "x", DAY, min_page_size=3)
    assert r["status"] == "partial"


class _Resp:
    def __init__(self, status, payload, text=None):
        self.status_code = status
        self._p = payload
        self.text = text or str(payload)
        self.headers = {}

    def json(self):
        return self._p


class _Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.headers = {}

    def get(self, url, params=None, timeout=None):
        return self.responses.pop(0)


def test_client_retries_rate_limit_body_then_succeeds():
    rl = {"data": None, "error": "Timeout. Maybe slow down a bit"}
    sess = _Session([_Resp(200, rl), _Resp(422, rl), _Resp(200, {"data": [{"id": "a"}]})])
    c = ArcticShiftClient(session=sess, min_interval=0, sleep=lambda s: None)
    res = c.get("posts/search", {"subreddit": "x"})
    assert res.body["data"] == [{"id": "a"}] and len(res.attempts) == 3


def test_client_gives_up_and_raises():
    rl = {"data": None, "error": "Timeout. Maybe slow down a bit"}
    sess = _Session([_Resp(200, rl)] * 3)
    c = ArcticShiftClient(session=sess, min_interval=0, max_attempts=3, sleep=lambda s: None)
    with pytest.raises(ArcticShiftError):
        c.get("posts/search", {"subreddit": "x"})


def test_server_error_waits_10_to_30s_and_retries_3_times():
    err = {"data": None, "error": "Internal server error"}
    sess = _Session([_Resp(200, err)] * 4)
    waits = []
    c = ArcticShiftClient(session=sess, min_interval=0, sleep=waits.append)
    with pytest.raises(ArcticShiftError) as e:
        c.get("posts/search", {"subreddit": "x"})
    assert len(e.value.attempts) == 4          # 1 try + 3 retries
    assert len(waits) == 3 and all(10 <= w <= 30 for w in waits)
