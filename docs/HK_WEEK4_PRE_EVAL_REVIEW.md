# Week 4 research pre-evaluation review

Reviewed: 2026-11-16T04:51:57.160753+00:00. Scope: read-only source review of `src/hk/week4/`
in the isolated research checkout. No empirical strategy backtests were executed
by this reviewer, and no research source was edited by the reviewer.

## Result

The material pre-evaluation findings are resolved in the current source snapshot.
The implementation agent was asked to verify phase order and no-op eligibility
with synthetic tests before the first empirical run. This review is a code
inspection, not evidence of strategy performance or completion of the evaluations.

## Resolved findings

- **Train before test:** the outer phase loop completes both markets' selected
  TRAIN base evaluations, 200 timing controls and drop-one ablations before
  candidate selection and the exclusive test-start marker. TEST receives the
  same parameters. No test metric determines the candidate or rule changes.
- **Redundant indicators:** unchanged train ablation return arrays/trade counts
  make the fixed case ineligible and force DROP. Prior hypotheses are retained
  for reporting; the code does not silently count a no-op indicator or tune rules
  after seeing test results. If none qualifies, the nominee is explicitly
  INELIGIBLE and is not represented as KEEP.
- **Maximum drawdown:** the worker computes MDD from equity with initial capital
  included in the running peak; final result rows expose train/test MDD.
- **Future exit censoring:** `make_plans()` raises when a triggered exit cannot
  execute before the split ends instead of silently dropping its earlier entry.
- **Overlap:** delayed exits colliding with a later same-instrument entry are
  rejected. Same-open exit then entry remains allowed.
- **Immutable preregistration:** resumed runs verify both source and input hashes.
- **Availability metadata:** weekly sentiment is labeled available from the next
  week's start; the underlying revision timestamp is kept separately.

## Other checks

Weekly baselines shift before rolling, regime quantiles use prior observations,
and week W signals enter at the first actual exchange session of W+1. Research
boundaries derive from configuration. The worker refuses post-cutoff arrays.
Calendar corrections are isolated from frozen Week 3 modules.

The random schedule preserves each instrument's count, realized session durations
and target weights, samples executable endpoints within the split, and prevents
same-instrument overlap. The engine checks actual count/durations and fails rather
than silently dropping rejected orders. Random null draws are not searched
strategies.

Selection-oriented IC ranks eligible names above rejected names and preserves
within-eligible priority. Its five-session forward label is a diagnostic, not the
realized stop/weekly holding return or a portfolio Sharpe proxy.

The prior 268-trial ledger already includes 21 legacy strategies, 101 older factor
attempts, 22 train variants and 124 evaluations. Those are not added twice. The
new strict HSI benchmark evaluated zero factors and contributes no new factor
trial. DSR remains a documented-search approximation because unknown earlier
searches and unavailable historical Sharpe samples cannot be certified.

## Limits to retain in the report

The previously observed 2022–September 2025 interval means the mandated extension
is not a fresh untouched holdout. Current constituents, current board lots and
retrieval-vintage adjusted prices remain research limitations. The predeclared
split-boundary rule leaves cash where a planned holding period cannot finish
within the split; explain this boundary effect. Data or execution validation may
still stop the run honestly.

`PRE_EVAL_REVIEW.json` records exact source SHA-256 hashes for this snapshot.
