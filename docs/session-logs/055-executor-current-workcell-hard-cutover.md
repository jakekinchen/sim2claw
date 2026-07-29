# Executor 055 — current-workcell hard cutover

Date: 2026-07-28

## Slice

Bound `9e563f4` as the immutable historical runtime boundary, classified every
production `build_scene_spec` caller, added the transform-free
`sim2claw.current_workcell` API, migrated Studio live/assets and the episode
record workspace, and added an explicit read-only legacy facade.

The first attempted internal refactor changed the hash-bound `scene.py`.
The orientation regression failed closed; the change was fully reverted and
the expected SHA-256 `4b7dd7b...` restored before continuing. The final
implementation contains one private fixed physical-layout binding inside the
canonical module and exposes no selector to active callers.

## Evidence

- Migration manifest:
  `configs/migrations/current_workcell_hard_cutover_v1.json`
- Goal loop:
  `docs/autonomous-workflow/current-workcell-hard-cutover-20260728.md`
- Focused result: `68 passed, 2 subtests passed`
- Scene callers classified: `24/24`, with no missing or extra paths
- Physical/gateway/serial/counting authority: false
- Unrelated `tools/build_fiducial_sheet.py`: untouched

Final relevant verification passed `96` tests and `18` subtests. Python
compilation, diff checking, JSON parsing, exact caller classification, and the
workflow audit also passed. Implementation commit `4706851` was pushed to the
working branch.
