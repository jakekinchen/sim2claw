# OR57 — Board-preserving camera parallax and edge alignment

Decision: `CONTINUE`

Evidence anchor: `OR56`

OR56 raises mean similarity to `0.793053` and clears p10, motion-region, and
all-phase gates, but its `7 px` blur reduces tolerant-edge F1 to `0.133238`.
The source camera is a board-plane registration rather than metric calibration.
Test whether a small camera-distance/focal family can align off-board-plane
robot and piece silhouettes while keeping the observed board corners fixed.

## Required outcome

Replay the immutable OR26 robot and selected-pawn state trace visually—never
through physics—under nine camera-parallax candidates. For each camera, apply
the frozen OR56 global BGR response and each previously frozen blur kernel.
Select among the resulting `36` candidates on development edge F1 subject to a
`0.78` development mean-similarity floor, then open validation and stress.

## Frozen constraints

- Bind OR26 and OR56 contracts, receipts, closeouts, and physical video.
- Scale only the OR26 board-to-camera translation and focal length by the
  preregistered factors; preserve camera rotation and principal point.
- Recompute one board-plane display homography for each camera so the same four
  observed board corners remain exact.
- Preserve all `531` robot and pawn states byte-identically. Do not integrate
  physics, change an action/state/object/contact/scene parameter, or fit to a
  terminal outcome.
- Keep the OR56 BGR matrix fixed. No physical composite, texture, background
  plate, per-frame correction, or additional warp is allowed.

## Terminal rule

Advance the camera-parallax mechanism only if untouched validation edge F1
improves by at least `0.05`, validation mean does not fall below `0.78`, and
stress mean does not regress by more than `0.005` from OR56. Evaluate the one
emitted candidate against every unchanged OR55 gate. Any pass is limited to
episode-specific visual replay and proves neither metric calibration nor
physics fidelity.
