# Pi fixed-base registration diagnostic

## Outcome

The stationary `left_base` silhouette is **not a reliable next camera
constraint from the current H, I, F, and fresh N images**. This is a
diagnostic terminal negative, not a candidate update.

The frozen candidate camera and intrinsics were reused byte-for-byte from
`runs/pi-link-tag-calibration/20260726-current-three-link-fresh-validation-v1/candidate.json`
(SHA-256 `115428d746867bd0ca1f25fb75f3ccaed7a928342fc980f995bcfce484ab50b5`).
There was no per-frame camera adjustment and no candidate parameter change.

## Diagnostic

The projection rasterizes every triangle from all four group-2 visual meshes
owned by the MuJoCo `left_base` body:

- `left_base_motor_holder_so101_v1`
- `left_base_so101_v2`
- `left_sts3215_03a_v1`
- `left_waveshare_mounting_plate_so101_v2`

It compares their union contour against Canny edges that remain present,
after a 2 px dilation, in at least three of the four source images. The
result is:

- 797 projected contour samples
- 17.3% within 4 px of a consensus edge
- 33.4% within 8 px
- 14.2 px median nearest-edge distance
- 45.0 px p90 nearest-edge distance

The visualization shows why this should fail closed: the black clamp hides
much of the lower and left base boundary, while the upper housing boundary
merges with the moving shoulder/column. Background and housing edges create
additional competing contours. A generic edge-distance score therefore
cannot distinguish the intended physical base outline defensibly.

## Minimal follow-up

Use two explicit, fixed landmarks rather than a silhouette evaluator:

1. the upper-left outer corner of the base motor housing;
2. the upper-right housing-to-column corner.

Label those same physical landmarks in H, I, F, and N, then report their
reprojection under the single frozen camera. Do not fit the camera per frame.
This is the smallest measurement that can disambiguate the base from the
clamp, shoulder, and background.

## Reproduction and evidence

```bash
uv run --offline python tools/diagnose_pi_fixed_base_registration.py \
  --candidate runs/pi-link-tag-calibration/20260726-current-three-link-fresh-validation-v1/candidate.json \
  --output-directory runs/pi-link-tag-calibration/20260726-fixed-base-registration-diagnostic-v1
```

Local ignored evidence:

- receipt: `runs/pi-link-tag-calibration/20260726-fixed-base-registration-diagnostic-v1/receipt.json`
  (`5ac2c833eb6b9440deac43123f0de2bd79f81ea7ea40ad4ff2d2a18a824a30e0`)
- visualization:
  `runs/pi-link-tag-calibration/20260726-fixed-base-registration-diagnostic-v1/visualization.jpg`
  (`f56764cdffdbb4a0b0270c242741a8794a4ba4af7f3f15f2fbc7cb19e5207dfa`)

All camera-update, simulator-promotion, policy, and physical-task authority
remain false. No hardware ran.
