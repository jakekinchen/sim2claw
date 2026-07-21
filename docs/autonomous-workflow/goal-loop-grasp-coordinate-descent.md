# Goal loop: action-frozen grasp coordinate descent

Status: `CLOSED — TERMINAL NEGATIVE FOR ONE PROMOTED COMPOSITE`

## Invariant milestones

### M1 — Frozen search and evaluator boundary

Status: complete.

Required outcome: immutable source actions, episode roles, coordinate bounds,
selection order, trace guardrails, and consequence stop gates. Verification:
hashed contract and fail-closed loader tests.

### M2 — Dense grasp funnel observability

Status: complete.

Required outcome: separate touch, bilateral/opposing capture, retention, slip,
lift, transport, placement, and release. Verification: deterministic synthetic
contact tests and per-episode trace receipts.

### M3 — Sentinel-only coordinate search

Status: complete.

Required outcome: two bounded coordinate passes using only three declared
sentinels. Verification: every candidate, decision, action hash, and simulator
parameter digest retained; only strict lexicographic improvements accepted.

### M4 — Frozen composite evaluation

Status: complete.

Required outcome: freeze the accumulated composite before opening the other
eight campaign episodes. Verification: 11-episode baseline/composite receipt,
paired bootstrap, RMS/EE guardrails, original strict evaluator, and visual
comparison.

### M5 — Closeout

Status: complete with a bounded sensitivity advancement and a terminal
negative for the requested single-composite promotion gate.

Required outcome: accept a consequence-level simulator sensitivity win or name
the first mechanism the retained data can no longer distinguish. Physical
calibration, simulator promotion, training admission, policy improvement, and
transfer remain false.

## Frozen verdict

- Trace-safe V3 doubles lifts from 2/11 to 4/11 with byte-identical actions;
  lift-and-transport remains 1/11 and strict success remains 0/11.
- Base z -15 mm and -20 mm each reach 2/11 lift-and-transport, but both fail
  the frozen joint and EE trace guardrails.
- The five-candidate posterior union covers 6/11 lifts and 5/11 transports. It
  is not a deployable composite and has no promotion authority.
- The paired-bootstrap lower bound for V3's lift delta is zero. The practical
  improvement is verified on the retained episodes, but statistical
  significance is not.
- Perfect measured-state replay fixes arm tracking without fixing grasp
  consequences, localizing the unresolved error to underidentified
  scene/contact variables rather than the action policy or actuator trajectory.

Canonical closeout: `outputs/pawn_bg_grasp_campaign_closeout_v1/` and
`docs/run-logs/2026-07-21-pawn-bg-grasp-campaign-closeout.md`.
