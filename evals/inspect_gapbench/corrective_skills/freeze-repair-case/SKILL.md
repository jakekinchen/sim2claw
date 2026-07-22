---
name: freeze-repair-case
description: Verify a corrective-repair case identity, evidence manifest, budgets, and authority before proposing a change.
---

# Freeze Repair Case

1. Call `repair_status` with the exact case ID.
2. Record the case digest, evidence IDs, probe and evaluation budgets, claim
   boundary, and absent training, promotion, and physical authority.
3. Read only evidence listed by the status response.
4. Stop if an identity changes or the request requires hidden state, raw joints,
   host access, network, credentials, devices, or robot motion.

This is a synthetic proposal benchmark, not simulator calibration or transfer
evidence.
