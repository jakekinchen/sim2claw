# Observable Registration and Contact-Causality Goal Loop

Status: `TERMINAL_RETAINED_DATA_VISUAL_ALIGNMENT_BOUNDARY`

Created: `2026-07-29`

## Mission

Execute
`docs/autonomous-workflow/observable-registration-successor-task-queue-20260729.md`
one card at a time. Build a held-out-validated camera/world/robot/object
registration, recover bounded physical pawn-and-jaw observations, localize the
first contact divergence, explain the remaining OR19 contact-consequence
failure, and evaluate at most one independently justified simulator correction
in a new immutable replay.

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
- OR21 reproduces OR19 before adding any introspection claim.
- OR22A keeps Pi footage separated by execution lineage and either publishes a
  bounded frame/action-interval association or fails closed.
- The original successful physical D1-to-D2 episode is never described as
  having a Pi view.
- Contact or task outcome is never used to align Pi frames or select a
  promotable simulator mechanism. OR49 may use the known exact-episode outcome
  only inside its permanent simulator-diagnostic quarantine.
- OR23 selects exactly one causal branch or returns insufficient evidence;
  OR24 cannot fit an independently unmeasured contact/object property.
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

- The retained C922 and D405 RGB streams cover the full successful physical
  action. That episode has no Pi IMX708 stream.
- Later guarded executions and contact-free tri-camera runs contain Pi IMX708
  videos, relative camera PTS, host process bounds, and host-timestamped joint
  samples. Host bounds do not prove exposure synchronization.
- The task-plane mapping is accepted but global mapping and exact C922
  calibration are not.
- OR19 preserves exact actions and reaches named unilateral contact plus
  `47.513 mm` signed D2 progress, but fails upright, height, and collateral
  gates.
- OR20 localizes simultaneous planar and vertical consequence at sample `248`;
  physical candidate lift begins one sample earlier and definite carry begins
  12 samples later.
- Physical robot motion is at an external elbow-service boundary.

### Recommended defaults

- Reproduce OR19 exactly while logging 5 ms contact, orientation, support, and
  slip state before choosing a mechanism.
- Validate one constant-lag Pi/action timing method on contact-free tri-camera
  motion, then apply it without refit to later guarded runs.
- Keep C922 and D405 RGB as the primary successful-episode sources. Use Pi only
  for same-run robot motion/context and negative-run consequence evidence.
- Associate Pi frames to bounded action intervals rather than claiming exact
  exposure timestamps.

### Open experiment questions

- Which internal simulated event first produces OR19's excessive pawn tilt:
  off-center contact moment, slip, support transition, or downstream collision.
- Whether contact-free motion yields a unique and stable constant Pi/host lag
  under the frozen OR22A gates.
- Whether retained RGB provides a bounded image-plane pawn orientation and
  support-loss witness without metric depth.
- Whether one independently measured mechanism remains admissible after OR23.

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
camera. Never merge Pi frames from one execution with actions or outcomes from
another. Fable or GPT research is reserved for a genuine trajectory blocker
after repository evidence and bounded alternatives have been exhausted.

## Progress ledger

```text
Current state: OR50_PASS_QUARANTINED_NUMERIC_TASK_REPLAY_EVENT_MISMATCH_REMAINS
Active card: none; OR50 terminal consequence success closed
Completed: predecessor evidence; OR0–OR23 and OR26–OR33; OR7C/OR7D and OR24/OR25 not run because their prerequisites failed
Evidence: OR26/OR27 provide the synchronized comparison and samples-248–260 visual split. OR28 isolates aperture as the upright/transport lever; OR29–OR33 reject bounded aperture, base XY, base yaw, and wrist-local corrections under unchanged gates.
Pi lineage: no Pi exists for the successful source; later guarded-run Pi files and contact-free tri-camera files are auxiliary, same-run-only evidence
Retained RGB evidence: OR22 yields 23 jaw and 10 crown proxies; contact/lift/carry timing corresponds, but no accepted pawn-base observation exists and pawn-axis orientation remains unknown
OR23 result: physical contact/lift/carry-start timing corresponds, but no physical channel directly discriminates off-center moment, slip, support transition, or downstream collision
Remaining: event-shape matching, exact intrinsics, pristine heldout extrinsics, globally approved mapping, physical pawn orientation/contact mechanics, promotable matching task outcome, and transfer remain unapproved
Blockers: OR48 still requires an external metric sensor and two jaw-bound landmarks; physical capture and all transfer claims remain false
Next step: preserve OR50's exact terminal success and residuals; any successor must target the early-motion, early-support-loss, absent-bilateral-contact, or transient-tilt channel without relabeling this outcome-informed fit as promotion evidence
```

## Stop conditions

Successful close requires the queue's preferred completion condition or a
fully documented evidence-limited result after OR21 through OR25 are completed
or receipt-backed prerequisites fail. Do not treat a local optimizer minimum,
visual plausibility, Pi timing association, or simulator task success as
mapping or transfer proof. Stop immediately before any unapproved hardware
action, paid compute, destructive operation, cross-episode evidence merge, or
sealed-outcome tuning.
