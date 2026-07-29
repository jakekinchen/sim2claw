# Realized-Action Outcome Calibration Task Queue

Status: `ACTIVE_C9`

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
| C3A | `PASS` | Automate first-divergence and parameter attribution. | All eight episodes report nine ordered channels; timing/actuation repeat cross-episode, contact does not; artifact `6cdc2b9b1022bdcb41f1df0f35d29af61f563018078940ab8d4f6d5217ba82c3`. | C4 admits only three-sample hold and direction response. C5 has no selectable mechanism. |
| C4 | `PASS` | Fit one versioned effective SO-101 temporal challenger. | Validation joint RMS improves `55.45%` and provisional EE RMS `58.51%`, with no joint regression; artifact `df50459a4c7f60894690610c8578f67e064c13de3d0a9f7e286aa8c26e736aa6`. | Three-sample hold remains noncausal; alpha `1.0` rejects extra smoothing; global mapping remains false. |
| C5 | `TERMINAL_NEGATIVE` | Fit only identifiable contact/object mechanisms from retained evidence. | `0/5` candidate dimensions have nonsealed witnesses; no parameter fit; artifact `6a904ef2231f634a65661778afd59ec5e901204386d7dfeee85a05d574961692`. | Current MuJoCo contact remains unvalidated diagnostic baseline and cannot promote C6. |
| C6 | `TERMINAL_NEGATIVE_0_OF_1` | Freeze and run the physical realized-action trajectory to simulator outcome replay exactly once. | Exact action/plant replay used no later observation or marker; no jaw carry formed; final error `69.148 mm`, tilt `179.992 deg`, height error `31.947 mm`; artifact `df3f6abab728ec6a74a468afeb531b4bec99346c693ec081786c8dd8fb8c2c38`. | Immutable `0/1`; no successor admitted because cross-episode contact evidence is absent. |
| C7 | `DETERMINISTIC_NEGATIVE_0_OF_3` | Populate measured uncertainty and run robustness checks. | Identified, direct, and diagnostic ZOH all fail; identified is best; no unknown distribution invented; artifact `5224dd435d9cbbd8db36fe4a917edce2d2c1e8a2647a6f202574e5c32c7ab682`. | C6 remains immutable `0/1`; probabilistic robustness unavailable. |
| C8 | `PASS` | Package the causal proof in Studio. | `#/proof` synchronizes `531` requested/sent/measured/applied rows, C922 video, residuals, first divergence, contact gap, pawn path, geometry, robustness, gates, hashes, and proof limits; desktop/phone acceptance passed; artifact `34b8dc493aa9d365a2bb25d8c90773c565f4e7dd39e294a02dc45d0b1b772436`. | Missing evidence remains visibly missing; the interface cannot promote a proof class. |
| C9 | `IN_PROGRESS` | Close future robust SIM-to-REAL packet and policy-ranking work at the service boundary. | Record elbow service, fresh requalification, preregistration, mapping, and separate authorization as prerequisites without opening physical authority. | No execution or counted attempt is allowed from this queue. |

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
