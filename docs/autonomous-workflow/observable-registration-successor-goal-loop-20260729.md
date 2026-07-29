# Observable Registration and Contact-Causality Goal Loop

Status: `ACTIVE`

Created: `2026-07-29`

## Mission

Execute
`docs/autonomous-workflow/observable-registration-successor-task-queue-20260729.md`
one card at a time. Build a held-out-validated camera/world/robot/object
registration, recover bounded physical pawn-and-jaw observations, localize the
first contact divergence, and evaluate one prospectively justified simulator
correction in a new immutable replay.

## Intended outcome

The repository can answer, with exact artifacts, whether the physical and
simulated episode begin in the same observable state; how camera, robot, jaw,
support, and pawn residuals differ; when physical and simulated contact first
separate; which single simulator mechanism the evidence supports changing; and
whether that correction improves natural-contact task consequence.

## Acceptance criteria

- OR0 through OR8 each reach an evidence-backed terminal status.
- The immutable C6 `0/1` receipt is never edited or rerun.
- Fit, validation, and sealed inputs are role-separated before optimization.
- Camera, geometry, contact, actuator, and outcome proof classes remain
  separate.
- Physical tracks include visibility, confidence, uncertainty, and explicit
  missingness.
- A successor simulator change is prospectively declared and validated away
  from its sealed outcome.
- A new replay preserves exact gateway-sent action bytes, row order, and timing.
- Studio and tracked closeouts show exact advancements and limitations.
- Workflow audit and relevant tests pass; scoped work is committed and pushed
  to `main`; the worktree is clean.
- Hardware remains unopened unless a later explicit current authorization and
  all service/safety gates permit it.

## Evidence standard

Every transition records changed paths, source/config/implementation/output
hashes, exact denominators, fit/validation/sealed counts, residuals, tests,
generated ignored artifacts, known missing channels, proof class, authority,
and the next active card.

## Decision status

### Confirmed

- The retained C922 and D405 RGB streams cover the full sealed physical action.
- The task-plane mapping is accepted but global mapping and exact C922
  calibration are not.
- The crown-only carry-prefix diagnostic failed because of occlusion.
- C6 forms no selected-pawn jaw contact and remains immutable.
- Physical robot motion is at an external elbow-service boundary.

### Recommended defaults

- Use the board plane as the gauge.
- Start with C922 because it is fixed and 30 fps; use wrist RGB to resolve
  contact visibility, not as unearned metric depth.
- Extend `ObservableEpisode.v2-min` through a separately hash-bound visual
  supplement instead of weakening its strict missingness contract.
- Prefer geometric or temporal contact localization before any contact-parameter
  fit.

### Open experiment questions

- Whether retained fixed and articulated tag/board observations identify a
  held-out-valid C922 camera model without new target acquisition.
- Whether C922 silhouettes plus wrist RGB expose enough pawn/jaw evidence to
  time-bound contact and lift.
- Whether the earliest residual supports jaw geometry, spatial mapping, or one
  contact/object mechanism.

## Execution rhythm

1. Read this prompt, the queue, graph, active brief, predecessor receipts, and
   git state.
2. Select only the smallest slice that advances the active card.
3. Freeze tests, source roles, annotations, and evaluator gates before opening
   the outcome.
4. Execute deterministically where possible.
5. Record receipts and proof boundaries immediately.
6. Review against the active card and choose `CONTINUE`, `NUDGE`, `REDIRECT`,
   `STOP`, or `ESCALATE`.
7. Commit and push the scoped transition.
8. Activate exactly one next card and repeat.

Do not stop after planning, infrastructure-only work, a first negative, or a
single occluded landmark. Do not ask the owner to move the robot, pawn, or
camera. Fable or GPT research is reserved for a genuine trajectory blocker
after repository evidence and bounded alternatives have been exhausted.

## Progress ledger

```text
Current state: ACTIVE
Active card: OR6
Completed: predecessor evidence; OR0 corpus; OR1 bounded camera model; OR2 rigid mapping negative; OR3 physical event episode; OR4 first contact divergence; OR5 single zero-offset aperture mechanism
Evidence: OR5 v2 artifact 74845f8e2553a1a9dfd8c6ae9bf82399111d7caf865feea68d7e408936b7a902; aggregate Jacobian singular value 204.972 px/rad; rank 1; validation visual values unopened
Remaining: OR6-OR8
Blockers: no current software blocker; physical motion remains service-gated
Next step: fit one scalar on six v4 views and open the four-view v3 no-refit validation exactly once
```

## Stop conditions

Successful close requires the queue's preferred completion condition or a
fully documented evidence-limited result after all safe cards are exhausted.
Do not treat a local optimizer minimum, visual plausibility, or simulator task
success as mapping or transfer proof. Stop immediately before any unapproved
hardware action, paid compute, destructive operation, or sealed-outcome tuning.
