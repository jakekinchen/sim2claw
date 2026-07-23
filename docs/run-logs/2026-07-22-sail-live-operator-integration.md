# SAIL decision/evidence control-plane corrective closeout

Date: 2026-07-22

## Scope

Replaced the manually sequenced retained C2 parameter-family search with one
generic, typed, budgeted SAIL decision plane. The plane binds arbitrary campaign
IDs through data contracts, composes the existing causal surfaces, freezes
predicted intervention signatures before results, and fail-closes on identity,
budget, posterior, affected-factor, evaluator, or promotion drift. It has no
intervention executor. Generic simulator-result admission is disabled; the
only currently admissible result lane deterministically recomputes synthetic
offline measurement results from packet-bound raw fixtures.

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

- Bare `--result` and simulator-receipt CLI input were removed. A
  self-consistent simulator raw/result/receipt forgery now fails because no
  trusted deterministic simulator adapter exists.
- The sealed-packet-bound offline measurement receipt binds campaign, selected
  and frozen interventions, action, evaluator code/config/source identities,
  exact execution/trial IDs, raw/result hashes, and evaluator-recomputed
  consequence. Promotion is derived false.
- Generated `campaign_state.json` has one ignored repository-relative path
  keyed by campaign and canonical config digest, independent of `--output`.
  Duplicate execution, replay, trial, receipt, or result identities fail across
  output roots.
- State transitions are prepared in memory. Selected intervention, likelihoods,
  affected-factor scope, closure, every artifact, and the receipt validate
  before the append-only state transition is committed as the final write. A
  rejected poison update leaves state bytes and budget unchanged.
- Exported `verify_live_operator_receipt` rechecks canonical digest, config,
  source, compiler and output hashes, the current state chain/head/budget,
  action/evaluator/intervention identity, and all-false authority. Artifact,
  resealed authority, and stale-state tamper fail.
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
  `80e427ec673043ca875b226a73a832c45b587baa6547d87f0e38fbb82b7807cd`
- Operator receipt digest:
  `4f9fa5a8ca18d06517e5097cddf4b034e196e8944f146868cd14a318cb31dfc6`
- Operator trace SHA-256:
  `9e32549a81afc7802fd454f0650ed24fe964aa34d2c539e004d33bee1f6a383f`
- Ablation SHA-256:
  `67605e89e24eef01444b4c532a8ab088827266c6fc656e203373f4ba62a0cdcd`
- Measurement packet SHA-256:
  `4398417efa987ce578b98191ec8f87d2c8ab7b3498ae3689087c01e7b06de374`
- Empty persistent-state SHA-256 / digest:
  `b9c63de8971cb4e280d6dbe547e0f552907c51431c674f6e61f8aab951988cd2` /
  `5e5bd42d11c6dc52977b1621114a37d7a7df83ef2fee6668258510e551cf94df`
- Canonical persistent-state path:
  `outputs/sail/live-campaign-state-v1/7e28883008da09d99249ea827284e7f28a78836a24e16e4c086ec8357baafd3f/campaign_state.json`
- Final project-state SHA-256:
  `c419ef9ca5a5d1445add86c9dd31972711fbfc6867acef1536137852f751fa89`

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

- Focused decision/composition: 78 passed in 4.47 seconds.
- SAIL tier 1, fast contract: 36 passed in 0.67 seconds.
- SAIL tier 2, synthetic golden: 58 passed in 2.28 seconds.
- SAIL tier 3, integration: 75 passed and 2 subtests passed in 28.47 seconds.
- SAIL tier 4, retained evidence: 6 passed in 2.91 seconds.
- Tiers 5 and 6 were not opened because provider and hardware authority were
  not granted.
- The prior corrective full suite passed 854 tests, skipped 3, and passed 328
  subtests. The second-corrective uninterrupted full-suite result is recorded
  below after the final authority rebind.
- Final second-corrective uninterrupted repository suite: 859 passed, 3
  skipped, and 328 subtests passed in 1306.07 seconds (21:46).
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
- `docs/reviewer-messages/027-sail-control-plane-corrective-review.md`
- `docs/run-logs/2026-07-22-sail-live-operator-integration.md`
- `docs/session-logs/025-executor-sail-live-operator.md`
- `src/sim2claw/cli.py`
- `src/sim2claw/sail/live_evidence.py`
- `src/sim2claw/sail/live_operator.py`
- `src/sim2claw/studio_web/live-operator.html`
- `src/sim2claw/studio_web/live-operator.js`
- `src/sim2claw/studio_web/publication/sail_live_operator_v1/manifest.json`
- `src/sim2claw/studio_web/publication/sail_live_operator_v1/receipt.json`
- `tests/test_sail_cli.py`
- `tests/test_sail_live_operator.py`

Added:

- `docs/reviewer-messages/028-sail-global-state-receipt-rereview.md`
