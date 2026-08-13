# OR156 independent review — source-clock provenance

Date: 2026-08-13

Decision: `STOP`

Scientific verdict: `PASS_TO_CLOSE_STOP_EXTERNAL_INPUT_BOUNDARY`

Evidence anchors: `100`. The exact pushed candidate is
`51352a9d5f3ccf899bf0cb79a79e86c3023ac1aa`; `HEAD == origin/main`, the agent
check and goal check pass, and all nine contract source hashes match. The
official receipt verifies with file SHA-256
`37a0aa946a7b69bb3feda14f7e8111949f6f4ec9308194c27b4126215079a4a7`
and content digest
`a7286e739bffb65134e9006629f0c99a686106370fd785859a11423aa8962819`.

Independent raw-JSONL derivation matches the receipt: 531 sample rows, 1,236
callbacks, 1,029 admitted C922 frames, and 171 admitted D405 frames. The
closure direct-clock separation is at most `0.039208 ms`; the maximum closure
elapsed-time rebind is `1.142334 ms`; and both cameras retain identical frame
indices at samples `224`, `228`, `232`, and `241`. The largest absolute full-
trace elapsed delta is `5.998042 ms` at sample `220`, while the D405 primary
association error reaches `100.066125 ms`. All 531 rows lack actuator
application/ack timestamps and synchronized device clocks.

The scientific conclusion is deliberately narrow. OR156 falsifies only the
sample-completion versus immediately preceding follower-position-read clock
choice under the frozen nearest-host-time/lower-frame-index association and
relative elapsed-time rebind. It does not falsify camera exposure timing,
actuator-application timing, device-clock error, another clock source, or the
spatial/contact explanations. Those remain unidentified.

The official path used zero MuJoCo calls, dynamics steps, simulator replays,
renders, fits, searches, task evaluations, mutations, hardware actions, or
paid compute. All 13 claim limits remain false and focused tests pass `3/3`.
OR156 supplies no correction and no task-level advancement. No successor is
admissible; close at the external-input boundary.
