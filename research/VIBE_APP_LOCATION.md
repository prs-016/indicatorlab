# Legacy Vibe app location

The old app was moved from this repository to **../Vibe Trading Original/**
(relative to the repository root). Old references in
research/hk_week2/WHERE_TO_FIND_HK_WORK.md to agent/src or agent/tests now refer
to that archive. The current contribution checkout remains
../Vibe-Trading-upstream and the current Week 3 research is ../indicatorlab-clean.

The original HK quote instructions below are historical notes preserved from
the old root README. Their commands belong to the app checkout, not this
research-only root. For current defaults and tested freshness, use the current
contribution README and indicatorlab-clean/HK_START_HERE.md.

### Hong Kong quote snapshots and continuous collection

`get_hk_quotes(symbols=["0700.HK", "0005.HK"], source="auto")` is available
to the research agent and MCP clients. It returns the raw price, currency,
provider quote time, retrieval time, quote age and delivery-delay metadata.
Yahoo HK quotes are [15 minutes delayed](https://help.yahoo.com/kb/finance/article-exchanges-data-delays-sln2310.html).
`auto` tries Tencent for missing or stale Yahoo quotes and keeps the newer
snapshot. Tencent delay is unknown. Explicit `yahoo`, `tencent` and `futu`
requests do not switch providers. Futu requires an installed `futu-api` SDK,
local FutuOpenD and the user's own quote entitlement; a successful snapshot
does not by itself establish real-time rights.

After installing this checkout with `pip install -e .`, run:

```bash
# One quote poll for the five default HK focus stocks.
python -m src.hk_data --once

# Record new snapshots every minute until Ctrl-C; resumes the same store.
python -m src.hk_data --symbols 0700.HK 0005.HK 1299.HK 0941.HK 0388.HK

# Any HK symbols in a CSV's ticker, yahoo_ticker or symbol column, or a text list.
python -m src.hk_data --symbols-file my_hk_symbols.csv --source tencent

# Read collected quotes and latest poll health, without a provider request.
python -m src.hk_data --latest
```

The collector stores snapshots and poll health in
`~/.vibe-trading/data/hk_quotes.sqlite3` (or the `VIBE_TRADING_HOME` runtime
directory). `--db` selects another store. Identical provider snapshots are
deduplicated across restarts, while changed values at the same timestamp are
preserved. The default retention is 30 days; `--retain-days 0` keeps all history.
Quotes stay labelled stale when their provider time stops advancing, including
after the close, on holidays or when a feed stalls. This collector is separate
from historical OHLCV loading and does not place orders. See
[`agent/src/hk_data/README.md`](<../../Vibe Trading Original/agent/src/hk_data/README.md>) for operation and
contribution details. Contributing the code lets each installation fetch future
updates; it does not require publishing anyone's local quote database.

