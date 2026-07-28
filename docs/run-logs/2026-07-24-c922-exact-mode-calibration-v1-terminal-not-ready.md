# C922 exact-mode calibration v1 terminal not-ready result

Date: 2026-07-24

Proof class: `camera_calibration_evaluator_infrastructure`

Twin status: unchanged `0 / 6`

Task score: unchanged `0 / 11`

## Frozen implementation

- Preregistration commit:
  `486f9ae9ebf142ad64a5fbdbb50cac867195c7fd`
- Execution commit:
  `e32553ebc2682fa18e5c531b4b1404b073d4c6d8`
- Execution tree:
  `8a7cf966473517f9da6dc357e814d83b6fb248f6`
- Contract SHA-256:
  `d586d262929063c924895f56142dfe88196c521cb039d2392dc4ba53259b087c`
- Target asset SHA-256:
  `8841927738e7ee31af5fb7373121863cf518808479599e315657b69d1ceb9285`
- Input manifest SHA-256:
  `1265302d05b8826c2f4f2a0c590d07dfcd1aa9cb14b8fed0f5a54e6630094b97`
- Evaluator SHA-256:
  `5877231a57a23c78d588a7837e691f9f8a2860e31e0ff177b01c38be27ae1163`

The retained 46-image SfM calibration belongs to `IMG_5349` at
`1600 × 2844`; it was not substituted for this exact `640 × 480` C922 mode.
The retained C922 visual fits remain one-view, zero-distortion or
distortion-excluded diagnostics.

## Evaluator result

The single authorized offline dataset evaluation returned
`calibration_dataset_not_ready`.

- Evaluation file SHA-256:
  `fbac56c8d8f8e1c6ed23c7d5ff6950d2a7ccfb492f9c031696849a3479d99f85`
- Evaluation digest:
  `f4b86a184d4b4427275c883cbfb51fc79949d1716940c96c9575a66f2d4d797e`
- Declared / accepted / rejected frames: `0 / 0 / 0`
- Fit / validation / held-out accepted frames: `0 / 0 / 0`
- Model fits: `0 / 2`
- Selected model: unavailable
- Intrinsics receipt: not emitted
- Lens-distortion receipt: not emitted

The ten explicit prerequisites are:

1. `constant_focus_setting`
2. `fit_split_count`
3. `held_out_split_count`
4. `minimum_accepted_frames`
5. `minimum_near_frontal_views`
6. `minimum_orientation_bins`
7. `minimum_scale_bins`
8. `minimum_tilted_views`
9. `required_centroid_bins`
10. `validation_split_count`

This is a missing-corpus result, not an evaluator rejection and not a camera
calibration. The tracked target's `20 mm` squares and `200 × 140 mm` grid are
nominal design values, not physical measurements or metric-scale authority.

## Verification and authority

Independent read/test review passed at the exact execution commit with `13 /
13` focused tests. The combined calibration plus metric-readiness focused
slice passed `42 / 42` tests before the formal evaluation.

Budget use was one dataset evaluation, zero model fits, zero camera sessions,
zero new camera frames, zero robot motions, zero simulator replays, zero
provider calls, and zero training rows. Frozen S2 evidence remained
byte-identical at eleven hashes and `1 event / 4 replays / 0 measurement
trials`.

V1 is exhausted and a tracked control refuses another evaluation before
delegation. A future physical acquisition requires a separately preregistered
transaction with the printed target present, exact focus observability, and
the frozen 18-view `12 / 3 / 3` corpus. Geometry/scale, simulator calibration,
training, promotion, physical transfer, and task authority remain closed.
