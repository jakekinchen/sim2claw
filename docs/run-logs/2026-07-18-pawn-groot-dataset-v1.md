# Pawn GR00T Dataset v1

## Outcome

The first pawn-specific GR00T dataset was derived from the strict, evaluator-
admitted canonical C8-to-A6 source episode in the current 100 mm workcell. The
dataset contains one training episode and zero held-out rows.

This closes the local source-to-LeRobot proof. It does not authorize GPU
training until the same payload passes the pinned NVIDIA loader on Brev, and it
does not promote a learned policy.

## Frozen identities

- dataset contract: `chess_pick_place_pawn_groot_dataset_v1`
- dataset contract SHA-256:
  `19b2a17e3a45e908ffba79814971b6149601ecccd4c33eaa4e1232ac00230ed8`
- dataset receipt SHA-256:
  `594d316ec8b99534a868f0c3b6b4c973eaceb6664d0250d587ff3417bc350c3e`
- payload manifest SHA-256:
  `324be03202c0eccd6c984f7e6312f951e83d1ba8052f9221ae29d87733907c8d`
- builder module SHA-256:
  `b32a1074c0c7c4dc7a4504e42c1b8223f66a5f2acbd6f9ba665451d93fd3e013`
- source recording: `pawn-source-20260719T011500Z-d6e847dd`
- source admission verdict SHA-256:
  `0f0b2026b2bf13a416286b6f65ebccd7260b44bed0e690e2dc7409a22e690587`

The scene remains `operator_updated_chess_workcell_v3`, workspace
`workspace_board_fiducial_robotward_100mm_20260718_v3`, board
`board_robotward_100mm_20260718_v3`, and reset
`c8_standoff_collision_free_reset_v1`.

## Dataset payload

- format: GR00T LeRobot v2.1
- episodes: 1
- source/output frames: 562
- tasks/prompts: 1
- FPS: 20
- state/action dimensions: 6/6
- video: 224 x 224 H.264, canonical top RGB mapped to `front`
- wrist RGB: retained and hash-bound in the canonical source, not consumed by
  this first single-view GR00T dataset
- action owner: geometric expert
- assistance frames: 0
- held-out rows: 0

Raw evaluator-only integration state, object poses, and contact traces are not
present in policy columns. Per-frame lineage binds the GR00T row to both source
camera hashes, its source action owner, and the admission payload.

## Local loader proof

- local preflight receipt SHA-256:
  `c3deb13a09a9f033d1dcaea32fc8729fc6654e57e3a7c2953df5986d2aaf6f1c`
- effective 16-step starts: 547
- action target slots: 8,752
- action scalars: 52,512
- target-index matrix SHA-256:
  `9c0c29f49ce1e1c793494fb55c34d91ffc8fc45d03468452d0cdf332eec3f600`
- all 562 source actions occur in at least one target chunk
- padding: none
- cross-language-boundary targets: zero
- encoded video: 562 frames at 20 FPS

The preflight rehashes the exact payload inventory, reads the Parquet data,
constructs the full action-index matrix independently, and checks the encoded
video metadata. Its `training_authorized_by_this_local_preflight` field is
false: a remote preflight through pinned NVIDIA commit
`23ace64f17aa5015259b8609d371eb61a357c776` is still mandatory.

## Authority boundary

This v1 dataset is deliberately narrow evidence for the frozen C8-to-A6 pawn
case. The historical physical recording cohort remains 72 mm evidence and is
used only for joint-response diagnostics and a visual camera-transfer preview;
it contributes zero rows here and is not relabelled as current 100 mm spatial
evidence. Multi-piece or physical claims require new evaluator-admitted source
episodes and new receipts.
