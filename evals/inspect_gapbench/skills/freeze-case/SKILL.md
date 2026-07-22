---
name: freeze-case
description: Verify a Sim2Claw GapBench case's frozen identity, public evidence, editable surface, budgets, and authority boundaries. Use before diagnosing, probing, or editing any GapBench candidate.
---

# Freeze Case

1. Call `case_status` with the exact case ID from the task.
2. Record the case digest, proof class, evidence IDs, editable parameter
   envelopes, probe menu, and remaining budgets.
3. Read only artifacts returned by `case_status`; never guess a path.
4. Confirm the claim boundary is synthetic and that physical authority and
   promotion authority are absent.
5. Stop if an identity changes, a digest fails, or the requested action needs
   hidden data, host access, credentials, network, devices, or robot motion.

Do not infer that a valid packet proves simulator fidelity or transfer. It
proves only that the benchmark input is frozen and internally attributable.
