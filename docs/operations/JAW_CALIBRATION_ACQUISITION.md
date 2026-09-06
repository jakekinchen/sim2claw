# Jaw calibration acquisition preparation

Status: software preparation only; no camera opened, capture, fit or motion.

## Evidence and next measurement

OR155 places the OR154 simulated closed-hold jaw midpoint 34.482 mm from exact
D1 and attributes first broad contact to a non-named gripper mesh. This is a
simulated spatial discrepancy, not a measured physical correction. OR156 bounds
the tested source-row clock alternative to 1.142 ms at closure without identifying
camera exposure or actuator application time. Neither supports moving a jaw by
that offset or retiming recorded actions to the video.

Sources:

- `configs/decisions/observable_registration_or154_closure_locus_audit_v1_closeout.json`
- `configs/decisions/observable_registration_source_clock_provenance_audit_v1_closeout.json`
- `configs/evaluations/observable_registration_external_metric_pad_surface_packet_v1.json`

OR48 already specifies 442 unchanged no-object command rows over 22.1 seconds:
cycles 1–2 for fit, cycle 3 for untouched validation, and the wide cycle for
stress. Preserve those bytes and original timestamps. Its old packet grants no
current execution authority.

## Prepared software

The frozen OR44 depth recorder remains unchanged. The separate
`tools/macos/RealSenseD405RGBDRecorder.cpp` requests 848×480 at 30 Hz and retains
raw Z16 depth, RGB8 color, actual strides/offsets, both stream intrinsics and
distortion, column-major depth-to-color extrinsics, separate frame numbers,
device timestamps/domains, host frameset arrival, and supported exposure/gain/FPS
metadata. Unsupported metadata is explicitly null.

An explicit serial, experiment ID and new output directory are required. There
is no overwrite or retry. Captures are capped at 900 frames, with a two-second
frame timeout and a 40-second frame-loop deadline; SDK startup has no real-time
guarantee. Partial data remains without a completion manifest. The default 800
frames is nominally 26.7 seconds; actual coverage and its relation to the gateway
must be established independently from recorded clocks.

Build/help and rejected-command checks perform no SDK context creation:

```bash
uv run --locked python scripts/build_d405_rgbd_recorder.py \
  --output outputs/rgbd-recorder-build-NEW-ID
```

Validate a separately acquired, existing capture offline:

```bash
uv run --locked python -m sim2claw.d405_rgbd_integrity \
  outputs/NEW-CAPTURE \
  --expected-serial 130322273474 \
  --expected-experiment NEW-EXPERIMENT-ID
```

The standard-library validator binds all four files by SHA-256 and reports
frame gaps, timestamp comparability and optional-metadata coverage. Exit zero
means `STRUCTURALLY_VALID_UNREVIEWED`. Synthetic fixtures remain synthetic;
physical provenance, synchronization, jaw geometry and calibration admission
remain false. Freeze returned hashes before annotation/fit. An initial hash
does not authenticate acquisition or detect pre-existing same-length tampering.

SDK framesets and equal clock-domain labels do not prove simultaneous exposure
or synchronization with robot clocks. The new utility does not coordinate or
authorize robot motion; future acquisition must use the reviewed gateway and
current camera/robot leases.

Dependency: the existing installed librealsense 2.58.3, for native profiles,
frames, calibration and metadata. No new package/runtime was introduced. APIs
were checked against installed `rs_pipeline.hpp`, `rs_frame.hpp` and `rs.h`;
upstream source: [Intel RealSense librealsense](https://github.com/realsenseai/librealsense).
SDK headers are system includes; warnings-as-errors remain enabled for our code.

## Physical inputs and acceptance

1. Confirm present robot/workcell identity, safe stationary pose, no object in
   the jaws, camera visibility and cable clearance.
2. Attach one rigid, uniquely identified landmark assembly to each jaw. Record
   independently measured dimensions and marker-to-contact-surface transforms,
   uncertainty, units, method and source evidence. A servo encoder or unscaled
   image point is not an independent load-side measurement.
3. Verify both jaws remain observable throughout the range. Camera factory
   intrinsics/extrinsics do not establish camera-to-board or jaw-to-robot mapping.
4. Freeze a new experiment, leases, evaluator and capture/gateway timing contract
   before acquisition. Retain requested, sent and measured joints and all raw
   RGBD. Missing actuator acknowledgement/application times stay missing.
5. Validate provenance and integrity, then derive jaw observations with measured
   uncertainty. Keep cycle 3 untouched until model and fit are frozen.

Existing OR48 gates require at least five metric frames per direction per
partition, both jaws visible, validation RMS ≤0.75 mm, ≥30% improvement over zero
cant, condition number ≤50, and geometry/encoder-lag correlation ≤0.85. Geometry
must be distinguishable from encoder offset/scale and camera extrinsics.
These gates have not been executed. If observations cannot meet them, improve
the measurement design before adding model parameters.

Only an independent mapping pass can support a new successor with one frozen
model change and one unchanged-action replay. Score contact identity, enclosure,
support loss, object motion, release and final pose. This packet excludes
friction/compliance/material fitting and task-outcome tuning. New whole-episode
validation is separately required for predictive simulator claims.

Actual native RGBD capture, landmark extraction, clock association with the
gateway and physical jaw-mapping accuracy remain unverified.
