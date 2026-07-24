#!/usr/bin/env python3
"""Retrace a stopped physical replay prefix back to episode sample zero."""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import numpy as np

from sim2claw.physical_gateway import shortest_delta_degrees
from sim2claw.physical_trace_replay import (
    START_BODY_RATE_DEG_S,
    START_COMMAND_HZ,
    START_GRIPPER_RATE_S,
    START_WRIST_ROLL_RATE_DEG_S,
    _default_gateway_factory,
    _gateway_identity,
    _mapped_leader_target,
    load_physical_trace_source,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recording", type=Path, required=True)
    parser.add_argument("--attempt", type=Path, required=True)
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    if not args.yes:
        parser.error("--yes is required to acknowledge physical follower motion")

    source = load_physical_trace_source(
        args.recording,
        allowed_root=args.recording.resolve().parent,
    )
    attempt = args.attempt.resolve()
    receipt = json.loads((attempt / "replay_receipt.json").read_text())
    if receipt["source_samples_sha256"] != source.receipt["samples_sha256"]:
        raise RuntimeError("Attempt and recording source hashes do not match.")
    rows = [
        json.loads(line)
        for line in (attempt / "replay_samples.jsonl").read_text().splitlines()
        if line.strip()
    ]
    if not rows:
        raise RuntimeError("Attempt has no completed source samples to retrace.")
    last_index = int(rows[-1]["source_sample_index"])
    if last_index < 0 or last_index >= len(source.rows):
        raise RuntimeError("Attempt source sample index is outside the recording.")

    commands = source.commands[: last_index + 1][::-1].copy()
    source_elapsed = source.elapsed_seconds[: last_index + 1]
    intervals = np.diff(source_elapsed)[::-1]
    elapsed = np.concatenate(([0.0], np.cumsum(intervals)))
    gateway = _default_gateway_factory(_gateway_identity())
    started_at = time.time()
    completed = 0
    opened = None
    try:
        opened = gateway.open(enable_motion=True, paired_pose_confirmed=True)
        leader_start = np.asarray(opened["leader_start_degrees"], dtype=np.float64)
        follower_start = np.asarray(opened["follower_start_degrees"], dtype=np.float64)
        first_delta = commands[0] - follower_start
        first_delta[4] = shortest_delta_degrees(
            float(commands[0, 4]),
            float(follower_start[4]),
        )
        maximum_body_delta = float(np.max(np.abs(first_delta[:4])))
        if maximum_body_delta > 45.0 or abs(float(first_delta[4])) > 60.0:
            raise RuntimeError(
                "Live follower is not close enough to the stopped prefix endpoint."
            )
        if abs(float(first_delta[5])) > 20.0:
            raise RuntimeError("Live gripper is not close enough to the prefix endpoint.")
        if np.any(commands < gateway.lower_limits - 1e-6) or np.any(
            commands > gateway.upper_limits + 1e-6
        ):
            raise RuntimeError("Return prefix leaves the calibrated joint envelope.")
        relative = commands - follower_start
        relative[:, 4] = [
            shortest_delta_degrees(float(value), float(follower_start[4]))
            for value in commands[:, 4]
        ]
        if float(np.max(np.abs(relative[:, :4]))) > 90.0:
            raise RuntimeError("Return prefix exceeds the body excursion guard.")

        pre_roll_seconds = max(
            0.5,
            maximum_body_delta / START_BODY_RATE_DEG_S,
            abs(float(first_delta[4])) / START_WRIST_ROLL_RATE_DEG_S,
            abs(float(first_delta[5])) / START_GRIPPER_RATE_S,
        )
        pre_roll_steps = max(1, math.ceil(pre_roll_seconds * START_COMMAND_HZ))
        wall_started = time.monotonic()
        for index in range(1, pre_roll_steps + 1):
            deadline = wall_started + index / START_COMMAND_HZ
            time.sleep(max(0.0, deadline - time.monotonic()))
            fraction = index / pre_roll_steps
            smooth = fraction * fraction * (3.0 - 2.0 * fraction)
            target = follower_start + smooth * first_delta
            gateway.leader.set_target(
                _mapped_leader_target(target, leader_start, follower_start)
            )
            gateway.sample(time.monotonic() - wall_started)

        trace_started = time.monotonic()
        for reverse_index, (target, target_elapsed) in enumerate(
            zip(commands, elapsed, strict=True)
        ):
            time.sleep(max(0.0, trace_started + float(target_elapsed) - time.monotonic()))
            gateway.leader.set_target(
                _mapped_leader_target(target, leader_start, follower_start)
            )
            gateway.sample(time.monotonic() - wall_started)
            completed = reverse_index + 1
            if completed == 1 or completed % 50 == 0:
                print(
                    json.dumps(
                        {
                            "event": "return_progress",
                            "completed": completed,
                            "total": len(commands),
                        }
                    ),
                    flush=True,
                )
        final_sample = None
        for _ in range(20):
            time.sleep(1.0 / START_COMMAND_HZ)
            gateway.leader.set_target(
                _mapped_leader_target(commands[-1], leader_start, follower_start)
            )
            final_sample = gateway.sample(time.monotonic() - wall_started)
        assert final_sample is not None
        final_actual = final_sample["follower_actual_position_degrees"]
        gateway.close()
        result = {
            "schema_version": "sim2claw.physical_replay_return_to_start.v1",
            "status": "completed",
            "source_recording_id": source.receipt["recording_id"],
            "source_samples_sha256": source.receipt["samples_sha256"],
            "stopped_source_sample_index": last_index,
            "reversed_source_sample_count": completed,
            "target_start_command_degrees": source.commands[0].tolist(),
            "final_actual_degrees": final_actual,
            "wall_duration_seconds": time.time() - started_at,
            "physical_follower_torque_enabled": False,
        }
        (attempt / "return_to_start_receipt.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n"
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    finally:
        gateway.close()


if __name__ == "__main__":
    raise SystemExit(main())
