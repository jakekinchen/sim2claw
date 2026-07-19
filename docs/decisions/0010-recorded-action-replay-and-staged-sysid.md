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

MuJoCo 3.5 introduced an official system-identification package, and the pinned
3.10.0 package exposes it as `mujoco.sysid`. Its official surface uses bounded
nonlinear least squares around batched MuJoCo rollouts. The base wheel contains
the module, but importing the complete public surface requires the upstream
`sysid` extra; the project therefore pins that extra explicitly.

## Decision

### Replay contract

- Adopt `sim2claw.recorded_action_episode.v1` as the versioned, proof-classed
  episode contract.
- Reject non-finite, duplicate, decreasing, over-gapped, or overlong timestamps.
  Never silently repair them.
- Make command interpolation, command latency, MuJoCo integration step, and
  measurement alignment explicit. V1 supports zero-order hold or linear command
  interpolation, non-negative command latency, native MuJoCo stepping, linear
  alignment for continuous values, and previous-sample hold for discrete values.
- Initialize `qpos` and `qvel` from the measured initial state, replay the exact
  command series, and record joint, end-effector, gripper, pawn, and contact
  series only when the scene and episode expose them.
- Every unavailable observable is emitted with a reason. No label, visual guess,
  endpoint proposal, or fabricated zero substitutes for missing telemetry.

### Losses and parameter stages

The objective is a weighted robust Huber objective. The implementation exports
Huber pseudo-residuals so a least-squares backend minimizes the documented
robust cost rather than an unbounded squared-error surrogate.

Stages are frozen in this order:

1. Geometry: end-effector site offsets, requiring end-effector or pawn
   trajectory data.
2. Timing and control: command latency, actuator gain scale, and joint damping
   scale, requiring measured joints.
3. Contact and object: pawn mass and contact friction, requiring pawn or contact
   telemetry.

A stage with no identifying data is rejected. In particular, the contact stage
cannot run from joint-only recordings. All parameters have reviewed bounds.
Each stage uses deterministic bounded multi-start optimization and reports the
near-equivalent-fit ensemble, parameter ranges, and empirical spread. It never
claims that one parameter vector is uniquely identified.

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
  window from one episode may cross train and held-out partitions.
- Deterministic hash and leave-one-column-out strategies are supported. The
  latter rejects any episode missing column metadata and places every episode
  from the selected file onto held-out.
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

## Canonical post-cherry-pick procedure

Run exactly:

```bash
cd /Users/kelly/Developer/sim2claw
uv sync --frozen
uv run --frozen sim2claw sysid-input-report --catalog configs/data/physical_pawn_move_catalog_20260719.json --repo-root /Users/kelly/Developer/sim2claw --inspection-scope canonical_checkout --output runs/sysid/physical_pawn_input_capability_post_cherry_pick.json
uv run --frozen sim2claw sysid-fit --split configs/sysid/physical_pawn_sysid_split_v1.json --config configs/sysid/recorded_action_sysid_v1.json --output runs/sysid/physical_pawn_joint_timing_v1 --backend auto
```

The input-report command returns zero only when every joint/timing input is
present and integrity-verified; it never claims full calibration readiness.
The staged fit returns nonzero unless
the complete held-out improvement and requested-stage gate passes. Inspect its
receipts even when the expected joint/timing fit completes but missing
pawn/contact or end-effector data prevents a full calibration-success claim.
