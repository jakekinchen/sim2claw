# AVFoundation Source Localization Preregistration

Date: 2026-07-24

Proof class: `camera_source_observability_preregistration`

The sealed D405 stationary campaign proved six complete D405 sources but
rejected all six combined trials because the C922 MP4 had repeatable container
PTS gaps at D405 open and close/finalization. It did not prove missing C922
physical exposures or identify the source, AVFoundation client, encoder, or
mux layer.

This transaction freezes a native source-callback probe before implementation.
It permits exactly twelve no-motion camera trials after the implementation is
committed: six C922-only controls and six C922-plus-D405-lifecycle treatments
in fixed balanced order, with zero replacements, robot motions, or provider
calls. The treatment opens the D405 at five seconds and stops it at 25 seconds
inside a 30-second C922 source window.

The evaluator will distinguish replicated AVFoundation source discontinuity,
replicated late-client/buffer pressure, source continuity under the lifecycle
factor, mixed evidence, and prerequisite abstention. Source continuity is not
physical-exposure proof and cannot reclassify the sealed container result.

The GPT-5.6 Pro Robotics and Sims review supplied advisory hypotheses and
instrumentation recommendations only. It has no evaluator, hardware, training,
promotion, or task authority.

## Pre-live implementation checkpoint

The preregistration was committed first at
`92c2f964befc9cc6ac33a2d1a918c63edc1f0fcd`. The implementation then added:

- a native Swift `AVCaptureVideoDataOutputSampleBufferDelegate` source probe;
- exact-name camera and requested-format selection;
- local sequence, `CMSampleBuffer` PTS/duration, `mach_continuous_time`,
  dimensions, pixel format, and callback timing;
- Apple dropped-frame reason and reason-info attachments;
- session runtime error/interruption and device connect/disconnect events;
- exact compiler, source, runner, FFmpeg, FFprobe, and compiled-binary binding;
- fixed campaign orchestration and an independent raw-event evaluator;
- fail-closed schema, order, budget, artifact, authority, and identity checks.

Source SHA-256:

- Swift probe
  `903658a0dd34012371e732b15277a2f5ce4070e9fdde532f7f4bf42dc586e4be`;
- Python runner/evaluator
  `7be758151ce3f48a3725443fa9c4b25161ad40ae186f12cc6e98ec5a5b4c3b72`.

Sixteen direct tests and the 60-test combined camera/HIL/Studio gate pass.
Swift type-check and Python compilation pass. Tests include malformed/replayed
events, source/runner/binary substitution, order and authority mutation,
post-hoc threshold change, PTS corruption, replicated source discontinuity,
late-client drop classification, USB-disconnect abstention, and byte-identical
evaluation materialization.

No camera, robot, simulator, provider, or training path was opened for this
checkpoint.
