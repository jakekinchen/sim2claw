# Executor log 088 — Observable registration OR0

Date: `2026-07-29`

## Outcome

OR0 passes. The new deterministic corpus binds 20 retained sources, the exact
531-row sealed action, 1029 C922 frames, 171 D405 RGB frames, camera timing
metadata, V04 fit and known-outcome validation surfaces, 3DGS registration,
static geometry, first divergence, RP04N, and immutable C6.

The observability matrix records five available, four bounded, two diagnostic,
two recoverable, and seven unavailable channels. Pawn carry and visual contact
events are recoverable; exact C922 intrinsics, physical contact state, metric
wrist depth, support height, and global mapping remain unavailable or
unapproved.

## Changed paths

- `configs/evaluations/observable_registration_corpus_v1.json`
- `src/sim2claw/observable_registration_corpus.py`
- `scripts/build_observable_registration_corpus.py`
- `tests/test_observable_registration_corpus.py`
- `configs/decisions/observable_registration_corpus_v1_closeout.json`

## Evidence

- freeze commit: `e72ae0c`;
- receipt SHA-256:
  `e4332e483908c4ba465c99bff3a543deb50bacf6c0ae281ea12555fafa52a739`;
- artifact SHA-256:
  `92402191296f3edcb518434a71ec35f7ea1969bccff091e94433a13790d68397`;
- exact gateway-sent SHA-256:
  `3b034bd965d4bf1a71591cc77f033e97f1fe8eb30aa75cb314cc529b4e40e3ef`.

## Validation

- `uv run pytest tests/test_observable_registration_corpus.py -q` —
  `4 passed`;
- authoritative receipt rebuilt twice byte-identically after the freeze commit;
- `git diff --check` — pass;
- autonomous workflow audit — clean;
- Ruff is not installed in the project environment and was recorded as
  unavailable rather than claimed.

## Boundary

This inventory does not calibrate a camera, approve global mapping, validate a
physical contact state, change C6, run a simulator, open hardware, or advance a
transfer numerator. It opens OR1 camera/world modeling.
