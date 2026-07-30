# Executor session 094 — OR22 retained RGB consequence proxies

Decision: `CONTINUE`

Evidence anchor: `100`

## Result

The accepted successful-source D405 tracks yield 23 jaw midpoint/aperture-axis
proxies and 10 accepted crown-to-jaw proxies. The first accepted crown is at
sample 290. No retained row has a distinct two-pass accepted pawn-base point,
so pawn-axis orientation abstains rather than being inferred.

The event timing is already tightly reconciled:

- simulator unilateral contact sample 231 is inside physical contact 228–232;
- simulator tilt onset sample 248 is inside physical lift 247–260;
- simulator sustained support loss sample 260 equals physical definite carry
  start 260.

The physical and simulated episodes therefore do not show a remaining coarse
timing mismatch at contact/lift/carry onset. The unresolved observable is the
physical pawn orientation/contact consequence inside the same interval.

## Verification

```text
uv run --locked pytest -q tests/test_retained_rgb_contact_consequence_proxies.py
2 passed

uv run --locked python scripts/build_retained_rgb_contact_consequence_proxies.py
PASS_BOUNDED_JAW_CROWN_EVENT_PROXY_PAWN_AXIS_INSUFFICIENT
```

No depth, force, reannotation, cross-episode merge, mapping approval, or
transfer claim was introduced.
