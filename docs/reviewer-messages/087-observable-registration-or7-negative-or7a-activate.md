# Reviewer message 087 — OR7 negative; activate OR7A

Decision: REDIRECT. Evidence anchor: 100.

OR7 changes only the statically validated gripper zero offset, yet the pawn
trace and task result remain exactly C6: zero selected-jaw contact, first
motion at `386`, catastrophic jump at `388`, and `69.148 mm` final D2 error.
The aperture projection residual was real but was not the task's sufficient
causal mechanism.

Do not fit contact material or rerun the task. Activate OR7A to measure the
signed simulator jaw-to-selected-pawn geometric gap over physical samples
`228–260` under both C6 and OR6 mappings. Use kinematic forward evaluation
only, the exact applied states, the unchanged initial pawn, named jaw collision
geometries, and no task outcome fitting. Report the nearest geom pair, gap,
jaw midpoint-to-pawn vector, and differential caused by OR6. This must
distinguish a jaw-center/global wrist spatial miss from a pad-shape miss before
another mechanism is declared.
