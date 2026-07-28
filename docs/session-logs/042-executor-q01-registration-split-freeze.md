# Executor log 042: Q01 registration split freeze

Date: 2026-07-27

Decision: Q01 acceptance checks passed.

## Scope

- Froze seven fit inputs from the immutable C2 contact/topple case and its
  exact current scene/mapping priors.
- Reserved one independent completed B7 high-hover episode as held-out using
  its packet, measured joints, native C922 recording, and existing
  task-relevant diagnostic.
- Computed held-out hashes without parsing, viewing, or semantically
  inspecting held-out content.
- Froze the Q02 candidate family before fitting: eight D4 board
  orientations followed by board XY/yaw only, bounded to `0.08 m` and
  `15 deg`. Action mutation is forbidden; joint-zero changes require
  separate identifiability.
- Issued no robot, camera, network, or paid-compute command.

## Validation

```text
uv run --offline pytest -q \
  tests/test_bidirectional_pawn_push_registration_dataset.py
..                                                                       [100%]
2 passed in 0.04s

python -m json.tool \
  configs/evaluations/bidirectional_pawn_push_registration_dataset_v1.json
PASS

shasum -a 256 \
  configs/evaluations/bidirectional_pawn_push_registration_dataset_v1.json
da203fae0e84ceb722631676858762e1ee3d5962be95c4555afb44f97bf51fdf
```

The hash test independently resolved every declared path and recomputed all
eleven SHA-256 values. It also asserted both split memberships, the one-open
held-out rule, the `25 mm` gates, and the bounded Q02 family.

## Claim boundary

Proof class: `zero_motion_registration_split`.

This freezes input identity and split membership only. It does not validate a
registration, open the held-out result, authorize motion, or prove physical
or bidirectional task success.
