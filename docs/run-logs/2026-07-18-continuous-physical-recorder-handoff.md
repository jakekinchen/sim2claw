# Continuous physical recorder handoff

Date: 2026-07-18 America/Chicago

## Failure addressed

Physical Start previously ran a standalone Sync request, closed the gateway and
released follower torque, waited through a browser-owned countdown, then opened
a second gateway session for recording. The follower could sag during that gap,
so the second session observed a calibration offset near 33 degrees even when
the arms had been physically matched before Sync.

## Implemented contract

- C922 diagnostic capture starts before the physical gateway opens.
- The server owns one continuous gateway session for bounded Sync, a three-second
  torque-held countdown, final paired-pose registration, and teleoperation.
- The 12-degree registration guard and 20-degree Sync admission limit remain
  unchanged. No calibration file is rewritten or relaxed.
- Leader motion, follower hold drift, and final registration are checked during
  the countdown. Any failure closes the gateway and releases follower torque.
- Pre-arm failures retain stage-specific leader/follower six-joint vectors and
  one second of C922 post-roll in failed-attempt storage.
- The browser performs one Start request and has a bounded request watchdog; it
  no longer owns physical timing or a separate automatic Sync request.
- Browser disconnects while a response is being written no longer terminate the
  Studio server.

## Verification

- `uv run ruff check ...`: passed for every changed Python and test file.
- `uv run pytest -q`: 66 tests and 10 subtests passed.
- `node --check src/sim2claw/studio_web/studio.js`: passed.
- `git diff --check`: passed.
- Live loopback Studio recorder endpoint: idle and responsive after restart.
- Live torque-off gateway preflight: both expected SO-101 buses and same-arm
  calibration hashes passed; maximum measured body offset was 7.30 degrees,
  under the unchanged 12-degree guard; follower torque remained off.
- The Record surface was reloaded and inspected in the actual in-app browser.

No live Sync or physical Start was initiated during verification. The continuous
motion path is covered by fake-bus regression tests and remains operator-gated in
the UI.
