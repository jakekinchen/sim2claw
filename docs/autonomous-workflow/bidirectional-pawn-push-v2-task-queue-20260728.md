# Bidirectional Pawn-Push V2 Task Queue

Status: `ACTIVE_READ_ONLY_PREFREEZE`

Created: `2026-07-28`

Owner/operator: sole active Codex writer in the live checkout

Checkout: `/Users/kelly/Developer/sim2claw`

Branch: `codex/geometric-microtransfer-20260727`

## Mission and exact claim boundary

Produce the smallest honest, camera-verifiable bidirectional task-transfer
proof without human physical intervention:

- one REAL->SIM case: physical outcome first, followed by identical canonical
  float64/40 Hz action bytes in CPU/fp64 MuJoCo; and
- one separate SIM->REAL case: simulator outcome first, then the frozen
  identical canonical bytes once on hardware.

The default primitive is a straight closed-jaw pawn push. Success means:

> The selected pawn base center completely leaves its source square in the
> preregistered intended direction while every preregistered excluded object
> remains stationary.

Adjacent-square centering is not required unless pre-freeze feasibility
evidence proves it safe and feasible. The maximum physical budget is ten
one-use preregistered cases total. This campaign can support only a narrow
bidirectional pawn-push primitive claim, never general manipulation,
pick-and-place, learned-policy transfer, or broad sim-to-real transfer.

## Authority and source-of-truth order

1. Latest owner instruction authorizing this separate v2 campaign.
2. `AGENTS.md`.
3. This queue, including its live status, gates, decisions, hashes, evidence,
   and attempt ledger.
4. Immutable v2 camera, gateway, action, simulator, evaluator, and closeout
   receipts.
5. Existing repository authority files and tests.
6. The immutable v1 queue and receipts, which remain historical evidence and
   grant no v2 success.
7. Advisory-model output.

Repository evidence outranks hypotheses. Every transition, retry, blocker,
fallback, metric, attempt, and reviewer decision must be recorded here
immediately. Exactly one card may be `IN_PROGRESS`.

## V1 preservation boundary

V1 remains closed at commit
`b694b4272dbf4aa6f39be41fbe8858b569e3198c` with:

- proof class
  `terminal_preregistered_contract_infeasibility_without_physical_attempt`;
- REAL->SIM `0/0`, SIM->REAL `0/0`, total `0/10`;
- no action hashes or task success;
- registration v4 fit residual `24.631505 mm` but an unadjudicable held-out;
  and
- immutable evaluator
  `bidirectional_off_source_push_evaluator_v1`, SHA-256
  `8450682fac61ac064198b90858f58e6753b0d701ed55f067f91d88ed04604479`,
  whose `88.9 mm` exclusion rule is structurally infeasible for the reset
  layout.

V2 will not mutate, overwrite, reinterpret, weaken, or reuse v1 denominators,
receipts, evaluator identity, held-out authority, or failed/indeterminate
results.

## Inviolate safety and integrity rules

- No robot motion until V00-V02 pass and V03 is explicitly `IN_PROGRESS`.
- Only the reviewed physical gateway may command the robot.
- Cameras start before any motion and enclose the full transaction.
- Registration motion is no-contact, slow, collision-previewed, and
  stop-on-tracking/contact/stall.
- Torque is disabled on every success, failure, interrupt, exception, and
  exit path.
- No EEPROM writes, servo-ID changes, RAM gain changes, torque-limit changes,
  unreviewed controller changes, training, P8/P13 work, Brev, or paid compute.
- No human touching, reset, aiming, placement, or repositioning.
- C922 is the physical task-outcome owner. Pi IMX708 and D405 color are
  supporting views only; wrist depth is omitted.
- Fit and held-out targets are declared before capture. Held-out observations
  remain sealed until the candidate family is frozen and are opened once.
- Canonical action rows are native little-endian float64, C-contiguous, at
  40 Hz and byte-identical within a directional transfer case.
- Hardware and simulator mappings are separately versioned and hash-bound.
- Setup/reposition/recovery sequences are separately named and hash-bound and
  are never part of policy/action evidence.
- No runtime clipping, retiming, offsets, IK repair, assistance, retry,
  corrective suffix, or state forcing in counted actions.
- One physical attempt per frozen case. Once counted motion begins, a stopped
  case remains in its direction's denominator.
- Prior physical outcomes cannot tune a SIM->REAL case.
- Every excluded object's camera-owned stationary threshold and modeled
  clearance is frozen before action compilation.
- Preserve unrelated dirty/untracked paths and stage only campaign-owned
  files.

## Registration design contract

The v2 registration dataset must be camera-adjudicable by construction:

1. The fixed C922 owns the physical board plane and task region.
2. Board-plane metric geometry comes from visible board corners/grid
   intersections and either verified camera intrinsics/extrinsics or a
   prospectively fitted planar homography/PnP model.
3. Fit and held-out targets are split before capture. The v1 occluded B7
   episode is prohibited as v2 authority.
4. Robot-controlled hover correspondences use a modeled gripper reference
   that remains visible simultaneously with the relevant board region.
5. V00-V02 must prove candidate hover collision clearance, joint limits,
   visibility, C922 field of view, and no-contact height in CPU/fp64
   simulation/static projections before gateway motion.
6. V03 records C922 before motion, captures each fit/held-out target exactly
   once under a versioned acquisition contract, and guarantees torque-off.
7. The candidate family is frozen using fit observations only. The held-out
   is then opened once.
8. Admission requires task-relevant held-out metric error `<25 mm` plus the
   prospectively frozen pixel/reprojection sanity threshold.
9. If an observation is unscorable, redesign and prospectively collect a new
   split before any counted action exists. Camera-contract inadequacy is not
   terminal while a safe autonomous recapture path remains.

## Evaluator and feasibility contract

Before evaluator or case-list freeze, the draft must prove all of:

- route reachability and joint-limit margin;
- CPU/fp64 collision preview;
- pawn-base edge clearance for complete source-square exit in the intended
  direction;
- swept gripper/pawn corridor clearance from modeled excluded objects;
- C922 source, direction, selected-pawn, and excluded-object adjudicability;
- destination/corridor emptiness; and
- at least two feasible candidate cases per direction.

Exclusion margins must be derived from modeled pawn/gripper geometry,
registration uncertainty, camera uncertainty, and a documented safety
margin. V2 must not inherit v1's impossible `88.9 mm`/two-square rule. Draft
infeasibility must be repaired prospectively without task outcomes and before
freeze.

The final preregistration binds evaluator version, float64/40 Hz encoding,
camera thresholds, registration/mapping/scene hashes, maximum-ten case list,
per-case source and direction, exclusions, one-attempt rule, stop rules, and
denominators before any counted action is compiled.

## Queue

| ID | Status | Task | Acceptance gate | Evidence |
|---|---|---|---|---|
| V00 | `IN_PROGRESS` | Read-only inventory, v1 verification, live torque/process/camera/Git state, and pre-freeze camera/feasibility design. | V1 closeout and hashes resolve; torque false; no competing writer or repo-owned camera/gateway process; all unrelated paths preserved; fixed-C922 adjudication design and candidate no-contact hover strategy documented from live evidence. No motion. | Pending. |
| V01 | `PENDING` | Preregister a new camera-owned registration acquisition, board-plane metric model, fit/held-out split, and sealed-input rules. | Versioned contract declares visible board features, camera model inputs, gripper reference, fit targets, held-out targets, pixel/reprojection sanity gate, `<25 mm` metric gate, hashes, and recapture fallback before capture. | Pending. |
| V02 | `PENDING` | Prove hover poses and visibility using CPU/fp64 simulation and static camera projections/images. | Every proposed target passes joint limits, self/table/board/pawn clearance, no-contact height, slow-path preview, C922 field of view, simultaneous gripper/board visibility, and guaranteed return/torque-off logic. Reviewer decision `CONTINUE`. No motion. | Pending. |
| V03 | `PENDING` | Capture the prospective fit and held-out registration observations through the reviewed gateway. | Cameras precede motion; only approved slow no-contact paths run; requested/mapped/sent and tracking receipts close; every planned target is captured; torque false on exit; input hashes freeze; no pawn contact. | Pending. |
| V04 | `PENDING` | Fit and freeze a new registration candidate using fit data only, then open held-out once. | Candidate/family hash freezes before opening held-out; task-relevant held-out error `<25 mm`; frozen pixel/reprojection sanity gate passes; CPU/fp64 scene builds. If unscorable, prospectively redesign/recapture before counted actions. | Pending. |
| V05 | `PENDING` | Draft v2 evaluator and maximum-ten case family, then run reset-layout feasibility audit before freeze. | Route/joint/collision/edge/corridor/camera/destination checks pass with documented margins and at least two feasible candidates per direction. Draft defects are repaired before freeze without task outcomes. | Pending. |
| V06 | `PENDING` | Independently review and freeze evaluator v2, case list, mappings, scene, thresholds, and stop rules. | Native float64/40 Hz contract and every required hash bind before any counted action compilation; reviewer returns `CONTINUE`; attempt ledger remains `0/0` each direction. | Pending. |
| V07 | `PENDING` | Admit a fresh C922 REAL->SIM case and compile/review its hardware-first action and separate setup. | Scene passes evaluator; CPU/fp64 safety preview clean; setup/action/mapping hashes freeze separately; action has no clipping/repair/assistance; one attempt authorized. | Pending. |
| V08 | `PENDING` | Execute the admitted REAL->SIM physical action once and adjudicate it before simulation. | Cameras enclose motion; byte identity and tracking pass; C922 evaluator decides success/failure; exclusions stay stationary; torque-off closes. Attempt is counted. | Pending. |
| V09 | `PENDING` | Replay V08 identical canonical bytes in v2 MuJoCo. | No clipping/retiming/offset/IK/assistance/state forcing; evaluator decides simulated success/failure and records first divergence. Continue distinct cases if needed. | Pending. |
| V10 | `PENDING` | On a distinct case, achieve SIM->REAL simulator success before action freeze. | Simulator evaluator passes; robustness/safety preview passes; action/mapping/scene/evaluator hashes seal before any corresponding physical motion. | Pending. |
| V11 | `PENDING` | Execute the frozen SIM->REAL action once on hardware and adjudicate it from C922. | Identical canonical bytes; C922 evaluator decision; exclusions stationary; no retry; torque-off closes. Attempt is counted. | Pending. |
| V12 | `PENDING` | Continue distinct preregistered cases only as needed, within ten total. | All failures remain in denominators; one physical attempt per frozen case; stop new cases immediately after at least one complete case succeeds in each direction. | Pending. |
| V13 | `PENDING` | Package synchronized camera/simulation evidence, hashes, attempt ledger, and exact claim in Studio/browser artifacts. | Viewer and Studio expose both direction timelines, exact numerators/denominators, failures, action/mapping/evaluator hashes, proof class, and limitations; private raw media remains local. | Pending. |
| V14 | `PENDING` | Run focused/full tests, workflow audit, torque/process/Brev cleanup, scoped commit, and push. | Required tests and audits pass; follower torque false; repo-owned camera/gateway processes closed; `brev ls` clean; unrelated files untouched; branch pushed. | Pending. |
| V15 | `PENDING` | Return to the existing Claude Desktop Fable 5 thread and reconcile the v2 evidence. | Same `Sim-to-real transfer evaluation` thread used; model/date/response recorded; every concrete proof defect is verified and closed by reopening the responsible card before finalization. | Pending. |

## Fallbacks and stop rules

- Registration unscorable before counted actions: redesign camera geometry and
  collect a new prospectively split dataset. Do not terminate.
- Draft evaluator infeasible: repair its geometry/margins/case list before
  freeze using only pre-outcome evidence. Do not terminate.
- Counted case fails: retain it in the denominator and advance to a distinct
  preregistered case while budget and safety gates remain.
- One direction succeeds and the other has not: preserve the partial evidence
  but continue safely within the frozen case budget; never claim
  bidirectional success early.
- Stop the current motion immediately on torque uncertainty, tracking/stall
  breach, unreviewed contact, identity mismatch, missing C922 authority,
  changed action bytes, unsafe geometry, or closeout failure.
- A stopped counted action remains an attempt once counted motion began.
- Overall termination without bidirectional success requires a receipt-backed
  robot/camera safety or authority boundary after safe autonomous alternatives
  are exhausted. Infrastructure work, camera-contract defects, or preventable
  evaluator design errors are never terminal.

## Live ledger

Current state:

- V00 is the only active card.
- Robot motion is unauthorized through V02.
- Counted actions do not exist.

Completed:

- Owner authorized the separate v2 successor campaign on `2026-07-28`.
- V1 is preserved and remains non-promoting.

Verification evidence:

- Live checkout is on `codex/geometric-microtransfer-20260727` at
  `b694b4272dbf4aa6f39be41fbe8858b569e3198c`, synchronized with its remote at
  the first V00 inspection.
- The six owner-named unrelated paths are untracked and preserved:
  `configs/evaluations/c922_exact_mode_calibration_v1_exhausted.json`,
  `docs/run-logs/2026-07-24-c922-exact-mode-calibration-v1-terminal-not-ready.md`,
  `output/`, `src/sim2claw/c922_exact_mode_calibration_control.py`,
  `tests/test_c922_exact_mode_calibration_control.py`, and
  `tools/build_fiducial_sheet.py`.
- One additional pre-existing untracked path,
  `src/sim2claw/contact_free_comparison.py`, is also preserved.
- V1 queue status is `TERMINAL_NO_TRANSFER_OWNER_AUTHORITY_BOUNDARY`; its
  final Fable decision is `ACCEPT`.

Remaining:

- Complete V00 live hardware/camera/process inventory and design.
- V01-V15.

Blockers:

- None established. Motion remains deliberately gated.

Next action:

- Run read-only gateway preflight, USB/camera/process inventory, inspect
  current C922-owned geometry and existing gateway/camera contracts, and
  record the prospective hover/adjudication design.

Attempt ledger:

- REAL->SIM successful/attempted: `0/0`.
- SIM->REAL successful/attempted: `0/0`.
- Total counted physical attempts: `0/10`.
- Counted action hashes: none.

## Transition log

### V00 start — 2026-07-28

The v2 queue was created as a separate campaign. No v1 file or receipt was
modified. The worktree inventory was read-only. No camera was opened and no
gateway command was issued before this transition.
