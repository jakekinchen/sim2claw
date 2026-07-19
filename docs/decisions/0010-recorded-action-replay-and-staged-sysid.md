# Decision 0010: recorded-action replay and staged system identification

Date: 2026-07-19

## Context

The simulator needs a reproducible way to initialize from a measured episode,
replay the exact recorded commands, compare only observables that were actually
recorded, and estimate bounded parameters without leaking held-out episodes.
The current physical catalog identifies 18 candidate episodes. In this isolated
Codex worktree, their ignored receipt and sample files are intentionally absent:
36 required receipt/sample inputs and all 54 catalog-bound assets are missing,
and 11 catalog entries also have metadata conflicts. That is an
input-capability result, not a claim about the canonical checkout.

The coordinator separately reported that canonical now contains all 18 ignored
recording directories and has verified 54 catalog-bound hashes. This worktree
did not inspect or reproduce that state. Canonical must regenerate the
capability receipt after these commits are cherry-picked. Endpoint visual
proposals remain unreviewed and are not pawn trajectories, contact telemetry,
or end-effector telemetry.

A subsequent coordinator-owned read-only audit found that presence and hashes
were insufficient: all 18 physical episodes begin with three mapped joints
outside the current MuJoCo ranges. Across 7,741 rows, the coordinator reported
2,255 measured rows and 2,231 command rows outside range, with maximum
exceedance 0.1235 rad. Those counts are external context, not reproduced proof
in this isolated worktree. They require canonical regeneration through the
strict parser and range auditor before any fit is considered.

MuJoCo 3.5 introduced an official system-identification package, and the pinned
3.10.0 package exposes it as `mujoco.sysid`. Its official surface uses bounded
nonlinear least squares around batched MuJoCo rollouts. The base wheel contains
the module, but importing the complete public surface requires the upstream
`sysid` extra; the project therefore pins that extra explicitly.

## Decision

### Replay contract

- Adopt `sim2claw.recorded_action_episode.v1` as the versioned, proof-classed
  episode contract.
- Canonical episodes must provide measured initial joint position and velocity,
  plus per-joint position/velocity units in exact `joint_names` order. Missing
  velocity is never replaced with zero. Hinge bindings require
  radian/radian-per-second semantics and slide bindings require
  meter/meter-per-second semantics; shape, finiteness, unit pairing, and model
  joint type are all checked before replay.
- Require an episode-specific `initial_object_state`: either a named body and
  free joint with measured world-frame pose/velocity, explicit units, and
  hash-bound provenance, or an explicit unavailable reason that blocks pawn and
  contact stages. A global pawn label cannot substitute for this binding.
- Reject non-finite, duplicate, decreasing, over-gapped, or overlong timestamps.
  Never silently repair them.
- Physical inputs use the hash-bound
  `sim2claw.physical_joint_transform.v1` contract. It freezes source and
  simulator joint identity/order plus per-joint sign, scale, units, and zero
  offset. The checked-in transform is provisional and not calibration-approved;
  range feasibility alone cannot approve its zero offsets.
- Make command interpolation, command latency, MuJoCo integration step, and
  measurement alignment explicit. V1 supports zero-order hold or linear command
  interpolation, non-negative command latency, native MuJoCo stepping, linear
  alignment for continuous values, and previous-sample hold for discrete values.
- Validate initial joints, the complete measured trajectory, and every recorded
  command against joint and actuator limits before assigning state or stepping.
  Exact replay forbids clipping. Synchronized rows emit recorded commands plus
  requested and applied controls, and calibration eligibility requires them to
  be identical.
- Initialize joint and, when available, named-object free-joint `qpos` and
  `qvel` from measured state. Record joint, end-effector, gripper, pawn, and
  contact series only when the scene and episode expose them.
- Continuous alignment is driven by explicit observable semantics. Only fields
  declared quaternion-valued receive sign handling and normalization; an Nx4
  joint vector remains an ordinary vector.
- Every unavailable observable is emitted with a reason. No label, visual guess,
  endpoint proposal, or fabricated zero substitutes for missing telemetry.
- Replay and fit receipts use repo-relative or content-addressed identities and
  preserve the full physical catalog -> receipt -> samples provenance chain.
  A caller-supplied catalog ID/hash is not enough: the loader must open the
  hash-matching catalog, resolve exactly one recording entry, and prove that
  its repo-relative assets and hashes bind the loaded receipt and samples.
- Physical replay requires the receipt and every row to bind the physical
  sample schema. The first measured joint-velocity vector initializes `qvel`;
  rates use only the transform's sign and scale, never its position zero
  offset. The rate field, units, formula, and sample hash remain explicit in
  the replay receipt.

### Losses and parameter stages

The objective is a weighted robust Huber objective. The implementation exports
Huber pseudo-residuals so a least-squares backend minimizes the documented
robust cost rather than an unbounded squared-error surrogate.

Stages are frozen in this order:

1. Geometry: end-effector site offsets, requiring measured end-effector
   position data.
2. Timing and control: command latency, actuator gain scale, and joint damping
   scale, requiring measured joints.
3. Contact and object: pawn mass and contact friction, requiring pawn or contact
   telemetry.

A stage with no identifying data is rejected. Each parameter declares its
allowed supporting observables, and a finite perturbation must produce a finite,
nontrivial weighted-residual sensitivity before any optimizer is called. A
pawn-only loss therefore cannot identify an end-effector site offset, and a
zero-Jacobian stage remains skipped or rejected. The contact stage cannot run
from joint-only recordings or without the measured object binding. Pawn mass
scaling updates both body mass and inertia by the same factor and calls
`mj_setConst` so MuJoCo recomputes derived subtree mass and dynamics constants.
All parameters have reviewed bounds. Each stage uses deterministic bounded
multi-start optimization and reports the near-equivalent-fit ensemble,
parameter ranges, and empirical spread. It never claims that one parameter
vector is uniquely identified.

### Optimizer capability boundary

The primary adapter targets the pinned official `mujoco.sysid` API. A checked-in
capability receipt records the importable exports and an exercised bounded fit.
Official sysid use may be claimed only when that exercise or a real fit actually
ran through the official package.

If the exact package is missing or incompatible, the adapter fails closed with
an actionable capability report. A deterministic finite-difference local
least-squares fallback is allowed only for parameters marked smooth and
fallback-supported. It refuses contact/object parameters and other non-smooth
surfaces.

### Split and acceptance ownership

- Splits contain complete episode identities and content hashes; no row or time
  window from one episode may cross train and held-out partitions. A canonical
  assignment digest binds the algorithm inputs, counts, assignments, fractions,
  columns, catalog/config hashes, and provenance fields.
- Deterministic hash and leave-one-column-out strategies are supported. The
  validator recomputes every assignment from the declared seed/fraction or
  selected column. Owner, unit, allowed/default strategy, seed, fraction,
  column rule, config ID, and config hash must also match the loaded hash-bound
  sysid configuration; a self-consistent manifest recomputed under a changed
  seed is rejected. Leave-one-column-out additionally rejects missing,
  unresolved, or conflicting task labels unless every episode carries reviewed,
  hash-bound column-adjudication lineage.
- The checked-in physical split freezes 15 train and 3 held-out episode
  identities. It does not imply that their ignored data exists in this
  worktree.
- Calibration succeeds only if the frozen held-out robust loss improves over
  the frozen baseline by both configured absolute and relative thresholds and
  every requested stage is valid. Training code never promotes itself.

## Public dependencies and reasons

| Dependency | Source | Reason |
| --- | --- | --- |
| `mujoco[sysid]==3.10.0` | https://github.com/google-deepmind/mujoco/tree/3.10.0/python/mujoco/sysid | Pinned official simulator and official bounded nonlinear system-identification surface. |
| Upstream `sysid` extra dependencies | The dependency set published by MuJoCo 3.10.0 and frozen in `uv.lock` | Import and exercise the official toolbox without locally reimplementing its optimizer stack. |

No prior-project implementation, environment, dataset, output, checkpoint, or
cache was inspected or copied for this work.

## Proof boundary

The checked-in tests and replay fixtures are synthetic proof. The official
toolbox receipt is dependency-capability proof. The input report is a
read-only capability receipt for this isolated checkout. None of these is a
physical task proof, pawn/contact observation, trained policy, endpoint
benchmark result, or robot-motion authority.

The checked-in physical transform is explicitly unapproved. Therefore current
canonical physical episodes are not joint/timing calibration inputs even if
their catalog, receipt, and sample hashes verify. No joint-zero parameter is
introduced: range feasibility is not physical geometry evidence.

## Canonical post-cherry-pick procedure

Run exactly:

```bash
cd /Users/kelly/Developer/sim2claw
uv sync --frozen
uv run --frozen sim2claw sysid-input-report --catalog configs/data/physical_pawn_move_catalog_20260719.json --config configs/sysid/recorded_action_sysid_v1.json --repo-root /Users/kelly/Developer/sim2claw --inspection-scope canonical_checkout --output runs/sysid/physical_pawn_input_capability_post_cherry_pick.json
```

The expected current result is nonzero with a report that parses all present
payloads, exposes exact per-joint/row limit violations, and keeps
`joint_timing_replay_ready=false` because the checked-in transform is not
calibration-approved. Do not run `sysid-fit` until a separately reviewed,
hash-bound transform resolves the range mismatch and the regenerated report is
green. Missing end-effector, object-pose, pawn, and contact observables still
prevent full calibration readiness after that narrower gate is resolved.

`--inspection-scope canonical_checkout` is retained as a coordinator-facing
CLI spelling, but a caller-supplied path does not prove canonical-checkout
identity. The receipt reports that supplied root as inspected and explicitly
makes no canonical identity claim. A zero-row range audit likewise reports
`audit_complete=false` and cannot claim that all audited values were in range.
