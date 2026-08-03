# Executor session 153: OR81

- Started from admitted active card `OR81` with validation and evaluator-heldout closed.
- Froze four reviewed frame-zero playing-surface quadrilaterals at `320x240`, `4 px` annotation uncertainty, the exact scene board body and `0.1778 m` half-side, eight square-symmetry hypotheses, one seven-parameter shared look-at camera, and reprojection-only selection.
- Added the contract, implementation, and two focused tests; tests and Python compilation passed.
- Searched 29,896 candidates across eight symmetry hypotheses. The selected fit did not converge and hit elevation/FOV bounds.
- Reprojection fails at `22.51 px` RMS / `29.55 px` max. Static mean similarity is `0.733059`; edge F1 is `0.386835`, an improvement of `0.095270` over OR78.
- All candidate pixels remained full 3D renders. The run used four development frames and traces, one camera fit, zero appearance/time/state fits, zero replays, zero validation/heldout reads, no hardware, and no paid compute.
- Reviewer decision: reject this camera family and add only optical-axis sensor roll in a new card.
