# Executor Session Log 009 - SAIL Retained Evidence Compile

**Date:** 2026-07-21

## Slice

P1-02 — compile the retained evidence inventory.

## Implemented

- A hash-bound retained B--G campaign contract with exact episode, row, split,
  action-frozen, context, and omission expectations.
- Deterministic physical telemetry and simulator trace importers that emit and
  verify `CalibrationEvidence.v1` items.
- Explicit null/false availability masks for unobserved physical contact,
  object, grasp, and latency channels.
- Separate regression-only items for the two already-open confirmation action
  identities; group metrics are not misassigned to individual episodes.
- Catalog, omissions, compile receipt, action-byte reconciliation, source
  digest verification, and deterministic regeneration.
- `sail-inventory` and `sail-compile-evidence` CLI routes.
- Missing-source, digest-drift, proof-class, channel-mask, action-hash,
  deterministic-repeat, and retained GOLD-16 coverage.

## Validation

- Focused tier: 22 passed.
- Broad tier: 642 passed, three skipped, all 328 subtests passed.
- Byte-repeat tree digest matched.
- Python compilation and `git diff --check`: pass.
- Optional `ruff` invocation was unavailable because the command is not in the
  locked environment; no lint claim is made.

## Known limitations

The original retained policy-concordance report has a declared hash but no
campaign-bound repo path, so no learned-policy evidence was imported. Five
physical episodes have no selected-campaign action-frozen trace, and the two
already-open confirmation identities have no retained per-row traces in this
receipt. No fresh physical holdout exists. These are explicit omissions, not
zeros or negative outcomes.
