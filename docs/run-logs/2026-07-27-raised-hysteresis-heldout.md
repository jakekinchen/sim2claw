# Raised wrist-hysteresis heldout

Date: 2026-07-27

Branch: `codex/geometric-microtransfer-20260727`

Frozen fit commit: `dfe85df`

Frozen route and evaluator commit: `acd2837`

## Decision

The bounded `0.015 N m` wrist load-sign hysteresis candidate failed its fresh,
contact-free raised-anchor heldout. It is rejected and is not promoted.
The previously passing direction-conditioned joint-play model remains the
best accepted contact-free transfer candidate.

## Frozen identities

- packet SHA-256:
  `70f20befd09034240a51c14c71118bc6ff6f4f22437f07c7933244d9f3f2b119`
- plan SHA-256:
  `0cdeff6eaf33b7c11b6c333fb6d5a58cca0defd670d0da5b1e00785e1d23ea96`
- heldout action SHA-256:
  `2442e46a9138d4d930162bb4e0f04d035ef08002d37708f05c106126043c0b7b`
- heldout hold SHA-256:
  `56bedcd4370e538f6d50b9e9bab829adf9854f7c8f1f38b72b3b4bf2f1f4a42c`
- independent decision:
  `SAFE-CANARY-RAISED-HYSTERESIS-20260727`

The route raised the pinch point by `20 mm`, moved to a positive-load anchor,
then executed a four-segment shuttle to a negative-load raised waypoint before
returning through clearance to the exact starting anchor. The heldout
simulator predicted four parent load-sign switches at source indices
`59, 146, 239, 326` and four hysteretic switches at
`91, 179, 271, 359`. The simulation contact preview reported no external
contact. Maximum slew was `4.3902 deg/s`.

## Physical execution

All three stages completed `361` motion rows plus `80` exact hold rows with no
executor error, clamp, rate limit, assistance, intervention, or action repair.
Follower torque was off after every stage.

| Stage | C922 | D405 | Pi | Receipt SHA-256 |
| --- | ---: | ---: | ---: | --- |
| setup | 377 | 63 | 440 | `d2ace534af30b5b98358db646235cb0d3cd77ba2279372b6684c15e32c22b664` |
| heldout | 372 | 62 | 440 | `6dce2b530663786975a6c3d187cf1846c21a90751e8331dd77900c21c456e840` |
| return | 378 | 63 | 440 | `4671f4545970596c2cde3a13e3212d6dfb3f05c9c3e76ab256a1818c981b0be2` |

Every camera interval enclosed its stage action. The final torque-off follower
pose was
`[-8.8791, -106.2857, 99.2088, -94.3736, -126.3736, 1.6627]`
degrees. Final return residuals were `0.5275 deg` pan, zero lift/elbow,
`0.3516 deg` wrist flex, and zero wrist roll/gripper.

Pi tag-specific visual return was also strong: ID 1 returned within
`0.494 px` and ID 2 within `1.150 px`, corresponding to `1.61%` and `3.10%`
of their peak excursions. This is diagnostic pixel evidence, not metric camera
registration.

## Frozen evaluation

| Metric | Parent no hysteresis | Selected 0.015 N m | Relative change |
| --- | ---: | ---: | ---: |
| Wrist RMS | 0.633824 deg | 0.742550 deg | 17.15% worse |
| Joint RMS | 0.368496 deg | 0.407063 deg | 10.47% worse |
| End-effector RMS | 2.802423 mm | 2.865424 mm | 2.25% worse |

The tricam, torque-off, exact-action, and return-error gates passed. All three
model-improvement gates failed. The deterministic receipt is
`runs/geometric-microtransfer/20260727-geometric-raised-opposite-four-crossing-tricam-v1/heldout-validation.json`
with SHA-256
`941e1e99030e6bc8a2f2fa859242e7d68a0a9f6b03a3b3037ac3d9d38e3a28aa`.

## Next gate

Stop the wrist `qfrc_bias` sign-threshold family. The smallest remaining
actuator hypothesis is the already frozen asymmetric wrist play corridor used
without load-sign switching. Separately, estimate one Pi PTS-to-joint phase
offset from the repeated tag trajectories while freezing camera geometry and
actuator parameters.

Pawn contact remains unauthorized by this receipt. The historical C8 action
packet is not a transfer candidate from the current follower anchor because
its initial body-joint targets are roughly `90-180 deg` away on several
joints. A future pawn probe must be generated and previewed from the current
physical anchor.
