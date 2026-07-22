---
name: design-repair-probe
description: Select a declared low-cost corrective probe only when it can change the repair estimate or mechanism diagnosis.
---

# Design Repair Probe

1. Check remaining probe budget with `repair_status`.
2. Predict whether a repeat pose estimate or control consistency check could
   change the proposed direction or distinguish the mechanism.
3. Call `request_repair_probe` only with a declared ID.
4. Recompute the estimate and confidence from the immutable receipt.

Never request physical interaction, arbitrary simulation access, or hidden
terminal perturbations.
