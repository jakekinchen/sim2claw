# Executor session 104 — OR34 measured-state visual twin

Decision: `STOP`

Evidence anchor: `101`

## Result

The retained D1-to-D2 episode now has a separate observation-conditioned visual
twin driven by all `531` raw `follower_actual_position_degrees` rows. The
original row order and timestamps are preserved. The selected pawn receives no
pose injection, latch, grasp/release mode, support projection, endpoint, or
other assistance.

The fitted effective-plant proxy differs from the raw follower trace by:

- `0.893668 deg` overall joint RMS;
- `1.159767 deg` shoulder-lift RMS;
- `1.005129 deg` elbow-flex RMS;
- `7.391400 mm` derived end-effector RMS;
- `15.173119 mm` derived end-effector p95.

With the raw trace, simulated jaw contact begins at sample `230`, inside the
physical `228–232` contact interval. The pawn moves more than `1 mm` at sample
`232`, while the retained physical lift interval does not begin until sample
`247`. This is now the first bounded object-level divergence.

Natural MuJoCo dynamics still tip the pawn by `102.104993 deg` and overshoot D2:
the final planar error is `33.946 mm`, versus `9.945 mm` under the identified
plant proxy. Raw-state progress is `86.165 mm`, versus `47.513 mm` under the
proxy. The raw trace therefore explains a material part of contact timing and
transport distance, but not the upright physical carry.

## Publication

The read-only responsive `/visible-divergence.html` surface defaults to the raw
measured-state lane and permits switching to the identified-plant predecessor.
Both variants share the retained physical C922 playhead. Desktop, variant
switching, playback, and `390x844` mobile layout were inspected in a real
browser.

## Boundary

This result is observation-conditioned and is not action-only transfer,
simulator calibration, global mapping approval, task success, or physical link
pose measurement. The remaining first causal channel is jaw/contact/load-path
response immediately after enclosure. No camera, serial bus, gateway, hardware
motion, paid compute, promotion, task-success claim, or transfer claim opened.
