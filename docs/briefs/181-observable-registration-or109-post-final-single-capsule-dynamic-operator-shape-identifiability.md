# OR109 — Single-capsule dynamic operator shape identifiability

OR108 validates moving operator-like support after removing a frozen persistent
board-frame confound. OR109 asks whether one bounded shape is adequate before
any 3D renderer actor is authorized.

For the largest dynamic component in each materially present frame, one
deterministic capsule is computed from its principal axis, fixed 5th/95th
endpoint percentiles, and fixed 90th-percentile minor radius. There is no search
or parameter fit. Development and validation require coverage as well as IoU,
so a wholesale oversized shape cannot pass by covering everything.

This is 2D shape identifiability only. It performs no render or replay and does
not establish operator identity, 3D geometry or trajectory, same-video match,
physics fidelity, transfer, or simulator promotion.
