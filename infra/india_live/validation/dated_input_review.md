# November 24, 2026 deployment-input validation

See the [year-end calendar review](nse_calendar_maintenance.md) for the later rollout window.

The candidate separates input validation from operational approval. The runtime
manifest remains unapproved. The raw exchange download and the dated runtime
files are local inputs for a dedicated build context.

- The published NSE CSV contained 100 unique EQ symbols and 100 unique ISINs.
  Its symbol set matched the October 23 local snapshot. The normalized runtime
  CSV retains only the `Symbol,Series` columns used by the collector. [NSE constituent CSV](https://archives.nseindia.com/content/indices/ind_nifty100list.csv)
- The calendar covers November 24 through December 4, 2026, inclusive, in
  Asia/Kolkata. It has eight regular sessions and three closures. November 24 is
  the announced Capital Market holiday, and November 28–29 are weekend closures.
  Mock trading is excluded. [NSE Capital Market holiday circular](https://nsearchives.nseindia.com/content/circulars/CMTR71775.pdf) · [NSE mock trading calendar](https://nsearchives.nseindia.com/content/circulars/MSD71999.pdf)
- The runtime uses the common continuous trading window of 09:15–15:15 IST.
  This ends before the closing auction for eligible stocks and omits the extra
  continuous minutes available to other stocks. The date window ends before
  the December 7 closing-auction changes. [NSE closing-auction schedule](https://betanseapi.nseindia.com/static/products-services/closing-auction-session) · [NSE December 7 changes](https://nsearchives.nseindia.com/web/mediaattachment/2026-11/FAQs_for_CM_and_FO_FOR_CAS_2.0_20261109152618.pdf)

| Runtime input | SHA-256 |
| --- | --- |
| `nifty100-roster.csv` | `ee7e745ff750591de041f0a5b366667dd3d5db102aae6d7199da471e78a419eb` |
| `nse-calendar.json` | `92f0f2daa4616a1cd06da95834191823145ea9c9f7b421aa2007e233da7f24c4` |

Use a fresh roster and review the latest session notices before issuing
operational approval. A calendar extending past December 4 needs a new review
window and updated hashes. The separate Yahoo full-roster pacing limitation
still blocks activation.

## Validation results

The existing Dockerfile built a local `linux/arm64` image with the candidate
inputs. The runtime refused the bundled unapproved manifest. With networking
disabled, the collector validated the same roster and calendar using a
separate offline-only test manifest and no Dhan credentials. The container
verified holiday and weekend gating, the 09:15 opening and 15:15 cutoff,
Ohio client wiring with injected clients, and the watchdog import.
The test manifest stayed outside the image and repository.

The focused suite passed 205 tests. Black passed for the India live scope.
Ruff and local Ohio CloudFormation lint passed. The unmodified shared
`tests/test_config.py` has an existing Black formatting difference.
