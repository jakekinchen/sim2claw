# Brief 041 - Torque-on wrist-view evidence

## Outcome

Correct the invalid post-close inspection boundary exposed by stage-1 v2 arm
sag. Capture the native D405/C922 streams while the gateway is still holding
the exact stage target, bind the camera artifacts and D405-to-joint host-clock
alignment, then close torque off on every exit.

## Invariants

- Preserve the reviewed 361-sample motion bytes.
- Use a separately hashed two-second exact-target hold for capture telemetry.
- Start capture only after the target residual passes.
- Finish capture before releasing gateway torque.
- Reverify native report, callback ledger, source-video, and browser-video
  hashes.
- Align only appended D405 frames overlapping the hold to nearest 40 Hz joint
  samples; never claim exposure synchronization.
- Read the anchor and stage targets from a hash-bound route file.
- Root owns live execution.

## Verification

- Current-scene preview of the supplied two-stage route.
- Success-path camera/hash/alignment fixture.
- Camera-start failure proves torque-off close and write-once failure receipt.
- Existing physical-canary, gateway, and native-camera regressions.
