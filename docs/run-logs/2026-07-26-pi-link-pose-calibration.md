# Pi link-pose calibration — held-out result

Date: 2026-07-26
Proof class: `physical_static_tag_bundle_fit_diagnostic_only`

## Outcome

The calibration transaction acquired five admitted fitting poses and one
pre-frozen held-out pose through the reviewed follower-only gateway. Each
admitted pose contains:

- 361 exact float64 motion samples and an 80-sample torque-on hold;
- synchronized C922 and D405 source videos in one native AVFoundation session;
- D405 frame-to-joint host-clock alignment;
- one 1536×864 IMX708 still captured while follower torque remained on; and
- a final torque-off close.

The transaction did **not** promote simulator parameters. The best held-out
tag-corner result was `13.8367 px RMSE / 17.9756 px max`, and the corresponding
elbow-flex and wrist-flex zero offsets saturated the preregistered `±8°`
bounds. The camera-distortion family reduced fitting error but worsened the
same held-out pose to `23.3319 px RMSE`. These are rejected diagnostics, not
digital-twin parity.

## Capability gains

1. Rebound the live D405 USB-topology identity without rewriting the sealed
   historical common-session contract.
2. Restored live native dual-camera capture. A stationary check produced
   14 D405 frames at 5 Hz and 82 C922 frames at 30 Hz with no container gaps,
   duplicate PTS, or callback drops.
3. Added torque-on IMX708 hold capture to the reviewed motion path.
4. Identified tag 2 as a follower distal marker and tag 0 as a stationary
   control marker. Tag 1 was also detected in the two highest-diversity views.
5. Measured a repeatable gravity-release effect: shoulder lift can sag roughly
   19–48° after torque release depending on pose, sometimes beyond its
   calibrated minimum. This is actuator/load-path evidence and explains why
   post-release stills cannot be paired with torque-on joint targets.
6. Made setup recovery apply its separately reviewed in-range command anchor
   after torque enable, while leaving normal execution unchanged.

## Admitted fitting observations

| Pose | Final actual body joints (degrees) | Tag 2 center (px) |
|---|---|---|
| A | `3.165, -77.538, 82.593, -94.901, -60.615` | `931.00, 182.50` |
| B | `-11.780, -67.253, 72.484, -94.901, -79.692` | `985.75, 162.00` |
| C | `14.154, -77.978, 74.945, -96.044, -40.747` | `894.50, 117.75` |
| E | `-0.703, -67.780, 67.385, -95.868, -99.560` | `963.75, 107.25` |
| F | `19.253, -82.549, 92.527, -95.868, -20.703` | `882.75, 225.00` |

Pose D was frozen before fitting and opened once:

- final actual: `-19.780, -72.440, 85.319, -95.780, -20.703`;
- tag 2 center: `972.00, 245.75 px`.

## Fit results

Source:
`runs/pi-link-tag-calibration/20260726-bundle-fit-v3/receipt.json`
SHA-256:
`947274191945bdbb1f70a2cbc906a5268327f1d20c3aef45ba6855dcb46e33c2`

| Family | Fit RMSE (px) | Held-out RMSE (px) | Verdict |
|---|---:|---:|---|
| Nominal joint zeros | 7.8698 | 22.5178 | reject |
| Bounded joint offsets | 6.9546 | 13.8367 | reject; two offsets at bound |
| Bounded offsets + camera terms | 5.8444 | 23.3319 | reject; worse held-out |

The nominal camera seed uses Raspberry Pi's official `102°` horizontal
wide-FoV specification and the live 3072/4608 sensor crop, yielding
`932.8712 px` focal length at 1536×864. Distortion is a diagnostic family,
not a calibrated intrinsic claim.

## Verification and terminal state

- `44 passed`:
  `tests/test_native_dual_camera.py`,
  `tests/test_physical_gateway.py`,
  `tests/test_wrist_view_reposition.py`.
- `ruff` is not installed in the project runtime; no lint claim is made.
- Final follower preflight passed.
- Follower torque is off.
- No device configuration was rewritten.
- No policy, teleoperation, task, training, provider, or paid-compute action
  was run.

## Next calibration, not policy execution

The next useful transaction must add an independently measured constraint,
not more parameters against the same single distal tag:

1. establish a CAD-keyed tag-to-link transform or directly measure it;
2. admit tag 1 on at least three additional diverse poses to constrain the
   proximal chain separately from the distal tag;
3. freeze a second held-out pose before refitting; and
4. promote only if both held-outs pass without a parameter at its bound.

Until then, the digital twin has materially better physical calibration data
but not full parity.
