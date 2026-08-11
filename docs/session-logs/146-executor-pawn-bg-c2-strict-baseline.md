# OR146 executor log

The one frozen C2-to-C1 baseline reproduced the exact `527×6` float64 action
and timestamp schedule with `11,851` complete integration rows and no unstable
warning. Independent verification rejects strict success.

C2 rose `59.213 mm` and finished upright `10.070 mm` from C1, but strict
same-pair bilateral dwell, qualified lift/carry, destination entry, and release
sequencing all failed. D1 was contacted for `238` steps and moved `254.071 mm`.

The full trace localizes the torque failure: original fixed-jaw primitives first
contact C2 at step `4398`; C2 exceeds `10 deg` at step `5148`; the moving rubber
pad first contacts at step `5169`. The added fixed rubber pad never contacts C2.
The next mechanism must address this unilateral surface sequence without action
assistance or C2-fitted parameter search.

OR146 closes as
`TERMINAL_STRICT_FAILURE_EARLY_UNILATERAL_FIXED_JAW_TORQUE_LOCALIZED`.
