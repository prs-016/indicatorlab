"""Explicit India live-service bootstrap; default invocation only validates files."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import signal
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from threading import Event

from src.live.dhan import DhanQuoteProvider
from src.live.india import (
    BUCKET,
    IST,
    REGION,
    TABLE,
    DynamoLatestStore,
    IndiaLiveService,
    S3MinuteStore,
    SessionCalendar,
    load_nifty100_symbols,
)

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class IndiaRuntime:
    """Validated local inputs, inactive provider and declared review expiry.

    Fields contain no AWS credentials. provider holds environment broker secrets;
    exclude it from the representation. start_date/valid_until bound the reviewed
    operational calendar, not any historical research or holdout period.
    """

    symbols: tuple[str, ...]
    calendar: SessionCalendar
    start_date: date
    valid_until: date
    interval: int
    fallback_authorized: bool
    provider: DhanQuoteProvider = field(repr=False)


def _utc_now():
    return datetime.now(UTC)


def prepare_runtime(
    config_path: str | Path, *, environ=None, clock=_utc_now
) -> IndiaRuntime:
    """Validate reviewed local inputs and credentials without AWS/quote requests.

    config_path is a local JSON referencing roster, instruments and calendar files
    by relative paths and SHA-256 hashes. A dated review attests their operational
    identity/session verification; hashes prove binding, not broker correctness.
    environ and clock permit offline tests. Returns an inactive runtime or raises.
    """
    path = Path(config_path)
    config = json.loads(path.read_text())
    review = config["review"]
    if not isinstance(review, Mapping) or review.get("approved") is not True:
        raise ValueError("Operational input review approval required")
    if not all(
        isinstance(review.get(k), str) and review[k].strip()
        for k in ["reviewed_by", "source"]
    ):
        raise ValueError("Operational review identity and evidence source required")
    now = clock()
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Aware operational clock required")
    reviewed = datetime.fromisoformat(review["reviewed_at"])
    if reviewed.tzinfo is None or reviewed.utcoffset() is None or reviewed > now:
        raise ValueError("Valid dated operational review required")
    start = date.fromisoformat(review["valid_from"])
    end = date.fromisoformat(review["valid_until"])
    today = now.astimezone(IST).date()
    if not start <= today <= end:
        raise ValueError("Operational review is not valid for current India date")
    files = {}
    for key in ["roster", "instruments", "calendar"]:
        spec = config[key]
        local = Path(spec["path"])
        if local.is_absolute() or ".." in local.parts:
            raise ValueError("Runtime input paths must be relative to configuration")
        local = path.parent / local
        if hashlib.sha256(local.read_bytes()).hexdigest() != spec["sha256"]:
            raise ValueError("Operational input checksum mismatch")
        files[key] = local
    symbols = load_nifty100_symbols(files["roster"])
    instruments = json.loads(files["instruments"].read_text())
    if not isinstance(instruments, Mapping) or set(instruments) != set(symbols):
        raise ValueError(
            "Instrument mappings must exactly match the reviewed 100-stock roster"
        )
    calendar = SessionCalendar.from_file(files["calendar"])
    # Require explicit session/closure entries throughout the approved window.
    # Check again at runtime: unknown or expired dates never contact the broker.
    if any(
        date.fromordinal(day) not in calendar.sessions
        for day in range(start.toordinal(), end.toordinal() + 1)
    ):
        raise ValueError("Reviewed operational calendar has uncovered dates")
    interval = config.get("poll_interval_seconds", 5)
    fallback = config.get("fallback_authorized", False)
    if (
        type(interval) is not int
        or interval not in (5, 60)
        or type(fallback) is not bool
        or (interval == 60 and not fallback)
    ):
        raise ValueError("Use five seconds or explicitly approved 60-second fallback")
    provider = DhanQuoteProvider.from_env(instruments, environ=environ, clock=clock)
    # Detect changed files during parsing as well as before it.
    for key, local in files.items():
        if hashlib.sha256(local.read_bytes()).hexdigest() != config[key]["sha256"]:
            raise ValueError("Operational inputs changed during validation")
    return IndiaRuntime(symbols, calendar, start, end, interval, fallback, provider)


class _ReviewedCalendar:
    def __init__(self, runtime):
        self.runtime = runtime
        self.source = runtime.calendar.source

    def is_open(self, now):
        day = now.astimezone(IST).date()
        if not self.runtime.start_date <= day <= self.runtime.valid_until:
            raise ValueError("Operational input review expired")
        return self.runtime.calendar.is_open(now)


def aws_client_factory():
    """Return a bounded-timeout AWS client factory, only after explicit activation.

    Uses boto3's standard credential chain (including ECS task roles). No static
    AWS credentials, SSM reads, resource provisioning or endpoint overrides occur.
    Missing deployment dependencies raise a sanitized actionable error.
    """
    try:
        import boto3
        from botocore.config import Config
    except ImportError:
        raise RuntimeError(
            "Install declared boto3 dependency before AWS execution"
        ) from None
    session = boto3.session.Session(region_name=REGION)
    config = Config(
        connect_timeout=3,
        read_timeout=5,
        retries={"mode": "standard", "total_max_attempts": 3},
    )
    return lambda service: session.client(service, region_name=REGION, config=config)


def build_service(
    runtime: IndiaRuntime, *, client_factory=None, clock=_utc_now
) -> IndiaLiveService:
    """Wire validated runtime to existing AWS sinks without creating resources.

    client_factory(service_name) is injectable for offline tests. Otherwise lazy
    boto3 clients use us-west-2 and task-role authentication. Returns an unstarted
    service; build_service alone never fetches quotes or writes market records.
    """
    factory = client_factory if client_factory is not None else aws_client_factory()
    latest = DynamoLatestStore(factory("dynamodb"), table=TABLE)
    snapshots = S3MinuteStore(factory("s3"), bucket=BUCKET)
    return IndiaLiveService(
        runtime.symbols,
        runtime.provider,
        _ReviewedCalendar(runtime),
        latest,
        snapshots,
        poll_interval_seconds=runtime.interval,
        fallback_authorized=runtime.fallback_authorized,
        clock=clock,
    )


def main(argv=None) -> int:
    """Validate by default; --run explicitly starts the configured AWS collector.

    Reads INDIA_LIVE_CONFIG and broker environment credentials. SIGTERM/SIGINT
    request graceful service shutdown and final snapshot flush. Returns 0 on
    successful validation/run, 1 on sanitized configuration/runtime failures.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run",
        action="store_true",
        help="Explicitly enable broker requests and AWS writes",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    try:
        config = os.environ.get("INDIA_LIVE_CONFIG")
        if not config:
            raise ValueError("INDIA_LIVE_CONFIG is required")
        runtime = prepare_runtime(config)
        if not args.run:
            LOGGER.info(
                "India live configuration validated; collection remains inactive"
            )
            return 0
        service = build_service(runtime)
        stop = Event()
        previous = {}
        try:
            for sig in (signal.SIGTERM, signal.SIGINT):
                previous[sig] = signal.signal(sig, lambda *_: stop.set())
            service.run(stop_event=stop)
        finally:
            for sig, handler in previous.items():
                signal.signal(sig, handler)
        return 0
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("India live startup/run refused: %s", type(exc).__name__)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
