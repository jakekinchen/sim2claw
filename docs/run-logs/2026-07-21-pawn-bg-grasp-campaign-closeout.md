# B--G action-frozen grasp campaign closeout

Date: 2026-07-21

This campaign replayed the same retained teleoperation action arrays under
bounded simulator-only hypotheses. No action value, order, or byte array was
changed. No hardware, network, paid API, policy inference, Brev instance, or
physical authority was used.

## Verified result

| Frozen hypothesis | Lifted | Lift + transport | Strict | Joint RMS | EE RMS | Trace guard |
|---|---:|---:|---:|---:|---:|---|
| v2 clean contact | 2/11 | 1/11 | 0/11 | 1.203 deg | 11.306 mm | pass |
| v3, 2.25 ms step | 4/11 | 1/11 | 0/11 | 1.214 deg | 11.417 mm | pass |
| base z -15 mm | 4/11 | 2/11 | 0/11 | 1.273 deg | 12.274 mm | fail |
| base z -20 mm | 4/11 | 2/11 | 0/11 | 1.333 deg | 13.124 mm | fail |

V3 is a verified trace-safe consequence advancement: lift count doubles from
2/11 to 4/11 while both predeclared trace guardrails pass. The vertical family
doubles lift-and-transport from 1/11 to 2/11, but cannot be promoted because it
regresses the trace vector beyond the frozen 1% bounds.

Across the frozen posterior family, the union covers 6/11 lifts and 5/11
lift-and-transport episodes. This is sensitivity coverage, not a single
simulator result. No candidate reaches 6/11 lift-and-transport or one strict
task success.

## Mechanism localization

Clamping the simulated robot to the retained measured joint trajectory reduces
sentinel EE RMS to 0.535 mm and closed-window gripper RMS to 0.003 degrees, but
produces only 1/3 lifts and 0/3 transports. Perfecting actuator tracking is
therefore not sufficient with the current scene/contact geometry.

The following bounded families were tested and rejected as single-composite
solutions: gripper force/gain/zero, load-triggered force, delay and per-joint
delay, solver step and iterations, solref/solimp, friction dimensions, pawn
mass/scale/radial scale, jaw primitive/mesh collisions, tip coverage/width/
thickness/normal offsets, capsule/ellipsoid tips, segmented rubber wraps,
board center/yaw/scale, source/reset offsets, and base height. An
evidence-derived D1 reset from the proposal homography was also a negative
control and retains no metric authority.

## Reproduction

```bash
uv run python scripts/closeout_pawn_bg_grasp_campaign.py
```

The generated receipt and figure live under
`outputs/pawn_bg_grasp_campaign_closeout_v1/` and bind every source receipt,
per-recording action hash, parameter digest, bootstrap interval, and claim
boundary.

Repository verification after regenerating the closeout:

```text
594 passed, 328 subtests passed in 1189.57s
```

## Claim boundary

The safe result is a retained, action-frozen simulator sensitivity advancement
plus a terminal negative for a promoted single composite. It is not physical
calibration, policy improvement, training admission, or sim-to-real transfer.
The smallest missing measurements are metric vertical registration, pawn
dimensions/mass, the jaw-tip rubber collision profile, and metric per-episode
initial pawn centers.
