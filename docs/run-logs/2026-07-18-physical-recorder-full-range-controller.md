# Physical Recorder Full-Range Controller

Date: 2026-07-18 America/Chicago

## Evidence and diagnosis

The retained physical attempt
`runs/teleop_recordings/failed_attempts/20260718T202325Z-c3a1dca3`
ended after the shoulder lift made no measurable progress for five seconds.
The leader requested about -61 degrees, the follower was near -16 degrees, and
the old LeRobot present-position clamp repeatedly held the command near -20
degrees. The four-degree command error did not produce enough movement at that
loaded pose, so the command could never advance toward the full target.

A later operator-authorized bounded diagnostic moved shoulder lift by -2 and
-4 degrees and returned at P=16. Residuals remained below 0.8 degrees, voltage
held at 12.1 V, temperature remained 29-30 C, status stayed zero, and current
was 0-2 raw units. This rules out a generally dead shoulder motor but does not
prove loaded-pose chess reach.

## Controller correction

Physical gateway v2 removes LeRobot's repeated present-position clamp and owns
three separate constraints:

- the full follower target remains the registered leader delta, clipped to the
  90-degree body workspace and measured follower calibration limits;
- commands advance by elapsed time at 60 degrees/s for body joints, 90
  degrees/s for wrist roll, and 100 units/s for the gripper; and
- command-to-actual backlog is capped at 6 degrees for general body joints, 8
  degrees for shoulder lift and wrist roll, and 12 gripper units.

This permits full travel over time without accumulating an unbounded command
that could jump after an obstruction clears. A joint that remains more than
the stall threshold behind its command and makes less than 0.5 degrees of
measurable progress for five seconds still fails closed.

## Upstream comparison

The correction was checked against current public upstream behavior rather
than prior-project implementation:

- Hugging Face's SO-101 setup and real-robot guides use the standard LeRobot
  follower and require same-ID calibration across teleoperation and recording:
  <https://huggingface.co/docs/lerobot/main/en/so101> and
  <https://huggingface.co/docs/lerobot/main/en/getting_started_real_world_robot>.
- The current LeRobot SO follower keeps `max_relative_target` optional and only
  performs the extra present-position read and clamp when it is explicitly
  configured: <https://github.com/huggingface/lerobot/blob/main/src/lerobot/robots/so_follower/so_follower.py>.
- The current generic teleoperation loop reads observation and leader action,
  sends the processed action, and paces the loop at a fixed requested rate:
  <https://github.com/huggingface/lerobot/blob/main/src/lerobot/scripts/lerobot_teleoperate.py>.
- LeRobot issue 3131 documents intermittent SO-101 synchronized-read failures,
  lower-frequency mitigation, and a collaborator-accepted bounded retry
  workaround when its delay does not disturb control:
  <https://github.com/huggingface/lerobot/issues/3131>.
- LeRobot issue 1010 records voltage and mixed-servo-firmware causes for
  incorrect status packets. Those remain hardware checks, not claims that a
  software retry repairs a USB reset:
  <https://github.com/huggingface/lerobot/issues/1010>.

Current telemetry is serialized on the same bus owner, sampled at 5 Hz, and is
diagnostic rather than motion-critical. One missed current packet marks the
telemetry stale; position or command-path communication failures still end the
attempt and release torque. Motion-critical position reads receive one bounded
2 ms retry for a transient malformed or missing packet; a repeated failure
still ends the attempt. The recorder defaults to 30 Hz for smoother physical
control without the 60 Hz bus pressure used by the upstream generic loop.

## Verification boundary

Fixture tests prove that a 60-degree leader request reaches the full requested
follower pose, control is independent of recorder sample interval, a frozen
joint still trips the five-second guard, one frozen joint cannot be hidden by
other moving joints, and a missed diagnostic current packet is nonfatal.

The controller has not yet been promoted as a successful physical chess
recording. The next operator-started recording is the live loaded-pose
validation, and the retained fault trace remains non-training evidence.
