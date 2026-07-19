# ACT Project-Scope Simulation Evaluation

Date: 2026-07-19 America/Chicago

This run evaluates the only locally accepted and currently compatible ACT
artifact: the narrow `chess_rook_lift_v1` simulated policy. It does not test a
B-G pawn policy, generalized chess manipulation, language conditioning,
physical transfer, or composability.

No training, robot, camera, serial bus, gateway, network research, physical
held-out data, Brev, or paid compute was used. All evaluation ran locally on
CPU/fp32 with the one frozen simulated seed, `9101`.

## Accepted policy identity

- checkpoint snapshot SHA-256:
  `f0a58e49dcaa320d3d0b86ef839b2e39893b65cf26a738954e2bb833dd3144fc`
- immutable snapshot size: `3,854,645` bytes
- v1 task contract SHA-256:
  `4c3c4f95a9a7d72acebaed993091c576baf125f9ed0454a960dfd2d5906c518f`
- manipulation-v2 contract SHA-256:
  `fb7c1f69ea9e7b9b8cd75b6d43180dbec86fc01dc9502485562d1deedc1ce634`
- contact-prior contract SHA-256:
  `e89eb1084e7e1dee64aaebfbc18b816b5bf58aefa98b18d38ef2e9a81b6ee499`

The checkpoint was read once into immutable bytes and authenticated before
deserialization. The manipulation evaluator now consumes and reports that
same snapshot; it does not reopen the informational source path after
preflight. Path inputs fail closed unless the caller supplies an accepted
digest. The two older local attempts have incompatible task hashes and were
not deserialized.

## Narrow rook-lift contact sensitivity

The same frozen policy and evaluator ran in the predeclared order below. These
are uncalibrated simulation priors, not measured rubber properties.

| Variant | v1 result | Maximum rise | Final rise | Longest contact | Final contact |
|---|---|---:|---:|---:|---:|
| nominal uncalibrated | pass | 0.09487619264668778 m | 0.09401030380165210 m | 1,083 steps | 1.0 |
| rubber-tip low prior | pass | 0.09374617764166371 m | 0.09294489935122874 m | 1,107 steps | 1.0 |
| rubber-tip midpoint prior | pass | 0.09373001022253469 m | 0.09322592536454744 m | 1,082 steps | 1.0 |
| rubber-tip high prior | fail | 0.02410701177222896 m | 0.01472428566496298 m | 147 steps | 0.0 |

The high prior failed maximum rise, final rise, and final-contact-fraction
gates. Categorical success changes across the ensemble; maximum rise spans
`0.07076918087445883 m` and final rise spans `0.07928601813668912 m`.
Therefore the policy is compatible with the accepted evaluator but sensitive
to this declared contact-prior ensemble.

Rubber mass is not modeled. Its physical mass is acknowledged as nonzero and
unmeasured but intentionally approximated as zero in simulator dynamics. All
variants have identical body mass, COM, inertia, joint/DOF, and actuator arrays;
only the intended collision/contact geometry arrays differ.

## Honest manipulation-v2 result

The separately owned v2 evaluator replayed the exact nominal v1 action trace
and applied its previously frozen collateral and grasp-quality gates. The v1
lift/contact score passes, but the honest manipulation score fails.

Failed v2 gates:

- maximum non-target displacement: `0.31288 m` versus `0.006 m` maximum;
- non-target ejections: `1` versus required `0` (`black_queen_d8`);
- no non-target arm contact: failed;
- target upright: `18.31 deg` versus `15 deg` maximum.

Additional results: the rook clears `0.09488 m`, settles at `0.0211 m/s`, and
does achieve bilateral pad contact. Non-target pieces over the displacement
threshold are `black_queen_d8` (`0.31288 m`), `black_bishop_c8` (`0.03324 m`),
and `black_knight_b8` (`0.02023 m`).

The correct current project-scope conclusion is: this checkpoint passes only
the narrow simulated rook-lift v1 scoring under nominal, low, and midpoint
contact settings. It does not pass the honest chess-manipulation evaluator.

## Receipts and verification

Generated artifacts remain ignored under the two rerun directories bound
below.

- contact benchmark receipt SHA-256:
  `3e32a60bc0a6225768ae5d830728e5c86ed6628b4a8b638e0d00937fd4b85f05`
- manipulation-v2 receipt SHA-256:
  `5259b397d611f91ea8fb08d9f3b2af1e45496d621bd198e602d89a5f88bde6f8`
- contact output:
  `outputs/polycam_chess_table/act/chess_rook_lift_v1/contact_sensitivity_v1-rerun-20260719/`
- manipulation-v2 output:
  `outputs/polycam_chess_table/act/chess_rook_lift_v1/manipulation_v2-rerun-20260719/`
- focused snapshot/contact tests: `19 passed, 254 subtests passed`
- full suite: `379 passed, 306 subtests passed` in `21.54 s`
- `uv lock --check`: passed
- `uv build`: source distribution and wheel built successfully
- `git diff --check`: passed

## Claim boundary

This run is simulation evidence only. It does not measure sim-to-real error,
calibrate or validate the real rubber bands, authorize physical motion, or
establish a pawn skill, broad manipulation competence, language generalization,
transfer, or composability. Physical trajectories and measured fingertip
properties would be required to test the real modification.
