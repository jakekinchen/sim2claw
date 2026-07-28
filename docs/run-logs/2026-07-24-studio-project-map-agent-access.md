# Studio project map and agent-access integration

Date: 2026-07-24

Status: simulator-twin reconciliation and the independently identified
rendering-race repair are committed; evaluator receipts are rebound. New
exact-head tier receipts and independent rereview still own final
verification; this log does not self-certify them.

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
  `5cde59a71f506ad680fffd2d0c24231b07c08faf98ce28ddc364e79be773a161` /
  `8f1bce61949ce5376d888989a3fc9e191fb2ead4f707a6ba4331bdddd1805c4a`.
- Publication package SHA-256:
  `98173b9d5dca97c75ce8aa579fd727b02a32ff96474e3025283d590ebdd8f833`.
- Publication receipt SHA-256 / digest:
  `c3cb2e2618fffd0d5746f17448e9a6a906b6382cfef95c369b004c40dd9913eb` /
  `542929707879989cb27de6f453e74c2c66f433d7e34f895ce60394c57948e4d4`.

The superseded pre-repair Studio/publication receipts remain preserved as
historical generated evidence at SHA-256 `c8489f8d...` and `6f72f0bd...`.
Their manifest/package payloads are unchanged; only compiler/config identities
and receipt digests changed.

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
  unambiguous Replay modes, synchronized 50% scrub at 24.820 seconds, and Twin
  fidelity focus return on Escape.
- Independent exact-head review corrected the earlier console claim. At
  `6fc3a9f`, missing replay → paired replay → second paired replay constructed
  two Three.js viewers on one canvas and produced 197 WebKit WebGL
  program-location errors. Reality stopped only the retained viewer while the
  orphan renderer continued.
- Repair commit `3195280b001e58aad6b43a4d60314daabe6e19f4`
  single-flights viewer creation, removes the redundant initial paired load,
  serializes scene mutation, and discards stale loads. The original sequence
  now completes with zero WebGL errors in the in-app Chromium runtime and a
  clean WebKit session. The sole remaining browser warning is the pre-existing
  Three.js Clock deprecation. The pre-rebind SAIL-observatory 503 was an
  expected fail-closed response to dirty compiler identity and is excluded;
  the rebound receipt removes it.
- Excluded full-suite receipt at
  `31e5ead86c6028284059365e3da1e1b3086b6e8b`: 1162 passed, three skipped,
  328 subtests passed, and one stale assertion failed because it still required
  every post-retained recording to be simulator-unavailable. Receipt digest
  `cfcf454f139d9344c3668f4e593ffdce3121d2df12145bdabf007e3c290e5ff9`;
  log SHA-256
  `18e70c1623bbaa4d9708ad87720ec94ed8ec1d5466140193dd4ac684aadd74c6`.
- The repaired test now separately asserts seven retained byte-identical
  publication pairings, one hash-bound converted source-command diagnostic,
  and two later simulator-unavailable recordings. The affected slice passes
  29 tests plus two subtests. A replacement exact-head full suite remains
  required.

## Authority

The surface is observational. Agent evaluator ownership, admission, promotion,
training, provider, paid compute, physical capture, gateway, robot motion,
simulator campaign, and physical task authority remain closed. No push was
performed by this checkpoint.
