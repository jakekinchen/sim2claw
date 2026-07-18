# GR00T N1.7 Flow-Consensus Campaign

Date: 2026-07-18 America/Chicago

## Lane boundary

- Branch: `codex/gr00t-n17-flow-consensus`.
- Isolated worktree: `/Users/kelly/Developer/sim2claw-dispersion`.
- Committed base: placement diagnostic commit `7c8eb31`.
- This lane owns inference-only action consensus, robust aggregation, and
  bounded flow-noise controls with zero assistance.
- The separate reward-guided lane owns multi-proposal geometric branching,
  assisted corrective-data generation, and any resulting trained challenger.
- This lane must not modify the reward-guided worktree or its Brev worker.

The division was acknowledged by the other lane before this campaign began.
Only a zero-assistance configuration with repeated full held-out consequence
passes may be shared as a positive result.

## Frozen identities

- Nominal checkpoint-4000 aggregate manifest SHA-256:
  `e89dae30e4b06af815b55e1a9e3036547eeae151463740e29f7fea8ad0b166ac`.
- NVIDIA source: `23ace64f17aa5015259b8609d371eb61a357c776`
  (`n1.7-release`).
- Cosmos snapshot: `9ce19a195e423419c349abfc86fd07178b230561`.
- Base task contract canonical SHA-256:
  `473915817b3a8474f796df53e199df92031d17fad152599a1d43ccecd3f15683`.
- Flow-consensus experiment SHA-256:
  `4558ccb360ecb58315c56d069b4836314a90ac488e6c848d2bd958d3106f4f8d`.
- Waypoint-execution v2 experiment SHA-256:
  `6fd12566e33c992994f74d7f68ab9a8c6b8796de9c7e4d5215658d99efc78b33`.
- Temporal-overlap v3 experiment SHA-256:
  `a07ea6b50d492511ab98720ae0b1ae44534a8a2fa66eff9e19d56d3d2424e458`.
- Deterministic diagnostic renderer: `MUJOCO_GL=osmesa` and
  `PYOPENGL_PLATFORM=osmesa`.
- OSMesa is a versioned deterministic diagnostic backend, not a new promotion
  authority.

The distinct recovery-v2 checkpoint-4000 is excluded from every comparison.
The CPU/fp32 consequence gates remain unchanged.

## Hypothesis and frozen order

The prior controlled placement sweep localized wide flow-sampling dispersion
and row-zero action divergence. Receding horizons alone produced no consequence
gain, while visual-unfreeze preconditions failed. This lane tests whether a
fixed deterministic set of complete model proposals can produce a more stable
action chunk without geometric selection or expert actions at evaluation time.

During checkpoint transfer, the reward-guided lane reported that exact nominal
training rows are terminal-negative under the learned evaluator's 20 Hz
zero-order hold. A local training-only causal replay reproduced that result and
isolated a second, nonredundant inference defect: the clean-room generator
executed a 200 Hz phase-local ramp but recorded only every tenth target. Exact
float32 source waypoints passed only 2/24 training episodes under sample hold;
deterministic same-phase linear reconstruction passed 22/24 with unchanged
gates. The diagnostic artifact is outside Git at
`/Users/kelly/Documents/Codex/sim2claw-groot-n17-consensus-0718/training-waypoint-replay/summary.json`
(SHA-256 `54ec5155...ee0f`) and accessed zero held-out rows.

The separately frozen waypoint-execution v2 contract reconstructs only the
unsaved targets between current and next model-produced waypoints. It holds at
known phase boundaries from the frozen task schedule, performs no expert or
geometric action selection, uses zero assistance, and leaves every consequence
gate unchanged. The already-frozen consensus canary and training-only probe
remain bounded; learned closed-loop priority moves to v2 after the probe ranks
the stochastic arms. Training development renders only policy-query frames to
avoid spending CPU time on video-only frames; every policy observation remains
rendered. Compatibility and sealed promotion retain full-frame cadence.

The exact experiment contract is
`configs/experiments/groot_n17_flow_consensus_v1.json`. Its order is:

1. reproduce the single-proposal OSMesa baseline;
2. compare ten frozen inference arms on training-only row-zero diagnostics;
3. advance at most two nonbaseline arms to training closed-loop evaluation;
4. freeze the winning configuration hash only after at least two unchanged-gate
   training consequence passes; and
5. open the sealed four-episode, two-inference-seed held-out promotion suite.

The minimum positive claim requires the same held-out episode to pass every
unchanged gate for both sealed inference seeds. A robust challenger target is
at least six of eight held-out consequences. Rerolling or selecting a proposal
with geometric/expert error during evaluation is forbidden.

## Implementation preflight

The action wrapper preserves the original seeded result as proposal zero.
Additional proposal seeds are versioned hashes of episode seed, sample step,
and proposal index. `medoid` selects one complete model-produced chunk;
`median`, `mean`, and `trimmed_mean` aggregate only model-produced chunks. The
bounded noise scale multiplies the flow head's sampled `torch.randn` latent for
one inference call and restores the original function immediately afterward.
Pinned-source inspection confirmed that the action head initializes the chunk
with `torch.randn` and uses four Euler flow-inference steps by default. The
same per-episode receipt also controls a bounded one-to-sixteen step count;
the frozen matrix adds only two eight-step arms.

Local preflight passed before remote execution:

- 41/41 repository tests, including analyzer rejection of held-out probes and
  assisted or incomplete closed-loop development evidence plus action-adapter
  phase-boundary behavior and causal temporal-overlap checks;
- Python compilation for the server, evaluator runner, probe, and consensus
  module;
- shell syntax for both Brev launch/sweep scripts;
- JSON parsing and `git diff --check`.

## Learned development results

The exact single-proposal baseline canary reproduced the prior deterministic
episode byte-for-byte and remained terminal negative: 44.201 mm maximum rise,
198.463 mm final XY error, a tipped rook, and 312 mm king displacement. The
complete 60-cell training-only row-zero proposal probe selected coordinate
median aggregation at K=5 with noise scales 1.0 and 0.5. Its summary SHA-256 is
`09f9a3f4...58d`; it has no promotion authority and accessed no held-out rows.

Waypoint v2 then evaluated the baseline and both shortlisted arms on the frozen
18-cell training matrix. Every arm had 0/6 full consequence passes, 0/6 final
XY passes, and 0/6 upright passes, so held-out remains sealed and no winning
configuration exists. The best nonbaseline arm was exactly K=5, coordinate
median, noise scale 0.5, four flow steps, and execution horizon eight. It
produced 2/6 lift passes and 5/6 board-safety passes. This is the one bounded
setting shared with the distinct corrected-checkpoint lane; it is not a
positive pick-and-place result. The v2 summary SHA-256 is
`8be1507f...39ab`. Its complete archive is preserved outside Git at
`/Users/kelly/Documents/Codex/sim2claw-groot-n17-consensus-0718/waypoint-v2-development-evidence.tgz`
with matching local/remote SHA-256 `b11171ad...aedb`.

The nonredundant v3 hypothesis is now frozen before learned evaluation. It
keeps that exact best v2 proposal/sampler setting and tests only causal temporal
overlap: H=8 mean over at most two model predictions, and H=4 coordinate median
over at most four. No future observation, expert action, geometry action, or
assistance may enter the aggregate. The same linear same-phase physics adapter,
renderer, training rows, seeds, consequence gates, and promotion gate remain
fixed. V3 may open held-out only if one arm produces at least two full training
consequence passes.

## Brev and evidence ledger

| Event | State | Evidence |
| --- | --- | --- |
| Initial inventory | PASS | only separately owned `sim2claw-gr00t-guided-0718` (`4v9suefrt`) was running |
| A100 price check | PASS | known-compatible `massedcompute_A100_sxm4_80G_DGX` quoted at `$1.656/hour`; one A100-80GB |
| Consensus worker | READY | `sim2claw-gr00t-consensus-0718` (`50abriamr`), one A100-SXM4-80GB at `$1.656/hour`; driver 580.126.09, compute capability 8.0 |
| Pinned runtime setup | PASS | NVIDIA source `23ace64f`; Torch 2.7.1+cu128 reports CUDA available; FFmpeg 4.4.2; libosmesa6 `23.2.1-1ubuntu3.1~22.04.4` |
| Source/config upload | PASS | remote flow-consensus experiment SHA-256 matches `4558ccb3...f8d`; remote scripts compile in the pinned GR00T runtime |
| Checkpoint restore | PASS | all 16 files match local; shard hashes `cbcaea5e...edec`, `e0f46753...f14e`, and `fcab36db...8fb` |
| Constructor dependency | PASS | pinned `nvidia/Cosmos-Reason2-2B` constructor cache resolved through the secured HF token; subsequent inference can remain cached |
| Baseline reproduction | PASS/TERMINAL NEGATIVE | exact deterministic hashes reproduced; 44.201 mm rise, 198.463 mm XY, tipped rook, 312 mm king displacement |
| Training diagnostic | PASS/NON-PROMOTING | complete 60-cell row-zero matrix; K=5 median noise 1.0 and 0.5 shortlisted |
| Waypoint v2 development | COMPLETE/TERMINAL NEGATIVE | 18/18 training cells; all arms 0/6 task passes; best nonbaseline K=5 median noise 0.5 had 2/6 lift and 5/6 safety passes |
| Temporal v3 development | FROZEN/PENDING | two-arm causal-overlap matrix; experiment `a07ea6b5...e458`; no learned row run yet |
| Held-out promotion | SEALED | cannot run until a configuration hash is frozen |
| Artifact preservation | PARTIAL | baseline, row-zero, waypoint replay, and v2 evidence are byte-preserved outside Git; v3 pending |
| Paid worker teardown | PENDING | delete this lane's worker when it no longer has a verified task |

## Authority boundary

This campaign produces synthetic simulation and learned-policy evidence only.
Training-only expert comparisons are diagnostics with no promotion authority.
All promotion episodes require model-derived actions, zero assistance, and the
unchanged separately evaluated task consequences. No result grants physical
camera, serial, servo, gateway, or motion authority.
