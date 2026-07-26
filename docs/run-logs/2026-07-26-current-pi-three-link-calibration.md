# Current Pi three-link calibration

Date: 2026-07-26

## Outcome

The current wide Pi-camera geometry now has one shared zero-distortion camera
model and a fresh held-out follower-pose result that passes the frozen
fiducial reprojection gates. The accepted physical tag attachment map is:

- tag 0: `left_shoulder`
- tag 1: `left_upper_arm`
- tag 2: `left_wrist`

The fresh pose N exposed all three tags and scored `5.7563 px` corner RMSE and
`9.2818 px` maximum error under the frozen `8 px / 15 px` gates. No per-frame
camera alignment, image-space part transform, IK, command clipping, joint
offset assistance, or corrective motion was used.

This is a passing static kinematic/camera diagnostic. It is not yet automatic
simulator-parameter promotion, contact/load-path evidence, task evidence, or
policy authority.

## Camera intrinsics

The current Pi view cannot reuse the earlier camera extrinsic because the
physical camera view changed. A full-resolution manual-focus sweep found lens
position 4 to be the strongest sheet-detection view. Six unique tag IDs on the
printed 5-by-4 sheet were admitted.

The sheet's printed tag occupies 20 mm including its 2 mm quiet-zone border on
each side; the detected black boundary used by the pose solver is therefore
16 mm. Leave-one-tag-out validation selected the zero-distortion model:

- full-resolution focal: `1954.8894 px` at 4608 pixels wide
- output focal: `651.6298 px` at 1536 pixels wide
- output mean validation RMSE: `1.0210 px`
- output maximum validation error: `3.5985 px`

The tested radial model was rejected because its leave-one-tag-out mean and
maximum errors worsened to `6.1265 px` and `31.2062 px` at full resolution.
The selected receipt remains limited by a single planar view and a focus
setting that is not proven identical to torque-on autofocus.

## Body-map correction and rejection

Tag 0 moved by roughly 150 pixels across follower-only poses and is therefore
a follower marker, not a stationary marker from the other arm. Training-only
leave-one-pose-out selection over sparse partial views incorrectly preferred
the `upper_upper` family. Its untouched pose M result was rejected at
`42.2762 px` RMSE and `61.5398 px` maximum.

Retrospective comparison on M identified `shoulder_upper` as the best physical
map at `14.9730 px` RMSE and `24.1580 px` maximum, but M had then been used for
selection and could not grant fresh validation authority. A new candidate was
therefore frozen with that physical map before pose N was selected or
captured.

On fresh pose N, all four body-map families scored:

| Body-map family | RMSE px | Maximum px |
| --- | ---: | ---: |
| `shoulder_upper` | 5.7563 | 9.2818 |
| `upper_upper` | 11.8836 | 21.1255 |
| `shoulder_lower` | 19.3022 | 30.5748 |
| `upper_lower` | 21.0715 | 31.2632 |

The same `shoulder_upper` family is best on the fresh pose and is the only
family that clears both frozen pixel gates.

## Full-model verification

The renderer projects every group-2 visual mesh belonging to the follower's
`left_` body tree. The fresh held-out overlay contains all 18 visual mesh
geometries across eight bodies:

`left_base`, `left_shoulder`, `left_upper_arm`, `left_lower_arm`,
`left_wrist`, `left_gripper`, `left_camera_mount`, and
`left_moving_jaw_so101_v1`.

No visual body is omitted. The non-visual `left_edge_clamp` fixture body has
no group-2 mesh and remains explicitly excluded. The fixed base is projected
from the same global camera as the links; it is not independently nudged.
Silhouette scoring and occlusion reasoning remain future diagnostics, so this
overlay verifies full-model inclusion and shared-frame consistency rather than
perfect photometric registration.

## Physical execution

Pose N used one reviewed follower-only route from the fresh torque-off pose to
`[0, -62, 90, -92, -5, 3.087886]` degrees. The exact 361-sample action passed
the current MuJoCo contact preview with no new or worsened kinematic contact.
The gateway completed all motion and hold samples, captured the native dual
camera streams and Pi still during the torque-on hold, and closed with follower
torque off.

## Local evidence

- Intrinsic receipt:
  `runs/pi-link-tag-calibration/20260726-current-camera-intrinsics-v1/receipt.json`
- Rejected first heldout:
  `runs/pi-link-tag-calibration/20260726-current-three-link-v2/heldout-evaluation.json`
- Fresh candidate and evaluation:
  `runs/pi-link-tag-calibration/20260726-current-three-link-fresh-validation-v1/`
- Fresh physical capture:
  `runs/pi-link-tag-calibration/20260726-current-camera-pose-n-fresh-heldout-v1/`
- Full-model overlay:
  `runs/pi-link-tag-calibration/20260726-current-three-link-fresh-validation-v1/full-model-overlay.jpg`

All run artifacts remain local and ignored by Git.
