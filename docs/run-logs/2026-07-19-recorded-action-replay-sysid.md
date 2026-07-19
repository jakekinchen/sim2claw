# Recorded-action replay and staged system-identification run log

Date: 2026-07-19 America/Chicago

## Request

Build the dependency-ready foundation for replaying exact recorded actions in
MuJoCo and fitting staged simulator parameters against whole-episode train and
held-out splits. Preserve proof classes and fail closed when observables or the
official optimizer surface are unavailable.

## Scope and constraints

- Worktree: `/Users/kelly/.codex/worktrees/5307ce13-4971-4a6c-abf3-abd28e179148/sim2claw`
- Branch: `codex/recorded-replay-sysid-foundation`
- Baseline: current `main` at `13a6dfd`
- No canonical-checkout writes or physical dataset copying.
- No robot, camera, serial, servo, gateway motion, Brev, paid compute, or model
  training.
- No B-G endpoint benchmark, Studio, submission asset, `GOAL.md`, or
  `project_state.json` ownership.
- Prior-project code, outputs, datasets, checkpoints, caches, and environments
  were not inspected or copied.

## Acceptance targets

- Versioned episode, replay, parameter, split, optimizer, and receipt contracts.
- Deterministic MuJoCo replay with strict timing semantics and synchronized
  observable tables.
- Robust observable losses and explicit unavailable-observable reasons.
- Ordered geometry, timing/control, and contact/object stages with parameter
  bounds, multi-start fits, and uncertainty summaries.
- Exercised official MuJoCo sysid adapter plus a smooth-parameter-only fallback.
- Frozen whole-episode and leave-one-column-out splits with leakage rejection.
- Held-out improvement required before calibration success.
- Focused fixtures and negative tests for every requested rejection class.

## Implementation record

1. Added `sim2claw.recorded_action_episode.v1` and the default staged sysid
   configuration.
2. Added strict episode loaders for canonical JSON and the repository's physical
   receipt/sample format, without guessing missing EE, pawn, or contact fields.
3. Added MuJoCo initialization, exact command replay, interpolation/latency,
   synchronized JSONL output, observable metrics, and robust Huber residuals.
4. Added deterministic whole-episode split freezing, leave-one-column-out,
   hash/leakage validation, staged parameter application, official and local
   bounded optimizers, near-equivalent ensembles, and held-out comparison.
5. Added CLI surfaces for replay, capability inspection, input inspection, split
   freezing, and staged fitting.
6. Pinned `mujoco[sysid]==3.10.0`, refreshed the lock, exercised the official
   API, and checked in its isolated capability receipt.
7. Froze the 18 catalog episode identities as 15 train and 3 held-out. This
   manifest contains no recording data.

Implementation commits:

- `dff9fa7` — strict recorded-action contracts, replay runtime, and synthetic
  fixtures/tests.
- `a32f6e7` — staged system identification, official adapter/fallback, split,
  CLI, dependency lock, and focused tests.

## Input-capability state

`docs/reference/SYSID_INPUT_CAPABILITY_20260719.json` is explicitly scoped to
this isolated worktree. It reports:

- 18 catalog episodes inspected.
- 0 ready here.
- 36 required system-identification receipt/sample assets absent here.
- 54 catalog-bound receipt/sample/video assets absent here; video would be
  hashed for integrity only, never interpreted as a metric observable.
- 11 catalog/receipt metadata conflicts that cannot be resolved without those
  ignored assets.
- no measured EE, pawn, or contact trajectories.

The coordinator separately reported 18 recovered canonical directories and 54
verified catalog-bound hashes. That statement is recorded as externally
reported context only; this receipt did not inspect canonical and does not
verify it. Endpoint visual proposals remain unreviewed and are not admitted as
telemetry.

## Verification ledger

| Check | Result | Proof class |
| --- | --- | --- |
| Focused replay and sysid tests | 15 passed in 0.73 seconds | Synthetic |
| Official `mujoco.sysid` bounded exercise | Passed; fitted `0.375` to target `0.375`, absolute error `0.0` | Dependency capability |
| Deterministic replay CLI smoke | Passed; 5 synchronized rows with joint/EE/gripper metrics and explicit pawn/contact absence | Synthetic replay |
| Isolated physical input report | Expected exit 1; 0/18 joint/timing-ready, 36 required inputs and 54 catalog-bound assets absent, full calibration readiness false | Physical read-only capability |
| Physical whole-episode split | 15 train / 3 held-out identities | Contract |
| Full repository tests | 179 passed and 30 subtests passed in 16.47 seconds | Mixed repository test proof |
| Package build | sdist and wheel built successfully under `/tmp/sim2claw-build-5307ce13` | Packaging |
| Lock, JSON, CLI, and whitespace checks | `uv lock --check`, `jq empty`, sysid input help, and `git diff --check` passed | Source hygiene |

## Result and limitations

The dependency-ready foundation and verification ledger are complete. No
physical calibration was performed in this worktree. Joint/timing
calibration must be rerun in canonical after integration. Geometry and
contact/object stages must remain skipped or rejected until measured identifying
observables are supplied. Even after a fit, calibration success requires the
frozen held-out gate; optimizer convergence alone is insufficient.

## Canonical post-cherry-pick commands

```bash
cd /Users/kelly/Developer/sim2claw
uv sync --frozen
uv run --frozen sim2claw sysid-input-report --catalog configs/data/physical_pawn_move_catalog_20260719.json --repo-root /Users/kelly/Developer/sim2claw --inspection-scope canonical_checkout --output runs/sysid/physical_pawn_input_capability_post_cherry_pick.json
uv run --frozen sim2claw sysid-fit --split configs/sysid/physical_pawn_sysid_split_v1.json --config configs/sysid/recorded_action_sysid_v1.json --output runs/sysid/physical_pawn_joint_timing_v1 --backend auto
```

The input report returns zero only for complete integrity-verified joint/timing
inputs; full calibration readiness remains false without geometry and
contact/object observables. The fit remains nonzero when the complete
held-out/stage calibration-success gate does not pass. Preserve and inspect the
generated ignored receipts rather than treating optimizer completion as
promotion.

Completed: 2026-07-19T06:17:06Z.
