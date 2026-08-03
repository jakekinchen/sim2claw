# OR111: actor reconstruction failure attribution

OR110 was a legitimate 3D render and improved present-frame linear similarity,
but its outside-board edge gain missed the frozen gate. Before adding geometry,
OR111 separates three explanations on the development-present rows:

1. The native 3D capsule silhouette no longer matches the frozen OR109 2D
   shape (`mean IoU < 0.85`).
2. The scene z-buffer hides too much of the actor (`visible coverage < 0.80`).
3. Otherwise, the single-part proxy lacks the hand/forearm boundary detail
   needed by the edge metric.

The card reads the lossless OR110 montage, re-renders only the isolated actor,
and reads no validation or source video pixels. It selects exactly one bounded
successor and cannot change a parameter or promote a result.
