# AVFoundation Dual-Camera Common Session v1 — Terminal Degraded

Date: 2026-07-24

## Result

The sole preregistered stationary native common session completed once. Both
exact inputs and outputs were admitted, both active formats survived start,
and both streams delivered bounded callbacks. The frozen evaluator still
returned `common_session_callback_delivery_degraded` because the active format
index for each device reset after stop.

This is a terminal degraded callback-health result, not a retry request and not
a Twin-fidelity, synchronization, motion-reliability, metric-depth, simulator,
or task pass.

## Exact identities

- Preregistration commit: `53ce2651711c3b38fae74d05a8e57639a54b0cad`
- Observation commit: `86d8005b5a97b2fc853be26db7db9b6788517525`
- Sealing commit: `84dcdb1cbe853ced3e9cd41e63d6feb3b379abd2`
- Contract: `c2ad7c333e06affae037998318976931da638c5eec2806e769f9c2971f817af1`
- Observer source: `8ee7ddc0a298c2ffc960961e58c8d86708f92a3d9015ce2be148a694c39e8e51`
- Observed evaluator: `380510825d3871e43408a285faca028ff2fcb6b8f72212c4c734786f310e52f5`
- Sealing evaluator: `49e6a87230d8b12a3d7a9c136a756ea4868fd2718acaee23019dd105db0b03fc`
- Runtime binary: `c5e2caab3739ee9406935b01530b2092d5eab12c6354b4776438d9e123308cd0`
- Prelaunch: `c17f86dbc7dfa6b938c58b2355644d1a9fb25951923b2c8e77c946d513d1eb89`
- Attempt: `e5c9e02e207f38c2c05b67d000928aeb41c51edf34fb3f3a4cf27a669b6968d5`
- Raw observation: `f78c363d3e45f4f6a191d8156f047e338d4ee786c9cb47fe10ab58af3b6a44d5`
- Empty stderr: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- Evaluation file/digest: `76cca950c1d696015ed31620dcbfd02f88aec65ba86c24b8e3f7051fc8aaea7b`
- Receipt file: `a33ada6551f297a5c1f95838716c1411b412d8fc4575a7c924f3b27889a4b53b`
- Receipt digest: `910f334722dbd56ccbc45bc610711e3c9c87b7c19936f1abe515a3e5cb9c2a4e`

## Independent metrics and gates

| Stream | callbacks | drops | scored callbacks | scored PTS span | maximum interval |
|---|---:|---:|---:|---:|---:|
| C922 | 338 | 0 | 315 | 10.466967 s | 0.034033 s |
| D405 | 61 | 0 | 60 | 11.799967 s | 0.200000 s |

The common host window was `10.447306 s`. Callback-count, zero-drop, cadence,
and common-window gates passed. The only failed gates were:

- `after_stop:c922_format_index`
- `after_stop:d405_format_index`

The independent sealer normalized only absent Swift `Codable` optional-nil
fields to their typed `null` meaning. It changed no callback or stage value and
no scientific threshold.

## Budget and authority

- observation attempts: `1 / 1`
- common capture sessions: `1 / 1`
- independent camera sessions: `0`
- retries/replacements: `0 / 0`
- robot motion trials: `0`
- simulator replays: `0`
- provider calls: `0`
- video containers: `0`

The tracked exhaustion guard records this exact result. The separate
post-terminal control validates the guard and refuses before runner or device
delegation. The next step is a new preregistered isolated-camera-host
architecture, not another common-session attempt.
