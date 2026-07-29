# Fable Elbow Boundary and Endgame Review

Date: `2026-07-29`

Thread: existing project thread `Sim-to-real transfer evaluation`

Model / effort: `Fable 5` / `High`

Review mode: read-only advisory at branch
`codex/bidirectional-transfer-goal-loop-20260728`, commit `e4d4f3d`

## Packet reviewed

The review received the current exact claim boundary, the fresh wrist held-out
receipt, mapping closeout, elbow-locked V1--V4 static receipts and closeouts,
attempt ledger (`REAL->SIM 0/0`, `SIM->REAL 0/0`, `0/10` physical task
attempts), false task/mapping/transfer authority, and the requirement to
classify every recommendation as accepted, deferred/rejected, or already
satisfied.

## Independent findings

Fable independently challenged the elbow-locked result with a pose-space
MuJoCo sweep over shoulder pan, shoulder lift, wrist flex, and two wrist-roll
values while holding elbow flex at the measured anchor. It reported:

- all `400` lowest poses below board level self-collided;
- the collision-free floor at pawn radii was approximately `57.5 mm` site
  height, corresponding to approximately `45--48 mm` jaw contact;
- that range independently brackets the V4 compiled-cell first-contact range
  `44.774--48.270 mm`;
- no finite IK, path, multistart, or approach-shape search can satisfy the
  unchanged `<=32 mm` sliding-push contact-height gate at the locked elbow
  anchor.

This confirms the existing V4 receipt-backed boundary for the declared
sliding-push primitive. It does not prove that all pawn consequences are
unreachable.

Fable also inspected retained joint samples and found that the elbow was not
diagnostically proven dead: a `2.91 deg` command excursion produced roughly
`0.79--0.88 deg` measured motion with raw current comparable to the tracking
lift channel, while a constant elbow target held. The evidence admits
`nonresponsive for task admission`; it does not yet distinguish mechanical
resistance, insufficient small-error torque, or a command/protection anomaly.

## Recommendation disposition

| Recommendation | Disposition | Repository action |
|---|---|---|
| Preserve sliding-push infeasibility at the elbow-locked anchor | Already satisfied | V4 receipt `eceb14e3...` and closeout `0df993af...`; no further sliding-push successor. |
| Preserve bounded wrist-channel mapping acceptance | Already satisfied | Held-out receipt `16b7896c...` and mapping closeout `78c4f24d...`. |
| Record full elbow and matched wrist-control telemetry for bounded probes, including a torque disable/enable cycle | Accepted in scope | New queue card `CC03E`; setup-only no-contact motion, no task attempt. |
| Freeze a directional pawn-displacement/knockdown primitive | Accepted in scope | New queue card `CC03K`; distinct proof task, never described as straight push or chess play. |
| Increase elbow Position-P gain in RAM | Deferred | Requires the `CC03E` low-current asymmetric signature and explicit new owner authority; the current authorization forbids gain writes. |
| Inspect, power-cycle, disassemble, or repair elbow hardware | Deferred external boundary | Human intervention and post-deadline work; not agent-owned in this campaign. |
| Continue elbow-locked sliding-push successors, use the simulated second arm, add a tool, or build new architecture/viewers | Rejected | V4 and the independent sweep close the geometry; the physical workcell has no evidenced second arm or agent-placeable tool; existing Studio surfaces are sufficient. |
| Build a synchronized wrist held-out real/sim overlay | Accepted after the directional attempt decision | Reuse the current Studio comparison surface; no new viewer architecture. |

## Accepted directional-displacement contract

The alternative consequence is named **directional pawn displacement**. The
primary evaluator is selected-pawn board-plane displacement in a
prospectively frozen direction quadrant with exclusion objects stationary.
Toppling/fall quadrant is secondary evidence and must be frozen before any
outcome. It is not a straight sliding push and does not demonstrate chess
play.

The bidirectional structure remains strict:

1. `REAL->SIM`: physical consequence first, followed by byte-identical
   CPU/fp64 replay from the same canonical action tensor.
2. `SIM->REAL`: simulator consequence and robustness sealed first, followed by
   one physical attempt on a distinct family.

Static feasibility must preserve current robot identity, calibrated ranges,
self-collision, robot-board exclusion, camera enclosure, gateway margins,
exact-byte, one-attempt, and ten-attempt-ledger gates. At least one
collision-free family per direction must be frozen before evaluator or
physical authority can open. If no family per direction survives, the
campaign remains a terminal hardware/workspace boundary.

## Decision sequence and stop conditions

1. Run `CC03E` elbow/control probes. The result is useful evidence regardless
   of diagnostic class. No gain/configuration write follows automatically.
2. Freeze and run `CC03K` static feasibility. Stop if either direction has no
   collision-free eligible family.
3. If both directions have an eligible family, freeze evaluator/cases within
   the remaining ten-attempt budget, then execute one `REAL->SIM` case and one
   distinct `SIM->REAL` case.
4. Package the supported claim tier and wrist overlay. Never claim above the
   receipt-backed tier.

## Review limitations

Fable did not modify repository files or touch hardware. Its sweep used the
modeled site frame as a jaw-contact proxy at `5--10 deg` resolution. It did
not rerun the full test suite or rederive the CC02 episode arrays. Repository
receipts, safety gates, held-outs, and proof-class boundaries remain
authoritative.
