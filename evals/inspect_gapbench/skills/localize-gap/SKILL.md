---
name: localize-gap
description: Diagnose a Sim2Claw GapBench reality gap by aligning public dataset and simulator evidence, finding the first divergence, and submitting ranked causal hypotheses. Use after freezing a case and before selecting a probe or repair.
---

# Localize Gap

1. Read the dataset-support and development-rollout artifacts.
2. Compare baseline predictions with observations over phases and feature
   directions. Locate the earliest repeatable residual pattern.
3. Maintain competing hypotheses from the allowed family list. Distinguish
   correlation from mechanism and note non-identifiable alternatives.
4. For every ranked hypothesis provide:
   - contiguous rank;
   - mechanism;
   - cited public evidence;
   - a prediction that separates it from the next hypothesis;
   - uncertainty in `[0, 1]`; and
   - explicit abstention when evidence is insufficient.
5. Submit the ledger with `submit_hypotheses` before a terminal candidate.

Prefer a small ranked ledger with falsifiable predictions over a long list of
plausible stories.
