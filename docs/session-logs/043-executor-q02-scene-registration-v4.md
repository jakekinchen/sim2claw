# Executor log 043: Q02 scene registration v4

Date: 2026-07-27

Decision: Q02 acceptance checks passed.

## Result

The fit-only candidate selected `reflect_ranks`, mapping physical C2 to the
scene's C7 coordinate, followed by a bounded table-frame board-center shift:

```text
delta_xy_m = [+0.03681671893371323, +0.06607855419702145]
center_xy_m = [+0.07681671893371322, +0.0010785541970214502]
yaw_relative_to_table_degrees = 1.55 (unchanged)
joint_zero_offsets_changed = false
fit_grasp_row = 242
modeled pawn-head center height = 0.051 m
fit residual = 24.63150540351977 mm
```

`reflect_ranks` was the only D4 member whose required C2 XY shift fit inside
both preregistered `+/-0.08 m` table-frame bounds. No yaw or joint-zero change
was identifiable from the single physical strike constraint, so neither was
fit.

The 51 mm target is the modeled pawn head center appropriate to the observed
strike/topple. It is deliberately distinct from Q00's 28 mm neck diagnostic.

## Validation

```text
uv run --offline pytest -q \
  tests/test_bidirectional_scene_registration_v4.py \
  tests/test_scene.py \
  tests/test_bidirectional_pawn_push_registration_dataset.py
...............                                                          [100%]
15 passed in 0.37s
```

The tests independently reproduce the fit from only Q01 fit members, check
all D4 maps are bijective, compile the registered scene in CPU/fp64 MuJoCo,
verify named physical C2 is placed at the transformed coordinate, and assert
the canonical NPY and raw float64 hashes remain unchanged.

Candidate SHA-256:
`c7c2b19d7bdf64e85c20f515b4d7fa859b2fd33948fa1a36438265571a752b7b`.

## Claim boundary

Proof class: `zero_motion_fit_only_scene_registration_candidate`.

Held-out content remained sealed throughout Q02. The fit candidate is not an
admitted registration and provides no physical or bidirectional task claim.
