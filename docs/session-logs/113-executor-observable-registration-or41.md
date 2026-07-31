# Executor session 113 — OR41 retained full-range gripper mapping

Date: 2026-07-31
Card: `OR41`
Result: `TERMINAL_NEGATIVE_RETAINED_CROSS_EPISODE_DIRECTIONAL_PLAY`

## Scope

OR41 tested the only already-retained contact-free recording with a complete
bidirectional gripper cycle before requesting new physical data. The contract
bound all `2401` measured rows, the `642`-frame `5 Hz` D405 browser stream, and
its callback-host timestamps before quantitative extraction. It reused OR40's
scale-free directional-play estimand and kept all metric, force, compliance,
task-outcome, dynamics, hardware, and transfer authorities false.

## Frozen method

- Gripper-cycle samples: `430–546`.
- Candidate D405 frames: `140–180`.
- Frame association: sequential non-warmup D405 callback host timestamp to
  nearest sample-start host timestamp, bounded by `110 ms`.
- Extraction: frozen HSV red-component thresholds with the two largest
  qualifying surfaces ordered left-to-right.
- Split: opening and closing rows partitioned independently, alternating
  chronological fit and validation rows.
- Candidate: the same bounded one-parameter causal play operator as OR40.
- Validation: internal no-refit rows plus the untouched OR40 task-clip
  preterminal observations.
- Dynamic replay budget: zero.

## Result

The source encoder trace contains the expected `1.0689° → 99.5249° → 1.6627°`
cycle. The wall-facing wrist video does not contain a usable matching visual
cycle under the frozen extractor:

- accepted frames: `4 / 41`;
- fit opening/closing frames: `1 / 2`;
- validation opening/closing frames: `0 / 1`;
- selected play half-width: `0.0°`;
- selected lag: upper bound `+0.11 s`;
- fit RMS: `3.8049 px`;
- internal validation RMS: `2.9573 px`;
- untouched OR40 task-clip validation RMS: `54.7367 px`;
- dynamic replays: `0`.

The existing full-range clip cannot identify the missing load-side jaw mapping
and cannot justify a physics intervention. Thresholds were not relaxed and no
alternate crop, manual metric label, task outcome, or convenient lag was used
after the negative.

## Verification

The OR40 and OR41 focused suites pass `7` tests. Agent workspace and goal
checks are recorded at the closeout transition.
