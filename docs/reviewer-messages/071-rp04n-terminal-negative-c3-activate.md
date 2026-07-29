# Reviewer 071 — RP04N Terminal Negative, Activate C3

Decision: `ACCEPT_TERMINAL_NEGATIVE_ACTIVATE_C3`

The evaluator was frozen before annotation, and both randomized annotation
passes were immutable before the simulator projection was opened. The selected
pawn crown is physically occluded by the gripper for 15 of 18 frozen samples,
so the preregistered visibility and temporal-coverage gates fail without
interpretive rescue.

Preserve `camera_projected_carry_prefix_real_to_sim: 0/1`. Do not substitute a
different landmark or refit the projection after the result. Proceed to C3
using only the frozen whole-episode action and joint-state evidence.
