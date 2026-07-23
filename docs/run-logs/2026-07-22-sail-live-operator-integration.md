# SAIL decision/evidence control-plane corrective closeout

Date: 2026-07-22

## Scope

Replaced the manually sequenced retained C2 parameter-family search with one
generic, typed, budgeted SAIL decision plane. The plane binds arbitrary campaign
IDs through data contracts, composes the existing causal surfaces, freezes
predicted intervention signatures before results, and fail-closes on identity,
budget, posterior, affected-factor, evaluator, or promotion drift. It has no
intervention executor and consumes only independently evaluated, hash-bound
receipts.

No new C2 family was run. B2-02X remains paused at 17 of 18 work-in-progress
anchor artifacts with no complete screen receipt.

## Terminal decision

The decision plane followed:

`residual evidence -> structural surprise -> belief -> mechanisms ->`
`acquisition -> budget -> influence -> posterior -> sparse closure ->`
`invariance/consequence -> abstention`.

It ranked `measurement_synchronized_force_deformation_probe` first because the
retained evidence cannot separate `flexural_rubber_contact_v1` from
`actuator_load_path_v1`. The measurement is unavailable under current
authority, so the decision plane emitted
`abstain_measurement_acquisition_required` before execution.

- Interventions: 0 of 1.
- C2 anchor replays: 0 of 18.
- Synthetic measurement trials: 0 of 6.
- Posterior: 0.5 / 0.5, unchanged because no result was opened.
- Observed information gain: unavailable, not imputed.
- Promotion, training, physical capture, and robot motion: false.

## Manual versus SAIL ablation

The retrospective manual baseline contains exactly 32 complete campaign
receipts, 514 C2 candidate replays, and zero accepted anchor passes. The
incomplete 17-artifact B2-02X screen is preserved separately and excluded.
The 514 historical evaluations informed the frozen retrospective decision;
SAIL used zero additional evaluations after the pause. This is retrospective
context, not a counterfactual efficiency or accepted task-gain claim.

## Corrective control-plane proof

- Bare `--result` input was removed. The CLI accepts only a simulator evaluator
  receipt or a sealed-packet-bound offline measurement evaluator receipt.
- Receipts bind campaign, selected and frozen interventions, action, evaluator
  code/config/source identities, exact execution/replay/trial IDs, actual
  mutations, raw/result hashes, and consequence. Promotion is derived false.
- Generated `campaign_state.json` is an atomic append-only receipt chain;
  duplicate execution, replay, trial, receipt, or result identities fail.
- Missing invariance feature/observation/action vectors now return
  `not_evaluable`; no default vectors are synthesized.
- Posterior entropy may increase. Entropy delta and observed information gain
  retain their mathematical signs.
- Mean response distance is now `predicted_signature_separation`.
- This rename is deliberately scoped to the new control-plane contract. The
  receipt-bound Phase 1 acquisition compiler/config/schema/fixture remain
  byte-identical to `5bc796f`; a regression test freezes their four SHA-256
  identities rather than invalidating prior Phase 1 receipts.
- The strictly offline measurement lane accepts synthetic fixtures only and
  validates common clock, sampling, skew, calibration, phases, packet and
  evaluator identity, hashes, and all-false authority before deterministically
  returning flexural-dominant, actuator-dominant, or ambiguous abstention.

## Evidence hashes

- Action SHA-256:
  `402a29e4cdc0c4cb90d41a83327ad8df5685544851b4e4d659129b3239744fd6`
- Evaluator digest:
  `906165a7faf334182a5d3bbee5189ef689c660a3f58b2d572a257b83d55bc359`
- Operator receipt SHA-256:
  `7155065350691aaef2d64f6a2fb4657ac2d01182d3355579ef9959cb9ccb8cea`
- Operator receipt digest:
  `67c2ab071ccf6a8c193328203573416c1d591ec666cb0c32b3f12817f13c8641`
- Operator trace SHA-256:
  `9e32549a81afc7802fd454f0650ed24fe964aa34d2c539e004d33bee1f6a383f`
- Ablation SHA-256:
  `67605e89e24eef01444b4c532a8ab088827266c6fc656e203373f4ba62a0cdcd`
- Measurement packet SHA-256:
  `4398417efa987ce578b98191ec8f87d2c8ab7b3498ae3689087c01e7b06de374`
- Empty persistent-state SHA-256 / digest:
  `addd4237ea5cc8437b53f8d70e9a8e4bba407f9cb3f06d84f331ece6aeb7ede9` /
  `b2e92cfe522c62eee804ec41863a1376231fe0967b529b2a17e05be8750d1153`
- Final project-state SHA-256:
  `0caafa1896ed6a90589005fbc96c0a6aaaea4b70ad304cbb81daf006bf241e1c`

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

- Focused decision/composition: 73 passed in 2.82 seconds.
- SAIL tier 1, fast contract: 36 passed in 0.62 seconds.
- SAIL tier 2, synthetic golden: 58 passed in 2.17 seconds.
- SAIL tier 3, integration: 75 passed and 2 subtests passed in 28.00
  seconds. A first attempt correctly rejected a changed frozen Studio index;
  the new route was kept standalone and the frozen index restored.
- SAIL tier 4, retained evidence: 6 passed in 2.67 seconds.
- Tiers 5 and 6 were not opened because provider and hardware authority were
  not granted.
- First broad corrective diagnostic: 853 passed, 3 skipped, 328 subtests, with
  one fail-closed stale project-state hash in the LF00-LF13 acceptance path.
  The final authority hash was then rebound and the acceptance test rerun.
- Final uninterrupted repository suite: 854 passed, 3 skipped, 328 subtests in
  1298.24 seconds (21:38), recorded after the final authority rebind.
- Read-only Studio returned HTTP 200 for `/live-operator.html` and its
  publication manifest.

No Brev, provider, GPU, hardware, camera, serial device, robot gateway, or paid
resource was touched; therefore no Brev inventory mutation or cleanup was
required. Proof class is
`retrospective_action_frozen_c2_decision_plane_abstention`.

## Corrective changed-file inventory

Modified:

- `.factory/orchestration-ledger.md`
- `GOAL.md`
- `configs/projects/pawn_rank12_reachable_bg_hackathon_v1.json`
- `configs/sail/live_operator_c2_v1.json`
- `docs/autonomous-workflow/goal-loop-sail-live-operator-integration.md`
- `docs/autonomous-workflow/project_state.json`
- `docs/briefs/036-sail-live-operator-contract.md`
- `docs/manager-log/002-sail-live-operator.md`
- `docs/research/2026-07-22-sail-live-operator-ablation.md`
- `docs/reviewer-messages/026-sail-live-operator.md`
- `docs/run-logs/2026-07-22-sail-live-operator-integration.md`
- `docs/session-logs/025-executor-sail-live-operator.md`
- `src/sim2claw/cli.py`
- `src/sim2claw/sail/live_operator.py`
- `src/sim2claw/studio_web/live-operator.html`
- `src/sim2claw/studio_web/live-operator.js`
- `src/sim2claw/studio_web/publication/sail_live_operator_v1/manifest.json`
- `src/sim2claw/studio_web/publication/sail_live_operator_v1/receipt.json`
- `tests/test_sail_cli.py`
- `tests/test_sail_live_operator.py`

Added:

- `docs/reviewer-messages/027-sail-control-plane-corrective-review.md`
- `src/sim2claw/sail/live_evidence.py`
