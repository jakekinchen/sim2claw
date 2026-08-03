# OR65 — Post-environment-primitive edge residual reattribution

Decision: `REATTRIBUTE_AFTER_FULL_FROZEN_LINE_FAMILY`

Evidence anchor: `OR64`

OR64 shows that the complete 24-line environment family has held-out edge
headroom, raising the edge-only counterfactual from `0.180341` to `0.287248`
over the full timeline. Recompute OR59's mutually exclusive residual classes
after that full family so the next mechanism targets the largest remaining
unmatched edge mass.

## Required outcome

Union the frozen 24-line skeleton with each decoded OR58 simulator Canny edge
map. Preserve the exact OR59 motion-union and board masks. Report baseline and
post-vector F1, denominator share, and unmatched edge mass for motion union,
non-motion board, and non-motion outside-board. Reproduce the OR59 baseline
counts and OR64 full-timeline mean edge F1 exactly, then select one next
mechanism using the frozen unmatched-mass rule.

## Frozen constraints

- Bind the immutable goal, OR55 metric, OR26 board registration, OR58 videos,
  OR59 receipt, OR63 scene spec, and OR64 receipt/closeout.
- Use all 24 primitives exactly once. No prefix selection or held-out tuning.
- Operate only on binary edge maps. Emit no BGR pixels, images, textures,
  videos, renders, simulator scene changes, actions, states, or physical
  composites.

## Terminal rule

The card passes when both predecessor metrics reproduce, the region partition
remains exhaustive, and exactly one residual class is selected. It cannot pass
the same-video target; its only outcome is a bounded next-mechanism decision.
