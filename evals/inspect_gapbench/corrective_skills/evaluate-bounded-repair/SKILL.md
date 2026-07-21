---
name: evaluate-bounded-repair
description: Edit and publicly evaluate a minimal typed task-space corrective proposal within the frozen budget.
---

# Evaluate Bounded Repair

1. Copy the unchanged candidate to `candidate/proposal.json`.
2. Preserve schema, bindings, proposer metadata, reference frame, zero rotation,
   zero gripper delta, duration, and all authority fields.
3. Edit only `waypoints[0].translation_delta_m`, keeping its norm at most 10 mm.
4. Call `run_public_repair_evaluation` and inspect residual, robustness, and
   simulator calls. Use additional candidates only to test a specific revision.

Development improvement does not admit data or establish sealed success.
