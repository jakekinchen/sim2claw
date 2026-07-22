# SAIL project application closeout

Date: 2026-07-22

## Scope

Applied the completed P1-00 through P1-17 system to the retained project
evidence, with an action-frozen focus on the observed C2-to-C1 pawn drop.

## Milestone outcomes

- **A1-00 complete:** froze exact source receipts, 11 action hashes, three
  sentinels, eight previously opened evaluation episodes, metrics, mechanisms,
  12-composite budget, acceptance gates, and stop conditions.
- **A1-01 complete:** reproduced C2 contact loss before release and added
  identity-rich contact-surface and deterministic load-bearing-pair witnesses.
- **A1-02 complete:** compiled 31 retained evidence items, 11 executable
  action-frozen episodes, 10 failure classes, and a receipt-bound belief graph.
- **A1-03 complete:** ran the bounded solver, no-slip, cone, contact-dimension,
  and fixed-rubber-placement sentinel campaign without action mutation.
- **A1-04 complete:** froze `condim4` before one evaluation pass over the eight
  previously opened episodes.
- **A1-05 complete:** rejected the candidate on task and EE gates; retained the
  secondary post-first-lift task diagnostic and exact failure localization.
- **A1-06 complete:** published the report, compiler, receipt, tests, and a
  read-only Studio publication page without changing the P1-bound Studio
  server or observatory assets.

## Evaluator verdict

`terminal_negative_for_bounded_contact_model_promotion_with_observability_and_diagnostic_metric_gains`

- Action invariance: pass, 11/11 exact SHA-256 identities.
- Candidate counts: 4/11 lifts, 1/11 lift-and-transport, 0/11 strict.
- Joint guard: pass, 1.22284 degrees ≤ 1.22397 degrees.
- EE guard: fail, 11.6466 mm > 11.4571 mm.
- New wrong-piece contacts: none relative to baseline.
- Maximum collateral: no worse than baseline.
- Training, simulator promotion, physical calibration, and physical authority:
  closed.

## Commands

```bash
uv run pytest -q tests/test_pawn_bg_grasp_coordinate_descent.py tests/test_sail_project_application.py tests/test_sail_studio_observatory.py
uv run python scripts/compile_sail_project_application.py
uv run pytest -q tests/test_sail_project_application.py tests/test_pawn_bg_grasp_coordinate_descent.py tests/test_sail_studio_observatory.py tests/test_sail_publication.py
uv run sim2claw studio --host 127.0.0.1 --port 4181 --no-open --read-only
uv run pytest -q
brev ls --json
docker ps --format '{{json .}}'
```

## Final verification

- Focused project-application, grasp, Studio, and publication tests:
  `25 passed in 2.99s`.
- Full repository suite: `792 passed, 3 skipped, 328 subtests passed in
  1263.56s (0:21:03)`.
- Final project-state, NemoClaw project, and Learning Factory binding tests
  after recording closeout metadata: `78 passed in 125.55s (0:02:05)`.
- The read-only Studio server returned HTTP 200 for
  `/project-application.html` and
  `/publication/sail_project_application_v1/manifest.json`; it was then shut
  down cleanly.
- Project-state authority binding, application receipt binding, and all four
  standalone Studio publication hashes matched their frozen values.
- Authenticated Brev inventory returned `{"workspaces": null}`; Docker had no
  running containers.

No robot, camera, serial device, Brev instance, container, or paid compute was
used or left running.
