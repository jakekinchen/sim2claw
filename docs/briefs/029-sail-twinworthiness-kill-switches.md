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
