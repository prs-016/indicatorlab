# K1 HK symbol adapter and teammate handoff

Prepared November 23, 2026. This is a local handoff, not evidence that a teammate
has received the files or that a branch has been pushed.

## Import contract

```python
from src.markets.hk_symbols import (
    HK_AMBIGUOUS,
    HK_SUBREDDITS,
    canonical_hk,
    hk_names,
    normalize_hk,
    tencent_code,
)
from src.markets.errors import SymbolLookupUnavailable, UnknownTicker
```

`normalize_hk(raw)` validates both syntax and Yahoo chart price-history presence.
The required aliases `700`, `0700`, `00700`, `0700.HK`, `700.HK`, `HK:700` and
`HKEX:0700` become `0700.HK`; `9988` becomes `9988.HK`; `80737` stays
`80737.HK`. Syntax is ASCII digits, positive and at most five digits. A successful
history lookup with no positive close raises `UnknownTicker`. A network error,
rate limit, malformed response or mismatched identity raises
`SymbolLookupUnavailable`, so an outage is not advertised as an unknown company.

The history check requests monthly bars over Yahoo's full available range, with
a five-second request timeout and a 2 MB response cap. Confirmed identities are
cached six hours; confirmed unknown symbols are cached one minute; outages are
not cached. A caller with prior successful resolution may use
`canonical_hk(raw)` or `normalize_hk(raw, validate=False)` for syntax only.
Tests can inject `history_check=callable` without touching the production cache.

`tencent_code("0700.HK")` returns `hk00700`; it does not repeat history lookup.
The collector's real-time request prepends `r_`, yielding `r_hk00700`.
`tencent_code("80737.HK")` returns `hk80737`. Normalization preserves the counter:
it does not claim that an 8xxxx RMB counter is an HKD quote.

James's `src/resolve.py` is absent from this checkout. When integrating, re-export
the exact `UnknownTicker` class from `src.markets.errors` and map it to the shared
404 `{ "error": "unknown_ticker" }` response. Map
`SymbolLookupUnavailable` to service-unavailable handling. This avoids a circular
import between the future resolver and its market adapter. No shared contracts
were silently replaced and no peer-owned resolver was added.

## Names, aliases and provenance

`hk_names()` returns a caller-owned dictionary keyed by canonical Yahoo symbol.
Every one of the dated November 4, 2026 roster's 95 members has `name`,
`short_name`, `name_zh`, `aliases`, `ambiguous`, `wiki_en` and `wiki_zh` fields.
The metadata is in `config/hk_final_symbol_metadata.json`, separate from frozen
research inputs. The roster/date is explicit; this is not a current or historical
membership service.

The existing sourced Wikipedia title map supplies the display labels. Curated
short names include Tencent, Alibaba, Meituan, HSBC and AIA. Link, Galaxy and
Sands have `ambiguous=true` and occur in `HK_AMBIGUOUS`; consumers must require
financial/ticker context for these names rather than count every ordinary use.

US ticker aliases are recorded only when a depositary or issuer source confirms
them. There are 74 verified issuer mappings, including the required TCEHY, BABA,
JD and BIDU, plus NTES, TCOM, LI, ZTO, EDU, LNVGY, AAGIY and ONC. The separately
labeled historical BeOne alias BGNE remains useful for text matching; it is not
advertised as the current US ticker. The metadata explicitly marks ADR coverage
as incomplete: absence means not verified, not "no ADR exists". Do not treat the
alias table as a tradeable US security master.

Primary verification examples:

- [Tencent's Citi depositary record](https://depositaryreceipts.citi.com/adr/guides/pgm_d.aspx?cusip=88032Q109&pageId=15&subpageid=106)
  links TCEHY to ordinary code 700.
- [Citi unsponsored ADR program table](https://depositaryreceipts.citi.com/adr/guides/unspresource.aspx?pageId=3&subpageID=173)
  supplies 55 additional HK issuer mappings; only symbols and mappings are kept,
  not a copy of the table.
- [Alibaba investor FAQ](https://www.alibabagroup.com/en-US/faqs-investor-information),
  [JD's results](https://ir.jd.com/node/12441), and
  [Baidu's results](https://ir.baidu.com/news-releases/news-release-details/baidu-announces-third-quarter-2026-results)
  confirm the core cross-listings. Each other verified alias carries its exact
  issuer/depositary source URL in the JSON metadata.

## Real source gap: Laopu's English Wikipedia article

English titles are available for **94 of 95** names. The existing map lacks an
English article for `6181.HK` (Laopu Gold). On this review,
[English Laopu_Gold](https://en.wikipedia.org/wiki/Laopu_Gold) returned 404 and
[the Chinese article](https://zh.wikipedia.org/wiki/老鋪黃金) exposed no English
interlanguage link. The module therefore returns `wiki_en: null`,
`wiki_status: "missing_english_article"`, and a note with the observed reason.

This is an unmet source-dependent K1 acceptance item, not a fabricated 95th
article. The dashboard/resolver can use Chinese `老鋪黃金` for this name and show
English-source unavailability. Any change to the shared language policy must be
agreed with the team. It must not silently fill English views with zero.

Two older title mappings cover broader entities: English `BYD_Electronic`
redirects to `BYD_Company`, and `Chow_Tai_Fook_Jewellery_Group` redirects to the
broader `Chow_Tai_Fook` article. Their metadata preserves that shared scope;
these pageviews are not isolated subsidiary attention.

## HK subreddit check

The named candidates were checked on November 23 UTC using Joshua's existing
`src.reddit.arctic_client.ArcticShiftClient`, retaining its User-Agent, pacing
and retry/backoff implementation (bounded to two attempts and a ten-second
timeout for this operational survey). The parameters were checked against the
[Arctic Shift API documentation](https://github.com/ArthurHeitmann/arctic_shift/blob/master/api/README.md).

The new final-week criterion is existence plus at least one archived 2026 post;
it differs from the older research survey's minimum weekly-post criterion.
The operational results do not overwrite the frozen old survey or its config.

| Candidate | Exact archive identity | 2026 post found | Selected |
|---|---|---|---|
| HongKong | Yes | Yes | Yes |
| HKStockMarket | No archive match | Not established | No |
| ChinaStocks | Yes | Yes | Yes |
| Chinesestocks | Yes | No archived 2026 post returned | No |

`HK_SUBREDDITS` is `("HongKong", "ChinaStocks")`. Evidence in
`config/hk_final_subreddit_evidence.json` retains request URLs, retrieval times,
HTTP status and the matching post IDs/timestamps. No Reddit post text is copied.
"No archive match" is not proof a subreddit does not exist on Reddit.

## Validation and completion boundaries

```bash
python -B -m pytest tests/test_hk_symbols.py -q -p no:cacheprovider
```

The scoped unit selection reports **42 passed**. It covers every required alias,
five-digit preservation, garbage rejection before networking, confirmed unknown
versus provider outage, response identity/size, cache expiry, all 95 member-name
records, core ADR aliases, mutable-consumer isolation and evidence-qualified
subreddits. The missing English article is asserted explicitly, not hidden by a
weakened "all English titles exist" claim. No empirical backtests were run.

The files are ready for James/Joshua locally. Posting or sending this handoff,
teammate interface agreement, the missing English article and remaining ADR
verification are external/source follow-up items; no delivery message was sent.
