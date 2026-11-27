# India Reddit survey evidence

This compact package preserves the completed November 14, 2026 survey without
raw posts or repeated acquisition. `weekly_counts_2024.csv` contains all 52 full
Monday–Sunday UTC weeks plus December 30–31 for four communities;
`source_comparison.csv` summarizes archive availability, counts and limitations.
The three communities passing every full week are active in `config.yaml`:

| Community | 2024 posts | Full-week median | Minimum | Weeks >=20 |
|---|---:|---:|---:|---:|
| IndianStockMarket | 50,563 | 997.5 | 404 | 52/52 |
| IndiaInvestments | 13,821 | 271 | 176 | 52/52 |
| IndianStreetBets | 28,590 | 517.5 | 379 | 52/52 |

DalalStreetTalks has a 19-post full week and remains inactive, although its
annual average exceeds 20. Partial weeks are not compared with full weeks.
Counts are records exposed by Arctic Shift, not proof of archive completeness,
usable historical text, sentiment or company-level research coverage.

The original survey used Arctic Shift daily submission aggregations; shifted
bucket labels were checked against requested windows and sampled day intervals.
Provider API documentation: https://github.com/ArthurHeitmann/arctic_shift/blob/master/api/README.md
The full raw query evidence remains preserved locally; it is not required by the
application and is not included in this publication.

`matching_rules.proposed.yaml` is the preserved 100-company proposal, not a
runtime configuration file. Active config omits its unvalidated contextual
RIL/TCS/SBI aliases. Qualified NSE identifiers and verified company-name patterns
use the shared matcher; bare ambiguous acronyms, brand guesses and historical
identity substitutions are not enabled. Current constituent identities do not
establish historical NIFTY 100 membership. No historical corpus is supplied.
