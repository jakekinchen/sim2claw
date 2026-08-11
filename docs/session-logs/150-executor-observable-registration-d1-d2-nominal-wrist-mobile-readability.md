# OR150 Executor log — nominal wrist mobile readability

Date: 2026-08-08

OR150 repairs only the legibility of OR149's burned publication disclosure at
the Observation Deck's 390 px mobile viewport. It does not run MuJoCo, render a
simulator scene, replay an action, alter state, fit a camera or parameter, or
evaluate task success.

The immutable OR149 source render was transcoded once with an exact 424×61
transparent disclosure overlay at image row 27. The three disclosure lines use
11–13 point Arial Narrow. The result preserves 424×240, H.264/yuv420p, 20 fps,
531 frames, and 26.55 seconds.

At the website's measured 330 CSS-pixel video width, the poster was separately
reviewed at an exact 330×187 raster. All three lines are legible and the pawn
and jaws remain visible. The website must still carry the adjacent full claim
boundary, serve only the exact MP4 and PNG, and label the following 531-sample
scoreboard as OR34/C922 evidence rather than wrist-camera synchronization.

Verification command:

```text
uv run --locked python outputs/observable_registration_d1_d2_nominal_wrist_mobile_readability_v1/verify.py
9/9 gates passed
```

The artifact is a non-scoring retained-state projection. Robot/camera motion
comes from measured-joint kinematics, the selected pawn comes from OR34's
retained simulated trace, and other pieces use fresh canonical-reset `qpos0`.
It is not a D405-calibrated camera, replay, task-success result,
physics-fidelity result, promotion, or transfer evidence.
