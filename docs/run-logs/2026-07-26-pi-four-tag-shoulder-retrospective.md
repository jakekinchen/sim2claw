# Pi four-tag shoulder bundle — consumed-D retrospective

Date: 2026-07-26

Proof class: `physical_static_current_camera_four_tag_pose_d_consumed_retrospective`

## Outcome

The four-tag bundle keeps the previously validated current-camera parameters,
tag 0–2 mounts, and joint offsets fixed. Only tag 3's six-DOF mount was fit
from the new pose-H and pose-I observations. The accepted physical attachment
classification is `left_shoulder`, based on the observed tag-3 image-x motion
tracking tag 0 across N/H/I/D.

Training-pose leave-one-out was retained as a disclosed diagnostic rather than
silently promoted:

| Tag-3 body | Mean fold RMSE px | Full tag-3 RMSE px | Full tag-3 max px |
| --- | ---: | ---: | ---: |
| `left_base` | 19.7475 | 22.3610 | 25.3160 |
| `left_shoulder` | 21.3905 | 8.2066 | 13.3887 |
| `left_upper_arm` | 19.3599 | 7.8187 | 12.0168 |

LOO alone preferred `left_upper_arm`; the physical motion classification
preferred `left_shoulder`. This disagreement is explicit and prevents the
result from serving as automatic attachment or simulator-parameter authority.

## Pose-D integrity

An initial, incorrectly broad joint-refit candidate consumed pose D and was
rejected at `70.5012 px` overall RMSE. That result is preserved at:

`runs/pi-link-tag-calibration/20260726-current-four-tag-v1/heldout-evaluation.json`

Pose D was not reopened. The corrected shoulder bundle was scored only from
the already-bound observations in that rejected receipt and is therefore
retrospective, not fresh held-out evidence.

The consumed-D shoulder result was also rejected:

| Tag | RMSE px | Maximum px |
| --- | ---: | ---: |
| 0 | 19.1336 | 26.9749 |
| 2 | 69.5815 | 75.9570 |
| 3 | 22.9735 | 29.0544 |
| Overall | 43.7244 | 75.9570 |

Because camera, tags 0–2, and joint offsets remained byte-for-parameter fixed,
the expanded bundle changes shared-tag RMSE by exactly `0.0 px` versus the
prior three-tag model. It adds a tag-3 diagnostic but does not improve the
old model on shared tags.

## Lineage

- Candidate:
  `runs/pi-link-tag-calibration/20260726-current-four-tag-v3-shoulder-retrospective/candidate.json`
  — SHA-256
  `d6f8017a115af25bd1b784934665f42fc43f6d8a0acd759b01a872c5109e1e33`
- Retrospective evaluation:
  `runs/pi-link-tag-calibration/20260726-current-four-tag-v3-shoulder-retrospective/retrospective-evaluation.json`
  — SHA-256
  `9ec5a1398beb5d5fe31a072856e158ed9fea4fa91990b691b7b40e05fd84c8fb`
- Tool: `tools/fit_pi_four_tag_bundle.py`

The run artifacts remain local and ignored. This diagnostic grants no
simulator promotion, policy authority, physical-task authority, or fresh
held-out claim. Follower torque remained off; this work performed no hardware
operation and used no Brev resource.
