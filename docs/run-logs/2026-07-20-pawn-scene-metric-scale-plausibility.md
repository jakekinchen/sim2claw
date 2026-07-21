# 2026-07-20 IMG_5349 board-scale plausibility

Command:

```text
uv run --offline python scripts/run_pawn_scene_metric_scale.py
```

## Bound evidence

- Source video SHA-256:
  `0079c19d5a321dd3613924f4a7e0838a4f99943b0833a0b8bed81a12d303dfa8`
- SfM frame SHA-256:
  `0ada1e8d9459fd66e826a38e48125a2c3cda611253eeaae4f4b842060d2a1e7d`
- Real 3DGS PLY SHA-256:
  `f8f3bfe0a0f1fa13d54e47602dbf43f8e0448178c0e85f0f22a5f2115530443b`
- Camera: fixed OPENCV intrinsics from the 46-image, 5,016-point exhaustive
  global SfM; mean bundle reprojection error 1.003 px.
- Fiducial: tag36h11 id 0; source-design black-border side 80 mm; post-print
  physical measurement unavailable.

## Measurement

The detected tag mean edge is 129.61 px and nominal-tag PnP reprojection RMS is
1.529 px. The reviewed Hough/TLS grid fit resolves the board playing-area
corners in the same frame. With the board surface 16--25 mm above a parallel
tag plane, the mean reconstructed playing side is 361.51--356.19 mm. The
conservative envelope over all four reconstructed edges is 336.47--373.55 mm;
opposite edges disagree by about 19 mm and that systematic remains visible.

| Hypothesis | Required tag black side | Required nominal rescale | Verdict |
|---|---:|---:|---|
| registered 355.6 mm | 78.69--79.87 mm | -1.63% to -0.16% | consistent |
| trace-fit 301.3 mm | 66.68--67.67 mm | -16.65% to -15.41% | materially inconsistent |

## Interpretation

The 355.6 mm board is physically plausible under the nominal printed-tag
model. The 301.3 mm trace optimum is much more plausibly compensation for
another simulator mechanism than the real board size. The result does not
establish metric scale because the print was never measured and the 3DGS is
monocular. It constrains the next simulator ablations but cannot promote a
physical calibration.

Generated artifacts are ignored under
`outputs/pawn_scene_metric_scale_plausibility_v1/`; the tracked contract,
implementation, test, and this regeneration command bind the result.
