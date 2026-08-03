# OR63 executor session

Date: 2026-08-02

OR63 used development frames only to freeze `24` persistent physical-only
outside-board vector lines and a six-centroid BGR palette. The stable residual
contains `20,769` pixels, but no pixel mask or median image was emitted.

The line family generalizes strongly. On untouched validation, mean physical
line support is `0.744611` while OR58 simulator support is `0.045505`, a
`0.699107` gap. Stress support is `0.740194` physical versus `0.056943`
simulator. Both acceptance gates pass.

The primitives include the wooden board surround and persistent environment
boundaries/clutter missing from the simulator view. They remain screen-space,
nonmetric observations: a future renderer must instantiate explicit geometry
and materials. Using them as a background image, texture, or screen-space
overlay is prohibited.

OR63 emitted JSON only. It ran no renderer or simulator replay and emitted no
image, texture, physical composite, warp, or candidate video. The same-video
target remains open.

Focused verification: `2 passed`.
