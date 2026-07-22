# Slice Brief 026 - SAIL Governed Inspect Campaign

**Date:** 2026-07-22

## Objective

Complete P1-11 by extending the existing Inspect/GapBench harness with typed
SAIL packets, equivalent Codex and Claude workspaces, frozen tools/budgets,
sealed evaluator ownership, exact runtime/provider attempt receipts, and
provider-independent GOLD-13, GOLD-14, and GOLD-24 controls.

## Acceptance Criteria

- Agent and deterministic conditions receive identical public evidence, tool
  semantics, limits, and terminal submission schema.
- Hidden/sealed state is evaluator-only and bounds/provider identity fail
  closed.
- Three representative development scenarios run before any wider campaign.
- Exact runtime, model/provider, prompt, reasoning, retry, token, cost, and
  duration fields are recorded per attempt; unavailable authenticated provider
  routes produce explicit zero-cost blocked attempts rather than fabricated
  results.
- Agent prose has zero score authority; only typed actions are evaluated.
- GOLD-13, GOLD-14, and GOLD-24 pass.

## Stop Conditions

- Provider identity changes or cannot be captured.
- Conditions receive unequal evidence/budgets.
- Sealed bytes become visible to a candidate.
- Any spend exceeds the frozen ceiling or any agent self-promotes.
