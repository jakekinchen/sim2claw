# Slice Brief 004: Physical Teleoperation Gateway and Simulator Replay

**Date:** 2026-07-18

**Milestone:** physical source infrastructure advanced by owner direction;
physical task proof remains separate

## Objective

Allow the identified physical SO-101 leader to control the identified physical
follower through one fail-closed gateway, save an explicitly unqualified raw
source trace, and replay the follower command trace through MuJoCo for a bounded
joint-response comparison.

The current task scene uses brown source pawns at A2, B1, C2, D1, E2, F1, G2,
H1 and mirrored tan pawns at A8, B7, C8, D7, E8, F7, G8, H7. New simulator
recording and trace-replay paths use that layout.

## Start protocol

1. Identify two distinct saved serial buses and exact calibration hashes.
2. Open both buses with torque forced off and read all six calibrated positions.
3. The operator places both arms in roughly the same physical pose. Sync
   refuses more than 20 degrees of body mismatch, commands the follower to hold
   its current position, then ramps it to the leader pose over 2.5 seconds.
4. Verify the final residual is at most three degrees, verify the leader stayed
   still, and finish Sync with follower torque off.
5. Require the workcell/power acknowledgement and display a three-second
   warning countdown.
6. Command the follower to its synchronized current position before enabling
   recording torque.
7. Capture the leader and follower values as a paired relative zero and begin
   recording only after that registration passes.
8. During recording, retain 4-degree command steps, calibrated joint-limit
   clipping, 90-degree body/180-degree wrist-roll relative excursions, current
   reads, and automatic stop after five seconds without measurable progress or
   immediately on a bus error.

## Evidence boundary

Physical rows retain leader target, requested/sent follower command, actual
follower position/velocity, tracking error, raw available current, clamp state,
rate-limit/stall state, and timestamps. Piece/target poses remain unavailable until a reviewed physical
pose source exists, so these rows are
`physical_teleoperation_source_unqualified` and are not ACT training rows.

The simulator replay applies the recorded physical follower commands to the
current MuJoCo SO-101 and reports joint RMSE/max error. It is a command-response
comparison, not a learned-policy evaluation, object/contact validation, or task
success result.

An operator-acknowledged physical command replay is also available through the
same gateway:

```bash
uv run sim2claw physical-replay \
  --recording datasets/act_source_recordings/<finalized-recording> \
  --yes
```

This path accepts only a finalized, hash-matching physical-follower recording.
It verifies position mode and calibration limits with torque off, holds the
follower at its current position, refuses more than 45 degrees of travel to the
recorded start pose, approaches that pose at 10 degrees per second, and then
requests the saved commands at their original timestamps. The ordinary gateway
rate, tracking, telemetry, stall, USB-failure, and shutdown guards remain in
force. A receipt and per-sample trace are retained under
`runs/physical_replays/`, including any safety limiting and an explicit
torque-off result.

Completing this replay proves command-trajectory delivery only. It does not
inherit the source label as a physical evaluator verdict and does not prove
piece motion, placement accuracy, learned-policy behavior, or task success.

## Owner-directed five-minute base loop

The fixed 12-recording base-to-inverse-to-base demo cycle has a separate
runner. Validate every source receipt without opening hardware first:

```bash
uv run python scripts/run_owner_directed_base_loop.py --dry-run
```

After separate owner authorization and a current powered-workcell-clear check,
run the guarded cycle explicitly:

```bash
uv run python scripts/run_owner_directed_base_loop.py \
  --yes \
  --owner-directed-unqualified-labels
```

The runner performs one move at a time through the guarded physical replay
path, releases torque between moves, retains an overhead checkpoint after each
move, and writes one aggregate receipt below
`runs/task_orchestrator/owner_directed_base_loop/`. It fails closed on source,
duration, gateway, camera, or torque-off errors. Folder-label selection and the
unregistered C922 checkpoints remain unqualified command-replay evidence; the
runner does not promote the recordings or claim the board outcome succeeded.

On a loopback Studio server, the Task Orchestrator exposes this same runner as
the narrow `Demo Physical` mode only when Studio is started with
`--enable-physical-demo`, the Logitech overhead camera is available, and the
follower bus is connected. Ordinary Studio startup keeps this mode absent. In
an explicitly opted-in demo session, the exact chat
commands `loop it`, `run the loop`, `start the loop`, `loop the base case`, and
`run the base case loop` bypass the model planner and start this fixed script.
The overhead image is labeled demo visual feedback rather than board-registered
occupancy evidence; square registration is not a prerequisite for this script.

The native controller in `apps/Sim2ClawDemoControl/` exposes four buttons over
the same loopback controller. Power starts or stops Studio and the Demo Physical
session; the two direction buttons select the first or last six fixed traces;
Loop selects the full 12-move five-minute cycle. Power Off requests a stop and
waits for the current guarded move to finish and release torque before it stops
the server. Build and launch it only for an owner-authorized physical session:

```bash
SIM2CLAW_ENABLE_PHYSICAL_DEMO=1 \
  apps/Sim2ClawDemoControl/Scripts/compile_and_run.sh
```

## Stop conditions

Calibration mismatch, missing/distinct-bus failure, Sync mismatch outside the
guard, post-hold movement, a sustained follower stall, USB dropout, or any
shutdown error stops the run and requests follower torque-off. A rate-limited
follower that advances or resumes within the five-second window does not count
as stalled. Failed samples are retained for diagnosis and do not block Retry.
