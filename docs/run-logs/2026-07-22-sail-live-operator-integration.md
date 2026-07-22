# SAIL live operator integration closeout

Date: 2026-07-22

## Scope

Replaced the manually sequenced retained C2 parameter-family search with one
generic, typed, budgeted SAIL operator. The operator binds arbitrary campaign
IDs through data contracts, composes the existing causal surfaces, freezes
predicted intervention signatures before results, and fail-closes on identity,
budget, posterior, affected-factor, evaluator, or promotion drift.

No new C2 family was run. B2-02X remains paused at 17 of 18 work-in-progress
anchor artifacts with no complete screen receipt.

## Terminal decision

The operator followed:

`residual evidence -> structural surprise -> belief -> mechanisms ->`
`acquisition -> budget -> influence -> posterior -> sparse closure ->`
`invariance/consequence -> abstention`.

It ranked `measurement_synchronized_force_deformation_probe` first because the
retained evidence cannot separate `flexural_rubber_contact_v1` from
`actuator_load_path_v1`. The measurement is unavailable under current
authority, so the operator emitted
`abstain_measurement_acquisition_required` before execution.

- Interventions: 0 of 1.
- C2 anchor replays: 0 of 18.
- Posterior: 0.5 / 0.5, unchanged because no result was opened.
- Observed information gain: unavailable, not imputed.
- Promotion, training, physical capture, and robot motion: false.

## Manual versus SAIL ablation

The retrospective manual baseline contains exactly 32 complete campaign
receipts, 514 C2 candidate replays, and zero accepted anchor passes. The
incomplete 17-artifact B2-02X screen is preserved separately and excluded.
SAIL used zero simulator evaluations and abstained before execution. Avoiding
514 evaluations is an efficiency observation, not an accepted task gain.

## Evidence hashes

- Action SHA-256:
  `402a29e4cdc0c4cb90d41a83327ad8df5685544851b4e4d659129b3239744fd6`
- Evaluator digest:
  `906165a7faf334182a5d3bbee5189ef689c660a3f58b2d572a257b83d55bc359`
- Operator receipt SHA-256:
  `e4aac1ce3cbf100902e71afc2be834a54a4b83555b51fb94196cd9e505490c23`
- Operator receipt digest:
  `caa30fdcf4592f52fdc02c94181e75bbf24bd413a3310fbeb4d06707d431036f`
- Operator trace SHA-256:
  `98dfd3e24da68e6d023ee2320875ad4b90bf44f3c162f4d44e23b30d8db7481d`
- Ablation SHA-256:
  `39596e54063503865aede2d42387730ac133256f74068a061e9a979a17061dde`
- Measurement packet SHA-256:
  `fd52e5e882b277259c7f5449e62abda8373ebe85a689ce9b7c7fc527671807bd`
- Final project-state SHA-256:
  `aee73be2998c67435cc6813d6e98f9e2a685cebc4f6ff6c63c3e89feab9507a7`

Generated evidence is under `outputs/sail/live-operator-c2-v1`. The committed
read-only publication is at `/live-operator.html` with its manifest and static
receipt under `src/sim2claw/studio_web/publication/sail_live_operator_v1`.

## Verification

```bash
uv run pytest tests/test_sail_live_operator.py tests/test_sail_acquisition.py tests/test_sail_belief_graph.py tests/test_sail_influence.py tests/test_sail_loop_closure.py tests/test_sail_invariance.py tests/test_sail_mechanisms.py tests/test_sail_cli.py -q
uv run pytest tests/test_sail_contracts.py tests/test_sail_twin_worthiness.py tests/test_sail_hardware_protocol.py -q
uv run pytest tests/test_sail_mechanisms.py tests/test_sail_belief_graph.py tests/test_sail_influence.py tests/test_sail_invariance.py tests/test_sail_acquisition.py tests/test_sail_loop_closure.py tests/test_sail_benchmark.py -q
uv run pytest tests/test_sail_agent_campaign.py tests/test_sail_capability_campaign.py tests/test_sail_policy_flywheel_campaign.py tests/test_learning_factory.py tests/test_sail_cli.py tests/test_studio.py tests/test_sail_studio_observatory.py tests/test_sail_publication.py -q
uv run pytest tests/test_sail_evidence.py -q
uv run pytest -q
```

- Focused operator/composition: 60 passed in 2.35 seconds.
- SAIL tier 1, fast contract: 36 passed in 0.62 seconds.
- SAIL tier 2, synthetic golden: 58 passed in 2.17 seconds.
- SAIL tier 3, integration: 74 passed and 2 subtests passed in 26.91
  seconds. A first attempt correctly rejected a changed frozen Studio index;
  the new route was kept standalone and the frozen index restored.
- SAIL tier 4, retained evidence: 6 passed in 2.67 seconds.
- Tiers 5 and 6 were not opened because provider and hardware authority were
  not granted.
- First broad diagnostic: 840 passed, 3 skipped, 328 subtests, with one
  fail-closed stale project-state hash. The final authority hash was rebound
  and the LF00-LF13 acceptance test passed in isolation.
- Final uninterrupted repository suite: 841 passed, 3 skipped, 328 subtests in
  1274.86 seconds (21:14).
- Read-only Studio returned HTTP 200 for `/live-operator.html` and its
  publication manifest.

No Brev, provider, GPU, hardware, camera, serial device, robot gateway, or paid
resource was touched; therefore no Brev inventory mutation or cleanup was
required. Proof class is
`retrospective_action_frozen_c2_live_operator_abstention`.

## Scoped changed-file inventory

Modified:

- `.factory/orchestration-ledger.md`
- `GOAL.md`
- `configs/projects/pawn_rank12_reachable_bg_hackathon_v1.json`
- `docs/autonomous-workflow/goal-loop-compliant-pad-win.md`
- `docs/autonomous-workflow/project_state.json`
- `src/sim2claw/cli.py`
- `tests/test_sail_cli.py`

Added:

- `configs/sail/live_operator_c2_v1.json`
- `docs/briefs/036-sail-live-operator-contract.md`
- `docs/manager-log/002-sail-live-operator.md`
- `docs/research/2026-07-22-sail-live-operator-ablation.md`
- `docs/reviewer-messages/026-sail-live-operator.md`
- `docs/run-logs/2026-07-22-sail-live-operator-integration.md`
- `docs/session-logs/025-executor-sail-live-operator.md`
- `src/sim2claw/sail/live_operator.py`
- `src/sim2claw/studio_web/live-operator.css`
- `src/sim2claw/studio_web/live-operator.html`
- `src/sim2claw/studio_web/live-operator.js`
- `src/sim2claw/studio_web/publication/sail_live_operator_v1/manifest.json`
- `src/sim2claw/studio_web/publication/sail_live_operator_v1/receipt.json`
- `tests/test_sail_live_operator.py`
