# Brief 095 — Observable registration OR2 robot/jaw mapping

Decision: CONTINUE. Evidence anchor: 100.

## Slice

Under the frozen OR1 camera/world model, fit only one planar-yaw plus XYZ
robot-to-board rigid correction from the six V04 fit jaw observations. Preserve
the existing physical-to-model joint mapping and modeled jaw geometry. Emit
fixed and moving jaw-tip as well as midpoint projections, then evaluate the
four V04 known-outcome validation observations with no refit.

## Acceptance

- OR1 camera intrinsics, distortion assumption, extrinsics, and board gauge are
  byte-bound and immutable.
- Fit parameters are exactly yaw plus XYZ translation, with prospective bounds.
- Fit annotations and validation annotations remain separate.
- Validation is labeled known-outcome reuse and cannot independently approve
  global mapping.
- Jaw midpoint and both annotated jaw tips have separate residuals.
- Existing fixed-base, articulated-link, robot-silhouette, and support-plane
  channels are imported without reinterpretation.
- Global mapping is true only if every mandatory channel passes; otherwise the
  best task-bounded jaw projection remains available for OR3/OR4 with an
  explicit ceiling.
- Tests cover camera immutability, split leakage, deterministic fit, bounds,
  validation no-refit, and global fail-closed behavior.

## Stop

OR2 may accept a task-bounded jaw projection while keeping global mapping
false. It cannot fit contact dynamics, use task outcome, rerun C6, open
hardware, or claim transfer.
