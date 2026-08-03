# OR67 — Static vector environment video render

Decision: `TWO_CANDIDATE_DEVELOPMENT_SELECTION_THEN_ONE_DECODED_VIDEO`

Evidence anchor: `OR66`

OR66 closes the held-out edge gate in a binary counterfactual. Convert its
finite vector observation into one time-invariant synthetic visual layer over
the existing action-identical OR58 simulator video, then judge the encoded and
decoded result under every unchanged OR55 gate.

## Required outcome

Render all `24` OR63 line primitives and `32` OR66 finite contours at one-pixel
width. For each alpha candidate `0.25/0.50`, assign every primitive exactly one
of the six OR63 palette colors by minimum development-only mean absolute error.
Keep only candidates with development full-frame mean similarity `>=0.80` and
select maximum development edge F1, then p10 and mean pixel similarity. Emit
one `531`-frame MP4, decode it, and score all five gates on the `516` available
physical frames.

## Frozen constraints

- The base is the decoded OR58 candidate. Geometry, actions, timestamps,
  simulator state, and the OR55 evaluator remain unchanged.
- The selected alpha and each primitive color are constant over every frame.
- Physical development pixels may choose among the six frozen material colors,
  but no physical pixel, image, mask, texture, or background plate may enter
  the candidate. Validation and stress cannot select or modify anything.
- No geometric warp, per-frame/phase/region response, missing-frame fill,
  simulator rerun, hardware action, physics claim, or promotion.

## Terminal rule

The decoded video must pass mean full-frame similarity `>=0.80`, p10 `>=0.75`,
motion-union mean `>=0.75`, every phase mean `>=0.78`, and tolerant-edge F1
`>=0.40`. A pass is an episode-specific screen-space visual replay only; it
does not establish metric 3D geometry, calibrated physics, or transfer.
