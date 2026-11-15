# HK contribution-only handoff

- This HK branch contains the v2 mentor package in contributions/vibe-trading
  and concise root metadata/docs. Keep unrelated templates, data and apps out.
- There are eight package files: three patches, manifest, historical benchmark
  summary, alignment review, README and license. Patch contents target 25 files.
- Apply 01 then 02, or APPLY_ALL, only inside the Vibe checkout/base in MANIFEST.
  PR 1 works standalone; PR 2 is stacked. Never apply these to this handoff repo.
- ALIGNMENT_REVIEW separates implemented fixes, proposed shared conventions and
  unverified NIFTY integration. The supplied India branch is read-only.
- When code changes, update/rebuild patch hashes and preserve older empirical
  results as historical evidence; do not silently rerun or relabel them.
- .gitattributes disables whitespace checks only for unified-diff containers.
  Preserve actual source validation and patch reconstruction checks.
- Keep Git/main and separate Jack research unchanged. User handles commit/push.
