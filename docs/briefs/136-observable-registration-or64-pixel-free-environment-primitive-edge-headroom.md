# OR64 — Pixel-free environment primitive edge headroom

Decision: `EVALUATE_ALL_PREFIXES_NO_SELECTION`

Evidence anchor: `OR63`

OR63 freezes `24` persistent physical-only line constraints. Quantify how much
of the unchanged OR55 edge deficit those vectors could address if implemented
as explicit scene geometry. This is an edge-only counterfactual, not a render.

## Required outcome

Rasterize line-skeleton prefixes `8`, `16`, and `24`; union each with the
decoded OR58 simulator Canny edge map; and recompute the unchanged `3 px`
tolerant-edge F1 for development, validation, stress, and all `516` frames.
Report every prefix, the improvement over the exactly reproduced OR58 edge
baseline, and the remaining gap to `0.40`.

## Frozen constraints

- Bind the immutable OR63 scene spec and closeout, OR55 metric, physical video,
  OR58 video, and OR58 receipt.
- Primitive order and prefixes are frozen. Validation/stress cannot select a
  prefix.
- Add only one-pixel vector skeletons to the simulator edge map. No BGR pixels,
  physical pixels, masks, images, textures, video, renderer, scene mutation,
  warp, or postprocessed candidate may be emitted.

## Terminal rule

A validation edge-F1 gain of at least `0.02` is a mechanism-headroom advance.
Even a counterfactual result above `0.40` cannot pass the target; only a future
decoded simulator video may be evaluated for that claim.
