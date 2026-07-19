# Pawn Source Expert at the 100 mm v3 Workcell

## Outcome

The deterministic geometric expert produced the first strict evaluator-admitted
canonical source episode in the current sixteen-pawn workcell. It moved
`tan_pawn_c8` to the unoccupied square `a6` under the exact deployed 20 Hz,
ten-physics-step sample-hold executor.

This is simulation expert/source-data evidence. It is not a learned-policy pass,
does not open held-out cases, and does not itself promote ACT or GR00T.

## Frozen workcell identity

- scene: `operator_updated_chess_workcell_v3`
- workspace: `workspace_board_fiducial_robotward_100mm_20260718_v3`
- board: `board_robotward_100mm_20260718_v3`
- board center in table frame: `(0.040, -0.065) m`
- total board displacement from the historical photo pose: `0.100 m`
- layout: `two_sided_sparse_pawns_rows_1_2_7_8_v1`
- reset: `c8_standoff_collision_free_reset_v1`

The 72 mm pose remains historical evidence only. Nothing in this run relabels
the earlier physical-video cohort or the frozen rook/king GR00T receipts.

## Source and evaluator identities

- source contract SHA-256: `737a368916643d083d400c42176ae044d0cd4a5e4697c9902e0b7e6b32367fda`
- evaluator contract SHA-256: `727daccd3ffece443742dd09a2a30f5e2a4db95c98de40f65efe65d6bf294a45`
- evaluator implementation SHA-256: `21887167c3b0725a9421326425aa4bd86099816fb201b4f3c3a331e0f0a736d4`
- recording id: `pawn-source-20260719T011500Z-d6e847dd`
- recording receipt SHA-256: `4fbe40bea0f177866f8d72a59323f1d7200e6aa7565533e9db2298bf1b3e1088`
- samples SHA-256: `fcf8153859a8b6d08eaa919b6c4ad1cc78ddb9b06fa9a1d884541ae6ac82bd94`
- admission verdict SHA-256: `0f0b2026b2bf13a416286b6f65ebccd7260b44bed0e690e2dc7409a22e690587`
- admission canonical payload SHA-256: `888d55399b55096034b98f4df58552cf890ce8d41794523da034088952ac9791`
- RGB manifest SHA-256: `42a7dd17d3836ea6856d050325c1809702d4be6ad35a307dd537a473bb36c2db`
- sample count: `562`
- top/wrist RGB files: `1,124`
- action owner: `geometric_expert`
- assistance frames: `0`

Generated source data is ignored by Git and retained under
`datasets/manipulation_source_recordings/`.

## Strict consequence result

| Measurement | Result | Gate |
| --- | ---: | ---: |
| Maximum rise | 100.566 mm | at least 40 mm |
| Final XY error | 9.954 mm | at most 15 mm |
| Final height error | 1.011 mm | at most 5 mm |
| Final upright cosine | 0.9999999998 | at least 0.95 |
| Final speed | 0.168 mm/s | at most 20 mm/s |
| Gripper clearance | 119.228 mm | at least 35 mm |
| Worst other-piece displacement | 0.000082 mm | at most 6 mm |
| Wrong-piece contact | false | required false |
| Final jaw contact | false | required false |

The evaluator replayed all 562 recorded float32 actions and matched every saved
MuJoCo integration state exactly. All 562 rows are authorized as ordinary
imitation rows by this evaluator verdict.

## Adapter proof

- GR00T adapter: 562 rows, SHA-256
  `5826644376b2980986a8a338d5173bece1a48467d7d8ecf36082dea8b2cdc701`
- ACT adapter: 562 rows, SHA-256
  `2fb0bcafa62f6ae979bf058c4f1213c91c493f5ce0b4fc644ff793d19dcdc6c1`

Both outputs retain source-row and admission lineage. GR00T receives only
top/wrist RGB paths, language, joint positions, and joint targets. Evaluator-only
integration state and contact traces remain outside both policy adapters.

## Next gate

This single source episode is sufficient to prove the source/evaluator/adapter
mechanism, but not enough to claim a dynamic multi-piece learned policy. Before
GPU work, a separately receipted GR00T dataset must contain only admitted
training episodes, zero held-out rows, exact RGB/action lineage, and a loader
preflight that proves its action-chunk semantics. Promotion remains an
independent zero-assistance CPU/fp32 consequence decision.
