# Bidirectional Pawn-Push V2 Task Queue

Status: `ACTIVE_V05_FROZEN_REHEARSAL_V2_SINGLE_EXECUTION`

Created: `2026-07-28`

Owner/operator: sole active Codex writer in the live checkout

Checkout: `/Users/kelly/Developer/sim2claw`

Branch: `codex/bidirectional-transfer-goal-loop-20260728`

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

## Consolidated critical path

The 2026-07-28 owner instruction resumes V04 and authorizes this sole writer
to goal-loop through the smallest honest bidirectional proof. The ordered path
is:

1. repair V04's row-zero start exactness with a versioned, hash-bound setup
   bridge while preserving the frozen `716 + 2596` rows and the immutable
   execution-v1 stop;
2. complete the one acquisition-v2 transaction, fit only its six fit targets,
   freeze the bounded rigid robot-to-board candidate, and open the four sealed
   heldouts once;
3. use exactly one acquisition-v3 family if that fit fails, then only the
   bounded masked-static-scene/CAD audit described below after a second
   registration failure;
4. run a sim-only closed-jaw push rehearsal before evaluator freeze;
5. freeze evaluator v2, feasible cases, mappings, hashes, safety rules, and a
   maximum ten-attempt ledger;
6. obtain one admitted REAL->SIM case and one distinct admitted SIM->REAL case;
7. connect admitted evidence to the existing Studio spatial/temporal surfaces
   and belief graph, validate and clean up, then obtain final read-only Fable 5
   defect review.

RoboPose training, EasyHeC expansion, the 24-pose fiducial sweep, SAIL/graph
expansion, learned world-model work, depth restoration, and paid compute are
deferred unless a later recorded gate explicitly activates them.

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
| V04 | `DONE` | Fit and freeze a new registration candidate using fit data only, then open held-out once. | Candidate/family hash freezes before opening held-out; task-relevant held-out error `<25 mm`; frozen pixel/reprojection sanity gate passes; CPU/fp64 scene builds. If unscorable, prospectively redesign/recapture before counted actions. | Frozen candidate `4d08518f...`; heldout PASS receipt `5eaf763b...`; all four scorable/pass; heldout RMS `4.684083 px` and `4.741723 mm`; zero refit. Registration only. |
| V05 | `IN_PROGRESS` | Draft v2 evaluator and maximum-ten case family, then run reset-layout feasibility audit before freeze. | Route/joint/collision/edge/corridor/camera/destination checks pass with documented margins and at least two feasible candidates per direction. Draft defects are repaired before freeze without task outcomes. | Rehearsal-v1 receipt `d4396104...` is an immutable terminal negative with no admitted case. A separately versioned correction may change only the defective jaw/joint-margin semantics before one new frozen run. |
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
  replacement-family recovery. Acquisition-v1 held-out remains prohibited.
  Acquisition-v2, its new six-fit/four-heldout split, rigid candidate family,
  and exact no-contact route are frozen; the CPU/fp64 static reviewer returned
  `CONTINUE`. Commit `f205bcbb097813a0c9050624e3895c9f2065aecb`
  binds and publishes those exact inputs. Capture packet v2 is now frozen but
  commit `9decefa` binds the rebase repair and fresh deterministic review
  SHA-256
  `7dc3e08ff3d0cbea2bdb6ed640aaa5792abea2b0d826967c04a3bae195c00868`
  returned `CONTINUE`. Execution-v1 then stopped before sending its first row
  because the exact target would require forbidden rate limiting, clamping,
  or correction. Torque-off cleanup passed. The owner has now explicitly
  resumed V04 on the sole-writer branch
  `codex/bidirectional-transfer-goal-loop-20260728`. Packet v3 now freezes the
  time-only start bridge with the unchanged arrays. Commit `df5c71d` binds
  packet v3, and fresh deterministic review SHA-256
  `b3ccca0e06549caeb13b6e520e003fd29fde00ae2e9ebab1246744444b69df94`
  returned `CONTINUE`, evidence anchor `100`, with all `13/13` gates true.
  Execution-v2 completed the one reviewed no-contact acquisition-v2
  transaction. All `716 + 2596` exact rows executed byte-identically, all ten
  targets were captured with zero C922 drops, and torque-off cleanup passed.
  Fit-only scorability audit rejected acquisition-v2 before annotation or
  fitting: only one of six fit images exposes both required pink endpoints.
  The four heldouts remain sealed and forbidden. The single allowed
  acquisition-v3 design is active.
- Acquisition-v3 is now prospectively frozen. Its six fit and four separately
  sealed held-out targets keep wrist flex at `-20 deg`, wrist roll at
  `-102.813187 deg`, pan inside the prior fit-visible `[-21,+9] deg` interval,
  and add lift levels `-85/-87/-89/-90 deg`. Static and live motion-free
  reviewers returned `CONTINUE`; exact no-contact capture is authorized only
  after the same immediate live safety checks pass again.
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
- Replacement acquisition-v2 contract SHA-256:
  `b308ef3d24e37893e13c6b28c00f338374ee2a21d84a464c9ccec073bd0b5483`.
  Its new split contains six fit and four sealed held-out hovers, none reused
  from acquisition-v1. The shared family is one normalized projective C922
  camera plus one orientation-preserving robot-to-board yaw/XYZ transform;
  there are no per-pose, joint-zero, board-pose, or scale fit parameters.
- Replacement route-v2 SHA-256:
  `40460c83750f8ea35670498758a5ad5b0e52a31351c957106f37154df6546756`.
  The exact source egress has `716` little-endian float64 rows and action hash
  `a2536181add1aaf901aac5b94929a5a7117974e571354a68abd94b3a361d4bab`.
  Capture/return has `2596` rows and action hash
  `06d531afba308c3582cb67972c735bf963c6cae35df365325e36139ba8eac1c2`.
  Its 10 target holds use a frozen `-60 deg` wrist roll so both distal pink
  endpoints are independently camera-visible.
- Static preview receipt SHA-256:
  `37b73f61d8a1c2124989d42bac16b8fd532ee0f15c385798ac5feed2a6b597e5`.
  All `11/11` gates pass, maximum slew is
  `3.000000000000043 deg/s`, board and pawn clearances have fail-closed lower
  bounds of `80 mm` and `50 mm`, and the minimum predicted C922 image margin
  is `80.359674 px`. Every fixed-tip ray first hits `left_gripper` and every
  moving-tip ray first hits `left_moving_jaw_so101_v1`; maximum observed
  endpoint surface offset is `15.710085 mm` under the geometry-derived
  `20 mm` cap. The reviewer decision is `CONTINUE`, evidence anchor `100`.
- Replacement capture packet SHA-256:
  `f8ae7922fc8df145ec30af625ae587f36f98135c92b8b4cd1fa9e431b87b6d41`.
  It binds the exact `716 + 2596` setup arrays, all ten capture slices, C922
  exact-mode contract and source, fixed-mount token, one sequential owner
  session per target plus return, maximum `2 deg` hold tracking error, exact
  requested/mapped/sent bytes, stop rules, one-use registration transaction,
  and unconditional torque-off. It grants no pawn contact, counted task,
  policy, success, transfer, or training authority.
- Live pre-motion review attempt 1 stopped before emitting a receipt, opening
  a camera, or constructing a gateway. The follower remained torque-off and
  was within `0.118765 deg` of the frozen anchor, inside the `1 deg` rebase
  envelope. The reviewer incorrectly substituted that passive live readback
  into frozen array row zero and then rejected its own byte comparison. The
  repair keeps the committed arrays immutable and checks live-start proximity
  as a separate fail-closed gate.
- Live pre-motion review attempt 2 passed all `12/12` gates with deterministic
  reviewer `CONTINUE`, evidence anchor `100`; receipt SHA-256
  `7dc3e08ff3d0cbea2bdb6ed640aaa5792abea2b0d826967c04a3bae195c00868`.
  Fresh follower start remained within `0.118765 deg` of the frozen anchor,
  torque was false, and the exact array/action hashes matched. The review
  opened no camera or gateway and issued no motion.
- Execution-v1 receipt SHA-256:
  `d17d901f5a18ac7e7fccc4b1c3d45538f290e06d62736c040530648f07197e04`.
  Status is `stopped_safely`; exact error is `Precompiled exact target would
  require rate limiting, clamping, or correction; the current sample was not
  sent.` The camera started before gateway open, the gateway opened, but
  `physical_motion_commanded:false`, source egress executed `0/716` rows,
  capture/return executed `0/2596` rows, no command was sent, camera drops
  were zero, final preflight passed with
  `physical_follower_torque_enabled:false` and
  `device_configuration_rewritten:false`.

Remaining:

- Commit and execute V04's preregistered new-version registration recapture,
  then complete its fit-only
  candidate freeze, and one-time held-out evaluation.
- V05-V15.

Blockers:

- No terminal blocker is established. Execution-v1 exposed a deterministic
  row-zero timing defect: the executor sampled the first frozen target at
  elapsed time `0`, leaving zero gateway slew allowance for the observed
  `0.118765 deg` torque-on settle. The already-frozen `20 Hz` interval gives
  `0.05 s`; under the reviewed `60 deg/s` gateway body limit that admits up to
  `3 deg` without rate limiting. The repair must freeze that time-only pre-row
  bridge in a new packet and must not widen the `1 deg` live-start envelope,
  alter either action array, or send an unreviewed command.

Next action:

- Freeze acquisition-v3 with empirical physical D405-housing occlusion gates,
  endpoint-visible roll geometry, greater height/off-plane diversity, a new
  fit/heldout split, and a CPU/fp64 static reviewer before any second capture.

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

### V04 replacement acquisition/route freeze — 2026-07-28

Before any replacement camera or hardware access, acquisition-v2 froze a new
six-fit/four-heldout split and the
`normalized_projective_camera_plus_planar_robot_board_rigid_v2` family. It
does not reuse acquisition-v1 targets or held-out observations. The six fit
hover model points span singular values
`[105.0108, 54.1699, 7.6828] mm` before the final visibility-driven wrist-roll
revision; the final ten-point exact-midpoint family spans
`[119.5754, 58.9231, 9.8502] mm`, above the frozen `5 mm` smallest-axis gate.

Static-validation attempt 1 returned `5 passed, 2 failed`. This happened
before contract freeze, capture, or motion. It exposed two definition defects:
the line-of-sight probe aimed at an internal midpoint and therefore could not
prove that both annotatable pink endpoints were visible, and an uncapped
MuJoCo mesh-distance query attempted to resolve separation beyond the actual
`80 mm` acceptance threshold and returned an isolated zero despite adjacent
samples above `103 mm` and no contact in the full CPU/fp64 route preview.
Neither result is task evidence and neither threshold was weakened.

The prospective repair requires independent rays to the fixed and moving
distal tip endpoints, each of which must first hit its own named gripper body.
The `20 mm` maximum surface offset is derived from the modeled fixed-jaw
`16.134 mm` collision half-extent plus `3.866 mm`; it cannot admit the former
moving-tip occlusion because a moving-tip ray that first hits the fixed jaw
fails. The wrist roll was frozen at `-60 deg`, and separate pre/post-capture
waypoints rotate at the elevated safe pose before any target traversal. The
clearance evaluator now performs threshold-capped separation queries: a row
with no geometry inside the `80 mm` board or `50 mm` pawn bound records that
bound explicitly as `lower_bound_only:true`; the independent swept-route
contact preview must also remain empty.

Validation attempt 2 passed:

```text
OPENCV_OPENCL_RUNTIME=disabled uv run --offline pytest -q \
  tests/test_bidirectional_pawn_push_v2_registration_acquisition_v2.py \
  tests/test_bidirectional_registration_v2_route.py
.......                                                                  [100%]
7 passed in 8.50s
```

The final deterministic static reviewer returned `CONTINUE`, evidence anchor
`100`, with all `11/11` gates true. The acquisition contract, route, source
egress, capture/return, and static receipt hashes are recorded in V04 and the
live ledger above. No camera opened, no gateway was constructed, no robot
motion or pawn contact occurred, acquisition-v1 held-out remained sealed,
held-out open count remained `0`, and counted attempts remained `0/10`.

During this design interval the external workspace-data owner advanced local
and origin HEAD from `ecab4f8` through `882f398` to `e88e3db`. Those commits
independently adopted the previously external `README.md`,
`docs/reference/WORKSPACE_DATA_RELEASE_20260728.md`,
`docs/reference/WORKSPACE_DATA_RELEASE_20260728.json`, and
`scripts/download_workspace_data.py`. This campaign did not modify or stage
their content. The six original unrelated untracked paths remain preserved.

The material queue transition was immediately source-bound as graph revision
`6`, event `V04_RECAPTURE_FREEZE`, with active node
`checkpoint:v04-recapture-static-gate`; all graph authority flags remain
false. Graph-validation attempt 1 rebuilt digest
`bd1e038fefd813345b02e18c7455531ecc100384e4ed9b022fe806ee3e3b807f`
but one test still asserted the former resume pointer. After updating that
fail-closed expectation, the combined graph/acquisition/route suite passed:

```text
OPENCV_OPENCL_RUNTIME=disabled uv run --offline pytest -q \
  tests/test_current_campaign_graph.py \
  tests/test_bidirectional_pawn_push_v2_registration_acquisition_v2.py \
  tests/test_bidirectional_registration_v2_route.py
.........                                                                [100%]
9 passed in 8.71s
```

The repository runtime does not contain `ruff`; the optional lint invocation
exited before running with `Failed to spawn: ruff / No such file or
directory`. This does not change any hardware or evidence authority.

### V04 replacement capture packet freeze — 2026-07-28

Scoped commit `f205bcbb097813a0c9050624e3895c9f2065aecb` was pushed to
`origin/codex/geometric-microtransfer-20260727` and binds the replacement
acquisition, route, static evaluator, tests, queue, and graph. The only
remaining worktree paths after that push were the six preserved unrelated
untracked paths.

Capture packet
`configs/hardware/bidirectional_pawn_push_v2_registration_capture_v2.json`,
SHA-256
`f8ae7922fc8df145ec30af625ae587f36f98135c92b8b4cd1fa9e431b87b6d41`,
was then prospectively frozen without opening a camera or gateway. It binds
the committed acquisition/route identities, immutable static receipt,
`716 + 2596` exact float64 setup rows, C922 exact-mode identity and fixed
mount, ten sequential target sessions plus return, tracking/stall/camera
stops, no-contact authority, one-use transaction, and unconditional
torque-off. The executor now derives the capture count from the frozen split
and preserves each replacement held-out `opaque_id`; the historical
eight-target packet remains supported and unchanged.

Focused success, forced-stop cleanup, historical-packet, replacement-packet,
route, acquisition, and graph validation passed:

```text
OPENCV_OPENCL_RUNTIME=disabled uv run --offline pytest -q \
  tests/test_bidirectional_registration_v2_capture.py \
  tests/test_bidirectional_registration_v2_route.py \
  tests/test_bidirectional_pawn_push_v2_registration_acquisition_v2.py \
  tests/test_current_campaign_graph.py
.............                                                            [100%]
13 passed in 9.16s
```

No camera opened, no gateway was constructed, no motion occurred, held-out
open count remains `0`, and counted attempts remain `0/10`. The packet still
requires a newly emitted deterministic live review after its own scoped
commit; authority remains false until that review passes.

After the packet tests, the external C922-calibration owner advanced local
HEAD to `afd0f85` and independently committed four of the formerly untracked
calibration paths plus its run log. This campaign did not modify or stage
them. `output/` remains ignored/present and `tools/build_fiducial_sheet.py`
remains the sole visible unrelated untracked path. The packet changes remain
scoped and are based on top of that external commit.

### V04 live review attempt 1 safe stop — 2026-07-28

Capture-packet commit `8922412632f47c279e5594c9ae9cbe0d636ab007`
was pushed and matched origin. Immediately before review there was no Git
lock, no C922 recorder/capture process, no follower-device owner, and no
repo-owned gateway process. Two read-only Studio servers were present and did
not own the C922 or serial gateway. `system_profiler` resolved the exact C922
model and unique ID. Packet and array SHA-256 values rechecked exactly:

- packet:
  `f8ae7922fc8df145ec30af625ae587f36f98135c92b8b4cd1fa9e431b87b6d41`;
- source egress NPY:
  `b2e141f99aa2deedd381d3d666c76c280d5aa5e900d0bcd00a4b49ef6a2453e7`;
- capture/return NPY:
  `27a06d80dae807cf27a8c11dc33194b73c8e5e11825009c9cef0dd97e20c56a1`.

The physical preflight passed with torque false and no configuration rewrite.
Fresh follower start was
`[-8.351648,-106.285714,99.208791,-94.109890,-125.318681,2.612827]`,
whose maximum absolute difference from the frozen anchor is
`0.118765 deg`. Review attempt 1 then stopped with:

```text
RegistrationCaptureV2Error:
frozen setup arrays differ from fresh compile or V02 receipt
```

No review receipt was emitted. Inspection proved that the reviewer had
recompiled row zero from the passive live readback even though the contract
requires the committed expected-anchor array; it then compared that altered
array against the frozen bytes. The fix compiles the immutable expected-anchor
arrays and separately checks the live readback against the frozen `1 deg`
rebase envelope in both review and execution. The packet, action arrays,
thresholds, and route are unchanged. Focused validation passes:

```text
OPENCV_OPENCL_RUNTIME=disabled uv run --offline pytest -q \
  tests/test_bidirectional_registration_v2_capture.py
....                                                                     [100%]
4 passed in 0.37s
```

The failed review opened no camera or gateway, issued no motion, and consumed
no registration transaction or task attempt. Torque remained false, held-out
open count remained `0`, and counted attempts remained `0/10`.

### V04 live review attempt 2 CONTINUE — 2026-07-28

Repair commit `9decefa39758ec190c6a26b4b37b89c08764bb63`
was pushed and matched origin. The next live check again found no Git lock,
C922 recorder/capture process, follower-device owner, or repo-owned gateway
process. The deterministic reviewer emitted
`runs/bidirectional-pawn-push-v2/20260728-v04-registration-recapture-v2/pre-motion-review-v1.json`,
SHA-256
`7dc3e08ff3d0cbea2bdb6ed640aaa5792abea2b0d826967c04a3bae195c00868`.
All `12/12` gates pass; reviewer decision is `CONTINUE`, evidence anchor
`100`. The fresh torque-off follower start is
`[-8.351648,-106.285714,99.208791,-94.109890,-125.318681,2.612827]`.
The exact source-egress and capture/return hashes remain
`a2536181add1aaf901aac5b94929a5a7117974e571354a68abd94b3a361d4bab`
and
`06d531afba308c3582cb67972c735bf963c6cae35df365325e36139ba8eac1c2`.

The review opened no camera or gateway and issued no motion. The graph remains
compact campaign context and does not widen its global authority flags; the
source-bound packet/review pair is the reviewed transaction authority.
Held-out open count remains `0`, counted attempts remain `0/10`, and V04
remains the sole active card.

### V04 execution-v1 stopped safely before first row — 2026-07-28

The execution command began before the owner's merge-pause message arrived.
Its immediate recheck found local/remote HEAD
`17c055d274f421bb011bcddb93810e209ed5b6b2`, no Git lock, no existing
execution directory, no C922 recorder/capture process, no follower-device
owner, and torque false. Packet, review, source-egress NPY, and
capture/return NPY hashes matched their frozen values.

The C922 recorder started before gateway open. The gateway then rejected the
very first frozen source-egress row before sending it:

```text
Precompiled exact target would require rate limiting, clamping, or correction;
the current sample was not sent.
```

Immutable receipt:
`runs/bidirectional-pawn-push-v2/20260728-v04-registration-recapture-v2/execution-v1/execution_receipt.json`,
SHA-256
`d17d901f5a18ac7e7fccc4b1c3d45538f290e06d62736c040530648f07197e04`.
Its exact outcome is:

- status `stopped_safely`;
- gateway opened, camera preceded it, zero camera drops;
- `physical_motion_commanded:false`;
- source egress `0/716` rows, executed action hash `null`;
- capture/return `0/2596` rows, executed action hash `null`;
- no command sent, no pawn or board contact;
- final preflight passed, no configuration rewrite, torque false;
- held-out open count `0`;
- registration transaction produced no observations; and
- counted task attempts remain `0/10`.

This is a no-motion setup rejection, not a physical task attempt, registration
success, or transfer result. The owner ordered an immediate merge pause after
recording it. V04 remains the sole `IN_PROGRESS` card, no new milestone is
started, and no execution retry is authorized.

### V04 owner resume / sole-writer start-bridge design — 2026-07-28

The owner explicitly authorized a new High-reasoning agent to consolidate the
critical path into this existing queue and goal-loop until bidirectional proof
or a genuine receipt-backed safety/authority boundary. Merged `main` was
verified at `98acce5`, including campaign tip `dc1dee3`. The sole writer
created branch `codex/bidirectional-transfer-goal-loop-20260728` from that
merge and preserved unrelated untracked
`tools/build_fiducial_sheet.py` without reading it into campaign evidence.

The workflow audit passed. V04 remains the only `IN_PROGRESS` card,
held-out open count remains `0`, REAL->SIM and SIM->REAL remain `0/0`, and
counted attempts remain `0/10`. The immutable execution-v1 stop remains
authoritative negative evidence.

Inspection localized the stop to row-zero timing rather than an unsafe frozen
route. `execute_registration_capture` established its motion epoch and
immediately requested row zero at elapsed `0`, while the reviewed gateway
correctly required any nonzero difference from its post-hold live pose to be
rate limited. The maximum recorded live-to-frozen delta was
`0.118765 deg`. A single frozen `20 Hz` interval is `0.05 s`, within the
gateway's `0.1 s` bounded control interval and providing up to `3 deg` of
reviewed body slew allowance at `60 deg/s`.

The prospective repair is a separately named, packet-bound,
`time_only_pre_row_bridge` of exactly one `0.05 s` interval. It sends no
command, changes no array, keeps the existing `1 deg` live-start tolerance,
and is excluded from policy, task, and transfer evidence. A new packet and
fresh deterministic reviewer `CONTINUE` are mandatory before any camera or
gateway opens. This transition grants design/test authority only and no
physical-motion authority.

### V04 start-bridge packet freeze — 2026-07-28

Versioned packet
`configs/hardware/bidirectional_pawn_push_v2_registration_capture_v3.json`,
SHA-256
`82aa900dbce4eb7c5bb370b8a31300794e108dcc4c71993fc12bb2af423a5cb8`,
freezes bridge ID
`v04_acquisition_v2_time_only_pre_row_bridge_v1`. It binds exactly
`0.05 s`, zero commands, the existing `1 deg` torque-off live-rebase
envelope, a `3 deg` post-hold-to-row-zero envelope derived from the gateway's
existing `60 deg/s * 0.05 s` constraint, no action-array changes, and explicit
exclusion from policy/task/transfer evidence.

The executor sleeps for the bridge duration only after C922 readiness and
gateway open, validates the post-hold live pose against the frozen envelope,
and then sends the unchanged first row with elapsed time `0.05 s`. The receipt
records actual bridge duration, zero setup commands, and the measured
post-hold-to-first-row delta. Legacy packets remain unchanged.

Focused synthetic validation covers motion-free bridge review and an
execution stopped after the first exact row:

```text
OPENCV_OPENCL_RUNTIME=disabled uv run --offline pytest -q \
  tests/test_bidirectional_registration_v2_capture.py
......                                                                   [100%]
6 passed in 0.47s
```

The synthetic receipt proves the first exact row occurs at `0.05 s`, the
bridge emits zero commands, requested/mapped/sent identity is preserved, and
the forced-stop path closes torque. No live camera or gateway opened and no
physical motion occurred. The packet must be committed before a fresh
deterministic live review; physical execution remains unauthorized.

### V04 start-bridge live review CONTINUE — 2026-07-28

Packet implementation commit
`df5c71d6f29a7ead470ee18d7a7bda8f96d97eac` binds packet SHA-256
`82aa900dbce4eb7c5bb370b8a31300794e108dcc4c71993fc12bb2af423a5cb8`.
The committed packet then produced fresh motion-free review
`runs/bidirectional-pawn-push-v2/20260728-v04-registration-recapture-v2/pre-motion-review-v2.json`,
SHA-256
`b3ccca0e06549caeb13b6e520e003fd29fde00ae2e9ebab1246744444b69df94`.

The deterministic reviewer returned `CONTINUE`, evidence anchor `100`, with
all `13/13` gates true. Fresh follower start was
`[-8.351648,-106.285714,99.208791,-94.109890,-125.318681,2.612827] deg`,
only `0.118765 deg` from the frozen anchor. The review binds the unchanged
`716 + 2596` arrays, ten capture slices, C922 source/mount, `0.05 s`
zero-command bridge, exact-byte requirements, no-contact limits, and
unconditional torque-off.

The pre- and post-review hardware checks passed with torque false,
`device_configuration_rewritten:false`, no Git lock, no serial owner, and no
repo-owned C922/gateway process. The review opened no camera or gateway,
commanded no motion, opened no held-out, and consumed no registration
transaction or task attempt. Physical execution is authorized only after this
transition is committed/pushed and the same live gates are rechecked
immediately.

### V04 acquisition-v2 capture complete / fit-only start — 2026-07-28

The exact committed packet-v3 command completed successfully in
`168.487068 s`. Immutable execution receipt
`runs/bidirectional-pawn-push-v2/20260728-v04-registration-recapture-v2/execution-v2/execution_receipt.json`,
SHA-256
`ce0b1e294c14c1d18a3ceace413dbd2b908bfd3d921474158fa80f0366cd8ae7`,
records proof class
`physical_rgb_no_contact_registration_observation_only`.

- Source egress completed `716/716` rows with planned/executed action SHA-256
  `a2536181add1aaf901aac5b94929a5a7117974e571354a68abd94b3a361d4bab`.
- Capture/return completed `2596/2596` rows with planned/executed action
  SHA-256
  `06d531afba308c3582cb67972c735bf963c6cae35df365325e36139ba8eac1c2`.
- Requested, mapped, and sent bytes are identical; there was no clamp, rate
  limit, correction, retry, assistance, contact, stall, or executor error.
- The time-only bridge emitted zero commands, measured `0.057937 s`, and saw
  `0.118765 deg` post-hold-to-row-zero delta.
- Ten target captures and the return are enclosed by eleven sequential C922
  sessions with zero drops. Maximum scored-hold error is `1.538462 deg`.
- Fit manifest SHA-256 is
  `f338f3598007c83db70f5b3d9e52bd0ad8dc741986b6270cbe339dba75be91ee`;
  sealed heldout manifest SHA-256 is
  `8ffb94790cbf0120c92bfd54a90f128468b022eac0ec57c0249f6a4d403af627`.
- Final and independent fresh preflight prove torque false and no device
  configuration rewrite. Camera/gateway processes and serial ownership are
  closed.

This is no-contact registration observation, not task action or transfer.
Heldout open count remains `0`; REAL->SIM and SIM->REAL remain `0/0`; counted
task attempts remain `0/10`. V04 remains the only `IN_PROGRESS` card and now
authorizes fit-image annotation only. The fit process must not read the
execution receipt's heldout target mapping, sealed heldout directory, or
heldout manifest contents before candidate freeze.

### V04 acquisition-v2 fit scorability rejection / acquisition-v3 trigger — 2026-07-28

Fit-only visual audit
`runs/bidirectional-pawn-push-v2/20260728-v04-registration-recapture-v2/fit-scorability-v2/audit.json`,
SHA-256
`6f9ecbf70c0a2e3f605352ceff6264ba04ce2e2f0733e93786aa9f781d87ba2d`,
binds all six fit-image hashes and no heldout inputs. Only
`v2r2-fit-panm20-wfm10` exposes both distal pink endpoint regions. The two
other `-10 deg` wrist-flex views expose only one endpoint; all three
`-26 deg` views expose none. The physical D405 wrist-camera housing occludes
the missing feature.

The acquisition-v2 MuJoCo visibility gate modeled jaw rays but not the
physical D405 housing, so its `11/11` static pass did not establish empirical
feature scorability. The audit therefore stopped before two-pass endpoint
annotation, board extraction, candidate fitting, or parameter selection.
There are no fit residuals, bound-saturation results, or identifiability
metrics to promote. Candidate creation is false and heldout open count remains
`0`.

This is the first and only acquisition-v2 registration-family failure for the
consolidated fallback. It activates exactly one acquisition-v3 family. V3 must
use fit-only empirical visibility observations, must explicitly model or
exclude D405-housing occlusion, must add height/off-plane diversity, and must
freeze a new split before capture. Acquisition-v2 heldouts remain permanently
sealed and cannot be reused.

### V04 acquisition-v3 static design and packet freeze — 2026-07-28

Acquisition contract
`configs/evaluations/bidirectional_pawn_push_v2_registration_acquisition_v3.json`,
SHA-256
`26f470db40ac666b26b26b4b0bcf3096fbb1a2e4ff9f47173f4f30e2e5fcdbfe`,
and route
`configs/hardware/bidirectional_pawn_push_v2_registration_route_v3.json`,
SHA-256
`779bddd3feeac475d380a564e3be48a728334a885e30b85c975c45ae5ab4b780`,
freeze six fit and four separately sealed held-out targets. All targets keep
the empirically positive v1 fit-only wrist family (`-20 deg` wrist flex,
`-102.813187 deg` wrist roll, pan within `[-21,+9] deg`) and introduce
prospective lift levels `-85/-87/-89/-90 deg`.

The empirical gate binds four v1 fit-only scorable images and the
acquisition-v2 fit-only D405-housing rejection while keeping both generations
of heldouts unopened. The contradicted jaw-only MuJoCo ray remains in the
receipt as a failed non-authoritative diagnostic; it does not replace the
physical fit-only visibility evidence.

Static receipt
`runs/bidirectional-pawn-push-v2/20260728-v04-registration-recapture-v3/static-review-v3/evaluation.json`,
SHA-256
`46efba3a137e9af3e69da5ea4ab0782675c5b004aba72f79fa3d3f806d808d78`,
returned deterministic reviewer `CONTINUE`, evidence anchor `100`, with all
authoritative gates true. The modeled midpoint singular values are
`[113.349,20.483,7.639] mm`; the minimum exceeds the frozen `5 mm` gate.
Predicted image margin is `82.198 px`; board and pawn clearance screens are
at least `80 mm` and `50 mm`; joint limits, final anchor, `3 deg/s` slew, and
no-new/no-external-contact previews pass.

Committed packet
`configs/hardware/bidirectional_pawn_push_v2_registration_capture_v4.json`,
SHA-256
`14d95c677e5cbfb574c9a4130d921c1e63e6c2c8d5d5e96e91240f13972b9145`,
binds exact source-egress action SHA-256
`f3e480e6b89582d51edff3a2b0845aa637103a3dbfe31e26f6865182e25e96f2`
(`715x6`) and capture/return SHA-256
`a006babcd3928bfe3bc6bab37d9bf0c6b9c53930e1f0a1ed2bc8cdd287d218b4`
(`1771x6`). Commits `3fe4feb` and `c9f1ed4` freeze and publish this design.
Focused capture/route tests pass `12/12`. No camera, gateway, or motion was
used; heldout open count and counted task attempts remain zero.

### V04 acquisition-v3 live review CONTINUE — 2026-07-28

The committed packet produced fresh motion-free review
`runs/bidirectional-pawn-push-v2/20260728-v04-registration-recapture-v3/pre-motion-review-v3.json`,
SHA-256
`924652d13e4f7ef7e96c01e6b3a0b16756c209c9acbeeb4d6e3b5f5217fa30f7`.
The deterministic reviewer returned `CONTINUE`, evidence anchor `100`, with
all `13/13` capture gates true. Fresh start was
`[-8.351648,-106.197802,99.208791,-93.846154,-125.142857,2.375297]`,
exactly the frozen anchor.

Independent AVFoundation enumeration found exactly one
`C922 Pro Stream Webcam`, unique ID `0x8310000046d085c`, model
`UVC Camera VendorID_1133 ProductID_2140`, and the bound
`640x480 420v 30.00003 fps` format/range. Pre- and post-review follower
checks passed with torque false and `device_configuration_rewritten:false`.
No serial owner, repo camera/gateway process, or Git lock remained. The review
opened no camera or gateway, commanded no motion, opened no heldout, and
consumed no registration transaction or task attempt.

Physical acquisition-v3 is authorized only after this checkpoint is
committed/pushed and the same identity, process, serial-owner, start-envelope,
torque-off, and no-rewrite gates pass immediately before execution.

### V04 acquisition-v3 terminal stop / masked-static audit trigger — 2026-07-28

The single committed acquisition-v3 transaction stopped fail-closed at target
9. Immutable receipt
`runs/bidirectional-pawn-push-v2/20260728-v04-registration-recapture-v3/execution-v3/execution_receipt.json`,
SHA-256
`6fe2373d4f776c48c8255cc26234ef2301fba3190af9d3dead8204dc7eb8fd0b`,
has status `stopped_safely` and exact error
`target hold did not meet the frozen two-second tracking gate`.

Source egress completed exact rows `715/715`, action SHA-256
`f3e480e6b89582d51edff3a2b0845aa637103a3dbfe31e26f6865182e25e96f2`.
Capture/return stopped after exact prefix `852/1771`, prefix SHA-256
`c2a21896b89322a0c4db15ec6ffe89afd3f68e8abbcb4bfdbc6c4d6bddfb8744`.
The target-9 scoring tail first row had `2.021978 deg` maximum tracking error,
exceeding the frozen `2.0 deg` gate by `0.021978 deg`; no threshold was
changed and no retry is authorized. The earlier shell full-HEAD string typo
stopped before camera/gateway/motion and consumed no budget.

Eight targets closed under exact C922 identity/mode/mount with zero drops:
four of six fit targets and all four separately sealed heldouts. The
incomplete fit manifest SHA-256 is
`341db2264aa3ee486c6cdc4b61330dabe8b376f3a848aea87b550c4aa0c47537`;
the still-sealed heldout manifest SHA-256 is
`b48d47d2606d9fbecf9df42de4188993def21592d57cdd8ed15db4b0c71a9c7e`.
The incomplete split is ineligible for candidate fitting. Heldouts remain
unopened and cannot be substituted for the missing fit targets.

Torque-off cleanup and an independent preflight passed; no camera/gateway
process, serial owner, configuration rewrite, or Git lock remained. The arm
is torque-off at
`[7.208791,-85.538462,99.472527,-20.087912,-103.340659,2.375297]`
because the stop occurred before the frozen return. No pawn contact or task
action occurred. REAL->SIM and SIM->REAL remain `0/0`; counted task attempts
remain `0/10`.

The one V3 registration transaction is consumed. V04 now activates only the
bounded masked-static-scene/CAD audit from the consolidated critical path.
That audit may use fit-only completed images and existing static/CAD evidence,
must not read heldout inputs, and grants no fit, simulator promotion, physical
motion, task action, or transfer authority.

### V04 fit-only masked-static/CAD diagnostic complete — 2026-07-28

Frozen diagnostic contract
`configs/evaluations/bidirectional_pawn_push_v2_masked_static_cad_diagnostic_v1.json`,
SHA-256
`26ff32aaf5d95ed5255d806a7f8ef859915280ee7ef5c9930c6e148508ce7ffa`,
binds exactly the four completed fit images, their fit receipts, the joint
ledger, the compiled CAD candidate, and the older rejected fit-only camera
diagnostic. The execution receipt is hash-checked for identity but its content
is not read. Every bound path containing `heldout` fails closed. Heldout open
count remains `0`.

Deterministic receipt
`runs/bidirectional-pawn-push-v2/20260728-v04-registration-recapture-v3/masked-static-cad-diagnostic-v1/receipt.json`,
SHA-256
`8e2bb5af0646e77dee2106e50e25fce84298b59d78e93798f05bf306c5c4c880`,
has status `diagnostic_complete`. Both physical pink endpoints are visible and
independently annotated in all four eligible fit images; maximum pass
disagreement is `1.414214 px`.

The masked board/background is internally stable: across the three
reference comparisons, maximum post-homography residual is `0.267353 px` RMS
and `0.695752 px` maximum. One frame has a `2.647810 px` median global raw
shift, but its post-warp residual is only `0.171990 px` RMS and `0.695185 px`
maximum. This supports a small whole-image camera shift, not moving board
geometry inside the masked region.

The target-9 stop is isolated to the scoring schedule. The first frozen score
row was `2.021978 deg`; row `813`, only `0.003232 s` later, was
`1.934066 deg`, and every remaining observed row stayed within the unchanged
`2.0 deg` gate through a final `0.703297 deg` error. The frozen 40-row score
tail spans only `1.468962 s`, failing the contract's true `>=2.0 s`
stationary requirement even though it was labeled a two-second hold.

The older rejected v1 fit-only camera does not make the current compiled
jaw/wrist transform coherent after a best 2D translation:
translation-corrected midpoint RMS is `13.380437 px` against the frozen
`8 px` diagnostic gate, and maximum pairwise motion-delta error is
`29.849916 px` against `15 px`. Because that camera has no admission
authority, this is a targeted counterexample rather than a metric CAD verdict.
It prevents silently treating a longer wait as sufficient registration proof.

The next bounded action is prospective design only: freeze a new versioned
registration acquisition that preserves the empirically visible wrist family
and unchanged `2 deg` tracking gate, starts scoring only after tracking enters
gate, and accepts a hold only when its monotonic-time scored interval is at
least `2.0 s`. The candidate must retain one shared rigid robot-board
correction and enough prospective fit diversity to adjudicate the transform;
it must not admit the rejected v1 camera or reuse V3 images/heldouts for
admission. This diagnostic grants no camera, gateway, motion, heldout, task,
or transfer authority.

### V04 acquisition-v4 true-time static route CONTINUE — 2026-07-28

Fresh acquisition contract
`configs/evaluations/bidirectional_pawn_push_v2_registration_acquisition_v4.json`,
SHA-256
`605f8973553e14d488dd43a5aab51e2b6915215553033878aba6a2577d0e01da`,
freezes six new `v2r4` fit targets and four new separately sealed heldouts.
No V3 target ID, image, receipt, or heldout can be used for candidate
admission. The empirical fit-only endpoint-visible wrist family and the
physical D405-housing occlusion counterexample remain bound. Pan stays inside
`[-21,+9] deg`, wrist flex/roll remain `-20/-102.813187 deg`, and lifts span
four levels from `-85` through `-90 deg`.

Route
`configs/hardware/bidirectional_pawn_push_v2_registration_route_v4.json`,
SHA-256
`a18e263a380f091ae98c84c77d7da5e0bfe4a4210dada7ce7d5012113c1b4d0b`,
uses the V3 postflight pose
`[7.208791,-85.538462,99.472527,-20.087912,-103.340659,2.375297]`
as a separately hash-bound torque-off start and return anchor. The V3 safe
stop grants pose evidence only, not image, candidate, heldout, task, or
transfer evidence.

The route freezes `71` identical rows per target as a hard upper bound, but
rows never define hold validity. Runtime mode `monotonic_true_time_v1`
resets its deadline after each camera-owner transition, requires at least
`0.5 s` of unscored monotonic settle, then at least `2.0 s` continuously
inside the unchanged `2.0 deg` gate. Total hold is bounded by `71` rows and
`3.6 s`; inability to enter, stay within, or complete the true-time window
fails closed.

Static receipt
`runs/bidirectional-pawn-push-v2/20260728-v04-registration-recapture-v4/static-review-v4/evaluation.json`,
SHA-256
`f407a89d939c1be8353d36eed1602056225139d1bcf1109876a7ca89fb4f95b3`,
returned deterministic reviewer `CONTINUE`, evidence anchor `100`, with all
authoritative gates true. Source egress is `123x6`, `6.10 s`, action SHA-256
`2229c16f28aa09bde94b021ff5f9cbde44087d26da4b844cca7b521bd347d424`.
Capture/return is `1274x6`, `63.65 s`, action SHA-256
`80d558d3c179582b4927a59641b6946a55a0ccaff2fbf11416462a5c0f5eb0ef`.
Maximum commanded slew is `3.000000000000114 deg/s`; modeled board and pawn
clearance lower bounds are `80 mm` and `50 mm`; predicted reference image
margin is `86.537645 px`; modeled target midpoint singular values are
`[115.296,18.092,7.341] mm`. Joint reach, collision/contact previews,
empirical visibility family, target count/diversity, and exact torque-off
anchor all pass.

Focused route and true-time capture tests pass `15/15`. No camera, gateway,
or physical motion was used. The only active action is to bind the exact
arrays and true-time contract into a new packet, then run a fresh motion-free
live review before any possible V4 execution.

### V04 acquisition-v4 exact packet freeze — 2026-07-28

Packet
`configs/hardware/bidirectional_pawn_push_v2_registration_capture_v5.json`,
SHA-256
`5ba5bc38f7b72d670da6dce3b7b193f31a4750bc2c63b25428284be46e075db5`,
binds the fresh acquisition contract, static `CONTINUE` receipt,
non-promoting diagnostic lineage, exact C922 identity/mode/mount, one-use
registration transaction, and exact `2229c16f...` / `80d558d3...` arrays.

The packet makes monotonic host time authoritative: each camera transition
resets the scheduler deadline, the first `0.5 s` is unscored, the scored
window must remain inside the unchanged `2 deg` gate for at least `2.0 s`,
and the hold fails closed after at most `71` rows or `3.6 s`. Exact requested,
mapped, and sent bytes remain required. Pawn, board, and table contact,
controller changes, task action, policy evidence, and transfer claims remain
forbidden. Every exit requires torque-off and a fresh torque-off postflight.

Focused capture tests pass `10/10`. Packet construction opened no camera or
gateway and commanded no motion. The only active action is a fresh
motion-free live review of device identity, current start, exact arrays,
true-time binding, process/serial ownership, configuration integrity, and
torque-off state.

### V04 acquisition-v4 live review CONTINUE — 2026-07-28

Fresh motion-free review
`runs/bidirectional-pawn-push-v2/20260728-v04-registration-recapture-v4/pre-motion-review-v4.json`,
SHA-256
`d207712ebd545729acd6961b588f8934a799f01a384069e9486113355e62797b`,
returned deterministic
`deterministic_registration_capture_pre_motion_reviewer` decision
`CONTINUE`, evidence anchor `100`. All `14/14` review gates pass, including
the new authoritative true-time hold binding.

The fresh follower pose exactly equals the frozen torque-off anchor:
`[7.208791,-85.538462,99.472527,-20.087912,-103.340659,2.375297]`.
Follower port is `/dev/cu.usbmodem5B3D0406411`, calibration SHA-256 is
`192404b6d3c1337495d69649969459aa9d3f66816cd916c67da2588815e93ec4`,
torque is false, and `device_configuration_rewritten` is false.

A separate observer-only AVFoundation enumeration found exactly one
`C922 Pro Stream Webcam`, unique ID `0x8310000046d085c`, model
`UVC Camera VendorID_1133 ProductID_2140`. Bound format/range `16/0` remains
`640x480`, `420v`, `30.00003000003 fps`. No C922 owner, registration gateway
process, serial owner, or Git index lock remained after review.

This review opened no camera stream or gateway and commanded no motion. The
next operation is the single V4 no-contact registration transaction:
`123` exact egress rows followed by `1274` exact capture/return rows, ten
fresh sequential C922 target sessions, and a return to the reviewed anchor.
Maximum slew is `3 deg/s`; pawn/board/table contact and task action remain
forbidden. The runtime must fail closed on identity, camera, tracking,
true-time, stall, contact, or exact-byte mismatch and torque off on every
exit. Physical execution remains paused for explicit acknowledgement of this
committed/pushed pre-motion notice.

### V04 acquisition-v4 physical capture complete — 2026-07-28

The explicitly acknowledged single V4 no-contact registration transaction
completed successfully. Immutable receipt
`runs/bidirectional-pawn-push-v2/20260728-v04-registration-recapture-v4/execution-v4/execution_receipt.json`,
SHA-256
`7fee16d78479c467b9084e49bfc8520fdae5aef04d00dc72bcd3be9f49515d44`,
has status `completed_no_contact_registration_capture` and `error:null`.

Source egress completed exact `123/123` rows with action
`2229c16f28aa09bde94b021ff5f9cbde44087d26da4b844cca7b521bd347d424`.
Capture/return completed exact `1274/1274` rows with action
`80d558d3c179582b4927a59641b6946a55a0ccaff2fbf11416462a5c0f5eb0ef`.
Requested, mapped, and sent bytes are identical.

All ten true-time holds passed. Observed total hold spans were
`3.491166–3.506415 s`; unscored settles were `0.500161–0.555660 s`; scored
windows were `2.000008–2.051200 s`. Maximum absolute tracking errors were
`0.527473–0.890110 deg`, all below the unchanged `2 deg` gate. There were
eleven sequential C922 sessions including return, with zero drops.

The six-member fit manifest SHA-256 is
`71f704ee95a2c1966f23f1ff96db04d6448bb409a86b209ea54b06e25e9f1f46`;
the four-member opaque sealed-heldout manifest SHA-256 is
`0116025742193193a73c6060335ccfb36f9a7123c43bd82157eb41b58f923bca`;
the joint ledger SHA-256 is
`32e623dc0d8ec219cdb329b79cdd2a8647ab4f0ba597af72606cf32d8de90f9f`.
Heldout open count remains `0`.

Torque-off postflight passed at
`[6.593407,-85.538462,99.472527,-20.087912,-103.340659,2.375297]`,
with no device configuration rewrite. No camera/gateway process, serial
owner, or Git lock remained. No pawn, board, or table contact or task action
occurred; counted task attempts remain `0/10`.

The active operation is fit-only: create two independent annotations for
both physical endpoints in each of the six fit images, freeze the annotation
hash, fit only the preregistered shared projective-camera plus one rigid
robot-board yaw/XYZ correction, and apply every frozen fit gate. The fit
process must not read the execution receipt, sealed manifest, or heldout
directory. Heldouts may open together exactly once only if the candidate
passes every fit gate and is hash-frozen first.

### V04 fit-only rigid candidate independently admitted for one sealed open — 2026-07-28

Fit-only annotations are frozen in
`configs/evaluations/bidirectional_pawn_push_v2_registration_fit_annotations_v4.json`,
SHA-256
`2a22f21601ed8cafccdee1f2666ead7b9c194ab1af091610082597238dffe5b3`.
All six fit images contain both physical pink jaw endpoints. Two annotation
passes have maximum tip disagreement `0.707107 px` and maximum midpoint
disagreement `0.559017 px`. The 25-point board lattice is generated through
one projective homography from the prior fit-only playing-corner seed; its
small residual is projective consistency and is not an independent current
board remeasurement.

The frozen shared projective-camera plus rigid robot-board yaw/XYZ candidate
is
`runs/bidirectional-pawn-push-v2/20260728-v04-registration-recapture-v4/fit-rigid-v4/candidate.json`,
SHA-256
`4d08518f3d8d6885fb184a93f9d7639ff017a76074a65e9ebedcd7c9d2a3739c`.
Immutable fit receipt SHA-256 is
`eef26fd6ea349070fc7d40094b6ec09753464be467071ff3c66fed3c870848ca`.
All `13/13` fit checks pass: board RMS/max are `0.039779/0.062698 px`,
hover RMS/max are `2.927792/4.926105 px`, and task-plane RMS/max are
`3.007454/5.493515 mm`. The refinement Jacobian is `62x15`, rank `15`,
condition number `624330.43`.

Independent optimizer-free review receipt
`runs/bidirectional-pawn-push-v2/20260728-v04-registration-recapture-v4/fit-rigid-v4/independent_review.json`,
SHA-256
`2020d906ea27f8e4c4e3b405c6dd1d0ab6237168f9e689ebed28c81bb9633b31`,
rederives the metrics and Jacobian without fitting. It passes all `11/11`
checks and returns `CONTINUE_TO_SINGLE_SEALED_HELDOUT_OPEN`.

The fitted robot-board translation is
`[126.674204,-107.533152,100.000000] mm` with yaw `17.090982 deg`.
The Z value exactly saturates the unchanged `+100 mm` bound. This is an
explicit extrapolation/identifiability risk, not an automatic threshold
expansion or promotion. All four frozen heldouts must open together exactly
once and pass the unchanged per-heldout and aggregate reprojection and
task-plane gates with this exact candidate and zero refit.

Heldout content remains unread and heldout open count remains `0`. No camera,
gateway, physical motion, task action, simulator promotion, or transfer claim
is authorized by this fit-only admission. The next action is to commit and
push this exact fit/reviewer state, verify clean HEAD lineage, then perform
the single all-four sealed heldout evaluation.

### V04 single-open heldout gate preregistered — 2026-07-28

Prospective contract
`configs/evaluations/bidirectional_pawn_push_v2_registration_heldout_v4.json`,
SHA-256
`be9d0c5366d6cbeff193e3324c7283614993dd79bc1bd960e340fef9a80ebe4e`,
binds candidate `4d08518f...`, fit receipt `eef26fd6...`, independent
review `2020d906...`, the four expected opaque members
`heldout-r4-01` through `heldout-r4-04`, and the sealed manifest SHA-256
`0116025742193193a73c6060335ccfb36f9a7123c43bd82157eb41b58f923bca`.

The evaluator may read the sealed manifest once and each raw member image
once, together in one transaction, to create a single derived 2x2 annotation
surface. Any existing marker or output fails closed. It freezes per-member
and aggregate reprojection gates at `<=8 px`, per-member and aggregate
task-plane gates at `<25 mm`, requires all four members to be scorable and
pass, and forbids candidate refit, camera/rigid updates, post-open threshold
changes, or Z-bound expansion.

The preregistration commit is `fa9b18e`. Focused fit, independent-review, and
heldout-contract tests pass `4/4`. At this checkpoint no heldout manifest or
pixel has been read, no open marker/output exists, and heldout open count
remains `0`. The graph open-authority checkpoint must be committed and pushed
before the one all-four open.

### V04 first heldout open failed closed before pixel access — 2026-07-28

The committed `a6106ff` one-open command read the sealed manifest once and
then failed before reading any raw image because the intentionally opaque
member schema has no top-level `image_path`. Immutable failure receipt
`runs/bidirectional-pawn-push-v2/20260728-v04-registration-recapture-v4/fit-rigid-v4/heldout_open_failure_v1.json`,
SHA-256
`54017f1facb2e1e38ab01f78c77134522f74552eabbd46d847d3cace50252ef4`,
records exact `KeyError: 'image_path'`, cumulative manifest reads `1`, raw
image reads `0`, heldout pixel content unread, and no marker, receipt,
contact sheet, evaluation, or heldout output root.

The candidate remains `4d08518f...`; no candidate refit, camera/rigid
parameter update, threshold update, Z-bound expansion, motion, or task action
occurred. This is a consumed manifest-only access and must not be represented
as the successful one-pixel-open transaction. A separately committed,
independently reviewed recovery protocol is required before any additional
manifest or pixel access.

### V04 versioned heldout pixel-open recovery independently admitted — 2026-07-28

Recovery contract
`configs/evaluations/bidirectional_pawn_push_v2_registration_heldout_recovery_v4.json`,
SHA-256
`cb5de6f91d240c6683ad5c4f29c1439fadaf4d49b21bc77cbbedcca87ffa217e`,
binds failure receipt `54017f1f...`, original contract `be9d0c53...`,
candidate `4d08518f...`, fit receipt `eef26fd6...`, fit review
`2020d906...`, the same four opaque members, the same sealed manifest, and
the same annotation and evaluation thresholds.

The corrected parser is hash-frozen at
`src/sim2claw/bidirectional_registration_rigid_heldout.py`, SHA-256
`aa1671f3105c681ff2e1396880c292f12e6fb8778c359bf6999fabc94007e787`.
It derives each sealed path from the capture source's reviewed rule:
`manifest parent / heldout-sealed / opaque_id / selected.png` and
`capture_receipt.json`. The recovery permits exactly one additional manifest
read, requires cumulative manifest reads `2`, and exactly one raw-image read
for each of all four members into one contact sheet. It preserves zero refit,
zero parameter/threshold update, and no Z-bound expansion.

Independent motion-free/content-free recovery review receipt
`runs/bidirectional-pawn-push-v2/20260728-v04-registration-recapture-v4/fit-rigid-v4/heldout_recovery_review_v1.json`,
SHA-256
`23357b14fbca8f9663864281caffbc9595a23dbb812c50799f8217dc8b2873a1`,
returns `CONTINUE_TO_VERSIONED_SINGLE_PIXEL_OPEN`; all `14/14` checks pass.
Focused heldout/fit/review tests pass `5/5`. No additional manifest read or
raw pixel access occurred during design or review. Cumulative manifest reads
remain `1`; heldout pixel open count remains `0`. The recovery and graph
authorization must be committed/pushed before the single recovery execution.

### V04 frozen registration heldout PASS — 2026-07-28

The committed versioned recovery opened all four heldout pixel sets together.
Open marker SHA-256 is
`cbe783d8fddb4299af6cf930a50f7b074e3c05a5b12def473244ef8d1cefaef8`;
open receipt SHA-256 is
`e35cf89214543c0ad47b11abb254a4aeec72a695eb3f0f1dcf7e50c6a2278607`;
the sole derived contact-sheet SHA-256 is
`9533dde5a16ac29d49b5aef76b210f733f6e40442d49677975c4129af014caa2`.
Cumulative manifest reads are exactly `2`: one failed manifest-only access and
one authorized recovery read. Heldout pixel open count is exactly `1`, with
one raw-image read per member.

The four member image SHA-256 values are, in opaque-ID order:

- `heldout-r4-01`: `e6d6424db945bc5ee36129b369c6f19e0262a75e7bca1e1a6895c79d3f7944cc`
- `heldout-r4-02`: `15d9b8b18b576d5ceda7696f6bbc8422d1b7ef56edaddcfcf9f9c73a8ec471a6`
- `heldout-r4-03`: `9a0755baa99e2e9a692894bcb594d3a7ec8032bc889d4d052a229816c8b37931`
- `heldout-r4-04`: `b739e114de6eae544cc56230a44374a24bb9323f64f450926c1041075d50ec53`

Two-pass derived-surface annotations are frozen in
`configs/evaluations/bidirectional_pawn_push_v2_registration_heldout_annotations_v4.json`,
SHA-256
`654b32fbe4dbb35096d9ed361e574f92a563d9241c0d434a9c756df06db2105d`.
No raw image was reopened for annotation.

Zero-refit evaluation receipt
`runs/bidirectional-pawn-push-v2/20260728-v04-registration-recapture-v4/heldout-rigid-v4/evaluation_receipt.json`,
SHA-256
`5eaf763b7f5beec9be8c38c61693ad0e5cd868cab7984853b54e417a690311f0`,
has status `registration_heldout_pass`. Per-member reprojection errors are
`[6.471232,5.222237,2.760176,3.315923] px`; per-member task-plane errors are
`[7.104333,4.539534,2.305403,3.679939] mm`. Aggregate RMS/max are
`4.684083/6.471232 px` and `4.741723/7.104333 mm`. All four members are
scorable, all four pass, and all seven aggregate/identity/open-count checks
pass against unchanged `<=8 px` and `<25 mm` gates.

Candidate SHA-256 remains
`4d08518f3d8d6885fb184a93f9d7639ff017a76074a65e9ebedcd7c9d2a3739c`.
There was no refit, camera/rigid update, threshold change, or Z-bound
expansion. V04 closes as accepted heldout camera/robot registration only. It
does not establish pawn contact, displacement, task success, simulator
promotion, physical transfer, or bidirectional transfer. REAL->SIM and
SIM->REAL task attempts remain `0/0`; counted physical task attempts remain
`0/10`.

V05 activates only a deterministic sim-only straight closed-jaw push
rehearsal using the accepted registration candidate. It must test feasible
rank-3-ward primitives, jaw/stroke/contact geometry, pawn fully off source,
exclusions, reach/collision/camera margins, and robustness without consuming
or using any physical task outcome. The evaluator and physical task packet
remain unfrozen until this rehearsal identifies one exact case family.

### V05 rehearsal-v1 immutable terminal negative — 2026-07-28

The frozen bounded grid was executed exactly once. Its authoritative receipt
is
`runs/bidirectional-pawn-push-v2/20260728-v05-sim-rehearsal-v1/receipt.json`,
SHA-256
`d43961040e2aabac115ff2355a48ff75a7db07a990ccd2a335465c250300836c`.
It reports `sim_rehearsal_reject`, no passing/admitted case, no candidate
refit, no task outcome used for design, no physical motion, and zero physical
task attempts. This verdict is terminal for rehearsal-v1 and will not be
reinterpreted after observing its results.

Every compiled cell reported `minimum_joint_limit_margin_rad = 0` because the
declared closed-jaw target `-0.174533 rad` is the modeled gripper lower stop,
while the v1 implementation applied the contract's `2 deg` joint-margin gate
to all six joints. This is a preregistration evaluator-design defect: the
intended exact lower-stop jaw and the generic margin gate cannot both pass.
It is not evidence of task transfer or physical success.

The complete 8-case by 3-height by 3-stroke outcome matrix is below. Each
cell is `CR` for compile rejection at the frozen IK gate, or `D<n>` where
`n` of the five frozen robustness replays passed all dynamic contact,
progress, exclusion, collision, and camera checks. Every `D<n>` cell still
failed the v1 static jaw-inclusive margin gate, so none is admitted.

| Case | 18 mm: 90/105/120 mm | 24 mm: 90/105/120 mm | 30 mm: 90/105/120 mm |
|---|---|---|---|
| `R2S_G2_G3` | `CR / CR / CR` | `CR / CR / CR` | `CR / CR / CR` |
| `R2S_A2_A3` | `D4 / D4 / D5` | `D4 / D5 / D5` | `D5 / D5 / D5` |
| `R2S_D1_D2` | `CR / CR / CR` | `CR / CR / CR` | `D0 / D0 / D0` |
| `R2S_B1_B2` | `D5 / D5 / D5` | `D2 / D2 / D2` | `D0 / D0 / D0` |
| `S2R_E2_E3` | `D5 / D5 / D5` | `D5 / D5 / D5` | `D5 / D5 / D5` |
| `S2R_H1_H2` | `CR / CR / CR` | `CR / CR / CR` | `CR / CR / CR` |
| `S2R_F1_F2` | `CR / CR / CR` | `CR / CR / CR` | `CR / CR / CR` |
| `DIAGNOSTIC_C2_C3` | `D5 / D5 / D5` | `D1 / D2 / D3` | `D2 / D3 / D3` |

The receipt contains every per-variant measurement and check. The strongest
recommendable dynamic-only families were:

- `R2S_A2_A3`: five-of-five robustness at `120/18`, `105/24`,
  `120/24`, and all three `30 mm` cells; worst signed progress among those
  cells was `36.575142 mm`.
- `R2S_B1_B2`: five-of-five robustness at all three `18 mm` cells; worst
  signed progress was `79.467306 mm`.
- `S2R_E2_E3`: five-of-five robustness at all nine cells; worst signed
  progress was `39.399419 mm`.
- excluded diagnostic `C2_C3`: five-of-five only at all three `18 mm` cells
  and remains ineligible for recommendation.

The genuine non-jaw failures remain negative evidence: `G2`, `H1`, and `F1`
compile-rejected all nine cells at the unchanged IK gate; `D1` compile-rejected
six and dynamically rejected three with excluded contacts/displacement and
insufficient progress. Across compiled robustness replays, `58` failed the
off-source progress gate and `15` each failed excluded-contact and
excluded-displacement gates. Camera, selected-contact, and new-collision
checks had zero failures.

The only authorized next action is a separately versioned prospective
contract/evaluator. It must preserve the exact cases, grid, scene,
registration, collision, task, exclusion, camera, and robustness rules. Its
sole semantic correction is: apply the unchanged `2 deg` limit margin to the
five arm joints, while requiring the jaw to equal the declared closed
lower-stop target within an explicit tolerance and remain within the
simulator/hardware bounds. The correction must be committed and pushed before
one rerun. Physical authority remains false.

### V05 rehearsal-v2 prospective correction freeze — 2026-07-28

The versioned contract is frozen at
`configs/evaluations/bidirectional_pawn_push_v2_sim_rehearsal_v2.json`,
SHA-256
`d57fc89a5874d630536ae6f981b78988c6da40bfb8934fee78ab2cfc02ac847f`.
Its evaluator is
`src/sim2claw/bidirectional_pawn_push_v2_sim_rehearsal_v2.py`, SHA-256
`69ce7fe8d16dd3371bf4ce03c7c14d509da92f5e1ca31aa9dd91d6682810de7c`;
the unchanged v1 base evaluator remains bound at
`9be8be092653ea923a6e987e52f3cc4bd7697ef93d38d891681b379f1953e8c9`.
Focused equivalence and binding tests pass `4/4`.

The contract mechanically proves equality to rehearsal-v1 for all eight
cases, nine height/stroke cells per case, five robustness variants, action
synthesis target and timing, MuJoCo scene and numeric mode, accepted
registration, contact/progress/exclusion/collision/camera rules, selection
rule, and false authority. The unchanged `2 deg` margin now applies only to
the five arm joints. The jaw has three explicit checks:

- every action row equals the unchanged `-0.174533 rad` closed target within
  `1e-12 rad`;
- the target lies within the compiled MuJoCo jaw bounds with only `5e-6 rad`
  source-rounding tolerance; and
- the target lies within the candidate manifest's frozen physical
  `0..100 percent` jaw mapping with the same `5e-6 rad` tolerance.

The tolerance covers the frozen transform's three-microradian serialized
offset difference (`-0.174530` mapped physical lower stop versus
`-0.174533` MuJoCo lower stop); it does not change any action value, bound,
grid cell, or task gate. Rehearsal-v2 may now execute this identical 72-cell
grid exactly once. No physical authority is granted.
