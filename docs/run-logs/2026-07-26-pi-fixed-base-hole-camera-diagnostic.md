# Pi fixed-base hole-center camera diagnostic

## Outcome

Two CAD-native fixed-base centers pass the correspondence gate, but a single
camera-only adjustment is **not a genuine Pareto improvement**. The frozen
candidate remains unchanged.

The diagnostic improves aggregate base-landmark RMSE from `80.86 px` to
`55.11 px`, but aggregate tag RMSE worsens from `3.96 px` to `8.03 px`.
Tag RMSE worsens in every H, I, F, and fresh N frame. This rejects a
camera-only explanation for the base/tag disagreement.

## Correspondence gate

Both features are centers of cylindrical mesh topology, not arbitrary mesh
vertices:

1. `left_base_so101_v2` side fastener aperture:
   - local axis: Z
   - fitted visible-ring center:
     `[0.00729504, -0.03671297, 0.01482388]` m
   - radius: `0.00076152 m`
   - 40 supporting faces
   - median normal/radial alignment: `0.99856`
2. `left_sts3215_03a_v1` exposed output cylinder:
   - local axis: Y
   - fitted visible-ring center:
     `[0.00000002, 0.01882735, 0.01190472]` m
   - radius: `0.00267502 m`
   - 388 supporting faces
   - median normal/radial alignment: `0.99989`

Fixed-ROI circle detection finds exactly one physical center for each
feature in every frame. Peak-to-peak center variation is at most 2 px:

| Frame | Base fastener px | Output center px |
|---|---:|---:|
| H | `[577.5, 492.5]` | `[700.5, 425.5]` |
| I | `[576.5, 490.5]` | `[700.5, 426.5]` |
| F | `[575.5, 491.5]` | `[700.5, 425.5]` |
| fresh N | `[576.5, 490.5]` | `[699.5, 425.5]` |

## Shared-camera fit

One bounded six-DOF camera transform was fit jointly to all base-center and
existing tag-corner residuals. The fit used one camera across all frames.
Joint offsets, tag mounts, mesh geometry, intrinsics, and per-frame state
remained frozen.

| Frame | Landmark RMSE before → after | Tag RMSE before → after |
|---|---:|---:|
| H | `80.87 → 55.15 px` | `1.48 → 6.25 px` |
| I | `80.74 → 54.96 px` | `4.78 → 10.96 px` |
| F | `81.26 → 55.55 px` | `1.56 → 6.12 px` |
| fresh N | `80.55 → 54.78 px` | `5.76 → 8.42 px` |
| aggregate | `80.86 → 55.11 px` | `3.96 → 8.03 px` |

The diagnostic camera would move by `8.03 degrees` and `0.177 m`, yet still
leave `55.11 px` landmark RMSE while more than doubling tag RMSE. It fails
the predeclared Pareto rule: both aggregate RMSE values must improve and no
frame's tag RMSE may worsen.

This pattern is evidence of a remaining base-frame, assembly, or
CAD-to-physical feature-map inconsistency. It does not authorize substituting
the diagnostic camera for the current tag-validated candidate.

## Reproduction and local evidence

```bash
uv run --offline python tools/fit_pi_fixed_base_hole_camera.py \
  --candidate runs/pi-link-tag-calibration/20260726-current-three-link-fresh-validation-v1/candidate.json \
  --output-directory runs/pi-link-tag-calibration/20260726-fixed-base-hole-camera-v1
```

- receipt:
  `runs/pi-link-tag-calibration/20260726-fixed-base-hole-camera-v1/receipt.json`
  (`bc6b6d041336c4dad25037820a0d86a2eece9ec98bfa0fef0294a40bd846e4f8`)
- visualization:
  `runs/pi-link-tag-calibration/20260726-fixed-base-hole-camera-v1/visualization.jpg`
  (`b141d85005ce6bc9cadeb2218048df2f750f7562650ef416da97796109c237c6`)

All candidate-update, simulator-promotion, policy, and physical-task
authority remain false. No hardware ran.
