# Bidirectional Pawn-Push V2 Goal Loop

## Mission

Autonomously complete the smallest honest, camera-verifiable bidirectional
straight pawn-push proof by closing the causal chain from exact action through
joint/link response, contact, planar object response, and task consequence.
Stop only at a genuine receipt-backed safety or authority boundary after safe
in-scope alternatives are exhausted.

## Source of Truth

1. Latest owner instruction.
2. `AGENTS.md`.
3. `docs/autonomous-workflow/causal-closure-successor-task-queue-20260728.md`.
4. The immutable predecessor queue
   `docs/autonomous-workflow/bidirectional-pawn-push-v2-task-queue-20260728.md`.
5. `docs/autonomous-workflow/bidirectional-pawn-push-v2-current-graph.json`.
6. Immutable camera, gateway, simulator, evaluator, action, and cleanup
   receipts.
7. `GOAL.md`, repository tests, and workflow protocols.
8. Advisory Fable output, which never overrides repository evidence.

The causal-closure successor queue is the sole active task list. The
predecessor v2 queue remains immutable authority for its terminal results.

## Intended Outcome

- At least one admitted REAL->SIM case: camera-owned physical consequence
  first, then byte-identical canonical little-endian float64/40 Hz replay in
  CPU/fp64 MuJoCo, with both outcomes passing the frozen evaluator.
- At least one distinct admitted SIM->REAL case: simulator consequence and
  robustness evidence first, then one safety-reviewed physical execution of
  the frozen identical bytes with C922-owned success.
- Every failure remains in its direction-specific denominator and the total
  physical budget does not exceed ten cases.

## Acceptance Criteria

- One preregistration commit predates every counted task action.
- Registration fit and sealed-heldout gates pass exactly as frozen in the
  queue.
- `ObservableEpisode.v2-min` preserves exact actions, timestamps, joint/link
  state, board-plane object state/covariance, contact/motion events, outcome,
  and explicit missingness.
- The four canonical seeded actions complete their frozen simulator
  consequence screen only after the v1 stock-range defect is closed and a
  calibrated-range v2 static receipt admits their exact hashes.
- The physical/model mapping receives a gauge-fixed, held-out-reviewed
  approval before any physical task packet.
- Evaluator ID/SHA, case list, mappings, scene, setup actions, task actions,
  stop rules, and camera thresholds are frozen before counted motion.
- Requested, mapped, and sent task bytes are identical; there is no clipping,
  retiming, offset, IK repair, assistance, correction, retry, or state forcing.
- C922 owns physical outcomes; CPU/fp64 MuJoCo owns simulator outcomes.
- At least one distinct complete success exists in each direction.
- Studio exposes synchronized spatial and temporal evidence, direction-specific
  numerators/denominators, failures, hashes, proof class, and limitations.
- After all implementation/evidence cards pass, the complete package receives
  an adversarial review in the existing project Fable thread. Every material
  recommendation is implemented or dispositioned with repository evidence,
  and the updated result returns to Fable for a final defect check.
- Tests, workflow audit, torque/process/camera/gateway cleanup, Brev cleanup,
  scoped push, graph update, and the CC13--CC15 Fable feedback loop complete.

The only final capability claim is the narrow preregistered bidirectional
straight pawn-push claim recorded in the queue.

## Evidence Standard

Before closing any card, record changed paths, commands, tests, immutable
receipts and hashes, reviewer decision, physical/camera/torque state, attempt
ledger, limitations, and next gate in the v2 queue and graph. Simulation,
registration, physical observation, task outcome, and transfer remain
separate proof classes.

## Decision Status

Confirmed:

- The predecessor V2 campaign is terminal without task or transfer authority.
- Canonical current-workcell cutover and task-plane registration pass.
- Legacy actions are rejected because their starts do not match the live
  anchor and the physical/model mapping is not approved.
- The v1 current-anchor-seeded apparent pass is quarantined because its live
  elbow seed is about 2.64 degrees outside the stock MuJoCo elbow limit.
- The calibrated-range v2 static rerun is frozen and passed at `fc23364`,
  re-admitting the same four exact actions `2/2` per direction with a minimum
  selected model-joint margin of `0.001829670515161086 rad`.
- Its authoritative receipt SHA-256 is
  `c68599e9f18120f46bea955732ccc82c3582b9f18af280292f2aad73cfd47977`;
  closeout decision SHA-256
  `ced92042e73ed53a5ccf27810ddce9d36f9a50f8f6a71110ca517bf116669929`
  preserves false dynamic, mapping, and physical authority.
- CC01 is complete. `ObservableEpisode.v2-min` closeout SHA-256
  `fe586670e539d9047acac3f84167883f5fc50a6fac39c98cf0e2b47b16c52178`
  accepts strict causal serialization and adapters without dynamic or
  physical authority.
- CC02 in the successor queue is the sole active card.
- V1 full-action temporary test outputs are explicitly non-admissible and
  closed by SHA-256 `1693f5c68af7298d27d6125340f48bd87b713f5fa3cd8639848b772eb5fc5f8d`.
  No outcome was used to change the action set, paths, variants, or gates.
- The V2 temporal successor is frozen at SHA-256
  `ae31376f2707ed3c4e6372313dc21ad7734e51e0a19392967df3c444e27e2870`
  and its official immutable replay ran exactly once.
- The official temporal receipt SHA-256 is
  `727ecd642681a6cb4a85327ccd95e4637df60e3ebdf4e2acd49e26e8f2e526ff`.
  It is an admissible action-frozen negative: REAL->SIM `0/2`, SIM->REAL
  `0/2`, and `0/40` outcomes passed. Selected contact passed `40/40`, no-lift
  passed `0/40`, progress passed `23/40`, and exclusion displacement passed
  `33/40`. Closeout SHA-256
  `98e3154e65a778c5f77e52cfc84b12e6886030a0bff7a4d66ac43fb8f184bfaf`
  preserves false mapping, evaluator-freeze, and hardware authority.
- A nominal-only exact-action contact-witness diagnostic is prospectively
  frozen at SHA-256
  `fa1524a2e27c4666c2185303ecddaa1014876f70ac8560d13e4073ed00730482`.
  It may localize modeled contact geometry and timing but cannot tune an
  outcome, calibrate physical parameters, change actions, or authorize motion.
- The witness ran once. Receipt SHA-256
  `89ecb1d20b2176fb0e890b1afda128c8f9eb577cc519277b171361626c4f5bc2`
  establishes that all eight nominal rises follow jaw contact and that six
  first contacts occur above `50 mm` from the pawn root from high-detail jaw
  collision meshes with strong vertical normals.
- A one-mechanism proxy-only jaw collision challenger is frozen at SHA-256
  `5bfefa645281fb9ea5fe99cbd93082d105c1972daeb7a5b9450ec7425432fdd6`.
  It preserves the exact action/evaluator surface and changes only the enabled
  jaw collision representation from meshes-plus-primitives to named
  primitives. It remains an uncalibrated diagnostic.
- V1 failed closed at stale inherited runner-binding validation before output
  creation, model loading, dynamics, or outcomes. Closeout SHA-256
  `a6ec6ab6b5b434f083b6a13f180d25888a834d2c73828e3d63652fc2f00daa39`.
- The outcome-identical V2 wiring successor is frozen at
  `a911f2a3b1945176949eff6de775f8602b656d919f6273262faedc0fc82fa496`.
- V2 generated files but failed at summary serialization. They remain
  uninspected and non-admissible under closeout
  `24e9eb55c93734e8bdde0c06b2fd2a11462e92236dc53be48c521b2aae89c5ef`.
- V3 adds only the serializer pass-through and is frozen at
  `7edc2866728d6787548cb911c4d4c168973e7acf6e28800fdc19596e5cb03156`.
- V3 rejected proxy-only collision geometry at `0/2` per direction. Receipt
  `5f578024...`; closeout `275cba65...`.
- A finite current-layout wrist/path static successor is frozen at
  `4912e8000648f088dd0677189f4a25715e750b59ddfecd7202e2f7b8ff2435cf`.
  It excludes the four outcome-informed cases and admits no dynamic or
  physical execution.
- V1 failed at import before execution; closeout `2fe53c07...`. V2 fixes only
  the helper import and is frozen at `e73b07b6...`.
- V2 admitted three families (`2/1`) and therefore rejected; receipt
  `307b94fa...`, closeout `9938421b...`.
- V3 changes only to lift before wrist rotation and is frozen at
  `3519c639...`.
- V3 remained at three families (`2/1`) and rejected; receipt `dc4d3e60...`,
  closeout `21d76b7c...`.
- V4 changes only to a geometry-derived `35 mm` rear standoff followed by a
  low horizontal precontact approach; frozen at `dc759ea2...`.
- V4 passed static admission with six families and a selected `2/2` split;
  receipt `b9374eaa...`, closeout `7b24317c...`.
- Exact-action dynamic baseline plus diagnostic ZOH replay is frozen at
  `ec29f12c...`.
- Dynamic V1 passed one SIM->REAL family and no REAL->SIM family; receipt
  `cbda502b...`, closeout `7491189f...`.
- The two unopened V4 family actions are frozen for static-only materialization
  at `4d38d758...`.
- Wrist depth is omitted and unnecessary for this campaign.
- One writer uses
  `codex/bidirectional-transfer-goal-loop-20260728`.

Recommended default:

- Replay only the calibrated-range v2-admitted exact actions through the
  accepted object/contact episode contract.
- Implement only the gauge-fixed calibration-graph factors required to
  approve or reject the current physical/model mapping.
- Fit only the simulation mechanism identified by first divergence, preserving
  exact actions and untouched held-outs.
- Complete bidirectional task evidence before the required bounded
  policy-screening pilot; do not delay transfer for new model training.

Open decisions are resolved only through the queue's recorded gates and
fallbacks. Do not activate deferred methods without their specified trigger.

## Execution Rhythm

Repeat:

1. inspect live repo, hardware, camera, process, torque, queue, and graph state;
2. choose the smallest action that moves the active acceptance gate;
3. update the queue and graph prospectively;
4. independently review and require `CONTINUE`;
5. execute once through the reviewed path;
6. verify receipts, hashes, tests, cameras, torque, attempts, and cleanup;
7. update the ledger immediately and commit scoped paths;
8. continue until both directional successes exist or a receipt-backed
   terminal boundary is reached.

Do not stop for planning, weak tooling friction, a recoverable camera defect,
or a preventable evaluator/registration defect.

Owner physical authorization is time-bounded from `2026-07-28 22:38 CDT`
through `2026-07-29 05:38 CDT`. It allows reviewed, recorded, productive
physical actions after their queue gates pass; it does not waive any safety,
identity, preregistration, evidence, action-integrity, or cleanup gate.

## Progress Ledger

```text
Current state:
Active card: CC02 finite current-workcell wrist-orientation and precontact-path static successor.
Completed: CC00, CC00A, CC01.
Evidence: dynamic V1 partial cbda502b...; action completion freeze 4d38d758....
REAL->SIM successes/attempts:
SIM->REAL successes/attempts:
Heldout open count: 1
Physical task attempts: 0/10
Physical/camera/torque state: closed/no motion; latest recorded torque state false.
Remaining: CC02 through CC15.
Blockers: the frozen action set is dynamically rejected; physical/model mapping remains unapproved.
Next step: commit/push the dynamic partial and completion freeze, then materialize the two unopened actions exactly once.
```

## Physical Authority Boundaries

Only the reviewed SO-101 gateway may command the robot. Cameras start before
motion and enclose each transaction. Stop immediately on torque uncertainty,
identity mismatch, missing C922 authority, unsafe geometry, unreviewed
contact, tracking/stall breach, changed bytes, or cleanup failure. Never
perform EEPROM, servo-ID, gain, torque-limit, unreviewed controller, training,
paid-compute, or unrelated work. No human repositioning is assumed.

## Stop Conditions

Stop successfully only after both directional transfer successes, the bounded
policy-screening result, the executable task-world bundle, the targeted
variation connection, the iterative Fable review has no material unresolved
in-scope proof defect, and the full closeout package exists. Stop
unsuccessfully only with a receipt-backed robot/camera safety or authority
boundary after safe autonomous alternatives in the queue are exhausted. A
counted stopped action stays in its denominator.
