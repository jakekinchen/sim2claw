# Executor session 092 — OR21 exact replay contact introspection

Decision: `CONTINUE`

Evidence anchor: `100`

## Result

OR19 reproduced exactly before the introspection trace was accepted. The
requested, gateway-sent, timestamp, and identified-applied source identities
remain unchanged, and the reproduced OR19 artifact digest is
`f33198841ce3e70a11dfc7f2e617174248e436bd18474b3bb626700b6674e184`.

The read-only 5 ms trace localizes the simulated consequence:

- unilateral named-jaw contact and tangential slip begin at source sample 231;
- pawn tilt first exceeds 5 degrees at sample 248;
- bilateral jaw contact begins at sample 255;
- sustained board-support loss begins at sample 260;
- maximum raw MuJoCo normal contact force is `6.130562`;
- maximum named-jaw tangential slip speed is `0.241345 m/s`.

The earliest residual is therefore inside the unilateral-contact/slip interval
before bilateral enclosure. This does not identify a physical force or admit a
contact parameter.

## Verification

```text
uv run --locked pytest -q tests/test_observable_registration_exact_replay_contact_introspection.py
2 passed

uv run --locked python scripts/build_observable_registration_exact_replay_contact_introspection.py
PASS_EXACT_REPRODUCTION_CONTACT_TRACE
```

## Proof limits

No model, configuration, action, camera, hardware, or authority changed.
Global mapping and transfer remain false. OR22A may now evaluate the already
frozen Pi/action timing association without using task contact or outcome.
