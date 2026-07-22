# SAIL Mechanism Plugins and Posterior Fitting Run Log

Date: 2026-07-22

Milestone: P1-06

Proof class: deterministic synthetic mechanism-recovery fixtures plus
retrospective configuration wrappers; no physical mechanism identification

## Commands

```bash
uv run sim2claw sail-compile-mechanisms --config configs/sail/mechanism_registry_v1.json --output outputs/sail/retired-bg-v1/mechanisms
uv run pytest -q tests/test_sail_mechanisms.py tests/test_sail_contracts.py
uv run pytest -q tests/test_sail_belief_graph.py tests/test_sail_contracts.py tests/test_sail_evidence.py tests/test_sail_hardware_protocol.py tests/test_sail_mechanisms.py tests/test_sail_residuals.py tests/test_sail_surprise.py tests/test_sail_twin_worthiness.py
uv run pytest -q
git diff --check
```

## Frozen identities

- Configuration: `f8c509aae1658eb17f114089a052e20c6261c826e71389ffcf7e0cc9252cd8c5`
- Registry artifact: `fbda9c716f9a266850fc39b28d6dc8dbc897564e80ed658075ce3fd7e2ef0428`
- Seeded posteriors: `0a07a428fea54e8ea3f9f00b9cc842d165b630ec3f86c1339a44b1ec068a691a`
- Retained particles: `c7fa9b0fe616ba4e4afe9fe8007b4073e67ce93ccbbb03629aec3f977e1d8fd3`
- Receipt: `7468813ffc5d82ce07e74f1277f4cd2ded61468ab6f2ee1a2bc38a77330817b9`
- Receipt digest: `dd8cdee0d4e486ba94adaa41cf77435f4590c0db816bd845c0f30e7e7321dd38`
- Deterministic tree digest: `71f36b5cec8401f672f1a01126e7d2f665914bf99930b709c0bf7fd033c1fd97`

## Compilation result

- Ten frozen-ABI plugins and ten source-bound historical wrappers compile.
- Timing, deadband, load, geometry, gripper, fingertip contact, contact
  friction, timestep, object dynamics, and camera timing/extrinsics are
  represented as separate bounded hypotheses.
- Bounded SciPy fits expose Laplace covariance and 200 whole-row bootstrap
  replicates at 95% confidence without leaving parameter bounds.
- Six seeded conditional particles stay separate; incompatible structures are
  ranked and never averaged.
- Five retained mechanisms abstain because load, contact, metric object, or
  metric camera observables are absent. Supported retained wrappers reproduce
  configurations only and are not refit.
- Historical result bytes and source action bytes remain unchanged.

## Validation result

- GOLD-06 load-versus-geometry recovery: pass.
- GOLD-07 fingertip-contact-versus-aperture recovery: pass.
- GOLD-08 camera timing/extrinsic-versus-geometry recovery: pass.
- Focused mechanism/contract tier: 29 passed.
- Complete SAIL tier: 74 passed.
- Complete repository: 681 passed, three expected skips, 328 subtests passed
  in 1,233.26 seconds.
- Repeated compilation and output-tree identities match byte-for-byte.

## Claim boundary

The seeded fits prove deterministic bounded inference behavior on synthetic
fixtures. Historical wrappers reproduce prior simulator configurations but do
not identify physical parameters, revise prior results, select a simulator, or
grant training, policy, capture, motion, or transfer authority.

No provider, network campaign, paid compute, physical gateway, robot motion, or
Brev resource was used.
