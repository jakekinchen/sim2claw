# D405 stationary RGBD capture ingestion

Date: 2026-07-25

Proof class: `physical_stationary_rgbd_capture_only`

Verdict: `physical_stationary_rgbd_capture_ingested_identity_reconciled`

## Scope

This was a read-only evaluation of the existing rosbag2 database,
librealsense enumeration/readiness receipt, and extracted RGB/depth artifacts.
The evaluator opened the SQLite database with `mode=ro&immutable=1`. It did not
open a camera, access a robot, issue motion, infer a board pose, or use an
AprilTag.

The positive result proves only that the named physical capture contains
internally consistent stationary RGBD evidence. "Stationary" is the capture
designation; robot stationarity was not independently instrumented. The result
does not grant board registration, camera-to-robot extrinsic, policy, task, or
physical-task authority.

## Command

```bash
.venv/bin/python scripts/evaluate_d405_stationary_rgbd_capture.py \
  runs/d405-rgbd-capture/20260725-stationary-v2 \
  runs/d405-rgbd-readiness/20260725-elevated-inventory \
  --output runs/d405-rgbd-capture/20260725-stationary-v2/evaluation/receipt.json
```

## Results

- The database has 72 topics. Both
  `/device_0/sensor_0/Depth_0/image/data` and
  `/device_0/sensor_0/Color_0/image/data` contain 135 frames at 848x480.
- Depth spans 4.467638083 s; color spans 4.467432209 s.
- Same-order rosbag timestamp pairing produced 135 pairs. Absolute RGB-depth
  delta was 0.003333-0.407584 ms, mean 0.160825874 ms, median 0.161541 ms,
  and p95 0.3038164 ms.
- The two extracted metadata pairs share frame counters 60 and 61. Their
  color-minus-depth device timestamp deltas are 0.304 ms and 0.305 ms.
- The capture declares depth as Z16 and color as RGB8, both 30 fps.
  `Depth_Units` is 0.000100 m per Z16 unit.
- The two meter-scaled depth CSVs are 480x848. Their nonzero fractions are
  0.805886399 and 0.800081073; nonzero medians are 0.0968 m and 0.0970 m.
  The depth PNGs are false-color previews, not metric depth arrays.
- Exact 848x480 depth/color intrinsics and the internal Depth-to-Color
  rotation/translation are preserved in the receipt. These are camera-internal
  calibration only, not camera-to-robot calibration.
- The readiness artifact reports librealsense 2.58.3.0 and preserves hashes for
  `rs-record`, `rs-convert`, and `rs-enumerate-devices`. The receipt also hashes
  every consumed capture and readiness artifact.

## Device identity reconciliation

The two serial values are distinct fields, not conflicting claims:

- The capture database and librealsense enumeration both record SDK logical
  `Serial Number=130322273474`.
- Those same two records both contain
  `Asic Serial Number=133323070214` and
  `Firmware Update Id=133323070214`.
- The readiness receipt's ioreg USB identity reports
  `serial_number=133323070214`.
- Product ID `0B5B` and physical port `0-2-1` also agree between the capture
  database and enumeration.

The evaluator requires every link above and fails closed if any one changes.
It never asserts that `130322273474` equals `133323070214`.

## Lineage hashes

- Contract:
  `221489a98fc0291a93fd71f10aeefdc6af088a9fbe20b6def9fb5de2fbc10570`
- Capture database:
  `deb2d2b6365918d6024f568e85f478434713277847e68dac3f245f43cf9d25eb`
- Readiness receipt:
  `b959f994cfecedc9d99fdca7d6933293d369cbcdd4bd4deef409737c0fcd90a0`
- Enumeration stdout:
  `1ad1405f6b7f0fc3e011968fc61e6be70fe8d120716380577f392e8dbd566f1a`
- Generated ignored receipt:
  `aa9eeb5081977c13c88763b6e1f93c1d1dbed459dd20da4de03084ec60a8070a`

## Verification

```text
.venv/bin/pytest -q tests/test_d405_stationary_rgbd_capture.py
.....                                                                    [100%]
5 passed in 0.31s
```

The focused tests cover CDR decoding, timestamp delta semantics, successful
field-specific identity reconciliation, fail-closed USB mismatch handling, and
the local artifact integration result.
