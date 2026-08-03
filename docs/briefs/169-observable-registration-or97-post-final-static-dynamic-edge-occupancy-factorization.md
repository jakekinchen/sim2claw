# OR97 post-final static/dynamic edge occupancy factorization

OR96 shows that rigid base placement explains only a minority of the persistent outside-board gap. OR97 separates scene-content error from moving robot/articulation error by constructing temporal edge-occupancy maps for all eleven physical/candidate video pairs at the exact OR95 evaluation frames.

Edges present in at least `80%` of an episode are persistent; edges present in `5-80%` are dynamic. Tolerant outside-board F1 is computed directly on each binary occupancy map. If persistent and dynamic F1 are each below `0.60` in at least nine episodes, both renderer-native static scene content and robot articulation are selected.

This is an evaluator diagnostic. It does not render, fit, select a candidate, alter pixels, restore held-out evidence, or support same-video, kinematic, physics, transfer, or promotion claims.
