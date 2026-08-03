# OR59 executor session

Date: 2026-08-02

OR59 recomputed the unchanged OR55 Canny edges, `3 px` tolerance, and motion
union from the immutable physical video and decoded OR58 candidate. The mean
per-frame edge F1 reproduces OR58 exactly at `0.18034068783682333`.

Non-motion outside-board content is the dominant residual. It contributes
`47.762%` of the total edge denominator and `7,494,697` unmatched edges at
only `0.094377` population-weighted F1. Non-motion board content contributes
`26.993%` at `0.297356` F1 and `3,286,261` unmatched edges. Motion-union
content contributes `25.245%` at `0.217925` F1 and `3,420,934` unmatched
edges. The same outside-board ordering persists in every phase.

The frozen decision rule therefore selects
`observed_static_environment_geometry_and_materials_without_physical_pixel_background`.
This agrees with direct footage inspection: the physical view contains
countertop texture, wall, monitor, cables, clutter, and physical arm detail
that are absent from the simplified simulator view. The board registration is
not perfect, but it is not the largest edge deficit.

OR59 emitted only JSON diagnostics. It produced no candidate video, ran no
renderer or simulator episode, and changed no action, state, physics, response,
or geometry. No physical pixel was composited or used as a texture/background
plate. The full same-video gate remains open.

Focused verification: `2 passed`.
