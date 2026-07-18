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
  `35be00ba838c0b03922ed04618f8785845faadba1e574d94e360b339ac2b04b8`.
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

The exact experiment contract is
`configs/experiments/groot_n17_flow_consensus_v1.json`. Its order is:

1. reproduce the single-proposal OSMesa baseline;
2. compare eight frozen inference arms on training-only row-zero diagnostics;
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

Local preflight passed:

- 27/27 repository tests;
- Python compilation for the server, evaluator runner, probe, and consensus
  module;
- shell syntax for both Brev launch/sweep scripts;
- JSON parsing and `git diff --check`.

## Brev and evidence ledger

| Event | State | Evidence |
| --- | --- | --- |
| Initial inventory | PASS | only separately owned `sim2claw-gr00t-guided-0718` (`4v9suefrt`) was running |
| A100 price check | PASS | known-compatible `massedcompute_A100_sxm4_80G_DGX` quoted at `$1.656/hour`; one A100-80GB |
| Consensus worker | PENDING | proposed name `sim2claw-gr00t-consensus-0718`; not yet created |
| Baseline reproduction | PENDING | exact nominal checkpoint and OSMesa hashes required |
| Training diagnostic | PENDING | no remote result yet |
| Closed-loop development | PENDING | no remote result yet |
| Held-out promotion | SEALED | cannot run until a configuration hash is frozen |
| Artifact preservation | PENDING | generated data, checkpoints, videos, and logs remain outside Git |
| Paid worker teardown | PENDING | delete this lane's worker when it no longer has a verified task |

## Authority boundary

This campaign produces synthetic simulation and learned-policy evidence only.
Training-only expert comparisons are diagnostics with no promotion authority.
All promotion episodes require model-derived actions, zero assistance, and the
unchanged separately evaluated task consequences. No result grants physical
camera, serial, servo, gateway, or motion authority.
