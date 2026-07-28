# Executor session 032: D405 wrist AprilTag observation

Date: 2026-07-25

## Outcome

Implemented a bounded offline D405 AprilTag observer and receipt. The command
uses the already pinned OpenCV 4.13 `DICT_APRILTAG_36h11` detector, selects the
largest valid ID `0` observation, and optionally extracts its selected frame.
A native common-session report can bind the exact 424x240, 5 fps, `yuvs` D405
video and device identity to the receipt.

The current physical-canary wrist video was scanned as a baseline. All 14
frames were read and bound to native recorder report SHA-256
`50f4839fb212e889133197f3f813275d6e08f7fb426fc7be63024ab3ea2ac389`.
No AprilTag was observed in that wrist orientation. This is a camera-framing
negative, not a registration failure.

The contract retains the existing source-design evidence as `tag36h11` ID `0`,
nominal 80 mm black-border side and nominal 100 mm full printed side. Neither
dimension is treated as a physical measurement. Metric registration still
needs:

- a measured physical tag black-border side;
- exact-mode D405 RGB intrinsics and distortion;
- a measured tag-to-board or tag-to-workcell transform;
- a measured D405 optical-to-wrist/tool transform; and
- the robot joint pose synchronized to the selected frame.

## Validation

```text
uv run --offline pytest -q tests/test_d405_apriltag_observation.py
5 passed in 0.11s

uv run --offline pytest -q \
  tests/test_d405_apriltag_observation.py \
  tests/test_pawn_scene_metric_scale.py \
  tests/test_native_dual_camera.py
11 passed, 1 skipped in 0.16s

git diff --check
pass
```

No camera was opened, no robot gateway was constructed, no hardware moved, no
provider was called, and no Brev resource was used.
