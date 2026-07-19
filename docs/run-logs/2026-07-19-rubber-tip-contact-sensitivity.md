# Rubber-Tip Contact Sensitivity Run Log

Date: 2026-07-19 America/Chicago

Benchmark label: **narrow simulated rook-lift contact-sensitivity benchmark**

Proof class: simulation contact-prior sensitivity using one frozen learned ACT
policy. Physical authority remained closed.

The first receipt from this branch was marked NO-INTEGRATE by independent
review. This log now describes the repaired v2 receipt only.

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
- accepted immutable checkpoint snapshot size: `3,854,645` bytes
- contact-prior contract SHA-256:
  `e89eb1084e7e1dee64aaebfbc18b816b5bf58aefa98b18d38ef2e9a81b6ee499`
- held-out seed: `9101`, once per predeclared variant
- variant order: nominal, low, midpoint, high
- evaluator thresholds, policy weights, observations, action semantics, seed,
  and initial piece offset remained unchanged
- evaluator rows admitted to training: zero

The checkpoint path was read once into immutable bytes. Those bytes were hashed
against the accepted digest before `torch.load`; all four evaluator calls then
received the same in-memory snapshot object and never reopened the path. The
preflight checked the checkpoint schema, task ID, embedded task hash, exact
snapshot hash, held-out seed, strict contract digest, and compiled nominal
identity before the first evaluator invocation. All checks passed.

## Prior contract

The nominal variant is a strict no-op. Each rubber variant adds one separate
distal box-sleeve collision approximation to the fixed finger and one to the
moving finger. The nominal SO-101 source model is not rewritten. Values below
are estimates used only to span sensitivity; none is a physical measurement.

| Variant | Thickness | Box half-width | Coverage | Friction (slide / torsion / roll) | `solref` |
|---|---:|---:|---:|---:|---:|
| low | 0.5 mm | 5.5 mm | 12 mm | 0.8 / 0.003 m / 0.0003 m | 0.015 s / 0.8 |
| midpoint | 1.0 mm | 6.0 mm | 18 mm | 1.2 / 0.006 m / 0.0006 m | 0.010 s / 1.0 |
| high | 1.5 mm | 6.5 mm | 24 mm | 1.8 / 0.012 m / 0.0012 m | 0.006 s / 1.2 |

Each variant also binds its five-value MuJoCo `solimp` vector in
`configs/simulation/rubber_tip_contact_sensitivity_v1.json`. “Midpoint” means
the middle of this declared ensemble, not a best estimate or calibrated truth.

Rubber mass is not modeled. The owner assessment is that two rubber bands do
not perceptibly affect mass; their physical mass is still acknowledged as
nonzero and unmeasured, then intentionally approximated as zero for simulator
dynamics. No child body, body-mass edit, COM edit, or inertia edit is made.

Variant identities:

- nominal: `89f3c21e19f8bffc9f8391bb2b7ee089765f698fe38de93ba7fc4cac3f5c3869`
- low: `cac9ef7043ba66589c72ff391459902537a79462fb5b3e388b86d08f20cf421d`
- midpoint: `fff57bff4ec9857cbcea4e254b26fd06472535ff0c159b11543162ac4f88ca14`
- high: `a47d0055e548211a497e4b876055a91ddae18723c34700ce27ee1a0b18df9ad6`

## Execution

```bash
uv run sim2claw act-contact-sensitivity \
  --checkpoint /Users/kelly/Developer/sim2claw/outputs/polycam_chess_table/act/chess_rook_lift_v1/checkpoint.pt \
  --output-directory outputs/polycam_chess_table/act/chess_rook_lift_v1/contact_sensitivity_v1
```

Generated checkpoints and run artifacts remain ignored. Videos were disabled;
the evaluator wrote an action trace, state trace, and receipt for every variant.

## Model and tool roles

| Role | Tool | Purpose | Output |
|---|---|---|---|
| Contract and runner repair | Codex | Strict schema, snapshot boundary, negative regressions | reviewed source and tests |
| Dynamics proof | MuJoCo 3.10.0 compiler | Compile nominal and contact-only variants | compiled identity hashes and geom bindings |
| Policy evaluation | PyTorch 2.11.0 CPU/fp32 | Deserialize accepted bytes and execute frozen ACT | four evaluator receipts |

No external or generated visual assets were used.

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

## Compiled and checkpoint identity proof

The legacy implicit nominal and explicit nominal variant have the same compiled
dynamics SHA-256:
`906e21892c4bac19f42a0db3dd03f2fa3c2e8225d675fe59b71c19ae722f0609`.
Their full selected dynamics arrays compare bit-for-bit.

All four variants share inertial/control SHA-256
`5b3a97545a2ebcbded7c8df42a7605a62449b49b172337c05d9a673a96326a76`
and compiled total body mass `320.78595512426926 kg`. Body mass, body COM,
body inertia, joint/DOF arrays, actuator arrays, and counts (`nbody=61`,
`njnt=44`, `nq=236`, `nv=204`, `nu=12`) are bitwise identical. Only the two
zero-mass simulator sleeve collision geoms and their contact arrays differ;
this zero is an approximation and not a claim that physical rubber is massless.

Compiled dynamics identities, including contact geometry:

- nominal: `906e21892c4bac19f42a0db3dd03f2fa3c2e8225d675fe59b71c19ae722f0609`
- low: `a9995ed1ff5adc2f37d02297e897e15fa551065df6e75d0a37242e19289c7c61`
- midpoint: `55d258d91ae87fc5a6b1c91c46e7d3be57ff5b1ed92b0468635dd081dd329637`
- high: `4ee6e849fd16a68025be75c607508e5fac6eac7d84ff3e69b60181bc975d6d2b`

Every evaluator receipt binds the same accepted checkpoint snapshot digest,
the compiled geom names/IDs, parent body names/IDs, half-extents, friction,
`solref`, `solimp`, `condim`, priority, zero modeled mass, and both compiled
identity hashes.

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
  `281245836bfd4b2f41a14f73c3b247137ecc9a77c294435b0dcdb4bd27db4d68`
- preflight receipt SHA-256:
  `2240f7e62cf35cd24cef2fac6fa86f264d5aa977365cf754dbc4169f4af86533`

## Verification and implementation commits

- focused contract, evaluator, and ACT tests: `16 passed, 254 subtests passed`
- negative regressions cover missing checkpoint, rejected hash before
  deserialization, unaccepted evaluator snapshot, post-preflight path
  replacement, contract/provenance/type/order/cardinality tamper, anchor
  mismatch, compiled contact identities, and cross-variant inertial identity
- full suite: `197 passed, 284 subtests passed` in `15.87 s`
- `uv lock --check`: passed
- `uv build`: built the source distribution and wheel successfully
- `git diff --check`: passed
- `bc1db8b` — freeze rubber-tip contact sensitivity priors
- `4aeabbf` — run the frozen ACT contact sensitivity ensemble
- `d24ac47` — exclude rubber mass and harden the contact contract
- `db4f5bd` — pin ACT evaluation to immutable checkpoint bytes
- `bcc9cda` — reject unaccepted contact benchmark snapshots

## Proof-wording audit

A separate closeout pass checked every claim against the frozen contract and
generated receipts. Accepted wording is limited to checkpoint compatibility,
the four simulated outcomes, exact trace identities, and sensitivity to this
declared unmeasured ensemble. Rejected wording includes physical calibration,
measured rubber friction or mass, modeled rubber mass, sim-to-real error,
real-gripper validation, B-G pawn skill, generalized chess manipulation,
language generalization, transfer, and composability.
