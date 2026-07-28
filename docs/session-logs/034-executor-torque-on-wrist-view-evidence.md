# Executor 034 - Torque-on wrist-view evidence

## Decision

`CONTINUE`

## Result

The staged executor now records a two-second native dual-camera observation
inside an exact 40 Hz final-target hold before `gateway.close()`. The receipt
reverifies six native report/callback/video artifacts and binds appended D405
frames to nearest final-hold joint samples on the host-continuous clock.
Capture and alignment remain diagnostic and explicitly are not exposure
synchronization.

The supplied route is frozen at
`configs/hardware/d405_tag_view_reposition_route_v2.json`. Its two 361-sample
motion hashes are
`af91e8ae30fffb64bc6045a29fe321328872a5af1e5e1462a87f203c5a0a4c42`
and
`893eee18a5581350be46c239cbb3311b5d3e7d7016cbe7c3fd0db130b7bca154`.
The current-scene preview observed zero external contacts.

Validation:

```text
uv run --offline pytest -q tests/test_wrist_view_reposition.py tests/test_physical_canary.py tests/test_physical_gateway.py tests/test_native_dual_camera.py
40 passed in 2.07s
```

No robot, serial bus, or camera was opened. No Brev resource was used.
