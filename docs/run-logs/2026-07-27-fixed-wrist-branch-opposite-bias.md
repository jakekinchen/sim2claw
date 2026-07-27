# Fixed wrist branch opposite-bias heldout

Date: 2026-07-27

Branch: `codex/geometric-microtransfer-20260727`

Retrospective selection commit: `6072fd3`

First two-configuration freeze: `317eb8f`

Exact normalized-action correction: `7bcfa85`

Stable opposite-bias route/evaluator: `c14ce31`, `fac783a`

## Decision

The fixed-positive asymmetric wrist-play branch is strongly supported as a
mechanism but is not promoted. The positive-bias trace is exactly equal to the
dynamic parent, and the negative-bias trace improves every preregistered model
metric by more than `63%`. The frozen aggregate contract nevertheless rejects
because it required strict improvement on both signs and both wrist-return
errors narrowly exceeded `0.75 deg`.

This is contact-free actuator/kinematic evidence only. It does not authorize
pawn contact, task success, physical calibration, policy claims, or global
simulator-parameter promotion.

## Why the route changed

The first dual-configuration packet was independently rejected before motion
because six normalized wrist-action rows differed by one float64 ULP. The
negative wrist anchor was moved to an exact `+10 deg` translation of the
positive anchor, making the two normalized arrays byte-identical with SHA-256
`32834e5010a5c35304bbf4e69d6692cce2acc643b40fa467b4c0ff46477cde40`.

The first negative-load shoulder/lift/elbow configuration then sagged after
torque-off, so its second triangle was never executed. A recovery packet was
also rejected because its simulator preview omitted the initial bounded setup
clamp. The corrected recovery:

- starts C922, D405, and Pi before gateway setup motion;
- freezes and freshly recomputes a `9 x 9 = 81` state joint-progress
  hyperrectangle for the two setup joints;
- previews the setup and full clearance route together;
- admits no new, external, or worsened contact;
- returns to the stable anchor before torque-off.

The accepted recovery decision was
`SAFE-CANARY-SAG-TO-STABLE-RECOVERY-V2-20260727`. Its execution receipt SHA-256
is `a5e5128088319c074a13ca30e8068babfd1927d48e0e7d3addd6631518b65ad7`.
It completed `441 / 441` rows, recorded `373 / 62 / 440` C922/D405/Pi frames,
and closed within `0.175824 deg` pan/wrist of stable anchor A.

## Replacement heldout

The replacement negative configuration kept the positive configuration's
pan/lift/elbow/roll/gripper values and changed only wrist flex by exactly
`+10 deg`. MuJoCo wrist `qfrc_bias` changed from `+0.019895419 N m` to
`-0.022115791 N m`.

Frozen packet identities:

- packet SHA-256:
  `fcb565b3fb4d34e16cc7b8fcb54cdc1c07742f961d4ae2adb022e2f6c19c412c`
- plan SHA-256:
  `580470579cb5b68e4475566ab699f9ab274275cdacac05e8e952133e74535804`
- independent decision:
  `SAFE-CANARY-STABLE-OPPOSITE-BIAS-TRIANGLE-20260727`
- negative triangle action SHA-256:
  `bd3afc4094297d2a5d90b131d20f160bbce1590864f0bf366144aea0b6b843af`
- normalized triangle SHA-256:
  `32834e5010a5c35304bbf4e69d6692cce2acc643b40fa467b4c0ff46477cde40`

All three physical stages completed `361` motion rows and `80` exact hold rows
without executor error, action repair, clamp, stall, assistance, or
intervention. Follower torque was off after each stage, and every camera
interval enclosed its action.

| Stage | Purpose | C922 | D405 | Pi | Receipt SHA-256 |
| --- | --- | ---: | ---: | ---: | --- |
| 1 | stable A to negative C' | 374 | 62 | 440 | `3db9f193ea7dd9507e09ca66cc68cdf8e8e208269927dcede16aaf8c30d24336` |
| 2 | exact negative-bias triangle | 385 | 63 | 440 | `10e1a8bcb8eeea0de6978b8c996f82062d44fefcd75401dac1209bb8add84bc2` |
| 3 | C' through clearance to A | 371 | 62 | 440 | `6ab91df0e10b2338ab3bb3ce102f2ff411968d1c18273daf8990a32e6682f10a` |

The final return residual was zero pan/elbow/roll/gripper,
`0.087912 deg` lift, and `0.175824 deg` wrist flex. The follower closed torque
off at stable anchor A.

## Frozen evaluation

| Configuration | Variant | Wrist RMS | Joint RMS | EE RMS |
| --- | --- | ---: | ---: | ---: |
| positive bias | dynamic parent | `0.229799 deg` | `0.113824 deg` | `0.656433 mm` |
| positive bias | fixed positive | `0.229799 deg` | `0.113824 deg` | `0.656433 mm` |
| negative bias | dynamic parent | `0.752302 deg` | `0.338919 deg` | `2.199393 mm` |
| negative bias | fixed positive | `0.258030 deg` | `0.122422 deg` | `0.715679 mm` |

Negative-bias relative improvements were `65.70%` wrist, `63.88%` joint, and
`67.46%` end effector. Positive-bias comparisons were exactly `0%` because the
dynamic parent already stayed on the positive branch.

The deterministic evaluation receipt is
`runs/geometric-microtransfer/20260727-geometric-stable-opposite-bias-wrist-triangle-tricam-v1/heldout-validation.json`
with SHA-256
`25eefb9eb9a1a17c27e8dec1decff45d55c13ba30ba5811a2c459f7aca23ba57`
and digest
`3302404ea9db3b4bbb0a37dd13fd77c18529653f52ba23ecba82ae0a7aed72fa`.

## Next gate

Do not rewrite this evaluator after opening its traces. A future replication
may be frozen with the mechanism-appropriate rule: non-inferiority on positive
bias, strict improvement on negative bias, exact normalized actions, tricam,
torque-off, and return precision. Separately model the remaining `0.8-0.9 deg`
wrist return/compliance residual.

Pawn contact remains unauthorized by this receipt. The next pawn work must
start in simulation from the current stable physical anchor and current
workcell geometry.
