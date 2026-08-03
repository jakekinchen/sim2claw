# OR122: renderer-native clipped rectilinear planar-array reconstruction

OR122 emitted a deterministic development-only renderer receipt, but the
implementation and test files changed after their identities were frozen. The
final implementation hash is `ae500959...`, not the contract-bound
`1596ffda...`; the final test hash is `605d4e3b...`, not `293fca2a...`.
Consequently the final source cannot load the frozen contract and the focused
suite ends at `1 passed, 2 failed`.

The receipt's canonical artifact digest is internally valid, but it is not
evidence for the final source pair. Its seven-row numeric result is advisory
only: outside-board edge F1 improves `+0.017517`, while local array ROI edge F1
and full-frame linear similarity improve only `+0.053325` and `+0.000108`.
Validation remained unopened.

Quarantine OR122 and reproduce the experiment under a new, immutable contract,
implementation, test, and output identity. Do not overwrite the receipt or
promote its numbers. Prediction, physics, event parity, transfer, and simulator
promotion remain false.
