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
