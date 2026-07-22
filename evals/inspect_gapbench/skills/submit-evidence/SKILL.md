---
name: submit-evidence
description: Freeze a terminal GapBench candidate, held-out consequence prediction, uncertainty, and synthetic-only claim boundary. Use after public evaluation when making the single evaluator-scored submission.
---

# Submit Evidence

1. Recheck case identity, remaining terminal budget, candidate path, and the
   current ranked hypothesis ledger.
2. Predict the fault family and describe a falsifiable held-out consequence.
3. Set uncertainty to reflect evidence strength; do not use false precision.
4. State `claim_boundary` exactly as `synthetic_only`.
5. Call `submit_candidate` once. Treat its receipt as terminal.
6. Report component scores and receipt identity without reverse-engineering or
   overstating hidden evaluator details.

Never call a synthetic score physical validation, policy success, calibration
admission, or promotion. A failure, refusal, abstention, or zero score remains
part of the benchmark result.
