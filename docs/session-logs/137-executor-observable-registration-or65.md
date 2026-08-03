# OR65 executor session

Date: 2026-08-02

OR65 reproduced the OR58 mean edge F1, all OR59 aggregate region counts, and
the OR64 full-24-line mean edge F1 exactly. The vector family improves
non-motion outside-board aggregate edge F1 from `0.094377` to `0.298451` and
reduces its unmatched edge mass by `883,845`, from `7,494,697` to `6,610,852`.

Outside-board context nevertheless remains the largest residual class. Motion
union retains `3,424,123` unmatched edges and non-motion board retains
`3,286,261`, both below the outside-board residual. The frozen decision rule
therefore selects a pixel-free static environment curve and finite-shape
primitive expansion.

OR65 operated on binary edge maps only and emitted no BGR pixels, image,
texture, video, render, scene mutation, action/state change, physical
composite, or warp. It cannot pass the same-video target.

Focused verification: `2 passed`; combined with predecessor evaluators:
`6 passed`.
