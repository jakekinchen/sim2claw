# Scene-v2 pawn source success — 2026-07-18

## Scope

- Scene: `operator_updated_chess_workcell_v2`
- Board pose: `board_robotward_72mm_20260718_v2`
- Board center: `[0.04, -0.093]` m in the table frame
- Layout: `two_sided_sparse_pawns_rows_1_2_7_8_v1`
- Training case: `tan_pawn_c8` to the empty square `c6`
- Held-out rows queried or exported: `0`
- Physical authority: `false`

The old sparse rook/king GR00T evidence grants no authority for this pawn
episode. The source is model-agnostic and carries no model or checkpoint
identity.

## Source and replay identities

- Source recording: `pawn-source-20260718T233812Z-d815a8a1`
- Source receipt SHA-256:
  `02a3176c52d66ac214466cc8cba888bcc69a95cb741011fd69b0e60dae4eb926`
- Samples SHA-256:
  `cbe758de54ce8237e47e217606a9244c9f33153e701d2e6f1cced3dce2936ed2`
- Source contract SHA-256:
  `ff032e80bfb352697cfe67daa51d22a09004d2c34715b7f3d679057090d0d8eb`
- Pawn evaluator SHA-256:
  `c5da67a0bdafefb626ddd633a1f1ce033612dd3d8cc958592c19f6c64e87b3f0`
- Admission payload SHA-256:
  `522248f33016ede6535ac4655e997e21e26a517fd5d95ba22d8e1b9e1982c516`
- Admission receipt SHA-256:
  `cea0f9624c5fd7fdb5951208c37dc469df646262ee9c2a7c8af918af265d7f68`

The source has 562 recorded and 562 executed float32 actions. Every action was
replayed with exact 20 Hz / ten-physics-step sample hold, and every saved
`mjSTATE_INTEGRATION` row matched bitwise.

## Consequence result

The separate evaluator returned `ordinary_strict_success`:

- maximum rise: `111.887 mm` (`>= 40 mm`)
- final XY error: `14.824 mm` (`<= 15 mm`)
- final height error: `1.011 mm` (`<= 5 mm`)
- upright cosine: `0.99999999998` (`>= 0.95`)
- final speed: `0.000192 m/s` (`<= 0.02 m/s`)
- gripper clearance: `124.923 mm` (`>= 35 mm`)
- worst other-pawn displacement: `0.000082 mm` (`<= 6 mm`)
- wrong-piece contact: `false`
- final jaw contact: `false`
- assistance frames: `0`

The successful mechanism was an airborne state-feedback re-center followed by
a 5 mm controlled lower, partial in-place release, 80 mm vertical extraction,
and full opening only after clearance. Earlier full-opening and horizontal
retreat variants were preserved as negative diagnostic reasoning and were not
admitted as imitation rows.

## Policy adapters

- ACT adapter: 562 rows, SHA-256
  `694bc11e412535b3a04322ea7d4aef6b39c1d3811946e1429efcc7d5e2d5b396`
- GR00T adapter: 562 rows, SHA-256
  `26f0ed40be4435c1e88cb9d1aba8b79628190fc63d8f7db10a34e65c43126731`
- Privileged-state strings in either adapter: `0`

The adapters are eligible source rows, not trained checkpoints and not policy
promotion evidence. A learned ACT or GR00T policy still needs a new frozen
dataset receipt, training identity, and zero-assistance development/held-out
evaluation chain for this scene.

## Ignored artifacts

The generated source directory is intentionally ignored by Git:

`datasets/manipulation_source_recordings/tan-pawn-c8-to-c6-scene-v2__pawn-source-20260718T233812Z-d815a8a1`

The synchronized top/wrist diagnostic video in that directory has SHA-256
`ebbf64c7da7d515dc4fca93b493be8f2aaf5f3dc2ee0236707bfa22b5e0ba806`.
