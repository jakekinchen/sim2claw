# OR155 independent review — closure-locus and contact provenance

Date: 2026-08-13

Decision: `STOP`

Scientific verdict: `PASS_TO_CLOSE_STOP_EXTERNAL_INPUT_BOUNDARY`

Evidence anchors: `100` — the official receipt verifies with content digest
`48f1f25a57bb6438c8b8aa38ebae054533dc34cd15d6e992f161db73377f526f`
and file SHA-256
`d6cead85f5a749710d9712712beb72c09aa8bec108dd7e7673f76f75fb0cca44`.
All 15 frozen source hashes match. The sole official execution used six
`mj_forward` calls and zero dynamics steps, replays, fits, searches, renders,
task evaluations, mutations, hardware actions, or paid compute.

At closed-command hold sample `241`, the named-jaw midpoint remains
`34.481658 mm` from exact D1. Raw measured gripper position is more open than
the sent position at samples `224`, `232`, and `241`, so early physical
actuator closure is not supported. At broad contact sample `271`, the closest
compiled collision is a non-named fixed-gripper CAD mesh at `-0.129711 mm`;
the nearest named jaw remains `+4.523143 mm` clear. The body-level contact does
not prove a named-jaw, bilateral, or pad enclosure.

All claim limits remain false. The retained corpus supplies zero admissible
fit rows and zero untouched validation cohorts for this discrepancy. OR155 is
a known-result, quarantined discrepancy attribution—not a correction, replay,
task success advancement, promotion, physical result, or transfer result. No
successor is admissible; stop at the external-input boundary.
