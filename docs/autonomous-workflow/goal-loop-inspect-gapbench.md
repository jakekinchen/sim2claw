# Inspect GapBench Build Goal Loop

## Mission

Build a hardware-free, reproducible Sim2Claw GapBench implementation that lets
Inspect AI run either the Codex CLI or Claude Code against the same frozen
real-to-sim diagnosis cases, shared skills, typed tools, budgets, sandbox, and
deterministic evaluator. The benchmark measures whether an agent can localize
a reality gap, choose informative probes, implement one bounded repair, and
predict held-out consequences without seeing sealed evaluator data.

This loop does not create physical-transfer evidence, policy-success evidence,
or promotion authority. It creates synthetic benchmark evidence and the
infrastructure needed for a later, separately authorized model campaign.

## Authority-ordered sources of truth

1. The current user request and repository `AGENTS.md`.
2. Live `GOAL.md`, `project_state.json`, and Learning Factory contracts.
3. `docs/research/2026-07-19-inspect-ai-inspect-swe-integration-plan.md`.
4. GapBench schemas, frozen fixture manifests, and evaluator code.
5. Tests and current run receipts.
6. This ledger. It records progress but cannot overrule the sources above.

## Intended outcome

- A typed `GapCase.v1`, `AgentAttempt.v1`, and campaign summary contract.
- Six seeded synthetic fault families with disjoint public and sealed bytes.
- Six bounded agent tools and a single-use sealed submission gate.
- Deterministic component scores and a frozen aggregate.
- Identical Inspect SWE Codex and Claude Code adapters.
- Five concise shared agent skills with a reproducible bundle digest.
- A non-root, network-isolated Docker image with pinned agent binaries.
- A local scripted end-to-end proof requiring no credentials or paid compute.
- Tests for secrecy, budgets, path safety, receipts, determinism, and adapters.
- A reviewer-readable dependency ledger, usage guide, and run log.

## Acceptance gates

- [x] Locked optional Inspect dependencies import under Python 3.12.
- [x] All public case manifests validate and all public artifact digests match.
- [x] Public packets contain no sealed paths, target values, credentials, home
      mounts, device mounts, or Docker socket.
- [x] The six tool schemas enforce case identity, path bounds, budgets, allowed
      probes, candidate bounds, and one terminal submission.
- [x] Sealed scoring returns aggregate receipts without returning target
      parameters or hidden trajectories.
- [x] All six seeded fault families reward the correct repair and penalize an
      unchanged or incorrect candidate.
- [x] Codex and Claude adapters use identical skills, tools, workspace, limits,
      and sandbox; only the harness identity differs.
- [x] Both pinned agent binaries execute `--version` in the same image.
- [x] The Inspect task loads without invoking a model provider.
- [x] Local end-to-end fixture runs reproduce byte-identical scientific score
      fields and preserve all attempts, including negative ones.
- [x] Full relevant tests pass and a durable run log records commands/results.
- [x] No provider-backed call, robot action, credential use, or Brev resource is
      needed or performed.

## Confirmed requirements

- Learning Factory evaluators, not agents or trainers, own verdicts.
- Fixture, synthetic, simulation, replay, learned-policy, and physical evidence
  remain separate proof classes.
- Hidden cases and evaluator state never enter the agent sandbox.
- Public evaluation never mutates sealed evaluation state.
- Agents receive the same semantic procedures and controlled tools.
- Raw generated workspaces, transcripts, `.eval` logs, and receipts stay out of
  Git unless explicitly redacted and selected for publication.

## Defaults used for this implementation

- Python packages: `inspect-ai==0.3.248`, `inspect-swe==0.2.66` in an optional
  dependency group.
- Agent binaries: Codex CLI `0.144.6`, Claude Code `2.1.199` in the benchmark
  image, used with Inspect SWE `version="sandbox"`.
- Cases: six deterministic seeded synthetic parameter-recovery cases.
- Attempt policy: one terminal submission, up to two public evaluations and
  two charged probes per case.
- Network: disabled in the sample container. Inspect model and bridged-tool
  traffic are harness-owned, not general sandbox network access.
- Model calls: disabled during build verification. A live campaign requires a
  separately frozen matrix, provider credentials, budgets, and authority.

## Explicit non-goals

- Claiming the synthetic benchmark bridges the current pawn task to hardware.
- Opening current held-out robot evidence or changing promotion thresholds.
- Giving an agent shell access to the host, evaluator, Docker daemon, cameras,
  serial devices, robot gateway, credentials, or Brev.
- Choosing paper-winning models from development cases.
- Treating an LLM judge as task-success authority.

## Execution rhythm

Repeat until every acceptance gate is either proved or explicitly blocked:

1. Inspect live authority and current dirty state.
2. Select the smallest incomplete gate with a deterministic test.
3. Implement only the bounded slice needed for that gate.
4. Run focused tests, then the local end-to-end proof.
5. Record exact evidence and update the ledger below.
6. Preserve failures and revise the next slice; never rewrite a negative result
   as success.
7. Close only after full verification and cost/resource cleanup checks.

## Progress ledger

| Gate | Status | Evidence |
|---|---|---|
| Goal contract and build ledger | complete | This file and the dated run log |
| Contracts and six fixtures | complete | `tests/test_gapbench_core.py` |
| Tool boundary and sealed scorer | complete | Budget, path, secrecy, and determinism tests |
| Inspect adapters and skills | complete | Both task factories load; five skills validate |
| Docker boundary | complete | Image `sha256:d5c8ac00...`; device/socket/network probes pass |
| Local end-to-end proof | complete | 12-attempt campaign `add69036...` and two mock harness runs |
| Full verification and closeout | complete | 487 tests and 328 subtests pass |

## Decision status

`COMPLETE` — the hardware-free implementation and no-provider proof are closed.
Provider-backed evaluation, physical probing, publication claims, committing,
pushing, and promotion remain outside this loop unless separately authorized.
