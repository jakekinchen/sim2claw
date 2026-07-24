# Twin fidelity closure and multilevel HIL preregistration

Date: 2026-07-24

Baseline: `main@1859ee22f0394ccc585600fe7df35e93eadf02be`

Proof classes:

- `twin_fidelity_measurement_readiness`
- `preregistered_physical_hil_action_packet` (zero attempts at this checkpoint)

## Closure result

The versioned evaluator requires six of six ordered domains to pass with no
required unknown. It reports `0 / 6`, does not compute a weighted percentage,
and keeps missing, partial, failed, and passed states distinct.

- contract SHA-256:
  `4e387a7b2a9195e5e2e5167aeb6aed4be358883bb919fa14326fe36ab8c105f8`
- report SHA-256:
  `1a63345540a59cef5a81e72db984c2621600e33b6f5c3296f52085dceaef025f`
- receipt file SHA-256:
  `2f3d07d51d2bdbafa2a9e5390949b8c9bbd0f3321520c9d1685084ed700e3e5a`
- receipt digest:
  `4d97887a5c88de723b8463c1f5f12adfb3f5aea060b463e889a6fb9885514334`

Future C922 and D405 reports include container presentation-timestamp
diagnostics. These are explicitly not camera exposure timestamps, a common
device clock, or proof that the camera itself dropped or duplicated a frame.
The D405 lossless acquisition source remains unchanged; its post-capture
browser derivative uses software x264 to avoid the prior resource-dependent
VideoToolbox failure.

## Frozen physical packet

`configs/evaluations/current_100mm_hil_multilevel_v2.json` has SHA-256
`8dbe616efc5450e6a94115459b38d50f8aac959453a77db3a75d8baea80671bb`.
It freezes exactly six ordered one-attempt packets, one per gateway joint.
Each packet uses multiple fixed levels and slow/fast cubic-smoothstep
traversals, holds non-target joints at the captured live start, returns after
every level, ends byte-exactly at the start, records both cameras, and has zero
adaptive retries or replacement packets.

At this checkpoint the campaign has `0 / 6` attempts, `0` retries, `0`
provider calls, and no generated campaign directory.

## Product and publication binding

Twin fidelity exposes the same fail-closed closure matrix in the existing
Replay drawer with no write controls. The SAIL observatory manifest remains
byte-identical at `127b2faa...`; only its compiler-bound receipt changed to
`0fd31a2c...`. The publication package remains byte-identical at
`98173b9d...`; its receipt changed to `1e230715...`. The preceding generated
receipts remain preserved in ignored, explicitly named historical directories.

## Verification

- focused HIL/timing/closure/Studio/publication: `52 passed`
- SAIL fast-contract tier: `36 passed`
- SAIL synthetic-golden tier: `58 passed`
- SAIL integration tier: `78 passed, 2 subtests passed`
- first full suite: `1093 passed, 3 skipped, 328 subtests passed`; one
  fail-closed stale Learning Factory project-state hash binding
- exact isolated LF00–LF13 component gate after the one-field rebind:
  `1 passed`
- replacement full suite: `1094 passed, 3 skipped, 328 subtests passed` in
  `1319.70 s`

No hardware, simulator replay, provider call, training, or promotion occurred
during these software gates.

## Frozen evidence and authority

All eleven S2 files remain byte-identical. Campaign accounting remains one
event, four action-identical anchor replays, and zero measurement trials. The
prior HIL campaign remains SHA-256 `b364aae6...` with four events, four
attempts, two admitted packets, two rejected packets, and zero retries.

The owner separately authorized bounded physical tests and guaranteed the
workcell clear. Physical execution remains blocked until this preregistration
is committed and live hardware/calibration identity, torque-off state, camera
inventory, and all six start-relative envelopes pass. Training, promotion,
provider, paid-compute, simulator search, and task-capability authority remain
closed.

The 33-commit overnight chain was separately pushed first as
`origin/main 694fa5a..1859ee2`. This transaction is not part of that push.
