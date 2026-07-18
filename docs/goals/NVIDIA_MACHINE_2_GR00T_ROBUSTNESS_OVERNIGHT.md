# NVIDIA Machine 2 Overnight Goal: GR00T Recovery and Robustness

This file is the command for the second GR00T-capable machine. Give the agent
this entire file and tell it to continue autonomously until a stop condition is
met. It is a complementary research lane, not a second copy of machine 1.

## Mission

Build and evaluate a recovery-focused GR00T N1.7 challenger for the simulated
mini-chess manipulation task. Use a deterministic geometric expert to produce
evaluator-accepted demonstrations of small manipulation primitives and
recovery behaviors, then test whether a learned policy can tolerate bounded
pose error, nearby distractors, and grasp slippage without disturbing the
board. Produce a useful positive, partial, or terminal-negative result by
morning; do not optimize the report into a success claim.

## Coordination boundary

- Machine 1 owns the nominal `chess_pick_place_groot_v1` campaign: the existing
  24 sparse-board demonstrations, the 5,000-step baseline, checkpoints at
  1,000-step intervals, and the four frozen v1 held-out trajectories.
- Machine 2 owns a new recovery/robustness contract and dataset. Do not rerun
  the nominal 24-example experiment as the main result.
- Use a separate clone or worktree and branch:
  `codex/gr00t-n17-recovery-overnight`.
- Start from `origin/main`, record the starting commit, and do not work directly
  in machine 1's checkout. Do not repeatedly merge a moving `main` into an
  active experiment.
- Do not modify `configs/tasks/chess_pick_place_groot_v1.json`, its frozen
  held-out rows, or its promotion gates. Put new behavior in clearly versioned
  v2 files, preferably `configs/tasks/chess_pick_place_groot_recovery_v2.json`
  and `src/sim2claw/groot_chess_recovery.py`.
- Machine 1 and machine 2 may be compared only through frozen evaluator
  receipts. Neither machine may promote its own checkpoint.

## Source of truth, in authority order

1. This goal and the owner's current instructions.
2. `AGENTS.md` and the clean-room operating rules.
3. `configs/tasks/chess_pick_place_groot_v1.json` for the shared nominal task
   identity and immutable v1 evaluation cases.
4. `src/sim2claw/groot_chess.py` and its consequence evaluator.
5. `docs/decisions/0003-groot-n17-dynamic-chess.md` for the model, source,
   evidence, and authority boundary.
6. `docs/run-logs/2026-07-18-groot-n17-chess-overnight.md` for machine 1's
   recorded history. Live machine-1 receipts supersede stale prose.
7. The read-only `sim-link` archive only for lessons. Copy nothing from it.

## Frozen technical identities

- NVIDIA source: Isaac-GR00T `n1.7-release` commit
  `23ace64f17aa5015259b8609d371eb61a357c776`.
- Base model: `nvidia/GR00T-N1.7-3B`, pinned revision already recorded by the
  repository.
- Backbone dependency: `nvidia/Cosmos-Reason2-2B` through an already-authorized
  local credential; never print, commit, or place that credential in a command
  line or receipt.
- Simulation only. No gateway, camera, serial, servo, or physical authority.
- Training loss and open-loop action error are diagnostic only. The separately
  invoked consequence evaluator owns promotion.

## Local physical-source intake note

The owner-local checkout now has five physical pawn teleoperation sources
indexed by `configs/data/physical_teleop_episode_intake_20260718.json`. None is
a GR00T v1 row. The frozen v1 dataset remains simulation-only, three physical
move labels conflict with recorder metadata, every formal outcome is
`unreviewed`, and the overhead C922 stream has not been exported under a
versioned GR00T LeRobot RGB/language/action modality contract. A future recovery
v2 lane may use the cohort only after metadata repair, synchronized modality
conversion, zero-row held-outs, and separate consequence evaluation.

## Locked pawn product benchmark

The owner-selected comparison target is now frozen at
`configs/evaluations/pawn_rank12_bidirectional_v1.json`: 16 directed near-side
pawn moves covering A1↔A2 through H1↔H2. Simulation uses three fixed
realizations per case, or 48 evaluator rows; physical evaluation uses one reset
trial per directed case. Exact evaluation seeds, states, trajectories, and
physical trials contribute zero training rows.

Do not mutate the frozen rook/king `chess_pick_place_groot_v1` task. A GR00T
pawn experiment needs a new versioned RGB/language/action contract. Generate
training examples for all 16 semantic instructions from disjoint seeds and
include safe push, pick/lift/place, nearby-pawn avoidance, and evaluator-linked
recovery variants. The benchmark accepts any safe strategy based on board
consequences; strategy is a diagnostic breakdown.

Before provisioning Brev, prove locally that the new dataset export, official
NVIDIA loader, 48-row reset builder, and separate consequence evaluator pass.
Then authorize one bounded clean-base N1.7 run with fixed checkpoints. Sweep
every checkpoint on the same 48 rows and rank by valid case coverage,
worst-file result, direction parity, collateral displacement, and only then
open-loop diagnostics. Convert failure classes into disjoint expert or
corrective training rows; never copy an evaluator realization into training.
No paid worker is authorized by this plan itself.

## Research hypothesis

The current nominal demonstrations mostly teach one uninterrupted trajectory.
The likely failure is not lack of semantic understanding; it is insufficient
coverage around contact, capture verification, reacquisition, and release. A
geometric expert should therefore remain the demonstration generator, while
GR00T learns to execute and recover from these small closed-loop motor units:

1. align above the named piece;
2. descend without contacting a distractor;
3. close and verify bilateral capture;
4. reacquire after a bounded miss or slip;
5. lift vertically before translating;
6. transport and settle over the named square;
7. release and retreat without dragging the piece.

Keep the natural-language task instruction constant through an episode. Phase
labels may be evaluator metadata, but must not become privileged inference
inputs unavailable during the held-out run.

## Phase A: establish an isolated, reproducible lane

```bash
git fetch origin
git switch -c codex/gr00t-n17-recovery-overnight origin/main
./scripts/bootstrap_runtime.sh
uv run python -m unittest discover -s tests -v
MUJOCO_GL=egl PYOPENGL_PLATFORM=egl \
  uv run sim2claw doctor --target nvidia --render-probe
./scripts/check_groot_n17_hf_access.sh
```

Record the commit, GPU, driver, CUDA, Torch, MuJoCo, NVIDIA source, model
revision, and credential-access result before training. If this is paid Brev
compute, do not provision anything without a separately stated budget. If a
Brev worker is authorized, use exactly one worker and delete it immediately
after the bounded run.

## Phase B: freeze the v2 evaluator before generating training data

Create a versioned recovery task without changing v1. Freeze exact seeds,
magnitudes, split membership, and evaluator behavior before training.

The default robustness matrix should cover both the rook and king and at least
these three failure families:

1. **Pose error:** initial target XY offsets of approximately 4 and 8 mm and
   yaw offsets of approximately 10 and 20 degrees, limited to collision-free
   resets.
2. **Distractor proximity:** one non-target piece placed close enough to punish
   sweeping approaches while remaining initially collision-free. Freeze the
   allowed spacing from geometry rather than silently hand-tuning per episode.
3. **Contact recovery:** a declared simulator fault injection that produces a
   small pre-lift miss or 3--6 mm slip, followed by policy-owned reacquisition.
   Record the injection separately from robot assistance; all robot actions
   after it must remain model-owned.

Required evaluator outputs include phase reached, first-contact identity,
bilateral jaw contact, maximum and final lift, placement error, upright and
settled state, final jaw clearance, maximum displacement of every non-target
piece, action ownership, fault-injection frames, and assistance frames.

Preserve the v1 hard gates, including the 6 mm distractor-displacement limit.
Do not weaken a gate because an early candidate fails it. Add deterministic
negative fixtures proving the evaluator rejects spills, wrong-piece contact,
failed capture, dragging, and late toppling.

## Phase C: generate a recovery curriculum with the geometric expert

- Generate demonstrations from repo-native geometry/IK and deterministic
  phase logic. The expert may observe exact simulator state; the learned policy
  may use only its declared RGB, language, and proprioceptive modalities.
- Include only demonstrations that pass the frozen consequence evaluator.
- Keep failed expert rollouts as counterexamples, never imitation rows.
- Generate at least 48 accepted training episodes, covering both piece types
  and all three perturbation families, unless a written feasibility result
  proves a smaller matrix is the largest valid one.
- Freeze at least 24 held-out robustness episodes with disjoint seeds and
  perturbation combinations. They contribute zero training rows.
- Retain nominal examples in the mixture so the challenger does not learn only
  recovery behavior. Record the exact nominal/recovery sampling ratio.
- Export a fresh GR00T LeRobot v2 dataset with hashes, stats, modality identity,
  task rows, and an immutable dataset receipt. Do not copy machine 1's generated
  dataset or checkpoint.

Do not start GPU training until the v2 contract tests, expert held-outs,
official NVIDIA loader, and dataset receipt all pass.

## Phase D: bounded candidate training

Train candidate A from the clean pinned N1.7 base, not from machine 1's
fine-tuned checkpoint. Use one GPU process and fixed checkpoints at 1,000,
2,000, 3,000, 4,000, and 5,000 optimizer steps. Preserve the exact command,
config, data receipt, start/end times, and exit status.

Stop immediately on any of the following:

- duplicate trainer or policy-server process;
- non-finite loss or action;
- data/evaluator identity mismatch;
- OOM that cannot be resolved without changing the declared experiment;
- held-out rows entering training;
- budget or morning cutoff;
- a request to open physical authority.

Setup failures before optimizer step zero may be corrected and relaunched only
when the failed log is preserved and the dataset, evaluator, and experiment
identity remain unchanged.

## Phase E: evaluator-owned checkpoint sweep

For every fixed checkpoint:

1. Run open-loop evaluation on v1 and v2 held-outs as diagnostics.
2. Start the pinned policy server and run closed-loop nominal v1 consequences.
3. Run closed-loop v2 robustness consequences across every failure family.
4. Save action traces, videos, per-gate results, and exact checkpoint/server
   identities. A receipt without the checkpoint hash is invalid.
5. Shut down each policy server before starting the next checkpoint.

Rank candidates lexicographically by:

1. valid, finite, model-owned execution with no undeclared assistance;
2. v2 consequence pass count and worst-case non-target displacement;
3. v1 nominal consequence pass count;
4. placement error and stable post-release hold;
5. open-loop MAE/MSE only as a final diagnostic tie-breaker.

Do not select a checkpoint merely because it is latest or has the lowest
training loss.

## Phase F: one bounded counterexample iteration

If candidate A leaves time before the cutoff, cluster closed-loop failures by
`approach`, `contact`, `capture`, `lift`, `transport`, `place`, or `release`.
Choose the single largest actionable cluster. Add one versioned set of
evaluator-passing expert demonstrations for that cluster, freeze a new dataset
receipt, and train candidate B from the same clean N1.7 base.

Do not mutate the held-out cases, consequence gates, or reward to make candidate
B look better. Do not perform more than one dataset-augmentation round without
new owner direction. A terminal negative with a localized failure cluster is a
successful research outcome.

## Continuous overnight rhythm

Continue without waiting for routine human confirmation:

1. inspect the current receipt and process state;
2. choose the next smallest step that can change the evidence state;
3. execute one bounded action;
4. record evidence in an ignored run ledger and a concise tracked session log;
5. compare against the acceptance criteria;
6. continue until completion or a stop condition.

Poll long-running jobs at a sensible interval. Do not spend the night emitting
status-only messages, redesigning the Studio UI, researching unrelated models,
or repeatedly rerunning an unchanged failure. Commit and push the branch at
stable evidence boundaries, never during a live file write.

## Acceptance criteria

The overnight lane is complete when all of the following are true:

- v1 remains byte-for-byte unchanged and its tests still pass;
- a frozen v2 recovery contract, deterministic rejection fixtures, accepted
  training set, zero-row held-out set, and dataset receipt exist;
- at least one clean-base GR00T candidate completed or a precise external
  blocker is proven before optimizer step zero;
- every fixed checkpoint that exists has evaluator-owned v1 and v2 results;
- the selected outcome is classified as pass, partial, or terminal negative
  without reward or training self-promotion;
- exact model, checkpoint, dataset, evaluator, source, and environment
  identities are recorded;
- generated datasets, checkpoints, videos, credentials, caches, `outputs/`,
  and `runs/` remain out of Git;
- the branch is pushed with a reviewer-ready session log and no unrelated
  changes;
- any paid worker and policy-server process is stopped, and paid inventory is
  verified empty.

## Stop conditions

Stop autonomous iteration at the earliest of:

- the acceptance criteria are met;
- 08:30 America/Chicago on 2026-07-18;
- candidate B has been evaluated;
- the same external blocker has been proven twice with no safe next step;
- an authorized compute ceiling would be exceeded.

At cutoff, preserve the current receipts, terminate training cleanly if
possible, stop policy servers, tear down paid resources, push the branch, and
report exactly what passed, failed, remains uncertain, and should happen next.

## Progress ledger format

```text
Current state:
Starting main commit:
Frozen v2 contract and evaluator identity:
Dataset receipt and accepted/held-out counts:
Active candidate and optimizer step:
Completed checkpoint evaluations:
Best consequence result:
Failure cluster:
Evidence paths:
Compute inventory and estimated spend:
Remaining:
Blockers:
Next step:
```
