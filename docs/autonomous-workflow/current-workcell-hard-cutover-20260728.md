# Current-workcell hard cutover

Status: verified complete.

## Outcome

All future Studio, episode-recording, and new transfer work uses one
transform-free public runtime: `sim2claw.current_workcell`. Standard rank 1 is
the near robot/operator side, rank 8 is far, and files run a-to-h
left-to-right from the operator view.

Commit `9e563f4` is the immutable historical boundary. The hash-bound
`src/sim2claw/scene.py`, prior receipts, action tensors, labels, and hashes are
not rewritten. Historical reproduction remains read-only through
`sim2claw.legacy`.

The immutable renderer still requires one private fixed physical-layout
binding inside `current_workcell.py`. That detail is quarantined: active
callers cannot select a transform, frame, or compatibility mode. Replacing
the hash-bound renderer would invalidate prior contracts and is therefore
outside this cutover.

## Milestones

| ID | Status | Acceptance |
|---|---|---|
| HC-01 | complete | Boundary and every production scene caller classified in `configs/migrations/current_workcell_hard_cutover_v1.json`. |
| HC-02 | complete | Canonical current-workcell API exposes no frame or transform parameter. |
| HC-03 | complete | Studio live, Studio assets, and the record workspace use the canonical builder. |
| HC-04 | complete | Explicit read-only legacy facade exists; frozen scene hash remains `4b7dd7b...`. |
| HC-05 | complete | Architecture and geometry regressions cover the active callers, all 64 unique centers, canonical body placement, and immutable history. |
| HC-06 | complete | `96` tests and `18` subtests pass; compileall, diff check, JSON/caller audit, and workflow audit pass; scoped commit is pushed. |

## Stop conditions

- Physical authority, gateway/serial authority, and counted attempts remain
  false.
- No physical packet may be frozen until a fresh canonical task-plane
  registration demonstrates `<=25 mm` error.
- Any historical hash drift fails the cutover closed.
- Any active caller importing `build_scene_spec`, a board-orientation adapter,
  or a frame/transform selector fails CI.

## Verification

The final relevant suite passed `96` tests plus `18` subtests. Python
compilation, `git diff --check`, JSON parsing, exact `24/24` production-caller
classification, and the autonomous workflow audit passed. The known
repository-wide live-C922 native segfault remains outside this cutover and
was not relabeled as a pass.
