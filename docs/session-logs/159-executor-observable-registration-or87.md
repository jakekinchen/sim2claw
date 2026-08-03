# Executor session 159: OR87

- Started from admitted active card `OR87`; agent profile and executor context passed.
- Rendered exactly three frozen validation episodes and `328` full-source-mesh frames using the OR82 camera, OR84 workcell transform, and OR86 global response without refit.
- Passed mean (`0.842051`), p10 (`0.825361`), motion (`0.799354`), every phase mean, and every episode mean gate.
- Failed only the tolerant-edge F1 gate: `0.391734 < 0.4`; all `7/7` integrity gates passed.
- Resource accounting: three validation video decodes, zero development or evaluator-heldout reads, zero fits or selections, no replays, no hardware, and no paid compute.
- Reviewer decision: reject the candidate, keep evaluator-heldout sealed, and freeze a new JSON-only split restart before any further development fit.
