# Executor Session 039 - D1→D2 exact-task preflight

**Date:** 2026-07-27

## Fresh Hardware State

A configuration-free follower-only preflight opened no leader, rewrote no
device configuration, commanded no motion, and verified torque disabled.

Fresh joint observation:

`[-6.681319, -92.395604, 101.670330, -50.417582, -104.131868, 1.662708]`

The follower calibration hash remains
`192404b6d3c1337495d69649969459aa9d3f66816cd916c67da2588815e93ec4`.
All joints are inside calibrated limits; the elbow has only `0.439560°`
upper-limit margin.

No repo-owned camera, gateway, Pi capture, or robot execution process was live
before or after the check.

## Existing Exact Executor Audit

The reviewed follower gateway accepts exact precompiled float64 targets,
records requested/sent/observed arrays and host timing, aborts before sending
any target that would require clipping or rate limiting, and treats gripper
contact deflection separately from a body-joint stall.

The existing geometric-physical compiler is not a REAL→SIM compiler. It
requires an already evaluator-passing simulator source episode, consumes
float32 simulator actions, inverse-maps them to hardware, and is therefore a
SIM→REAL surface. Reusing it here would reverse the mandated evidence order.

## Demonstration-Derived Corridor Audit

The old physical recording remains provenance only:

- source samples SHA-256:
  `ad606b9b917d985a4e866399a0c2d44adb12f3b48d310aa11452de9e03e73302`;
- observed `531 x 6` float64 tensor SHA-256:
  `ec75ad25adf9957311e837744af7340e27b602cfec5a2985db7841b5c3558312`;
- first elbow sample below `93.934066°`: index `51`;
- first elbow sample below `79.120879°`: index `64`;
- pre-grasp sample `100`: elbow `68.703297°`;
- minimum observed elbow: `44.527473°`.

This path crosses two immutable physical no-progress results before the
pre-grasp:

1. camera-pose setup v1 stopped at `82.769231°` while the exact request was
   `79.120879°`;
2. recovery v2 stopped at `97.186813°` while the exact request was
   `93.934066°`.

Both stops occurred after the gateway observed one second without measurable
elbow progress. No thresholds were changed and no rejected sample was
reconstructed.

## Decision

Task compilation stopped before producing canonical action bytes. Direct
demonstration-pose use crosses the failed elbow corridor. Re-anchoring joint
deltas does not preserve the physical gripper pose. Simulator IK would create
a simulator-owned action before the required REAL leg and, with the current
`11.195–19.997 mm` contact-free residual, would not independently admit pawn
contact.

No physical task motion occurred. REAL→SIM physics and SIM→REAL were not run
because their predecessor gates did not pass.

Accepted proof class:
`prospective_task_preflight_terminal_safety_blocker_no_action_or_task_or_transfer_authority`.
