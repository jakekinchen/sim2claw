# New-scene AprilTag capture sweep

Date: 2026-07-26
Proof class: `physical_static_fiducial_calibration_diagnostic_only`

## Outcome

Three reviewed follower-only calibration poses captured the newly visible tag 3
in the fixed wide Pi view. Tag 3 moves with tag 0 under shoulder pan and is
therefore classified as a second `left_shoulder` observation, not a fixed
workcell or base datum.

The additional observation does not improve the accepted three-tag model. The
only admissible follow-up kept the validated camera, tag 0-2 mounts, and joint
offsets byte-for-value frozen and fit tag 3 alone from poses H and I. Its pose-D
score is retrospective because an earlier broad refit had already consumed D.
That retrospective score was rejected at `43.7244 px` corner RMSE and
`75.9570 px` maximum. The accepted fresh three-tag pose-N result therefore
remains unchanged at `5.7563 px` RMSE and `9.2818 px` maximum.

The large tag 18 visible at the bottom of the Pi image belongs to the current
20-tag printed sheet. It was not treated as the older two-tag simulation
graphic or as an automatically registered world datum.

## Captures

| Pose | Final follower degrees | Pi tag IDs | Capture SHA-256 |
| --- | --- | --- | --- |
| H | `[9.318681, -61.098901, 92.879121, -94.197802, -29.318681, 3.087886]` | `0, 2, 3, 18` | `2ea77ccb5630e73b2a4090a8456da7cc840acb6e0fc6a7cbc1d4375f59942a00` |
| I | `[29.098901, -69.978022, 85.406593, -94.285714, 49.362637, 3.087886]` | `0, 3` | `ff5e2959a253228f8ade42fd314f48278dc57a866e9424442fd08eb5f056c9fe` |
| D | `[-19.604396, -69.978022, 88.043956, -94.285714, -19.384615, 3.087886]` | `0, 2, 3` | `949e8d191d72953e4b0ed4ee8a60ffff124b86e4ffd9ae7452f326d5da269699` |

The C922 was also captured at `1920 x 1080` after every move. It saw the wider
board-and-arm scene but did not decode a tag face in these oblique views.

## Physical closeout

All three routes passed the existing MuJoCo contact preview and the reviewed
gateway completed each stage. Every execution receipt records
`physical_follower_torque_enabled: false` at close. No policy or task command
was executed.

Generated captures and receipts remain ignored under:

- `runs/pi-link-tag-calibration/20260726-new-scene-tags-pose-h-v1/`
- `runs/pi-link-tag-calibration/20260726-new-scene-tags-pose-i-v1/`
- `runs/pi-link-tag-calibration/20260726-new-scene-tags-pose-d-v1/`

The frozen retrospective four-tag implementation and full rejection accounting
are recorded separately in
`docs/run-logs/2026-07-26-pi-four-tag-shoulder-retrospective.md`.

## Authority boundary

This sweep establishes a kinematic body classification for tag 3 and records
three static calibration captures. It does not promote camera intrinsics,
robot geometry, contact, actuator/load behavior, task consequence, policy
transfer, or physical task authority.
