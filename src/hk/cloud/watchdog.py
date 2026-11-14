"""Independent ingestion watchdog, gated by the actual HKEX session calendar."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from src.hk.calendar import market_state


def health(now: datetime, exchange_state: str, received_times: list[str]) -> dict:
    """Evaluate receipt freshness, with closed-session and reopening grace handling."""
    if now.tzinfo is None:
        raise ValueError("Timezone-aware time required")
    local = now.astimezone(ZoneInfo("Asia/Hong_Kong"))
    grace = (local.hour == 9 and local.minute == 30) or (
        local.hour == 13 and local.minute == 0
    )
    if exchange_state != "open" or grace:
        return {
            "healthy": True,
            "state": exchange_state,
            "reason": "closed_or_opening_grace",
            "age_seconds": None,
        }
    stamps = []
    for value in received_times:
        try:
            stamp = datetime.fromisoformat(value)
            if stamp.tzinfo is not None and stamp <= now:
                stamps.append(stamp)
        except (ValueError, TypeError):
            continue
    age = (now - max(stamps)).total_seconds() if stamps else None
    return {
        "healthy": age is not None and age <= 60,
        "state": exchange_state,
        "reason": (
            "recent_receipt"
            if age is not None and age <= 60
            else "no_quote_within_60_seconds"
        ),
        "age_seconds": age,
    }


def handler(_event, _context):
    """Check DynamoDB and publish a health metric; no trade or user message is sent."""
    import boto3

    now = datetime.now(UTC)
    state = market_state(now)
    table = boto3.resource("dynamodb", region_name="us-west-2").Table(
        os.getenv("HK_QUOTE_TABLE", "indicatorlab-live-hk")
    )
    stamps = []
    if state == "open":
        response = table.scan(ProjectionExpression="ts_received")
        stamps.extend(
            item["ts_received"]
            for item in response.get("Items", [])
            if "ts_received" in item
        )
        while response.get("LastEvaluatedKey"):
            response = table.scan(
                ProjectionExpression="ts_received",
                ExclusiveStartKey=response["LastEvaluatedKey"],
            )
            stamps.extend(
                item["ts_received"]
                for item in response.get("Items", [])
                if "ts_received" in item
            )
    result = health(now, state, stamps)
    boto3.client("cloudwatch", region_name="us-west-2").put_metric_data(
        Namespace="IndicatorLab",
        MetricData=[
            {
                "MetricName": "HKIngestionHealthy",
                "Value": float(result["healthy"]),
                "Unit": "Count",
                "Timestamp": now,
            }
        ],
    )
    return result
