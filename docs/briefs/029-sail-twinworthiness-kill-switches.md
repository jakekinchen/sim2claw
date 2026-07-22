# Slice Brief 029 - SAIL TwinWorthiness and Downstream Kill Switches

**Date:** 2026-07-22

## Objective

Complete P1-14 by making evaluator-owned TwinWorthiness certificates the
content-addressed capability boundary for Learning Factory data generation,
policy comparison, physical canaries, and robot motion. Current retained and
prospective simulator evidence must exercise every downstream path while
remaining fail-closed at `TW-REPLAY`.

## Acceptance Criteria

- Certificate truth tables, issuance, verification, task/distribution scope,
  simulator/evidence/evaluator identities, and revocation semantics are exact
  and content-addressed.
- LF-08/LF-09 data generation requires a valid matching `TW-DATA` certificate;
  policy comparison claims require `TW-SELECTION`; canary and motion paths
  require their separately declared levels and authority.
- Missing, expired, mismatched, malformed, or tampered certificates revoke the
  affected capability before work begins and emit the failed gate plus minimum
  resolving evidence.
- Simulation, learned-policy simulation, physical read-only, physical canary,
  and physical task evidence remain separate proof classes.
- GOLD-17, GOLD-18, and GOLD-19 pass; fixtures make downstream code reachable,
  while the current `TW-REPLAY` certificate opens no downstream capability.
- The Learning Factory remains the only verdict and promotion owner.

## Stop Conditions

- A consumer infers capability from RMS, simulated reward, a checkpoint, a
  receipt, or prose instead of a verified matching certificate.
- A certificate can self-issue, self-promote, broaden task/distribution scope,
  or survive identity mismatch or tampering.
- Current evidence opens data generation, policy selection, physical canary,
  robot motion, or transfer authority.
- The slice trains a policy, generates admitted data, invokes hardware, or
  changes the frozen Phase 2 prediction packet.

## Result

Status: `COMPLETE`

An operational, content-addressed capability envelope now wraps the immutable
scientific TwinWorthiness verdict without modifying the five frozen P1-01
schemas. It binds the exact twin, workcell, task, distribution, task and
distribution hashes, evidence, graph, posterior, simulator, evaluator, policy
identities, validity window, and evaluator-only issuance request. Missing,
legacy-unscoped, tampered, scope-mismatched, identity-mismatched, expired, and
revoked envelopes all deny capability.

Learning Factory stages LF-08 and LF-09 recompute `data_generation` before
curriculum or dataset mutation; LF-11 and LF-13 recompute `policy_selection`
before comparison or promotion state. The direct mutating helpers repeat the
verification, so a caller cannot forge an allowed decision object. Denials
publish stable codes, failed gates, and the minimum new evidence needed.

The current retained-workcell base verdict remains `TW-REPLAY`: diagnostics is
the only allowed capability. Data generation, policy selection, physical
canary, and robot motion remain closed. Synthetic `TW-SELECTION` and
`TW-PHYSICAL-CANARY` certificates exercise the downstream branches but carry
the explicit proof class `synthetic_capability_fixture_not_real_authority`.
GOLD-17, GOLD-18, and GOLD-19 pass. No data were admitted, no policy was
trained or selected, no hardware was invoked, and no physical authority was
created.
