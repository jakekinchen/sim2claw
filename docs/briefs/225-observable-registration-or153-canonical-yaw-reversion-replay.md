# OR153 canonical-yaw reversion replay

OR153 is one write-once observation-conditioned sensitivity replay cloned from
OR152. It preserves OR152's transported pawn board coordinate, support Z,
upright quaternion, all 531 raw measured robot rows, timestamps, row order,
native-timestep interpolation, model, solver, contact and object parameters,
joint-range union, post-action settle, and frozen evaluator. Its only admitted
change replaces OR18's outcome-informed left-robot base yaw of `-82 deg` with
the otherwise semantically identical pre-task OR13 scene at `-88 deg`.

The loader must prove that the two scene JSON objects have exactly one semantic
leaf difference at
`simulation_estimates.robots[0].yaw_relative_to_table_degrees`. Source hashes,
the factor boundary, and advancement thresholds are frozen before dynamics.
There is no prototype or temporary replay, fit, search, retry, sweep, sign test,
action repair, IK, offset, clipping, latch, endpoint injection, hardware,
held-out access, paid compute, calibration claim, or transfer claim.

Advancement is measured against immutable OR152: selected-pawn contact must be
preserved and at least one task-consequence metric must improve by its frozen
threshold (1 mm planar error, 5 deg tilt, or 1 mm height), or one unchanged task
gate must flip false-to-true. Full simulator task success still requires every
unchanged OR34 task gate. Whatever the outcome, it remains a simulator
sensitivity diagnostic—not identified calibration, physics fidelity, physical
task evidence, simulator promotion, or transfer proof.
