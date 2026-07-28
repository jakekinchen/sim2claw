# AVFoundation format-inventory preregistration

Date: 2026-07-24

Baseline: clean centralized
`main == origin/main == 2e8b33da36a73a002d248c353eeb7095bbb9fd7f`.

## Purpose

The prior native source-probe family is exhausted and sealed as
`prerequisite_abstention`: all 12 attempts failed before session startup
because the preregistered C922 `640 × 480 @ 30 fps` format was unavailable.
No source sample or D405 lifecycle was executed.

This new transaction observes only the exact-name C922's native
`AVCaptureDevice.Format` inventory. It does not start `AVCaptureSession`,
create an input/output, receive frames, touch the D405, or reopen prior trials.

## Frozen method

- Contract:
  `configs/evaluations/avfoundation_format_inventory_v1.json`.
- Contract SHA-256:
  `a7977a5b32b4f67da004a725f956c9c44a526f8fe14219256c6b068c698c4380`.
- Goal SHA-256:
  `d90fa324bea2fa38cc9ee91077e40571f1c9a94facec47c3c7966ed427bce4a9`.
- Exact device name: `C922 Pro Stream Webcam`; exactly one match required.
- Target: exact `640 × 480`, nearest supported rate to `30.0 fps`.
- Maximum fractional-rate deviation: `0.05 fps`.
- Ranking: deviation, frozen subtype preference, subtype text, native format
  index, then range index.
- Observer emits all declared native fields and never scores or selects.
- Evaluator alone validates, ranks, selects, or abstains.

## Budget and authority

One inventory observation is allowed after implementation is committed.
Capture sessions, source frames, D405 lifecycle operations, robot motion,
simulator replay, training, promotion, provider calls, paid compute, and task
score changes are all zero/closed.

All eleven S2 files, both HIL states, sealed D405 evidence, and the prior
AVFoundation campaign/evaluation/receipt remain immutable. No observation has
run at this preregistration checkpoint.
