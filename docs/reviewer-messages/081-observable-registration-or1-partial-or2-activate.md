# Reviewer message 081 — OR1 bounded pass; activate OR2

Decision: CONTINUE. Evidence anchor: 100.

The camera/world result is fit only to the board gauge and explicitly rejects
the physically implausible projective decomposition. It is sufficient to stop
camera parameters from absorbing downstream robot/jaw residuals, while its
intrinsic and validation limitations remain visible.

Activate OR2. Freeze the OR1 camera completely. Fit only the smallest
task-bounded robot-to-board rigid correction on the six V04 fit jaw
observations, then score the four known-outcome validation observations without
refitting. Report fixed base, articulated links, full jaw pads, and support
plane separately; do not approve the global mapping unless every mandatory
channel passes.
