"""Replay a physical follower command trace through the current MuJoCo arm.

This measures joint-space response agreement only.  It does not validate object
pose, contact, learned-policy behavior, or task success.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import mujoco
import numpy as np

from .scene import (
    CURRENT_TASK_PIECE_LAYOUT,
    ROBOT_JOINTS,
    build_scene_spec,
    initialize_robot_poses,
)
from .state_trace import EpisodeStateTraceRecorder


SIM_REPLAY_SCHEMA = "sim2claw.physical_command_sim_replay.v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def physical_values_to_sim(
    values: list[float] | np.ndarray,
    gripper_bounds: np.ndarray,
) -> np.ndarray:
    physical = np.asarray(values, dtype=np.float64)
    if physical.shape != (6,) or not np.all(np.isfinite(physical)):
        raise ValueError("physical replay requires six finite joint values")
    converted = np.empty(6, dtype=np.float64)
    converted[:5] = np.deg2rad(physical[:5])
    low, high = (float(value) for value in gripper_bounds)
    converted[5] = low + np.clip(physical[5], 0.0, 100.0) / 100.0 * (high - low)
    return converted


def replay_physical_recording(recording_directory: Path) -> dict[str, Any]:
    recording_directory = recording_directory.resolve()
    receipt_path = recording_directory / "recording_receipt.json"
    samples_path = recording_directory / "samples.jsonl"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("mode") != "physical_follower":
        raise ValueError("simulator accuracy replay requires a physical-follower recording")
    if _sha256(samples_path) != receipt.get("samples_sha256"):
        raise ValueError("physical source samples do not match their receipt")
    samples = [
        json.loads(line)
        for line in samples_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not samples:
        raise ValueError("physical source recording is empty")

    model = build_scene_spec(piece_layout=CURRENT_TASK_PIECE_LAYOUT).compile()
    data = mujoco.MjData(model)
    initialize_robot_poses(model, data)
    state_trace = EpisodeStateTraceRecorder(
        model,
        piece_layout=CURRENT_TASK_PIECE_LAYOUT,
        fps=max(1, int(receipt.get("sample_hz") or 20)),
        proof_class="simulation_physical_command_replay",
    )
    actuator_ids: list[int] = []
    qpos_addresses: list[int] = []
    for joint in ROBOT_JOINTS:
        name = f"left_{joint}"
        actuator_id = mujoco.mj_name2id(
            model,
            mujoco.mjtObj.mjOBJ_ACTUATOR,
            name,
        )
        joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        if actuator_id < 0 or joint_id < 0:
            raise ValueError(f"current simulator is missing {name}")
        actuator_ids.append(actuator_id)
        qpos_addresses.append(int(model.jnt_qposadr[joint_id]))
    bounds = model.actuator_ctrlrange[actuator_ids]
    gripper_bounds = bounds[-1]

    first_actual = physical_values_to_sim(
        samples[0]["follower_actual_position_degrees"],
        gripper_bounds,
    )
    data.qpos[qpos_addresses] = np.clip(first_actual, bounds[:, 0], bounds[:, 1])
    data.ctrl[actuator_ids] = data.qpos[qpos_addresses]
    mujoco.mj_forward(model, data)

    errors: list[np.ndarray] = []
    trace_path = recording_directory / "sim_replay_trace.jsonl"
    previous_timestamp: float | None = None
    nominal_dt = 1.0 / max(1, int(receipt.get("sample_hz") or 20))
    with trace_path.open("w", encoding="utf-8") as handle:
        for index, sample in enumerate(samples):
            timestamp = float(sample["timestamp_monotonic_seconds"])
            dt = nominal_dt if previous_timestamp is None else timestamp - previous_timestamp
            if not math.isfinite(dt) or dt <= 0.0 or dt > 1.0:
                dt = nominal_dt
            previous_timestamp = timestamp
            command = physical_values_to_sim(
                sample["follower_command_degrees"],
                gripper_bounds,
            )
            actual = physical_values_to_sim(
                sample["follower_actual_position_degrees"],
                gripper_bounds,
            )
            command = np.clip(command, bounds[:, 0], bounds[:, 1])
            data.ctrl[actuator_ids] = command
            steps = max(1, round(dt / float(model.opt.timestep)))
            mujoco.mj_step(model, data, nstep=steps)
            state_trace.capture(data, phase="physical_command_replay", force=True)
            simulated = data.qpos[qpos_addresses].astype(float)
            error = simulated - actual
            errors.append(error.copy())
            row = {
                "schema_version": SIM_REPLAY_SCHEMA,
                "sample_index": index,
                "source_timestamp_seconds": timestamp,
                "dt_seconds": dt,
                "command_sim_units": command.tolist(),
                "physical_actual_sim_units": actual.tolist(),
                "simulated_position": simulated.tolist(),
                "sim_minus_physical_error": error.tolist(),
            }
            handle.write(json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n")

    error_array = np.asarray(errors, dtype=np.float64)
    rmse = np.sqrt(np.mean(np.square(error_array), axis=0))
    maximum = np.max(np.abs(error_array), axis=0)
    body_rmse_deg = np.rad2deg(rmse[:5])
    body_max_deg = np.rad2deg(maximum[:5])
    visual_trace_path = recording_directory / "sim_replay_state_trace.json"
    visual_trace = state_trace.write(visual_trace_path)
    report = {
        "schema_version": SIM_REPLAY_SCHEMA,
        "source_recording_id": receipt["recording_id"],
        "source_samples_sha256": receipt["samples_sha256"],
        "sample_count": len(samples),
        "joint_order": list(ROBOT_JOINTS),
        "joint_rmse_sim_units": rmse.tolist(),
        "joint_max_absolute_error_sim_units": maximum.tolist(),
        "body_joint_rmse_degrees": body_rmse_deg.tolist(),
        "body_joint_max_absolute_error_degrees": body_max_deg.tolist(),
        "aggregate_body_joint_rmse_degrees": float(
            np.sqrt(np.mean(np.square(np.rad2deg(error_array[:, :5]))))
        ),
        "maximum_body_joint_error_degrees": float(np.max(body_max_deg)),
        "gripper_rmse_actuator_rad": float(rmse[5]),
        "trace_path": trace_path.name,
        "trace_sha256": _sha256(trace_path),
        "state_trace_path": visual_trace_path.name,
        "state_trace_sha256": visual_trace["sha256"],
        "state_trace_schema_version": visual_trace["schema_version"],
        "state_trace_frame_count": visual_trace["frame_count"],
        "state_trace_fps": visual_trace["fps"],
        "state_trace_duration_seconds": visual_trace["duration_seconds"],
        "state_trace_piece_layout": visual_trace["scene"]["piece_layout"],
        "state_trace_manifest_url": visual_trace["scene"]["manifest_url"],
        "simulator_scene": "photo_aligned_chess_workcell_v1:left_so101",
        "comparison_scope": "joint_space_command_response_only",
        "learned_policy_verified": False,
        "object_or_contact_dynamics_verified": False,
        "task_success_verified": False,
        "created_at": datetime.now(UTC).isoformat(),
    }
    _write_json(recording_directory / "sim_replay_receipt.json", report)
    return report
