# Photo and Polycam Alignment Run Log

Request: verify the robot-arm, chessboard, table, and upper ledge relationships
with a comparison overlay instead of another visual-only scene pass.

Repo/path: `/Users/kelly/Developer/sim2claw`

Date: 2026-07-17 America/Chicago

Historical status: this log preserves the board pose measured on 2026-07-17.
The live workcell registration was superseded on 2026-07-18 when the owner
moved the board 72 mm toward the robots; see
[`2026-07-18-board-robotward-72mm-registration.md`](./2026-07-18-board-robotward-72mm-registration.md).

## Acceptance criteria

- Use the Polycam RoomPlan table as the metric reference surface.
- Apply the capture-to-RoomPlan transform before judging scan alignment.
- Register the new overhead photo to the measured table plane.
- Correct both arm mount positions, board placement/size, fiducial, tripod, and
  ledge relationship.
- Generate reviewable photo and textured-scan overlays plus a JSON report.
- Quantify residuals and keep photo estimates separate from metric evidence.

## Inputs and tools

| Input/tool | Role | Identity |
| --- | --- | --- |
| Polycam RoomPlan | Metric table dimensions and scan alignment transform | Capture `8873B66C-774C-48B1-B51D-338645867009` |
| Polycam textured mesh | Board-size/pose cross-check and historical layout | Exact verified `raw.gltf`, binary, and texture under ignored `external/` |
| Owner overhead photo | Current board, clamps, fiducial, and ledge landmarks | 2880 x 3840; SHA-256 `1201ca9ec105aabb8bb06d126ed582c1c1b30fb1f4f6c94de79f82d355d56ced` |
| NumPy 2.5.1 | Planar homography, inverse projection, and residual calculations | Directly pinned in `pyproject.toml` |
| Pillow 12.3.0 | Deterministic annotated overlay output | Directly pinned in `pyproject.toml` |
| MuJoCo 3.10.0 | Properly transformed textured-scan render and scene proof | Directly pinned in `pyproject.toml` |

## Critical correction

The earlier scan overlay applied only the y-up to z-up rotation and floor
offset. It omitted `optimized_roomplan.alignment_transform`, so the raw mesh
was displaced from the semantic RoomPlan table. The corrected scene applies
the exact inverse transform as MuJoCo position
`[0.0362411, 0.21954003, 1.2534494413]` and quaternion
`[0.69594089, 0.69594089, -0.12516501, -0.12516501]`.

After that correction, the measured table outline matches the textured table,
and the Polycam-capture board can be fit independently from the later photo.

## Current dimensional result

| Relationship | Result | Evidence class |
| --- | --- | --- |
| Table | 1.3513037 x 0.79171795 x 0.7799972 m | RoomPlan, high confidence |
| Board playing area | 0.3556 m | Photo registration and aligned-scan cross-check |
| Board overall | 0.4064 m | Aligned scan visual range 0.394–0.418 m |
| Board rear clearance | 0.0277 m | Overhead-photo planar registration |
| Left arm mount | `(-0.040, 0.365) m` | Overhead-photo registration |
| Right arm mount | `(-0.526, 0.365) m` | Overhead-photo registration |
| Clamp separation | 0.486 m | Overhead-photo registration |
| Left mount to nearest board edge | 0.329 m | Derived table-plane distance |
| Right mount to nearest board edge | 0.488 m | Derived table-plane distance |
| Sill bottom above table | 0.140 m | Single-photo estimate |
| Sill front overhang | 0.050 m | Single-photo estimate |

The two evidence surfaces contain different board poses. The Polycam capture
has the board center near `(-0.022, 0.182) m`; the later overhead photo places
it at `(0.040, -0.165) m`, a 0.352 m displacement. This is treated as a real
scene-state change, not registration noise. These values remain the historical
2026-07-17 result; they are not the current workcell pose.

## Verification and proof

Command:

```bash
uv run sim2claw compare-alignment \
  --photo /path/to/the/exact/overhead-Photo-1.jpg \
  --output-directory outputs/polycam_chess_table/alignment
```

| Proof | Result |
| --- | --- |
| Photo overlay | `photo-layout-overlay.png`; SHA-256 `2bd9dfb48edd4a8d7ad7a31ffd4ade80e2e66031c07628153542dc95ddb0dba8` |
| Polycam overlay | `polycam-scan-overlay.png`; SHA-256 `d00ead1d3b3f38b7bfedc3e4768f596acbaecfd75b9aa6ebcc6923d350630cf5` |
| Alignment report | `alignment-report.json`; content SHA-256 recorded by the command |
| Left clamp residual | 1.75 source pixels |
| Right clamp residual | 2.01 source pixels |
| Fiducial residual | 6.75 source pixels |
| Board corner residual | 0.0328 m RMS on the inferred table plane |
| Contract/unit tests | PASS, 9 tests |

## Proof boundary

This is a deterministic table-plane registration, not perfect 3D calibration.
The table dimensions and scan transform are metric. The board mesh bounds,
photo landmarks, ledge height/profile, and camera model remain estimates. The
single image does not identify lens distortion or provide hand-eye, joint-zero,
camera-intrinsic, or robot-base calibration. No hardware path or physical
authority was opened.

## Recommended next pass

For sub-centimeter 3D alignment, capture one calibration image with a measured
AprilTag grid spanning the table, record camera intrinsics, measure the board
outer edge and sill height/depth with a ruler, and measure each base axis from
two table edges. Those observations can replace the current photo-estimated
fields without changing the overlay workflow.
