# OR151 Executor log — coordinate and landmark audit

Date: 2026-08-11

## Scope

OR151 audited immutable OR34 initialization in the exact OR18 scene without
stepping dynamics. It transported the retained physical file/rank board
coordinate through OR18's board basis and compared that result with OR34's
legacy world-XY copy, compiled D1, the pawn free joint, body position, support
plane, and the frozen nominal projection diagnostic.

## Result

All six frozen gates pass. OR34's legacy XY is `14.4160 mm` from OR18 D1. The
retained board coordinate transported through OR18 is `2.8251 mm` from D1 and
requires a `13.9782 mm` XY change. The compiled pawn body position and free-joint
translation agree exactly, rejecting a hidden body-origin/base-landmark offset.

The endpoint receipt's stored Z is `8 mm` below the OR18 support plane, but OR34
itself explicitly replaced Z with the settled scene support before the replay.
This is a provenance/bookkeeping distinction, not an authorized replay factor.

At common support Z, the frozen nominal uncalibrated presentation projection
residual changes from `9.8848 px` for the copied XY to `1.0000 px` for the
transported XY. OR34 reported `10.7742 px` from its actual initialized state.
The projection is corroboration only and grants no camera calibration claim.

## Verification

```text
uv run --locked pytest -q tests/test_observable_registration_or34_coordinate_landmark_audit.py
3 passed

uv run --locked sim2claw check --profile agent
pass
```

Receipt SHA-256:
`03316d9241df9f051c472d441908e2a009ccd980e3e6fb627a33151576f737bc`.

OR151 used one model compilation and `mj_forward`, with zero `mj_step`, replay,
fit, search, camera warp/fit, hardware, or paid-compute operations. It does not
mutate OR34 or establish physical world registration, physics fidelity, task
success, promotion, or transfer. Subject to independent Reviewer approval, it
admits only a separately frozen observation-conditioned replay whose sole
changed factor is the selected pawn's initial XY.
