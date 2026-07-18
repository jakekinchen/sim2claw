# GR00T N1.7 Receding-Horizon Placement Campaign

Date: 2026-07-18 America/Chicago

## Bounded campaign

- User ceiling across the overnight GR00T work: `$50.00`.
- This lane owns exactly one Brev worker:
  `sim2claw-gr00t-placement-0718` (`lpfsp2w5x`).
- Selected type: `massedcompute_A100_sxm4_80G_DGX`, quoted
  `$1.656/hour`.
- Cutoff: 09:00 CDT, or earlier if this lane no longer has a verified task.
- NVIDIA source remains frozen at `n1.7-release` /
  `23ace64f17aa5015259b8609d371eb61a357c776`.
- Candidate is the preserved `checkpoint-4000` selected by the previous
  held-out open-loop sweep.

The other live Brev worker belongs to the separately isolated recovery-v2
task. That lane owns contact recovery, slip/reacquisition, and distractor
geometry. This lane owns receding-horizon inference and destination,
transit, lower, and release diagnosis so the paid experiments are not
duplicates.

## Frozen hypothesis and experiment order

The checkpoint predicts 16 sampled actions per policy query. The previous
closed-loop evaluator executed all 16 actions, or 0.8 seconds at 20 Hz,
before observing again. Low held-out open-loop MSE together with rapid
closed-loop divergence is consistent with action-chunk covariate shift.
The pinned NVIDIA tree's real-robot SO-100 evaluator defaults to executing
eight actions before observing again, which independently supports testing
`8` first without changing the frozen checkpoint.

Before any additional training, evaluate the same frozen checkpoint and
held-out episodes with execution horizons `8`, `4`, `2`, and `1`. Each query
still returns the model's 16-action prediction, but only the first requested
prefix is executed before observing and querying again. Every physics action
remains model-owned and assistance remains zero.

Run the horizons in the declared order on held-out episode 0. A horizon may
advance to episodes 1 and 2 only when it improves a consequence gate over the
16-action baseline or provides a clearly distinct diagnostic result. Do not
select by training loss or diagnostic reward. The independent frozen evaluator
continues to own promotion.

If no execution horizon produces a repeatable consequence improvement,
localize the first divergence by episode phase. Train another challenger only
when that localization supports a narrow placement/transit/lower/release data
hypothesis. Blindly extending the original 5,000-step schedule is excluded
because held-out open-loop error had already plateaued.

## Frozen consequence gates

- piece rise at least 40 mm;
- final XY error at most 15 mm;
- final height error at most 5 mm;
- final upright cosine at least 0.95;
- final linear speed at most 20 mm/s;
- gripper clearance at least 35 mm;
- every other piece displaced at most 6 mm;
- no final jaw contact;
- all actions model-owned and no assistance.

## Evidence boundary

Passing open-loop error, finite loss, or diagnostic reward is not task
success. A result is promoted only if the frozen CPU/fp32 consequence
evaluator passes all gates. Partial lift or placement gains are reported as
partial evidence; a failed full verdict remains terminal negative for that
episode.

## Live ledger

| Event | Local time | State | Spend basis |
| --- | --- | --- | --- |
| Initial inventory | 04:19 CDT | recovery worker only | prior campaign approximately `$4.03` |
| Placement worker created | approximately 04:21 CDT | starting | `$1.656/hour` |
| Placement worker ready | approximately 04:23 CDT | healthy shell | `$1.656/hour` |
| Placement server stopped | approximately 06:35 CDT | GPU idle; token absent | placement estimate below `$3.90` |
| Placement worker deleted | approximately 06:39 CDT | Brev inventory empty | campaign estimate below `$12.00` |

Final checkpoint, rollout, consequence, artifact-hash, cost, and teardown
results will be appended before this campaign closes.

## Pre-sweep diagnostic

The preserved checkpoint-4000 trajectories for held-out episodes 0, 1, and 2
were compared row-for-row with their accepted expert trajectories. In all
three cases, learned state L2 divergence exceeded `0.1` at sampled row 1;
action L2 error already exceeded `0.25` at row 0. The failure therefore starts
during initial stand-off rather than first appearing at destination placement.
This is diagnostic evidence only, but it makes the receding-horizon sweep a
better first intervention than a placement-only retrain.

For held-out episode 0, checkpoint 4,000 improved stand-off action MAE from
`0.2581` at checkpoint 250 to `0.1861`, consistent with its observed lift gain.
However, whole-episode closed-loop action RMSE worsened from `0.4451` to
`0.4988`, and transit action MAE worsened from `0.3172` to `0.4554`. This is
not a promotion comparison because both episodes are terminal negatives; it
is further evidence that compounding closed-loop drift, rather than optimizer
step count alone, is the next variable to test.

## Determinism localization

Reset-time Python, NumPy, PyTorch, and CUDA seeds did not make the original
EGL runs reproducible. Exact repeats began with different row-0 actions even
when the full MuJoCo `qpos`, `qvel`, and `xpos` hashes matched. The GR00T
flow-matching action head uses global `torch.randn`; no held generator,
CUDA-graph wrapper, or `torch.compile` path was found. The seeded server was
therefore changed to derive and apply a fresh query seed from
`(episode_seed, sample_step)` and to record RNG, observation, state, and action
hashes at every request.

Repeated EGL renders still differed by one least-significant channel value.
Disabling GL dithering, reducing offscreen samples, disabling shadows, and
render warmups did not remove that variation. A diagnostic OSMesa backend was
then installed on this worker. Three fresh evaluator processes produced the
same full state hash, frame hash, and action hash. Two complete held-out
episode-0, horizon-8 canaries in fresh evaluator processes were bitwise equal:

- trajectory SHA-256:
  `98a4743e447ed8c7633a37faf0c3d635f0c00146c689711bc0ec8145ee38c34a`;
- query-frame sequence SHA-256:
  `6b3f69cd277195d69b2453a70969406a0caa6470f1837ef074acb8c509698205`;
- query-seed sequence SHA-256:
  `129549b90e9a91853c879cf2511f9cee1a9cf3cde2021ab3e7ad317876139006`.

OSMesa is a versioned diagnostic backend, not a replacement promotion
authority. Its initial image differs from the frozen EGL surface by mean
absolute error `0.46986`, PSNR `40.55 dB`, and maximum channel delta `81`.
The controlled sweep below is therefore a deterministic causal diagnostic;
all consequence verdicts remain terminal negatives under the frozen gates.

## Controlled receding-horizon result

The selected checkpoint was tested on held-out episode 0 with query seeds
`0`, `1`, and `2` at execution horizons `16`, `8`, and `4`. Horizon `2` and
`1` were not continued after the deterministic arms showed no consequence
gain and the smaller horizons increased instability. All nine episodes used
model-owned actions with zero assistance.

| Horizon | Success | Lift gate | Final XY | Upright | Board safety | Median whole-action MAE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 16 | 0/3 | 1/3 | 0/3 | 0/3 | 0/3 | `0.300` |
| 8 | 0/3 | 1/3 | 0/3 | 0/3 | 0/3 | `0.193` |
| 4 | 0/3 | 1/3 | 0/3 | 0/3 | 0/3 | `0.323` |

Horizon 8 had the lowest median action error, particularly from lift through
release, but did not improve a single full-task consequence verdict. Every
arm exceeded action L2 `0.1` at row 0 and state L2 `0.1` at row 1. The failure
is therefore not placement-only and is not repaired by more frequent policy
queries. No horizon is promoted.

The per-seed results are:

| Seed | H | Rise m | Final XY m | Height error m | Upright cosine | Other-piece displacement m |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 16 | 0.021109 | 0.217067 | 0.002287 | -0.09933 | 78.9528 |
| 0 | 8 | 0.044201 | 0.198463 | 0.002287 | -0.09934 | 0.312022 |
| 0 | 4 | 0.075481 | 1.219700 | 0.786192 | -0.09931 | 0.397278 |
| 1 | 16 | 0.015036 | 0.151679 | 0.013742 | -0.10429 | 0.447231 |
| 1 | 8 | 0.016477 | 0.379546 | 0.786194 | -0.09895 | 0.289548 |
| 1 | 4 | 0.027035 | 0.501423 | 0.786196 | -0.09903 | 0.318457 |
| 2 | 16 | 0.041251 | 0.733988 | 0.786196 | -0.09904 | 0.020125 |
| 2 | 8 | 0.017124 | 0.579554 | 0.786197 | -0.09895 | 0.192648 |
| 2 | 4 | 0.026869 | 0.183561 | 0.003754 | 0.32152 | 0.263093 |

## Training-challenger decision

The original NVIDIA fine-tune already applied substantial color jitter
(`brightness=0.3`, `contrast=0.4`, `saturation=0.5`, `hue=0.08`) while leaving
the Cosmos visual encoder frozen. Because row-0 actions changed under small
render differences, a short `tune_visual=true` continuation was considered.
Fable was consulted in the repo-correct Claude Code session and advised two
zero-training gates before spending more GPU time.

The evaluator-owned perception gate compared the three first predictions with
the expert action. Their centroid is `0.63620` L2 from the expert, but the
maximum seed-to-seed separation is `1.01885` and mean seed distance from the
centroid is `0.46941`. This is wide sampling dispersion, not a tight but
systematically biased prediction cluster. Gate A fails.

For Gate B, the exact held-out dataset video frame 0 was decoded and queried
with the same initial robot state and seeds. Despite differing from the fresh
OSMesa frame by MAE `5.26302` and PSNR `20.66 dB`, it did not improve row-0
prediction: median action MAE worsened from `0.23793` to `0.24527`. Gate B
also fails. The resulting `perception-gate.json` SHA-256 is
`a8bda7b272827a5036a92ad754796f6cc464a6a719ad9113187068f28aef64a5`.

Because both pre-training gates fail, visual unfreezing is not a justified
challenger. A generic continuation is also excluded by the prior loss plateau,
and the distinct recovery lane independently reports 0/120 on recovery-v2
plus 0/20 on its unchanged v1 regression. No additional checkpoint is trained.
This conserves paid compute and makes the next evidence-backed axis explicit:
reduce flow-sampling dispersion or collect closed-loop corrective data rather
than modifying the visual encoder on the same demonstrations.

## Preserved evidence

The placement evidence root is outside Git at
`/Users/kelly/Documents/Codex/sim2claw-groot-n17-20260718/evidence/placement-overnight`.
The deterministic rollout bundle is
`deterministic-osmesa-evidence.tgz`, SHA-256
`8145df34cc54a667010b15b4a073d1786e81bab389713ba0c60840fd1dec60b3`.
It includes the nine controlled trajectories and videos, two bitwise canaries,
renderer probes, the query-seeded policy log, and immutable receipts. The
dataset-frame probes, exact frame, expert episode parquet, phase reports, and
perception-gate report are stored alongside it.

The encompassing `placement-final-evidence.tgz` archive is 8.4 MiB with
SHA-256
`41b363d1971430236881e80e5495f76f3e06f447ebb626a3ddabf8ee4723ccc0`.

## Cost and teardown closeout

The placement worker ran for approximately 2 hours 18 minutes at the quoted
`$1.656/hour`, or less than `$3.90` by elapsed-time arithmetic. Combining the
`$4.03` pre-placement campaign estimate with both later lane runtimes gives a
conservative overall estimate below `$12`, well inside the authorized `$50`
ceiling. This is an estimate because the CLI inventory does not expose an
invoice-grade charge total.

Before teardown, the current policy log and all new perception-gate artifacts
were copied locally and hashed. The GR00T server was stopped, `nvidia-smi`
showed no compute process, and `~/.cache/huggingface/token` was absent. The
separate recovery task completed its own artifact transfer, pushed commit
`d76443c`, and deleted its independently owned worker. This lane then deleted
`sim2claw-gr00t-placement-0718` (`lpfsp2w5x`). The final authenticated
`brev ls --json` returned `"workspaces": null`; no Brev resource remains.
