# Current C922 board/base registration: terminal identifiability failure

Date: 2026-07-26

## Outcome

The widened 640x480 C922 captures J/S/K/L/M now have a deterministic,
receipt-bound native-frame evaluator using the exact full SO-101 group-2 visual
meshes.  The result is
`identifiability_failed_no_P13_candidate`.

This is a bounded terminal negative for the present captures, not a claim that
CAD registration is impossible.  The current data can choose the only
plausible board symmetry and produce a locally repeatable conditional edge
fit, but it cannot identify a defensible metric shared camera/base transform.
No simulator parameter, joint mapping, P13 evidence, or physical authority was
promoted.

## Frozen extraction and split

The evaluator opens only the receipt-bound native
`overhead_c922.native.mov`.  It selects the appended C922 callback closest to
the median host time of the final 80 joint-hold samples, uses that callback's
zero-based ordinal as the native MOV frame, and binds the nearest joint sample.
It explicitly forbids the convenience PNGs.

| Pose | Role | MOV frame | PNG digest prefix | Joint delta |
| --- | --- | ---: | --- | ---: |
| J | fit | 307 | `d67d128e` | +9.264 ms |
| S | fit | 305 | `e9cc8c7d` | -10.207 ms |
| K | fit | 306 | `0061fd04` | -4.428 ms |
| L | fit | 305 | `b260bf00` | -3.465 ms |
| M | retrospective validation | 306 | `611aecb6` | -12.683 ms |

J/S/K/L are the frozen fit split.  M is retrospective validation.  There is no
unopened future heldout pose, so this result cannot promote even if the other
gates were to pass.

## Exact-CAD conditional fit

The board edge detector found seven seed-consistent row lines but only four
seed-consistent column lines.  Arm, cable, pawn, and board-edge features
produce many raw Hough responses; they are not counted as direct lattice
support unless they agree with a unique expected playing-grid line.

All eight square symmetries were tested.  D4 permutation `[1, 0, 3, 2]` is the
only winner that places the exact fixed SO-101 base in the observed lower-right
region.

The conditional centered, square-pixel, zero-distortion pinhole solve reports:

- focal length: 3580.09 px
- four-corner RMSE: 5.049 px
- Jacobian condition number: 608.52
- camera translation: `[0.0512, -0.1001, 4.0000]` m

The 4.0 m depth bound is active.  The shared base delta also drives to the
search boundary: translation `[+0.05, -0.05, +0.05]` m and rotation vector
`[-0.1612, -0.1666, +0.0912]` rad.  Although repeated starts collapse to the
same boundary solution (2.49 px median and 7.71 px p90 proximal-base edge
distance), boundary agreement is not identifiability.

Changing the unmeasured 44.45 mm square design prior by +/-1 mm changes the
conditional focal from 3666.95 px to 3497.04 px and the four-corner RMSE from
4.945 px to 5.155 px.  Camera depth remains on the 4 m bound.  The design prior
therefore cannot serve as a measured metric anchor.

With the one camera/base fit frozen for both candidates, retrospective M gives:

- identity full-CAD p90: 12.048 px
- Stage-D full-CAD p90: 10.356 px
- Stage-D margin: 1.693 px, below the frozen 2 px gate

This is no joint-map verdict.  The failed gates are direct column support,
board-camera coordinate fit, camera fit interior, base fit interior, identity
validation edge error, hypothesis margin, and future heldout.

## One-stage calibration pose P

A simulation-only search was run from the repeated start
`[0, -106.11, 100.18, -100.18, -119.08, 2.494]` degrees.  It enforced the
calibrated joint ranges, at most 90 degrees excursion on every joint, and zero
MuJoCo robot contacts.  Of 375 valid grid candidates, the recommended target
is:

`[89, -16.5, 60, -20, -60, 2.494]` degrees

Its maximum stage excursion is 89.61 degrees.  Under the conditional camera it
keeps 100% of the sampled moving CAD visible, overlaps 6.843% of the playing
board, and projects to `[353.2, 253.9, 600.3, 428.0]` px.  It is preferable to
the supplied seed `[80, -20, 40, -20, -30, 2.494]`, which is also collision
free but has 94.45% visibility and 12.24% overlap.

The unconstrained diagnostic target `[100, 0, 40, 20, 0, 2.494]` reaches only
0.179% board overlap, but its 120.18 degree maximum stage excursion violates
the one-stage gate and is not the executable recommendation.

The generated `pose-P-preview.png` is a diagnostic projection onto the
receipt-bound M frame; it is not an observation of pose P and is not physical
execution evidence.

## Exact missing observations

The present result needs all of the following before a P13 candidate can be
considered:

1. Direct, unoccluded support for at least seven playing-lattice lines on both
   axes.  Pose P is designed to improve this without hiding the CAD arm/base.
2. An independently measured board square side or another metric anchor.
3. A non-planar intrinsic/distortion calibration; a single board plane cannot
   independently identify the assumed camera family.
4. One future heldout pose captured only after the candidate is frozen.

## Reproduction

```bash
uv run --offline python \
  tools/evaluate_current_c922_board_base_registration.py \
  --output runs/c922-board-base-registration/20260726-current-c922-v1

uv run --offline pytest -q \
  tests/test_current_c922_board_base_registration.py
```

Result: `2 passed in 22.23s`.

Tracked contract SHA-256:
`21225fcb7b916e5b82af2696f2bee93ea76486db8d976b1ac5918915fa66954a`.
