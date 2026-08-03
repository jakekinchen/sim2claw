# Executor session 183: OR111

- Re-rendered the `13` development-present OR110 actors in isolation and read
  the lossless OR110 montage once. No source/candidate video or validation pixel
  was decoded, and no full scene was rendered.
- The isolated native 3D silhouette matches the frozen OR109 2D capsule at mean
  IoU `0.960853` (minimum `0.919286`). In-scene visible coverage is `0.986822`
  (minimum `0.828947`), so neither projection nor depth/occlusion explains the
  OR110 edge shortfall.
- Local physical-edge F1 is already weak for the frozen target (`0.286138`) and
  remains comparable after 3D rendering (`0.281318`). The failure is therefore
  attributed to single-proxy boundary-detail loss.
- Exactly one bounded successor is admitted: a deterministic two-part
  hand/forearm shape test before any second renderer-native actor render.
