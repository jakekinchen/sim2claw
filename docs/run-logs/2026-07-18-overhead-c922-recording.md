# Overhead C922 episode recording

Date: 2026-07-18 America/Chicago

## Scope

Add time-correlated overhead video to every Studio teleoperation recording
without adding camera work to the arm serial/control loop.

## Implemented contract

- The exact AVFoundation device name `C922 Pro Stream Webcam` is opened before
  the selected follower backend.
- Capture runs in a separate ffmpeg process using NV12 640x480, requested 30
  fps, 180-degree rotation, VideoToolbox H.264, and no audio.
- Arm samples include `overhead_video_time_seconds` against the camera start
  clock. The camera receipt records action start/stop offsets and the observed
  media properties reported by ffprobe.
- The arm backend closes before video finalization. Capture continues through
  at least one second of post-roll and uses ffmpeg's graceful `q` shutdown so
  the MP4 is finalized and seekable.
- A missing or prematurely exited camera fails the attempt closed. Available
  video, ffmpeg logs, samples, and draft state remain in failed-attempt storage.
- Saved episodes checksum `overhead_c922.mp4`, `overhead_video.json`, and the
  ffmpeg log. Video remains diagnostic-only and is not ACT training admission.

## Live camera verification

No arm bus was opened and no torque or motion was enabled for these checks.

- Exact-name camera open: passed.
- Graceful stop and readable H.264 MP4: passed.
- Configured mode: 640x480 NV12 at requested 30 fps.
- Short-run observed rate: `1635/58`, approximately 28.19 fps, with 109 frames.
- Action start offset: 1.060 seconds after video start.
- Requested post-roll: 1.000 seconds.
- Observed post-roll before capture-stop request: 1.004 seconds.
- Captured frame was visually inspected and confirmed upright with the chess
  workcell visible.

The earlier 1280x720 NV12 probe was rejected intermittently by AVFoundation and
fell back to 10 fps on the current shared USB path. The 640x480 mode avoided the
configuration fallback and preserves temporal evidence more reliably.

## Automated verification

- `uv run python -m unittest discover -s tests -p 'test_teleop_recording.py'`
- `uv run python -m unittest discover -s tests -p 'test_studio.py'`
- `uv run ruff check src/sim2claw/overhead_video.py src/sim2claw/teleop_recording.py tests/test_teleop_recording.py tests/test_studio.py`
