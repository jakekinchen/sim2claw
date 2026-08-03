# Executor session 182: OR110

- Back-projected each materially present OR109 capsule at the nearest registered
  simulated-gripper depth minus the frozen `0.025 m` camera-forward margin.
  Every actor is a real `248`-triangle 3D capsule in the same native z-buffer as
  the exact OR95 scene.
- Baseline metrics reproduce OR95 exactly, endpoint/radius reprojection is
  numerical-exact, and actor-absent rows are byte-identical to baseline. No
  physical pixel was copied, warped, blended, composited, or projected as a
  texture.
- Present-frame full similarity improves by `+0.009426`; `10/13` present rows
  improve outside-board edge F1. The mean present edge gain is only `+0.007340`
  versus `+0.015`, and the all-sample gain is `+0.004544` versus `+0.008`.
  Development therefore fails and validation remains unopened.
- Montage review shows correct coarse actor placement but a single uniform
  capsule cannot reproduce the hand-plus-forearm boundary detail. The next card
  must distinguish projected-shape loss, scene occlusion, and proxy-detail loss
  before adding any geometry degree of freedom.
