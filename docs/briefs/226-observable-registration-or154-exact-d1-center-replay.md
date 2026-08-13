# OR154 exact-D1-center replay

OR154 freezes one future write-once observation-conditioned sensitivity replay
cloned from immutable OR153. Its sole change is selected-pawn initial board
coordinate from the retained measured value
`[3.568645477294922, 0.48760929703712463]` to exact D1 center `[3.5, 0.5]`.
It preserves OR153's `-88 deg` scene, settled support Z, upright quaternion,
all 531 raw measured robot rows and timestamps in order, native-step
interpolation, model, solver, contact and object parameters, joint-range union,
one-second settle, and unchanged evaluator.

The future replay has a stricter acceptance rule than OR153. It passes only on
numeric task success, or when selected-pawn contact remains true, at least one
previously false frozen task gate becomes true, and no previously true gate
becomes false. Metric-only improvement cannot pass. This rule is frozen against
the hash-bound OR153 receipt and full 531-row trace before dynamics.

There is no prototype or temporary replay, fit, search, retry, sweep, render,
action mutation, retiming, object injection, latch, endpoint assistance,
hardware access, held-out access, or paid compute. Exact D1 is an
owner-declared canonical-centering sensitivity, not physical measurement,
camera, robot, or action calibration, physics fidelity, physical task evidence,
simulator promotion, or transfer proof.

This slice materializes the owner authorization, contract, implementation,
deterministic static tests, brief, and pre-run Executor log only. No MuJoCo
model compilation, forward call, dynamics step, or replay is permitted during
preflight. A read-only post-run verifier is frozen now so a later closeout must
hash-bind its contract, implementation, Executor log, receipt, and trace.
