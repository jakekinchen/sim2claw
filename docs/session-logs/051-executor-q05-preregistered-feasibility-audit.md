# Executor log 051: Q05 preregistered-feasibility audit

Date: 2026-07-27

Decision: Q05's frozen evaluator is preserved, but its case family was
structurally infeasible before Q06.

The evaluator remains byte-identical at SHA-256
`8450682fac61ac064198b90858f58e6753b0d701ed55f067f91d88ed04604479`.
Its route-clearance requirement is `88.9 mm`. Every route contains its source
point, and every occupied source in the frozen sparse layout has another pawn
one file and one rank away. The best possible source-to-nearest-exclusion
distance is therefore:

```text
sqrt(2) * 44.45 mm = 62.861793 mm < 88.9 mm
```

The evaluator could not admit any case under the frozen reset layout,
independent of the later C922 capture. This should have been rejected by a
pre-freeze feasibility check. It is a preregistered-contract infeasibility,
not a physical safety event, mechanical failure, task attempt, or transfer
result.

The v4 scene's far-side source-to-left-base planar distances are independently
reproduced as `0.478092 m` (B7), `0.485519 m` (D7), and `0.508618 m` (F7).
Distance alone does not adjudicate kinematic reachability here, so those rows
remain diagnostic and do not affect the terminal gate.

No data was opened, no action was compiled, no robot gateway was constructed,
and no robot motion occurred.
