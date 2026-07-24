# AVFoundation source-localization terminal abstention

Date: 2026-07-24

Proof class: `camera_source_lifecycle_localization`. The result is a
prerequisite abstention, not camera continuity, physical-exposure, metric
depth, simulator calibration, or task evidence.

## Frozen execution

Contract `c7063d8f875c576007d21a1f676a5ec75dec286d80c4a207af28d2a99e065df5`
froze six C922-only controls and six C922-plus-D405-lifecycle treatments in a
balanced order. Preregistration commit `92c2f96` and implementation commit
`6948496` preceded live use. The campaign consumed all 12 one-attempt slots,
with zero replacements, robot motions, or provider calls.

Every attempt selected the exact `C922 Pro Stream Webcam` device but exited
before AVFoundation session startup. All 12 stderr artifacts contain
`AVFoundationSourceProbe: requested_format_unavailable` for the frozen
`640 × 480 @ 30 fps` request. Consequently:

- usable source-measurement trials: `0 / 12`;
- source samples or dropped-sample callbacks: `0`;
- completed AVFoundation session starts: `0`;
- D405 lifecycle starts: `0`;
- retries or replacement attempts: `0`.

The standard evaluator refused the incomplete logs before writing any output.
To preserve the execution-bound Python runner byte-identically at
`7be758151ce3f48a3725443fa9c4b25161ad40ae186f12cc6e98ec5a5b4c3b72`,
the fail-closed serializer was implemented separately and committed as
`d234ed7`. It validates contract, runner, Swift source, compiled binary,
campaign/trial ordering, authority, budgets, trial and raw-artifact hashes,
and refuses to discard any observed source sample or executed lifecycle.

## Content-addressed result

- Swift source:
  `903658a0dd34012371e732b15277a2f5ce4070e9fdde532f7f4bf42dc586e4be`.
- Compiled source probe:
  `8222f3802b9758dbb35df29bebd07f0c7e162f351b6823cb3109ab2f004103c9`.
- Abstention evaluator:
  `d54a3a3b503cbf14a5dfcab133506b081dc12cbe99cf98b82d24251543035cf7`.
- Raw campaign:
  `7c8b6ad359cf0db3260937f3836b1be7bc9c09005f32c727f53568a702f7b7dd`.
- Evaluation:
  `d0d65fbe43779a2eb0dcbd53c87ec05f089b3811c4642831650612d57eccee3c`.
- Receipt file / embedded digest:
  `ac636601a8f178aaca06f58d597dfd1fa17e52de21d139ec1721f964eb063a7e` /
  `35b8f9d9ad681a2e1ab3928a61f86685e3f25967ab76e8a1a515f407778cd5da`.
- Verdict: `prerequisite_abstention`.

The generated output remains ignored and frozen. The prior D405 stationary
campaign/evaluation/receipt remain `57d4983c...`, `80ed9ac3...`, and
`cfc11ff3...`; both HIL campaign states and the eleven-file S2 set remain
byte-identical.

The pre-freeze static/focused gate passed Swift typecheck and `81 / 81`
camera, HIL, and Studio tests. The 19-artifact guard—eleven S2 files, two HIL
states, three D405 qualification files, and the new campaign/evaluation/receipt—
was byte-identical before and after.

## Decision and next prerequisite

No source-vs-container localization claim is available. The sealed C922
container gaps remain unexplained at source level, and the motion-correlated
D405 cable/connector fault remains a separate physical prerequisite.

A future campaign must first enumerate the exact C922 AVFoundation formats,
freeze a supported callback format and pixel-format selection rule, and obtain
new attempt authority. It may not reuse or relabel these 12 failed attempts.
The broader Twin fidelity result remains `0 / 6`; no simulator parameter,
posterior, task score, training, promotion, or physical-task authority changed.
