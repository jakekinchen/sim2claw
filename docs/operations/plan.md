# Operations atlas implementation ledger

Authorization: the owner's 2026-09-05 request to audit repository agent logs,
learn from success and failure, and build an efficient, human-interpretable CLI
with subagent assistance. This is a software operations project. It does not
activate a simulation campaign or change `GOAL.md`, evaluator ownership,
held-out boundaries, hardware authority, or paid-resource authority.

Baseline: clean `main` at `9a91ba850149270685076ceade762bb367808f31`;
`check --profile agent` passed; manager context reports OR156 closed, no active
card, no execution admission. Implementation branch: `codex/operations-atlas`.

## Acceptance milestones

| Milestone | Required outcome | Gate | State |
| --- | --- | --- | --- |
| M1 Evidence audit | Account for repository agent logs and decision records; derive cited operational lessons and architecture gaps | Three independent audits, explicit coverage and exclusions, no inferred capability promotion | complete |
| M2 Usable CLI | Incrementally index evidence; search, inspect lessons, show current authority and an explicit architecture map; record human observations | Real-corpus run plus adversarial indexing, drift and input tests | complete |
| M3 Human visibility | Terminal progress/watch and an interactive, inspectable local report use the same evidence model | Exercise search/filter/details, source provenance, fresh/stale display, event feedback | delivered; browser visual gate unavailable |
| M4 Independent closeout | Reviewer checks implementation, reproducibility and claim boundaries; documented operating path and future gates | Focused/adjacent tests, live campaign checks, scoped commit and durable reviewer decision | complete for software scope |

One milestone is active at a time. Implementations can be delegated in parallel
within the current acceptance gate. Audit reports live beside this ledger.
Generated indexes, reports and receipts live in ignored `outputs/operations/`.

## Design constraints

- Use the current role-context compiler for authority; historical prose and
  statistical keyword counts never authorize work or prove success.
- Prefer a small Python standard-library CLI over a new agent framework,
  hosted service, vector database, LLM provider, or duplicate simulator.
- Every source has a relative path, content hash, coverage state and line
  anchors. Oversize, missing, malformed and excluded sources are visible.
- Separate reported findings, reviewed reusable lessons, human annotations,
  runtime observations and current campaign state.
- Human interaction initially means search/filter/inspect, replayable local
  events and explicit feedback. It does not execute commands from logs.
- Preserve existing campaign documents and generated data. No external
  publication, provider setup, physical work or paid compute is required.

## Review and completion record

M1 evidence: `history-audit.md`, `run-audit.md`, `infrastructure-audit.md`;
527 nonempty history documents and 134,561 runtime inventory paths accounted
for with explicit overlap, caps and exclusions. Eighteen proposed lessons have
51 current source anchors. Whole-corpus scanning is not independent reproduction
of historical results. The architecture catalog contains 24 nodes and 33 edges.

Initial real-corpus implementation scan: 9,619 candidate text sources, 9,185
indexed, 434 over 4 MiB, 3,060,225,350 source bytes read. An initial per-line
full-text implementation was interrupted after its quadratic insertion cost
became visible. Document indexing completed in 66.905 seconds but created a
6.4 GiB cache, prompting compressed source storage and a narrative-only runtime
JSON search projection. These are development observations, not final performance
claims. The empty-annotation development cache alone was removed for rebuilding.

Human annotations were moved to a separate transactional `journal.sqlite` after
independent review identified that rebuilding a disposable index could lose
notes. Campaign checks correctly refuse this software feature branch because the
campaign manifest requires `main`; the compiler is not bypassed or weakened.

Final implementation evidence is recorded in `verification.md`: 9,382 of 9,816
discovered text sources indexed; all oversized skips are JSON/JSONL payloads;
140 focused/adjacent tests pass; exact citations, byte budgets, persistent
feedback, unchanged watch and campaign-source preservation pass. The offline
report was generated. Browser Use refused its local-file URL and prohibited
workarounds, so real-browser interaction/layout remains an open validation gate.
No authority or external resource is needed to use the delivered terminal path.

Implementation committed as `de2a94b` on `codex/operations-atlas`. Independent
review records PASS for bounded software R1, with 68 focused tests and separately
reproduced adversarial cases. The broader adjacent validation passed 140 tests.
The immutable final review receipt is retained at
`outputs/operations-audit/review-final-receipt.json`; its SHA-256 is
`03baa087ebc644bce8fa99672b65d3a11d697e044bfe2e1dbb7180f1ddbec236`.
Only the browser interaction/layout gate remains unavailable for this release.
No simulation/evaluator/campaign source or external authority was changed.

Perfection is not a testable
completion claim. The first release must satisfy every gate above and leave a
ranked, dependency-mapped expansion plan with measurable acceptance criteria.
