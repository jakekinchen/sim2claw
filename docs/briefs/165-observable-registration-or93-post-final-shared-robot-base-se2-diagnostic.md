# OR93 post-final shared robot-base SE(2) diagnostic

OR92 localized the semantic failure outside the board. OR93 tests the smallest renderer-native factorization: retain OR84's transform for the photo background, mug, table, and clamps, while both robot subtrees share one separately fitted board-anchored planar rigid transform.

The fit uses only the six already-open OR91 audit frames. A fixed-seed analytic proxy may evaluate at most `195` three-parameter candidates; the selected vector and the original OR84 baseline each receive exactly six full-source-mesh renders with the frozen OR82 camera and OR89 monotone response. No image warp, action change, timing change, video decode, or simulator replay is allowed.

This is retrospective diagnostic evidence. It can select a structural successor only if outside-board edge F1 improves by at least `0.05`, at least four samples improve by `0.02`, and board F1 remains at least `0.50` and within `0.03` of baseline. It cannot restore an untouched cohort or support same-video, physics, transfer, or promotion claims.
