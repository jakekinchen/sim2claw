# AI Build Run Log

Request: Build the table-and-chess simulation from the supplied Polycam link,
then correct it because the first scene did not align with the supplied workcell
photo.

Repo/path: `/Users/kelly/Developer/sim2claw`

Date: 2026-07-17 America/Chicago

Owner constraints: clean-room implementation; imported archive inert; separate
proof classes; generated assets outside Git; physical authority closed.

## Acceptance criteria

- Preserve the capture's measured table dimensions and exact source identities.
- Use the correction photo as the visual composition truth surface.
- Include two white edge-mounted SO-101 arms: left reaching, right folded.
- Put black pieces at the near side and the board near the rear/window side.
- Include the visible fiducial sheet, window/sill/blinds, and left tripod.
- Render through a front-left portrait camera similar to the photo.
- Compile, step, and render on Apple Silicon without opening hardware paths.
- Mark photo-derived placement separately from RoomPlan measurement evidence.

## Model and tool roles

| Role | Model/tool | Purpose | Output |
| --- | --- | --- | --- |
| Specification and implementation | Codex | Clean-room architecture, scene correction, tests, documentation | Runtime and source-controlled scene generator |
| Metric reference | Polycam RoomPlan | Table dimensions, center, and yaw | Frozen config with exact artifact hashes |
| Visual reference | Owner correction photo | Scene composition, handedness, arm roles, props, portrait framing | Frozen JPEG identity and estimate labels |
| Robot model | MuJoCo Menagerie `robotstudio_so101` | Public articulated SO-101 geometry, joints, actuators, collisions | Exact upstream directory vendored at commit `71f066a…` |
| Physics/render | MuJoCo 3.10.0 | Attach two robot specs, compile, settle, and render | PNG, MJCF, JSON report |
| Environment | uv / Python 3.12 | Reproduce locked runtime | `uv.lock`, `.venv/` |
| Texture conversion | Pillow 12.3.0 | Convert verified Polycam JPEG texture to PNG | Ignored external derivative |

## Source and generated assets

| Asset | Source | Output path | License/notes |
| --- | --- | --- | --- |
| Polycam OBJ/MTL/PNG | Owner-provided capture `8873…7009` | `external/polycam/8873…7009/` | Ignored; do not redistribute |
| Correction photo identity | Owner attachment, 2880 x 3840 | Recorded in capture config | SHA-256 `b673f959ddf608e1c64098e8c1194196741c5cbd938f2756c3bf2b20b1901889`; not copied into repo |
| SO-101 model | Fresh sparse checkout of `google-deepmind/mujoco_menagerie` | `third_party/mujoco_menagerie/robotstudio_so101/` | Apache-2.0; commit `71f066ad0be9cd271f7ed58c030243ef157af9f4`; upstream files unchanged |
| Photo-aligned proof | Repo-native scene plus two attached SO-101 specs | `outputs/polycam_chess_table/photo-aligned-final.{png,xml,json}` | Generated proof; ignored |

## Correction record

The rejected first render had only the measured table, generic board/pieces,
and a landscape workcell camera. It omitted the two photographed arms,
fiducial, tripod, and window environment. The first robot correction was then
mirrored. Camera-side inspection exposed that error, after which the reaching
and folded roles, fiducial, and tripod were swapped to the photographed sides.

The accepted simulation contract now contains 56 bodies, 382 geoms, 44 joints
(32 free piece joints plus 12 robot joints), and 12 position actuators. The
final portrait image is 900 x 1200, settles for 500 steps, and has SHA-256
`840197f7e32f810535ccb734aef901a7cbd6ca818174905aaacf20d246f00994`.

## Verification

| Proof surface | Command | Result |
| --- | --- | --- |
| Unit/contract tests | `uv run python -m unittest discover -s tests -v` | PASS, 7 tests |
| Mac doctor | `uv run sim2claw doctor --target auto --render-probe --json` | PASS; Python 3.12.12, MuJoCo 3.10.0, arm64, compile/step/render; probe SHA-256 `0f501254…9dad3b` |
| Final render | `uv run sim2claw render --output outputs/polycam_chess_table/photo-aligned-final.png --width 900 --height 1200 --settle-steps 500` | PASS; image SHA-256 `840197f7…00994` |
| Visual inspection | Final PNG compared to owner photo | Major composition aligned: active left arm, folded right arm, rear board, near black pieces, fiducials, tripod, window/blinds, portrait view |

## Known gaps

- Only table dimensions/pose come from high-confidence RoomPlan evidence.
- Board placement, robot mounts/joint poses, background props, and camera are
  single-photo estimates, not calibrated transforms.
- The procedural chess pieces match type/color/count and near/far orientation,
  not the exact per-square state or detailed carved meshes in the photo.
- Static pose rendering does not prove collision-free manipulation reach,
  grasp success, evaluator readiness, or sim-to-real equivalence.
- NVIDIA/EGL has a fail-closed preflight contract but no live NVIDIA proof.
- This log describes an uncommitted working tree and has no final commit ID.

## Next reviewed slice

Freeze the first manipulation task, training and held-out seeds, and a separately
owned deterministic CPU/fp32 evaluator before training code is introduced.
