"""Observation-conditioned REAL-to-SIM support-handoff successor.

RP04K showed that the measured physical joint trace can carry the selected
pawn into the destination neighborhood, while the simulator's free 30 mm
release topples a pawn that remained upright in the reviewed physical video.
This successor does not fit contact parameters.  It explicitly supplies that
camera-observed upright/support mode, preserves handoff XY, and enumerates the
small symmetric event-timing uncertainty caused by absent actuator
application timestamps.
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

from .learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .paths import REPO_ROOT
from .pawn_bg_action_frozen_gap import _array_sha256, _load_partition, _reconstruct_stage_d
from .pawn_bg_demo_sim import (
    BASELINE_PIECE_BY_FILE,
    _piece_bodies,
    physical_values_to_sim_with_adapter,
)
from .pawn_bg_workcell_fit import _workcell_square_center, build_workcell_model
from .retrospective_real_to_sim_hybrid import (
    CONTRACT_PATH as PREDECESSOR_CONTRACT_PATH,
)
from .retrospective_real_to_sim_hybrid import (
    RetrospectiveHybridReplayError,
    _Latch,
    _read_json,
    _rotation,
    _wxyz,
    evaluate_outcome,
    load_contract as load_predecessor_contract,
)
from .state_trace import EpisodeStateTraceRecorder


CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "retrospective_real_to_sim_support_handoff_v1.json"
)
OUTPUT_DIRECTORY = (
    REPO_ROOT / "outputs" / "retrospective_real_to_sim_support_handoff_v1"
)
SCHEMA = "sim2claw.retrospective_real_to_sim_support_handoff.v1"
RECEIPT_SCHEMA = "sim2claw.retrospective_real_to_sim_support_handoff_receipt.v1"


class SupportHandoffReplayError(RetrospectiveHybridReplayError):
    """The frozen support-handoff replay cannot execute as specified."""


def _require_hash(path: Path, expected: str) -> None:
    if not path.is_file() or sha256_file(path) != expected:
        raise SupportHandoffReplayError(f"bound evidence hash rejected: {path}")


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    contract = _read_json(path)
    if contract.get("schema_version") != SCHEMA:
        raise SupportHandoffReplayError("unexpected support-handoff schema")
    predecessor = contract.get("predecessor")
    source = contract.get("source")
    replay = contract.get("replay")
    acceptance = contract.get("acceptance")
    authority = contract.get("authority")
    if not all(
        isinstance(value, dict)
        for value in (predecessor, source, replay, acceptance, authority)
    ):
        raise SupportHandoffReplayError("support-handoff contract is incomplete")
    _require_hash(
        REPO_ROOT / predecessor["contract_path"],
        str(predecessor["contract_sha256"]),
    )
    _require_hash(
        REPO_ROOT / predecessor["closeout_path"],
        str(predecessor["closeout_sha256"]),
    )
    if (REPO_ROOT / predecessor["contract_path"]).resolve() != (
        PREDECESSOR_CONTRACT_PATH.resolve()
    ):
        raise SupportHandoffReplayError("predecessor contract path changed")
    load_predecessor_contract(PREDECESSOR_CONTRACT_PATH)
    if replay.get("driver") != "observed_joint_state_upper_bound":
        raise SupportHandoffReplayError("support-handoff driver changed")
    if replay.get("release_event_sample_offsets") != [-1, 0, 1]:
        raise SupportHandoffReplayError("release-event grid is not symmetric")
    for field in (
        "preserve_source_row_order",
        "preserve_source_host_timestamps",
        "preserve_observed_joint_state_bytes",
        "preserve_handoff_xy",
        "preserve_destination",
    ):
        if replay.get(field) is not True:
            raise SupportHandoffReplayError(f"{field} must remain true")
    for field in (
        "action_clipping_allowed",
        "action_smoothing_allowed",
        "action_offset_or_ik_repair_allowed",
        "terminal_xy_forcing_allowed",
        "terminal_destination_pose_forcing_allowed",
    ):
        if replay.get(field) is not False:
            raise SupportHandoffReplayError(f"{field} must remain false")
    if replay.get("support_handoff_mode") != (
        "camera_observed_upright_quasistatic_support_projection"
    ):
        raise SupportHandoffReplayError("support-handoff mode changed")
    if not 0.0 < float(replay["maximum_vertical_support_projection_m"]) <= 0.04:
        raise SupportHandoffReplayError("vertical support projection widened")
    if (
        int(acceptance["minimum_successful_offsets_for_narrow_advancement"])
        != 1
    ):
        raise SupportHandoffReplayError("success threshold changed")
    if authority != {
        "camera": False,
        "hardware": False,
        "physical_motion": False,
        "physical_task_attempt": False,
        "sim_to_real": False,
        "pure_action_only_transfer": False,
        "free_release_physics_transfer": False,
        "simulator_replay": True,
    }:
        raise SupportHandoffReplayError("support-handoff authority widened")
    return contract


def _little_endian_hash(values: np.ndarray, dtype: str) -> str:
    array = np.ascontiguousarray(values, dtype=np.dtype(dtype))
    return hashlib.sha256(array.tobytes(order="C")).hexdigest()


def apply_support_handoff(
    *,
    model: mujoco.MjModel,
    data: mujoco.MjData,
    selected_body: int,
    selected_qpos: int,
    selected_dof: int,
    support_height_m: float,
    upright_rotation: np.ndarray,
) -> dict[str, Any]:
    """Project only Z/orientation to the observed support mode; preserve XY."""

    before_position = np.asarray(
        data.qpos[selected_qpos : selected_qpos + 3], dtype=np.float64
    ).copy()
    before_rotation = _rotation(data, selected_body)
    after_position = before_position.copy()
    after_position[2] = support_height_m
    data.qpos[selected_qpos : selected_qpos + 3] = after_position
    data.qpos[selected_qpos + 3 : selected_qpos + 7] = _wxyz(upright_rotation)
    data.qvel[selected_dof : selected_dof + 6] = 0.0
    mujoco.mj_forward(model, data)
    return {
        "before_position_m": before_position.astype(float).tolist(),
        "after_position_m": after_position.astype(float).tolist(),
        "xy_projection_m": float(
            np.linalg.norm(after_position[:2] - before_position[:2])
        ),
        "vertical_projection_m": abs(
            float(after_position[2] - before_position[2])
        ),
        "before_tilt_degrees": math.degrees(
            math.acos(float(np.clip(before_rotation[2, 2], -1.0, 1.0)))
        ),
        "terminal_destination_pose_forced": False,
    }


def _prepare_inputs(
    predecessor: dict[str, Any],
) -> tuple[Any, list[dict[str, Any]], np.ndarray, np.ndarray, dict[str, Any]]:
    source = predecessor["source"]
    source_directory = (REPO_ROOT / source["directory"]).resolve()
    recording = _read_json(source_directory / "recording_receipt.json")
    phase_a = _read_json(source_directory / "phase_a_comparison_receipt.json")
    rows = [
        json.loads(line)
        for line in (source_directory / "samples.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    if len(rows) != int(recording["sample_count"]):
        raise SupportHandoffReplayError("source sample count changed")
    raw_measured = np.asarray(
        [row["follower_actual_position_degrees"] for row in rows],
        dtype=np.float64,
    )
    raw_timestamps = np.asarray(
        [row["timestamp_monotonic_seconds"] for row in rows],
        dtype=np.float64,
    )
    lineage = phase_a["action_lineage"]
    expected_measured_hash = lineage["observed_physical_joints"][
        "float64_little_endian_sha256"
    ]
    if _little_endian_hash(raw_measured, "<f8") != expected_measured_hash:
        raise SupportHandoffReplayError("observed joint-state bytes changed")
    timestamps = raw_timestamps - raw_timestamps[0]
    if np.any(np.diff(timestamps) <= 0.0):
        raise SupportHandoffReplayError("source timestamps are not strictly ordered")
    train, events = _load_partition(REPO_ROOT, "train")
    _, candidate, _, _ = _reconstruct_stage_d(train, events)
    binding = build_workcell_model(candidate)
    bounds = np.asarray(binding["actuator_bounds"], dtype=np.float64)
    adapter = candidate.adapter()
    measured = np.ascontiguousarray(
        np.asarray(
            [
                physical_values_to_sim_with_adapter(row, bounds[-1], adapter)
                for row in raw_measured
            ],
            dtype=np.float64,
        )
    )
    if np.any(measured < bounds[:, 0]) or np.any(measured > bounds[:, 1]):
        raise SupportHandoffReplayError("observed states leave the modeled range")
    return candidate, rows, measured, timestamps, lineage


def _offset_label(offset: int) -> str:
    if offset < 0:
        return f"minus_{abs(offset)}"
    if offset > 0:
        return f"plus_{offset}"
    return "zero"


def _replay_offset(
    *,
    offset: int,
    contract: dict[str, Any],
    predecessor: dict[str, Any],
    candidate: Any,
    measured: np.ndarray,
    timestamps: np.ndarray,
    output_directory: Path,
) -> dict[str, Any]:
    source = predecessor["source"]
    replay = contract["replay"]
    binding = build_workcell_model(candidate)
    model: mujoco.MjModel = binding["model"]
    data: mujoco.MjData = binding["data"]
    actuator_ids = np.asarray(binding["actuator_ids"], dtype=np.int32)
    qpos_addresses = np.asarray(binding["qpos_addresses"], dtype=np.int32)
    joint_names = (
        "shoulder_pan",
        "shoulder_lift",
        "elbow_flex",
        "wrist_flex",
        "wrist_roll",
        "gripper",
    )
    joint_ids = np.asarray(
        [
            mujoco.mj_name2id(
                model, mujoco.mjtObj.mjOBJ_JOINT, f"left_{joint}"
            )
            for joint in joint_names
        ],
        dtype=np.int32,
    )
    if np.any(joint_ids < 0):
        raise SupportHandoffReplayError("left-arm joint inventory changed")
    dof_addresses = np.asarray(model.jnt_dofadr[joint_ids], dtype=np.int32)
    selected_name = str(source["selected_piece"])
    if selected_name != BASELINE_PIECE_BY_FILE[str(source["source_square"])[0]]:
        raise SupportHandoffReplayError("selected pawn identity changed")
    selected_body = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_BODY, selected_name
    )
    selected_joint = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_JOINT, f"{selected_name}_free"
    )
    if selected_body < 0 or selected_joint < 0:
        raise SupportHandoffReplayError("selected pawn is missing")
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
    data.ctrl[actuator_ids] = measured[0]
    mujoco.mj_forward(model, data)
    mujoco.mj_step(model, data, nstep=100)
    support_height = float(data.xpos[selected_body][2])
    upright_rotation = _rotation(data, selected_body)
    piece_bodies = _piece_bodies(model)
    initial_piece_positions = {
        name: np.asarray(data.xpos[body_id], dtype=np.float64).copy()
        for name, body_id in piece_bodies.items()
    }
    fixed_tip_geom = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_GEOM, "left_fixed_jaw_sph_tip2"
    )
    if fixed_tip_geom < 0:
        raise SupportHandoffReplayError("fixed-jaw tip geometry changed")
    latch = _Latch(
        selected_qpos=selected_qpos,
        selected_dof=selected_dof,
        jaw_body=int(model.geom_bodyid[fixed_tip_geom]),
        pinch_local=np.asarray(binding["pinch_offset_local"], dtype=np.float64),
    )
    grasp_index = int(source["grasp_marker_sample_index"])
    release_index = int(source["release_marker_sample_index"]) + offset
    if not grasp_index < release_index < len(measured):
        raise SupportHandoffReplayError("event offset leaves source bounds")
    timestep = float(model.opt.timestep)
    nominal_dt = 1.0 / 20.0
    maximum_quantization_error = 0.0
    squared_tracking_error = np.zeros(6, dtype=np.float64)
    maximum_tracking_error = np.zeros(6, dtype=np.float64)
    previous_state = measured[0].copy()
    handoff: dict[str, Any] | None = None
    trace_rows: list[dict[str, Any]] = []
    state_trace = EpisodeStateTraceRecorder(
        model,
        piece_layout="sparse_two_sided_pawns",
        fps=20,
        proof_class=f"real_to_sim_support_handoff_offset_{offset:+d}",
    )

    for index, observed in enumerate(measured):
        dt = (
            nominal_dt
            if index == 0
            else float(timestamps[index] - timestamps[index - 1])
        )
        if not math.isfinite(dt) or dt <= 0.0:
            raise SupportHandoffReplayError("source timestamps are not monotonic")
        nstep = max(1, round(dt / timestep))
        maximum_quantization_error = max(
            maximum_quantization_error, abs(nstep * timestep - dt)
        )
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
        previous_state = observed.copy()
        if index == grasp_index:
            latch.engage(
                model,
                data,
                selected_body=selected_body,
                maximum_distance_m=float(
                    load_predecessor_contract()["replay"]["maximum_attach_distance_m"]
                ),
            )
        if index == release_index:
            handoff = apply_support_handoff(
                model=model,
                data=data,
                selected_body=selected_body,
                selected_qpos=selected_qpos,
                selected_dof=selected_dof,
                support_height_m=support_height,
                upright_rotation=upright_rotation,
            )
            latch.release()
        simulated = np.asarray(data.qpos[qpos_addresses], dtype=np.float64)
        tracking_error = simulated - observed
        squared_tracking_error += np.square(tracking_error)
        maximum_tracking_error = np.maximum(
            maximum_tracking_error, np.abs(tracking_error)
        )
        state_trace.capture(
            data,
            phase=(
                "pregrasp"
                if index < grasp_index
                else "mode_conditioned_carry"
                if index < release_index
                else "observed_support_handoff_then_free_physics"
            ),
            force=True,
        )
        trace_rows.append(
            {
                "sample_index": index,
                "source_timestamp_seconds": float(timestamps[index]),
                "observed_joint_state": observed.astype(float).tolist(),
                "simulated_joint_state": simulated.astype(float).tolist(),
                "selected_pawn_position_m": np.asarray(
                    data.xpos[selected_body], dtype=np.float64
                ).astype(float).tolist(),
                "grasp_mode_active": latch.active,
                "support_handoff_applied": index == release_index,
            }
        )

    if handoff is None or not latch.released:
        raise SupportHandoffReplayError("support handoff did not execute exactly once")
    data.qvel[dof_addresses] = 0.0
    data.qpos[qpos_addresses] = measured[-1]
    data.ctrl[actuator_ids] = measured[-1]
    mujoco.mj_forward(model, data)
    settle_steps = round(
        float(replay["post_handoff_free_physics_settle_seconds"]) / timestep
    )
    for _ in range(settle_steps):
        mujoco.mj_step(model, data)
    state_trace.capture(data, phase="settled", force=True)
    maximum_other_displacement = max(
        (
            float(
                np.linalg.norm(
                    np.asarray(data.xpos[body_id], dtype=np.float64)
                    - initial_piece_positions[name]
                )
            )
            for name, body_id in piece_bodies.items()
            if name != selected_name
        ),
        default=0.0,
    )
    outcome = evaluate_outcome(
        final_position=np.asarray(data.xpos[selected_body], dtype=np.float64),
        final_rotation=_rotation(data, selected_body),
        final_velocity=np.asarray(
            data.qvel[selected_dof : selected_dof + 6], dtype=np.float64
        ),
        initial_height_m=support_height,
        target_position=target_position,
        maximum_other_piece_displacement_m=maximum_other_displacement,
        evaluator=load_predecessor_contract()["evaluator"],
    )
    outcome["gates"]["support_handoff_applied_once"] = True
    outcome["gates"]["handoff_xy_preserved"] = handoff["xy_projection_m"] == 0.0
    outcome["gates"]["bounded_vertical_support_projection"] = handoff[
        "vertical_projection_m"
    ] <= float(replay["maximum_vertical_support_projection_m"])
    outcome["gates"]["timestamp_quantization"] = maximum_quantization_error <= float(
        replay["maximum_timestamp_quantization_error_seconds"]
    )
    additional_gates_pass = all(
        outcome["gates"][key]
        for key in (
            "support_handoff_applied_once",
            "handoff_xy_preserved",
            "bounded_vertical_support_projection",
            "timestamp_quantization",
        )
    )
    outcome["coarse_square_task_success"] = bool(
        outcome["coarse_square_task_success"] and additional_gates_pass
    )
    outcome["composable_task_success"] = bool(
        outcome["composable_task_success"] and additional_gates_pass
    )
    label = _offset_label(offset)
    trace_path = output_directory / f"offset_{label}_trace.json"
    atomic_write_json(
        trace_path,
        {
            "schema_version": "sim2claw.retrospective_real_to_sim_support_handoff_trace.v1",
            "release_event_sample_offset": offset,
            "rows": trace_rows,
        },
    )
    state_trace_path = output_directory / f"offset_{label}_state_trace.json"
    state_trace_receipt = state_trace.write(state_trace_path)
    return {
        "release_event_sample_offset": offset,
        "release_event_sample_index": release_index,
        "observed_joint_state_sha256": _array_sha256(measured),
        "source_timestamp_sha256": _little_endian_hash(timestamps, "<f8"),
        "maximum_timestamp_quantization_error_seconds": maximum_quantization_error,
        "tracking": {
            "per_joint_rms_sim_units": np.sqrt(
                squared_tracking_error / len(measured)
            ).astype(float).tolist(),
            "per_joint_maximum_absolute_error_sim_units": maximum_tracking_error.astype(
                float
            ).tolist(),
        },
        "grasp_mode": {
            "engaged": latch.engaged,
            "released": latch.released,
            "attach_distance_m": latch.attach_distance_m,
            "terminal_destination_pose_forced": False,
        },
        "support_handoff": handoff,
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
    predecessor = load_predecessor_contract(PREDECESSOR_CONTRACT_PATH)
    source = contract["source"]
    predecessor_source = predecessor["source"]
    for key in (
        "recording_id",
        "source_square",
        "destination_square",
        "selected_piece",
        "grasp_marker_sample_index",
        "release_marker_sample_index",
    ):
        if source[key] != predecessor_source[key]:
            raise SupportHandoffReplayError(f"source {key} changed")
    if (
        source["physical_initial_upright_reviewed"] is not True
        or source["physical_terminal_upright_reviewed"] is not True
    ):
        raise SupportHandoffReplayError("camera-reviewed upright mode was removed")
    candidate, _, measured, timestamps, lineage = _prepare_inputs(predecessor)
    output_directory.mkdir(parents=True, exist_ok=True)
    variants = {
        _offset_label(offset): _replay_offset(
            offset=int(offset),
            contract=contract,
            predecessor=predecessor,
            candidate=candidate,
            measured=measured,
            timestamps=timestamps,
            output_directory=output_directory,
        )
        for offset in contract["replay"]["release_event_sample_offsets"]
    }
    successes = sum(
        int(variant["outcome"]["coarse_square_task_success"])
        for variant in variants.values()
    )
    attempts = len(variants)
    minimum = int(
        contract["acceptance"]["minimum_successful_offsets_for_narrow_advancement"]
    )
    timing_sensitive = 0 < successes < attempts
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "created_at": datetime.now(UTC).isoformat(),
        "experiment_id": contract["experiment_id"],
        "proof_class": contract["proof_class"],
        "contract_path": str(contract_path.resolve().relative_to(REPO_ROOT)),
        "contract_sha256": sha256_file(contract_path),
        "implementation_path": str(Path(__file__).resolve().relative_to(REPO_ROOT)),
        "implementation_sha256": sha256_file(Path(__file__).resolve()),
        "predecessor": contract["predecessor"],
        "source": {
            "recording_id": source["recording_id"],
            "source_square": source["source_square"],
            "destination_square": source["destination_square"],
            "physical_initial_upright_reviewed": True,
            "physical_terminal_upright_reviewed": True,
            "observed_joint_state_float64_sha256": lineage[
                "observed_physical_joints"
            ]["float64_little_endian_sha256"],
            "pure_action_replay_eligible": False,
            "pure_action_replay_blockers": lineage["exact_action_replay_blockers"],
        },
        "mapping": {
            "candidate": candidate.as_dict(),
            "global_physical_model_mapping_approved": False,
        },
        "variants": variants,
        "ledger": {
            "pure_action_only_real_to_sim": {"successes": 0, "attempts": 0},
            "free_release_hybrid_real_to_sim": {"successes": 0, "attempts": 2},
            "observed_state_plus_upright_support_mode_real_to_sim": {
                "successes": successes,
                "attempts": attempts,
            },
            "physical_task_attempts_added": 0,
            "sim_to_real_added": 0,
        },
        "timing_sensitive": timing_sensitive,
        "verdict": (
            "OBSERVATION_CONDITIONED_REAL_TO_SIM_ADVANCED_TIMING_SENSITIVE"
            if successes >= minimum and timing_sensitive
            else "OBSERVATION_CONDITIONED_REAL_TO_SIM_ADVANCED"
            if successes >= minimum
            else "OBSERVATION_CONDITIONED_REAL_TO_SIM_NEGATIVE"
        ),
        "claim_boundary": contract["claim_boundary"],
        "authority": contract["authority"],
    }
    receipt = {**unsigned, "receipt_sha256": canonical_digest(unsigned)}
    atomic_write_json(output_directory / "receipt.json", receipt)
    return receipt


__all__ = [
    "CONTRACT_PATH",
    "OUTPUT_DIRECTORY",
    "RECEIPT_SCHEMA",
    "SupportHandoffReplayError",
    "apply_support_handoff",
    "load_contract",
    "replay",
]
