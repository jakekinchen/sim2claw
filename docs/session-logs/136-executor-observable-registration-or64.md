# OR64 executor session

Date: 2026-08-02

OR64 reproduced the OR58 mean edge F1 exactly at `0.18034068783682333`
and evaluated every frozen vector prefix without selection. The `8`, `16`,
and `24` line prefixes raise the edge-only full-timeline counterfactual to
`0.238207`, `0.268438`, and `0.287248`, respectively.

The full `24`-line family improves untouched validation by `0.107020` to
`0.285621` and stress by `0.103638` to `0.291106`. This is strong evidence
that missing environment geometry is a real mechanism, not merely a
development artifact. It still leaves a `0.112752` gap to the unchanged
`0.40` edge gate.

OR64 operated on binary edge maps only. It emitted no BGR image, texture,
video, render, scene mutation, physical composite, or warp. The counterfactual
cannot pass the same-video target.

Focused verification: `2 passed`.
