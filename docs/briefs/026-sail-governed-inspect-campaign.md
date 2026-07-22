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

## Result

Completed. The existing Inspect/GapBench package now exposes eight structural
SAIL packets through an equivalent eight-tool Codex/Claude bridge and a
deterministic sealed scorer. Three representative development scenarios
(single fault, compensating two-fault, and missing-observable) completed before
the frozen provider lanes were considered.

Inspect cannot reuse either native CLI's authenticated subscription transport;
its adapters proxy provider traffic. Because substituting a native one-shot
call would violate tool/workspace equivalence and the campaign spend ceiling is
zero, all six Codex/Claude case attempts are preserved as scored
`blocked_before_model_call` failures. They used zero tokens, zero dollars, zero
retries, and zero measured provider runtime. This is not a model tie, win, or
loss. GOLD-13, GOLD-14, and GOLD-24 pass, and no provider session, container,
device, credential, or Brev resource remains active.
