# Session 087 — Realized-Action Goal Closeout

Date: `2026-07-29`

Decision: `COMPLETE_SAFE_SCOPE_EXTERNAL_SERVICE_BOUNDARY`

## Outcome

The C0--C9 realized-action calibration goal loop is complete for every safe
zero-new-physical-data card. C8's read-only Studio proof is committed on
`main`; C9 is closed at the follower-elbow service boundary.

The strongest new quantitative advancement is the C4 effective plant:
untouched validation joint RMS improved from `2.368` to `1.055 deg`
(`55.45%`) and provisional end-effector RMS improved from `16.786` to
`6.965 mm` (`58.51%`). The action-to-task experiment was also genuinely
attempted exactly once and remains an honest `0/1`; it localized the simulator
failure to absent grasp/carry contact followed by a late launch at samples
`386/388`.

## Final evidence ladder

1. Simulator task success: previously confirmed, unchanged.
2. Physical endpoint to simulator endpoint: `1/1` episodes and `2/2` endpoint
   states, unchanged.
3. Physical realized gateway-sent action trajectory to matching simulator task
   outcome: `0/1`, terminal for the retained corpus.

Other owner metrics remain:

- SIM-to-REAL pawn-task transfer: `0/0`.
- Physical pawn-task attempts: `0/10`.
- Globally approved physical/model mapping: no.
- Predictive policy ranking: insufficient physical sample.

These zeros are preserved because no authorized, mechanically qualified
physical path exists; they are not represented as successful completion.

## Restart

`configs/evaluations/realized_action_post_service_successor_v1.json` defines
the ordered PS0--PS8 restart path. It is a precondition contract, not an
executable physical packet. Elbow service, torque-off re-inventory,
no-contact tracking qualification, global mapping approval, new observable
source episodes, and separate authorization precede any counted attempt.

## Cleanup

No camera, gateway, serial bus, torque, physical motion, pawn attempt, paid
compute, or Brev resource was opened by this goal loop. The temporary
read-only Studio server was stopped during final cleanup. Campaign-relevant
verification passed with `61` tests and `2` subtests; JavaScript syntax,
Python compileall, JSON parsing, diff check, and the workflow audit passed.
