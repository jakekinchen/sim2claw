# Executor session 156: OR84

- Started from admitted active card `OR84` after agent profile and executor-context checks passed.
- Froze one three-parameter board-anchored SE(2) family over the photo background/mug, table, clamps, and both robot subtrees; board/pawns/fiducials remained fixed.
- Searched `195` deterministic analytic candidates on four development opening frames; no validation or held-out input was read.
- Evaluated the selected vector with exactly four full-source-mesh native renders (`824,944` triangles each).
- Whole-frame edge F1 improves by `0.126326` over OR82; outside-board F1 improves in every episode; all `14/14` gates pass.
- The optimizer hit the frozen iteration cap, so only the selected frozen vector—not convergence—is admitted.
- Resource accounting: four development frame decodes, one shared three-parameter fit, four exact renders, zero simulator replays, zero validation/heldout reads, no hardware, and no paid compute.
- Reviewer decision: freeze the vector and run the full development timeline without refit.
