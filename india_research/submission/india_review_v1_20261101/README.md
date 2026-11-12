# IndicatorLab India — portable PM review evidence (v1, 2026-11-01)

All eight backtests remain PROVISIONAL; two factors are non-evaluable. All final
PM decisions remain pending. No new scoring, convention selection or portfolio run
was performed. Start with [report](report.md), [Strategy Log](strategy_log.md) or
[CSV](strategy_log.csv). Evidence is selected from immutable existing archives.

- [Bundle manifest](bundle_manifest.json): checksums/sizes of included files and
  per-copy original source hashes. Sanitization changes JSON/Markdown hashes.
- [Review history](REVIEW_HISTORY.json): audits both previous evidence JSON files;
  originals remain unchanged and their full machine-specific maps are excluded.
- [Archive index](ARCHIVE_INDEX.md): original inventory identities and exclusions.
- `evidence/runs/`: eight saved portfolios, including daily returns, IC and trades.
- `evidence/signals/`: non-evaluable and Phase 2 signal-readiness evidence.
- `evidence/datasets/`: metadata only, not source market data.
- `supporting/`: sanitized narrative copies and methodological context.

Run `python verify_package.py` from this directory (standard library only).
It verifies bundle checksums, links, saved-metric identities and CSV alignment;
it does not download data, compute factors or simulate portfolios. The recorded
353-test log is historical; no full strategy test suite was rerun here.

ILLIQ uses adjusted-INR close times vendor volume as a turnover proxy, not actual
exchange turnover. India use is a developer metadata exception, not upstream
endorsement. Preserve 51/209 dividend and 31/209 normalization sensitivity, frozen
non-point-in-time vintage, Reliance/Kotak and calendar-inventory limitations.

`SUBMISSION_FILES.txt` lists the 155 evidence-change paths, including AGENTS.md;
no force-add of results/ is needed. India implementation, setup documentation and
root code_review.md are reviewed separately from this evidence allowlist. Do not
stage the whole india_research/ tree or old machine-specific evidence JSONs.
Staging a submission does not authorize a commit, push, PR, merge or publication.
