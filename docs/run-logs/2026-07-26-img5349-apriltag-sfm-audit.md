# IMG_5349 AprilTag/SfM fusion audit

Date: 2026-07-26  
Proof class: `source_video_static_fiducial_sfm_diagnostic`

## Outcome

The accepted early COLMAP component contains one robustly triangulatable
`tag36h11` marker, but it is a historical table/board marker, not a link
fiducial. There are therefore **zero legitimate tag-to-link correspondences**
between IMG_5349 and the current arm-tag model.

This is a useful negative result. Reusing the integer ID `0` in a later
arm-mounted tag does not preserve the physical marker, mounting transform, or
capture-time datum.

## Bounded source scan

The audit used only the 21 registered images in the accepted coherent
`registered_frames_1_through_25` component. The detector used the pinned
OpenCV `tag36h11` dictionary, subpixel corner refinement, and zero error
correction.

Five exact detections were recovered:

- ID `0`: frames `1`, `2`, `17`, and `18`;
- ID `1`: frame `22`;
- IDs `2` and `3`: absent.

ID `1` is excluded because a single registered view cannot triangulate it.
No newly added current-scene tag was projected backward into the historical
3DGS.

## Strict ID 0 triangulation

All four ID 0 corners were triangulated jointly across the four registered
views. Every explicit diagnostic gate passed:

| Metric | Result | Gate |
| --- | ---: | ---: |
| Corner observations | 16 | at least 12 |
| Reprojection RMS | `2.960902 px` | at most `4 px` |
| Reprojection maximum | `6.199551 px` | at most `7 px` |
| Minimum depth | `3.096582` SfM units | positive |
| Maximum pair parallax | `35.692213 deg` | at least `10 deg` |
| Side coefficient of variation | `0.012885` | at most `0.05` |
| Plane maximum residual | `0.004208` SfM units | diagnostic |

Applying the tracked IMG_5349 board-conditioned Sim(3) maps the marker to:

```text
center = [-0.0677446, 0.7440937, 0.7758274] m
mean detected side = 0.0778866 m
```

The center is `25.0566 mm` below the chessboard playing surface and
`67.3446 mm` outside the `a8-h8` playing edge in XY. This agrees with its
visible placement on the table beside the board and rejects treating it as
the current `left_shoulder` marker.

## Reproduction

The clean-room tool reads the public COLMAP binary layout directly and uses
only existing pinned NumPy and OpenCV dependencies:

```bash
uv run python tools/audit_img5349_apriltag_sfm.py \
  --images /Users/kelly/Developer/robo-scan/artifacts/private/IMG_5349-0079c19d-global-sfm-v1/images \
  --model /Users/kelly/Developer/robo-scan/artifacts/private/IMG_5349-0079c19d-global-sfm-v1/sparse-exhaustive/0 \
  --output runs/img5349-apriltag-fusion/20260726-early-component-v1/receipt.json

uv run pytest -q tests/test_img5349_apriltag_sfm_audit.py
```

The focused tests pass: `2 passed`. The ignored receipt is at
`runs/img5349-apriltag-fusion/20260726-early-component-v1/receipt.json`, with
SHA-256
`71e11aaba89273cecf4a2f745a7b87dc4db0fa0a12dec29ba3faa5e754a393e7`.

## Bounded next method and authority

The historical ID 0 can serve only as a board-adjacent world check for
IMG_5349. Current arm tags may be fused with current camera captures after
their tag-to-link transforms are measured; they cannot retroactively
calibrate a historical reconstruction through reused IDs.

This audit grants no metric-scale, tag-to-link, robot-geometry,
collision/contact, task, policy-transfer, or physical-control authority.
