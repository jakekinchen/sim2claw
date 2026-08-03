# Executor session 163: OR91

- Started from admitted active card `OR91`; agent profile and executor context passed.
- Executed the single allowed evaluation of final-heldout positions `10-11`, rendering exactly `246` full-source-mesh frames with no fit, threshold change, retry, replay, hardware, or paid compute.
- Passed all `6/6` metric and `7/7` integrity gates: mean `0.844452`, p10 `0.827628`, motion `0.809905`, edge F1 `0.428812`, every phase, and both episode means.
- The immutable OR91 receipt therefore passes the preregistered numeric visual target.
- A post-evaluation visual sanity audit extracted six initial/middle/terminal frame pairs. It found board-plus-margin edge F1 `0.544332` but outside-board edge F1 only `0.306256`, with visibly missing/misaligned robot structure.
- This audit cannot retroactively change the OR91 receipt and cannot support tuning on an untouched cohort because all original held-out pixels are now opened. It does prevent representing the numeric pass as an honest same-video semantic match.
- Reviewer decision: retain the numeric pass, reject the broader same-video claim, and factor the robot/workcell residual in a post-final diagnostic lane.
