# Executor log 060 — ObservableEpisode.v2-min

CC01 implemented a strict causal record and deterministic adapters without
opening cameras, gateway, serial, MuJoCo task execution, or hardware.

The accepted contract binds exact little-endian float64 requested, mapped,
sent, and applied rows; monotonic host/device/application timing; six-joint
state; link poses; canonical board-plane object SE(2) with covariance; contact;
first motion; final outcome; provenance; and explicit unavailable channels.
Applied commands are stored as rows as well as hashes, so a timing challenger
can be localized before downstream state divergence.

Validation:

- `uv run pytest -q tests/test_observable_episode.py` — `9 passed`.
- Observable plus V2 static regression — `14 passed`.
- Current campaign graph baseline — `2 passed`.
- `git diff --check` — pass.
- Full repository run excluding the known macOS C922 successor segfault test:
  `1832 passed, 8 skipped, 332 subtests passed, 16 failed, 6 errors`.
  The failures are outside CC01: historical frozen-hash drift, owner-local
  publication/source inventory drift, native-camera topology drift, live
  retrospective reproduction drift, cross-test module-import state, and the
  still-uncommitted CC02 temporal draft. The CC01-focused and campaign-graph
  gates remain green.
- The unexcluded full run reached the known
  `test_current_c922_pose_p2_successor.py` native-extension segmentation fault
  after exposing the same unrelated early failures; it did not invalidate a
  CC01 assertion.

No physical task attempt occurred. Directional transfer remains `0/0` in both
directions. The next slice is CC02, which must freeze and run the four
V2-admitted actions under direct-target and diagnostic `0.11 s` ZOH paths and
emit this schema.
