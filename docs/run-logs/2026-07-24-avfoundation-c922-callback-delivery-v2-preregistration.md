# AVFoundation C922 Callback Delivery v2 — Preregistration

Date: `2026-07-24`

Baseline: reviewed clean `main@5d62e15816aa4a1bd7902585a12aeb88ed2d4202`

V1 is terminal degraded and exhausted. V2 does not retry its configuration; it
tests one newly frozen mechanism: associate the exact C922 input with the
session before setting format 16/range 0, then verify active format after input
association, commit, and start before judging delivered buffers.

The v1 count/drop/dimension/subtype/cadence gates remain unchanged. One
observation and at most one ten-second C922 session are available. D405,
robot, simulator, provider, training, promotion, task-score, and physical-task
authority remain closed.
