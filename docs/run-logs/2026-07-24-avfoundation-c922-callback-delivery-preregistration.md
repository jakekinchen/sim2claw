# AVFoundation C922 Callback Delivery v1 — Preregistration

Date: `2026-07-24`

Baseline: `main@7ad9757fb7d23d52f24635b4d4d234b1fe2983e0`

This transaction measures one C922-only AVFoundation callback stream against
the candidate selected by the sealed format-inventory v2 evaluator. The frozen
candidate is format `16`, range `0`, `640×480`, `420v`,
`30.00003000003 fps`, with frame duration `0.03333330000003333 s`.

The observer implementation does not exist at preregistration time. The
contract permits one ten-second capture session and at most 600 callbacks. It
permits no D405 lifecycle operation, robot motion, simulator replay, provider
call, training, promotion, task-score change, or retry.

The independent evaluator will report verified delivery, degraded delivery,
or prerequisite abstention. Even a verified result proves only native
camera-source callback delivery; it does not prove container timing, physical
exposure continuity, cross-camera synchronization, metric calibration,
simulator fidelity, or task success.
