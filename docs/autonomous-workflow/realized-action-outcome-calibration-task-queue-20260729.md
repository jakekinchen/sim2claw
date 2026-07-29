# Realized-Action Outcome Calibration Task Queue

Status: `ACTIVE_C3A`

Created: `2026-07-29`

Branch: `main`

Planning revision: `f3fc5617aa465d51b77ecee52a2985e68e8b52ef`

## Mission

Use only already-retained physical evidence to reach the next honest evidence
rung:

> A hash-bound physical action trajectory produces the matching pawn-task
> outcome in the identified simulator without endpoint injection, observed
> joint-state driving, or an observed grasp/release mode.

The physical pathway remains paused at the follower-elbow service boundary.
No card in this queue opens a live camera, gateway, serial bus, torque, robot
motion, pawn attempt, or SIM-to-REAL execution.

This queue follows the completed RP04K, RP04L, and RP04M results without
rewriting them:

- RP04K: free-release hybrid `0/2`.
- RP04L: observation-conditioned support handoff `1/3`.
- RP04M: camera-endpoint REAL-to-SIM `1/1` episodes and `2/2` endpoint
  states.
- Strict precompiled action-only REAL-to-SIM remains `0/0`.

The target proof is narrower than strict precompiled action-only replay because
the retained source was gateway-transformed and has no actuator-application
timestamps. Its intended proof class is:

`physical_realized_gateway_sent_action_trajectory_to_identified_simulator_task_outcome`

## Planning inputs

The queue reconciles:

1. The zero-new-physical-data P0--P10 implementation list from the most recent
   non-current Codex project thread.
2. The completed GPT Pro repository review against commit `f3fc561`, which
   recommends a prospectively frozen C922 pawn-crown carry-prefix comparison.
3. Current repository receipts and the user's required third evidence rung.

The GPT recommendation becomes card C2-RP04N. It is a useful calibration
diagnostic, but it is explicitly action-free and cannot satisfy the mission.

## Operating rules

- Exactly one card is active at a time.
- Whole episodes, not frames, define fit, validation, and sealed cohorts.
- Raw requested, gateway-sent, measured, and timestamp channels remain
  separate and hash-bound.
- The `531 x 6` gateway-sent source trace is the immutable action trajectory
  for the mission result.
- No action clipping, smoothing, offset, retiming, IK repair, suffix, endpoint
  forcing, observed-state driving, camera correction after initialization, or
  observed grasp/release marker may enter the mission replay.
- The RP04M initial D1 camera observation may initialize the pawn and validate
  the task-plane mapping. Its terminal D2 observation is evaluator-only and
  cannot drive the replay.
- A simulator grasp mechanism is admissible only if it is episode-independent,
  triggered entirely by simulated geometry/contact plus the immutable gripper
  action, fitted outside the sealed mission episode, and validated on untouched
  episodes.
- Sample-domain alignment must never be relabeled as causal actuator latency.
- Parameters that are not identifiable from retained evidence remain unknown.
- Prior receipts and negative results are immutable.
- Fable remains reserved for a genuine unresolved trajectory blocker.

## Critical-path queue

| ID | Status | Required outcome | Acceptance gate | Failure / redirect |
|---|---|---|---|---|
| C0 | `PASS` | Freeze the retrospective evidence corpus and whole-episode cohorts. | `29` recordings inventoried; fit `4`, validation `3`, sealed `1`; artifact `232c80bb28cac325f54d829e31fd2b84d12df85df1948d3d8fb5b4fd3e4739d1`; closeout `configs/decisions/realized_action_retrospective_corpus_v1_closeout.json`. | No split leakage; `11` metadata-conflicted episodes remain provenance-only. |
| C1 | `PASS` | Build deterministic `EpisodeTwinBundle.v1` artifacts. | Eight bundles and 41 generated files rebuild identically; receipt artifact `5290ef26caa3fa5a22db8f0bfc4aa1ec8e69c9eca63d431fab73a612e8258914`; tracked closeout `configs/decisions/episode_twin_bundle_v1_closeout.json`. | Missing actuator/contact/depth/object channels remain explicit. |
| C2 | `PARTIAL_ACCEPTED` | Reconcile defensible static geometry using existing images only. | Task plane `4.742 mm` RMS and pawn endpoints `3.101/3.357 mm` accepted; fixed-base/articulated/floor gaps preserved; artifact `db3104c720293076eaf4b30bf8ed3744ae35e5de7ce183c1902e8f6a48aa1f44`. | Global mapping remains unapproved; no joint refit performed. |
| C2-RP04N | `TERMINAL_NEGATIVE_0_OF_1` | Run the GPT-advised D1-conditioned C922 pawn-crown carry-prefix correspondence test. | Frozen evaluation admitted only `3/18` crown points, all in the last tercile; artifact `cf1fbfff5d914b2a5fedff7825bcb3f89ef60a8001ab653e97bbc5f33a35bf0b`. | The gripper occludes the crown through the carry. Preserve `camera_projected_carry_prefix_real_to_sim: 0/1`; no alternate landmark or projection refit. |
| C3 | `PASS` | Run retrospective SAGE-lite actuator analysis. | Eight episodes and `3433` samples analyzed; fit/validation agree on elbow, lift, wrist EE contribution and `+3` sample association; artifact `f03dbd13d2fdd85d1893e2ed03923dcdc4b15fa6deeb9bb9f95845b367c6054f`. | Association remains non-causal; current remains an uncalibrated proxy; global mapping remains false. |
| C3A | `IN_PROGRESS` | Automate first-divergence and parameter attribution. | Every episode is checked in order for initial geometry, requested/sent action, joint response, EE projection, first contact, pawn planar motion, lift/tip, release/support, and final consequence. A sensitivity matrix separates geometry, timing, actuation, contact, and evaluator channels and flags compensating parameters. | No parameter advances unless it changes an observed residual in more than the episode that exposed it. |
| C4 | `PENDING` | Fit one versioned effective SO-101 temporal challenger. | Preserve requested and gateway-sent bytes. Emit separate requested/sent/applied traces. Fit gateway behavior, hold/delay, rate/saturation, gain/time response, and only evidence-supported directional play in that order. Compare direct target, diagnostic `0.11 s` ZOH, and the identified plant on untouched episodes. Require prospectively frozen pooled joint and EE improvement gates with no material per-joint regression. | If no plant generalizes, preserve the terminal actuator-model negative and do not compensate with contact or camera parameters. |
| C5 | `PENDING` | Fit only identifiable contact/object mechanisms from retained evidence. | Use fit episodes for first-contact and carried-object/contact witnesses, validation episodes for selection, and the mission episode only after freeze. Candidate dimensions may include effective jaw/pusher geometry, contact height, pawn-board friction, supported compliance/damping, and pawn mass/CoM only where constrained. Any grasp abstraction must trigger only from simulated contact/geometry and the gripper action. | Reject candidates that use source markers, final-square loss, unsupported forces, impossible geometry, or sealed outcomes to select parameters. If no mechanism validates, preserve the contact-model negative. |
| C6 | `PENDING_MISSION_GATE` | Freeze and run the physical realized-action trajectory to simulator outcome replay exactly once. | Bind source/contract/implementation/model/evaluator hashes before the run. Initialize from the frozen D1 state; apply the exact gateway-sent `531 x 6` float32 rows in source order through C4's identified plant and C5's validated episode-independent contact model. Supply no later camera, observed joint, grasp-mode, release-marker, endpoint, or task-state input. Require the unchanged RP04K task gates, including composable center error `≤6 mm`, upright `≤10 deg`, other-piece displacement `≤5 mm`, height error `≤6 mm`, and settled linear/angular velocity. | A pass records mission success `1/1`. A failure is immutable. Permit at most one new successor only when C3A identifies one cross-episode mechanism not already tested; otherwise close the rung as a terminal negative pending new physical evidence. |
| C7 | `PENDING_AFTER_C6` | Populate measured uncertainty and run robustness checks. | Every distribution bound links to an existing artifact, cross-validation residual, or fit covariance. Evaluate the exact C6 action under direct, identified, and independently implemented challenger plants plus admissible geometry/contact uncertainty. Report nominal and robust success separately. | Unknown dimensions are not randomized. Robustness cannot demote or retroactively redefine the one-run C6 result. |
| C8 | `PENDING_AFTER_C6` | Package the causal proof in Studio. | Mobile and desktop views synchronize physical video, direct and identified simulations, requested/sent/measured/applied traces, residuals, first divergence, contact witnesses, pawn path, geometry overlay, uncertainty result, task gates, hashes, and proof-class limits. | Missing evidence remains visibly missing; the interface cannot promote a proof class. |
| C9 | `DEFERRED_UNTIL_SERVICE` | Prepare a future robust SIM-to-REAL packet and policy-ranking pilot. | Only after elbow service, fresh requalification, and a separately reviewed physical authorization. | No execution or counted attempt is allowed from this queue. |

## C2-RP04N prospective design boundary

Before any trajectory annotations are made:

- Freeze C922 source/video/orientation hashes and the RP04K/RP04M lineage.
- Freeze source indices
  `[255,263,271,280,288,296,304,313,321,329,337,346,354,362,370,379,387,395]`.
- Use the visible pawn crown center as the only landmark.
- Use two randomized annotation passes with visibility labels.
- Require D1 disagreement `≤1 px`, carry disagreement `≤2 px`, at least
  `12/18` visible points, at least three points per temporal tercile, and no
  more than three consecutive invalid frames.
- Permit only one D1-derived 2D translation of magnitude `≤6 px`.
- Freeze the ordered-curve implementation and its thresholds before the
  simulator track is revealed.

The result is a 2D observation-correspondence diagnostic. A board-plane
homography is not used as metric XY for the elevated pawn.

## C6 exact ledger

If C6 passes:

- `realized_gateway_sent_action_trajectory_real_to_sim: 1/1`
- `camera_endpoint_episode_real_to_sim: 1/1` remains unchanged.
- `camera_projected_carry_prefix_real_to_sim` reports its independent RP04N
  result.
- `strict_precompiled_action_only_real_to_sim: 0/0` remains unchanged because
  the physical source was not precompiled and lacks actuator-application
  timestamps.
- `SIM_TO_REAL: 0/0`, physical pawn attempts `0/10`, global mapping
  unapproved, and policy ranking insufficient remain unchanged.

The honest success claim is:

> One retained physical D1→D2 realized gateway-sent action trajectory,
> initialized from its frozen physical D1 state and replayed without later
> observation or endpoint injection, produced the same upright D2 task
> consequence under a separately identified, held-out-validated simulator
> plant and episode-independent contact model.

## Two-day execution order

### Day 1: make the replay identifiable

1. C0 corpus freeze and episode splits.
2. C1 mission/fit/validation bundle compiler.
3. C2 minimal static residual reconciliation.
4. C2-RP04N physical annotations and one diagnostic run.
5. C3/C3A SAGE-lite and first-divergence reports.

### Day 2: close the action/outcome rung

1. C4 identified temporal challenger.
2. C5 one bounded contact/object family, only if C3A supports it.
3. C6 freeze commit, one outcome run, and immutable closeout.
4. If C6 passes, C7 robustness and C8 Studio packaging.
5. If C6 fails, record the terminal negative and package the localized first
   divergence rather than weakening the proof.

## Deferred work

Do not delay C6 for:

- Isaac Lab migration or a second full simulator.
- GapONet or neural residual dynamics.
- New ACT/GR00T training or sim+real co-training.
- Wrist-depth recovery.
- Another 3DGS reconstruction.
- Cosmos augmentation.
- Broad arbitrary domain randomization.
- A simultaneous high-dimensional camera/robot/contact optimizer.
- Policy ranking or physical SIM-to-REAL execution before elbow service.
