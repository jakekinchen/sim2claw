# Reviewer message 037 — D1→D2 exact-task pre-motion stop

Decision: `STOP_BEFORE_TASK_ACTION_FREEZE_OR_MOTION`

Evidence anchor: `100`

The fresh follower-only read verifies the expected identity, in-range anchor,
and torque-off state without motion. It does not overturn recovery v2's
terminal decision: exact recovery tracking failed, and its receipt explicitly
keeps Slice B and Slice C closed.

The demonstration-derived task corridor is also not admissible. Two separate
frozen physical campaigns stopped on inward elbow no-progress at observed
positions `97.186813°` and `82.769231°`, while the successful task template
requires `68.703297°` by pre-grasp and reaches `44.527473°`. Existing hover
evidence retains an `11.195 mm` stationary residual and `19.997 mm` route
maximum, which is not pawn-contact authority.

Do not create or execute task bytes by substituting re-anchored joint deltas,
simulator IK, clipping, changed thresholds, assistance, or a corrective
suffix. Do not run Phase 2. The Phase A release remains valid and unchanged.

Accepted proof class:
`prospective_task_preflight_terminal_safety_blocker_no_action_or_task_or_transfer_authority`.
