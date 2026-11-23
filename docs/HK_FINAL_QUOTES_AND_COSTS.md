# On-demand HK quotes and USD purchase costs

## Quote module and existing API

```python
from src.live.quote import get_quote
quote = get_quote("HK:700", "hk")
```

The HK branch reads known operational-roster members using DynamoDB
`GetItem(Key={"symbol": "0700.HK"}, ConsistentRead=True)` on
`indicatorlab-live-hk`, region `us-west-2`, through the existing environment/IAM
chain. Importing does not contact AWS, start collection or expose credentials.
`INDICATORLAB_LIVE_HK_TABLE`, `AWS_REGION` and `INDICATORLAB_HSI_ROSTER` retain
their existing meanings. Unknown markets fail explicitly until their owners'
providers are composed; no fake India/US provider is supplied.

For explicit local development:

```python
from src.live.quote import QuoteService, local_hsi_reader
service = QuoteService(hsi_reader=local_hsi_reader)
quote = service.get("700")
```

Non-HSI symbols use Tencent `r_` plus `tencent_code`, e.g. `r_hk00100`. The
four-digit path reuses the frozen collector parser. Five-digit counters extend
its exact field map without changing that frozen file. Counter identity is
preserved; an 8xxxx RMB counter is not converted as HKD. Non-HSI currency is
left unknown where the provider format does not establish it.

Quotes retain the seven shared fields: symbol, price, change_pct, volume,
ts_exchange, ts_received and source. Added metadata includes store, market,
market_open, market_state, next_open, delay_seconds and label. Session labels
and exchange age are recomputed even within the five-second observation cache.
Lunch is `lunch break`; other non-open sessions are `market closed`. In an open
session, age below 60 seconds is `live`; older observations are `delayed ~N min`.
The label describes observed last-trade age, not certified publication latency.
Source failure is not fabricated as an unknown company or a zero price.

The existing `GET /live/hk` list response remains unchanged. Optional queries:

```text
GET /live/hk?symbol=700
GET /live/hk?symbol=700&shares=100
GET /live/hk?symbol=700&shares=100&hkd_per_usd=7.8&commission_hkd=50&platform_fee_hkd=0&fx_spread_bps=10&fx_fee_usd=2&transfer_fee_usd=5&settlement_pass_through=true
```

The last example's exchange rate and fees are illustrative manual inputs.
Without `shares`, return the on-demand quote. With `shares`, return
`{"quote": ..., "estimate": ...}`. The existing API source mode decides local
versus DynamoDB explicitly; it does not silently switch AWS to local. Invalid
cost inputs return 422, unknown tickers 404, and unavailable quote/FX services
503. These errors stay inside the calculator rather than falsely marking a
working HK list feed disconnected. The currency estimator supports known HKD
ordinary-share counters only.

## Cash conversion and fees

`src.hk.trade_costs.estimate_order` uses Decimal arithmetic. For a purchase:

```text
executed shares = floor(requested shares / board lot) * board lot
effective HKD per USD = reference * (1 - FX spread bps / 10000)
USD needed = (share value + known HKD charges) / effective rate
             + fixed conversion fee USD + transfer fee USD
```

Selling deducts HKD costs before converting and applies an adverse spread in
the opposite direction. A request below one board lot is rejected. Unfilled
shares and their indicative notional are shown separately. The existing dated
lot table is not a historical database; a missing symbol warns before using
one share. No new HKEX reference copy is downloaded for this feature.

For ordinary stamp-duty-subject shares, duty is 0.10% per side through July 31,
2021; 0.13% August 1, 2021 through November 16, 2023; 0.10% from November 17,
2023. Each note rounds duty up to a whole HK dollar. SFC, AFRC and HKEX trading
fees are individually cent-rounded with their dated rates. Settlement charges
and the pre-2023 trading tariff are broker pass-through choices, not universal
retail charges. Current participant settlement estimates use cent rounding as
an explicitly indicative broker assumption; the broker controls its bill.

All source documents, rates and effective dates are in
[`hk_order_cost_sources.json`](../config/hk_order_cost_sources.json), including
the [IRD rate history](https://www.ird.gov.hk/eng/pdf/sd_stock_rates.pdf),
[HKEX fee circular](https://www.hkex.com.hk/-/media/HKEX-Market/Services/Circulars-and-Notices/Participant-and-Members-Circulars/SEHK/2022/CT14122E.pdf)
and [2025 settlement circular](https://www.hkex.com.hk/-/media/HKEX-Market/Services/Circulars-and-Notices/Participant-and-Members-Circulars/HKSCC/2025/ce_HKSCC_SET_022_2025.pdf).

Broker commission, platform charge, FX spread, fixed FX fee, transfer fee and
settlement choice default to unknown. A numeric result with any unknown charge
is explicitly a **Known-cost USD subtotal**. Enter zero only to state that a
charge does not apply. Personal US income/dividend/capital-gains taxation,
custody/account fees and slippage are outside the estimate. US residents'
worldwide-income and investment-tax rules are documented by the
[IRS](https://www.irs.gov/individuals/international-taxpayers/us-residents);
there is no single per-order US tax rate to insert for every investor.

## Actual display FX and the separate historical contract

Automatic display FX reads the official HKMA daily API. If it is unavailable or
materially old (over seven days), use paired `HKD=X` market price/time metadata
through the project's existing yfinance client. Both branches retain the rate's
direction, source and observation date; the market branch retains the exact
provider timestamp and identifies itself as `market_reference`. There is no
fixed peg fallback. If neither source supplies a recent rate, enter an explicit
manual reference or wait; old FX is not relabelled live. The hour-long cache also
rechecks wall-clock age after a sleep or clock jump. Data is display-only.

For reproducible manual calculation without a frontend:

```bash
python -B -m src.hk.trade_costs --symbol 0700.HK --shares 100 --price-hkd 400 --hkd-per-usd 7.8 --commission-hkd 50 --platform-fee-hkd 0 --fx-spread-bps 10 --fx-fee-usd 2 --transfer-fee-usd 5 --settlement-pass-through yes
```

This illustrative example gives HKD40,000 principal, HKD45.08 exchange/duty/
settlement charges, HKD50 commission, and approximately USD5,152.54 required
under those exact assumptions. It is not a current price or broker quote.

The historical B3 engine adapter is separate. It obtains daily `HKD=X` through
Vibe's loader and requires explicit close/publication-time evidence before
causal USD valuation. No display quote or newer-than-cutoff FX enters a frozen
strategy result. See the K3 patch's `agent/backtest/HK_FINAL_K3.md`.

## Tests and evidence

```bash
python -B -m pytest tests/test_hk_symbols.py tests/test_hk_on_demand_quote.py tests/test_hk_order_costs.py tests/test_hk_quote_cost_api.py -q -p no:cacheprovider
```

`tests/fixtures/hk_on_demand/` contains a timestamped, hashed public Tencent
capture, a true unknown-symbol response, the observed stale HKMA response and
paired Yahoo FX metadata only (no raw Yahoo history CSV). These reproduce
parser identity, field mapping, future-time rejection and FX-freshness behavior
offline. No background collector or AWS request is required by unit tests.
