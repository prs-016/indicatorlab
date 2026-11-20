# HK attention configuration handoff

Prepared locally on 2026-11-15 for Joshua (Reddit) and James (Wikipedia).
Sending it and agreeing an interface remain external team actions.

`config/hk_week4_handoff.json` is the portable export. It contains 95 dated
current-roster symbols and all 270 evidenced English/Chinese title intervals
from `config/hk_wiki_title_intervals.csv`. The roster is observed 2026-11-04;
the official review is effective 2026-09-07. It is not historical membership.
The Wikipedia benchmark table's separate 85-name discrepancy is not concealed.

One interval (`0006.HK`, `香港電燈`) has no evidenced `valid_from`; the export
marks it unavailable for historical research. Do not infer that date from
retrieval time or sum overlapping aliases as separate articles. Preserve the
page identity, interval ends and corporate-group article scope.

The root config references this full-HSI map. The five named research stocks
remain in `markets.HK.stocks` for the strategy study; they do not represent the
full HSI universe. The live roster is a separate official 95-name operational
snapshot, explicitly disclosed because the Wikipedia table is stale relative
to that reference.

No surveyed market-specific subreddit reached the existing 20-posts/week
threshold for 2024. Keep `general`, `sector`, `product` and `stock` selections
empty; `results/hk/week3/reddit_survey_2024.csv` records observations and errors.
The broad HongKong community is not an investing community. Xiaomi's failed
request is unavailable, not zero. Joshua can agree a broader scope later; this
handoff does not invent qualifying HK sources or authorize deployment.

Research reads the root `holdout_start` (2026-11-01) and
`spike.baseline_weeks` (8). Monday-labelled complete weeks become tradable
only on the first following market session. The last fully completed
Monday–Sunday attention week before the cutoff begins 2026-10-19.

Suggested team message (not sent):

> The HK config handoff contains the full 95-name current reference and 270
> dated English/Chinese Wikipedia intervals. One undated interval is excluded
> from historical research. No surveyed market-specific subreddit passes the
> current activity rule, so the HK subreddit lists remain empty with evidence.
> Please confirm the config contract before wiring the hourly/daily pipelines.
