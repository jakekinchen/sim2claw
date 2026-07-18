# Decision 0002 — State ACT for the first chess-rook lift

## Status

Accepted for one bounded simulation task on 2026-07-17. No physical or broad
policy authority follows.

## Decision

Use a fresh, state-based conditional-VAE Action Chunking Transformer for
`chess_rook_lift_v1`. The policy consumes one 31-value observation and predicts
50 future six-joint position targets. Evaluation consumes the full 50-action
chunk before re-decoding. The observation contains joint state, controller
targets, simulated rook and pinch positions, and explicit frozen episode/phase
progress. Phase features make this a fixed-horizon task policy, not a general
visual chess manipulation policy.

Training uses eight synthetic unassisted demonstrations with no rows from the
held-out seed. A different process loads the selected checkpoint on CPU in
float32, owns all success thresholds, and judges the resulting physics trace.
Training writes a checkpoint and receipt but cannot mark itself successful.

## Dependency

PyTorch `2.11.0` is directly pinned and locked. It is adopted from the public
PyTorch project to provide MPS training, CPU/fp32 evaluation, Transformer
layers, and checkpoint serialization. Hugging Face's public LeRobot ACT
documentation describes ACT as a conditional-VAE policy that combines robot
state, a latent style variable, and a Transformer decoder to emit future action
chunks. This implementation is freshly authored here and does not copy
LeRobot or `sim-link` code.

Sources:

- <https://huggingface.co/docs/lerobot/act>
- <https://pypi.org/project/torch/>

## Frozen evaluation gates

- maximum rook rise at least 40 mm;
- final rook rise at least 40 mm;
- at least 80 consecutive jaw-contact control steps;
- jaw contact during at least 60% of the final 200-step window;
- all 2,020 actions owned by the loaded ACT checkpoint;
- zero grasp assistance and no camera, serial, gateway, network, or physical
  path.

## Evidence-led revisions

Attempt 1 used receding-10 execution and stalled at stand-off with no contact.
Attempt 2 used full chunk-50 execution plus state perturbation and reached 77
consecutive contact steps and 6.56 mm lift, still below every frozen lift gate.
Revision 3 added explicit phase/progress observation features and increased the
gripper loss weight. It passed without changing the held-out seed or evaluator
thresholds.

## Consequences and limits

The accepted result proves one learned ACT checkpoint can grasp and hold the
named simulated rook in the frozen photo-aligned workcell. It does not prove
vision-conditioned behavior, chess legality, multi-piece or multi-pose
robustness, collision-free behavior for surrounding pieces, calibration,
gateway readiness, sim-to-real transfer, or physical manipulation.
