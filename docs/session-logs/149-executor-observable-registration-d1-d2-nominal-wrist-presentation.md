# OR149 Executor log — nominal wrist presentation

Date: 2026-08-08

## Scope

OR149 rendered the existing 531-row OR34 retained state timeline once through
the unchanged compiled `left_wrist_cam`. The render is a presentation-only,
non-scoring state projection. It did not run `mj_step`, integrate actions,
write controllers, fit parameters or camera geometry, evaluate task success,
or perform a simulator replay.

The physical wrist source remains the retained D405 RGB recording. No depth is
inferred from that RGB stream.

## Provenance correction

The original render receipt's phrase “OR34 canonical initial scene” was too
broad for non-selected pieces. The executable created a fresh compiled model
with canonical piece reset and did not restore OR34's 100-step settled full
scene. The exact publication wording is therefore:

- robot and camera: OR34 raw measured rows through frozen kinematics;
- selected pawn: retained OR34 simulated pose rows;
- other pieces: fresh compiled canonical-reset `qpos0`, not retained OR34
  state, with no dynamic-pose claim.

## Publication repair

The single simulator render was preserved byte-for-byte. A presentation-only
H.264 derivative added an inseparable disclosure band; this introduced zero
MuJoCo calls and zero additional simulator renders. The publication verifier
binds the original render, derivative, exact frame manifest, current scene
lineage, full SO-101 asset-directory digest, compiled MJB identity, D405 sample
association schedule, and all first-level/transitive helpers used to construct
the projection.

During verification, `mj_step`, `mj_step1`, and `mj_step2` were monkeypatched to
raise during context construction. All counters remained zero. The verifier
also checked the camera name, mounting body, resolution, focal lengths, sensor
size, local pose, and field of view.

The D405 relationship is sample-time associated for presentation with a frozen
maximum association error of `100.066125 ms`; camera exposures and device
clocks were not synchronized, and actuator-application timestamps are absent.

## Verification

```text
uv run --locked pytest -q tests/test_observable_registration_d1_d2_nominal_wrist_presentation.py
3 passed

uv run --locked python outputs/observable_registration_d1_d2_nominal_wrist_presentation_v1/verify_publication.py
11/11 gates passed
```

Publication media:

- `nominal_wrist.publication.mp4`: 424×240, H.264/yuv420p, 20 fps, 531
  frames, 26.55 s;
- video SHA-256:
  `615c9a31d3455b83dcf44bf92886cab9c45bd645e3f81cef1a6df489a06c7f64`;
- decoded-frame digest:
  `7eaa80a59b2183ee870383c51f1cfc595f4afda81e9952b4ab7a185a3d80a127`;
- representative poster: exact decoded sample 248.

## Claim boundary

This closes only the missing nominal simulator wrist-angle presentation. It is
not a calibrated or camera-matched D405 view, a complete OR34 scene replay, a
physics replay, a task-success result, simulator promotion, or transfer
evidence. OR149 admits no successor and restores the OR148 external-observation
boundary.
