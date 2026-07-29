# Session 077 — Realized-Action C1 EpisodeTwinBundle

Date: `2026-07-29`

Decision: `PASS_C1_ACTIVATE_C2`

## Result

C1 emitted `8` deterministic `EpisodeTwinBundle.v1` artifacts:

- fit: `4`;
- validation: `3`;
- sealed: `1`.

Each bundle has raw little-endian binary tensors for operator-requested
float32, gateway-sent float32, measured-joint float64, and source-timestamp
float64 data. Bundle manifests bind the C0 receipt/sample assets, declared
dtype, unit, joint order, shape, raw hash, file hash, source-time semantics,
and exact first row.

Two complete builds produced zero hash differences across all `41` files.

## Sealed mission boundary

The sealed D1-to-D2 bundle binds:

- bundle artifact:
  `c696e4218f914fd118b4f7c2613655e96befcb66c9dfd439703451db9bb75555`;
- gateway-sent tensor:
  `3b034bd965d4bf1a71591cc77f033e97f1fe8eb30aa75cb314cc529b4e40e3ef`;
- measured joints:
  `ec75ad25adf9957311e837744af7340e27b602cfec5a2985db7841b5c3558312`;
- source timestamps:
  `68e87c15992123e4415b2a3ec6d1a8e68cffd1ca642ac35002ed255544829f48`.

Its only object state is the evaluator-owned initial D1 metric observation,
whose accepted registration error is `3.1006005 mm`. No terminal D2 endpoint
is present as replay input.

## Missingness

Actuator application command/time, force, per-sample contact, per-sample
metric object pose, hidden pawn pose, wrist depth, and terminal endpoint input
remain explicitly missing.

## Verification

- `uv run pytest tests/test_episode_twin_bundle.py tests/test_realized_action_corpus.py -q`
  — `5 passed`.
- Two generated tree digest lists were identical.
- Workflow audit and diff check pass in the closeout transition.
- No camera, gateway, serial, hardware, motion, pawn attempt, or paid compute
  was used.

## Proof boundary

These are source-evidence bundles, not simulator replays or transfer
numerators. C2 is active.
