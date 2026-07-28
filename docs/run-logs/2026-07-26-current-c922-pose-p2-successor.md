# Current C922 pose P2 successor evaluation

Date: 2026-07-26

## Outcome

Pose P2 is an accepted, receipt-bound **fit observation**.  Adding it to the
frozen J/S/K/L fit split does not produce an identifiable P13 candidate.  The
successor result is:

`identifiability_failed_no_P13_candidate`

The split is J/S/K/L/P2 for fit and M for retrospective diagnostic use only.
P2 is not held out.  No camera, base, joint mapping, simulator parameter, or
physical capability was promoted.

## P2 source binding

The frozen acquisition contract selected P2 before capture.  The successor
evaluator consumes only the native 640x480 C922 MOV bound by the execution
receipt.

- execution receipt SHA-256:
  `e59ca19049de7a1ad161e4d675e2b850f640ba9ca22d874291fc167941bb0d30`
- joint samples SHA-256:
  `d6471d53910416bd133651ebb81affb02cae92a08edfceb38d5e89d584063d6a`
- callback ledger SHA-256:
  `776c198cca6aa549aab572983b8bac46d1769a3833009c7eb1f7b2a97fec94bf`
- native C922 MOV SHA-256:
  `9cf1f8c152393ea40a7b8f98c2d6d14956993b2d3cf2b655adea5bc0072f6e0b`
- selected zero-based MOV frame: 306
- selected callback sequence: 337
- nearest zero-based joint sample: 401
- joint-to-frame delta: +6.51625 ms
- deterministic decoded PNG SHA-256:
  `8c3e807b7fa663b3107e284eb8116ae59d349b7245976ec45d9ddf3090c3a01a`
- receipt-bound actual joint pose:
  `[75.51648, 9.84615, 41.01099, -29.84615, -60.52747, 2.49406]`
  degrees

The alignment passes the frozen 20 ms gate.  Convenience or manually selected
frames remain forbidden.

## Board evidence

Using the predecessor's exact Canny/Hough/unique-seed-line method:

- P2 directly supports 8 row lines and only 1 column line.
- J/S/K/L/P2 collectively support 8 row lines and only 2 column lines.
- exhaustive/accurate OpenCV 7x7 detection on P2 returns no corners.

P2 therefore improves row visibility but does not supply the missing
robot-side column evidence.  It fails the frozen minimum of seven directly
supported lines on both axes.

## Shared camera/base and exact CAD

All eight board symmetries were reranked using one shared camera and one shared
base delta over J/S/K/L/P2.  D4 `[1, 0, 3, 2]` remains preferred.

The conditional camera remains unchanged:

- focal length: 3580.09 px
- four-corner RMSE: 5.049 px
- Jacobian condition number: 608.52
- translation: `[0.0512, -0.1001, 4.0000]` m

The 4 m camera-depth bound remains active.  Changing the unmeasured square
design prior from 43.45 to 45.45 mm moves focal length from 3666.95 to
3497.04 px while camera depth stays bounded.

The five-fit-pose static base solve reports:

- median proximal-base edge distance: 4.077 px
- p90 proximal-base edge distance: 9.354 px
- selected translation: approximately `[+0.05, -0.05, +0.05]` m

The base translation remains on all three search bounds.  P2 exposes more
cross-pose inconsistency; repeatable convergence to a boundary is not
identifiability.

With that one camera/base fit frozen for both joint hypotheses:

| Evidence | Identity p90 | Stage-D p90 |
| --- | ---: | ---: |
| P2 fit observation | 11.480 px | 13.857 px |
| Fit mean across J/S/K/L/P2 | 10.823 px | 11.588 px |
| Retrospective M | 8.674 px | 9.886 px |

Identity is numerically better on P2 and on the five-pose fit average.  On
retrospective M it wins by only 1.212 px, below the frozen 2 px margin, and its
8.674 px p90 also misses the frozen 8 px edge gate.  This is no joint-mapping
verdict.

## Remaining blockers

The failed gates are:

1. P2 and the fit union still lack seven directly supported column lines.
2. Board-camera corner RMSE remains above 2 px.
3. Camera depth and base translation remain on active bounds.
4. Retrospective M misses both the winner edge and hypothesis-margin gates.
5. The 44.45 mm square side remains a design prior, not an independent metric
   measurement.
6. There is no nonplanar intrinsic/distortion calibration.
7. There is no future heldout pose captured after a successor candidate is
   frozen.

The first four are numerical failures in the current evidence.  The last three
are mandatory proof gates and cannot be inferred from P2.

## Reproduction

```bash
OPENCV_OPENCL_RUNTIME=disabled uv run --offline python \
  tools/evaluate_current_c922_pose_p2_successor.py \
  --output runs/c922-board-base-registration/\
20260726-current-c922-pose-p2-successor-v1

OPENCV_OPENCL_RUNTIME=disabled uv run --offline pytest -q \
  tests/test_current_c922_pose_p2_successor.py
```

Result: `2 passed in 12.03s`.

Successor contract SHA-256:
`9c81423bc55f49eb9eefd4f6ec73d78fc045715fc16f6d7472f5bb2b8066d496`.
