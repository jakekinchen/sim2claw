# Bidirectional Pawn-Push Transfer Task Queue

Status: `ACTIVE`

Created: `2026-07-27`

Owner: one new same-checkout implementation agent

Required checkout: `/Users/kelly/Developer/sim2claw`

Required branch: `codex/geometric-microtransfer-20260727`

## Mission

Produce the smallest honest, camera-verifiable proof of bidirectional task
transfer between the physical SO-101 workcell and MuJoCo without asking the
user to touch, reset, support, inspect, or reposition the robot, board, pawns,
or cameras.

The target claim is:

> Under a preregistered evaluator, at least one of at most ten counted
> adjacent-square pawn-push cases transferred bidirectionally between the
> physical SO-101 workcell and MuJoCo. One prospectively frozen
> hardware-first action achieved camera-owned physical task success and
> identical-canonical-byte simulator task success. A separate
> simulator-first action achieved simulator task success before freeze and
> camera-owned physical task success after unchanged hardware execution. All
> counted failures remain in the denominator.

The task is a closed-jaw adjacent-square pawn **push**, not general chess
pick-and-place. Do not broaden the final claim.

### Active F1 claim reduction

Q03 triggered the preregistered F1 fallback. The metric registration
held-out gate failed, so the target claim above is no longer available.
For all subsequent cards, the maximum possible claim is:

> Under a preregistered evaluator, at least one prospectively frozen
> hardware-first action and one separate simulator-first action each
> displaced the selected pawn base center completely off its admitted source
> square in both the physical SO-101 workcell and MuJoCo while preserving
> identical canonical action bytes within each case. Every counted failure
> remains in the denominator.

Destination-square occupancy is no longer required or claimed. This is a
bidirectional off-source displacement primitive, not adjacent-square
placement and not the original registration-qualified target.

## Source-of-truth order

1. The latest user instruction.
2. `AGENTS.md`.
3. This task queue, including its live status and evidence ledger.
4. Immutable physical receipts and media under
   `runs/prospective-real-to-sim/`.
5. Existing workflow briefs, executor logs, reviewer messages, and run logs.
6. `GOAL.md` and `docs/autonomous-workflow/project_state.json`.
7. Commit messages, summaries, and advisory-model output.

Repository and receipt evidence outrank this queue where they contradict a
starting hypothesis. Update the queue rather than rewriting evidence.

## Starting evidence

- Public Phase A release:
  `https://github.com/jakekinchen/sim2claw/releases/tag/phase-a-real-to-sim-d1-d2-20260727`.
- Latest branch commit at queue creation: `d7c8e15`.
- Current strict headline: `TWIN FIDELITY 0/6`, `TASK SCORE 0/11`,
  complete bidirectional cases `0`.
- C2 physical task:
  `runs/prospective-real-to-sim/20260727-c2-c1-exact-v1/`.
  All `701` counted float64/40 Hz rows were issued unchanged with zero clamps,
  rate limits, or bus retries. The pawn was displaced/toppled near C2, not
  upright on C1.
- C2 physics replay:
  `runs/prospective-real-to-sim/20260727-c2-c1-exact-v1/physics/exact_action_replay_receipt.json`.
  Identical canonical bytes produced no pawn contact, zero rise, and
  `312.326 mm` minimum gripper clearance. Its joint transform is
  `calibration_approved:false` and
  `review_status:provisional_range_audit_blocked`.
- Servo health:
  `runs/prospective-real-to-sim/20260727-d1-d2-elbow-health-v1/health_receipt.json`.
  Elbow is servo ID `3`; all six servos reported model `777`, firmware `3.9`,
  zero current transport/status faults, elbow `12.1–12.2 V`, and `28 C`.
- Faster torque-on elbow qualification:
  `docs/briefs/058-d1-d2-elbow-tracking-qualification.md`.
  The elbow reached `88.396 deg` against an `85 deg` target at about
  `8.34 deg/s`; torque-off gravity sag, not a dead servo, remains the known
  mechanism.
- Immutable terminal task attempts:
  `docs/briefs/059-d1-d2-exact-real-to-sim-v4.md` and
  `docs/run-logs/2026-07-27-c2-c1-exact-real-to-sim-terminal-negative.md`.
  Never rerun or mutate their bytes.
- RGB cameras are sufficient. C922 owns board/task outcome; Pi IMX708 owns
  external arm context; D405 is supporting RGB. `metric_depth:false`.
- Current operator authority, added after queue creation: the user reports
  that all pawns have been reset to their original state and authorizes the
  agent to run the preregistered physical tests after Q00-Q07 pass. This is
  not camera verification of the current scene; Q06 must capture and admit a
  fresh C922 observation before any motion. The agent must not ask the user to
  manipulate the scene between attempts.
- Advisory hypothesis to reproduce, not blindly trust: the physics board is
  side-flipped. Perfect-tracking FK reportedly approaches simulated C2 only
  to about `265.3 mm`, but approaches near-side C8 to about `64.5 mm`, almost
  exactly the six-rank distance `6 * 44.45 mm = 266.7 mm`.

## Definition of done

The queue is complete only when all of the following are true:

1. A versioned scene registration, created without new robot motion, fixes the
   categorical board side/orientation error and passes both fit and held-out
   `<=25 mm` task-relevant correspondence gates.
2. A native float64/40 Hz adjacent-square pawn-push evaluator and at-most-ten
   case family are frozen before any counted action bytes.
3. At least one counted REAL→SIM case passes both the C922 physical outcome
   and identical-canonical-byte MuJoCo outcome.
4. At least one separate counted SIM→REAL case passes simulation before
   action freeze and C922 physical outcome after unchanged execution.
5. Every counted attempt, including failures, appears in the denominator and
   has immutable action, mapping, camera, execution, outcome, and closeout
   receipts.
6. A synchronized Studio/browser artifact and a concise application claim
   expose the exact proof class, denominator, limitations, and separate
   directions.
7. Follower torque is off; repo-owned camera/gateway processes are closed;
   scoped changes are committed and pushed; unrelated user files are
   preserved.

If bidirectional success is not achieved, do not mark the queue complete.

F1 is now active. For termination auditing, Definition-of-Done item 1 is
replaced by preservation of the failed v4 candidate and its single-open
held-out receipt; items 3 and 4 use the off-source consequence gate above.
This is exactly the preregistered fallback and does not convert the failed
`<=25 mm` registration gate into a pass.

## Inviolate rules

- Canonical action bytes remain immutable within each counted case.
- Hardware and simulator mappings may differ but must be frozen, separately
  hash-bound, and consume the identical canonical action tensor.
- Setup/recovery prefixes are excluded with separate hashes.
- One physical attempt per counted case. A different prospectively frozen
  action is a new counted case.
- Fit scene registration before evaluator/case preregistration; freeze the
  evaluator/case family before compiling counted actions.
- C922 owns physical source/destination adjudication. Pi and D405 RGB remain
  separate supporting evidence lanes.
- Preserve prior receipts, action bytes, scene IDs, and the Phase A release.
- No runtime clipping, retiming, offsets, IK repair, assistance, threshold
  changes, retries, or corrective suffixes in counted actions.
- Require CPU/fp64 contact/limit preview, independent review, cameras before
  motion, stop-on-contact/stall/tracking failure, and guaranteed torque-off.
- Do not touch EEPROM, servo IDs, or servo RAM gains during this queue.
- Do not use Brev, paid compute, ACT, GR00T, VLA training, D405 depth work,
  printed-target P8/P13 calibration, or broad new framework families.
- Keep the historical C2 attempt immutable and do not reuse its old bytes.
- Do not autonomously reset or rearrange pawns between counted attempts.
- Do not ask the user for physical intervention.
- Preserve the existing unrelated untracked C922 calibration and
  `output/` files. Stage intended paths only.

## Allowed task-local scene scope

Whole-board exact initial-state matching is replaced prospectively by a
task-local evaluator scope:

- selected pawn must be upright and inside its admitted source square;
- destination square must be empty;
- the complete swept robot/pawn corridor must remain at least two squares
  from every excluded object identified in the fresh Q06 C922 scene;
- excluded objects must have zero simulated contact and remain stationary in
  C922 within a frozen pixel tolerance;
- every exclusion and minimum clearance must be frozen and disclosed before
  action compilation;
- if a counted action touches or moves an excluded object, the case fails.

This is a new preregistered scope. It does not retroactively promote old
attempts or silently override reviewer message `038`.

## Execution rhythm

1. Read the queue, authority files, latest receipts, and Git state.
2. Set exactly one queue card to `IN_PROGRESS`.
3. Execute the smallest evidence-producing slice.
4. Write tests first where practical and run focused validation.
5. Update that card with exact evidence paths, hashes, metrics, and decision.
6. Write one executor log and one independent reviewer decision for material
   slices.
7. Commit scoped tracked changes.
8. Set the next card to `IN_PROGRESS` and continue without waiting for the
   user while a safe agent-led path remains.

Do not end the task after an intermediate negative. Convert it into the next
evidence-driven queue action unless a stop rule below is met.

## Goal loop contract

Run a continuous verification-driven goal loop over Q00-Q15. Producing code,
a document, media, or another artifact never ends the task by itself.

Each iteration must:

1. Reread the latest user instruction, `AGENTS.md`, this queue, relevant
   repository authority files, immutable receipts, and Git state.
2. Keep exactly one smallest unblocked queue card `IN_PROGRESS`.
3. Execute that card without broadening its authorized scope.
4. Run every acceptance check declared by the card.
5. Record exact commands, results, hashes, media, and receipt paths in this
   queue.
6. Obtain or author the required independent reviewer decision for material
   evidence.
7. Mark a card `DONE` only when every acceptance check is evidenced. Otherwise
   record the exact failure and pivot or retry only through a preregistered
   fallback.
8. Immediately advance the next smallest unblocked card.

`Implemented`, `ran`, `looks correct`, planning complete, infrastructure
ready, a checkpoint, simulated reward, or camera media alone are not
completion. Completion requires evaluator-owned evidence matching this
queue's proof class.

Maintain a compact live ledger containing: Current state; Completed;
Verification evidence; Remaining; Blockers; Next action; and attempt
numerator/denominator per direction.

Before finalizing, run and record a queue self-audit proving:

- no unjustified `PENDING` or `IN_PROGRESS` cards remain;
- every Q00-Q15 acceptance row has evidence or an explicitly authorized
  terminal-stop disposition;
- every Definition-of-Done condition is independently verified;
- Q15 was performed only after Q00-Q14 and the Definition of Done were
  locally verified, or after a genuine receipt-backed terminal boundary;
- the existing Claude Desktop Fable 5 thread was used unless its
  unavailability was evidenced;
- Fable's response, date, model/thread identity, evidence reconciliation, and
  final next-step decision are captured in a scoped repository artifact;
- every concrete required-criterion defect raised by Fable was independently
  verified and either closed through a reopened queue card or left Q15
  incomplete;
- follower torque and repo-owned camera/gateway process cleanup are verified;
- required tests pass;
- artifacts exist and every declared hash resolves;
- scoped commits are pushed; and
- claims match the exact attempt denominator and proof class.

Continue autonomously until Q00-Q15 and every Definition-of-Done condition are
verified complete. The only alternative termination is a queue-authorized,
receipt-backed genuine F3/mechanical/safety/human-authority boundary after all
safe in-scope alternatives are exhausted. A blocker never silently converts
remaining cards to complete.

## Task queue

| ID | Status | Task | Acceptance gate | Evidence |
|---|---|---|---|---|
| Q00 | `DONE` | Reproduce the advisory board-side diagnosis read-only. Use the immutable C2 action, current compiled task scene, and perfect-tracking FK. | Report minimum approach to simulated C2, C8, and C7; confirm or reject the approximately six-rank categorical error; identify the exact code/config source. No file mutation beyond queue/evidence docs and no motion. | `docs/run-logs/2026-07-27-bidirectional-pawn-push-q00-board-side-diagnosis.md`; reviewer `039` (`CONTINUE`, anchor `100`). Site/base minima: C2 `265.275519 mm`, C8 `80.897091 mm`, C7 `100.783880 mm`. Pad-gap/28 mm-neck minima: C2 `257.506340 mm`, C8 `64.673854 mm`, C7 `85.525518 mm`. C2-C8 separation `266.700000 mm`; categorical rank-side error confirmed, residual still `>25 mm`. No motion. |
| Q01 | `DONE` | Freeze the zero-motion registration dataset split. Fit data may include C2 contact/topple-frame joints, C922 grid/corner tags, prior C2 dual-camera replay, and Pi link tags. Reserve at least one independent hover/episode as held-out before fitting. | Versioned manifest hashes every input and declares fit versus held-out membership. No held-out inspection after freeze until candidate family freezes. | Manifest `configs/evaluations/bidirectional_pawn_push_registration_dataset_v1.json`, SHA-256 `da203fae0e84ceb722631676858762e1ee3d5962be95c4555afb44f97bf51fdf`; seven fit inputs plus four opaque held-out inputs from independent B7 high-hover episode; all eleven hashes resolve; `2 passed in 0.04s`; executor `042`; reviewer `040` (`CONTINUE`, anchor `100`). No held-out semantic inspection and no motion. |
| Q02 | `DONE` | Implement scene-registration v4 as the smallest versioned correction: categorical side/orientation first, then bounded board XY/yaw refinement. Add joint-zero changes only if separately identifiable. | Old scene IDs and receipts remain unchanged. Candidate deterministically rebuilds and loads in CPU/fp64 MuJoCo. No action bytes change. | Candidate `configs/scenes/bidirectional_pawn_push_scene_registration_v4.json`, SHA-256 `c7c2b19d7bdf64e85c20f515b4d7fa859b2fd33948fa1a36438265571a752b7b`; `reflect_ranks`; table-frame center shift `[+36.817,+66.079] mm`; yaw and joint zeros unchanged; C2 modeled-head-center fit residual `24.631505 mm` at row `242`; canonical hashes unchanged; CPU/fp64 scene load passes; `15 passed in 0.37s`; executor `043`; reviewer `041` (`CONTINUE`, anchor `100`). Held-out still sealed; no motion. |
| Q03 | `F1_TRIGGERED` | Evaluate v4 on fit evidence and open the held-out once. | C2 grasp-phase FK approach to corrected C2 center `<=25 mm`; held-out task-relevant correspondence `<=25 mm`; no worsened known-safe geometry/contact. If either fails, follow F1 once rather than launching an unbounded fit family. | Terminal negative receipt `runs/bidirectional-pawn-push/20260727-registration-v4-heldout/evaluation.json`, SHA-256 `7bfd06be5dd397a8c25dc7a4e3cdadd08fa006271fec38d4abcac27d04c125bf`; fit `24.631505 mm` pass; single-open B7 held-out `164.353128 mm` fail with vector `[+20.370202,+162.834641,-9.049048] mm`; no new external contact; v4 rejected; F1 active; `5 passed in 0.32s`; executor `044`; reviewer `042` (`REDIRECT`, anchor `100`). No motion. |
| Q04 | `DONE` | Re-run immutable C2 bytes under v4 as retrospective diagnostics only. | Produce side-by-side old/v4 first-divergence and contact metrics. Label post-outcome scene correction and no promotion. A useful target is reproduction of physical strike/topple-near-source behavior, but failure remains evidence. | Receipt `runs/bidirectional-pawn-push/20260727-c2-v4-retrospective/evaluation.json`, SHA-256 `36110ee04a6625a3607c657855c92d99e6feac35f38a5541610542dc719e1664`; old/v4 clearance `312.326353/75.624879 mm`; v4 selected/wrong contact `0/0`; rise `0`; off-source false; first divergence row `247`; identical raw action SHA; `5 passed in 1.46s`; executor `045`; reviewer `043` (`CONTINUE`, anchor `100`). Post-outcome diagnostic only; no promotion or motion. |
| Q05 | `IN_PROGRESS` | Preregister a native float64/40 Hz adjacent-square push evaluator and the complete case family of at most ten attempts. | Evaluator owns selected-pawn source/destination geometry, upright gate, task-local exclusions, non-interaction, canonical hashes, direction, denominator, and camera adjudication. Freeze before any counted action compilation. | Pending |
| Q06 | `PENDING` | Select the first REAL→SIM scene from a fresh motion-free C922 frame. Prefer an upright near-rank E/F/G-file pawn at least three files from C with an empty adjacent destination. | User-reported reset is independently camera-verified; selected pawn/destination admitted; all exclusions have at least two-square route clearance; Pi/C922/D405 RGB availability verified; no depth dependency. | Pending |
| Q07 | `PENDING` | Compile and independently review the first hardware-first push action. Closed jaws, `>=60 mm` stroke, elbow `>=60 deg`, large-joint motion approximately `5–10 deg/s`, no slow deep holds. | CPU/fp64 preview clean; exact mappings and action hash frozen; zero clipping/rate/offset/repair/assistance; setup hash separate; one physical attempt admitted. | Pending |
| Q08 | `PENDING` | Execute the counted REAL→SIM physical case once and adjudicate it before simulation. | All cameras enclose action; requested/mapped/sent identity passes; C922 evaluator reports physical success; excluded objects remain stationary; torque-off closeout passes. On failure, count it and advance to a distinct preregistered case if budget remains. | Pending |
| Q09 | `PENDING` | Apply Q08 identical canonical bytes in v4 MuJoCo from the admitted task-local initial state. | No clipping/retiming/repair/state forcing; selected pawn ends inside destination and passes upright/non-interaction gates. Count pass/fail and first divergence. At least one REAL→SIM case must pass. | Pending |
| Q10 | `PENDING` | Create a separate SIM→REAL push on a different admitted pawn/file and evaluate it in simulation before freeze. | Simulator task success and robustness gate pass before action freeze; action/mappings/scene/evaluator hashes sealed; prior physical outcomes do not tune this case. | Pending |
| Q11 | `PENDING` | Execute the Q10 frozen SIM→REAL action physically once. | C922 reports selected-pawn destination success; exclusions remain stationary; bytes unchanged; no clamp/rate/repair/retry; torque-off and camera cleanup pass. Count pass/fail. At least one SIM→REAL case must pass. | Pending |
| Q12 | `PENDING` | Continue distinct preregistered cases only as needed, up to the frozen maximum of ten. | Stop new cases immediately after one complete bidirectional result exists. Every failure remains in the denominator; no post-hoc family expansion. | Pending |
| Q13 | `PENDING` | Produce the bidirectional evidence package. | Synchronized browser-playable comparisons, posters, action/mapping/evaluator receipts, case-index denominator, first-divergence summaries, Studio catalog entry, and exact claim boundary verified. Raw private recordings remain unpublished. | Pending |
| Q14 | `PENDING` | Final verification and publication closeout. | Focused/full relevant tests pass; workflow audit passes; Git diff is scoped; branch commit is pushed; public release/portfolio surface is updated only if already authorized and privacy-reviewed; torque and processes are clean. | Pending |
| Q15 | `PENDING` | Fable 5 post-result review. After Q00-Q14 and the Definition of Done are locally verified, or after a genuine receipt-backed terminal boundary, return via Computer Use to the existing Claude Desktop conversation titled `Sim-to-real transfer evaluation`; do not start a replacement unless the existing conversation is genuinely unavailable. Submit a concise evidence-complete report covering the original goal, exact actions, per-direction numerator/denominator, proof class, action/mapping/scene/evaluator hashes and versions, fit and held-out registration metrics, simulator and physical outcomes, camera paths, failures and stop conditions, tests, commits/branch, and limitations. Ask Fable to audit claim support, strongest result, weakest proof link, overlooked concrete defects or missing verification, and highest-leverage application/demo and sim2real next steps. | Existing Fable thread actually receives the report; response plus date/model/thread identity is captured in a scoped advisory/reviewer artifact; verified repository evidence is distinguished from inference; secrets and unsupported claims are excluded; feedback is reconciled against receipts and frozen evaluators; recommendations and final decision are written under `Advisory feedback / next steps`. Fable remains advisory. If it identifies a concrete reproducible defect in required Q00-Q14 acceptance, Q15 stays incomplete, the affected card is reopened, the defect is independently verified, and the loop resumes. Strategic or optional suggestions become follow-on work without retroactively changing the evaluator. |

## Fallback queue

| ID | Trigger | Action | Acceptance/claim boundary |
|---|---|---|---|
| F1 | Q03 fit or held-out residual exceeds `25 mm` after the single bounded v4 refinement family. | Preserve the failed v4 candidate. Widen the preregistered push stroke and, before action compilation, reduce the physical/sim consequence gate from “inside destination square” to “selected pawn base center displaced completely off the source square.” | The reduced primitive must still pass in both directions under identical-byte and camera-owned rules. Do not describe it as adjacent-square placement. |
| F2 | A REAL→SIM push succeeds but SIM→REAL does not before the deadline/case budget. | Package the successful one-direction push, corrected-scene retrospective C2 diagnostic, and complete failed second-direction evidence. | Claim one direction proven and the second preregistered/attempted; do not claim bidirectional transfer. Queue remains incomplete. |
| F3 | Healthy-corridor contact motion stalls or breaches the frozen tracking gate in two distinct mechanism-relevant counted cases. | Stop further physical contact attempts, close torque/processes, and publish the exact repeated mechanism evidence. | This is the only route to declaring physical mechanical inspection a true blocker. Do not ask the user to intervene inside this task. |

## Stop rules

- Stop immediately on torque uncertainty, unreviewed external contact,
  identity mismatch, missing C922 outcome authority, changed counted bytes,
  unsafe geometry, or failed closeout.
- A stopped physical case is counted if counted motion began.
- A blocker below workflow evidence anchor `75` cannot stop the overall queue.
- A blocked task may end only after F3 or another genuinely human-only safety
  boundary has been reproduced and all safe task-local alternatives are
  exhausted.
- Budget or deadline pressure never converts a negative into success.

## Live progress ledger

Current state:

- Q00-Q02 are verified complete; Q03 is a terminal F1-triggering negative;
  Q04 is verified complete and Q05 is active.
- Commit `0b3afab` adopted this queue and its goal-loop contract.
- Existing prior receipts remain unchanged.
- No new robot motion is authorized until Q00-Q05 complete.

Completed:

- Phase A public partial artifact.
- Exact gateway, tricam capture, byte/hash/receipt, review, and torque-off
  infrastructure.
- Read-only servo health and faster elbow qualification.
- Immutable D1 and C2 terminal task attempts.
- Q00 deterministic action-frozen board-side diagnosis. The categorical
  rank-side defect is confirmed, but the advisory mixed site/base and
  pad-gap/neck metrics; the remaining corrected-side residual exceeds
  `25 mm`.
- Q01 zero-motion split freeze. Seven fit inputs bind the immutable C2
  contact/topple case and current scene/mapping priors. Four held-out inputs
  bind an independent completed B7 high-hover episode and remain semantically
  unopened through Q01.
- Q02 fit-only scene-registration v4. The bounded winner is rank reflection
  plus `[+36.817,+66.079] mm` table-frame board-center shift; yaw and joint
  zeros remain unchanged. Fit residual is `24.631505 mm`.
- Q03 single-open held-out validation. B7 residual is `164.353128 mm`, so v4
  is rejected for metric registration and F1 is active. The prospective claim
  is reduced to complete off-source displacement in both directions.
- Q04 immutable C2 v4 retrospective. Clearance improves to `75.624879 mm`
  from `312.326353 mm`, but contact, rise, and off-source displacement remain
  zero; no promotion.

Verification evidence:

- Q00 run log:
  `docs/run-logs/2026-07-27-bidirectional-pawn-push-q00-board-side-diagnosis.md`.
- Q00 executor log:
  `docs/session-logs/041-executor-q00-board-side-diagnosis.md`.
- Q00 reviewer:
  `docs/reviewer-messages/039-q00-board-side-diagnosis.md`,
  decision `CONTINUE`, evidence anchor `100`.
- Immutable action raw SHA-256:
  `0add8f1357c65bee011755e6e4a124d0e339cbc0dce9fd3a92b78399380a37da`.
- Candidate manifest SHA-256:
  `f4110c4be9712aa14df9682ce0e28f4d7f0d6d00bc8bc2561290cc49de18f170`.
- Independent direct-transform formula check: `PASS` at `1e-9 mm`.
- Q01 manifest:
  `configs/evaluations/bidirectional_pawn_push_registration_dataset_v1.json`,
  SHA-256
  `da203fae0e84ceb722631676858762e1ee3d5962be95c4555afb44f97bf51fdf`.
- Q01 validation:
  `uv run --offline pytest -q tests/test_bidirectional_pawn_push_registration_dataset.py`
  -> `2 passed in 0.04s`; all eleven input hashes resolved.
- Q01 executor/reviewer: `docs/session-logs/042-executor-q01-registration-split-freeze.md`;
  `docs/reviewer-messages/040-q01-registration-split-freeze.md`,
  decision `CONTINUE`, anchor `100`.
- Q02 candidate:
  `configs/scenes/bidirectional_pawn_push_scene_registration_v4.json`,
  SHA-256
  `c7c2b19d7bdf64e85c20f515b4d7fa859b2fd33948fa1a36438265571a752b7b`.
- Q02 validation:
  `uv run --offline pytest -q tests/test_bidirectional_scene_registration_v4.py tests/test_scene.py tests/test_bidirectional_pawn_push_registration_dataset.py`
  -> `15 passed in 0.37s`.
- Q02 executor/reviewer: `docs/session-logs/043-executor-q02-scene-registration-v4.md`;
  `docs/reviewer-messages/041-q02-scene-registration-v4.md`,
  decision `CONTINUE`, anchor `100`.
- Q03 receipt:
  `runs/bidirectional-pawn-push/20260727-registration-v4-heldout/evaluation.json`,
  SHA-256
  `7bfd06be5dd397a8c25dc7a4e3cdadd08fa006271fec38d4abcac27d04c125bf`.
- Q03 executor/reviewer: `docs/session-logs/044-executor-q03-registration-heldout.md`;
  `docs/reviewer-messages/042-q03-registration-heldout.md`,
  decision `REDIRECT`, anchor `100`.
- Q04 receipt:
  `runs/bidirectional-pawn-push/20260727-c2-v4-retrospective/evaluation.json`,
  SHA-256
  `36110ee04a6625a3607c657855c92d99e6feac35f38a5541610542dc719e1664`.
- Q04 executor/reviewer: `docs/session-logs/045-executor-q04-c2-v4-retrospective.md`;
  `docs/reviewer-messages/043-q04-c2-v4-retrospective.md`,
  decision `CONTINUE`, anchor `100`.

Remaining:

- Q05-Q15. Q03 remains visibly `F1_TRIGGERED`, not passed.

Blockers:

- The v4 metric-registration candidate is rejected. Q05 must freeze the F1
  evaluator and case budget before any new action is compiled.

Next step:

- Preregister the native float64/40 Hz off-source evaluator and all at-most-ten
  cases, including case identities, directions, exclusions, denominators,
  camera authority, hashes required at action freeze, and stop rules.

Attempt ledger:

- REAL→SIM counted pushes: `0/0`.
- SIM→REAL counted pushes: `0/0`.
- Total counted physical attempts: `0/10`.

Advisory feedback / next steps:

- Pending Q15. Do not contact Fable before Q00-Q14 and the Definition of Done
  are locally verified, or before a genuine receipt-backed terminal boundary
  has been fully packaged and locally audited.

## Q01 transition record

Exact commands and results:

```text
uv run --offline pytest -q tests/test_bidirectional_pawn_push_registration_dataset.py
..                                                                       [100%]
2 passed in 0.04s

python -m json.tool configs/evaluations/bidirectional_pawn_push_registration_dataset_v1.json
PASS

shasum -a 256 configs/evaluations/bidirectional_pawn_push_registration_dataset_v1.json
da203fae0e84ceb722631676858762e1ee3d5962be95c4555afb44f97bf51fdf
```

The Q01 hash verifier read every declared file only as opaque bytes. It did
not parse, view, or interpret any held-out JSON, image, video, or episode
result. Q02 is the only active card. Physical attempts remain `0/10`.

## Q02 transition record

Exact command and result:

```text
uv run --offline pytest -q tests/test_bidirectional_scene_registration_v4.py tests/test_scene.py tests/test_bidirectional_pawn_push_registration_dataset.py
...............                                                          [100%]
15 passed in 0.37s

shasum -a 256 configs/scenes/bidirectional_pawn_push_scene_registration_v4.json
c7c2b19d7bdf64e85c20f515b4d7fa859b2fd33948fa1a36438265571a752b7b
```

The candidate was reproduced from fit members only. The held-out semantic
content remained sealed through candidate serialization and hash freeze.
Q03 is the only active card; physical attempts remain `0/10`.

## Q03 transition record

Exact commands and results:

```text
uv run --offline pytest -q tests/test_bidirectional_registration_v4_evaluator.py tests/test_bidirectional_scene_registration_v4.py
.....                                                                    [100%]
5 passed in 0.32s

uv run --offline python scripts/evaluate_bidirectional_registration_v4.py --output runs/bidirectional-pawn-push/20260727-registration-v4-heldout/evaluation.json
PASS

shasum -a 256 runs/bidirectional-pawn-push/20260727-registration-v4-heldout/evaluation.json
7bfd06be5dd397a8c25dc7a4e3cdadd08fa006271fec38d4abcac27d04c125bf
```

The single-open B7 result failed at `164.353128 mm`. V4 was not tuned after
opening. F1 claim wording was activated before any action compilation. Q04 is
the only active card; physical attempts remain `0/10`.

## Q04 transition record

Exact commands and results:

```text
uv run --offline pytest -q tests/test_bidirectional_c2_v4_replay.py tests/test_bidirectional_scene_registration_v4.py
.....                                                                    [100%]
5 passed in 1.46s

uv run --offline python scripts/evaluate_bidirectional_c2_v4_replay.py --output runs/bidirectional-pawn-push/20260727-c2-v4-retrospective/evaluation.json
PASS

shasum -a 256 runs/bidirectional-pawn-push/20260727-c2-v4-retrospective/evaluation.json
36110ee04a6625a3607c657855c92d99e6feac35f38a5541610542dc719e1664
```

V4 remains a post-outcome negative: zero contact and zero off-source
displacement. Q05 is the only active card; physical attempts remain `0/10`.
