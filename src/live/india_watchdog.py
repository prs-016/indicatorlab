"""Independent, session-aware India receipt monitoring; no broker credentials."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import UTC, date, datetime
from pathlib import Path

from src.live.india import IST, REGION, TABLE, SessionCalendar, load_nifty100_symbols

NAMESPACE = "IndicatorLab/India"
MAX_AGE_SECONDS = 60
LOGGER = logging.getLogger(__name__)


def _inputs(path, now):
    path = Path(path)
    config = json.loads(path.read_text())
    review = config["review"]
    stamp = datetime.fromisoformat(review["reviewed_at"])
    day = now.astimezone(IST).date()
    if (
        review.get("approved") is not True
        or not review.get("reviewed_by")
        or not review.get("source")
        or stamp.tzinfo is None
        or stamp > now
        or not date.fromisoformat(review["valid_from"])
        <= day
        <= date.fromisoformat(review["valid_until"])
    ):
        raise ValueError("Invalid operational review")
    files = {}
    for key in ["roster", "calendar"]:
        local = Path(config[key]["path"])
        if local.is_absolute() or ".." in local.parts:
            raise ValueError("Invalid operational input path")
        local = path.parent / local
        if hashlib.sha256(local.read_bytes()).hexdigest() != config[key]["sha256"]:
            raise ValueError("Operational checksum mismatch")
        files[key] = local
    return load_nifty100_symbols(files["roster"]), SessionCalendar.from_file(
        files["calendar"]
    )


def evaluate_health(
    now: datetime, calendar: SessionCalendar, symbols, receipts
) -> bool:
    """Return receipt health for every required symbol during explicit sessions.

    now must be timezone-aware; receipts maps names to provider-independent UTC
    receipt strings. Closures return healthy, unknown dates raise, opening 60s
    allow acquisition grace. Old, missing, invalid or future receipts fail health.
    This checks ingestion, not freshness of a stock's last exchange trade.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Aware watchdog time required")
    if not calendar.is_open(now):
        return True
    local = now.astimezone(IST)
    for opening, closing in calendar.sessions[local.date()]:
        if opening <= local.time() < closing:
            opened = datetime.combine(local.date(), opening, IST)
            if (now - opened).total_seconds() < MAX_AGE_SECONDS:
                return True
    for symbol in symbols:
        try:
            stamp = datetime.fromisoformat(receipts[symbol])
            if (
                stamp.tzinfo is None
                or not 0 <= (now - stamp).total_seconds() <= MAX_AGE_SECONDS
            ):
                return False
        except (KeyError, TypeError, ValueError):
            return False
    return True


def check_once(config_path, dynamodb, cloudwatch, *, now: datetime) -> dict:
    """Read reviewed inputs and up to 100 DynamoDB receipts, then publish health.

    Injected low-level AWS clients allow fully offline tests. No broker SDK,
    credentials, quote retrieval, resource creation or table writes are involved.
    Missing configuration/unprocessed keys fail health; errors log types only.
    """
    healthy = False
    try:
        symbols, calendar = _inputs(config_path, now)
        # Avoid table calls outside sessions or during the opening grace.
        if evaluate_health(now, calendar, symbols, {}):
            healthy = True
        else:
            response = dynamodb.batch_get_item(
                RequestItems={
                    TABLE: {
                        "Keys": [{"symbol": {"S": symbol}} for symbol in symbols],
                        "ProjectionExpression": "#s, ts_received",
                        "ExpressionAttributeNames": {"#s": "symbol"},
                        "ConsistentRead": True,
                    }
                }
            )
            rows = response.get("Responses", {}).get(TABLE, [])
            receipts = {}
            for row in rows:
                symbol = row["symbol"]["S"]
                if symbol not in symbols or symbol in receipts:
                    raise ValueError("Unexpected receipt identity")
                receipts[symbol] = row["ts_received"]["S"]
            healthy = not response.get("UnprocessedKeys") and evaluate_health(
                now, calendar, symbols, receipts
            )
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("India watchdog unhealthy: %s", type(exc).__name__)
    cloudwatch.put_metric_data(
        Namespace=NAMESPACE,
        MetricData=[
            {
                "MetricName": "IngestionHealthy",
                "Dimensions": [{"Name": "Service", "Value": TABLE}],
                "Value": int(healthy),
                "Unit": "Count",
                "Timestamp": now,
            }
        ],
    )
    return {"healthy": bool(healthy)}


def handler(_event, _context):
    """Lambda entry point using task-independent role credentials and bounded I/O.

    Reads only INDIA_LIVE_CONFIG, creates standard role-authenticated AWS clients,
    and returns the published health result. Publishing failure raises so missing
    watchdog metrics breach the independent alarm instead of appearing healthy.
    """
    import boto3
    from botocore.config import Config

    session = boto3.session.Session(region_name=REGION)
    config = Config(
        connect_timeout=3,
        read_timeout=5,
        retries={"mode": "standard", "total_max_attempts": 2},
    )
    return check_once(
        os.environ.get("INDIA_LIVE_CONFIG", ""),
        session.client("dynamodb", config=config),
        session.client("cloudwatch", config=config),
        now=datetime.now(UTC),
    )
