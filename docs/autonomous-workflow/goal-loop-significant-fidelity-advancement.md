# Goal loop: significant fidelity advancement

Status: `STOP CONDITION SATISFIED BY RMS LANE`

## Baseline authority

- Receipt: `outputs/pawn_bg_publication_gate_v1/publication_gate_receipt.json`
- Joint RMS: 1.2955576824267467 degrees
- EE RMS: 0.012936396427477485 m
- Contact/lift/strict success: 11/2/0 of 11
- Actions: contiguous float64, byte-identical across variants

## Invariant milestones

### M1 — Residual mechanism map

Required outcome: explain which joint/phase/load signatures dominate the
remaining RMS. Verification: source-bound per-episode residual receipt with no
candidate promotion.

Result: complete. Elbow flex dominates the residual and its negative bias is
stronger in stationary/load-bearing rows and varies with pose.

### M2 — Cross-validated simulator response candidate

Required outcome: evaluate frozen bounded response families over whole-episode
folds while retaining action hashes. Verification: candidate and fold receipts,
action-invariance gate, RMS/EE advancement gates, and already-opened confirmation
used only after selection.

Result: complete. The frozen 63-candidate load-response family reduces pooled
CV joint RMS 6.461% and EE RMS 12.312%, with every fold improving and unchanged
action hashes. The selected coefficient is a disclosed search-boundary value,
not an identified physical parameter.

### M3 — Target-piece consequence comparison

Required outcome: replay the accepted response candidate through the unchanged
strict consequence evaluator and compare contact, lift, transport, release, and
success. Verification: per-episode evaluator receipts and full-vector verdict.

Result: complete and negative for promotion. Contact is unchanged, lift falls
from 2/11 to 1/11, destination-inside endings rise from 0/11 to 2/11, and strict
success remains 0/11.

### M4 — Closeout

Required outcome: accept a significant advancement or publish a bounded
terminal negative. Verification: composite receipt, deterministic tests, run
log, reviewer decision, and explicit physical/non-physical authority.

Result: complete. The paired 10,000-replicate whole-episode bootstrap has a
positive 4.398--8.540% joint-improvement interval. The receipt stops the RMS
lane while explicitly retaining the grasp/transport terminal negative.
