# OR98 post-final legacy photo-background ablation

OR97 identifies persistent scene content as the dominant residual. The scene manifest still contains a prior `photo_background` (rear wall, dark window, sill, and blinds) plus an `antler_mug` that do not describe the retained white-enclosure footage. OR98 tests their removal from rendering before creating any replacement geometry.

For the initial state of all eleven episodes, OR98 renders the exact frozen OR95 scene and a single preregistered ablation of body IDs `6-7`. Table, fiducials, board, pawns, clamps, both robots, camera, transforms, response, actions, and states remain fixed. The ablation removes exactly `7,396` triangles and adds nothing.

Selection requires mean outside-board edge F1 to improve by `0.02`, at least eight episodes to improve by `0.01`, and mean board/full-frame metrics not to regress by more than `0.01`. This is retrospective renderer-only evidence, not physics or same-video proof.
