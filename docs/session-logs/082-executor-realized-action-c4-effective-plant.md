# Session 082 — Realized-Action C4 Effective Plant

Date: `2026-07-29`

Decision: `PASS_C4_ACTIVATE_C5`

## Result

The identified effective plant preserves all requested and gateway-sent source
bytes and emits separate applied predictions. It uses the preregistered
three-sample hold and fit-only direction-conditioned offsets. All per-joint
first-order response searches selected alpha `1.0`, so no additional smoothing
or time constant is supported.

On three untouched validation episodes and `1340` samples, joint RMS improves
from `2.3682 deg` to `1.0551 deg` (`55.45%`) and provisional EE RMS improves
from `16.7864 mm` to `6.9650 mm` (`58.51%`). Every joint improves.

The report-only sealed episode improves from `2.1047 deg` to `0.8937 deg` and
from `16.9254 mm` to `7.3730 mm` provisional EE RMS.

## Evidence

Generated ignored receipt:

- file: `outputs/realized_action_effective_plant_v1/receipt.json`;
- file SHA-256:
  `5afba2e280e7c34308aa51548b938a6af54bd299e49038d6083043342b353c07`;
- artifact SHA-256:
  `df50459a4c7f60894690610c8578f67e064c13de3d0a9f7e286aa8c26e736aa6`.

Two builds were byte-identical.

## Boundary

The hold is sample-domain association, not causal latency. The diagnostic
`0.11 s` ZOH is not calibrated. Provisional EE metrics do not approve the
global mapping. No task/contact/transfer result was added. C5 is active.
