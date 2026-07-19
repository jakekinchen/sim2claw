# Rubber-Tip Contact Sensitivity Run Log

Date: 2026-07-19 America/Chicago

Benchmark label: **narrow simulated rook-lift contact-sensitivity benchmark**

Proof class: simulation contact-prior sensitivity using one frozen learned ACT
policy. Physical authority remained closed.

## Question and boundary

The owner reported approximately four to five rubber-band wraps around each
SO-101 gripper fingertip. No wrap thickness, covered length, mass, material
hardness, friction, compliance, or physical trajectory was measured. This run
therefore asks only whether the accepted `chess_rook_lift_v1` simulated ACT
outcome changes across an explicit uncalibrated contact-prior ensemble.

This is not calibration and does not measure sim-to-real error. It is not the
B-G pawn benchmark: no pawn ACT checkpoint was evaluated. It does not establish
physical rubber-band validity, pawn skill, language generalization, transfer,
or composability.

No robot, camera, serial bus, physical gateway, network research, training,
Brev, paid compute, or physical held-out data was used.

## Frozen identities and fail-closed preflight

- task: `chess_rook_lift_v1`
- task contract SHA-256:
  `4c3c4f95a9a7d72acebaed993091c576baf125f9ed0454a960dfd2d5906c518f`
- separately owned evaluator block SHA-256:
  `fb400468df6a131940c9abfce25c38cfdeced95ed337e4e4a1d079ad32915f0d`
- accepted ignored checkpoint SHA-256:
  `f0a58e49dcaa320d3d0b86ef839b2e39893b65cf26a738954e2bb833dd3144fc`
- contact-prior contract SHA-256:
  `fbc5e995a055c923e4badd4513e448c61e60ca854ec179ac3e18cef64632a01f`
- held-out seed: `9101`, once per predeclared variant
- variant order: nominal, low, midpoint, high
- evaluator thresholds, policy weights, observations, action semantics, seed,
  and initial piece offset remained unchanged
- evaluator rows admitted to training: zero

The preflight checked the checkpoint schema, task ID, embedded task hash, exact
accepted checkpoint hash, held-out seed, and frozen variant contract before the
first evaluator invocation. All checks passed.

## Prior contract

The nominal variant is a strict no-op. Each rubber variant adds one separate
distal box-sleeve collision approximation to the fixed finger and one to the
moving finger. The nominal SO-101 source model is not rewritten. Values below
are estimates used only to span sensitivity; none is a physical measurement.

| Variant | Thickness | Outer radius | Coverage | Friction (slide / torsion / roll) | `solref` | Added mass / finger |
|---|---:|---:|---:|---:|---:|---:|
| low | 0.5 mm | 5.5 mm | 12 mm | 0.8 / 0.003 m / 0.0003 m | 0.015 s / 0.8 | 0.2 g |
| midpoint | 1.0 mm | 6.0 mm | 18 mm | 1.2 / 0.006 m / 0.0006 m | 0.010 s / 1.0 | 0.5 g |
| high | 1.5 mm | 6.5 mm | 24 mm | 1.8 / 0.012 m / 0.0012 m | 0.006 s / 1.2 | 1.0 g |

Each variant also binds its five-value MuJoCo `solimp` vector in
`configs/simulation/rubber_tip_contact_sensitivity_v1.json`. “Midpoint” means
the middle of this declared ensemble, not a best estimate or calibrated truth.

Variant identities:

- nominal: `586599e174a4d738130132a77ecf8985b0bf8809deafe90e6bc25164dda5c4c4`
- low: `fecb6a9443e1bc65d769cf4dfbbae7ed7c8d2f0035d4c4990ce1de924a3783ba`
- midpoint: `819ab7a25349608bd7ae0cf642c191398336fed0adcfc404ede18434f1c8149a`
- high: `20441b6151047f109ca00042c5e6b33f9127eec2f76086370f259a159837496e`

## Execution

```bash
uv run sim2claw act-contact-sensitivity \
  --checkpoint /Users/kelly/Developer/sim2claw/outputs/polycam_chess_table/act/chess_rook_lift_v1/checkpoint.pt \
  --output-directory outputs/polycam_chess_table/act/chess_rook_lift_v1/contact_sensitivity_v1
```

Generated checkpoints and run artifacts remain ignored. Videos were disabled;
the evaluator wrote an action trace, state trace, and receipt for every variant.

## Results

| Variant | Success | Max rise | Final rise | Longest contact | Final contact | First contact | Longest contact span | Failed gates |
|---|---|---:|---:|---:|---:|---:|---:|---|
| nominal | yes | 0.09487619264668778 m | 0.09401030380165210 m | 1,083 | 1.0 | 548 | 937–2,019 | none |
| low | yes | 0.09374617764166371 m | 0.09294489935122874 m | 1,107 | 1.0 | 548 | 913–2,019 | none |
| midpoint | yes | 0.09373001022253469 m | 0.09322592536454744 m | 1,082 | 1.0 | 548 | 938–2,019 | none |
| high | no | 0.02410701177222896 m | 0.01472428566496298 m | 147 | 0.0 | 536 | 953–1,099 | maximum rise, final rise, final contact fraction |

“Success” here means only the frozen v1 lift/contact gates passed. This run does
not rescore or supersede the separately documented v2 collateral-damage gates.

The frozen task has no release phase, so release timing is unavailable rather
than inferred from transient contact losses.

All four simulations remained finite. Peak piece linear / angular speed was:

- nominal: `0.5767597128221816 m/s` / `16.956151178969236 rad/s`
- low: `0.4589566956176437 m/s` / `14.480923120743073 rad/s`
- midpoint: `0.4558688253049965 m/s` / `15.870410487971817 rad/s`
- high: `1.061360135257721 m/s` / `76.63985429780577 rad/s`

Finite state is only a numerical check. In particular, the high prior's large
transient angular speed is not evidence of physical realism or stability.

## Trace identities and sensitivity verdict

| Variant | Action trace SHA-256 | State trace SHA-256 |
|---|---|---|
| nominal | `ae05cd5923203ca4e253a3fecb971c4a876e876864a1505dd8b7eacd41f58d58` | `58b441ca743274643b28d47a5da773803d877c9e7352e67933b3513b7ca9d34b` |
| low | `c16b46bdfda2bbeceaa4c58c6430481adf25d44f75a0bcaabdcc0f73f4fb1d4d` | `f770c02a72436c734b9e5d704b8cc92a740b530f14f2228ec9cee36ec38d75f2` |
| midpoint | `7357aed7b6a2d5f96a513c7dfa6fa4771cbc7f26a2c0e933a2c1ba19053b0173` | `28970b41ce87c6bab721bd2c82788676fc52d23e9a849239c5ffed5fb0f02d58` |
| high | `54b169299de4581fd4af254d735e35710b46a1a3321c36c25701e9b4d43152af` | `6eb84aca67ef474efa0f1f1c49a90188e486703fa51de275c885582d33754b36` |

The nominal action trace and rise/contact values exactly reproduce the accepted
2026-07-17 episode. Contact-state feedback changes later ACT actions in every
rubber variant. Across the ensemble, maximum rise spans
`0.07076918087445883 m`, final rise spans `0.07928601813668912 m`, and the
categorical success verdict changes. The narrow simulated policy is therefore
checkpoint-compatible but outcome-sensitive to the declared contact prior.

This does not say that rubber wrapping helps or hurts the real gripper. The
high-effect prior is one deliberately bounded estimate, not an observation.
Physical trajectories and measured fingertip properties would be required to
test model error or calibrate any setting.

## Receipts

- ignored benchmark receipt:
  `outputs/polycam_chess_table/act/chess_rook_lift_v1/contact_sensitivity_v1/benchmark_receipt.json`
- benchmark receipt SHA-256:
  `3af74d67807658c6e37aeaa459a5ce57814cfe7c59908075e8aa342a7b353410`
- preflight receipt SHA-256:
  `d172edb4058fb21d377e520c8007e844c7d68cfeb31f0d59ff2ed2ccc63736be`

## Verification and implementation commits

- focused contract, evaluator, and ACT tests: `8 passed`
- full suite: `189 passed, 30 subtests passed` in `32.36 s`
- `uv lock --check`: passed
- `uv build`: built the source distribution and wheel successfully
- `git diff --check`: passed
- `bc1db8b` — freeze rubber-tip contact sensitivity priors
- `4aeabbf` — run the frozen ACT contact sensitivity ensemble

## Proof-wording audit

A separate closeout pass checked every claim against the frozen contract and
generated receipts. Accepted wording is limited to checkpoint compatibility,
the four simulated outcomes, exact trace identities, and sensitivity to this
declared unmeasured ensemble. Rejected wording includes physical calibration,
measured rubber friction, sim-to-real error, real-gripper validation, B-G pawn
skill, generalized chess manipulation, language generalization, transfer, and
composability.
