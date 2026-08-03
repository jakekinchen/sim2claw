# OR59 — Retained edge-residual mechanism diagnosis

Decision: `CONTINUE_EVALUATOR_ONLY`

Evidence anchor: `OR58`

OR58 reaches the numeric temporal range with one global response, but only
four of five gates pass. Mean tolerant-edge F1 remains `0.180341` against the
frozen `0.40` gate. Before another simulator mechanism is proposed, attribute
that deficit to mutually exclusive spatial and temporal classes.

## Required outcome

Recompute the unchanged OR55 edges and motion union from the immutable
physical video and decoded OR58 candidate. Aggregate physical and simulator
edge counts, bidirectional tolerant matches, precision, recall, F1,
denominator share, and unmatched-edge mass for:

- motion union;
- non-motion registered board;
- non-motion outside-board context.

Also publish phase totals and an `8×6` tile table. The class with the largest
unmatched-edge mass selects the next mechanism through a frozen mapping.

## Frozen constraints

- Bind the OR55 contract, OR26 receipt, OR58 receipt/closeout, physical video,
  and OR58 candidate video by SHA-256.
- Use the OR55 Canny thresholds, `3 px` tolerance kernel, motion thresholds,
  blur, and dilation unchanged.
- The three masks must be mutually exclusive and exhaustive on every scored
  pixel.
- No candidate video, renderer, response fit, geometric warp, per-frame or
  per-region correction, physical composite/texture, action, state, physics,
  or hardware operation is allowed.

## Terminal rule

OR59 is diagnostic only and cannot pass the temporal-pixel target. It may
select one evidence-backed visual mechanism. The OR58 mean result remains a
partial numeric similarity until a later decoded simulator candidate passes
all five OR55 gates unchanged.
