---
name: submit-repair-evidence
description: Freeze one terminal corrective proposal with the synthetic-only claim boundary after evidence-bound public evaluation.
---

# Submit Repair Evidence

1. Confirm a hypothesis and at least one public evaluation exist.
2. Recheck the candidate's bounded task-space intent and case bindings.
3. Call `submit_repair` exactly once with
   `claim_boundary='synthetic_benchmark_only'`.
4. Report the deterministic receipt, component scores, and limitations.

Never call the receipt training admission, checkpoint promotion, learned-policy
success, posterior calibration, or physical transfer.
