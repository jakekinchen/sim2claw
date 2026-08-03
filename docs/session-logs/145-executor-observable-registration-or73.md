# OR73 executor session

Date: 2026-08-03

OR73 fit one shared seven-parameter 3D look-at camera against only the four
development initial frames. Physical frames received the known C922
`hflip,vflip` orientation and were evaluator targets only. Candidate frames
remained analytic projections from the frozen 3D scene and frame-zero states.

The frozen differential-evolution budget evaluated `336` shared vectors and
rendered `1,344` search frames. It stopped at the maximum iteration budget, so
optimizer convergence is not claimed. The best admissible vector passes all
four advance gates across all four episodes. At `160×120`, mean full-frame
similarity improves `0.574015 → 0.795110` and tolerant-edge F1 improves
`0.270848 → 0.415990`. At the final `320×240` resolution, the four-frame mean
is `0.790402` and edge F1 is `0.276779`; the resolution-dependent edge deficit
remains explicit.

No appearance, time, state, or physics parameter was fit. No validation or
evaluator-heldout data, simulator replay, hardware action, or paid compute was
used. The selected vector is frozen for a full development-timeline rerun and
does not yet prove temporal pixel similarity, camera fidelity, event parity,
physics fidelity, promotion, or transfer.

Focused verification: `2 passed`.
