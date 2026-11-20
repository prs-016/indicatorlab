# Shared live-feed code, AWS deferred

New opt-in layout: `src/live/base.py` and `src/live/hk.py`. The existing
`src.hk.local_service` worker in the separate `indicatorlab-clean` checkout was
not changed, stopped or restarted. Do not launch both on the same output path.

After installing the repository dependencies, run explicitly from the root:

```bash
python -m src.live.hk --config config.yaml --output data/live_hk_week4
```

Without `--aws`, this writes local latest JSON and complete minute Parquet
snapshots. Memory is bounded by the configured symbol list; minute files grow
by date, while the latest file is replaced. No new collector was started during
this work. The existing November 12 ten-minute observation remains the empirical
feed audit; the new loop has offline tests, not a new session acceptance test.

Tencent batches are capped conservatively at 100 names; this was tested with
the 95-name operational roster, not established as the provider's maximum.
Requests time out after three seconds. A malformed or failed symbol is isolated;
valid partial polls update retained state. Failed writes retain pending rows.
The retry sequence is 1, 2, 4, 8, 16, 30 seconds, capped at 30. Calendar gating
waits until the next continuous session, including the lunch pause, holidays,
half-days and the explicitly evidenced historical weather exceptions.

The source preserves seven fields: symbol, price, change_pct, volume,
ts_exchange, ts_received, source. Named Tencent field constants document the
wire positions. Quantity remains provider-native; the older closing-price
Google comparison supports that sample, not every intraday record's accuracy.

With `--aws`, injected boto3 clients use `batch_writer()` upserts keyed by symbol,
all retained quotes in `raw/live/hk/date=YYYY-MM-DD/HHMM.parquet` (UTC partitions),
and the minute `LastUpdateAgeSeconds` metric. Oldest receipt age and never-seen
configured symbols reveal partial-universe staleness. Per-poll logs retain
provider last-trade ages. These are distinct: publication delay is not proven by
last-trade age, and polling every five seconds does not guarantee a new trade.

The prior 120-poll audit reports median last-trade age 10.63 seconds, p95 86.58
seconds and 90.95% under one minute. See `results/hk/week3/live_delay_summary.json`.
No fresh universal subminute promise follows from it.

AWS deployment, ECS/Scheduler configuration, session-aware alarms, S3/DynamoDB
acceptance and James's `/live/hk` integration remain explicitly deferred by the
user. The older `infra/hk_live` is historical preparation, not proof of a live
Week 4 shared stack. Do not deploy it as if those acceptance criteria passed.
