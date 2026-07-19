# Board and Fiducial 100 mm Workspace Registration

Date: 2026-07-18  
Proof class: operator-reported simulation workspace registration  
Physical authority: false

## Change

The owner reported that the physical chessboard is now 100 mm total toward the
robots from the 2026-07-17 overhead-photo registration, along table-frame `+y`.
The owner also reported moving the AprilTag paper with the board.

The previous simulator change moved only the chessboard 72 mm. This update
therefore applies different increments while reaching the same total offset:

| Component | Photo-registered center (m) | Prior simulated center (m) | Current center (m) | Increment now | Total |
| --- | --- | --- | --- | --- | --- |
| Chessboard | `(0.040, -0.165)` | `(0.040, -0.093)` | `(0.040, -0.065)` | 28 mm | 100 mm |
| Fiducial sheet | `(0.020, 0.080)` | `(0.020, 0.080)` | `(0.020, 0.180)` | 100 mm | 100 mm |

Current identities:

- workspace: `workspace_board_fiducial_robotward_100mm_20260718_v3`
- board: `board_robotward_100mm_20260718_v3`
- fiducial: `fiducial_robotward_100mm_20260718_v2`

The configuration remains an operator-reported scene estimate. It is not a
camera calibration, robot-base calibration, collision-validation result, or
grant of physical control authority.

## Propagation

The capture configuration is the single current-pose source consumed by the
MuJoCo scene, board square coordinates, Studio catalog and posters, and new
teleoperation recording receipts. New receipts carry the paired workspace,
board, and fiducial identities.

The historical 72 mm board pose remains resolvable as
`operator_updated_chess_workcell_v2`. Existing recordings and receipts are not
rewritten. The frozen `pawn_rank12_bidirectional_v1` product evaluation still
binds `board_robotward_72mm_20260718_v2`; testing against the current workspace
requires an explicitly reviewed requalification or a new frozen evaluation,
not a silent edit to that contract.

## Geometry effects

- Board rear clearance: approximately 0.1277 m.
- Reaching-arm mount to nearest board edge in the table plane: approximately
  0.2288 m.
- Folded-arm mount to nearest board edge in the table plane: approximately
  0.4263 m.

## Validation

- `uv run pytest -q`: 77 tests and 10 subtests passed.
- `uv run sim2claw scene-info`: reported the v3 workspace, board center
  `(0.040, -0.065) m`, and fiducial center `(0.020, 0.180) m`.
- `uv run sim2claw studio-assets`: regenerated three current-scene posters and
  their source-hash receipt; visual inspection confirmed the mug on the left
  sill and the fiducial sheet translated toward the robots with the board.
- `uv run sim2claw grasp-probe`: passed in simulation with a 0.0935 m piece
  rise and continuous jaw contact during lift and hold.
- `git diff --check`: passed.
