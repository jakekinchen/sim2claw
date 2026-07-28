# Slice Brief 046 — Multi-View CAD Registration

## Required outcome

Replace sparse-tag-only fitting with a visibility-aware registration of the
exact simulated follower geometry against physical Pi, C922, and D405 frames.
AprilTags remain identity, scale, and link-frame anchors; they are not required
to be visible in every frame.

## Shared model

The optimizer shares one follower kinematic model across cameras and poses:

- tag 1 is bound to `left_upper_arm`;
- tag 2 is bound to `left_wrist`, before `left_wrist_roll`;
- encoder samples provide per-frame joint observations;
- CAD meshes and primitives come from the exact hash-bound candidate manifest;
- camera intrinsics/extrinsics are camera-specific; and
- link geometry, joint-zero offsets, and tag-to-body transforms are shared.

## Visibility-aware objective

For each camera/pose pair:

1. render body-ID, depth, silhouette, and visible CAD edges;
2. compare rendered edges to a CAD-guided physical edge distance transform;
3. compare silhouettes with a robust overlap/distance loss;
4. add tag-corner reprojection only for uniquely decoded visible tags;
5. add encoder and measured-intrinsic priors; and
6. give zero weight to z-buffer-occluded or out-of-frame features.

The neighboring leader arm, camera stand, cables, tags on other bodies, and
chess pieces must be excluded by body-ID/ROI masks rather than explained by
moving follower geometry.

## Optimization and validation

- Optimize camera-only parameters first.
- Then optimize tag transforms and bounded joint zeros.
- Add link dimensions only if the residual remains structured across at least
  three poses and two camera views.
- Use robust Huber/Tukey losses; never substitute missing observations.
- Freeze a new pose M and its camera frames before the final composite fit.
- Promote nothing unless the new heldout passes the existing tag gate and a
  separately frozen dense silhouette/edge gate.

## Current bootstrap

`tools/render_pi_cad_overlay.py` already projects the exact follower geoms into
pose L using the training-only focal and two-link candidate. The renderer
applies the candidate joint-zero offsets, excludes collision proxies, projects
only visual meshes, and draws virtual tag36h11 IDs 1 and 2 at their modeled
link mounts. A bounded per-frame camera-only diagnostic may align those virtual
corners to the detected follower tags; tag 0 on the crossing arm is explicitly
excluded. Its output remains diagnostic: no silhouette fitting, occlusion
reasoning, global-camera promotion, or simulator promotion occurs yet.

## Stop boundary

This is calibration software and static calibration capture only. Stop before
policy, teleoperation, geometric task commands, or task motion.
