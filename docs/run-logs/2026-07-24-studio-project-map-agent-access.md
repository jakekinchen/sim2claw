# Studio project map and agent-access integration

Date: 2026-07-24

Status: frozen implementation checkpoint. Exact-head receipts and independent
review own final verification; this log does not self-certify them.

## Product result

Studio now has one contextual Project map rather than another detached
destination. Its ordered spine covers Capture, Scene, Simulate, Replay,
Evaluate, Diagnose, Improve, and Learn/transfer. Every stage presents two
coequal lanes:

- the researcher routes and drawers available in Studio;
- the loopback JSON or content-addressed artifact contract available to a
  bounded agent.

Both lanes display the same observed evidence, proof class, missing
prerequisite, evaluator boundary, and authority state. Learning Factory
remains the governed improvement backend and is not restored as a primary
navigation tab.

## Architectural input

The signed-in Robotics and Sims ChatGPT project was inspected read-only.
Relevant prior discussions converged on an agent-driven outer loop, causal
trace diagnosis, deterministic evaluator ownership, one canonical episode and
evidence system, and progressive artifacts that expose missing scale,
geometry, collision, dynamics, coverage, and consequence. Advice was used as
design input only; repository contracts and receipts remain authoritative.

## Evidence projection

`GET /api/project-map` is deterministic and read-only. It composes:

- the existing Studio catalog;
- the receipt-verified SAIL observatory;
- the hash-bound Learning Factory project declaration;
- server mode flags for existing recorder and orchestrator availability.

It does not invent an overall fidelity percentage, synthesize missing MuJoCo
replays, score a method, mutate actions, or grant authority. Invalid config,
unknown route substitution, stale project-state binding, or invalid SAIL
receipt produces an unavailable state.

The current live projection reports 22 physical source episodes, two
dual-camera sources, 97 catalog episodes, seven physical sources with existing
physics pairings, and 15 missing physics pairings. These are catalog
observations, not a task-completion score.

## Verification checkpoint

- JavaScript syntax and Python compilation: pass.
- Project-map unit/API/static coverage: 7 passed.
- Project-map, Studio, Twin fidelity, SAIL observatory, Task Orchestrator, and
  Learning Factory focused coverage: 103 passed plus 24 subtests.
- Desktop inspection: no horizontal overflow; drawer width 920 px; Close
  receives focus on open and Escape returns focus to Project map.
- Console: zero errors; one pre-existing Three.js Clock deprecation warning.
- Responsive behavior: deterministic CSS/static checks cover the single-column
  rail, full-width drawer, focus, and compact trigger breakpoints. The in-app
  browser security boundary prevented constructing an artificial embedded
  mobile harness, so no claim of a second live mobile viewport is made here.
- Frozen S2 evidence before and after the focused tier: 11/11 hashes unchanged,
  one campaign event, four anchor replays, zero measurement trials.

## Authority

The surface is observational. Agent evaluator ownership, admission, promotion,
training, provider, paid compute, physical capture, gateway, robot motion,
simulator campaign, and physical task authority remain closed. No push was
performed by this checkpoint.
