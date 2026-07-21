# Decision 0011: Inspect AI and Inspect SWE for GapBench

## Status

Accepted for the optional hardware-free evaluation group on 2026-07-19.

## Decision

Adopt these reviewed public dependencies outside the Sim2Claw robot runtime:

| Dependency | Pin | Source | Reason |
|---|---:|---|---|
| Inspect AI | `0.3.248` | `inspect.aisi.org.uk` / PyPI `inspect-ai` | Own datasets, sample sandboxes, limits, transcripts, approvals, deterministic scorers, and evaluation logs. |
| OpenAI Python | `2.46.0` | PyPI `openai` | Required by Inspect's Responses bridge used by Codex CLI. |
| Anthropic Python | `0.117.0` | PyPI `anthropic` | Required by Inspect's Anthropic bridge used by Claude Code. |
| Inspect SWE | `0.2.66` | `meridianlabs-ai.github.io/inspect_swe` / PyPI `inspect-swe` | Run Codex CLI and Claude Code through the same Inspect agent bridge, skills, and bridged tools. |
| Codex CLI | `0.144.6` | npm `@openai/codex` | One benchmarked coding-agent harness in the shared Linux image. |
| Claude Code | `2.1.199` | npm `@anthropic-ai/claude-code` | The second benchmarked harness in the same image and semantic condition. |
| Node.js image | `22.17.1-bookworm-slim` | Docker Hub official `node` image | Reproducible Linux runtime for both pinned agent binaries. |

The Python packages live in the `inspect` dependency group in `pyproject.toml`
and `uv.lock`. They are not runtime dependencies of simulation, training,
Studio, the evaluator, or the robot gateway.

## Boundaries

- Inspect orchestrates attempts but cannot promote a simulator or policy.
- The sealed evaluator remains a host-side deterministic service. Production
  sealed bytes are absent from Git and packages, injected by explicit path or
  `SIM2CLAW_GAPBENCH_SEALED_SOURCE`, and verified against the public campaign
  digest before a task is built.
- Agent sandboxes receive public packets only and have no external network,
  host mounts, credentials, devices, Docker socket, or robot gateway.
- Inspect SWE model requests require separately configured provider access.
  No provider-backed request is authorized by this decision.
- Synthetic benchmark scores are not physical-transfer evidence.

## Consequences

The benchmark can compare harnesses and models with controlled inputs, skills,
tools, limits, and receipts. It also adds a sizable optional dependency closure
and a container build, so paper runs must report the exact lock, image digest,
agent versions, provider identity, and cost.
