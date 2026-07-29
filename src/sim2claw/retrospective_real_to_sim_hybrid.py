"""Prospectively frozen REAL-to-SIM hybrid replay for the Phase-A D1->D2 source.

The historical physical source cannot support pure action-only replay: the
gateway transformed many requested rows and did not record actuator
application timestamps.  This narrower proof keeps those limitations visible.
It replays the actual gateway-sent command trace and, separately, the measured
joint-state upper bound while supplying the visually reviewed discrete
grasp/hold/release mode as an explicit input.  The selected pawn pose is never
forced to the destination; after release it is governed by free MuJoCo
physics.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation

from .grasp import _pinch_point
from .learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .paths import REPO_ROOT
from .pawn_bg_action_frozen_gap import _array_sha256, _load_partition, _reconstruct_stage_d
from .pawn_bg_demo_sim import (
    BASELINE_PIECE_BY_FILE,
    _piece_bodies,
    physical_values_to_sim_with_adapter,
)
from .pawn_bg_workcell_fit import _workcell_square_center, build_workcell_model
from .state_trace import EpisodeStateTraceRecorder


CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "retrospective_real_to_sim_hybrid_v1.json"
)
OUTPUT_DIRECTORY = REPO_ROOT / "outputs" / "retrospective_real_to_sim_hybrid_v1"
SCHEMA = "sim2claw.retrospective_real_to_sim_hybrid.v1"
RECEIPT_SCHEMA = "sim2claw.retrospective_real_to_sim_hybrid_receipt.v1"


class RetrospectiveHybridReplayError(RuntimeError):
    """The frozen hybrid replay cannot run without changing its contract."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RetrospectiveHybridReplayError(f"cannot read {path}: {error}") from error
    if not isinstance(value, dict):
        raise RetrospectiveHybridReplayError(f"{path} must contain an object")
    return value


def _require_hash(path: Path, expected: str) -> None:
    if not path.is_file() or sha256_file(path) != expected:
        raise RetrospectiveHybridReplayError(f"evidence hash rejected: {path}")


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    contract = _read_json(path)
    if contract.get("schema_version") != SCHEMA:
        raise RetrospectiveHybridReplayError("unexpected hybrid replay schema")
    source = contract.get("source")
    replay = contract.get("replay")
    evaluator = contract.get("evaluator")
    authority = contract.get("authority")
    if not all(isinstance(value, dict) for value in (source, replay, evaluator, authority)):
        raise RetrospectiveHybridReplayError("hybrid replay contract is incomplete")
    if authority != {
        "camera": False,
        "hardware": False,
        "physical_motion": False,
        "physical_task_attempt": False,
        "sim_to_real": False,
        "pure_action_only_transfer": False,
        "simulator_replay": True,
    }:
        raise RetrospectiveHybridReplayError("hybrid replay authority widened")
    if replay.get("drivers") != [
        "mapped_gateway_command_zoh",
        "observed_joint_state_upper_bound",
    ]:
        raise RetrospectiveHybridReplayError("hybrid replay drivers changed")
    required_true = (
        "preserve_source_row_order",
        "preserve_source_host_timestamps",
    )
    if any(replay.get(key) is not True for key in required_true):
        raise RetrospectiveHybridReplayError("source identity is not fail closed")
    forbidden = (
        "action_clipping_allowed",
        "action_smoothing_allowed",
        "action_offset_or_ik_repair_allowed",
        "terminal_object_pose_forcing_allowed",
    )
    if any(replay.get(key) is not False for key in forbidden):
        raise RetrospectiveHybridReplayError("forbidden replay repair was enabled")
    grasp_index = int(source["grasp_marker_sample_index"])
    release_index = int(source["release_marker_sample_index"])
    if not 0 <= grasp_index < release_index:
        raise RetrospectiveHybridReplayError("grasp/release markers are invalid")
    if not 0.0 < float(replay["maximum_attach_distance_m"]) <= 0.06:
        raise RetrospectiveHybridReplayError("attach-distance bound widened")
    if not 0.0 < float(replay["post_release_settle_seconds"]) <= 2.0:
        raise RetrospectiveHybridReplayError("settle duration widened")
    source_directory = (REPO_ROOT / source["directory"]).resolve()
    _require_hash(
        source_directory / "recording_receipt.json",
        str(source["recording_receipt_sha256"]),
    )
    _require_hash(source_directory / "samples.jsonl", str(source["samples_sha256"]))
    _require_hash(
        source_directory / "phase_a_comparison_receipt.json",
        str(source["phase_a_receipt_sha256"]),
    )
    for binding in contract["mapping"].values():
        if not isinstance(binding, dict):
            continue
        _require_hash(REPO_ROOT / binding["path"], str(binding["sha256"]))
    return contract


def _little_endian_hash(values: np.ndarray, dtype: str) -> str:
    array = np.ascontiguousarray(values, dtype=np.dtype(dtype))
    return hashlib.sha256(array.tobytes(order="C")).hexdigest()


def _rotation(data: mujoco.MjData, body_id: int) -> np.ndarray:
    return np.asarray(data.xmat[body_id], dtype=np.float64).reshape(3, 3).copy()


def _wxyz(rotation: np.ndarray) -> np.ndarray:
    xyzw = Rotation.from_matrix(rotation).as_quat()
    return np.asarray([xyzw[3], xyzw[0], xyzw[1], xyzw[2]], dtype=np.float64)


@dataclass
class _Latch:
    selected_qpos: int
    selected_dof: int
    jaw_body: int
    pinch_local: np.ndarray
    active: bool = False
    engaged: bool = False
    released: bool = False
    relative_position: np.ndarray | None = None
    relative_rotation: np.ndarray | None = None
    previous_position: np.ndarray | None = None
    previous_rotation: np.ndarray | None = None
    attach_distance_m: float | None = None
    maximum_hold_pose_step_m: float = 0.0

    def _frame(
        self, model: mujoco.MjModel, data: mujoco.MjData
    ) -> tuple[np.ndarray, np.ndarray]:
        return (
            _pinch_point(model, data, "left", self.pinch_local),
            _rotation(data, self.jaw_body),
        )

    def engage(
        self,
        model: mujoco.MjModel,
        data: mujoco.MjData,
        *,
        selected_body: int,
        maximum_distance_m: float,
    ) -> None:
        if self.engaged:
            raise RetrospectiveHybridReplayError("hybrid latch engaged more than once")
        origin, jaw_rotation = self._frame(model, data)
        object_position = np.asarray(data.xpos[selected_body], dtype=np.float64).copy()
        object_rotation = _rotation(data, selected_body)
        distance = float(np.linalg.norm(object_position - origin))
        if distance > maximum_distance_m:
            raise RetrospectiveHybridReplayError(
                f"grasp marker is {distance:.6f} m from the selected pawn"
            )
        self.relative_position = jaw_rotation.T @ (object_position - origin)
        self.relative_rotation = jaw_rotation.T @ object_rotation
        self.previous_position = object_position
        self.previous_rotation = object_rotation
        self.attach_distance_m = distance
        self.active = True
        self.engaged = True

    def enforce(
        self, model: mujoco.MjModel, data: mujoco.MjData, *, dt: float
    ) -> None:
        if not self.active:
            return
        assert self.relative_position is not None
        assert self.relative_rotation is not None
        assert self.previous_position is not None
        assert self.previous_rotation is not None
        origin, jaw_rotation = self._frame(model, data)
        position = origin + jaw_rotation @ self.relative_position
        rotation = jaw_rotation @ self.relative_rotation
        step = float(np.linalg.norm(position - self.previous_position))
        self.maximum_hold_pose_step_m = max(self.maximum_hold_pose_step_m, step)
        linear_velocity = (position - self.previous_position) / dt
        angular_velocity = (
            Rotation.from_matrix(rotation @ self.previous_rotation.T).as_rotvec() / dt
        )
        data.qpos[self.selected_qpos : self.selected_qpos + 3] = position
        data.qpos[self.selected_qpos + 3 : self.selected_qpos + 7] = _wxyz(rotation)
        data.qvel[self.selected_dof : self.selected_dof + 3] = linear_velocity
        data.qvel[self.selected_dof + 3 : self.selected_dof + 6] = angular_velocity
        mujoco.mj_forward(model, data)
        self.previous_position = position
        self.previous_rotation = rotation

    def release(self) -> None:
        if not self.active or not self.engaged or self.released:
            raise RetrospectiveHybridReplayError("hybrid latch release is invalid")
        self.active = False
        self.released = True


def evaluate_outcome(
    *,
    final_position: np.ndarray,
    final_rotation: np.ndarray,
    final_velocity: np.ndarray,
    initial_height_m: float,
    target_position: np.ndarray,
    maximum_other_piece_displacement_m: float,
    evaluator: dict[str, Any],
) -> dict[str, Any]:
    planar_error = float(np.linalg.norm(final_position[:2] - target_position[:2]))
    tilt = math.degrees(
        math.acos(float(np.clip(final_rotation[2, 2], -1.0, 1.0)))
    )
    linear_speed = float(np.linalg.norm(final_velocity[:3]))
    angular_speed = float(np.linalg.norm(final_velocity[3:]))
    height_error = abs(float(final_position[2] - initial_height_m))
    gates = {
        "whole_base_inside_destination": planar_error
        <= float(evaluator["maximum_final_planar_center_error_for_whole_base_inside_m"]),
        "composable_center": planar_error
        <= float(evaluator["maximum_final_planar_center_error_composable_m"]),
        "upright": tilt <= float(evaluator["maximum_upright_tilt_degrees"]),
        "other_pieces_stationary": maximum_other_piece_displacement_m
        <= float(evaluator["maximum_other_piece_displacement_m"]),
        "settled_linear": linear_speed
        <= float(evaluator["maximum_final_linear_speed_m_s"]),
        "settled_angular": angular_speed
        <= float(evaluator["maximum_final_angular_speed_rad_s"]),
        "settled_height": height_error
        <= float(evaluator["maximum_final_height_error_m"]),
    }
    return {
        "final_position_m": final_position.astype(float).tolist(),
        "target_position_m": target_position.astype(float).tolist(),
        "final_planar_center_error_m": planar_error,
        "final_upright_tilt_degrees": tilt,
        "final_linear_speed_m_s": linear_speed,
        "final_angular_speed_rad_s": angular_speed,
        "final_height_error_m": height_error,
        "maximum_other_piece_displacement_m": maximum_other_piece_displacement_m,
        "gates": gates,
        "coarse_square_task_success": all(
            gates[key]
            for key in (
                "whole_base_inside_destination",
                "upright",
                "other_pieces_stationary",
                "settled_linear",
                "settled_angular",
                "settled_height",
            )
        ),
        "composable_task_success": all(gates.values()),
    }


def _replay_driver(
    *,
    driver: str,
    contract: dict[str, Any],
    candidate: Any,
    rows: list[dict[str, Any]],
    actions: np.ndarray,
    measured: np.ndarray,
    timestamps: np.ndarray,
    output_directory: Path,
) -> dict[str, Any]:
    source = contract["source"]
    replay = contract["replay"]
    binding = build_workcell_model(candidate)
    model: mujoco.MjModel = binding["model"]
    data: mujoco.MjData = binding["data"]
    actuator_ids = np.asarray(binding["actuator_ids"], dtype=np.int32)
    qpos_addresses = np.asarray(binding["qpos_addresses"], dtype=np.int32)
    dof_addresses = np.asarray(
        [
            int(model.jnt_dofadr[mujoco.mj_name2id(
                model, mujoco.mjtObj.mjOBJ_JOINT, f"left_{joint}"
            )])
            for joint in (
                "shoulder_pan",
                "shoulder_lift",
                "elbow_flex",
                "wrist_flex",
                "wrist_roll",
                "gripper",
            )
        ],
        dtype=np.int32,
    )
    selected_name = str(source["selected_piece"])
    expected_name = BASELINE_PIECE_BY_FILE[str(source["source_square"])[0]]
    if selected_name != expected_name:
        raise RetrospectiveHybridReplayError("selected pawn does not match file identity")
    selected_body = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_BODY, selected_name
    )
    selected_joint = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_JOINT, f"{selected_name}_free"
    )
    if selected_body < 0 or selected_joint < 0:
        raise RetrospectiveHybridReplayError("selected pawn is missing")
    selected_qpos = int(model.jnt_qposadr[selected_joint])
    selected_dof = int(model.jnt_dofadr[selected_joint])
    source_position = np.asarray(
        _workcell_square_center(
            str(source["source_square"]),
            board_center_in_table_frame_xy_m=candidate.board_center_in_table_frame_xy_m,
            board_yaw_relative_to_table_degrees=candidate.board_yaw_relative_to_table_degrees,
            board_side_m=candidate.board_side_m,
        ),
        dtype=np.float64,
    )
    target_position = np.asarray(
        _workcell_square_center(
            str(source["destination_square"]),
            board_center_in_table_frame_xy_m=candidate.board_center_in_table_frame_xy_m,
            board_yaw_relative_to_table_degrees=candidate.board_yaw_relative_to_table_degrees,
            board_side_m=candidate.board_side_m,
        ),
        dtype=np.float64,
    )
    data.qpos[selected_qpos : selected_qpos + 3] = source_position
    data.qpos[selected_qpos + 3 : selected_qpos + 7] = [1.0, 0.0, 0.0, 0.0]
    data.qvel[selected_dof : selected_dof + 6] = 0.0
    data.qpos[qpos_addresses] = measured[0]
    data.ctrl[actuator_ids] = actions[0]
    mujoco.mj_forward(model, data)
    mujoco.mj_step(model, data, nstep=100)
    initial_height = float(data.xpos[selected_body][2])
    piece_bodies = _piece_bodies(model)
    initial_piece_positions = {
        name: np.asarray(data.xpos[body_id], dtype=np.float64).copy()
        for name, body_id in piece_bodies.items()
    }
    fixed_tip_geom = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_GEOM, "left_fixed_jaw_sph_tip2"
    )
    jaw_body = int(model.geom_bodyid[fixed_tip_geom])
    latch = _Latch(
        selected_qpos=selected_qpos,
        selected_dof=selected_dof,
        jaw_body=jaw_body,
        pinch_local=np.asarray(binding["pinch_offset_local"], dtype=np.float64),
    )
    state_trace = EpisodeStateTraceRecorder(
        model,
        piece_layout="sparse_two_sided_pawns",
        fps=20,
        proof_class=f"real_to_sim_hybrid_{driver}",
    )
    trace_rows: list[dict[str, Any]] = []
    maximum_quantization_error = 0.0
    maximum_tracking_error = np.zeros(6, dtype=np.float64)
    squared_tracking_error = np.zeros(6, dtype=np.float64)
    tracking_samples = 0
    previous_state = measured[0].copy()
    grasp_index = int(source["grasp_marker_sample_index"])
    release_index = int(source["release_marker_sample_index"])
    timestep = float(model.opt.timestep)
    nominal_dt = 1.0 / 20.0

    for index, (action, observed) in enumerate(
        zip(actions, measured, strict=True)
    ):
        dt = nominal_dt if index == 0 else float(timestamps[index] - timestamps[index - 1])
        if not math.isfinite(dt) or dt <= 0.0:
            raise RetrospectiveHybridReplayError("source timestamps are not monotonic")
        nstep = max(1, round(dt / timestep))
        maximum_quantization_error = max(
            maximum_quantization_error, abs(nstep * timestep - dt)
        )
        if driver == "mapped_gateway_command_zoh":
            data.ctrl[actuator_ids] = action
            for _ in range(nstep):
                mujoco.mj_step(model, data)
                latch.enforce(model, data, dt=timestep)
        elif driver == "observed_joint_state_upper_bound":
            velocity = (observed - previous_state) / dt
            for step in range(nstep):
                alpha = (step + 1) / nstep
                pose = previous_state + alpha * (observed - previous_state)
                data.qpos[qpos_addresses] = pose
                data.qvel[dof_addresses] = velocity
                data.ctrl[actuator_ids] = pose
                mujoco.mj_forward(model, data)
                mujoco.mj_step(model, data)
                latch.enforce(model, data, dt=timestep)
        else:
            raise RetrospectiveHybridReplayError(f"unknown replay driver: {driver}")
        previous_state = observed.copy()
        if index == grasp_index:
            latch.engage(
                model,
                data,
                selected_body=selected_body,
                maximum_distance_m=float(replay["maximum_attach_distance_m"]),
            )
        if index == release_index:
            latch.release()
        simulated = np.asarray(data.qpos[qpos_addresses], dtype=np.float64)
        error = simulated - observed
        maximum_tracking_error = np.maximum(maximum_tracking_error, np.abs(error))
        squared_tracking_error += np.square(error)
        tracking_samples += 1
        state_trace.capture(
            data,
            phase=(
                "pregrasp"
                if index < grasp_index
                else "mode_conditioned_carry"
                if index < release_index
                else "release_and_settle"
            ),
            force=True,
        )
        trace_rows.append(
            {
                "sample_index": index,
                "source_timestamp_seconds": float(timestamps[index]),
                "mapped_action": action.astype(float).tolist(),
                "observed_joint_state": observed.astype(float).tolist(),
                "simulated_joint_state": simulated.astype(float).tolist(),
                "selected_pawn_position_m": np.asarray(
                    data.xpos[selected_body], dtype=np.float64
                ).astype(float).tolist(),
                "grasp_mode_active": latch.active,
            }
        )

    settle_steps = round(
        float(replay["post_release_settle_seconds"]) / timestep
    )
    if driver == "observed_joint_state_upper_bound":
        data.qvel[dof_addresses] = 0.0
        data.qpos[qpos_addresses] = measured[-1]
        data.ctrl[actuator_ids] = measured[-1]
        mujoco.mj_forward(model, data)
    for _ in range(settle_steps):
        mujoco.mj_step(model, data)
    state_trace.capture(data, phase="settled", force=True)

    other_displacement = 0.0
    for name, body_id in piece_bodies.items():
        if name == selected_name:
            continue
        other_displacement = max(
            other_displacement,
            float(
                np.linalg.norm(
                    np.asarray(data.xpos[body_id], dtype=np.float64)
                    - initial_piece_positions[name]
                )
            ),
        )
    outcome = evaluate_outcome(
        final_position=np.asarray(data.xpos[selected_body], dtype=np.float64),
        final_rotation=_rotation(data, selected_body),
        final_velocity=np.asarray(
            data.qvel[selected_dof : selected_dof + 6], dtype=np.float64
        ),
        initial_height_m=initial_height,
        target_position=target_position,
        maximum_other_piece_displacement_m=other_displacement,
        evaluator=contract["evaluator"],
    )
    outcome["gates"]["latch_engaged_once"] = latch.engaged
    outcome["gates"]["latch_released_once"] = latch.released
    outcome["gates"]["timestamp_quantization"] = maximum_quantization_error <= float(
        replay["maximum_timestamp_quantization_error_seconds"]
    )
    outcome["coarse_square_task_success"] = bool(
        outcome["coarse_square_task_success"]
        and outcome["gates"]["latch_engaged_once"]
        and outcome["gates"]["latch_released_once"]
        and outcome["gates"]["timestamp_quantization"]
    )
    outcome["composable_task_success"] = bool(
        outcome["composable_task_success"]
        and outcome["gates"]["latch_engaged_once"]
        and outcome["gates"]["latch_released_once"]
        and outcome["gates"]["timestamp_quantization"]
    )
    trace_path = output_directory / f"{driver}_trace.json"
    atomic_write_json(
        trace_path,
        {
            "schema_version": "sim2claw.retrospective_real_to_sim_hybrid_trace.v1",
            "driver": driver,
            "rows": trace_rows,
        },
    )
    state_trace_path = output_directory / f"{driver}_state_trace.json"
    state_trace_receipt = state_trace.write(state_trace_path)
    return {
        "driver": driver,
        "mapped_action_sha256": _array_sha256(actions),
        "mapped_action_shape": list(actions.shape),
        "mapped_action_dtype": str(actions.dtype),
        "source_timestamp_sha256": _little_endian_hash(timestamps, "<f8"),
        "maximum_timestamp_quantization_error_seconds": maximum_quantization_error,
        "tracking": {
            "per_joint_rms_sim_units": np.sqrt(
                squared_tracking_error / tracking_samples
            ).astype(float).tolist(),
            "per_joint_maximum_absolute_error_sim_units": maximum_tracking_error.astype(
                float
            ).tolist(),
        },
        "grasp_mode": {
            "engaged": latch.engaged,
            "released": latch.released,
            "attach_distance_m": latch.attach_distance_m,
            "maximum_hold_pose_step_m": latch.maximum_hold_pose_step_m,
            "terminal_pose_forced": False,
        },
        "outcome": outcome,
        "trace_path": str(trace_path.relative_to(REPO_ROOT)),
        "trace_sha256": sha256_file(trace_path),
        "state_trace_path": str(state_trace_path.relative_to(REPO_ROOT)),
        "state_trace_sha256": state_trace_receipt["sha256"],
    }


def replay(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
) -> dict[str, Any]:
    contract = load_contract(contract_path)
    source = contract["source"]
    source_directory = (REPO_ROOT / source["directory"]).resolve()
    receipt = _read_json(source_directory / "recording_receipt.json")
    phase_a = _read_json(source_directory / "phase_a_comparison_receipt.json")
    if receipt.get("recording_id") != source["recording_id"]:
        raise RetrospectiveHybridReplayError("source recording identity changed")
    visual = phase_a.get("source_visual_verification", {})
    c922 = visual.get("c922", {})
    if not (
        visual.get("verified") is True
        and c922.get("initial_square") == source["source_square"]
        and c922.get("terminal_square") == source["destination_square"]
        and c922.get("initial_upright") is True
        and c922.get("terminal_upright") is True
        and visual.get("grasp_marker", {}).get("sample_index")
        == source["grasp_marker_sample_index"]
        and visual.get("release_marker", {}).get("sample_index")
        == source["release_marker_sample_index"]
    ):
        raise RetrospectiveHybridReplayError("Phase-A visual authority changed")
    rows = [
        json.loads(line)
        for line in (source_directory / "samples.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    if len(rows) != int(receipt["sample_count"]):
        raise RetrospectiveHybridReplayError("source sample count changed")
    raw_commands = np.asarray(
        [row["follower_command_degrees"] for row in rows], dtype=np.float64
    )
    raw_measured = np.asarray(
        [row["follower_actual_position_degrees"] for row in rows], dtype=np.float64
    )
    raw_timestamps = np.asarray(
        [row["timestamp_monotonic_seconds"] for row in rows], dtype=np.float64
    )
    phase_lineage = phase_a["action_lineage"]
    if _little_endian_hash(raw_commands, "<f4") != phase_lineage[
        "gateway_sent_action"
    ]["float32_little_endian_sha256"]:
        raise RetrospectiveHybridReplayError("gateway-sent source bytes changed")
    if _little_endian_hash(raw_measured, "<f8") != phase_lineage[
        "observed_physical_joints"
    ]["float64_little_endian_sha256"]:
        raise RetrospectiveHybridReplayError("observed joint-state bytes changed")
    timestamps = raw_timestamps - raw_timestamps[0]
    if np.any(np.diff(timestamps) <= 0.0):
        raise RetrospectiveHybridReplayError("source timestamps are not strictly ordered")

    train, events = _load_partition(REPO_ROOT, "train")
    _, candidate, stage_d_parameters, _ = _reconstruct_stage_d(train, events)
    binding = build_workcell_model(candidate)
    bounds = np.asarray(binding["actuator_bounds"], dtype=np.float64)
    adapter = candidate.adapter()
    actions = np.ascontiguousarray(
        np.asarray(
            [
                physical_values_to_sim_with_adapter(row, bounds[-1], adapter)
                for row in raw_commands
            ],
            dtype=np.float64,
        )
    )
    measured = np.ascontiguousarray(
        np.asarray(
            [
                physical_values_to_sim_with_adapter(row, bounds[-1], adapter)
                for row in raw_measured
            ],
            dtype=np.float64,
        )
    )
    if np.any(actions < bounds[:, 0]) or np.any(actions > bounds[:, 1]):
        raise RetrospectiveHybridReplayError("mapped actions would require clipping")
    if np.any(measured < bounds[:, 0]) or np.any(measured > bounds[:, 1]):
        raise RetrospectiveHybridReplayError("observed states leave the modeled range")

    output_directory.mkdir(parents=True, exist_ok=True)
    drivers = {
        name: _replay_driver(
            driver=name,
            contract=contract,
            candidate=candidate,
            rows=rows,
            actions=actions,
            measured=measured,
            timestamps=timestamps,
            output_directory=output_directory,
        )
        for name in contract["replay"]["drivers"]
    }
    command_success = bool(
        drivers["mapped_gateway_command_zoh"]["outcome"][
            "coarse_square_task_success"
        ]
    )
    state_success = bool(
        drivers["observed_joint_state_upper_bound"]["outcome"][
            "coarse_square_task_success"
        ]
    )
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "created_at": datetime.now(UTC).isoformat(),
        "experiment_id": contract["experiment_id"],
        "proof_class": contract["proof_class"],
        "contract_path": str(contract_path.resolve().relative_to(REPO_ROOT)),
        "contract_sha256": sha256_file(contract_path),
        "implementation_path": str(Path(__file__).resolve().relative_to(REPO_ROOT)),
        "implementation_sha256": sha256_file(Path(__file__).resolve()),
        "source": {
            "recording_id": source["recording_id"],
            "physical_visual_outcome_verified": True,
            "source_square": source["source_square"],
            "destination_square": source["destination_square"],
            "recording_receipt_sha256": source["recording_receipt_sha256"],
            "samples_sha256": source["samples_sha256"],
            "phase_a_receipt_sha256": source["phase_a_receipt_sha256"],
            "gateway_sent_float32_sha256": phase_lineage[
                "gateway_sent_action"
            ]["float32_little_endian_sha256"],
            "observed_joint_state_float64_sha256": phase_lineage[
                "observed_physical_joints"
            ]["float64_little_endian_sha256"],
            "pure_action_replay_eligible": False,
            "pure_action_replay_blockers": phase_lineage[
                "exact_action_replay_blockers"
            ],
        },
        "mapping": {
            "candidate": candidate.as_dict(),
            "stage_d_parameters": stage_d_parameters,
            "global_physical_model_mapping_approved": False,
        },
        "drivers": drivers,
        "ledger": {
            "pure_action_only_real_to_sim": {"successes": 0, "attempts": 0},
            "command_plus_observed_grasp_mode_real_to_sim": {
                "successes": int(command_success),
                "attempts": 1,
            },
            "observed_state_plus_observed_grasp_mode_real_to_sim": {
                "successes": int(state_success),
                "attempts": 1,
            },
            "physical_task_attempts_added": 0,
            "sim_to_real_added": 0,
        },
        "verdict": (
            "HYBRID_REAL_TO_SIM_TASK_REPLAY_ADVANCED"
            if command_success or state_success
            else "HYBRID_REAL_TO_SIM_TASK_REPLAY_NEGATIVE"
        ),
        "claim_boundary": contract["claim_boundary"],
        "authority": contract["authority"],
    }
    receipt_payload = {**unsigned, "receipt_sha256": canonical_digest(unsigned)}
    atomic_write_json(output_directory / "receipt.json", receipt_payload)
    return receipt_payload


__all__ = [
    "CONTRACT_PATH",
    "OUTPUT_DIRECTORY",
    "RECEIPT_SCHEMA",
    "RetrospectiveHybridReplayError",
    "evaluate_outcome",
    "load_contract",
    "replay",
]
