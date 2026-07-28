# Bidirectional Pawn-Push V2 Task Queue

Status: `ACTIVE_V02_STATIC_ROUTE_VISIBILITY_PROOF`

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
| V02 | `IN_PROGRESS` | Prove hover poses and visibility using CPU/fp64 simulation and static camera projections/images. | Every proposed target passes joint limits, self/table/board/pawn clearance, no-contact height, slow-path preview, C922 field of view, simultaneous gripper/board visibility, and guaranteed return/torque-off logic. Reviewer decision `CONTINUE`. No motion. | In progress. |
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

- V02 is the only active card.
- Robot motion is unauthorized through V02.
- Counted actions do not exist.

Completed:

- Owner authorized the separate v2 successor campaign on `2026-07-28`.
- V1 is preserved and remains non-promoting.
- V00 completed read-only. The live C922, SO-101 buses, torque state,
  processes, v1 hashes, and candidate hover geometry were inventoried without
  motion.
- V01 froze the first v2 registration acquisition contract before any
  authoritative capture or motion.

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

Remaining:

- Complete V02 exact static route, visibility, and return proof.
- V03-V15.

Blockers:

- No terminal blocker is established. Motion remains deliberately gated.
- The live source pose has modeled folded-arm self-overlap and the prior elbow
  corridor has a physical stall history. V02 must prove a source-only egress,
  every hover transition, and a collision-free return to a previously
  demonstrated torque-off anchor. Preliminary CPU search found such a return
  with elbow no lower than `96.558819 deg`; this is not yet frozen or
  authorized.

Next action:

- Compile exact setup/hover/return arrays from a fresh read-only rebase,
  evaluate every row in CPU/fp64 for joint limits and external clearances,
  render/score C922 visibility proxies, and emit a deterministic V02 reviewer
  decision. No gateway execution.

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

V02 is the only active card. Robot motion and counted actions remain
unauthorized; attempts remain `0/10`.
