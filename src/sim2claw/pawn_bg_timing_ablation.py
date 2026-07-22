"""Action-byte-invariant timestamp/application timing ablation for B--G replay."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import mujoco
import numpy as np

from .learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .paths import REPO_ROOT
from .pawn_bg_action_frozen_gap import (
    _array_sha256,
    _load_partition,
    _point,
    _reconstruct_stage_d,
)
from .pawn_bg_demo_sim import (
    BASELINE_PIECE_BY_FILE,
    _piece_bodies,
    _trace_row,
    physical_values_to_sim_with_adapter,
)
from .pawn_bg_reward import load_reward_contract, score_episode
from .pawn_bg_workcell_fit import (
    WorkcellCandidate,
    _workcell_square_center,
    build_workcell_model,
)
from .grasp import _pinch_point


CONTRACT_PATH = REPO_ROOT / "configs" / "sysid" / "pawn_bg_timing_ablation_v1.json"
SCHEMA = "sim2claw.pawn_bg_timing_ablation.v1"
RECEIPT_SCHEMA = "sim2claw.pawn_bg_timing_ablation_receipt.v1"
TRACE_SCHEMA = "sim2claw.pawn_bg_timing_ablation_trace.v1"
BODY_JOINT_NAMES = (
    "shoulder_pan",
    "shoulder_lift",
    "elbow_flex",
    "wrist_flex",
    "wrist_roll",
)


class TimingAblationError(RuntimeError):
    """The timing experiment violates its frozen evidence boundary."""


def load_timing_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise TimingAblationError(f"cannot read timing contract {path}: {error}") from error
    if contract.get("schema_version") != SCHEMA:
        raise TimingAblationError("unexpected timing contract schema")
    authority = contract.get("authority")
    if not isinstance(authority, dict) or not authority or any(authority.values()):
        raise TimingAblationError("timing authority widened")
    invariance = contract.get("action_invariance", {})
    if not invariance or any(value is not True for value in invariance.values()):
        raise TimingAblationError("action invariance is not fail closed")
    delays = [
        float(value)
        for value in contract["variants"]["timestamp_aligned_zoh"][
            "application_delay_grid_seconds"
        ]
    ]
    if delays != sorted(set(delays)) or delays[0] != 0.0 or delays[-1] > 0.15:
        raise TimingAblationError("invalid delay grid")
    folds = contract["grouped_cross_validation"]["folds"]
    members = [str(recording_id) for fold in folds for recording_id in fold]
    if len(members) != 11 or len(set(members)) != 11:
        raise TimingAblationError("grouped CV folds must cover 11 unique episodes")
    return contract


def _array_receipt(actions: np.ndarray) -> dict[str, Any]:
    if actions.dtype != np.float64 or actions.ndim != 2 or actions.shape[1] != 6:
        raise TimingAblationError("source actions must be Nx6 float64")
    return {
        "shape": list(actions.shape),
        "dtype": str(actions.dtype),
        "sha256": _array_sha256(actions),
        "clipped_rows": 0,
        "post_policy_transform": None,
        "ik_correction": None,
        "assistance": False,
    }


def _mapped_episode(
    payload: tuple[dict[str, Any], str, str, list[dict[str, Any]]],
    candidate: WorkcellCandidate,
) -> dict[str, Any]:
    episode, source, destination, samples = payload
    binding = build_workcell_model(candidate)
    bounds = binding["actuator_bounds"]
    adapter = candidate.adapter()
    actions = np.ascontiguousarray(
        np.asarray(
            [
                physical_values_to_sim_with_adapter(
                    row["follower_command_degrees"], bounds[-1], adapter
                )
                for row in samples
            ],
            dtype=np.float64,
        )
    )
    measured = np.ascontiguousarray(
        np.asarray(
            [
                physical_values_to_sim_with_adapter(
                    row["follower_actual_position_degrees"], bounds[-1], adapter
                )
                for row in samples
            ],
            dtype=np.float64,
        )
    )
    if np.any(actions < bounds[:, 0]) or np.any(actions > bounds[:, 1]):
        raise TimingAblationError(f"action clipping would be required for {episode['recording_id']}")
    timestamps = np.asarray(
        [float(row["timestamp_monotonic_seconds"]) for row in samples], dtype=np.float64
    )
    timestamps -= timestamps[0]
    return {
        "episode": episode,
        "source": source,
        "destination": destination,
        "samples": samples,
        "timestamps": timestamps,
        "actions": actions,
        "measured": measured,
        "action_receipt": _array_receipt(actions),
    }


def _initialize(
    candidate: WorkcellCandidate, measured_first: np.ndarray, settle_steps: int
) -> dict[str, Any]:
    binding = build_workcell_model(candidate)
    model, data = binding["model"], binding["data"]
    data.qpos[binding["qpos_addresses"]] = measured_first
    data.ctrl[binding["actuator_ids"]] = measured_first
    mujoco.mj_forward(model, data)
    if settle_steps:
        mujoco.mj_step(model, data, nstep=settle_steps)
    return binding


def _legacy_step_then_record(
    mapped: dict[str, Any], candidate: WorkcellCandidate, settle_steps: int
) -> tuple[np.ndarray, dict[str, Any]]:
    binding = _initialize(candidate, mapped["measured"][0], settle_steps)
    model, data = binding["model"], binding["data"]
    outputs = np.empty_like(mapped["measured"])
    previous: float | None = None
    nominal_dt = 1.0 / int(mapped["episode"]["sample_hz"])
    for index, (timestamp, action) in enumerate(
        zip(mapped["timestamps"], mapped["actions"], strict=True)
    ):
        dt = nominal_dt if previous is None else float(timestamp - previous)
        previous = float(timestamp)
        data.ctrl[binding["actuator_ids"]] = action
        mujoco.mj_step(model, data, nstep=max(1, round(dt / float(model.opt.timestep))))
        outputs[index] = data.qpos[binding["qpos_addresses"]]
    schedule = {
        "semantics": "legacy_apply_integrate_then_record",
        "source_indices_at_rows": list(range(len(mapped["actions"]))),
        "application_delay_seconds": 0.0,
    }
    schedule["sha256"] = canonical_digest(schedule)
    return outputs, schedule


def _timestamp_aligned_zoh(
    mapped: dict[str, Any],
    candidate: WorkcellCandidate,
    *,
    settle_steps: int,
    delay_seconds: float,
    servo_deadband_degrees: dict[str, float] | None = None,
) -> tuple[np.ndarray, dict[str, Any]]:
    binding = _initialize(candidate, mapped["measured"][0], settle_steps)
    model, data = binding["model"], binding["data"]
    times = mapped["timestamps"]
    actions = mapped["actions"]
    outputs = np.empty_like(mapped["measured"])
    transitions: list[list[float | int]] = []
    last_index: int | None = None
    timestep = float(model.opt.timestep)
    deadband = servo_deadband_degrees or {}
    nominal_gain = model.actuator_gainprm[:, 0].copy()
    nominal_bias = model.actuator_biasprm[:, 1].copy()

    def apply_servo_model(action: np.ndarray) -> None:
        data.ctrl[binding["actuator_ids"]] = action
        for joint_name, threshold_degrees in deadband.items():
            try:
                joint_index = BODY_JOINT_NAMES.index(joint_name)
            except ValueError as error:
                raise TimingAblationError(
                    f"unsupported servo deadband joint: {joint_name}"
                ) from error
            actuator_id = binding["actuator_ids"][joint_index]
            qpos_address = binding["qpos_addresses"][joint_index]
            inactive = abs(float(action[joint_index] - data.qpos[qpos_address])) <= math.radians(
                float(threshold_degrees)
            )
            scale = 0.0 if inactive else 1.0
            model.actuator_gainprm[actuator_id, 0] = nominal_gain[actuator_id] * scale
            model.actuator_biasprm[actuator_id, 1] = nominal_bias[actuator_id] * scale

    for row_index, timestamp in enumerate(times):
        outputs[row_index] = data.qpos[binding["qpos_addresses"]]
        if row_index == len(times) - 1:
            break
        interval = float(times[row_index + 1] - timestamp)
        step_count = max(1, round(interval / timestep))
        for step in range(step_count):
            now = float(timestamp) + step * timestep
            source_index = max(
                0,
                int(np.searchsorted(times, now - delay_seconds, side="right") - 1),
            )
            if source_index != last_index:
                transitions.append([now, source_index])
                last_index = source_index
            apply_servo_model(actions[source_index])
            mujoco.mj_step(model, data)
    schedule = {
        "semantics": "record_at_timestamp_then_apply_zoh_over_next_interval",
        "application_delay_seconds": float(delay_seconds),
        "servo_deadband_degrees": deadband,
        "source_index_transitions": transitions,
    }
    schedule["sha256"] = canonical_digest(schedule)
    return outputs, schedule


def _fk_points(candidate: WorkcellCandidate, states: np.ndarray) -> np.ndarray:
    binding = build_workcell_model(candidate)
    points = []
    for state in states:
        binding["data"].qpos[binding["qpos_addresses"]] = state
        mujoco.mj_forward(binding["model"], binding["data"])
        points.append(_point(binding))
    return np.asarray(points, dtype=np.float64)


def _stall_counts(
    mapped: dict[str, Any], simulated: np.ndarray, contract: dict[str, Any]
) -> tuple[np.ndarray, np.ndarray]:
    settings = contract["stall_probe"]
    measured_step = np.abs(np.diff(mapped["measured"][:, :5], axis=0))
    command_gap = np.abs(mapped["actions"][:, :5] - mapped["measured"][:, :5])
    stall = np.vstack(
        (
            np.zeros((1, 5), dtype=bool),
            (measured_step < np.radians(float(settings["real_stationary_maximum_step_degrees"])))
            & (command_gap[1:] > np.radians(float(settings["command_measurement_minimum_gap_degrees"]))),
        )
    )
    simulated_gap = np.abs(mapped["actions"][:, :5] - simulated[:, :5])
    reproduced = stall & (
        simulated_gap
        > np.radians(float(settings["sim_reproduction_minimum_gap_degrees"]))
    )
    return stall.sum(axis=0), reproduced.sum(axis=0)


def _episode_metrics(
    mapped: dict[str, Any],
    simulated: np.ndarray,
    candidate: WorkcellCandidate,
    contract: dict[str, Any],
) -> dict[str, Any]:
    error_degrees = np.degrees(simulated[:, :5] - mapped["measured"][:, :5])
    actual_points = _fk_points(candidate, mapped["measured"])
    simulated_points = _fk_points(candidate, simulated)
    ee_error = np.linalg.norm(simulated_points - actual_points, axis=1)
    stall_rows, stall_reproduced = _stall_counts(mapped, simulated, contract)
    return {
        "sample_count": len(simulated),
        "joint_squared_error_degrees": np.sum(error_degrees**2, axis=0).tolist(),
        "per_joint_rms_degrees": dict(
            zip(BODY_JOINT_NAMES, np.sqrt(np.mean(error_degrees**2, axis=0)).tolist(), strict=True)
        ),
        "overall_joint_rms_degrees": float(np.sqrt(np.mean(error_degrees**2))),
        "ee_squared_error_m2": float(np.sum(ee_error**2)),
        "ee_rms_m": float(np.sqrt(np.mean(ee_error**2))),
        "ee_max_m": float(np.max(ee_error)),
        "stall_rows": dict(zip(BODY_JOINT_NAMES, stall_rows.astype(int).tolist(), strict=True)),
        "stall_reproduced": dict(
            zip(BODY_JOINT_NAMES, stall_reproduced.astype(int).tolist(), strict=True)
        ),
        "actual_points": actual_points,
        "simulated_points": simulated_points,
        "simulated_states": simulated,
    }


def _pool(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    materialized = list(rows)
    samples = sum(int(row["sample_count"]) for row in materialized)
    joint_sse = np.sum(
        np.asarray([row["joint_squared_error_degrees"] for row in materialized]), axis=0
    )
    ee_sse = sum(float(row["ee_squared_error_m2"]) for row in materialized)
    stall_rows = np.sum(
        np.asarray(
            [[row["stall_rows"][name] for name in BODY_JOINT_NAMES] for row in materialized]
        ),
        axis=0,
    )
    reproduced = np.sum(
        np.asarray(
            [
                [row["stall_reproduced"][name] for name in BODY_JOINT_NAMES]
                for row in materialized
            ]
        ),
        axis=0,
    )
    per_joint = np.sqrt(joint_sse / samples)
    with np.errstate(divide="ignore", invalid="ignore"):
        rates = reproduced / stall_rows
    return {
        "episode_count": len(materialized),
        "sample_count": samples,
        "per_joint_rms_degrees": dict(zip(BODY_JOINT_NAMES, per_joint.tolist(), strict=True)),
        "overall_joint_rms_degrees": float(np.sqrt(np.mean(per_joint**2))),
        "ee_rms_m": float(np.sqrt(ee_sse / samples)),
        "stall_rows": dict(zip(BODY_JOINT_NAMES, stall_rows.astype(int).tolist(), strict=True)),
        "stall_reproduction_fraction": dict(zip(BODY_JOINT_NAMES, rates.tolist(), strict=True)),
    }


def _strip_arrays(metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in metrics.items()
        if key not in {"actual_points", "simulated_points", "simulated_states"}
    }


def _write_episode_trace(
    *,
    mapped: dict[str, Any],
    variants: dict[str, dict[str, Any]],
    output_path: Path,
) -> str:
    rows = []
    for index in range(len(mapped["actions"])):
        row: dict[str, Any] = {
            "sample_index": index,
            "elapsed_seconds": float(mapped["timestamps"][index]),
            "applied_action": mapped["actions"][index].tolist(),
            "mapped_measured_joint_state": mapped["measured"][index].tolist(),
        }
        for name, metrics in variants.items():
            row[name] = {
                "simulated_joint_state": metrics["simulated_states"][index].tolist(),
                "mapped_measured_ee_xyz_m": metrics["actual_points"][index].tolist(),
                "simulated_ee_xyz_m": metrics["simulated_points"][index].tolist(),
                "ee_error_m": float(
                    np.linalg.norm(
                        metrics["simulated_points"][index] - metrics["actual_points"][index]
                    )
                ),
            }
        rows.append(row)
    artifact = {
        "schema_version": TRACE_SCHEMA,
        "recording_id": mapped["episode"]["recording_id"],
        "action_invariance": mapped["action_receipt"],
        "rows": rows,
    }
    atomic_write_json(output_path, artifact)
    return sha256_file(output_path)


def _timing_consequence_episode(
    *,
    mapped: dict[str, Any],
    candidate: WorkcellCandidate,
    reward_contract: dict[str, Any],
    mode: str,
    delay_seconds: float,
    settle_steps: int,
    servo_deadband_degrees: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Replay one source action array with a declared application schedule."""

    binding = build_workcell_model(candidate)
    model, data = binding["model"], binding["data"]
    actuator_ids = binding["actuator_ids"]
    qpos_addresses = binding["qpos_addresses"]
    source = str(mapped["source"])
    destination = str(mapped["destination"])
    selected_name = BASELINE_PIECE_BY_FILE[source[0]]
    selected_body = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_BODY, selected_name
    )
    selected_joint = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_JOINT, f"{selected_name}_free"
    )
    if selected_body < 0 or selected_joint < 0:
        raise TimingAblationError("selected pawn is missing from timing consequence replay")
    selected_qpos = int(model.jnt_qposadr[selected_joint])
    selected_dof = int(model.jnt_dofadr[selected_joint])
    source_xyz = np.asarray(
        _workcell_square_center(
            source,
            board_center_in_table_frame_xy_m=candidate.board_center_in_table_frame_xy_m,
            board_yaw_relative_to_table_degrees=candidate.board_yaw_relative_to_table_degrees,
            board_side_m=candidate.board_side_m,
        ),
        dtype=np.float64,
    )
    data.qpos[selected_qpos : selected_qpos + 3] = source_xyz
    data.qvel[selected_dof : selected_dof + 6] = 0.0
    data.qpos[qpos_addresses] = mapped["measured"][0]
    data.ctrl[actuator_ids] = mapped["measured"][0]
    mujoco.mj_forward(model, data)
    if settle_steps:
        mujoco.mj_step(model, data, nstep=settle_steps)
    piece_bodies = _piece_bodies(model)
    initial_positions = {
        name: np.asarray(data.xpos[body_id], dtype=np.float64).copy()
        for name, body_id in piece_bodies.items()
    }
    initial_height = float(data.xpos[selected_body][2])
    robot_body_ids = {
        body_id
        for body_id in range(model.nbody)
        if (mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id) or "").startswith(
            "left_"
        )
    }
    fixed_geom = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_GEOM, "left_fixed_jaw_box1"
    )
    jaw_body_ids = {
        int(model.geom_bodyid[fixed_geom]),
        mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_BODY, "left_moving_jaw_so101_v1"
        ),
    }

    def trace_row() -> dict[str, Any]:
        return _trace_row(
            model,
            data,
            selected_body=selected_body,
            selected_dof=selected_dof,
            piece_bodies=piece_bodies,
            initial_piece_positions=initial_positions,
            robot_body_ids=robot_body_ids,
            jaw_body_ids=jaw_body_ids,
        )

    pinch_local = binding["pinch_offset_local"]
    deadband = servo_deadband_degrees or {}
    nominal_gain = model.actuator_gainprm[:, 0].copy()
    nominal_bias = model.actuator_biasprm[:, 1].copy()

    def apply_servo_model(action: np.ndarray) -> None:
        data.ctrl[actuator_ids] = action
        for joint_name, threshold_degrees in deadband.items():
            try:
                joint_index = BODY_JOINT_NAMES.index(joint_name)
            except ValueError as error:
                raise TimingAblationError(
                    f"unsupported servo deadband joint: {joint_name}"
                ) from error
            actuator_id = actuator_ids[joint_index]
            qpos_address = qpos_addresses[joint_index]
            inactive = abs(float(action[joint_index] - data.qpos[qpos_address])) <= math.radians(
                float(threshold_degrees)
            )
            scale = 0.0 if inactive else 1.0
            model.actuator_gainprm[actuator_id, 0] = nominal_gain[actuator_id] * scale
            model.actuator_biasprm[actuator_id, 1] = nominal_bias[actuator_id] * scale

    def pinch_distance() -> float:
        point = _pinch_point(model, data, "left", pinch_local)
        return float(np.linalg.norm(point - np.asarray(data.xpos[selected_body])))

    trace = [trace_row()]
    minimum_pinch = pinch_distance()
    actions = mapped["actions"]
    times = mapped["timestamps"]
    timestep = float(model.opt.timestep)
    if mode == "legacy_step_then_record":
        previous: float | None = None
        nominal_dt = 1.0 / int(mapped["episode"]["sample_hz"])
        for timestamp, action in zip(times, actions, strict=True):
            dt = nominal_dt if previous is None else float(timestamp - previous)
            previous = float(timestamp)
            apply_servo_model(action)
            step_count = max(1, round(dt / timestep))
            for _ in range(step_count):
                mujoco.mj_step(model, data)
                minimum_pinch = min(minimum_pinch, pinch_distance())
            trace.append(trace_row())
    elif mode == "timestamp_aligned_zoh":
        for row_index, timestamp in enumerate(times[:-1]):
            interval = float(times[row_index + 1] - timestamp)
            step_count = max(1, round(interval / timestep))
            for step in range(step_count):
                now = float(timestamp) + step * timestep
                source_index = max(
                    0,
                    int(np.searchsorted(times, now - delay_seconds, side="right") - 1),
                )
                apply_servo_model(actions[source_index])
                mujoco.mj_step(model, data)
                minimum_pinch = min(minimum_pinch, pinch_distance())
            trace.append(trace_row())
        final_index = max(
            0,
            int(
                np.searchsorted(times, float(times[-1]) - delay_seconds, side="right")
                - 1
            ),
        )
        apply_servo_model(actions[final_index])
    else:
        raise TimingAblationError(f"unsupported consequence timing mode: {mode}")
    for _ in range(200):
        apply_servo_model(np.asarray(data.ctrl[actuator_ids], dtype=np.float64))
        mujoco.mj_step(model, data)
        minimum_pinch = min(minimum_pinch, pinch_distance())
    trace.append(trace_row())
    target_xyz = _workcell_square_center(
        destination,
        board_center_in_table_frame_xy_m=candidate.board_center_in_table_frame_xy_m,
        board_yaw_relative_to_table_degrees=candidate.board_yaw_relative_to_table_degrees,
        board_side_m=candidate.board_side_m,
    )
    score = score_episode(
        reward_contract,
        skill_id=f"pawn_{source}_to_{destination}",
        trace=trace,
        target_position_xyz_m=target_xyz,
        initial_piece_height_m=initial_height,
        evaluation_mode="source_demonstration_replay",
        action_owner="physical_teleoperator",
        assistance_used=False,
    )
    return {
        "recording_id": mapped["episode"]["recording_id"],
        "folder_label": mapped["episode"]["folder_label"],
        "mode": mode,
        "delay_seconds": float(delay_seconds),
        "servo_deadband_degrees": deadband,
        "action_sha256": mapped["action_receipt"]["sha256"],
        "clipped_action_rows": 0,
        "minimum_pinch_to_selected_piece_m": minimum_pinch,
        "selected_piece_contact_observed": bool(
            score["gate_results"]["selected_piece_contact_observed"]
        ),
        "piece_lifted": bool(score["gate_results"]["piece_lifted"]),
        "maximum_piece_rise_m": float(score["maximum_piece_rise_m"]),
        "final_target_distance_m": float(score["final_center_distance_m"]),
        "task_consequence_success": bool(score["task_consequence_success"]),
    }


def _consequence_summary(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    materialized = list(rows)
    return {
        "episode_count": len(materialized),
        "selected_piece_contact": sum(
            int(row["selected_piece_contact_observed"]) for row in materialized
        ),
        "lifted": sum(int(row["piece_lifted"]) for row in materialized),
        "task_consequence_successes": sum(
            int(row["task_consequence_success"]) for row in materialized
        ),
        "mean_minimum_pinch_to_selected_piece_m": float(
            np.mean([row["minimum_pinch_to_selected_piece_m"] for row in materialized])
        ),
        "mean_maximum_piece_rise_m": float(
            np.mean([row["maximum_piece_rise_m"] for row in materialized])
        ),
        "mean_final_target_distance_m": float(
            np.mean([row["final_target_distance_m"] for row in materialized])
        ),
    }


def _evaluate_partition(
    payloads: list[tuple[dict[str, Any], str, str, list[dict[str, Any]]]],
    candidate: WorkcellCandidate,
    contract: dict[str, Any],
    delays: list[float],
    *,
    include_legacy: bool,
) -> tuple[dict[str, dict[str, dict[str, Any]]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    mapped_by_id: dict[str, dict[str, Any]] = {}
    results: dict[str, dict[str, dict[str, Any]]] = {}
    schedules: dict[str, dict[str, Any]] = {}
    settle_steps = int(contract["variants"]["timestamp_aligned_zoh"]["initial_settle_steps"])
    for payload in payloads:
        mapped = _mapped_episode(payload, candidate)
        recording_id = str(mapped["episode"]["recording_id"])
        mapped_by_id[recording_id] = mapped
        results[recording_id] = {}
        schedules[recording_id] = {}
        if include_legacy:
            states, schedule = _legacy_step_then_record(mapped, candidate, settle_steps)
            results[recording_id]["legacy_step_then_record"] = _episode_metrics(
                mapped, states, candidate, contract
            )
            schedules[recording_id]["legacy_step_then_record"] = schedule
        for delay in delays:
            key = f"aligned_delay_{int(round(delay * 1000)):03d}ms"
            states, schedule = _timestamp_aligned_zoh(
                mapped,
                candidate,
                settle_steps=settle_steps,
                delay_seconds=delay,
            )
            results[recording_id][key] = _episode_metrics(mapped, states, candidate, contract)
            schedules[recording_id][key] = schedule
    return results, mapped_by_id, schedules


def run_timing_ablation(
    *, source_repository_root: Path, output_root: Path, contract_path: Path = CONTRACT_PATH
) -> dict[str, Any]:
    contract = load_timing_contract(contract_path)
    train_payloads, events = _load_partition(source_repository_root, "train")
    confirmation_payloads, _confirmation_events = _load_partition(
        source_repository_root, "held_out"
    )
    expected_train = int(contract["source"]["expected_train_episode_count"])
    expected_confirmation = int(
        contract["source"]["expected_already_opened_confirmation_episode_count"]
    )
    if len(train_payloads) != expected_train or len(confirmation_payloads) != expected_confirmation:
        raise TimingAblationError("product episode inventory changed")
    _parent, candidate, parameters, _details = _reconstruct_stage_d(train_payloads, events)
    board_side = float(contract["source"]["candidate_board_playing_side_m"])
    if candidate.board_side_m is not None:
        raise TimingAblationError("Stage-D candidate unexpectedly overrides board side")
    delays = [
        float(value)
        for value in contract["variants"]["timestamp_aligned_zoh"][
            "application_delay_grid_seconds"
        ]
    ]
    train_results, mapped_train, train_schedules = _evaluate_partition(
        train_payloads, candidate, contract, delays, include_legacy=True
    )
    train_ids = sorted(train_results)

    def pooled(ids: Iterable[str], key: str) -> dict[str, Any]:
        return _pool(train_results[recording_id][key] for recording_id in ids)

    delay_rows = []
    for delay in delays:
        key = f"aligned_delay_{int(round(delay * 1000)):03d}ms"
        delay_rows.append({"delay_seconds": delay, "variant": key, **pooled(train_ids, key)})
    selected_row = min(delay_rows, key=lambda row: row["overall_joint_rms_degrees"])
    selected_delay = float(selected_row["delay_seconds"])
    selected_key = str(selected_row["variant"])
    folds = [list(map(str, fold)) for fold in contract["grouped_cross_validation"]["folds"]]
    if set(recording_id for fold in folds for recording_id in fold) != set(train_ids):
        raise TimingAblationError("grouped CV fold identities differ from train episodes")
    cv_rows = []
    for fold_index, validation_ids in enumerate(folds):
        fit_ids = [recording_id for recording_id in train_ids if recording_id not in validation_ids]
        fold_candidates = []
        for delay in delays:
            key = f"aligned_delay_{int(round(delay * 1000)):03d}ms"
            fold_candidates.append((delay, key, pooled(fit_ids, key)))
        fold_delay, fold_key, fold_fit = min(
            fold_candidates, key=lambda item: item[2]["overall_joint_rms_degrees"]
        )
        validation_baseline = pooled(validation_ids, "aligned_delay_000ms")
        validation_candidate = pooled(validation_ids, fold_key)
        cv_rows.append(
            {
                "fold_index": fold_index,
                "fit_episode_ids": fit_ids,
                "validation_episode_ids": validation_ids,
                "selected_delay_seconds": fold_delay,
                "fit_metrics": fold_fit,
                "validation_baseline": validation_baseline,
                "validation_candidate": validation_candidate,
                "validation_relative_improvement": float(
                    (
                        validation_baseline["overall_joint_rms_degrees"]
                        - validation_candidate["overall_joint_rms_degrees"]
                    )
                    / validation_baseline["overall_joint_rms_degrees"]
                ),
            }
        )
    cv_baseline = _pool(
        train_results[recording_id]["aligned_delay_000ms"]
        for row in cv_rows
        for recording_id in row["validation_episode_ids"]
    )
    cv_selected_rows = []
    for row in cv_rows:
        key = f"aligned_delay_{int(round(float(row['selected_delay_seconds']) * 1000)):03d}ms"
        cv_selected_rows.extend(
            train_results[recording_id][key]
            for recording_id in row["validation_episode_ids"]
        )
    cv_candidate = _pool(cv_selected_rows)
    cv_improvement = float(
        (cv_baseline["overall_joint_rms_degrees"] - cv_candidate["overall_joint_rms_degrees"])
        / cv_baseline["overall_joint_rms_degrees"]
    )
    legacy = pooled(train_ids, "legacy_step_then_record")
    aligned_zero = pooled(train_ids, "aligned_delay_000ms")
    selected = pooled(train_ids, selected_key)
    action_invariant = all(
        mapped["action_receipt"]["sha256"]
        == _array_sha256(mapped["actions"])
        for mapped in mapped_train.values()
    )
    per_joint_no_regression = all(
        selected["per_joint_rms_degrees"][name]
        <= legacy["per_joint_rms_degrees"][name]
        for name in BODY_JOINT_NAMES
    )
    acceptance = contract["acceptance"]
    ee_improvement = float((legacy["ee_rms_m"] - selected["ee_rms_m"]) / legacy["ee_rms_m"])
    gates = {
        "action_invariance_gate": action_invariant,
        "cross_validated_joint_rms_gate": cv_improvement
        >= float(acceptance["minimum_cross_validated_joint_rms_relative_improvement"]),
        "train_ee_rms_gate": ee_improvement
        >= float(acceptance["minimum_all_train_ee_rms_relative_improvement_from_legacy"]),
        "per_joint_no_regression_gate": per_joint_no_regression,
    }
    timing_diagnostic_accepted = all(gates.values())

    reward_contract = load_reward_contract()
    consequence_rows: dict[str, list[dict[str, Any]]] = {
        "legacy_step_then_record": [],
        "timestamp_aligned_zero_delay": [],
        "timestamp_aligned_selected_delay": [],
    }
    settle_steps = int(
        contract["variants"]["timestamp_aligned_zoh"]["initial_settle_steps"]
    )
    for recording_id in train_ids:
        mapped = mapped_train[recording_id]
        consequence_rows["legacy_step_then_record"].append(
            _timing_consequence_episode(
                mapped=mapped,
                candidate=candidate,
                reward_contract=reward_contract,
                mode="legacy_step_then_record",
                delay_seconds=0.0,
                settle_steps=settle_steps,
            )
        )
        consequence_rows["timestamp_aligned_zero_delay"].append(
            _timing_consequence_episode(
                mapped=mapped,
                candidate=candidate,
                reward_contract=reward_contract,
                mode="timestamp_aligned_zoh",
                delay_seconds=0.0,
                settle_steps=settle_steps,
            )
        )
        consequence_rows["timestamp_aligned_selected_delay"].append(
            _timing_consequence_episode(
                mapped=mapped,
                candidate=candidate,
                reward_contract=reward_contract,
                mode="timestamp_aligned_zoh",
                delay_seconds=selected_delay,
                settle_steps=settle_steps,
            )
        )
    consequence_replay = {
        name: {
            "summary": _consequence_summary(rows),
            "episodes": rows,
        }
        for name, rows in consequence_rows.items()
    }

    confirmation_results, mapped_confirmation, confirmation_schedules = _evaluate_partition(
        confirmation_payloads,
        candidate,
        contract,
        [0.0, selected_delay],
        include_legacy=True,
    )
    confirmation_ids = sorted(confirmation_results)
    confirmation = {
        "legacy_step_then_record": _pool(
            confirmation_results[recording_id]["legacy_step_then_record"]
            for recording_id in confirmation_ids
        ),
        "aligned_delay_000ms": _pool(
            confirmation_results[recording_id]["aligned_delay_000ms"]
            for recording_id in confirmation_ids
        ),
        selected_key: _pool(
            confirmation_results[recording_id][selected_key]
            for recording_id in confirmation_ids
        ),
        "selection_use": "none_already_opened_regression_only",
    }

    trace_rows = []
    for recording_id in train_ids:
        path = output_root.resolve() / "traces" / f"{recording_id}.json"
        variants = {
            "legacy_step_then_record": train_results[recording_id][
                "legacy_step_then_record"
            ],
            "aligned_zero_delay": train_results[recording_id]["aligned_delay_000ms"],
            "aligned_selected_delay": train_results[recording_id][selected_key],
        }
        digest = _write_episode_trace(
            mapped=mapped_train[recording_id], variants=variants, output_path=path
        )
        trace_rows.append(
            {
                "recording_id": recording_id,
                "action": mapped_train[recording_id]["action_receipt"],
                "trace_path": str(path),
                "trace_sha256": digest,
                "schedules": {
                    "legacy_step_then_record": train_schedules[recording_id][
                        "legacy_step_then_record"
                    ],
                    "aligned_zero_delay": train_schedules[recording_id][
                        "aligned_delay_000ms"
                    ],
                    "aligned_selected_delay": train_schedules[recording_id][selected_key],
                },
                "metrics": {
                    name: _strip_arrays(metrics) for name, metrics in variants.items()
                },
            }
        )
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "proof_class": "action_frozen_simulator_timing_diagnostic",
        "contract": {
            "path": str(contract_path.resolve()),
            "sha256": sha256_file(contract_path),
        },
        "implementation": {
            "path": str(Path(__file__).resolve()),
            "sha256": sha256_file(Path(__file__).resolve()),
        },
        "stage_d_parameters": parameters,
        "board_playing_side_m": board_side,
        "board_scale_status": contract["source"]["board_scale_status"],
        "train_episode_count": len(train_ids),
        "action_arrays_byte_identical_across_variants": action_invariant,
        "legacy_step_then_record": legacy,
        "timestamp_aligned_zero_delay": aligned_zero,
        "delay_grid": delay_rows,
        "selected_delay_seconds": selected_delay,
        "selected_variant": selected_key,
        "selected_train_metrics": selected,
        "legacy_to_selected_ee_rms_relative_improvement": ee_improvement,
        "grouped_cross_validation": {
            "folds": cv_rows,
            "pooled_baseline": cv_baseline,
            "pooled_candidate": cv_candidate,
            "pooled_relative_improvement": cv_improvement,
        },
        "train_acceptance": {
            "gates": gates,
            "accepted_as_timing_diagnostic": timing_diagnostic_accepted,
            "accepted_as_composite_simulator_candidate": False,
        },
        "action_frozen_consequence_replay": consequence_replay,
        "already_opened_confirmation": confirmation,
        "traces": trace_rows,
        "confirmation_action_hashes": {
            recording_id: mapped["action_receipt"]
            for recording_id, mapped in mapped_confirmation.items()
        },
        "confirmation_schedules": confirmation_schedules,
        "authority": contract["authority"],
        "claim_boundary": (
            "The selected result corrects trace timestamp/application semantics and "
            "selects a bounded simulator-side delay under byte-identical action arrays. "
            "It is not an action correction, physical latency calibration, contact fit, "
            "task result, policy improvement, or simulator composite promotion."
        ),
    }
    receipt["receipt_digest"] = canonical_digest(receipt)
    atomic_write_json(output_root.resolve() / "timing_ablation_receipt.json", receipt)
    return receipt
