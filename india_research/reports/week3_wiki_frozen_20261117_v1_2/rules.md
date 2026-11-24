# Frozen WATM/WVB/WCR v1_2

Complete rules: [rules.json](rules.json). Original proposals: [original_v1_rules.md](original_v1_rules.md). [Parent frozen v1_1](../week3_wiki_frozen_20261117/rules.json) is unchanged.

v1_2 adds explicit same-close sale-fee reservation and cash-constrained proportional buy funding, discovered by synthetic integration tests. Baseline selection, thresholds, stops and risk target formulas are unchanged. Requested and funded targets are audited separately. Existing portfolio accounting and original market fees remain authoritative. All three satisfy four indicators/two independent sources/three layers under the supplied Prakhar clarification; WATM supplies portfolio attention filtering.

Rules are frozen before historical evaluation. NOT REGISTERED; NOT EVALUATED. Runtime initial cash remains a required explicit local-currency setting before shared registration/run, never inferred from fixture capital.
