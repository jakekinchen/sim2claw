# 2026-07-20 B--G endpoint appearance intervals

Command:

```text
uv run --offline python scripts/run_pawn_bg_endpoint_motion.py --partition train
```

The source-bound pipeline evaluated 11 product-scope training episodes and read
no held-out videos. Every video, sample file, and owner-reviewed endpoint marker
frame is SHA-bound. It detected sustained source appearance loss in 11/11 and
final destination appearance in 11/11.

Source appearance loss occurs a mean 1.386 seconds before gripper closure onset
(range -4.645 to +2.416 seconds). Destination final appearance occurs a mean
0.832 seconds after release onset (range -0.450 to +2.746 seconds). The wide
source interval demonstrates that arm occlusion can erase the pawn before the
gripper closes; a flat gripper response is therefore not an exact contact label.

The output explicitly claims neither contact, grasp, z motion, lift, nor metric
object trajectory. It contributes interval bounds and a reason to abstain.

Receipt:
`outputs/pawn_bg_endpoint_motion_v1/train/endpoint_motion_receipt.json`.
