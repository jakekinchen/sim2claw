# Brief 100 — Observable registration OR6 jaw aperture fit

Decision: CONTINUE. Evidence anchor: 100.

## Slice

Fit the single OR5-approved `gripper_zero_offset_rad` parameter on six v4
static views, then score the fixed candidate on four v3 static views with no
refit.

## Acceptance

- freeze implementation, optimizer, objective, source bindings, and all gates
  before opening the v3 validation annotations;
- fit only jaw-tip pair separation in pixels;
- do not fit tip midpoint, camera, robot-board transform, gain, body joints,
  mesh/collision geometry, plant, contact, object, action, timing, or task
  outcome;
- report baseline/candidate separation residuals and midpoint residuals for fit
  and validation;
- require fit RMS at most `3 px` and at least `80%` relative improvement;
- require validation RMS at most `5 px` and at least `70%` relative
  improvement;
- require midpoint RMS regression at most `5 px` in both cohorts;
- require the parameter at least `0.005 rad` from either bound;
- require all transformed fit, validation, and sealed C6 gripper positions to
  remain inside the model joint range;
- retain `global_mapping_approved:false`.

## Stop

OR6 promotes a versioned simulator candidate only if every static and
regression gate passes. It may not run the dynamic task replay.
