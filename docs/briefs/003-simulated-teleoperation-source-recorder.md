# Slice Brief 003: Simulated Teleoperation Source Recorder

**Date:** 2026-07-18

**Milestone:** M7 - source-collection prerequisite only

## Objective

Provide a loopback-only Studio workflow that records a physical SO-101 leader
driving the simulated follower, then labels and stores the raw episode with the
provenance required by the frozen M6 contract.

## Acceptance criteria

- Detect the expected leader and follower serial identities while rejecting a
  USB Billboard device as a motor bus.
- Verify the expected same-arm calibration files and exact LeRobot runtime.
- Start and stop leader-to-MuJoCo recording from the Studio.
- Persist leader target, follower command, actual follower state/velocity,
  tracking error, selected-piece pose, continuous target pose, timestamps, and
  proof class.
- Require a human label, declared skill, and success/failure/correction outcome
  before moving the draft into `datasets/act_source_recordings/`.
- Mark every saved artifact as raw source, ignored by Git, not held-out, and not
  training data pending deterministic replay and separate evaluator admission.
- Keep physical follower mode disabled by default and keep automated validation
  entirely on the leader-to-simulator path.

## Validation

```bash
uv run sim2claw teleop-preflight
uv run pytest -q
git diff --check
```

Render and exercise `http://127.0.0.1:4173/#/record`, including one bounded
leader-to-simulator smoke recording. Confirm the saved receipt and that the
physical follower bus was never opened by the smoke path.

## Out of scope

Trajectory segmentation, object/target-frame retargeting, planner stitching,
IK generation, strict evaluator admission, ACT training, checkpoint promotion,
camera pose estimation, physical follower validation, or any M13 claim.

## Next slice

Implement the deterministic M7 source segmentation and retarget/replay
pipeline against this source schema plus repo-native constructive experts.
