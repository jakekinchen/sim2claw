# GR00T N1.7 Reward-Guided Corrective-Data Lane

Date: 2026-07-18 America/Chicago

## Bounded campaign

- This lane owns one Brev worker: `sim2claw-gr00t-guided-0718`
  (`4v9suefrt`).
- Worker type: `massedcompute_A100_sxm4_80G_DGX`, quoted at `$1.656/hour`.
- The user-authorized ceiling remains `$50.00` across the overnight Brev
  campaign. The preceding work conservatively estimated total spend below
  `$12.00`; both active lanes must keep their combined elapsed-cost estimate
  below the remaining allowance.
- This worker is deleted as soon as this lane no longer has a verified paid
  task, after preserving receipts and checking the authenticated inventory.

## Frozen artifact identities

- GR00T source: NVIDIA `n1.7-release` at
  `23ace64f17aa5015259b8609d371eb61a357c776`.
- Nominal checkpoint: `checkpoint-4000`.
- Checkpoint aggregate manifest SHA-256:
  `e89dae30e4b06af815b55e1a9e3036547eeae151463740e29f7fea8ad0b166ac`.
- Base chess task contract SHA-256:
  `473915817b3a8474f796df53e199df92031d17fad152599a1d43ccecd3f15683`.
- Renderer for deterministic development diagnostics: OSMesa.

## Strategy and proof boundary

The nominal checkpoint has high flow-sampling dispersion and failed all nine
strict deterministic receding-horizon trials. This lane tests whether a
simulator-side phase reward can identify useful actions among independent
model proposals. At each receding-horizon query it obtains a fixed number of
seeded GR00T action chunks, branches the current MuJoCo state, scores the short
consequences, restores the exact state, and executes the best model-proposed
prefix.

Proposal ranking is external assistance. A guided trajectory may establish a
task-consequence pass and supply corrective training data, but it is never a
strict learned-policy success and cannot be promoted. The frozen evaluator
reports task consequences separately from the strict verdict. Only a later
pure-policy challenger with all actions model-owned and zero assistance can
satisfy the campaign goal.

The sibling Codex lane exclusively owns inference-only proposal consensus and
sampler controls on the same nominal checkpoint. This lane owns reward-guided
selection, corrective-data generation, and any trained challenger, preventing
duplicate Brev experiments.

## Development-to-held-out order

1. Verify exact simulator state restoration and reward-contract binding
   locally.
2. Restore and hash the nominal checkpoint on the paid worker.
3. Run short training-split probes to test proposal diversity and phase-score
   direction before a full episode.
4. Tune only against development cases. Freeze a new guidance hash before any
   held-out use.
5. If guided selection earns a full task-consequence pass, preserve that
   trajectory as assisted corrective data and train one bounded challenger.
6. Evaluate the challenger through the unchanged zero-assistance consequence
   gates on separately owned held-out cases.

## Live ledger

| Event | Local time | Evidence state |
| --- | --- | --- |
| Worker requested | approximately 07:26 CDT | starting |
| Worker healthy | approximately 07:28 CDT | A100-SXM4-80GB, CUDA available, pinned GR00T source |
| Local controller validation | approximately 07:31 CDT | 26 tests passed; Ruff and diff checks clean |

Final candidate, receipt, cost, and teardown entries will be appended as the
campaign advances.
