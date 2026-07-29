# Session 076 — Realized-Action C0 Corpus Freeze

Date: `2026-07-29`

Decision: `PASS_C0_ACTIVATE_C1`

## Result

C0 closed with a deterministic inventory of all `29` retained recording
directories that contain both a recording receipt and samples.

The frozen whole-episode cohorts are:

- fit: `4`;
- validation: `3`;
- sealed: `1`;
- metadata-conflicted provenance-only: `11`;
- other explicitly named diagnostic/provenance roles: `10`.

The sealed episode is only
`20260727T041737Z-89190e53`. It is absent from fit and validation. Its raw
`b2 -> b1` receipt metadata remains visible beside the evaluator-corrected
current canonical `d1 -> d2` task.

## Exact source bindings

The compiler independently reproduced:

- operator-requested float32:
  `5d58874c166d2df9b890177ab9f1ef0a6934e53d46242b2346bf3428e5904c79`;
- gateway-sent float32:
  `3b034bd965d4bf1a71591cc77f033e97f1fe8eb30aa75cb314cc529b4e40e3ef`;
- measured joints float64:
  `ec75ad25adf9957311e837744af7340e27b602cfec5a2985db7841b5c3558312`;
- source timestamps float64:
  `68e87c15992123e4415b2a3ec6d1a8e68cffd1ca642ac35002ed255544829f48`.

It also preserved `0 / 531` actuator application/ack timestamps, `151 / 531`
rate-limited rows, `151 / 531` safety-clamped rows, and `284 / 531`
requested-versus-sent mismatches.

## Prospective order

An initial deterministic compiler rehearsal occurred before the freeze commit.
It is explicitly non-authoritative. The same artifact digest was rebuilt after
the contract/compiler/test freeze was pushed at `4a21f92`; only that second
build is the recorded C0 result.

Generated ignored receipt:

- path:
  `outputs/realized_action_retrospective_corpus_v1/receipt.json`;
- file SHA-256:
  `7511180748e12b0df842129004d692458b23df297df8cd94106100487c490bd5`;
- canonical artifact SHA-256:
  `232c80bb28cac325f54d829e31fd2b84d12df85df1948d3d8fb5b4fd3e4739d1`.

Tracked closeout:
`configs/decisions/realized_action_retrospective_corpus_v1_closeout.json`.

## Verification

- `uv run pytest tests/test_realized_action_corpus.py -q` — `2 passed`.
- `git diff --check` — passed.
- Ruff was not installed in the project environment; no dependency was added.
- No camera, gateway, serial, hardware, motion, pawn attempt, or paid compute
  was used.

## Proof boundary

This is an evidence-inventory and split result, not a transfer numerator.
Legacy square labels remain noncanonical unless an evaluator-owned correction
exists. C1 is active.
