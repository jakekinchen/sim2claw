# Executor Session 002 - groot n17 brev auth gate

**Date:** 2026-07-18

## Slice

Pinned NVIDIA loader/model preflight and the first bounded 250-step GR00T N1.7
post-training attempt on one Brev A100-80GB.

## Files Changed

Brev setup/preflight/training scripts, Hugging Face dependency-access preflight,
campaign run ledger, milestone/project state, and closeout review artifacts.

## Tests / Validation

- Worker: A100-SXM4-80GB, CUDA 12.8, Torch 2.7.1+cu128.
- Isaac-GR00T commit `23ace64f...` and N1.7 model revision `2fc962b...`.
- NVIDIA loader accepted 24 episodes and the custom modality config.
- Training stopped before optimizer step zero on Cosmos gated access.
- Final `brev --no-check-latest ls --json`: `workspaces: null`.

## Reachability

The dataset is reachable by NVIDIA's pinned runtime. Learned-policy reachability
is unresolved: no checkpoint or server response was produced.

## Evidence

The initial non-login `uv` path failure and Git-LFS wheel-pointer failure were
fixed in scripts. The worker then reached model construction. Remote auth
returned `401` for `nvidia/Cosmos-Reason2-2B`; a recovered valid local token for
account `jakekinchen` returns `403` for the same gated config. No credential was
recorded in Git or run artifacts.

## Step-9 Flags For Reviewer

Do not describe this as a learned episode, fine-tuning completion, or policy
server proof. It is official-loader proof plus a terminal external-access gate.
Do not reprovision until the local access check passes.

## Next Suggested Slice

The human account owner accepts or obtains Cosmos access. Run
`scripts/check_groot_n17_hf_access.sh` locally; only a PASS unlocks a fresh
bounded worker, the same 250-step candidate, and held-out evaluator attempt.
