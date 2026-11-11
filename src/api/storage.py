"""Where the dashboard API reads its tables: the S3 bucket on AWS, the repo's data/ folder locally.

Keys follow the bucket layout (Week 3 guide), e.g. processed/wiki_weekly.parquet. INDICATORLAB_DATA
picks the root: empty for data/ in the repo, a folder path, or s3://indicatorlab-data. Tables are
cached in memory for `api.cache_seconds` (config.yaml), so S3 is read at most every 10 minutes.
Live quotes come from the DynamoDB tables on AWS, or from live/<market>.json under a local root.
"""
from __future__ import annotations

import io
import json
import os
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from src import config

LOCAL_ROOT = Path(__file__).resolve().parents[2] / "data"


@dataclass
class Storage:
    """Reads parquet tables and live quotes from a local folder or an s3:// bucket, with a TTL cache."""
    root: str
    ttl: float = 600.0
    _cache: dict = field(default_factory=dict)

    @property
    def is_s3(self) -> bool:
        return self.root.startswith("s3://")

    def _bucket_key(self, key: str) -> tuple[str, str]:
        bucket, _, prefix = self.root[len("s3://"):].partition("/")
        return bucket, f"{prefix.rstrip('/')}/{key}".lstrip("/")

    def _s3(self):
        import boto3
        return boto3.client("s3", region_name=os.getenv("AWS_REGION", "us-west-2"))

    def keys(self, prefix: str) -> list[str]:
        """Table keys under a prefix, e.g. keys("processed/") -> ["processed/wiki_weekly.parquet", ...]."""
        if self.is_s3:
            bucket, full = self._bucket_key(prefix)
            pages = self._s3().get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix=full)
            base = full[: len(full) - len(prefix)]
            return sorted(o["Key"][len(base):] for p in pages for o in p.get("Contents", []))
        root = Path(self.root)
        return sorted(str(p.relative_to(root)) for p in (root / prefix).glob("*") if p.is_file())

    def modified(self, key: str) -> datetime | None:
        """When a table was last written (UTC), or None if it does not exist."""
        if not self.is_s3:
            f = Path(self.root) / key
            return datetime.fromtimestamp(f.stat().st_mtime, tz=UTC) if f.exists() else None
        from botocore.exceptions import ClientError
        bucket, k = self._bucket_key(key)
        try:
            return self._s3().head_object(Bucket=bucket, Key=k)["LastModified"]
        except ClientError:   # missing object: reported as no data
            return None

    def table(self, key: str) -> pd.DataFrame:
        """A parquet table (empty if missing), reread at most every `ttl` seconds."""
        hit = self._cache.get(key)
        if hit and time.monotonic() - hit[0] < self.ttl:
            return hit[1]
        if self.is_s3:
            from botocore.exceptions import ClientError
            bucket, k = self._bucket_key(key)
            try:
                body = self._s3().get_object(Bucket=bucket, Key=k)["Body"].read()
            except ClientError:   # missing object: an empty table
                body = None
            df = pd.read_parquet(io.BytesIO(body)) if body else pd.DataFrame()
        else:
            f = Path(self.root) / key
            df = pd.read_parquet(f) if f.exists() else pd.DataFrame()
        self._cache[key] = (time.monotonic(), df)
        return df

    def live(self, market: str) -> list[dict]:
        """Latest quote per symbol: the DynamoDB table on AWS, live/<market>.json locally."""
        if self.is_s3:
            import boto3
            name = config.load()["api"]["live_tables"][market]
            t = boto3.resource("dynamodb", region_name=os.getenv("AWS_REGION", "us-west-2")).Table(name)
            items, kw = [], {}
            while True:
                page = t.scan(**kw)
                items += page["Items"]
                if "LastEvaluatedKey" not in page:
                    return [{k: float(v) if hasattr(v, "is_finite") else v for k, v in i.items()} for i in items]
                kw["ExclusiveStartKey"] = page["LastEvaluatedKey"]
        f = Path(self.root) / "live" / f"{market}.json"
        return json.loads(f.read_text()) if f.exists() else []


def from_env() -> Storage:
    """The storage INDICATORLAB_DATA points at (data/ in the repo when unset)."""
    return Storage(os.getenv("INDICATORLAB_DATA") or str(LOCAL_ROOT), config.load()["api"]["cache_seconds"])
