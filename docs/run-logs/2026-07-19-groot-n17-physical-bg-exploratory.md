# GR00T N1.7 physical B--G exploratory run

Status: 5,000-step fine-tune complete; checkpoint 5000 selected open-loop;
frozen closed-loop simulator evaluation terminal-negative at 0/12

Date: 2026-07-19 America/Chicago

## Scope

This is a bounded exploratory fine-tuning probe over all 18 finalized physical
B--G teleoperation source recordings. It is an explicit non-promotion lane.
The recordings remain `physical_teleoperation_source_unqualified`, their
training admission remains pending deterministic replay and a separate
evaluator, and the dataset receipt records that its rows are not evaluator
admitted. Training loss is not a policy result.

No held-out rows, raw failed outcomes, prior 72 mm recordings, generated
episodes, or repeated episode weights enter this dataset. Each of the 18 source
episodes appears exactly once.

## Frozen local input

- experiment: `configs/experiments/groot_n17_physical_bg_exploratory_v1.json`;
- dataset: `datasets/groot_n17_physical_bg_exploratory_20260719` (ignored);
- unique episodes: 18;
- frames: 7,741;
- dataset receipt SHA-256:
  `2b76ba47a2d39bc82bd9646e0b05d55c4361abf843b93e6fc92c17d772fe0e19`;
- payload manifest SHA-256:
  `4a34694eb1bde282256ba95d57de8529c5be68fa2487be115468af9271f8e9be`;
- transferred dataset archive SHA-256:
  `4ea813dc01463cd6faa17f62e748044fbd99feabe9779013cd71742cd1eca67e`.

The local structural preflight passed all 18 parquet/video episode pairs and
all 7,741 rows. Python compilation passed. Ruff was unavailable in the frozen
project environment and is not claimed.

## Paid-compute boundary

- GR00T base: `nvidia/GR00T-N1.7-3B` at the pinned project revision;
- initial smoke-probe bound: 500 optimizer steps;
- owner-authorized same-day continuation bound: 5,000 optimizer steps;
- save interval: 500;
- per-invocation training timeout: 1,200 seconds;
- no automatic retry;
- successful worker: 1 x Denvr A100-SXM4-80GB at a quoted $1.68/hour;
- retain the run receipt, logs, loss history, and compact checkpoint manifests;
- retain the worker through the authorized same-day window, then delete it at
  23:55 CDT and verify Brev inventory.

The first provider allocation, `sim2claw-groot-bg-0719`, never became
reachable and reached provider status `UNHEALTHY`; it was deleted before any
setup, model download, or GPU process. The second allocation,
`sim2claw-groot-bg-0719b`, was healthy but exposed only a CUDA 12.4 driver image
without a configured CUDA 12.8 apt repository. Its setup stopped before clone,
model download, or training and the worker was deleted. The setup script was
then repaired to add NVIDIA's official repository and install the exact 12.8
toolkit. Three later campaign allocations (`sim2claw-groot-bg-0719c`,
`sim2claw-groot-bg-h100-0719`, and `sim2claw-groot-bg-h200-0719`) became
provider-unhealthy before SSH and were deleted. None ran training.

The successful allocation was `sim2claw-groot-bg-denvr-0719`. Its frozen
runtime was NVIDIA source commit
`23ace64f17aa5015259b8609d371eb61a357c776`, PyTorch `2.7.1+cu128`, CUDA 12.8,
MuJoCo 3.10.0, and an A100-SXM4-80GB. The base and processor snapshots were
downloaded at their pinned revisions and then used offline; the temporary model
download token was removed before training.

Remote preflight passed NVIDIA's episode loader over all 18 episodes and 7,741
decoded 256 x 256 RGB frames. It found 7,471 valid horizon-16 starts, zero
held-out rows, and preserved `all_training_rows_evaluator_admitted=false` and
`training_cannot_promote=true`.

## Training result

The first invocation used episode sampling rate 1.0 and stopped before optimizer
step 1: 18 episode pieces could not fill NVIDIA's requested 59 balanced shards.
That terminal-negative pre-step log is retained. The corrected invocation used
the pinned 0.1 sampling rate, producing 59 balanced shards from 7,471 starts
(mean shard length 126.6271, standard deviation 7.9017).

The corrected run completed 500 of 500 optimizer steps with exit code 0 in
162.4937 seconds (3.077 steps/second). It trained 1,620,515,968 of
3,144,016,000 parameters. Aggregate training loss was 0.8827517547607422; the
reported step-500 window loss was 0.6039. These numbers establish successful
optimization only. They do not establish held-out, replay, simulation, or
physical policy performance.

Checkpoint `checkpoint-500` contains three weight shards:

- `model-00001-of-00003.safetensors`:
  `cbcaea5ee88f1e0f1465043920a2647c67e7de17d24adfd1c477742a6168edec`;
- `model-00002-of-00003.safetensors`:
  `a6377e57a8425a307fde37ec813c3721810f8ddf5f9d10f051bc4f7e7c2914d9`;
- `model-00003-of-00003.safetensors`:
  `e267985dd8e20d7e156c6cc0ef263ce31dec6208a06c67955311b6a010e8f694`.

The compact evidence archive is stored outside Git at
`/Users/kelly/Documents/Codex/sim2claw-groot-n17-physical-bg-exploratory-20260719/groot-n17-physical-bg-evidence.tgz`
with SHA-256
`903580c0e9cd523c6a3b0a352117f5188d2e85e6f21a9c721e207da8a9317aeb`.
The attempted local checkpoint-500 transfer did not finish its first and third
weight shards and is not a usable checkpoint. It is retained only as partial
transfer evidence and was never used for evaluation.

## Same-day continuation

At the owner's direction, the healthy worker remained active for same-day
continuation. NVIDIA's trainer resumed from global step 500 and completed the
planned 5,000-step sweep with checkpoints every 500 steps and a cloud retention
limit of one. Checkpoints 2,000, 3,000, 4,000, and 5,000 were compared; protected
hard-link snapshots prevented retention from erasing the active comparison
baseline. The run used no W&B upload and granted no robot authority.

An interruption during checkpoint-2500 serialization produced an incomplete
directory with no index, processor state, or trainer state. Preflight rejected
it before inference and it was removed. At step 4,000 NVIDIA's redundant final
run-root save exhausted disk after the complete checkpoint directory had
already been written; the redundant partial copy was removed and checkpoint
4000 then passed a full 16-file manifest. Checkpoint 5000 completed normally
and passed the same manifest gate.

## Open-loop diagnostic selection

The untouched GR00T base cannot be evaluated with this custom embodiment:
NVIDIA correctly rejects `NEW_EMBODIMENT` because the base checkpoint has no
custom SO-101 head. The numeric comparison therefore begins at checkpoint 2000.

The selection matrix used diagnostic seed 20260719, action horizon 16, all 18
training trajectories, and a common 317-step window. This is an in-sample
open-loop action diagnostic, not held-out generalization or task-consequence
evaluation.

| Checkpoint | Mean MSE | Mean MAE | Selection note |
| --- | ---: | ---: | --- |
| 2000 | 0.00847435 | 0.06341812 | comparison baseline |
| 3000 | 0.00800934 | 0.06163142 | mixed; four instruction groups regressed |
| 4000 | 0.00590446 | 0.05286571 | all nine observed groups improved vs 2000 |
| 5000 | 0.00467273 | 0.04619851 | selected; all nine groups improved again |

Checkpoint 5000 reduces MSE by 44.86% and MAE by 27.15% relative to checkpoint
2000. All 18 trajectories and all nine observed receipt-label instruction
groups improve. The weakest individual trajectory still improves 24.27% MSE
and 15.65% MAE; the weakest group improves 29.49% MSE and 17.57% MAE. This is
the strongest result in the bounded sweep and is the selected exploratory
checkpoint.

The label surface is not the full 12-skill product benchmark. The receipt-based
dataset contains nine distinct instructions, includes five repeated E1-to-F1
rows outside the B--G rank-1/rank-2 product moves, and preserves eleven known
folder/receipt conflicts rather than silently relabeling them. Exact held-out,
closed-loop simulation, replay, and physical consequence claims remain closed.

## Counterfactual language diagnostic

To test whether checkpoint 5000 merely followed the visual/state trajectory or
responded to requested move text, a hard-linked derivative kept every image,
state, and ground-truth action unchanged while deterministically rotating all
nine observed instructions. Every one of the 18 episodes received a wrong
instruction. The task mapping is bound by SHA-256
`e5accf425feaa3afa7ade33afdb7700699f130fd7ddcc65055a3fba7e9783977`;
the remote derivative receipt file is bound by SHA-256
`26a81b9b4965861bbb7cc184aa607978455a073c011d74b0fb5732713b879865`.

Under identical seed, 317-step window, and action horizon, the wrong-instruction
condition produced MSE 0.00549396 and MAE 0.05031039. Relative to that condition,
the correct instructions reduce MSE by 14.95% and MAE by 8.17%. Correct text has
lower MSE on 16/18 trajectories and on all nine instruction-group aggregates;
it has lower MAE on 16/18 trajectories and eight of nine group aggregates.

This establishes controlled in-sample language sensitivity in the desired
direction. It does not establish unseen-instruction compositionality, held-out
episode generalization, simulated task consequence, or physical execution.
The raw wrong-instruction log, plot, derivative receipt, and comparison are in
the local `evaluation/counterfactual-language-317-v1` artifact directory.

The selected checkpoint manifest has canonical payload SHA-256
`caf75b08192e3274d1c73dcadaa26e06fbf2f55778b25ac9349c1f16403437f1`.
Its three weight shard SHA-256 values are:

- `cbcaea5ee88f1e0f1465043920a2647c67e7de17d24adfd1c477742a6168edec`;
- `bfdcbf02510dca03e04be784814f958eff9130d1356271d50af65752610d430e`;
- `878bdbc627f229748ae95040472c9bb3c19a8a203ad15198b3ec4fb685f0d466`.

The full checkpoint transfer target is
`/Users/kelly/Documents/Codex/sim2claw-groot-n17-physical-bg-exploratory-20260719/checkpoint-5000`.
The completed local checkpoint contains 16 files and 12,583,271,153 bytes. Its
locally regenerated manifest is byte-for-byte identical to the remote manifest,
including canonical payload SHA-256
`caf75b08192e3274d1c73dcadaa26e06fbf2f55778b25ac9349c1f16403437f1`.
Comparison receipts and plots are under its sibling `evaluation` directory.
The compact post-evaluation evidence archive (logs, plots, comparison receipts,
and local checkpoint manifest, but not checkpoint weights) is
`groot-n17-physical-bg-evidence-v2.tgz`, SHA-256
`c3b1c270d3c558ed660e98aff149fe3286c350415a273388c04994994524a4b0`.

## Frozen closed-loop pawn-centering evaluation

Checkpoint 5000 was then run model-owned in the current MuJoCo simulator over
the frozen 12-skill B--G rank-1/rank-2 centering order and seed 190719. The
runner used the scene `workcell` camera, nominal uncalibrated contact prior,
317 actions at 20 Hz, five deterministic diffusion proposals, median proposal
consensus, four inference timesteps, and overlapping eight-step queries. The
complete 16-file checkpoint inventory and the evaluator implementation were
hash-verified before inference; the implementation was reverified afterward.

The result is a terminal negative:

- task-consequence success: 0/12;
- policy success: 0/12;
- forward success: 0/6;
- reverse success: 0/6;
- selected-piece jaw contact: 0/12;
- action clipping: 0 rows in every case;
- mean diagnostic reward: -0.89999979;
- final center distance: approximately 44.45 mm in every case, exactly one
  square away because the selected pawn never moved;
- maximum selected-pawn rise: below 0.00015 mm in every case;
- wrong-piece contact and collateral-gate failure: 12/12, with maximum other
  piece displacement ranging from 54.86 mm to 310.68 mm.

The uniform failure is not a centering-threshold near miss. The model emits
finite, in-range actions, but the current simulator reset and visual domain do
not match the physical training distribution. For example, the simulator's
six-joint reset is `[-0.2233, 0.6556, -0.5257, 0.7046, 1.9648, 0.45]`, while
the first B1 training state is approximately
`[-0.1243, -1.8642, 1.7192, -1.7637, -2.0721, 0.0187]`. The model therefore
returns physical-source-like joint targets that drive the simulator arm into
the wrong part of the scene.

The immutable report is outside Git at
`/Users/kelly/Documents/Codex/sim2claw-groot-n17-physical-bg-exploratory-20260719/evaluation/pawn-centering-checkpoint5000-full-v1/report.json`.
Its file SHA-256 is
`6611818631950ba3643e50178fadf3e0ebc999a68d4c82deb37f5b077bff0056`;
its canonical payload SHA-256 is
`3a2dbcd852e723cefa1ccdc62f3c6c9aaa32ba30cd6581c96295ac520be1b597`.
Per-case traces, action arrays, initial/final frames, and the exact runner bytes
are retained beside it.

## Training-source-aligned bridge diagnostic

A separate B1-to-B2 diagnostic tested the already-frozen `stage_d_lift`
source-fit candidate without altering the frozen 0/12 result. This path used
the training-fitted board pose and fixed joint-zero offsets, expanded joint
ranges, the owner-corrected visual-only layout, the proposal-only C922 angle
transfer rotated like the exported training video, and the median initial B1
training state. It did not open held-out rows. Because these inputs are
training-conditioned and explicitly lack evaluator authority, this is not a
frozen policy evaluation and cannot promote the checkpoint.

The bridge removed the unsafe-looking collateral behavior but did not recover
the skill:

- selected-piece contact: false;
- lift: false;
- final center distance: 44.45 mm;
- action clipping: zero;
- maximum other-piece displacement: 0.000167 mm;
- diagnostic reward: 0.10000005;
- frozen policy success is intentionally suppressed because the bridge counts
  as assistance.

This isolates the next bottleneck more tightly: the fitted state/action and
camera bridge can keep the rollout collision-free, but checkpoint 5000 still
does not map the rendered simulator image to a target-reaching action. The
aligned report is outside Git at
`/Users/kelly/Documents/Codex/sim2claw-groot-n17-physical-bg-exploratory-20260719/evaluation/pawn-centering-checkpoint5000-stage-d-aligned-smoke-v1/report.json`,
with file SHA-256
`e3215aa5361391117521d9a98bb8f724ff2bc566da7cbe2a9ddb6ad02b011c17`
and canonical payload SHA-256
`7934a4faca7539f1a690aa5b9dba1ced2918e0261dc998202eafbb1f3142ad96`.

## End-of-day worker guard

A separate local launchd guard is loaded as
`com.codex.brev-cleanup.sim2claw-groot-bg-denvr-0719`; at 23:55 CDT on
2026-07-19 it deletes the exact campaign worker, records the resulting Brev
inventory under `/Users/kelly/Documents/Codex/brev-cleanup-logs`, and retries
every 15 minutes after the cutoff if authentication or deletion fails. It
removes its own script and plist only after authenticated inventory confirms
the named worker is absent. The pre-existing stopped CPU workspace
`nemoclaw-e3fca7` is outside this cleanup target.

The Brev API session expired after evaluation, so API deletion requires renewed
authentication. An independent remote systemd timer
`codex-brev-midnight-shutdown.timer` is active for 04:55 UTC (23:55 CDT) as a
power-down fallback. Power-down is not equivalent to authenticated Brev
deletion, so inventory deletion remains an explicit closeout requirement.
