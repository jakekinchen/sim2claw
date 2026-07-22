---
name: implement-repair
description: Implement and publicly evaluate one bounded GapBench candidate repair tied to a causal hypothesis. Use after localization to modify candidate JSON without crossing the frozen parameter envelope or evidence boundary.
---

# Implement Repair

1. Copy the baseline candidate to a new file under `candidate/`.
2. Change the smallest parameter set supported by the leading hypothesis.
   Leave unrelated parameters unchanged unless evidence requires otherwise.
3. Keep every value inside the exact envelope returned by `case_status`.
4. Run `run_public_evaluation` and compare candidate residuals with baseline.
5. If the candidate regresses, preserve the receipt, revise the hypothesis,
   and use the remaining public-evaluation budget deliberately.

Do not edit the case, evidence, evaluator, thresholds, skills, or tool code.
Public improvement is development evidence, not sealed success or physical
transfer.
