# Bidirectional Pawn-Push Transfer Task Queue

Status: `TERMINAL_NO_TRANSFER_OWNER_AUTHORITY_BOUNDARY`

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

### Historical F1 claim reduction invalidated by Q15

Q03 originally appeared to trigger the preregistered F1 fallback. Q15 found
that the held-out evaluator had treated an old-simulator route name as a
camera-owned physical square. The sealed cameras cannot adjudicate an exact
replacement square, so the original `164.353128 mm` score is preserved but
invalid as a held-out decision. V4 is neither metric-admitted nor
metric-rejected by that held-out. The F1 trigger is unsupported.

Q05's off-source evaluator remains immutable as a historical preregistered
contract, but no action was compiled and it grants no task authority. Its
maximum intended claim was:

> Under a preregistered evaluator, at least one prospectively frozen
> hardware-first action and one separate simulator-first action each
> displaced the selected pawn base center completely off its admitted source
> square in both the physical SO-101 workcell and MuJoCo while preserving
> identical canonical action bytes within each case. Every counted failure
> remains in the denominator.

This would have been a bidirectional off-source displacement primitive, not
adjacent-square placement and not the original registration-qualified target.
No such result exists.

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

For termination auditing, Definition-of-Done item 1 is not met: v4 fit passes
at `24.631505 mm`, but the single-open held-out is unscorable because an exact
camera-owned physical square is unavailable. The original receipt and the
post-Q15 correction are both preserved. Items 3 and 4 are also not met; no
case was admitted and no action was compiled.

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
| Q03 | `DONE_CORRECTED_UNSCORABLE` | Evaluate v4 on fit evidence and open the held-out once. | C2 grasp-phase FK approach to corrected C2 center `<=25 mm`; held-out task-relevant correspondence `<=25 mm`; no worsened known-safe geometry/contact. If either fails, follow F1 once rather than launching an unbounded fit family. | Correction receipt `runs/bidirectional-pawn-push/20260727-registration-v4-heldout-label-audit-v2/evaluation.json`, SHA-256 `efaf436bdba9e52df781973abaabf0a2b346261daddbb8e9fe259a1cd61efd02`; contract SHA-256 `33877ed6e295a79347b1cf430306a2e442ed2b7bc5d755c6df45114522af9091`. The original receipt/hash is preserved, but its B7 label is not camera-owned. C922 self-occludes the high-hover association, Pi places the gripper outside frame, D405 points away, and camera extrinsics are unavailable. Corrected square/residual: unavailable; held-out open count remains `1`; v4 neither metric-admitted nor metric-rejected; F1 trigger unsupported. `7 passed in 0.46s`; executor `050`. No new data or motion. |
| Q04 | `DONE` | Re-run immutable C2 bytes under v4 as retrospective diagnostics only. | Produce side-by-side old/v4 first-divergence and contact metrics. Label post-outcome scene correction and no promotion. A useful target is reproduction of physical strike/topple-near-source behavior, but failure remains evidence. | Receipt `runs/bidirectional-pawn-push/20260727-c2-v4-retrospective/evaluation.json`, SHA-256 `36110ee04a6625a3607c657855c92d99e6feac35f38a5541610542dc719e1664`; old/v4 clearance `312.326353/75.624879 mm`; v4 selected/wrong contact `0/0`; rise `0`; off-source false; first divergence row `247`; identical raw action SHA; `5 passed in 1.46s`; executor `045`; reviewer `043` (`CONTINUE`, anchor `100`). Post-outcome diagnostic only; no promotion or motion. |
| Q05 | `DONE_WITH_POSTFREEZE_FEASIBILITY_DEFECT` | Preregister a native float64/40 Hz adjacent-square push evaluator and the complete case family of at most ten attempts. | Evaluator owns selected-pawn source/destination geometry, upright gate, task-local exclusions, non-interaction, canonical hashes, direction, denominator, and camera adjudication. Freeze before any counted action compilation. | Immutable evaluator remains SHA-256 `8450682fac61ac064198b90858f58e6753b0d701ed55f067f91d88ed04604479`. Postfreeze receipt `runs/bidirectional-pawn-push/20260727-q05-feasibility-audit-v1/evaluation.json`, SHA-256 `0dbe2cbdb078b219c172e20ffd08c7be96e01f68abbca84355c4d04afa3bd591`: frozen `88.9 mm` clearance is structurally infeasible because every route contains a source whose nearest reset-layout exclusion is `sqrt(2) * 44.45 = 62.861793 mm`. This omission was detectable before Q06. `6 passed in 0.20s`; executor `051`. No action compiled or motion. |
| Q06 | `DONE_CONTRACT_INFEASIBILITY` | Select the first REAL→SIM scene from a fresh motion-free C922 frame. Prefer an upright near-rank E/F/G-file pawn at least three files from C with an empty adjacent destination. | User-reported reset is independently camera-verified; selected pawn/destination admitted; all exclusions have at least two-square route clearance; Pi/C922/D405 RGB availability verified; no depth dependency. | Fresh RGB receipt unchanged at SHA-256 `ee6d71d98723e5133097c24c30ab8d2b16881e6554d22078aae632fe99966730`; corrected gate receipt SHA-256 `9863ccdeadb2d5d01dd959d14bd226f997eec1b2755156f6c441a9d98e7010f1`. All ten routes remain rejected at `44.45 mm`; global reset-layout upper bound `62.861793 mm < 88.9 mm`. Proof class `terminal_preregistered_contract_infeasibility_without_physical_attempt`; zero actions/motion/attempts; not a safety event or F3. `7 passed in 0.23s`; executor `052`. |
| Q07 | `NOT_AUTHORIZED_Q06_BOUNDARY` | Compile and independently review the first hardware-first push action. Closed jaws, `>=60 mm` stroke, elbow `>=60 deg`, large-joint motion approximately `5–10 deg/s`, no slow deep holds. | CPU/fp64 preview clean; exact mappings and action hash frozen; zero clipping/rate/offset/repair/assistance; setup hash separate; one physical attempt admitted. | Q06 admitted no case; compiling an action would violate the frozen exclusion gate. |
| Q08 | `NOT_AUTHORIZED_Q06_BOUNDARY` | Execute the counted REAL→SIM physical case once and adjudicate it before simulation. | All cameras enclose action; requested/mapped/sent identity passes; C922 evaluator reports physical success; excluded objects remain stationary; torque-off closeout passes. On failure, count it and advance to a distinct preregistered case if budget remains. | No Q07 action exists and no counted motion began. REAL→SIM denominator remains `0/0`. |
| Q09 | `NOT_AUTHORIZED_Q06_BOUNDARY` | Apply Q08 identical canonical bytes in v4 MuJoCo from the admitted task-local initial state. | No clipping/retiming/repair/state forcing; selected pawn ends inside destination and passes upright/non-interaction gates. Count pass/fail and first divergence. At least one REAL→SIM case must pass. | No Q08 canonical bytes exist. No REAL→SIM transfer claim. |
| Q10 | `NOT_AUTHORIZED_Q06_BOUNDARY` | Create a separate SIM→REAL push on a different admitted pawn/file and evaluate it in simulation before freeze. | Simulator task success and robustness gate pass before action freeze; action/mappings/scene/evaluator hashes sealed; prior physical outcomes do not tune this case. | Q06 found no admitted case in either direction; no SIM→REAL action may be compiled. |
| Q11 | `NOT_AUTHORIZED_Q06_BOUNDARY` | Execute the Q10 frozen SIM→REAL action physically once. | C922 reports selected-pawn destination success; exclusions remain stationary; bytes unchanged; no clamp/rate/repair/retry; torque-off and camera cleanup pass. Count pass/fail. At least one SIM→REAL case must pass. | No Q10 action exists and no counted motion began. SIM→REAL denominator remains `0/0`. |
| Q12 | `NOT_AUTHORIZED_Q06_BOUNDARY` | Continue distinct preregistered cases only as needed, up to the frozen maximum of ten. | Stop new cases immediately after one complete bidirectional result exists. Every failure remains in the denominator; no post-hoc family expansion. | Every one of the ten preregistered cases was rejected before compilation by the same frozen Q06 clearance gate; expansion and post-observation weakening are forbidden. |
| Q13 | `DONE_CORRECTED_TERMINAL_PACKAGE` | Produce the bidirectional evidence package. | Synchronized browser-playable comparisons, posters, action/mapping/evaluator receipts, case-index denominator, first-divergence summaries, Studio catalog entry, and exact claim boundary verified. Raw private recordings remain unpublished. | Corrected receipt SHA-256 `5ad9376a4be007bef22bbf93f08e5d54576e87db40b4fa08a78b716c91727e44`; viewer SHA-256 `6f13722a9be419e44d40de5526bdf1a042ae6bee0838bffc88fff05919911fbe`; contract SHA-256 `86c64da69ffce7ee9729d9f757daef9d500e9e45b57a2d3496e570f1c5c8dbc8`. Viewer/Studio expose unscorable held-out, contract infeasibility, `0/0` per direction, empty action hashes, and no task/transfer/safety-event authority. `24 passed, 2 subtests passed in 7.87s`; executor `053`; raw recordings unpublished. |
| Q14 | `DONE_CORRECTED_AND_PUSHED` | Final verification and publication closeout. | Focused/full relevant tests pass; workflow audit passes; Git diff is scoped; branch commit is pushed; public release/portfolio surface is updated only if already authorized and privacy-reviewed; torque and processes are clean. | `45 passed, 2 subtests passed in 8.40s`; workflow audit clean; fresh preflight passed with no rewrite/alignment motion and follower torque false; existing torque receipt SHA-256 `ca50d9dae4aa9a7dd672edee625dfe51ff2e4ad65cb76e7a28e39f3f06457d09` reproduced; zero repo-owned camera/gateway processes; `brev ls` reports no instances; unrelated files preserved; public release skipped as unauthorized. Corrected closeout through commit `68a7de3` pushed to `origin/codex/geometric-microtransfer-20260727`. Executor `054`. |
| Q15 | `DONE_ACCEPTED` | Fable 5 post-result review. After Q00-Q14 and the Definition of Done are locally verified, or after a genuine receipt-backed terminal boundary, return via Computer Use to the existing Claude Desktop conversation titled `Sim-to-real transfer evaluation`; do not start a replacement unless the existing conversation is genuinely unavailable. Submit a concise evidence-complete report covering the original goal, exact actions, per-direction numerator/denominator, proof class, action/mapping/scene/evaluator hashes and versions, fit and held-out registration metrics, simulator and physical outcomes, camera paths, failures and stop conditions, tests, commits/branch, and limitations. Ask Fable to audit claim support, strongest result, weakest proof link, overlooked concrete defects or missing verification, and highest-leverage application/demo and sim2real next steps. | Same existing thread/model/date used. Fable independently verified hashes, re-extracted the C922 apex, inspected Pi, accepted Q03 as honestly unadjudicable, accepted the Q05/Q06/Q13 infeasibility correction and denominators, found no remaining required defect, and returned `ACCEPT`. Artifact `docs/reviewer-messages/048-q15-fable-final-reconciliation.md`. |

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

- Q00-Q15 are dispositioned. Q07-Q12 remain explicitly unauthorized because
  no case/action was admitted. Fable returned `ACCEPT` after independently
  verifying the correction chain. No queue card is active.
- Commit `0b3afab` adopted this queue and its goal-loop contract.
- Existing prior receipts remain unchanged.
- Robot motion remains unauthorized. Q06 admitted no case and Q07 cannot
  begin.

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
- Q03 single-open held-out correction. The original B7-provenance residual
  remains `164.353128 mm`, but B7 was not camera-adjudicated. The sealed
  cameras cannot supply an exact replacement square, so corrected residual is
  unavailable, v4 is neither metric-admitted nor metric-rejected by the
  held-out, and F1 is unsupported.
- Q04 immutable C2 v4 retrospective. Clearance improves to `75.624879 mm`
  from `312.326353 mm`, but contact, rise, and off-source displacement remain
  zero; no promotion.
- Q05 evaluator/case freeze. Native float64/40 Hz F1 evaluation, all ten
  one-use slots, direction order, identity boundaries, exclusions, safety,
  and denominators were frozen before action compilation. Postfreeze audit
  proves the `88.9 mm` clearance was structurally infeasible against the
  reset-layout upper bound `62.861793 mm`; the reviewer should have caught
  this before Q06.
- Q06 fresh RGB scene gate. C922, D405 color, and Pi IMX708 were captured
  without motion or depth. All ten frozen routes are `44.45 mm` from an
  excluded reset-layout pawn versus the required `88.9 mm`, so no case was
  admitted and no action was compiled.
- Q13 terminal package. A hash-bound local viewer, receipt, and read-only
  Studio entry preserve the fresh camera evidence, all ten rejection rows,
  `0/0` per-direction denominators, and the absence of action/task evidence.

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
- Q03 post-Q15 correction:
  `runs/bidirectional-pawn-push/20260727-registration-v4-heldout-label-audit-v2/evaluation.json`,
  SHA-256
  `efaf436bdba9e52df781973abaabf0a2b346261daddbb8e9fe259a1cd61efd02`;
  `docs/session-logs/050-executor-q03-heldout-label-authority-correction.md`;
  `7 passed in 0.46s`.
- Q04 receipt:
  `runs/bidirectional-pawn-push/20260727-c2-v4-retrospective/evaluation.json`,
  SHA-256
  `36110ee04a6625a3607c657855c92d99e6feac35f38a5541610542dc719e1664`.
- Q04 executor/reviewer: `docs/session-logs/045-executor-q04-c2-v4-retrospective.md`;
  `docs/reviewer-messages/043-q04-c2-v4-retrospective.md`,
  decision `CONTINUE`, anchor `100`.
- Q05 evaluator:
  `configs/evaluations/bidirectional_off_source_push_evaluator_v1.json`,
  SHA-256
  `8450682fac61ac064198b90858f58e6753b0d701ed55f067f91d88ed04604479`.
- Q05 executor/reviewer: `docs/session-logs/046-executor-q05-off-source-evaluator-freeze.md`;
  `docs/reviewer-messages/044-q05-off-source-evaluator-freeze.md`,
  decision `CONTINUE`, anchor `100`.
- Q05 feasibility correction:
  `runs/bidirectional-pawn-push/20260727-q05-feasibility-audit-v1/evaluation.json`,
  SHA-256
  `0dbe2cbdb078b219c172e20ffd08c7be96e01f68abbca84355c4d04afa3bd591`;
  `docs/session-logs/051-executor-q05-preregistered-feasibility-audit.md`;
  `6 passed in 0.20s`.
- Q06 capture receipt:
  `runs/bidirectional-pawn-push/20260727-q06-scene-v1/capture_receipt.json`,
  SHA-256
  `ee6d71d98723e5133097c24c30ab8d2b16881e6554d22078aae632fe99966730`.
- Q06 gate receipt:
  `runs/bidirectional-pawn-push/20260727-q06-scene-v1/scene_gate_receipt.json`,
  SHA-256
  `9863ccdeadb2d5d01dd959d14bd226f997eec1b2755156f6c441a9d98e7010f1`.
- Q06 executor/reviewer:
  `docs/session-logs/047-executor-q06-fresh-rgb-scene-gate.md`;
  `docs/reviewer-messages/045-q06-fresh-rgb-scene-gate.md`,
  decision `ESCALATE`, anchor `100`.
- Q13 receipt:
  `runs/bidirectional-pawn-push/20260727-terminal-evidence-v1/terminal_evidence_package.json`,
  SHA-256
  `5ad9376a4be007bef22bbf93f08e5d54576e87db40b4fa08a78b716c91727e44`.
- Q13 viewer:
  `runs/bidirectional-pawn-push/20260727-terminal-evidence-v1/index.html`,
  SHA-256
  `6f13722a9be419e44d40de5526bdf1a042ae6bee0838bffc88fff05919911fbe`.
- Q13 executor/reviewer:
  `docs/session-logs/048-executor-q13-terminal-evidence-package.md`;
  `docs/reviewer-messages/046-q13-terminal-evidence-package.md`,
  decision `CONTINUE`, anchor `100`.

Remaining:

- No in-scope card remains. Q07-Q12 remain visibly not authorized, not
  passed. A successor campaign is outside this queue.

Blockers:

- V4 has a passing `24.631505 mm` fit result but no valid held-out decision;
  metric admission and rejection are both unsupported.
- The single-open registration held-out has no camera-owned physical-square
  label and cannot be rescored without new evidence, which is forbidden.
- The frozen evaluator is structurally incompatible with the reset layout:
  its best possible route-clearance upper bound is `62.861793 mm`, below
  `88.9 mm`; every preregistered route is actually `44.45 mm`.
- Replacing or weakening the already-observed evaluator requires prospective
  owner authorization outside this frozen campaign. It is not a physical
  safety or F3 mechanical boundary.

Next step:

- None within this queue. Any new held-out episode or feasible successor
  evaluator requires separate owner authorization.

Attempt ledger:

- REAL→SIM counted pushes: `0/0`.
- SIM→REAL counted pushes: `0/0`.
- Total counted physical attempts: `0/10`.

Advisory feedback / next steps:

- Pending Q15. Do not contact Fable before Q00-Q14 and the Definition of Done
  are locally verified, or before a genuine receipt-backed terminal boundary
  has been fully packaged and locally audited.
- Q15 report was delivered to the existing Claude Desktop conversation
  `Sim-to-real transfer evaluation` on 2026-07-27 with model
  `claude-fable-5`.
- Fable independently verified the cited hashes, denominators, Q00
  reproduction, and frozen Q06 infeasibility. It identified one required
  defect: the B7 hover's run-path/old-sim label was treated as a
  camera-adjudicated physical square in Q03.
- Q03 is corrected and closed as unscorable. Q05 is reopened for the
  independently reproducible preregistration-feasibility omission. Fable's
  suggestions for a successor center-ward evaluator are optional and require
  separate owner authorization; they do not modify the frozen v1 evaluator.
- Final reconciliation returned `ACCEPT`. Fable verified the corrected
  artifacts and found no remaining required-criterion defect. Reviewer
  artifact:
  `docs/reviewer-messages/048-q15-fable-final-reconciliation.md`.

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

### Q03 post-Q15 correction

Q15 exposed that `B7` in the original evaluator came from the old-simulator
route name rather than a camera-owned physical-square label. The original
receipt remains immutable, but it no longer supports metric rejection or F1.

```text
uv run --offline pytest -q \
  tests/test_bidirectional_registration_v4_label_audit.py \
  tests/test_bidirectional_registration_v4_evaluator.py \
  tests/test_bidirectional_scene_registration_v4.py
.......                                                                  [100%]
7 passed in 0.46s

uv run --offline python \
  scripts/evaluate_bidirectional_registration_v4_label_audit.py \
  --output \
  runs/bidirectional-pawn-push/20260727-registration-v4-heldout-label-audit-v2/evaluation.json
PASS

shasum -a 256 \
  configs/evaluations/bidirectional_pawn_push_registration_v4_label_audit_v2.json \
  runs/bidirectional-pawn-push/20260727-registration-v4-heldout-label-audit-v2/evaluation.json
33877ed6e295a79347b1cf430306a2e442ed2b7bc5d755c6df45114522af9091
efaf436bdba9e52df781973abaabf0a2b346261daddbb8e9fe259a1cd61efd02
```

The sealed C922, Pi, and D405 views were exhausted. They cannot assign the
high-hover apex to an exact square: C922 is self-occluded and lacks metric
extrinsics, Pi places the gripper outside frame, and D405 points away. The
corrected held-out square/residual/pass are therefore unavailable. Selecting
A3 from the `22.337386 mm` v4-FK counterfactual or A2 from the `19.719086 mm`
raw-center counterfactual would be circular and is expressly non-authoritative.
The held-out open count remains `1`; no new data or motion occurred. Q05 is
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

## Q05 transition record

Exact commands and results:

```text
uv run --offline pytest -q tests/test_bidirectional_off_source_evaluator.py
....                                                                     [100%]
4 passed in 0.05s

python -m json.tool configs/evaluations/bidirectional_off_source_push_evaluator_v1.json
PASS

shasum -a 256 configs/evaluations/bidirectional_off_source_push_evaluator_v1.json
8450682fac61ac064198b90858f58e6753b0d701ed55f067f91d88ed04604479
```

No counted action existed at evaluator freeze. Q06 is the only active card;
physical attempts remain `0/10`.

### Q05 post-Q15 feasibility correction

```text
uv run --offline pytest -q \
  tests/test_bidirectional_off_source_feasibility_audit.py \
  tests/test_bidirectional_off_source_evaluator.py
......                                                                   [100%]
6 passed in 0.20s

uv run --offline python \
  scripts/evaluate_bidirectional_off_source_feasibility.py \
  --output \
  runs/bidirectional-pawn-push/20260727-q05-feasibility-audit-v1/evaluation.json
PASS

shasum -a 256 \
  runs/bidirectional-pawn-push/20260727-q05-feasibility-audit-v1/evaluation.json
0dbe2cbdb078b219c172e20ffd08c7be96e01f68abbca84355c4d04afa3bd591
```

The frozen evaluator was not modified. Every route contains its source, and
every occupied source has another reset-layout pawn one file and one rank
away. The global clearance upper bound was therefore
`sqrt(2) * 44.45 = 62.861793 mm`, below the frozen `88.9 mm` gate. This
structural infeasibility was detectable before Q06 and should have prevented
the evaluator from being accepted as executable. B7/D7/F7 planar source-to-
left-base distances were also reproduced as
`0.478092/0.485519/0.508618 m`; distance alone is not promoted to a
reachability decision. No new data, action, gateway, motion, or attempt
occurred. Q06 is the only active card.

## Q06 transition record

Exact commands and results:

```text
uv run --offline pytest -q \
  tests/test_bidirectional_q06_scene_gate.py \
  tests/test_bidirectional_off_source_evaluator.py
.....                                                                    [100%]
5 passed in 0.10s

uv run --offline python scripts/evaluate_bidirectional_q06_scene_gate.py \
  --output \
  runs/bidirectional-pawn-push/20260727-q06-scene-v1/scene_gate_receipt.json
PASS

python -m json.tool \
  configs/evaluations/bidirectional_q06_rgb_scene_gate_v1.json
PASS

shasum -a 256 \
  runs/bidirectional-pawn-push/20260727-q06-scene-v1/scene_gate_receipt.json
3c81caaa626043d1a12c34bf9b05e11fa0e0823070b516f001e8857b5c59ec0c
```

Camera inputs:

```text
capture receipt:
ee6d71d98723e5133097c24c30ab8d2b16881e6554d22078aae632fe99966730
C922 native video:
e56831344ab2a17aba8b0483a49bdb922c4a7285297761a5f710fbc59032fba1
D405 color native video:
774c3960ec16b57d7bfe581656e47f5a62505657a36305b905d730b981c4b55d
C922 scene frame:
5803cce3e87aa5066589e8aada64b81fe37e2a821e70b47aeb32807860a22883
D405 color scene frame:
e95fc50183c63e34d5f25fb4bb4f18ea0d278af9364ae5197a12b9546633e049
Pi IMX708 scene frame:
3bfe6a4862fb980eb1afd53b4091779bd71c53bf1f3d03aa5c1d98cebd5c78ab
```

All ten cases were evaluated before any action compilation. Every route has
`44.45 mm` center-to-route clearance from its nearest excluded pawn, below
the frozen `88.9 mm` requirement. F1 stroke widening, changing selected
board side, and setup prefixes cannot cure initial scene clearance. Case
expansion, pawn manipulation, and post-observation gate weakening are
forbidden. The initial “human-only safety boundary” label was later invalidated
by Q15; see the correction below. Q07-Q12 are not authorized. Physical
attempts remain `0/10`; no direction has an attempted or successful case.

### Q06 post-Q15 proof-class correction

```text
uv run --offline pytest -q \
  tests/test_bidirectional_q06_scene_gate.py \
  tests/test_bidirectional_off_source_feasibility_audit.py \
  tests/test_bidirectional_off_source_evaluator.py
.......                                                                  [100%]
7 passed in 0.23s

uv run --offline python scripts/evaluate_bidirectional_q06_scene_gate.py \
  --output \
  runs/bidirectional-pawn-push/20260727-q06-scene-v1/scene_gate_receipt.json
PASS

shasum -a 256 \
  runs/bidirectional-pawn-push/20260727-q06-scene-v1/scene_gate_receipt.json
9863ccdeadb2d5d01dd959d14bd226f997eec1b2755156f6c441a9d98e7010f1
```

All camera inputs and all ten rejection metrics are unchanged. The corrected
proof class is
`terminal_preregistered_contract_infeasibility_without_physical_attempt`.
The evaluator could not admit the frozen reset layout even in principle; the
camera merely confirmed the expected layout. This was no physical safety
event, mechanical failure, F3 event, or counted attempt. Q13 is the only
active card.

## Q13 transition record

Exact commands and results:

```text
uv run --offline python scripts/build_bidirectional_terminal_evidence.py
PASS

shasum -a 256 \
  runs/bidirectional-pawn-push/20260727-terminal-evidence-v1/terminal_evidence_package.json \
  runs/bidirectional-pawn-push/20260727-terminal-evidence-v1/index.html
97e689864e0e4f3a04602c341415166b8971bee7fa77be95378807781bba8124
d8d31f83c880cf741dd8941a509db43770f6a3391323d42e1ea2fb0ac87d90b2

uv run --offline pytest -q \
  tests/test_bidirectional_terminal_evidence.py \
  tests/test_bidirectional_q06_scene_gate.py \
  tests/test_studio.py
...................                                                     [100%]
19 passed, 2 subtests passed in 8.79s
```

The local viewer presents fresh RGB scene evidence and deterministic clearance
rows; it does not pretend there was an action replay. Studio admits the
receipt as a blocked terminal episode with no action hash and no physical,
simulator, transfer, training, or promotion authority. Raw recordings were not
published. Q14 is the only active card.

### Q13 post-Q15 package correction

```text
uv run --offline python scripts/build_bidirectional_terminal_evidence.py
PASS

uv run --offline pytest -q \
  tests/test_bidirectional_terminal_evidence.py \
  tests/test_bidirectional_q06_scene_gate.py \
  tests/test_bidirectional_off_source_feasibility_audit.py \
  tests/test_bidirectional_registration_v4_label_audit.py \
  tests/test_studio.py
........................                                                 [100%]
24 passed, 2 subtests passed in 7.87s

shasum -a 256 \
  configs/evaluations/bidirectional_terminal_evidence_package_v1.json \
  runs/bidirectional-pawn-push/20260727-terminal-evidence-v1/terminal_evidence_package.json \
  runs/bidirectional-pawn-push/20260727-terminal-evidence-v1/index.html
86c64da69ffce7ee9729d9f757daef9d500e9e45b57a2d3496e570f1c5c8dbc8
5ad9376a4be007bef22bbf93f08e5d54576e87db40b4fa08a78b716c91727e44
6f13722a9be419e44d40de5526bdf1a042ae6bee0838bffc88fff05919911fbe
```

The rebuilt viewer and Studio entry say “frozen contract infeasibility,” not
“safety boundary,” and say the held-out is unscorable, not that v4 is
rejected. Exact denominators remain `0/0` in each direction and `0/10`
overall; action hashes remain empty. Q14 is the only active card.

## Q14 transition record

Exact commands and results:

```text
uv run --offline sim2claw physical-gateway-preflight
passed: true
device_configuration_rewritten: false
start_alignment_motion_commanded: false
physical_follower_torque_enabled: false

scripts/audit_autonomous_workflow.sh
workflow audit clean

uv run --offline pytest -q \
  tests/test_bidirectional_pawn_push_registration_dataset.py \
  tests/test_bidirectional_scene_registration_v4.py \
  tests/test_bidirectional_registration_v4_evaluator.py \
  tests/test_bidirectional_c2_v4_replay.py \
  tests/test_bidirectional_off_source_evaluator.py \
  tests/test_bidirectional_q06_scene_gate.py \
  tests/test_bidirectional_terminal_evidence.py \
  tests/test_scene.py \
  tests/test_studio.py
.........................................                              [100%]
41 passed, 2 subtests passed in 8.10s

git push origin codex/geometric-microtransfer-20260727
d7c8e15..f3e7394
```

Postflight torque-off receipt SHA-256:
`ca50d9dae4aa9a7dd672edee625dfe51ff2e4ad65cb76e7a28e39f3f06457d09`.
No recorder/gateway processes remained. No paid compute or Brev was used.
The unrelated untracked files remain unstaged. Public release was skipped
because it was not authorized. Q15 is the only active card.

### Q14 post-Q15 corrected closeout

```text
uv run --offline pytest -q \
  tests/test_bidirectional_pawn_push_registration_dataset.py \
  tests/test_bidirectional_scene_registration_v4.py \
  tests/test_bidirectional_registration_v4_evaluator.py \
  tests/test_bidirectional_registration_v4_label_audit.py \
  tests/test_bidirectional_c2_v4_replay.py \
  tests/test_bidirectional_off_source_evaluator.py \
  tests/test_bidirectional_off_source_feasibility_audit.py \
  tests/test_bidirectional_q06_scene_gate.py \
  tests/test_bidirectional_terminal_evidence.py \
  tests/test_scene.py \
  tests/test_studio.py
.............................................                          [100%]
45 passed, 2 subtests passed in 8.40s

scripts/audit_autonomous_workflow.sh
workflow audit clean

uv run --offline sim2claw physical-gateway-preflight
passed: true
device_configuration_rewritten: false
start_alignment_motion_commanded: false
physical_follower_torque_enabled: false

brev ls
No instances in org NCA-09be-32030

git push origin codex/geometric-microtransfer-20260727
c272104..68a7de3
```

The fresh preflight reproduced the existing torque-off receipt SHA-256
`ca50d9dae4aa9a7dd672edee625dfe51ff2e4ad65cb76e7a28e39f3f06457d09`.
No repo-owned camera/gateway process remained. The unrelated untracked files
remain unstaged; no Brev or paid compute was used. Q15 is the only active
card.

## Q15 final reconciliation

Computer Use returned to the existing Claude Desktop conversation
`Sim-to-real transfer evaluation`; model selector and response identity both
reported Claude Fable 5 (`claude-fable-5`). No replacement thread was
created. The correction report covered Q03/Q05/Q06/Q13 hashes, exact
denominators, absent action hashes, tests, torque/process/Brev state, pushed
commits, and limitations.

Fable independently read the pushed repository, verified the new hashes,
re-extracted the sealed C922 apex, inspected the Pi apex, ran a sample of the
new tests (`6 passed`), and confirmed origin at `ee7ef46`. Its final decision:

```text
ACCEPT
Q03 is honestly closed as unadjudicable rather than circularly rescored.
The corrected proof class, denominators, and v4-indeterminate status follow.
No remaining required-criterion defect must reopen a card.
```

Identity: Claude Fable 5 (`claude-fable-5`), same
`Sim-to-real transfer evaluation` conversation, 2026-07-27, read-only.
Artifact:
`docs/reviewer-messages/048-q15-fable-final-reconciliation.md`.

## Final queue self-audit

- Active cards: `0`.
- Unjustified `PENDING` cards: `0`.
- Q00-Q06 and Q13-Q15: evidence-backed dispositions.
- Q07-Q12: explicitly not authorized because Q06 admitted no case and no
  action existed; none is marked passed.
- Definition-of-Done item 1: unmet. V4 fit passes at `24.631505 mm`; held-out
  metric status is unscorable/indeterminate.
- Definition-of-Done item 2: a native float64/40 Hz ten-case evaluator was
  frozen, but its F1 premise is unsupported and its clearance contract is
  structurally infeasible for the reset layout.
- Definition-of-Done items 3-4: unmet. REAL→SIM `0/0`; SIM→REAL `0/0`.
- Definition-of-Done item 5: no counted attempt began; there are no action,
  mapping, execution, or outcome receipts to fabricate.
- Definition-of-Done item 6: corrected local viewer/package and Studio
  blocked entry expose exact zeros, empty action hashes, and limitations.
- Definition-of-Done item 7: torque false; zero repo-owned camera/gateway
  processes; unrelated files preserved; corrected commits pushed through
  `ee7ef46`; public release skipped as unauthorized.
- Artifacts/hashes: Q03 correction, Q05 feasibility, Q06 gate, Q13 package,
  viewer, evaluator, candidate, and torque receipt resolve.
- Tests: `45 passed, 2 subtests passed`; workflow audit clean.
- Brev: no instances; no paid compute used.
- Final proof class:
  `terminal_preregistered_contract_infeasibility_without_physical_attempt`.
- Final attempt ledger: REAL→SIM `0/0`; SIM→REAL `0/0`; total `0/10`.
- Counted action hashes: none.
- Physical/simulator/bidirectional task success: none.

The target bidirectional claim was not achieved and the queue is not marked
successful. Continuing would require a new camera-adjudicable held-out
episode and a prospectively feasible successor evaluator. Both are outside
the frozen queue and require new owner authorization; no user physical
intervention is requested.
