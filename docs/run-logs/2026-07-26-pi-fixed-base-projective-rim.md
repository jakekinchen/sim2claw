# Pi fixed-base projective-rim evaluation

Date: 2026-07-26
Proof class: `physical_image_frozen_projective_rim_diagnostic_only`

## Outcome

The prior `80.86 px` fixed-base center-point contradiction does **not**
disappear when the exact projective rim observable is used.

With the current candidate frozen, the depth-visible near CAD rims have:

- `78.29 px` aggregate CAD-to-physical-arc RMSE;
- `78.01 px` median;
- `95.17 px` p90;
- zero of 5,760 rim samples within 10 px of a
  tangent-compatible physical arc; and
- `78.26 px` symmetric oriented RMSE.

This is only a 3.2% reduction from the prior fitted-center RMSE and remains
almost eight times the predeclared 10 px disappearance threshold. Neither the
near nor far exact rim supports a model or camera correction.

## Strict no-fit method

No camera, intrinsics, joint value, joint-zero offset, tag mount, feature
center, mesh transform, or per-frame value was optimized.

For each of the two existing topology-derived features, the evaluator:

1. reselects the exact cylindrical side faces using the frozen topology
   specification;
2. extracts the two closed degree-two boundary loops from mesh edge
   incidence, yielding 20/20 vertices for the base aperture and 72/74 vertices
   for the servo output;
3. samples each exact polygonal rim at 720 arc-length-spaced locations;
4. transforms it through its owning `left_base` geom and body;
5. projects it with candidate
   `115428d746867bd0ca1f25fb75f3ccaed7a928342fc980f995bcfce484ab50b5`;
6. ranks near and far rims only by mean positive camera depth; and
7. scores tangent-compatible nearest-arc distances in both directions.

Physical arc support is extracted independently in the two already
preregistered feature ROIs using a fixed 5×5 Gaussian blur, fixed Canny
thresholds `[30, 90]`, and Sobel edge normals. Every oriented edge pixel in
each ROI is admitted. This deliberately conservative choice allows clutter to
make the nearest-arc residual smaller; it cannot manufacture a larger
contradiction by selectively discarding inconvenient edge support.

The tangent-normal compatibility tolerance is fixed at 45 degrees. The
previous Hough-fitted image-circle centers and their `80.8556 px` aggregate
RMSE are copied into the receipt only as diagnostic metadata. They are not
used for arc extraction, rim selection, visibility, or scoring.

The preregistered decision says the contradiction disappears only if the
depth-visible near-rim CAD-to-physical-arc RMSE and p90 are both at most
10 px.

## Results

Depth-visible near-rim CAD-to-physical-arc results:

| Frame | Base aperture RMSE / median / p90 px | Servo output RMSE / median / p90 px |
|---|---:|---:|
| H | `93.79 / 93.92 / 96.26` | `61.38 / 61.47 / 63.91` |
| I | `94.19 / 94.58 / 96.26` | `60.14 / 60.09 / 62.75` |
| F | `94.41 / 94.58 / 96.95` | `60.11 / 60.09 / 62.75` |
| fresh N | `94.24 / 94.58 / 96.26` | `50.67 / 50.57 / 52.80` |
| aggregate | `94.16 / 94.37 / 96.44` | `58.23 / 59.35 / 62.89` |

The fresh-N servo residual is smaller because its conservative ROI admits
more edge clutter: 77 pixels versus 41–59 in H/I/F. Even this optimistic
support leaves `50.67 px` RMSE and zero samples within 10 px.

Scoring the far rims does not reverse the result:

| Feature | Far-rim RMSE / median / p90 px |
|---|---:|
| Base aperture | `94.83 / 95.04 / 97.10` |
| Servo output | `57.01 / 58.14 / 61.67` |

The exact near/far rim distinction therefore changes the residual by roughly
one pixel, not the 50–95 pixels required to reconcile the CAD and physical
arcs.

## Evidence and authority

Reproduction:

```bash
uv run --offline python tools/evaluate_pi_fixed_base_projective_rims.py \
  --candidate runs/pi-link-tag-calibration/20260726-current-three-link-fresh-validation-v1/candidate.json \
  --output-directory runs/pi-link-tag-calibration/20260726-fixed-base-projective-rim-v1
```

- receipt:
  `runs/pi-link-tag-calibration/20260726-fixed-base-projective-rim-v1/receipt.json`
  (`3355f35347a3d0c24fee0c2a5564e9d4171605a6e88c4baa3a6c29383af1665d`);
- annotated H/I/F/N arcs and exact rims:
  `runs/pi-link-tag-calibration/20260726-fixed-base-projective-rim-v1/visualization.jpg`
  (`f2515fbf52ed207f96165aae28d88b6b3f8d38def42dc3eb43f41832f8217e67`);
- prior center receipt, metadata only:
  `bc6b6d041336c4dad25037820a0d86a2eece9ec98bfa0fef0294a40bd846e4f8`.

All camera-update, simulator-promotion, policy, and physical-task authority
remain false. No hardware, paid compute, or Brev resource ran.
