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
| Corrected dataset exported | approximately 11:15 CDT | 13 episodes, 4,719 frames, 13/13 source and exact-replay gates pass |
| NVIDIA loader preflight | approximately 11:17 CDT | 13 episodes, 363 rows in first episode, all configured modalities loaded |
| Bounded challenger started | approximately 11:18 CDT | fresh optimizer/output, checkpoint-4000 initialization, 1,000-step cap |

Final candidate, receipt, cost, and teardown entries will be appended as the
campaign advances.

## Control-rate counterexample and corrective-data decision

Before spending a full episode on best-of-16 guidance, the exact recorded
training episode-0 actions were replayed using the learned-policy evaluator's
execution semantics: one float32 command held for ten 5 ms physics steps. The
sampled replay failed despite the original 200 Hz scripted trajectory passing:
only 15.0 mm rise, 463.9 mm final XY error, upright cosine -0.1004, and final
speed 104.5 mm/s. A perfect predictor of those labels therefore could not
reproduce their source consequence.

The corrective dataset contract is frozen at
`configs/tasks/chess_pick_place_groot_zoh_dataset_v2.json`. It generates a
planning pass, then records observations from an exact float32 20 Hz
zero-order-hold replay of the resulting commands. Admission requires that this
replay pass every unchanged gate. Selection used only the 24 training rows;
held-out cases and seeds were not inspected. Thirteen source episodes pass and
are admitted: `0, 1, 8, 11, 14, 16, 17, 18, 19, 20, 21, 22, 23`.

The first admitted replay establishes the mechanism: 70.0 mm rise, 10.4 mm
final XY error, upright cosine effectively 1.0, final speed 0.006 mm/s, 139.8
mm gripper clearance, and sub-micrometer other-piece displacement. This is
scripted synthetic training evidence only.

An attempted Linux export was rejected at its first frozen gate and its
incomplete dataset directory was deleted. The source, MuJoCo version (3.10.0),
and float32 commands matched the Mac run, but the x86_64 planning pass differed
from arm64 at approximately 1e-5 joint radians and contact dynamics diverged:
15.0 mm rise, 99.6 mm final XY error, and upright cosine -0.099. Dataset
generation is therefore bound to the separately owned Mac CPU evaluator
runtime; the receipt records platform, Python, NumPy, and MuJoCo versions. The
resulting files are transferred byte-for-byte to CUDA training. This does not
change the independently executed Linux policy promotion gate.

The completed raw dataset receipt SHA-256 is
`298d9b143ac7c4e5baa8a30952e53cd537c64f072cd5d466c7d0515ac0f75619`;
its canonical zero-order-hold contract SHA-256 is
`238a9e4533f926314675bab94e5d228f238d0757e1f0810b8b8cbe0e97a26804`.
An `rsync --checksum --dry-run` after transfer reported no differences.
NVIDIA's pinned loader accepted all configured state, action, video, and
language modalities before training began.

One bounded challenger is pre-registered: initialize model weights from the
byte-verified nominal checkpoint-4000 into a new run with a fresh optimizer;
change only the training dataset to the replay-aligned contract; keep the
original trainable set, augmentation, batch size, learning rate, state dropout,
and NVIDIA source; cap at 1,000 steps with checkpoints every 250. Strict
promotion remains a separate zero-assistance held-out consequence evaluation.
