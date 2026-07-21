# B--G rubber-tip retention sensitivity

Date: 2026-07-21

This campaign tested the owner-reported rubber bands on the SO-101 fingertip
without changing any retained teleoperation action value or order. It used no
hardware, network model inference, paid API, or Brev compute. The result is a
simulator sensitivity analysis, not physical rubber calibration.

## Video evidence boundary

The exact E2-to-E1 recording (`20260719T031615Z-0e058ca2`) has a synchronized
C922 overhead video. Close frames visibly support distinct red rubber rings at
the distal fingertip. That episode has no recording-bound wrist stream. The
available D405 wrist release belongs to source recording
`20260718T230416Z-573f2320`, so it is generic gripper-shape context only and was
not used as synchronized E2-to-E1 evidence.

## Drop localization

The baseline ranked state traces show:

| Rank | Move | First bilateral lifted contact | First contact loss | Falls below 20 mm after peak |
|---:|---|---:|---:|---:|
| 1 | C2 to C1 | 13.401 s | 16.301 s | 16.369 s |
| 2 | E2 to E1 | 11.801 s | 12.067 s | 12.501 s |
| 3 | D2 to D1 | 9.302 s | 11.201 s | 11.234 s |
| 4 | F2 to F1 | 9.869 s | 12.002 s | 11.268 s |

E2-to-E1 is the clearest slip/drop case: bilateral contact is lost about
0.30 seconds before peak rise and about 0.43 seconds before the pawn falls
below the lift threshold. F2-to-F1 is different: the pawn descends below the
threshold while jaw contact remains, so it should not be described as a pure
frictional release.

## Bounded campaign

Twenty-eight sentinel candidates were retained: 16 continuous-sleeve plus
raised-ridge geometry probes and 12 material/contact probes. The ridge model
kept the continuous pad and superimposed four or five narrow bands, matching
the visible topology more faithfully than the earlier gapped segmentation.

No raised-ridge candidate passed all three selection conditions: preserve the
3/3 lift and 1/3 lift-plus-transport counts, pass both trace RMS guards, and
keep peak rise below the 100 mm launch-instability limit. One attractive
scalar result launched C2 by 337 mm and was explicitly rejected.

Sliding friction 2.0 was the sole frozen candidate advanced from the sentinel
stage. It preserved 3/3 lifts and 1/3 lift-plus-transport, passed both sentinel
trace guards, and raised mean sentinel retention from 0.404 seconds to 0.429
seconds.

## Frozen full-set result

| Metric | V3 baseline | Rubber friction 2.0 | Delta |
|---|---:|---:|---:|
| Lifted | 4/11 | 4/11 | 0 |
| Lift plus transport | 1/11 | 1/11 | 0 |
| Strict success | 0/11 | 0/11 | 0 |
| Mean retained grasp | 0.1158 s | 0.1235 s | +6.7% |
| Mean final target distance | 106.2 mm | 82.8 mm | -22.0% |
| Mean post-grasp slip | 17.05 mm | 16.66 mm | -2.3% |
| Mean targetward progress | 14.56% | 13.82% | -5.1% |
| Joint RMS | 1.2138 deg | 1.2197 deg | pass |
| EE RMS | 11.4168 mm | 11.5576 mm | **fail** (11.4571 mm limit) |

For E2-to-E1, final target distance falls from 219.6 mm to 18.1 mm and
retention rises from 60.75 ms to 72.0 ms, but slip slightly worsens, targetward
progress slightly decreases, and the episode remains outside the
lift-plus-transport gate. This is a strong endpoint sensitivity, not a verified
task-success gain.

## Decision

Retain V3 as the default simulator. The rubber hypothesis produces a verified
partial diagnostic improvement, but it does not improve lift/transport counts
and fails the all-episode EE RMS guard. It is not promoted, not training data,
and not evidence of physical transfer.

Reproduce the closeout from retained receipts:

```bash
uv run python scripts/closeout_pawn_bg_rubber_retention.py
```

The typed receipt is written to
`outputs/pawn_bg_rubber_retention_closeout_v1/rubber_retention_closeout_receipt.json`.
The read-only Studio comparison task is
`pawn_bg_rubber_sliding2_sensitivity`; it is intentionally separate from the
default ranked V3 gallery.
