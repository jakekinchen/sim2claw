# OR110: renderer-native single-capsule operator reconstruction

## Question

Can the OR109 2D observation be expressed as genuine z-buffered 3D scene
content and materially improve the sampled physical/candidate comparison?

## Frozen construction

- Reuse the exact OR95 scene, camera, workcell registration, independent robot
  registrations, response curve, action-identical state rows, and rasterizer.
- For each materially present OR109 row, select the nearest projected registered
  left/right gripper center and place the actor `0.025 m` toward the camera.
- Invert the frozen rolled pinhole at that depth for both endpoints and radius,
  then instantiate one real triangulated capsule (`248` triangles).
- Estimate one shared development dynamic-component median BGR value and invert
  the frozen response LUT once. Validation cannot change it.
- Render baseline and actor in the same native z-buffer. No physical pixel may
  be copied, warped, blended, composited, or texture-projected into a candidate.

## Claim boundary

Passing OR110 would establish only a retained-footage-conditioned exogenous
actor reconstruction. The capsule depth is a simulator-relative gauge, not a
physical 3D measurement; therefore it cannot establish predictive simulation,
operator trajectory calibration, physics fidelity, transfer, or promotion.
