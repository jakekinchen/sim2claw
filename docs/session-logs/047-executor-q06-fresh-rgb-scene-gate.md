# Executor log 047: Q06 fresh RGB scene gate

Date: 2026-07-27

Decision: Q06 produced a terminal pre-motion safety boundary. No case was
admitted.

## Fresh scene evidence

A motion-free camera capture was recorded at:

`runs/bidirectional-pawn-push/20260727-q06-scene-v1/`

Capture receipt SHA-256:
`ee6d71d98723e5133097c24c30ab8d2b16881e6554d22078aae632fe99966730`.

The capture used the repository-owned native dual-camera recorder for C922 and
D405 color plus the existing Pi IMX708 SSH capture path. It did not construct
the robot gateway, issue a robot command, or request metric depth.

Bound scene frames:

```text
C922 RGB:
5803cce3e87aa5066589e8aada64b81fe37e2a821e70b47aeb32807860a22883
D405 color RGB:
e95fc50183c63e34d5f25fb4bb4f18ea0d278af9364ae5197a12b9546633e049
Pi IMX708 RGB:
3bfe6a4862fb980eb1afd53b4091779bd71c53bf1f3d03aa5c1d98cebd5c78ab
```

The C922 frame verifies the expected sparse reset layout, apparently upright
pawns, and apparently empty preregistered destinations. This is RGB
adjudication only.

## Frozen exclusion result

Q05 requires every selected source-to-destination route to remain at least
`88.9 mm` from each excluded object. All ten preregistered routes are only
`44.45 mm` center-to-route from another reset-layout pawn, or approximately
`16.85 mm` after subtracting the `13.8 mm` pawn-base radii. The nearest
excluded square is:

```text
R01 h1  R02 d1  R03 g2  R04 e2  R05 a2
S01 e2  S02 b1  S03 a8  S04 e8  S05 e8
```

Receipt:
`runs/bidirectional-pawn-push/20260727-q06-scene-v1/scene_gate_receipt.json`.

Receipt SHA-256:
`3c81caaa626043d1a12c34bf9b05e11fa0e0823070b516f001e8857b5c59ec0c`.

Status:
`terminal_safety_boundary_no_admissible_case`.

Safe in-scope alternatives are exhausted: all ten frozen cases cover both
directions and both board sides; the F1 stroke widening cannot change initial
exclusion clearance; setup prefixes may move only the robot, not pawns; and
case expansion or gate weakening after scene observation is forbidden.

The remaining remedies require a person or separately authorized system to
reconfigure the scene, or a prospective new evaluator with a different safety
contract. Both are outside this queue. This is not F3: no healthy-corridor
motion was admitted and no counted attempt began.

## Validation

```text
uv run --offline pytest -q \
  tests/test_bidirectional_q06_scene_gate.py \
  tests/test_bidirectional_off_source_evaluator.py
.....                                                                    [100%]
5 passed in 0.10s

python -m json.tool \
  configs/evaluations/bidirectional_q06_rgb_scene_gate_v1.json
PASS

shasum -a 256 \
  runs/bidirectional-pawn-push/20260727-q06-scene-v1/scene_gate_receipt.json
3c81caaa626043d1a12c34bf9b05e11fa0e0823070b516f001e8857b5c59ec0c
```

Proof class: `fresh_rgb_scene_and_frozen_exclusion_geometry`.

Counted physical attempts: `0/10`. No action was compiled. No robot motion,
training, paid compute, or Brev resource was used. Camera recorder processes
were absent after capture.
