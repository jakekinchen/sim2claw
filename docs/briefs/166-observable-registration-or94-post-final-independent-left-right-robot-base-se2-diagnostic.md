# OR94 post-final independent left/right robot-base SE(2) diagnostic

OR93 rejected one shared rigid transform for both robot subtrees. OR94 separates body IDs `29-36` and `37-44` into independent board-anchored planar registrations while leaving camera, board, static workcell, response, states, actions, and timing fixed.

The fixed-seed search evaluates at most `198` six-parameter candidates. Unlike OR93, its proxy rasterizes the actual source meshes for only the two robot subtrees at `160x120` with the native depth buffer; analytic bounds are prohibited. The original baseline and selected vector then receive six exact full-scene renders each at `320x240`.

Selection requires exact full-scene outside-board edge F1 to rise by at least `0.05`, at least four samples to improve by `0.02`, and board F1 to remain at least `0.50` and within `0.03` of baseline. This remains retrospective diagnostic evidence: there is no untouched cohort and no same-video, physics, transfer, or promotion claim.
