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
8. Repaired frozen-split authority: validation now recomputes deterministic or
   LOCO assignments, fractions, columns, counts, and a canonical assignment
   digest. LOCO additionally requires reviewed, hash-bound per-episode column
   adjudication; the current conflicted catalog is not LOCO-ready.
9. Extended episode v1 with an explicit measured object body/free-joint state
   or an unavailable reason. Pawn/contact replay and fitting remain blocked
   without that binding.
10. Added parameter-to-observable declarations and finite perturbation
    sensitivity gates. Zero-sensitivity parameters never reach an optimizer.
11. Made quaternion alignment semantic-driven, added physically consistent
    mass/inertia scaling, and made requested/applied control diagnostics exact.
12. Added the hash-bound `sim2claw.physical_joint_transform.v1` contract and a
    strict physical parser/range audit. Initial state, every measured row, and
    every command must be in range; clipping is forbidden.
13. Made replay and fit identities portable and bound the physical catalog,
    receipt, and sample provenance chain, including relocation and tamper tests.
14. Bound split validation to the exact loaded config authority. A changed seed,
    fraction, owner, strategy, column rule, or config hash is rejected even when
    all assignments, counts, and the internal digest are recomputed.
15. Removed the false implication that a caller-supplied root proves canonical
    checkout identity. The compatibility scope spelling now means only that the
    supplied root was inspected.
16. Required the physical loader itself to open the hash-bound catalog and
    resolve its recording entry before a replay receipt can claim a complete
    provenance chain.
17. Recomputed MuJoCo derived constants after mass/inertia scaling and verified
    the changed `body_subtreemass`, not only the directly mutated arrays.
18. Required and parsed measured physical joint velocity, initialized `qvel`
    from the first row with sign/scale only, and bound its schema, units,
    transform semantics, and sample provenance. Empty range audits now report
    incomplete/false instead of vacuous success.

Implementation commits:

- `dff9fa7` — strict recorded-action contracts, replay runtime, and synthetic
  fixtures/tests.
- `a32f6e7` — staged system identification, official adapter/fallback, split,
  CLI, dependency lock, and focused tests.
- `4d0fb09409b579887b2626638154f6053f6ee482` — independent-review repair for
  split authority, object binding, sensitivity, semantic alignment, strict
  physical transforms/ranges, exact controls, portable provenance, and
  mass/inertia consistency.
- `aaadce2112574af5210847327f7aca3e93b98d52` — binds the split to evaluator
  config authority, downgrades caller-supplied checkout identity, verifies the
  catalog entry inside the physical loader, and refreshes derived MuJoCo mass
  constants.
- `58e6a50d1e9d1b0c0e9d36dfb8930e94308b9327` — binds measured initial joint
  velocity and makes empty joint-range audits explicitly incomplete.

The coordinator's independent reviewer formally recommended holding the three
original commits until this repair is integrated and rerun. This log does not
override that integration hold.

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
- the checked-in physical transform is provisional and
  `calibration_approved=false`.

The coordinator separately reported 18 recovered canonical directories and 54
verified catalog-bound hashes. That statement is recorded as externally
reported context only; this receipt did not inspect canonical and does not
verify it. Endpoint visual proposals remain unreviewed and are not admitted as
telemetry.

The coordinator also reported a canonical read-only range audit: all 18
episodes begin out of range in three mapped joints; 2,255 of 7,741 measured rows
and 2,231 command rows are out of range, with maximum exceedance 0.1235 rad.
Those numbers were not reproduced in this isolated checkout. The repaired
canonical input command must regenerate them through the strict adapter. Until
that report is green with a separately reviewed transform, timing/control
fitting is forbidden.

## Verification ledger

| Check | Result | Proof class |
| --- | --- | --- |
| Focused replay and sysid tests | 36 passed and 14 subtests passed in 1.35 seconds | Synthetic |
| Official `mujoco.sysid` bounded exercise | Passed; fitted `0.375` to target `0.375`, absolute error `0.0` | Dependency capability |
| Deterministic replay CLI smoke | Passed; 5 synchronized rows with joint/EE/gripper metrics and explicit pawn/contact absence | Synthetic replay |
| Isolated physical input report | Expected exit 1; 0/18 joint/timing-ready, 36 required inputs and 54 catalog-bound assets absent, full calibration readiness false | Physical read-only capability |
| Physical whole-episode split | 15 train / 3 held-out identities; assignment digest `370581db3fa383e6a36a77de6463db401c384ecbf5ef46314abb939158a14d95`; exact config authority plus 18 full catalog/receipt/sample bindings | Contract |
| Full repository tests | 200 passed and 44 subtests passed in 16.92 seconds | Mixed repository test proof |
| Package build | sdist and wheel built successfully under `/tmp/sim2claw-w4-velocity-final.Jt38JE` | Packaging |
| Lock, JSON, CLI, and whitespace checks | `uv lock --check`, `jq empty`, sysid input help, and `git diff --check` passed | Source hygiene |

## Result and limitations

The repaired dependency-ready foundation and verification ledger are complete.
No physical calibration was performed in this worktree. Canonical must first
regenerate the strict input capability report; it must not run joint/timing
fitting with the provisional transform or any range violation. Geometry and
contact/object stages remain skipped or rejected until measured identifying
observables and the episode-specific object binding are supplied. Even after a
future eligible fit, calibration success requires the frozen held-out gate;
optimizer convergence alone is insufficient.

## Canonical post-cherry-pick commands

```bash
cd /Users/kelly/Developer/sim2claw
uv sync --frozen
uv run --frozen sim2claw sysid-input-report --catalog configs/data/physical_pawn_move_catalog_20260719.json --config configs/sysid/recorded_action_sysid_v1.json --repo-root /Users/kelly/Developer/sim2claw --inspection-scope canonical_checkout --output runs/sysid/physical_pawn_input_capability_post_cherry_pick.json
```

The expected current input-report result is nonzero and
`joint_timing_replay_ready=false`, with exact range diagnostics and the
provisional-transform blocker. Do not invoke `sysid-fit` until a reviewed,
hash-bound transform resolves the mismatch and the regenerated report returns
zero. Full calibration readiness still requires geometry, object-pose, pawn,
and contact observables. The legacy `canonical_checkout` scope spelling records
that this caller-supplied root was inspected; it does not independently prove
that the root is the coordinator's canonical checkout.

Repair completed: 2026-07-19T07:20:45Z.
