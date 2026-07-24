# Studio project map and agent-access integration

Date: 2026-07-24

Status: simulator-twin reconciliation committed and evaluator receipts rebound.
Exact-head tier receipts and independent review still own final verification;
this log does not self-certify them.

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
dual-camera sources, 101 catalog episodes, eight physical sources with
receipt-bound simulator pairings, and 14 missing simulator pairings. Seven of
the pairings preserve a byte-identical action hash. The eighth is explicitly a
source-command diagnostic whose unit conversion and model-bound clipping
preclude an exact-action claim. No image-derived visual twin remains active.
These are catalog observations, not a task-completion score.

## Replay reconciliation checkpoint

Implementation commit
`cfc502140999e9e35bcd2d5dbeefbfb3c04a6aa8` collapses the Replay toolbar to
Reality / Twin / Compare and uses one synchronized timeline for the physical
source and MuJoCo state trace. The old pixel-filter visual mimic is unavailable
because it was not simulator evidence. The replay source badge is
informational rather than a duplicate navigation route.

Adjacent source-command replay receipts are admitted only when source samples,
the replay receipt, response trace, and state trace all match their declared
hashes and identities. Tampering fails closed. A loopback-only, single-flight
POST may generate the existing local diagnostic; the read-only Studio surface
does not expose that write control.

Official evaluator-owned bindings after the committed compiler:

- Studio manifest SHA-256:
  `127b2faa0fbfcff3b946184920b3c3d324d5bcc62ff6745940499be4f0bf0422`.
- Studio receipt SHA-256 / digest:
  `c8489f8d72e35413b933944689027b5ac1ebb46059d1aaed0a77d1b6d98eb66f` /
  `51670fb8d172c63399d516eba35fc4e8ec19272649345ba55faa133335348e44`.
- Publication package SHA-256:
  `98173b9d5dca97c75ce8aa579fd727b02a32ff96474e3025283d590ebdd8f833`.
- Publication receipt SHA-256 / digest:
  `6f72f0bd8aca46ddb9fe58ede65c536e493fb1a0102543d57ce55b8f7fe88696` /
  `9cad224906e27ee40fcb2f9638b3cd2af5f4982db5ad9c6c6054f5ee2f750b1d`.

## Verification checkpoint

- JavaScript syntax and Python compilation: pass.
- Project-map unit/API/static coverage: 7 passed.
- Project-map, Studio, Twin fidelity, SAIL observatory, Task Orchestrator, and
  Learning Factory focused coverage: 103 passed plus 24 subtests.
- Desktop inspection: no horizontal overflow; drawer width 920 px; Close
  receives focus on open and Escape returns focus to Project map.
- Console: zero errors; one pre-existing Three.js Clock deprecation warning.
- Original project-map responsive checkpoint: deterministic CSS/static checks
  covered the single-column rail, full-width drawer, focus, and compact trigger
  breakpoints. The later reconciliation checkpoint below adds the live mobile
  viewport proof.
- Frozen S2 evidence before and after the focused tier: 11/11 hashes unchanged,
  one campaign event, four anchor replays, zero measurement trials.
- Reconciled focused/static gate: 55 passed plus two subtests; JavaScript syntax,
  Python compilation, and diff checks passed.
- Live desktop and 390×844 mobile inspection: no horizontal overflow, three
  unambiguous Replay modes, synchronized 50% scrub at 24.820 seconds, Twin
  fidelity focus return on Escape, and zero console errors. The sole console
  warning remains the pre-existing Three.js Clock deprecation.

## Authority

The surface is observational. Agent evaluator ownership, admission, promotion,
training, provider, paid compute, physical capture, gateway, robot motion,
simulator campaign, and physical task authority remain closed. No push was
performed by this checkpoint.
