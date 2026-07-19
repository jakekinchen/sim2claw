# Slice Brief 006: Studio Dynamic Task Orchestrator

**Status:** proposed architecture and implementation plan; no orchestrator,
remote camera intake, model call, ACT execution, or physical authority is
implemented by this brief

**Primary surface:** a new Studio tab labeled **Task Orchestrator**

**Requested model:** user-facing label `5.6 luna`, medium reasoning, supplied
through a server-side model adapter. The exact provider identifier must be
resolved and frozen by that adapter; the implementation must fail closed
rather than silently substitute another model.

## Objective

Add a bounded dynamic task runtime to Studio. While a user-controlled session
is active, the runtime obtains one overhead frame from the workcell connected
to `silicon.local.net` at a configurable interval, suppresses visually
redundant frames, combines material visual changes with user chat, asks the
configured model to select from an allowlist of promoted ACT skills, executes
at most one skill at a time, and verifies its postcondition before continuing.

The first named compound task is **restore the managed B--G pawn region to its
base case**. The orchestrator is a downstream consumer of promoted policies;
it cannot train, evaluate, admit, or promote a checkpoint. All policy, camera,
model, frame, decision, and action identities must be recorded in an ignored
session receipt.

## Current repo boundary

- Studio is a dependency-free, loopback-first HTTP service. Its current live
  camera adapter discovers local AVFoundation devices and has no remote frame
  adapter for `silicon.local.net`.
- Current Studio POST controls are loopback-only. The orchestrator must retain
  that boundary and keep provider credentials out of the browser.
- The current sparse MuJoCo layout includes brown pawns on `A2, B1, C2, D1,
  E2, F1, G2, H1` and mirrored tan pawns on ranks 7--8. The orchestrator base
  case manages only B--G on ranks 1--2; A/H and the tan side are outside its
  authority and remain untouched.
- The frozen B--G language contract defines 12 same-file moves, B1<->B2 through
  G1<->G2. A promoted compatible ACT checkpoint does not yet exist for those
  12 physical actions. Initial implementation must therefore stop at
  observation/dry-run and simulation execution until separately evaluated
  skill adapters are available.
- Studio currently reports `physical_authority: false`. This brief does not
  change that value or authorize physical policy execution.

## User experience

The Task Orchestrator tab should expose:

1. **Session controls:** Start, Pause/Resume, and Stop.
2. **Mode:** Observe only, Simulation, Physical shadow, and Physical gated.
   Only modes that pass their own capability and authority preflights are
   selectable. Observe only is the initial default.
3. **Overhead source:** connection state, latest captured frame time, latest
   accepted-frame hash, and source health.
4. **Polling:** default 15 seconds, adjustable without restarting the session.
   A bounded initial range of 2--300 seconds is sufficient.
5. **Deduplication:** default similarity threshold `0.97`, with the current
   similarity score and suppression count visible in advanced details.
6. **Base-case state:** required squares, observed occupancy, mismatched files,
   confidence, and the evidence frame used for the classification.
7. **Chat:** user messages wake the model immediately even if the new frame is
   visually redundant.
8. **Allowed skills:** immutable skill ID, checkpoint/evaluator receipt,
   execution mode, readiness, and last result.
9. **Action queue:** proposed plan, current single action, expected
   postcondition, and verification state.
10. **Session ledger:** accepted/ignored frames, model decisions, executed
    skills, pauses, faults, and user acknowledgements.

The main status must never collapse `observing`, `proposed`, `executing`,
`verified`, and `failed` into a generic “active” indicator.

## Base-case contract

Create a versioned contract with an ID such as
`pawn_bg_diagonal_base_case_v1`.

### Managed region

- Files: B, C, D, E, F, G.
- Ranks: 1 and 2.
- Piece class: brown pawns.
- Pawns are interchangeable for base-case restoration; occupancy, not hidden
  physical identity, defines the state.
- A/H, ranks 3--8, tan pawns, robots, props, and anything outside the managed
  board region are immutable context.

### Required occupancy

```text
B1, C2, D1, E2, F1, G2
```

### Required empty squares

```text
B2, C1, D2, E1, F2, G1
```

### Restorable state

Each managed file must contain exactly one confidently observed pawn on rank 1
or rank 2. A non-base file can then be restored with exactly one allowlisted
same-file ACT move. Restore files one at a time and reacquire/verify a frame
after every move.

If a file contains zero pawns, two pawns, an uncertain pawn, an obstruction, or
a pawn outside the supported two-square pair, the orchestrator must ask the
user for help. It may not improvise an unregistered cross-file recovery.

“Restore all non-base cases to the base case” means: repeatedly restore every
confidently restorable mismatched file until the managed occupancy equals the
required occupancy, or pause with a precise blocker.

## Frame intake and comparison

### Remote source adapter

Add a server-side `silicon_overhead_snapshot_v1` adapter. The implementation
must define and verify one authenticated or otherwise explicitly protected
snapshot endpoint on `silicon.local.net`; the current repo has no such endpoint
contract. The browser must not connect directly to the remote camera or hold a
camera/model credential.

Every captured frame record includes:

- source host and camera role;
- capture timestamp and Studio receipt timestamp;
- width, height, encoding, byte count, and SHA-256;
- source freshness/maximum-age result;
- board-registration/ROI contract identity;
- fetch duration and any error.

A stale, malformed, oversized, redirected-to-unapproved-host, or unavailable
source pauses the orchestrator. Do not reuse the last image as if it were live.

### Two different visual comparisons

The `0.97` threshold is only a **model-call deduplication gate**:

1. Rectify and crop the registered board/workcell region.
2. Normalize bounded luminance/exposure changes.
3. Compare the new ROI with the last frame accepted for model reasoning using
   a frozen metric such as SSIM.
4. If similarity is greater than or equal to `0.97`, record the frame as
   ignored and do not call the model.

Whole-frame similarity is not evidence that the pawn arrangement matches the
base case. A single moved pawn may occupy too few pixels to lower a global
score reliably. Base-case classification therefore uses a separate
square-level occupancy result with confidence for every managed square.

The following events force an accepted observation even when similarity is at
or above the deduplication threshold:

- user chat;
- Start or Resume;
- completion or failure of an ACT skill;
- explicit user Refresh;
- a source-health recovery after a fault.

## Session state machine

```text
STOPPED
  -> STARTING
  -> OBSERVING
  -> AWAITING_MODEL
  -> PROPOSED_ACTION
  -> EXECUTING_SKILL
  -> VERIFYING
  -> OBSERVING

Any active state -> PAUSING -> PAUSED
Any active state -> STOPPING -> STOPPED
Any active state -> FAULTED -> PAUSED
```

Rules:

- Only one model turn and one skill execution may be active at a time.
- A new frame may be captured while a skill runs for evidence, but it cannot
  cause a second skill dispatch.
- Pause prevents new polling, model turns, and skill dispatch while preserving
  the session ledger.
- Stop cancels future work, requests the current adapter's safe-stop behavior,
  releases leases/resources, and requires a new Start for future execution.
- An in-flight physical adapter must reach its fail-closed stop/torque-off
  boundary before the session reports Paused or Stopped.

## Inactivity behavior

Use two independent five-minute timers, both defaulting to 300 seconds and
both visible in the UI:

1. **User inactivity:** time since Start/Resume or the most recent user chat,
   manual Refresh, or explicit action approval.
2. **World/action inactivity:** time since a material accepted frame change or
   a skill start/completion.

Expiry of either timer requests auto-pause. The runtime finishes or safely
stops the one in-flight skill, records the exact pause reason, stops polling
and model calls, and requires explicit Resume. Polling and ignored duplicate
frames do not reset either timer.

## Model-orchestrator contract

The model adapter is server-side and receives only bounded, receipt-linked
context:

- configured model and reasoning effort;
- current accepted frame and base-case reference image;
- structured managed-square occupancy plus confidence;
- newest user chat message and bounded recent conversation;
- current session state and recent action results;
- exact allowlisted skill schemas and promotion receipts;
- the immutable base-case contract and authority limits.

The system prompt must state:

1. The base case is B1, C2, D1, E2, F1, G2 occupied and the paired opposite
   squares empty.
2. Only B--G ranks 1--2 are managed. Everything else is immutable context.
3. Exactly one allowlisted skill may be requested per decision.
4. The model may propose actions but cannot bypass executor validation.
5. It must ask the user when occupancy, calibration, obstruction, skill
   readiness, or postcondition confidence is insufficient.
6. It cannot declare task success from its own prose; the state/evaluator
   result owns completion.
7. It cannot train, promote, change a checkpoint, edit a contract, call an
   arbitrary command, or emit raw joint/servo actions.

Require a schema-valid response such as:

```json
{
  "decision": "observe|ask_user|run_skill|pause|complete",
  "reason": "short auditable rationale",
  "skill_id": null,
  "arguments": {},
  "expected_postcondition": {},
  "confidence": 0.0
}
```

Invalid, unavailable, timed-out, or policy-violating model output is recorded
and pauses the session. Do not retry indefinitely and do not substitute a
different model silently.

## Skill adapter and execution contract

The orchestrator-facing registry is a runtime view of separately promoted
skills. Each entry must bind:

- `skill_id` and version;
- ACT architecture and checkpoint digest;
- evaluator and promotion receipt digests;
- observation/action schemas;
- supported scene/workcell/calibration identities;
- preconditions, expected postconditions, timeout, and safe-stop behavior;
- execution modes: simulation, physical shadow, or physical gated;
- known failure regions and recovery restrictions.

The initial intended allowlist is the 12 B--G same-file rank moves, but an
entry remains unavailable until a compatible checkpoint has passed its
separate evaluator. The frozen rook-lift ACT proof is not a pawn reset skill
and cannot be relabeled into this registry.

The executor validates the requested skill and arguments, rechecks the latest
state, obtains any mode-specific authority, dispatches one adapter, records its
trace, and forces a post-action observation. The model cannot dispatch another
action until that postcondition is verified or the session pauses.

## Physical authority boundary

Implement in four capability tiers:

1. **Observe only:** remote frames, deduplication, base-case classification,
   chat, dry-run model decisions, and receipts. No policy execution.
2. **Simulation:** run allowlisted skills only against the bound MuJoCo scene.
3. **Physical shadow:** generate and display the action that would be requested,
   but issue no hardware command.
4. **Physical gated:** later and separately authorized. It must use the single
   reviewed gateway, require a fresh operator/workcell acknowledgement, prevent
   concurrent recorder/live owners, enforce skill timeout/tracking/stall
   limits, and prove torque-off shutdown.

The first three tiers do not grant physical authority. Tier 4 must not be
enabled merely because the model, simulation, or a checkpoint reports success.

## Proposed server surfaces

Keep all mutating routes loopback-only:

```text
GET  /api/orchestrator
GET  /api/orchestrator/frame
POST /api/orchestrator/session   {action: start|pause|resume|stop}
POST /api/orchestrator/chat      {message: ...}
POST /api/orchestrator/refresh   {}
```

Run camera polling, model calls, and skill execution in a background service;
never block the Studio HTTP request thread for a model turn or policy rollout.

Suggested implementation boundaries:

- `task_orchestrator.py`: state machine, timers, event queue, and receipts;
- `orchestrator_frames.py`: Silicon snapshot adapter, ROI preparation, hashes,
  similarity, and source health;
- `orchestrator_perception.py`: square-level occupancy contract;
- `orchestrator_model.py`: exact `5.6 luna` provider adapter and response
  validation;
- `orchestrator_skills.py`: registry loading and one-at-a-time dispatch;
- versioned base-case and orchestrator configs below `configs/`;
- ignored session output below `runs/task_orchestrator/<session-id>/`.

## Evidence and privacy

For every session retain:

- configuration and contract digests;
- start/pause/resume/stop/fault timestamps;
- all captured-frame hashes and comparison scores;
- accepted frames and forced-accept reasons;
- ignored-frame metadata without requiring duplicate model calls;
- model request identity, response, validation result, latency, and token/cost
  fields when available;
- user messages;
- requested, rejected, executed, and verified skill events;
- policy/checkpoint/evaluator identities;
- pre/post state and frame identities;
- final physical-authority and torque-off fields.

Credentials, raw provider secrets, and unrestricted remote URLs never enter
Git, browser storage, the model prompt, or receipts. Retention of raw accepted
frames should be configurable; hashes and decision lineage are mandatory.

## Implementation slices

### TO-0: freeze contracts and fixtures

- Freeze the base-case, orchestrator configuration, event/result schemas, and
  a small sequence of synthetic frame fixtures.
- Define the Silicon snapshot endpoint contract without opening hardware.
- Add negative fixtures for stale frames, camera drift, missing pawns, two
  pawns in one file, malformed model output, unavailable skills, and timeout.

### TO-1: Studio observe-only tab

- Add the Task Orchestrator tab and session state display.
- Implement Start/Pause/Resume/Stop, polling interval, inactivity timers,
  remote frame health, and receipts.
- Display the image and decisions; do not call a model or execute a policy.

### TO-2: frame deduplication and base-state perception

- Implement registered ROI preprocessing and the frozen similarity metric.
- Prove `>= 0.97` suppresses redundant model inputs while small square-level
  changes still reach base-case classification.
- Keep base-case confidence and deduplication similarity separate in API/UI.

### TO-3: model dry run

- Add the exact configured `5.6 luna` model adapter at medium reasoning.
- Chat and material frames produce schema-validated dry-run decisions.
- Show rejected/unavailable action proposals without dispatching them.

### TO-4: simulation skill execution

- Admit only separately evaluated ACT adapters.
- Execute one requested skill in MuJoCo, force a new observation, and verify
  the postcondition before continuing.
- Demonstrate restoration from every one-file mismatch and several multi-file
  combinations.

### TO-5: continuous base-case restoration

- Support “restore all non-base cases” as a bounded sequence of individually
  verified moves.
- Stop complete when the deterministic managed-region checker passes, not when
  the model claims completion.
- Pause on ambiguous, unsupported, obstructed, or failed states.

### TO-6: physical shadow and separately authorized canary

- First compare proposed actions with supervised operator choices in shadow
  mode.
- Define a new physical evaluator and operator approval procedure.
- Only then consider one bounded physical skill canary through the existing
  gateway. Dynamic unattended physical execution is outside this brief.

## Acceptance criteria

- The tab is accessible and usable without affecting Replay, Library,
  Calibration, Robots, Record, or Live leases.
- Default polling is 15 seconds and can be adjusted during a session.
- A frame at or above 0.97 similarity is ignored for model reasoning, recorded
  as ignored, and does not reset inactivity timers.
- User chat forces an immediate accepted observation/model turn.
- Either five-minute inactivity timer auto-pauses with an explicit reason.
- The base-case contract is exactly B1/C2/D1/E2/F1/G2 within the managed B--G
  rank-1/rank-2 region.
- Whole-frame similarity is never used as the base-case verdict.
- The model can select only schema-valid allowlisted skills.
- No second skill starts before the first skill's postcondition resolves.
- Stop and fault paths release frame/model/skill resources; any future physical
  adapter proves fail-closed torque-off.
- The deterministic checker, not the model, owns base-case completion.
- Observe-only and simulation receipts retain `physical_authority: false`.
- Current absence of promoted B--G ACT skills is presented as an unavailable
  capability, not silently replaced by rook, GR00T, scripted, or raw-motion
  behavior.

## General implementation task

Build a loopback-controlled, receipt-producing Studio Task Orchestrator that
observes an authenticated Silicon overhead snapshot source, suppresses
redundant frames, classifies the versioned B--G base-case occupancy, combines
material changes and user chat into bounded `5.6 luna` medium-reasoning turns,
and dispatches at most one separately promoted ACT skill at a time with
postcondition verification, inactivity auto-pause, and no physical authority
until a later explicit gateway canary.
