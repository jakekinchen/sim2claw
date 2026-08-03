# Executor session 154: OR82

- Started from admitted active card `OR82`; preserved OR81 annotations, correspondence, renderer, metrics, and gates.
- Added only one shared optical-axis sensor-roll parameter. Principal point, distortion, appearance, timing, state, validation, and held-out expansion remained prohibited.
- Added the contract, implementation, and two focused tests; tests and Python compilation passed.
- Searched 43,183 candidates across the unchanged eight board symmetries. Reprojection improves to `8.80 px` RMS / `10.16 px` max but still fails; the optimizer is unconverged and FOV-bound.
- Static mean similarity is `0.766321`; whole-frame edge F1 is `0.326581`, below OR81 and the frozen gates.
- A read-only region diagnostic found board edge F1 improves in all four frames (`~0.57→~0.63`) while outside-board F1 collapses (`~0.40→~0.23`).
- Resource accounting: four development frames and traces, one shared camera fit, zero other fits, zero replays, zero validation/heldout reads, no hardware, and no paid compute.
- Reviewer decision: reject whole-frame advance and formalize board-versus-scene residual attribution next.
