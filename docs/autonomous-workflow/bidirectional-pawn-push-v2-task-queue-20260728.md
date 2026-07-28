# Bidirectional Pawn-Push V2 Task Queue

Status: `ACTIVE_V04_VERSIONED_RECAPTURE_DESIGN`

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
| V00 | `DONE` | Read-only inventory, v1 verification, live torque/process/camera/Git state, and pre-freeze camera/feasibility design. | V1 closeout and hashes resolve; torque false; no competing writer or repo-owned camera/gateway process; all unrelated paths preserved; fixed-C922 adjudication design and candidate no-contact hover strategy documented from live evidence. No motion. | Receipt `runs/bidirectional-pawn-push-v2/20260728-v00-read-only-design/v00_read_only_design_receipt.json`, SHA-256 `2c818ed0b70458ca0cd2d2758ec2c4a74790dcc6bc0733bc82dafca157908ebf`. Fresh exact-mode C922 frame SHA-256 `00e1e84b83e28344849400c502975bdca70ad40975815c31b10c20073483cebe`; `92` callbacks, zero drops. Gateway preflight passed with torque false and no motion/config rewrite. CPU/fp64 found a fixed-elbow `13.615385 deg` source egress that monotonically clears the two source-only modeled folded-arm contacts, then a contact-free seven-pan hover family spanning `106.558 mm` in model x plus a separate elevated held-out. No physical motion. |
| V01 | `DONE` | Preregister a new camera-owned registration acquisition, board-plane metric model, fit/held-out split, and sealed-input rules. | Versioned contract declares visible board features, camera model inputs, gripper reference, fit targets, held-out targets, pixel/reprojection sanity gate, `<25 mm` metric gate, hashes, and recapture fallback before capture. | Contract `configs/evaluations/bidirectional_pawn_push_v2_registration_acquisition_v1.json`, SHA-256 `f345d9ff55ed38b8509dac061af7d0ce7aeaefb59cb78f92ba4460b5dbe82024`. Four fit targets and four held-out targets are disjoint and prospectively frozen; v1 B7 reuse forbidden; C922 owns board/task; D405 depth omitted; normalized zero-distortion `3x4` DLT family and pixel/annotation/`<25 mm` gates fixed; held-out single-open and versioned recapture fallback fixed. Validation attempt 1 failed only on a mistyped C922-contract digest before freeze; corrected to the live digest. Attempt 2: `3 passed in 0.04s`. No capture or motion. |
| V02 | `DONE` | Prove hover poses and visibility using CPU/fp64 simulation and static camera projections/images. | Every proposed target passes joint limits, self/table/board/pawn clearance, no-contact height, slow-path preview, C922 field of view, simultaneous gripper/board visibility, and guaranteed return/torque-off logic. Reviewer decision `CONTINUE`. No motion. | Route `configs/hardware/bidirectional_pawn_push_v2_registration_route_v1.json`, SHA-256 `b7464a34a6abe744d778323a7a017f5ab8f40d6f6556b7691f5944e1bbd52d8e`. Final receipt `runs/bidirectional-pawn-push-v2/20260728-v02-static-route-v2/evaluation.json`, SHA-256 `53c6b4dec93cae8f41e9bc24a106fcc0883d3c11d97c887aec3c630491bdbcf6`; deterministic reviewer `CONTINUE`, evidence anchor `100`, all `11/11` gates true. Fresh torque-off start matched the frozen rebase exactly. Source egress: `92` float64 rows, `4.55 s`, hash `9a3ccff7ba26e94f2cce2963480e33a2999b07efa16777edc73530a8fa28e142`. Capture/return: `1541` float64 rows, `77.0 s`, hash `6d05f2471ec0ca8f83beadbc9bbfcc4b6d8ae4c679198414fad600bf29a1dbdf`. Maximum slew `2.999531 deg/s`; minimum jaw clearance `66.282 mm` to any pawn and `93.975 mm` to board; C922 proxy minimum image margin `206.268 px`. All eight camera rays first hit the intended moving jaw `5.865-7.045 mm` before the registered midpoint, within the frozen `15 mm` surface-offset gate. No motion occurred; no camera opened, gateway was constructed, or attempt was counted. |
| V03 | `DONE` | Capture the prospective fit and held-out registration observations through the reviewed gateway. | Cameras precede motion; only approved slow no-contact paths run; requested/mapped/sent and tracking receipts close; every planned target is captured; torque false on exit; input hashes freeze; no pawn contact. | Execution receipt `runs/bidirectional-pawn-push-v2/20260728-v03-registration-capture-v1/execution/execution_receipt.json`, SHA-256 `a1692a5b87d88b7b2c37151159660546d9104c9b3973de85f0801de0d9e793a3`, status `completed_no_contact_registration_capture`, proof class `physical_rgb_no_contact_registration_observation_only`. All exact `92 + 1541` requested/mapped/sent rows are byte-identical to the reviewed arrays; all eight scored holds pass; nine C922 sessions have zero drops; fit and sealed-heldout manifests hash to `933f121a60b741d5a555b865caccf8fedce1ea0b6accd0e007cd42f77eafa8a5` and `6fd932ddf33c2e5aae87680e141eb1a41f05feb19196eac2fd2343ad3f5a18d6`; final preflight proves torque false. No pawn contact or task attempt. |
| V04 | `IN_PROGRESS` | Fit and freeze a new registration candidate using fit data only, then open held-out once. | Candidate/family hash freezes before opening held-out; task-relevant held-out error `<25 mm`; frozen pixel/reprojection sanity gate passes; CPU/fp64 scene builds. If unscorable, prospectively redesign/recapture before counted actions. | Acquisition-v1 fit attempt 1 was rejected before held-out: receipt `runs/bidirectional-pawn-push-v2/20260728-v04-registration-fit-v1/fit_receipt.json`, SHA-256 `9b6378fc32a3f22fc6c9c6379a86df2a96562b3c0207f07488494d68c13adedb`. Board and annotation gates pass, but hover reprojection is `11.281007 px` RMS / `15.767004 px` max versus frozen `6/10 px` gates. Held-out open count remains `0`. Owner resume authorizes the preregistered nonterminal fallback. A new family and newly split observations must freeze and pass CPU/fp64 route/visibility review before any camera or gateway opens. |
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

- V04 is the only active card.
- The fit manifest is frozen and the held-out manifest remains separately
  sealed. Acquisition-v1 failed its fit-only pixel gate without a held-out
  open. The owner integration barrier is closed and V04 is active in
  replacement-family design. Acquisition-v1 held-out remains prohibited.
  Camera open, gateway construction, and robot motion remain unauthorized
  until the new split/family and CPU/fp64 route/visibility gate freeze and
  pass.
- Counted actions do not exist.

Completed:

- Owner authorized the separate v2 successor campaign on `2026-07-28`.
- V1 is preserved and remains non-promoting.
- V00 completed read-only. The live C922, SO-101 buses, torque state,
  processes, v1 hashes, and candidate hover geometry were inventoried without
  motion.
- V01 froze the first v2 registration acquisition contract before any
  authoritative capture or motion.
- V02 froze and passed the exact CPU/fp64 source-egress, eight-hover,
  camera-visibility, and safe-return proof without motion.
- V03 completed the single reviewed no-contact registration transaction,
  froze four fit and four sealed-heldout C922 observations, and closed with
  torque false. It consumed zero task attempts.

Verification evidence:

- Live checkout began V00 on
  `codex/geometric-microtransfer-20260727` at
  `b694b4272dbf4aa6f39be41fbe8858b569e3198c`, synchronized with its remote.
  Queue adoption commit is `1bf7839`.
- A pre-existing Claude Desktop process committed
  `3c4f04588b7c1d2fa8c22df5d0981dd790d50e19`
  (`Publish B7 action-identical same-camera proof`) immediately after queue
  adoption. It changed only `src/sim2claw/contact_free_comparison.py`. The
  commit is preserved. A five-second follow-up found stable HEAD, no Git lock,
  no open regular repository file from that idle process, and no further
  write; V00 did not classify it as an active competing writer. Recheck this
  boundary before every campaign commit and every gateway transaction.
- The six owner-named unrelated paths are untracked and preserved:
  `configs/evaluations/c922_exact_mode_calibration_v1_exhausted.json`,
  `docs/run-logs/2026-07-24-c922-exact-mode-calibration-v1-terminal-not-ready.md`,
  `output/`, `src/sim2claw/c922_exact_mode_calibration_control.py`,
  `tests/test_c922_exact_mode_calibration_control.py`, and
  `tools/build_fiducial_sheet.py`.
- The additional path `src/sim2claw/contact_free_comparison.py` is no longer
  untracked because concurrent commit `3c4f045` adopted it. V2 did not edit
  it.
- V1 queue status is `TERMINAL_NO_TRANSFER_OWNER_AUTHORITY_BOUNDARY`; its
  final Fable decision is `ACCEPT`.
- V00 receipt:
  `runs/bidirectional-pawn-push-v2/20260728-v00-read-only-design/v00_read_only_design_receipt.json`,
  SHA-256
  `2c818ed0b70458ca0cd2d2758ec2c4a74790dcc6bc0733bc82dafca157908ebf`.
- Fresh C922 inventory:
  `runs/bidirectional-pawn-push-v2/20260728-v00-c922-inventory/frames/frame-091.png`,
  SHA-256
  `00e1e84b83e28344849400c502975bdca70ad40975815c31b10c20073483cebe`;
  exact `640x480`, `420v`, `30.00003000003 fps`, `92` callbacks, zero drops,
  recorder closed. All playing-area corners and most grid lines are visible;
  the folded arm occludes the center/lower-right, so this frame is inventory
  only and prohibited from the v2 registration fit.
- Fresh physical-gateway preflight: passed; follower torque false; no start
  alignment motion; no configuration rewrite; follower start
  `[-11.164835,-71.384615,99.472527,-25.714286,-102.813187,2.494062] deg`.
- CPU/fp64 source-state screen: only modeled
  shoulder/lower-arm `-3.235353 mm` and shoulder/wrist `-1.687426 mm`
  folded-arm overlaps; no external contact. A `138`-sample, `20 Hz`,
  `6.85 s` fixed-elbow egress to
  `[-11,-85,99.472527,-20,-102.813187,2.494062]` never worsens or expands
  those source pairs and ends contact-free.
- Proposed fit pan targets are `[-21,-11,-1,9] deg`; interleaved held-out pan
  targets are `[-16,-6,4] deg`, all with lift `-85`, elbow `99.472527`,
  wrist-flex `-20`, wrist-roll `-102.813187`, and gripper `2.494062`.
  Their CPU/fp64 pan sweep is contact-free and spans model pinch x
  `[-123.200,-16.642] mm`. A separate elevated held-out at pan `-6`,
  lift `-90` is contact-free and changes pinch z from `940.779` to
  `956.471 mm`.
- The registration candidate design is a normalized zero-distortion `3x4`
  projective-camera DLT using C922 board corners/grid plus four fit hovers,
  followed by a single-open test on the three interleaved pan targets and the
  elevated target. The observed reference is the distal closed-jaw tip
  midpoint under a frozen agent-only annotation protocol. V01 must freeze
  exact pixel/reprojection gates and annotator-agreement checks before any
  authoritative capture.
- V01 contract:
  `configs/evaluations/bidirectional_pawn_push_v2_registration_acquisition_v1.json`,
  SHA-256
  `f345d9ff55ed38b8509dac061af7d0ce7aeaefb59cb78f92ba4460b5dbe82024`.
  It binds four fit and four held-out hovers, C922 identity/mode, board
  lattice requirements, blinded two-pass distal-jaw annotation, one shared
  projective DLT family, pixel/reprojection gates, exclusive `<25 mm`
  held-out metric gate, held-out single-open rules, safety constraints, and a
  non-terminal versioned recapture fallback. `3 passed in 0.04s`.
- V02 route:
  `configs/hardware/bidirectional_pawn_push_v2_registration_route_v1.json`,
  SHA-256
  `b7464a34a6abe744d778323a7a017f5ab8f40d6f6556b7691f5944e1bbd52d8e`.
  The final CPU/fp64 receipt is
  `runs/bidirectional-pawn-push-v2/20260728-v02-static-route-v2/evaluation.json`,
  SHA-256
  `53c6b4dec93cae8f41e9bc24a106fcc0883d3c11d97c887aec3c630491bdbcf6`.
  Its deterministic reviewer returned `CONTINUE` with evidence anchor `100`
  and all `11/11` gates true.
- The exact little-endian float64 source-egress setup contains `92` rows over
  `4.55 s`, action/raw hash
  `9a3ccff7ba26e94f2cce2963480e33a2999b07efa16777edc73530a8fa28e142`,
  NPY SHA-256
  `71d22ad33620c4d95a7b9d3ff293ae507ab010f360f9b7ec77506f8bd2ea0451`.
  The capture/return setup contains `1541` rows over `77.0 s`, action/raw hash
  `6d05f2471ec0ca8f83beadbc9bbfcc4b6d8ae4c679198414fad600bf29a1dbdf`,
  NPY SHA-256
  `655d0ce093abbd9c52036074e3a57cc2419d2de52871e490199c06e18d721e87`.
  These are registration/setup arrays, not task-policy evidence.
- Fresh V02 preflight again returned torque false, no start-alignment motion,
  and no configuration rewrite. The observed follower start matched the
  frozen rebase exactly. CPU/fp64 found no new or external contact, a maximum
  slew of `2.999530315835841 deg/s`, minimum distal-jaw clearance
  `66.281754 mm` to any pawn and `93.975057 mm` to the board, and a final
  identity match to the prior physically demonstrated torque-off anchor.
- Static C922 proxy overlay:
  `runs/bidirectional-pawn-push-v2/20260728-v02-static-route-v2/c922_visibility_proxy.png`,
  SHA-256
  `50f7bc23ee1cd1beac16394a703caa15c810c3dc22d7f90d8648f73cdcaa1ee2`.
  The minimum predicted reference image margin is `206.267549 px`. A
  prospective MuJoCo ray gate added before any motion requires the first
  visible surface to be an allowed distal-jaw body within `15 mm` of the
  midpoint. All eight targets pass: every first hit is
  `left_moving_jaw_so101_v1`, with surface offsets from `5.865303` to
  `7.044856 mm`.
- V03 capture packet:
  `configs/hardware/bidirectional_pawn_push_v2_registration_capture_v1.json`,
  SHA-256
  `673458da820e977646151e08e84b5aff246302889f6e4da890554ba5cce15cbe`.
  It binds both exact V02 setup arrays, the V02 static receipt, C922 identity
  and source, sequential single-owner camera sessions, final-two-second hold
  selection, the `<=2 deg` tracking gate, zero callback drops, and
  torque-off/fresh-preflight cleanup. Setup arrays are explicitly excluded
  from policy, task, and transfer evidence.
- V03 pre-motion review:
  `runs/bidirectional-pawn-push-v2/20260728-v03-registration-capture-v1/pre-motion-review.json`,
  SHA-256
  `6d5e7e25ec6c8fbff48142466b94849463e7748431e1dd77c37387497219b040`.
  Fresh follower start again exactly matched the frozen source. The
  deterministic reviewer returned `CONTINUE`, evidence anchor `100`, all
  `12/12` gates true, and explicitly records no camera open, gateway
  construction, motion, or counted attempt.
- The V03 executor starts the first fixed C922 owner before gateway creation,
  requires one live owner for every exact row, closes and hashes a separate
  target session after each hold, starts the next owner before the next motion
  row, and uses a ninth camera session for the return. Requested, mapped, and
  sent physical-unit rows must be byte-identical. It writes stopped-safe
  evidence on error, closes the gateway in `finally`, and requires a fresh
  torque-off preflight before returning.
- V03 focused synthetic validation covers a complete `92 + 1541` row
  transaction and a forced sample-5 stop:
  `8 passed in 22.83s`. Both the success and forced-stop paths confirm
  torque-off and zero counted attempts. Python bytecode compilation and Git
  diff checks pass. The optional `ruff` executable is absent from the offline
  runtime, so no lint claim is made.
- V03 physical execution receipt:
  `runs/bidirectional-pawn-push-v2/20260728-v03-registration-capture-v1/execution/execution_receipt.json`,
  SHA-256
  `a1692a5b87d88b7b2c37151159660546d9104c9b3973de85f0801de0d9e793a3`.
  The `83.450816 s` transaction completed with proof class
  `physical_rgb_no_contact_registration_observation_only`. The source egress
  executed all `92/92` reviewed rows with identical hash
  `9a3ccff7ba26e94f2cce2963480e33a2999b07efa16777edc73530a8fa28e142`;
  capture/return executed all `1541/1541` rows with identical hash
  `6d05f2471ec0ca8f83beadbc9bbfcc4b6d8ae4c679198414fad600bf29a1dbdf`.
  Requested, mapped, and sent bytes were identical. Every final `40`-sample
  hold passed the exclusive `2 deg` tracking gate; the maximum target error
  ranged from `0.516484` to `0.681319 deg`. Nine sequential C922 sessions
  completed with zero callback drops. The joint-sample digest is
  `946813baa7fa3ad6e66a80bcadc59963d5d911fffb88d47d89313742e3a4a613`.
- The V03 fit manifest is
  `runs/bidirectional-pawn-push-v2/20260728-v03-registration-capture-v1/execution/fit_manifest.json`,
  SHA-256
  `933f121a60b741d5a555b865caccf8fedce1ea0b6accd0e007cd42f77eafa8a5`.
  Its four selected-image hashes are
  `0366cc50ab509c4e7b1c75299239e6447922c4f5d48105debd76e47f0673e996`,
  `6332f495f471bdffe48a314bad1fae19c60fa9e9cf96aefcdff20456c3ae627a`,
  `8cedd6534147119c01aeb8dd688ecedec7c79d7d45c624af48d53d4ae02ee641`,
  and
  `2f62561294d78c592991258e38293856bf18edb69196753ef708c8b7fc15dab4`.
  The separately sealed held-out manifest is
  `runs/bidirectional-pawn-push-v2/20260728-v03-registration-capture-v1/execution/heldout_sealed_manifest.json`,
  SHA-256
  `6fd932ddf33c2e5aae87680e141eb1a41f05feb19196eac2fd2343ad3f5a18d6`.
  Its opaque image hashes are
  `91190ac222b3934e0192b4aa56627195e585ad6d2b29e968bdd44cf1e4ac9073`,
  `1ae033388daa488387787ce1426eaf8bcec48b6a590762d2b160ea95cddaa485`,
  `0905a2d22cf18ce5b83ac734f43fef3755f19bc75a3cce3566e85e25e5afad39`,
  and
  `2f739cbd0453a52b42ad9954a15bc53192514601015288d89767e879d317bf14`.
  The physical frames show both distal jaw tips and the complete board lattice
  without pawn contact. This visual audit is observation-only and grants no
  registration or task success by itself.
- Final V03 gateway preflight passed with torque false,
  `device_configuration_rewritten:false`, and follower anchor
  `[-8.263736,-106.197802,99.208791,-94.021978,-125.318681,2.494062] deg`.
  The recorder and gateway were closed, no repo-owned C922 process remained,
  and no task action or physical attempt was counted.
- V04 acquisition-v1 fit annotations:
  `configs/evaluations/bidirectional_pawn_push_v2_registration_fit_annotations_v1.json`,
  SHA-256
  `35d60b5a9123ee9bb351538c90f00d3a6821e01b33563ea85730250268ee983a`.
  The fit process reads only the four fit images and their scored joint holds.
  Two independent jaw-tip passes agree within `0.707107 px`; the extracted
  board lattice has `1.486607 px` RMS and `3.9 px` maximum line residual, so
  all annotation and board gates pass.
- Frozen acquisition-v1 fit candidate SHA-256:
  `ea9caa941517956ca6115d71137ead7456d72548ee4fcb8acbcd8ee1e4f92dab`.
  Fit receipt SHA-256:
  `9b6378fc32a3f22fc6c9c6379a86df2a96562b3c0207f07488494d68c13adedb`.
  The exact contract feature is the midpoint of the means of the three fixed
  and three moving distal tip sphere centers at each observed hold. The
  normalized DLT condition number is `10.406306`, but hover reprojection is
  `11.281007 px` RMS and `15.767004 px` maximum, failing the frozen `6/10 px`
  gates. Board reprojection remains `1.604546 px` RMS / `1.955275 px` max.
  Status is `rejected_before_heldout`; held-out inputs were not read and
  held-out open count remains `0`.

Remaining:

- Complete V04's preregistered new-version registration recapture, fit-only
  candidate freeze, and one-time held-out evaluation.
- V05-V15.

Blockers:

- No terminal blocker is established. The owner integration barrier is
  complete. Registration design is authorized; physical recapture remains
  gated on a new frozen contract plus CPU/fp64 collision/visibility review.

Next action:

- Prospectively freeze a task-plane registration family and newly split
  non-collinear hover dataset, then prove the exact route and visibility in
  CPU/fp64. Do not reuse acquisition-v1 held-out or weaken any gate.

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

### V00 complete / V01 start — 2026-07-28

Exact read-only commands included:

```text
uv run --offline sim2claw physical-gateway-preflight
system_profiler SPCameraDataType
NativeC922StillRecorder(...); sleep 3.0; finish()
preview_wrist_view_actions(..., recovery_source_contact_admission=True)
preview_wrist_view_actions(... pan sweep ...)
```

The preflight returned `passed:true`,
`physical_follower_torque_enabled:false`,
`device_configuration_rewritten:false`, and
`start_alignment_motion_commanded:false`. The C922 inventory recorder closed
after `92` callbacks with zero drops. No robot motion occurred.

The CPU/fp64 static design found a bounded source-only egress that holds the
live elbow fixed, clears both modeled source self-contact pairs without
worsening them, and reaches a contact-free family of pan-separated hovers.
The inventory image is excluded from the future dataset. V01 is active;
physical attempts remain `0/10`.

### V01 complete / V02 start — 2026-07-28

The acquisition contract froze four fit hovers at pan
`[-21,-11,-1,9] deg`; three same-height held-out hovers at
`[-16,-6,4] deg`; and one elevated held-out at pan `-6`, lift `-90 deg`.
All other hover joints, camera identity/mode, split storage, annotation
protocol, DLT family, gates, sealing, and fallback rules are fixed.

Validation attempt 1 reported one source-binding typo:

```text
expected C922 capture contract:
904af4c...
live SHA-256:
e2daa9dc...
```

This occurred before contract freeze, capture, or motion. The binding was
corrected to the live file digest. Validation attempt 2:

```text
uv run --offline pytest -q \
  tests/test_bidirectional_pawn_push_v2_registration_acquisition.py
...                                                                      [100%]
3 passed in 0.04s
```

At that transition V02 became the only active card. Robot motion and counted
actions remained unauthorized; attempts were `0/10`.

### V02 complete / V03 start — 2026-07-28

The first fresh V02 command exited before evaluation because its local
assertion looked for a nonexistent `follower_torque_enabled` key. The actual
gateway-preflight schema exposes `physical_follower_torque_enabled`. No output
directory, camera, gateway, or motion resulted. A second read-only preflight
confirmed `passed:true`, `physical_follower_torque_enabled:false`,
`start_alignment_motion_commanded:false`, and
`device_configuration_rewritten:false`.

The first complete CPU/fp64 evaluation returned `CONTINUE`, but visual review
of its C922 overlay identified that an in-frame midpoint alone did not prove
the distal jaw was unobstructed. Before motion or capture, V02 added a frozen
camera-to-reference MuJoCo ray gate. The superseded diagnostic remains at
`runs/bidirectional-pawn-push-v2/20260728-v02-static-route-v1/`; it is not the
final V02 authority.

The final command was equivalent to:

```text
preflight = physical_gateway_preflight()
assert preflight["physical_follower_torque_enabled"] is False
evaluate_route(
  route_path=...registration_route_v1.json,
  output_root=.../20260728-v02-static-route-v2,
  observed_start=preflight["follower_start_degrees"],
)
```

The final receipt SHA-256 is
`53c6b4dec93cae8f41e9bc24a106fcc0883d3c11d97c887aec3c630491bdbcf6`;
all `11/11` gates pass and reviewer decision is `CONTINUE`. Focused
validation:

```text
OPENCV_OPENCL_RUNTIME=disabled uv run --offline pytest -q \
  tests/test_bidirectional_pawn_push_v2_registration_acquisition.py \
  tests/test_bidirectional_registration_v2_route.py
.....                                                                    [100%]
5 passed in 22.64s
```

V03 is the only active card. No physical motion has occurred in v2. Camera and
gateway remained unopened during V02. Counted attempts remain `0/10`.

### V03 pre-motion review — 2026-07-28

The capture packet prospectively binds:

- the V02 source egress and capture/return NPY files and semantic hashes;
- eight interleaved target holds with the final `40` samples (`2.0 s`) scored
  at an exclusive maximum absolute joint tracking error of `2.0 deg`;
- sequential exact-mode C922 sessions with one owner, zero drops, and a
  selected callback frame nearest the scored-hold midpoint;
- requested/mapped/sent byte identity, no rate limiting/clamping/assistance,
  stop-on-camera/tracking/stall, and torque-off plus fresh preflight on exit;
- separate fit and sealed-heldout directories/manifests; and
- zero task-action, pawn-contact, task-success, or transfer authority.

Focused validation:

```text
OPENCV_OPENCL_RUNTIME=disabled uv run --offline pytest -q \
  tests/test_bidirectional_registration_v2_capture.py \
  tests/test_bidirectional_registration_v2_route.py \
  tests/test_bidirectional_pawn_push_v2_registration_acquisition.py
........                                                                 [100%]
8 passed in 22.83s
```

The live motion-free command:

```text
python scripts/capture_bidirectional_registration_v2.py \
  --packet ...registration_capture_v1.json \
  --review .../pre-motion-review.json \
  --output .../execution \
  --review-only
```

returned `CONTINUE`, evidence anchor `100`, and all `12/12` gates true.
Review SHA-256:
`6d5e7e25ec6c8fbff48142466b94849463e7748431e1dd77c37387497219b040`.
It records torque-off fresh start, exact-array/V02 equality, and no camera,
gateway, motion, or counted attempt. V03 remains the only active card and
attempts remain `0/10`.

### V03 complete / V04 start — 2026-07-28

Immediately before the single physical transaction, the live branch HEAD
remained the committed V03 implementation `b7c00e8`; no Git lock or competing
repository writer was present; the exact packet, V02 receipt, and setup hashes
matched; no repo-owned C922 or gateway process was running; a fresh gateway
preflight passed without start alignment or configuration rewrite and proved
follower torque false.

The exact committed execution command was:

```text
OPENCV_OPENCL_RUNTIME=disabled uv run --offline python \
  scripts/capture_bidirectional_registration_v2.py \
  --packet \
  configs/hardware/bidirectional_pawn_push_v2_registration_capture_v1.json \
  --review \
  runs/bidirectional-pawn-push-v2/20260728-v03-registration-capture-v1/pre-motion-review.json \
  --output \
  runs/bidirectional-pawn-push-v2/20260728-v03-registration-capture-v1/execution \
  --yes
```

It exited successfully after `83.450816 s`. All eight target captures and the
return were enclosed by sequential exact-mode C922 owner sessions. The exact
reviewed `92`-row egress and `1541`-row capture/return arrays executed with
planned/executed semantic hashes unchanged, requested/mapped/sent byte
identity true, every target hold below `0.682 deg` maximum absolute error, and
zero camera drops. No pawn contact was authorized or observed. The gateway
closed unconditionally and a fresh post-close preflight proved torque false.

Execution receipt SHA-256:
`a1692a5b87d88b7b2c37151159660546d9104c9b3973de85f0801de0d9e793a3`.
Fit-manifest SHA-256:
`933f121a60b741d5a555b865caccf8fedce1ea0b6accd0e007cd42f77eafa8a5`.
Sealed-heldout-manifest SHA-256:
`6fd932ddf33c2e5aae87680e141eb1a41f05feb19196eac2fd2343ad3f5a18d6`.

V03 is `DONE`; V04 is the only active card. Held-out open count is `0`.
Counted physical attempts remain `0/10`.

### V04 acquisition-v1 fit rejection / recapture fallback — 2026-07-28

The fit-only annotation file froze four image hashes, two independent
distal-tip passes per image, fit-only board-lattice extraction, exact scored
joint-hold telemetry, and the exact modeled feature before executing the fit.
The implementation uses the arithmetic mean of the three fixed distal-tip
sphere centers and the three moving distal-tip sphere centers at each actual
hold, then their midpoint. It does not reuse the reach planner's closed-jaw
local offset.

Focused validation:

```text
uv run --offline pytest -q \
  tests/test_bidirectional_registration_v2_fit.py
..                                                                       [100%]
2 passed in 0.29s
```

The exact fit command was:

```text
OPENCV_OPENCL_RUNTIME=disabled uv run --offline python \
  scripts/fit_bidirectional_registration_v2.py \
  --annotations \
  configs/evaluations/bidirectional_pawn_push_v2_registration_fit_annotations_v1.json \
  --output \
  runs/bidirectional-pawn-push-v2/20260728-v04-registration-fit-v1
```

The seeded board lattice passed at `1.486607 px` RMS and `3.9 px` maximum.
Annotation tip and midpoint agreement passed. The normalized DLT design
condition number passed at `10.406306`. The fit hover reprojection did not
pass: `11.281007 px` RMS and `15.767004 px` maximum versus frozen limits of
`6 px` and `10 px`. Receipt status is `rejected_before_heldout`.

No held-out image or annotation was read by the fit evaluator; held-out open
count is `0`. The v1 candidate and failed receipt are immutable diagnostics
and grant no registration or task success. The acquisition contract's
versioned recapture fallback is mandatory and nonterminal, but is pending and
not authorized during the owner pause. V04 remains the only active card.
Counted attempts remain `0/10`.

### V04 owner pause checkpoint — 2026-07-28

The owner imposed a pause at the safe fit-rejection boundary so separate
current-campaign graph integration and visual 3DGS/simulator comparison work
can complete. This writer will not implement those integrations and will not
open a camera, construct a gateway, open held-out, design or execute a
replacement capture, or issue robot motion while paused.

The clean checkpoint scope is limited to the V03 completion record, frozen
fit annotations, deterministic fit-only implementation and tests, immutable
acquisition-v1 rejection receipt/hash, and this queue transition. V04 remains
`IN_PROGRESS` as the sole active card because its acceptance gate has not
passed. The replacement recapture fallback is pending explicit resume.

Checkpoint verification:

```text
OPENCV_OPENCL_RUNTIME=disabled uv run --offline pytest -q \
  tests/test_bidirectional_registration_v2_fit.py \
  tests/test_bidirectional_registration_v2_capture.py \
  tests/test_bidirectional_registration_v2_route.py \
  tests/test_bidirectional_pawn_push_v2_registration_acquisition.py
..........                                                               [100%]
10 passed in 22.99s
```

Python bytecode compilation and `git diff --check` pass. The live HEAD before
the checkpoint commit is `b7c00e86585d180c454a45b06673015182b1ce50`; the
index lock is absent. The long-lived Claude Desktop process `46361` has no
open regular file in this repository and is not treated as a competing
writer.

The last live post-motion gateway preflight is embedded in the immutable V03
execution receipt. It reports `passed:true`,
`physical_follower_torque_enabled:false`,
`torque_off_confirmed:true`, no configuration rewrite, and no error. A fresh
process/device-owner audit at this pause found no repo-owned C922 capture or
gateway/controller process and no open handle on follower device
`/dev/cu.usbmodem5B3D0406411`. Because the pause forbids gateway construction,
the checkpoint intentionally did not perform another bus-opening preflight;
there has been no subsequent motion command after the receipt-backed
torque-off close.

The five-path scoped V04 implementation checkpoint was committed as
`23b410d` (`Checkpoint rejected v2 registration fit`) and pushed to
`origin/codex/geometric-microtransfer-20260727`. This queue-only successor
records that completed handoff; the six unrelated untracked paths remain
unstaged and untouched.

### Owner integration barrier result — 2026-07-28

The separately authorized integration keeps V04 paused and adds two
read-only, non-motion surfaces before resume:

1. A deterministic current-campaign adapter compiles V00 through V04 into the
   shared SAIL belief-graph vocabulary. It binds the live queue, V00/V02/V03
   receipts, immutable V04 rejected-fit receipt/candidate, retained
   simulator-candidate manifest, and registered IMG_5349 visual reference.
   The graph retains a five-revision timeline, source hashes, explicit
   configuration context, and an active pointer back to this paused V04
   checkpoint. Tracked output:
   `docs/autonomous-workflow/bidirectional-pawn-push-v2-current-graph.json`.
   Config:
   `configs/sail/bidirectional_pawn_push_v2_current_graph_v1.json`.
2. The existing Studio `#/calibration` route becomes the responsive
   world-space light table. It renders the complete registered
   `334,537`-splat workspace and complete reviewed MuJoCo scene in the same
   orbit camera, exposes independent 3DGS and MuJoCo opacity rails plus
   isolate/overlay presets, and reads its delta ledger from the validated
   graph.

The integration deliberately separates three claims:

- **World visual:** a non-zero visual delta is present. The retained
  board-conditioned 3DGS registration has `3.758551 px` held-out corner RMS
  across `166` corners. Its `22.7/39.0 mm` base-cloud-to-CAD medians are
  orientation diagnostics only, not measured robot pose or global metric
  geometry error.
- **Current camera-to-model registration:** V04 has a separate non-zero
  `11.281007 px` RMS / `15.767004 px` maximum jaw-projection residual and is
  rejected before held-out. This is not transferred-action evidence.
- **Directional task/action:** REAL->SIM remains `0/0`, SIM->REAL remains
  `0/0`, and direction-specific RMS is unavailable. The UI must not infer it.

This means the currently observed mismatch is **not only action data**:
visual world registration and camera-to-model registration each expose
non-zero image-space residuals. It remains invalid to turn either pixel
residual into a global 3D metric, collision, contact, actuator, task, or
bidirectional-transfer claim.

No camera, gateway, held-out input, or robot motion is authorized by this
integration. After its graph digest and browser verification are reported,
the sole V04 writer may resume only through a new explicit thread prompt that
preserves the graph as its active context and continues the prospectively
versioned recapture fallback.

### V04 owner resume / versioned recapture design start — 2026-07-28

The owner explicitly closed the integration barrier and authorized the
existing V04 fallback. The live branch and origin both resolve to integration
commit `084a9e33f8cd2b701bba47d35fa4e53d69f2972f`. The tracked graph's embedded
canonical digest is
`44a856941a16a736de302e55d4c025220786b7d7fca88ea641436dfa4a383153`;
its outer file SHA-256 is
`923962215759f80107e18c7067d6f28a00f082475864e38652e4b648a558ff9b`.
The distinction is intentional. The graph adapter baseline passes:

```text
uv run --offline pytest -q tests/test_current_campaign_graph.py
..                                                                       [100%]
2 passed in 0.40s
```

Read-only resumption checks found exactly one `IN_PROGRESS` card, held-out
open count `0`, counted task attempts `0/10`, no repo-owned C922 or gateway
process, no follower-device owner, and no Git index lock. The immutable V03
post-close receipt still binds torque false and no later motion exists.

The six previously named unrelated untracked paths remain preserved. Three
additional externally authored paths are also out of campaign scope and
must not be staged or edited:

- modified `README.md`, SHA-256
  `e62164ad178aaaf047d4bf168b2f04d1a5962241e303b4464fda54f02a8f2e4a`;
- untracked `docs/reference/WORKSPACE_DATA_RELEASE_20260728.md`, SHA-256
  `9402b626d02e44e0ec8dd6f8be7d11871c020704b50738c580bf2cc86dcbfa1e`;
- untracked `docs/reference/WORKSPACE_DATA_RELEASE_20260728.json`, SHA-256
  `9365d5a6fa8216d1463c134495657cd49868044a5fdcbc178910f084b215b499`;
- untracked `scripts/download_workspace_data.py`, SHA-256
  `34119f989d9ab2e55cb551398b53fc57e20c61248952514f0654cf5f33560759`.

This transition authorizes prospective registration design only. A new
acquisition contract, fit/held-out split, candidate family, and exact route
must freeze and pass CPU/fp64 collision/visibility review before camera open,
gateway construction, or motion. Acquisition-v1 held-out remains sealed and
forbidden.

The first post-transition graph test rebuilt the graph successfully but its
assertions still required the former paused pointer and five-revision length:
`2 failed in 0.27s`. The test was updated to require the source-bound
`V04_RESUME` revision while explicitly preserving event IDs `V00` through
`V04`; the fail-closed lineage mutation now targets the new nonempty revision.
Validation attempt 2 passed:

```text
uv run --offline pytest -q tests/test_current_campaign_graph.py
..                                                                       [100%]
2 passed in 0.28s
```
