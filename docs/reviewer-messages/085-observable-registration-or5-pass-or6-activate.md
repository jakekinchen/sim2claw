# Reviewer message 085 — OR5 pass; activate OR6

Decision: CONTINUE. Evidence anchor: 100.

OR5 identifies exactly one fit-capable family:
`single_gripper_zero_offset_aperture_mapping_v1`. The aggregate Jacobian is
rank one with singular value `204.972 px/rad`, condition number `1.0`, and
same-sign response across all six fit views. Gripper gain remains
unidentifiable because every retained pose has the same physical gripper
value. Preserve the v1 per-view threshold negative.

Activate OR6. Fit only `gripper_zero_offset_rad` against the six v4 jaw-pair
separations. Then open the four v3 validation annotations once, score the
already fixed candidate without refit, and apply the preregistered separation,
relative-improvement, midpoint-regression, and joint-range gates. Keep the OR1
camera, OR2 robot-board transform, all mesh/collision geometry, body-joint
mapping, actuator plant, contact material, object properties, initialization,
and actions unchanged. This static fit cannot approve global mapping or task
transfer.
