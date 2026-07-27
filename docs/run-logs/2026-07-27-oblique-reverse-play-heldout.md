# Oblique reverse-play heldout

Date: 2026-07-27

Branch: `codex/geometric-microtransfer-20260727`

Frozen implementation commit: `70cc91a`

## Decision

The direction-conditioned joint-play candidate passed its first fresh,
contact-free geometric heldout. It remains a diagnostic simulator candidate;
this receipt does not authorize pawn contact, policy execution, task success,
or global Twin-fidelity promotion.

## Frozen identities

- Packet SHA-256:
  `753aec0e371a6f9c9eb60f45023011be51b355e5e21f42dd0bb37de901bcc7f3`
- Plan SHA-256:
  `106e47b181d4d1b63650adff04c46ab14dbe522d63d3ec00ed3b034f987a1fbc`
- Motion action SHA-256:
  `5a8a3ab0cd2264b33169f197b0904676a787dfe7573a56225e5e6ff0a42e7ab1`
- Hold action SHA-256:
  `51ec3224f4477f9a17fd120aba89ba6c9d86185e54d1b6919e3cc65e2ab6931a`
- Evaluator contract SHA-256:
  `d469ad8dcb726271acdcc39a1c3fe92525052b305596507cc2189f665aee389c`
- Evaluator implementation SHA-256:
  `624d031f66df155a75c3165888470d513252a634e3148190c977b6546efb725c`
- Independent review decision:
  `safe-canary-audit-20260727-oblique-reverse-heldout-readiness-v1`

## Execution

The exact `361 x 6` float64 route moved negative 5 mm in model-world X,
negative 15 mm in Y, and positive 15 mm in Z before returning to the starting
pose. Maximum joint excursion was `6.621417472 deg`; maximum slew was
`1.471426105 deg/s`. The simulation preview reported no contact.

Physical execution completed `361` motion rows and `80` exact return-hold
rows. No executor error was recorded. Final absolute return residuals were
`0.351648 deg` pan, `0.087912 deg` lift, `0.175824 deg` elbow, and effectively
zero wrist flex. Follower torque was off at close.

All three cameras enclosed the action:

- C922: `373` retained frames, zero inferred native-container gaps;
- D405: `62` retained frames, zero inferred native-container gaps;
- Pi IMX708: `440` frames.

The cameras share host bounds but not exposure synchronization or metric
cross-camera registration.

## Frozen evaluation

The selected reverse-play model improved both preregistered metrics over the
parent stateful model:

| Metric | Parent | Selected | Relative improvement |
| --- | ---: | ---: | ---: |
| Joint RMS | 0.654310 deg | 0.293635 deg | 55.12% |
| End-effector RMS | 5.430299 mm | 2.126002 mm | 60.85% |

Every gate passed: exact action invariance, all-three-camera action enclosure,
torque off, bounded return error, joint improvement, and end-effector
improvement. The validation receipt is
`runs/geometric-microtransfer/20260727-geometric-oblique-xm5-ym15-z15-round-trip-tricam-v1/heldout-validation.json`
with SHA-256
`29aa556d9b2e3e18d401fb3f2da4123857f993c4304e756da26256e53b7a0a75`.

## Next gate

Keep this passing model frozen. Use the heldout only to localize residuals,
not to retroactively alter this verdict. Select one independent contact-free
route from a bounded simulation route matrix, freeze its evaluator, and
require the same tricam execution contract. Pawn actions remain
simulation-only until separately admitted.
