# SAIL Retained Evidence Compile Run Log

Date: 2026-07-21

Milestone: P1-02

Proof class: deterministic retrospective evidence compilation

## Commands

```bash
uv run sim2claw sail-inventory --campaign configs/sail/campaign_retired_bg_v1.json
uv run sim2claw sail-compile-evidence --campaign configs/sail/campaign_retired_bg_v1.json --output outputs/sail/retired-bg-v1/evidence
uv run pytest tests/test_sail_evidence.py tests/test_sail_contracts.py -q
uv run pytest -q
uv run python -m compileall -q src/sim2claw/sail src/sim2claw/cli.py
git diff --check
```

`ruff` was not installed in the locked runtime, so no linter result is claimed.
Compilation, focused tests, the complete suite, and whitespace checks passed.

## Frozen identities

- Campaign: `a952131392d5212f5a26903cf4c68f06399b6a9507cf4a5673072b656635d239`
- Catalog: `e79dc7a3e6f684644fa18d77e5a1a4f11126829176a14e3c7c247d3daec02ed2`
- Omissions: `32dc9b7fc63bed6f403888cb3185731efb6f46f3a169dd06a233aa91d92c98b2`
- Receipt: `50f8eae5244ded8092ecd4921bab5667f910c788121d2c7cd95fbd918984b563`
- Receipt digest: `d3b17946c81379f2fcefdd2a9199df5b487575c009a04a303bc39eb3ed26b97a`
- Deterministic tree digest: `92481306375653225a73e2de8c8f0860cc1873153ef35abe2488960471ea67ba`

## Reconciliation

- Physical recordings: 18 episodes, 7,741 rows.
- Physical split: 15 train, three previously held out by the sysid split.
- Action-frozen simulator: 11 development traces.
- Already-open action-frozen confirmation: two regression-only action
  identities with no per-row trace values manufactured.
- Context: six hash-verified artifacts spanning video-event, contact,
  publication, nominal-print-conditioned scale, and visual-only 3DGS evidence.
- Omissions: seven explicit classes, including the unavailable original policy
  report path, missing physical channels, and the absent fresh holdout.

## Validation result

- Focused evidence plus contract tier: 22 passed.
- Complete repository: 642 passed, three expected skips, 328 subtests passed in
  1,232.08 seconds.
- Repeated materialization produced the same 34-file tree digest byte-for-byte.
- Every emitted evidence item validates and verifies its canonical digest.

## Claim boundary

P1-02 compiles retained evidence; it creates no new physical observation. Human
teleoperation and simulator replay remain separate proof classes. 3DGS remains
visual-only, AprilTag scale remains nominal-print-conditioned, missing channels
remain false masks, and all training, selection, simulator promotion, and
physical authority remain closed.

No provider, network campaign, paid compute, physical gateway, robot motion, or
Brev resource was used.
