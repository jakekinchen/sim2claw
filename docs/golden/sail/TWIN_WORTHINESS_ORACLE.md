# TwinWorthiness Oracle

Gate statuses are exactly `pass`, `fail`, or `not_evaluable`.

- `pass`: all required observations are present and every frozen threshold
  passes.
- `fail`: required observations are present and at least one threshold fails.
- `not_evaluable`: a required observation or identity is absent. It never
  contributes to a higher level.

| Level | Required passing gates | Data generation | Policy selection | Physical canary |
| --- | --- | --- | --- | --- |
| `TW-DIAGNOSTIC` | G0 | closed | closed | closed |
| `TW-REPLAY` | G0-G1 | closed | closed | closed |
| `TW-DATA` | G0-G2 | open for strict admission only | closed | closed |
| `TW-SELECTION` | G0-G4 | open | open | closed |
| `TW-PHYSICAL-CANARY` | G0-G4 plus separate authority packet | open | open | protocol-eligible |

Levels are monotonic only while the exact certificate bytes and all bound
artifacts remain valid. Missing or modified artifacts reduce capability to
unavailable. Even `TW-PHYSICAL-CANARY` does not grant robot motion; the reviewed
gateway and explicit owner authority remain independent.

Thresholds and required channels are frozen in
`configs/sail/twin_worthiness_v1.json`. Changes require a new version.
