# Retained-C2 Trusted Adapter Preregistration

Date: 2026-07-23

Status: frozen and tested; no retained-C2 simulator replay executed.

## Boundary

This checkpoint registers exactly one non-fixture adapter,
`retained_action_frozen_c2_v1`. Its request contains source and evaluator
identities but no fixture schema, caller-authored result, consequence,
likelihood, factor update, score, or promotion value. The adapter owns
mutation, runner invocation, raw artifact materialization, independent
consequence evaluation, and content-addressed receipt issuance.

The live campaign and adapter contract are reusable contracts. Python does not
enumerate campaign IDs or candidate IDs. The adapter registry contains exactly
one new non-fixture adapter. Candidate mutation fields are contract-declared
per factorial axis.

## Frozen intervention

- intervention count: `0 / 1` used at this checkpoint
- anchor replay count: `0 / 4` used at this checkpoint (`4 / 18` owner ceiling)
- retry count: `0`
- provider calls: `0`
- action SHA-256:
  `402a29e4cdc0c4cb90d41a83327ad8df5685544851b4e4d659129b3239744fd6`
- family: balanced two-axis factorial
- candidates: baseline, flexural contact, actuator load path, combined
- hypotheses: `flexural_rubber_contact_v1`,
  `actuator_load_path_v1`
- predicted signatures: competing flexural versus actuator factorial main
  effects
- affected factors: `factor:rubber_contact_patch`,
  `factor:actuator_load_path`

Posterior movement requires admitted evaluator-owned mechanism evidence and a
strict task-plus-EE pass. The absolute main-effect threshold is `0.02`.
Rejection or abstention preserves the 0.5/0.5 prior.

Strict consequence thresholds:

- EE RMS at most `0.02 m`
- joint RMS at most `2.0 degrees`
- absolute loaded-aperture bias at most `0.5 degrees`
- bilateral contact retained through release onset
- piece lift, bilateral lift retention, lift-and-transport, release, simulation
  stability, rubber load path, slip-reduction, energy, and force-transition
  gates all required by the independent anchor evaluator
- lower RMS without strict task success is diagnostic only

No IK, action offset, clipping, resampling, reordering, corrective suffix,
assistance, or measured-state substitution is authorized.

## Content identities

- adapter contract file SHA-256:
  `156540d4bd800e6bad95058573ebb3b9bbdbbdd57f472ef320c9da353dd4ee11`
- adapter contract canonical digest:
  `1cccd19a249f84606ddedda4925767eff5b3ef34294ba1de757323634b95dbfd`
- live campaign file SHA-256:
  `893ff56afb7ac2476acd061cdf89865394e5b51a0462975faa369469b314f311`
- independent consequence evaluator SHA-256:
  `ac6751a22eaa840357ce422ff1806a8f52dad92c152d649f43c995fbd883a330`
- adapter implementation SHA-256:
  `edb1e0a8b8492f049b9a0ea30b123522e221cfb91e64e435b5d125c1088d7d7e`

The live campaign deterministically selects
`simulator_preregistered_c2_factorial` with frozen predicted score `0.99`,
before any result exists.

## Interface verification

`60 passed`:

```text
uv run pytest -q \
  tests/test_sail_c2_trusted_adapter.py \
  tests/test_sail_live_operator.py \
  tests/test_sail_cli.py
```

The C2 tests use an explicit action-identity-preserving test double. They do
not execute the retained simulator. Real replay execution remains gated on
the commit containing this preregistration.

## Proof class and closed authority

The eventual result can establish only retained action-frozen simulator and
infrastructure evidence. It cannot establish physical calibration, task
authority, policy quality, training admission, simulator promotion, robot
gateway or motion authority, or transfer.
