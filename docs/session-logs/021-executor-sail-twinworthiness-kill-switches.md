# Executor Session Log 021 - SAIL TwinWorthiness Kill Switches

**Date:** 2026-07-22

P1-14 added an operational exact-scope capability envelope around the frozen
TwinWorthiness scientific certificate. The evaluator-issued envelope is
content-addressed, expiring, revocable, and bound to twin, workcell, task,
distribution, evidence, graph, posterior, simulator, evaluator, and policy
identities. Learning Factory LF-08/LF-09 require `TW-DATA`; LF-11/LF-13 require
`TW-SELECTION`; each stage and each direct mutating helper recomputes the
decision before work.

Seven negative paths are retained and denied: missing, legacy unscoped,
tampered, scope mismatch, identity mismatch, expired, and revoked. The current
`TW-REPLAY` certificate opens diagnostics only. Synthetic higher-level
certificates exercise data, selection, canary, and motion branches without
granting real authority. GOLD-17 through GOLD-19 pass. Focused validation
passed 180 tests, and the production-component LF-00 through LF-13 fixture
passed separately. The final repository gate passed 757 tests plus 328
subtests with three expected skips.
