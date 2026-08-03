# OR63 — Renderer-independent static environment scene specification

Decision: `CONTINUE_WITHOUT_RENDERER`

Evidence anchor: `OR59`; runtime boundary: `OR62`

OR59 shows that persistent outside-board scene content is the largest edge
deficit. Every local renderer route is unavailable, so compile the observation
constraints now without copying pixels or pretending a postprocess is a
simulator render.

## Required outcome

On the `220` development frames only, compute physical and OR58-candidate edge
occurrence outside a dilated board polygon. Extract at most `24` persistent
physical-only Hough line primitives, deduplicate them, and derive a six-color
development palette. Freeze those primitives before opening validation and
stress. Report physical and simulator line support on all partitions.

## Frozen constraints

- Bind OR26, OR58, OR59, OR62, the physical video, and the OR58 candidate.
- Stable residual: physical edge occurrence `>=0.35`, simulator occurrence
  `<=0.10`, outside a `7 px` dilated board exclusion.
- Hough threshold `12`, minimum length `18 px`, maximum gap `8 px`; retain at
  most `24` lines using development-only overlap deduplication.
- Palette uses six deterministic BGR centroids from a fixed subsample of
  development pixels outside the board exclusion.
- Emit JSON only. No median image, mask image, copied pixels, texture,
  background plate, render, composite, candidate video, or geometric warp.

## Terminal rule

Pass if at least eight primitives are frozen and their aggregate validation
physical support exceeds simulator support by at least `0.20`. This establishes
a renderer-independent observation specification only. It cannot pass the
same-video target or provide metric 3D geometry.
