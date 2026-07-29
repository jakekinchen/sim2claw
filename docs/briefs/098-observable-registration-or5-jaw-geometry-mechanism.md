# Brief 098 — Observable registration OR5 jaw geometry mechanism

Decision: CONTINUE. Evidence anchor: 100.

## Slice

Use the frozen OR2 static jaw annotations and immutable OR1 camera to determine
whether a bounded jaw-aperture/contact-geometry correction is identifiable
without the C6 task outcome. Declare exactly one finite mechanism family and
its fit/validation roles before any successor evaluation.

## Acceptance

- inventory the physical gripper positions represented by the OR2 fit and
  validation observations;
- reject gripper gain or offset if the retained poses do not excite aperture;
- preserve OR1 camera parameters and OR2 robot-board transform;
- define the smallest jaw-axis geometry parameterization supported by the
  static observations;
- freeze parameter bounds, optimizer behavior, fit observations, untouched
  validation observations, residual gates, and model-regression gates;
- keep the C6 terminal outcome sealed and do not run a dynamic task replay;
- keep contact material, actuator plant, object parameters, actions, timing,
  and initialization unchanged;
- explicitly retain `global_mapping_approved:false`.

## Stop

OR5 ends with a frozen, identifiable static-geometry contract or a terminal
`no_identifiable_mechanism` closeout. It cannot promote a candidate or open the
successor dynamic replay.
