# OR58 executor session

Date: 2026-08-02

OR58 evaluated all `100` preregistered time-invariant common-channel
gain/bias/blur candidates on `220` development frames. Twenty-four candidates
reached the development mean threshold. The development-only selection uses
common BGR gain `0.4`, bias `+64`, and no Gaussian blur (`1 px` kernel).
Validation and stress were not read for selection.

The decoded emitted video scores `0.800309` mean full-frame linear pixel
similarity, `0.787592` p10, and `0.782326` motion-union mean across all `516`
available physical frames. Every phase mean exceeds `0.78`. The same candidate
scores `0.801780` on the untouched validation partition and `0.798897` on the
stress partition. The mean, p10, motion-union, and phase gates all pass.

Mean tolerant-edge F1 is only `0.180341` against the unchanged `0.40` gate.
The result therefore establishes the requested numeric temporal pixel range
but not the full same-video target. Visual review confirms the residual is
structural: the physical recording includes countertop texture, wall,
monitor, cables, clutter, and the physical arm surface, while the simulator
contains simplified scene geometry and appearance. Global exposure matching
cannot recover those edges.

OR58 changed no action, state, physics, camera pose, or geometry; it ran no
simulator episode or renderer and used no physical pixels as a composite,
texture, or background plate. The retained candidate remains an
episode-specific visual diagnostic and supplies no physics, transfer, or
promotion proof.

Focused verification: `2 passed` for the OR58 fail-closed contract and
exactly-once evaluator tests.

Resource note: the host remained below `1 GiB` free. A follow-up attempt to
invoke MuJoCo's native macOS trampoline with the standalone Python shared
library reproduced the recursive GLFW helper failure; the process group was
stopped and all `1,934` helpers were terminated. This route is closed for the
current goal loop.
