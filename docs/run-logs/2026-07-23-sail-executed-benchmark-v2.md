# SAIL Evaluator-Executed Benchmark v2

Date: 2026-07-23

## Proof boundary

This checkpoint is synthetic executed-benchmark evidence. It does not prove
simulator, task, physical, calibration, training, promotion, or transfer
capability. Candidate code is trusted in-repository code receiving deep-copied
public payloads. Input, output, action, method, evaluator, and source identities
are digest-checked. This is not cryptographic isolation or hostile-code
sandboxing.

Benchmark v1 remains historical. Benchmark v2 removes method-name-conditioned
scoring from evidence: eight registered callables executed across eight frozen
public cases, and a separate evaluator scored their strictly validated
prediction artifacts against sealed truth. Oracle and full-batch controls
remain evaluator-owned.

## Execution

Command:

```text
uv run sim2claw sail-compile-executed-benchmark \
  --config configs/sail/seeded_benchmark_v2.json \
  --output outputs/sail/seeded-benchmark-v2
```

Counts and accounting:

- public cases: 8
- candidate methods: 8
- candidate method executions: 64
- evaluator-owned controls: 4
- executed golden checks: 25 passed, 0 failed
- probes: 54
- recomputations: 125
- synthetic simulator evaluations: 54
- abstentions: 6
- method failures: 0
- provider calls: 0

Primary mechanism-family top-1 accuracy:

- `parameter_only_v2`: 0.625
- `sequential_no_revisit_v2`: 1.000
- `deterministic_random_probe_v2`: 0.750
- `residual_magnitude_v2`: 0.625
- `sail_without_invariance_v2`: 0.875
- `sail_without_loop_closure_v2`: 0.625
- `sail_without_structural_acquisition_v2`: 0.625
- `sail_deterministic_v2`: 0.625

The frozen primary comparison is therefore a tie between
`sail_deterministic_v2` and `parameter_only_v2`. SAIL's recovery-threshold
rate was 0.625 versus 0.000 for parameter-only, but the benchmark does not
relabel that secondary result as a primary win. The unchanged and incorrect
controls scored 0.000 top-1; the oracle and full-batch evaluator controls
scored 1.000.

## Content identities

- receipt file SHA-256:
  `4f65b80d7a19ad97dbb0daf0eaac014ff3f51e682031c91abec8386a6d19b803`
- receipt digest:
  `013716ef4356ff0ead320b0e309b5ab061dad675553d6f155f48498751135e76`
- scorecard file SHA-256:
  `7affef8bfb8060e270bd4aaa07fdf8109bdb0495cc0306cbc4516cf0b05ea16b`
- scorecard digest:
  `132aaaa5f2244c7e362cc38a58e9276c4c240a81c6c9a71ab94f4d4e42fdd1df`
- golden execution digest:
  `ca4da562ec2653937d4784de495cba691d6de9ca031bf8edf21f71420134963b`

A second materialization produced the same receipt file SHA-256 and embedded
digests. Generated outputs remain ignored; this durable log records their
content identities.

## Focused verification

`28 passed`:

```text
uv run pytest -q \
  tests/test_sail_executed_benchmark.py \
  tests/test_sail_cli.py \
  tests/test_sail_benchmark.py
```

Adversarial coverage rejects sealed-field leakage, malformed or self-scored
outputs, method substitution, action mutation, evaluator mutation, post-hoc
threshold changes, duplicate case identities, replayed outputs, budget
overruns, failed golden checks, and output tampering. Repeated materialization
is byte-identical.
