# Sim2Claw on NemoClaw

This directory is the repo-owned, fail-closed deployment design for the
hackathon reference implementation. It targets one already-provisioned remote
host, one NemoClaw/OpenShell sandbox, the OpenClaw agent surface, and one
read-only Studio surface on port `4173`.

## Current proof state

As of the repository handoff, the `nemoclaw-e3fca7` workspace is **STOPPED**.
No NVIDIA API key was generated or registered, no NVIDIA Endpoint or OpenClaw
inference route was validated, and onboarding plus end-to-end deployment remain
incomplete. Nothing in this directory is a deployment-success receipt.

The historical local tarballs created during the rejected attempt were dirty
snapshots rooted at `7646ddfc4c1e88384234347991fb1b8dbfa6eb8e`. They are stale,
are not current source authority, and must never be deployed. A future attempt
must rebuild from a reviewed, clean, committed HEAD.

## Runtime shape

- Brev host: `nemoclaw-e3fca7`
- sandbox: `sim2claw-hackathon`
- project: `configs/projects/pawn_rank12_reachable_bg_hackathon_v1.json`
- intended inference: NVIDIA Endpoints, not configured or validated
- intended agent: OpenClaw, onboarding incomplete
- Studio: `sim2claw studio --read-only`, with recorder/live-device APIs disabled

`scripts/nemoclaw/deploy.sh` refuses any tracked or untracked dirt, creates the
source archive only with `git archive HEAD`, binds the committed revision and
both outer archive digests, verifies both digests on the host and in the
sandbox, inspects the project bundle before extraction, and fails if service
exposure or strict read-only verification fails.

## Public dependencies

No new Python runtime dependency is introduced by this layer. The deployment
uses the repository's reviewed `uv.lock`, the official NemoClaw/OpenShell CLIs,
and a preinstalled reviewed `uv 0.9.29`. Bootstrap performs no network-fetched
installer execution. These dependencies reproduce the repo runtime; they do
not grant evidence or authority.

## Verification

Inside the sandbox:

```bash
cd /sandbox/sim2claw
bash scripts/nemoclaw/verify-deployment.sh
```

The receipt records the exact source revision, project/evaluator inspection,
latest bounded stage result, skill hash, and Studio health. A `passed` inspect
stage proves only deployment integrity. `partial` and `blocked` project gates
remain terminally meaningful and must not be rewritten as capability claims.
