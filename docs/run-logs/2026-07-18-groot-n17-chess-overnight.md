# GR00T N1.7 Dynamic Chess Overnight Campaign

Date: 2026-07-18 America/Chicago

## Frozen campaign

- User ceiling: `$50.00`.
- Worker count: exactly one.
- Selected type: `massedcompute_A100_sxm4_80G_DGX`, quoted `$1.656/hour`.
- Time cutoff: 08:30 CDT or budget ceiling, whichever occurs first.
- Projected 00:32--08:30 compute: `$13.248`.
- NVIDIA source: `n1.7-release` / `23ace64f17aa5015259b8609d371eb61a357c776`.
- Base model: `nvidia/GR00T-N1.7-3B`.

## Local foundation

The first full-board expert carried the a8 rook to b6 within 8.6 mm but the
arm displaced the black queen by 0.888 m. That trajectory is a counterexample,
not training data. The frozen first curriculum therefore keeps the rook and
king visible and parks all other pieces during reset.

The accepted split contains 24 training demonstrations for rook a8 to b6,
king e8 to d6, and king e8 to c6. Four held-out demonstrations cover unseen
rook a8 to c6 and king e8 to e6 cases with zero training rows. All 28 scripted
consequences passed lift, placement, upright, settled, clearance, distractor,
contact, ownership, and assistance gates. `uv run pytest -q` passed 15 tests.

## Evidence boundary

These are synthetic scripted demonstrations, not learned-policy results. The
dense reward is diagnostic and cannot promote.

## Brev execution result

One `massedcompute_A100_sxm4_80G_DGX` workspace named
`sim2claw-gr00t-n17-0718` (`qr1mn1lpc`) was provisioned. The worker proved:

- A100-SXM4-80GB, 81,920 MiB, compute capability 8.0;
- NVIDIA driver 580.126.09, CUDA runtime 12.8, and Torch 2.7.1+cu128;
- Isaac-GR00T source at the frozen commit `23ace64f...`;
- FFmpeg 4.4.2 and the NVIDIA LeRobot loader accepting all 24 episodes;
- model snapshot `nvidia/GR00T-N1.7-3B` at revision
  `2fc962b973bccdd5d8ce4f67cc63b264d6886495`.

Two reproducible setup defects were found and fixed: non-login Brev commands
did not include `uv` on `PATH`, and the cloned deployment wheel remained a
Git-LFS pointer. The scripts now use the absolute `uv` path and explicitly pull
the pinned deployment wheel.

The declared 250-step post-training command reached model construction but
failed before optimizer step zero. GR00T N1.7 loads the separately gated
`nvidia/Cosmos-Reason2-2B` dependency, and Hugging Face returned `401` on the
worker. No checkpoint or learned-policy episode exists from this attempt.

After teardown, a surviving local read token for Hugging Face account
`jakekinchen` was recovered without copying it into this repository. The token
is valid, but a direct authenticated request for the Cosmos config returns
`403`; the account has not accepted or been granted that model's gated access.
`scripts/check_groot_n17_hf_access.sh` now fails before provisioning until that
dependency is accessible.

## Spend ledger

| Event | Local time | State | Accrued/projected spend |
| --- | --- | --- | --- |
| Initial inventory | 00:30 CDT | `workspaces: null` | `$0.00` |
| Campaign frozen | 00:32 CDT | no worker provisioned | `$0.00` |
| Provisioned | approximately 00:56 CDT | A100-80GB running | `$1.656/hour` |
| Training stopped | approximately 01:05 CDT | gated dependency; optimizer step 0 | approximately `$0.25` |
| Deletion requested | 01:06:47 CDT | workspace deleting | under `$0.40` conservative bound |
| Final inventory proof | 01:15:57 CDT | `workspaces: null` | no further accrual |

Brev does not expose a final line-item bill through the CLI. Based on roughly
eleven minutes between provisioning and deletion request, estimated compute is
about `$0.30`; the conservative recorded bound is `$0.40`, far below `$50`.

## Current classification

- M1 demonstration dataset: **PASS**, including official NVIDIA loader proof.
- M2 environment/model preflight: **PARTIAL**; custom policy serving requires a
  post-trained checkpoint, which the gated dependency prevented.
- M3 bounded post-training: **BLOCKED**, no optimizer step and no checkpoint.
- M4 learned closed-loop consequence: **NOT RUN**.
- M5 paid-compute teardown: **PASS**, authenticated inventory empty.
