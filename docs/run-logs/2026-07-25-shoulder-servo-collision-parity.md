# Shoulder-servo collision parity correction

Date: 2026-07-25

Status: simulation-only collision correction with retrospective physical-canary
comparison. This is not task, policy, or physical-transfer evidence.

## Result

The frozen simulation canary previously reported a nonstructural
`left_shoulder` to `left_lower_arm` contact at native step zero. At the
post-normalization physical-canary pose, the same coarse collision primitive
penetrated the lower arm by about 11 mm even though the exact bounded physical
canary completed without a stall, bus retry, rate limit, or safety clamp.

The vendored MuJoCo Menagerie source remains unchanged. During scene assembly,
Sim2Claw now tightens only the over-broad local X half-extent of the shoulder
STS3215 collision box from 23 mm to 12.4 mm. The 12.4 mm value matches the
compiled bound STL extent on that axis. The Y and Z box extents remain at their
conservative upstream values, so the servo retains collision coverage.

The existing frozen simulation-only canary then passed:

- action consumer SHA-256:
  `52a856a54d8edc9dc53ed44e83f8bfc5f6c670b79fec30dfc1eb56d4f6c08095`
- native MuJoCo steps: `842`
- forbidden contacts: `0`
- receipt:
  `runs/physical_excitation/20260725-follower-only-v1/simulation-canary-v2-contact-refined/receipt.json`
- receipt SHA-256:
  `666c3ea4352766c03caa02600dce99b20a74165ecf070c148541c539200b764f`

## Retrospective physical response comparison

The comparison reused physical canary action SHA-256
`129441d03791570782dc8771f13e0b6125dbd5e01369645bd0fd641ee4c22a20`
and its 37 measured follower samples. No robot command or new data collection
was performed.

| Metric | Coarse upstream box | Tightened X extent |
| --- | ---: | ---: |
| Aggregate joint RMSE | 2.548379° | 0.168784° |
| Elbow-flex RMSE | 5.908040° | 0.176887° |
| Maximum absolute joint error | 9.391076° | 0.515565° |

The aggregate reduction is 93.38%. This isolates a collision-geometry
abstraction error for this exact unloaded canary. It does not identify the
remaining camera extrinsic, joint-zero ownership, contact/compliance, pawn
consequence, or task-transfer domains.

With the collision correction active, the independently admitted timing
candidate still reduced aggregate canary RMSE from `0.177570°` to `0.168784°`
and maximum absolute error from `0.625452°` to `0.515565°`. It was not uniformly
better per joint: elbow RMSE changed from `0.140744°` to `0.176887°`, so this
retrospective canary does not widen the timing candidate's existing
configuration-input-only authority.

## Verification

`uv run --offline pytest -q tests/test_scene.py tests/test_physical_canary.py tests/test_recorded_replay.py`

Result: `25 passed, 10 subtests passed`.
