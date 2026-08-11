# OR136 executor log

OR136 repaired only OR135's historical source-boundary sampling mismatch. Its
fresh rigid run reproduced the historical compiled model and all frozen
source-boundary compatibility metrics, and the independent compatibility gate
passed. The rigid trace remained a strict task failure.

The frozen flex family then ran in its declared order: 10, 25, 63, 158, and
400 kPa. All five independently failed strict evaluation. More importantly,
each flex model emitted `mjWARN_BADQACC` during the initial 100-step settle,
before the recorded action replay began. Subsequent values reflect MuJoCo's
warning/reset behavior and cannot support task or stiffness comparisons.

OR136 therefore closes as
`TERMINAL_FLEX_CAP_PREACTION_NUMERICAL_INSTABILITY_NO_STRICT_PASS`. Exactly one
rigid and five flex executions ran, with zero admissible flex task trials, zero
strict successes, zero no-refit confirmations, and zero renders. No stiffness,
calibration, simulator-promotion, transfer, or physical-fidelity conclusion is
allowed. A successor requires a new identity and an independently verified
per-step zero-action cap-stability gate before any replay action is consumed.
