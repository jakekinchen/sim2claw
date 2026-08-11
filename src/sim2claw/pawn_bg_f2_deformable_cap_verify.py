"""Independent full-step verifier for the frozen OR134 replay."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from .learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .paths import REPO_ROOT
from .pawn_bg_action_frozen_gap import _load_partition, _reconstruct_stage_d
from .pawn_bg_timing_ablation import _mapped_episode


CONTRACT_PATH = (
    REPO_ROOT / "configs" / "evaluations" / "pawn_bg_f2_deformable_cap_v1.json"
)
SCHEMA = "sim2claw.pawn_bg_f2_deformable_cap.v1"
TRACE_SCHEMA = "sim2claw.pawn_bg_f2_deformable_cap_full_step_trace.v1"
VERDICT_SCHEMA = "sim2claw.pawn_bg_f2_deformable_cap_independent_verdict.v1"
UNSTABLE_WARNINGS = {
    "mjWARN_BADQPOS",
    "mjWARN_BADQVEL",
    "mjWARN_BADQACC",
    "mjWARN_BADCTRL",
}


class IndependentVerifierError(RuntimeError):
    """The OR134 trace or evaluator binding is invalid."""


def _array_sha256(value: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()


def _load_contract(path: Path, *, expected_schema: str = SCHEMA) -> dict[str, Any]:
    contract = json.loads(path.read_text(encoding="utf-8"))
    return _validate_contract(contract, expected_schema=expected_schema)


def _validate_contract(
    contract: Mapping[str, Any], *, expected_schema: str
) -> dict[str, Any]:
    if contract.get("schema_version") != expected_schema:
        raise IndependentVerifierError("unexpected deformable-cap contract schema")
    reward = contract["source_bindings"]["original_reward"]
    reward_path = REPO_ROOT / reward["path"]
    if sha256_file(reward_path) != reward["sha256"]:
        raise IndependentVerifierError("original reward binding drifted")
    if any(contract.get("authority", {}).values()):
        raise IndependentVerifierError("OR134 external authority widened")
    return dict(contract)


def _source_episode(contract: Mapping[str, Any]) -> dict[str, Any]:
    train, events = _load_partition(REPO_ROOT, "train")
    _parent, workcell, _parameters, _details = _reconstruct_stage_d(train, events)
    recording_id = str(contract["source_bindings"]["recording_id"])
    rows = [
        _mapped_episode(payload, workcell)
        for payload in train
        if str(payload[0]["recording_id"]) == recording_id
    ]
    if len(rows) != 1:
        raise IndependentVerifierError("source episode identity is not unique")
    mapped = rows[0]
    actions = np.ascontiguousarray(mapped["actions"], dtype=np.float64)
    timestamps = np.ascontiguousarray(mapped["timestamps"], dtype=np.float64)
    if (
        list(actions.shape) != contract["action_invariance"]["shape"]
        or actions.dtype != np.float64
        or _array_sha256(actions) != contract["source_bindings"]["action_sha256"]
        or _array_sha256(timestamps)
        != contract["source_bindings"]["timestamp_sha256"]
        or workcell.adapter().sha256
        != contract["source_bindings"]["stage_d_adapter_sha256"]
    ):
        raise IndependentVerifierError("source action/timing/adapter provenance drifted")
    return {"actions": actions, "timestamps": timestamps}


def _load_trace(
    trace_path: Path,
    metadata_path: Path,
    *,
    expected_schema: str = TRACE_SCHEMA,
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("schema_version") != expected_schema:
        raise IndependentVerifierError("unexpected full-step trace schema")
    with np.load(trace_path, allow_pickle=False) as archive:
        arrays = {name: np.asarray(archive[name]) for name in archive.files}
    required = {
        "time",
        "phase",
        "source_indices",
        "requested_action",
        "applied_ctrl",
        "qpos",
        "qvel",
        "selected_position",
        "selected_quaternion_wxyz",
        "selected_linear_velocity",
        "selected_angular_velocity",
        "piece_positions",
        "piece_quaternions_wxyz",
        "contact_offsets",
        "contact_step",
        "contact_geom",
        "contact_flex",
        "contact_elem",
        "contact_vert",
        "contact_pos",
        "contact_frame",
        "contact_force",
        "contact_dim",
        "contact_dist",
    }
    if set(arrays) != required:
        raise IndependentVerifierError(
            f"trace arrays drifted: {sorted(set(arrays) ^ required)}"
        )
    digest = hashlib.sha256()
    for name in sorted(arrays):
        value = np.ascontiguousarray(arrays[name])
        digest.update(name.encode("utf-8"))
        digest.update(value.dtype.str.encode("ascii"))
        digest.update(np.asarray(value.shape, dtype=np.int64).tobytes())
        digest.update(value.tobytes())
    if digest.hexdigest() != metadata.get("array_digest"):
        raise IndependentVerifierError("full-step array digest mismatch")
    if sha256_file(trace_path) != metadata.get("array_file_sha256"):
        raise IndependentVerifierError("full-step trace file hash mismatch")
    if canonical_digest(metadata.get("model_invariant_payload")) != metadata.get(
        "model_invariant_digest"
    ):
        raise IndependentVerifierError("named model invariant payload digest mismatch")
    return arrays, metadata


def _quaternion_tilt_degrees(quaternion_wxyz: np.ndarray) -> np.ndarray:
    quaternion = np.asarray(quaternion_wxyz, dtype=np.float64)
    norms = np.linalg.norm(quaternion, axis=-1)
    if np.any(np.abs(norms - 1.0) > 1e-6):
        raise IndependentVerifierError("non-unit pawn quaternion in trace")
    x = quaternion[..., 1]
    y = quaternion[..., 2]
    upright_cosine = np.clip(1.0 - 2.0 * (x * x + y * y), -1.0, 1.0)
    return np.degrees(np.arccos(upright_cosine))


def _quaternion_distance_degrees(
    initial: np.ndarray, observed: np.ndarray
) -> np.ndarray:
    dots = np.abs(np.sum(observed * initial, axis=-1))
    return np.degrees(2.0 * np.arccos(np.clip(dots, 0.0, 1.0)))


def _maximum_run(condition: np.ndarray) -> tuple[int, int | None, int | None]:
    best = current = 0
    best_start = best_end = None
    start = 0
    for index, active in enumerate(condition.astype(bool)):
        if active:
            if current == 0:
                start = index
            current += 1
            if current > best:
                best = current
                best_start = start
                best_end = index
        else:
            current = 0
    return best, best_start, best_end


def _endpoint(
    arrays: Mapping[str, np.ndarray],
    metadata: Mapping[str, Any],
    contact_index: int,
    side: int,
) -> dict[str, Any]:
    geom_id = int(arrays["contact_geom"][contact_index, side])
    flex_id = int(arrays["contact_flex"][contact_index, side])
    if geom_id >= 0 and flex_id >= 0:
        raise IndependentVerifierError("contact endpoint has geom and flex identity")
    if geom_id >= 0:
        geom_body_ids = metadata["geom_body_ids"]
        if geom_id >= len(geom_body_ids):
            raise IndependentVerifierError("contact geom id is out of range")
        body_id = int(geom_body_ids[geom_id])
        return {
            "kind": "geom",
            "geom_id": geom_id,
            "flex_id": -1,
            "body_id": body_id,
            "body_name": metadata["body_names"][body_id],
            "object_name": metadata["geom_names"][geom_id],
            "role": None,
        }
    if flex_id >= 0:
        rows = [
            row for row in metadata["flex_semantics"] if row["flex_id"] == flex_id
        ]
        if len(rows) != 1:
            raise IndependentVerifierError("flex contact semantic alias is missing")
        row = rows[0]
        return {
            "kind": "flex",
            "geom_id": -1,
            "flex_id": flex_id,
            "body_id": int(row["body_id"]),
            "body_name": str(row["body_name"]),
            "object_name": str(row["flex_name"]),
            "role": str(row["role"]),
        }
    raise IndependentVerifierError("contact endpoint has no identity")


def _contact_step_semantics(
    arrays: Mapping[str, np.ndarray],
    metadata: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> dict[str, np.ndarray]:
    step_count = len(arrays["time"])
    offsets = arrays["contact_offsets"]
    if len(offsets) != step_count + 1 or offsets[0] != 0:
        raise IndependentVerifierError("contact offsets are malformed")
    if int(offsets[-1]) != len(arrays["contact_step"]):
        raise IndependentVerifierError("contact offsets do not cover contacts")
    selected = int(metadata["selected_body_id"])
    piece_ids = set(int(value) for value in metadata["piece_body_ids"])
    wrong_piece_ids = piece_ids - {selected}
    robot_ids = set(int(value) for value in metadata["robot_body_ids"])
    board_names = set(str(value) for value in metadata["board_support_body_names"])
    candidate_is_flex = str(metadata["candidate_id"]).startswith("flex_")
    gates = contract["supplemental_gates"]
    qualified = np.zeros(step_count, dtype=bool)
    selected_robot = np.zeros(step_count, dtype=bool)
    board_support = np.zeros(step_count, dtype=bool)
    wrong_contact = np.zeros(step_count, dtype=bool)
    pair_span = np.zeros(step_count, dtype=np.float64)
    pair_opposition = np.full(step_count, -1.0, dtype=np.float64)
    for step in range(step_count):
        fixed: list[dict[str, Any]] = []
        moving: list[dict[str, Any]] = []
        for contact_index in range(int(offsets[step]), int(offsets[step + 1])):
            if int(arrays["contact_step"][contact_index]) != step:
                raise IndependentVerifierError("contact step index disagrees with offsets")
            endpoint0 = _endpoint(arrays, metadata, contact_index, 0)
            endpoint1 = _endpoint(arrays, metadata, contact_index, 1)
            bodies = {endpoint0["body_id"], endpoint1["body_id"]}
            if selected in bodies and bodies & robot_ids:
                selected_robot[step] = True
            if selected in bodies and (
                endpoint0["body_name"] in board_names
                or endpoint1["body_name"] in board_names
            ):
                board_support[step] = True
            if (bodies & wrong_piece_ids and bodies & robot_ids) or (
                selected in bodies and bool(bodies & wrong_piece_ids)
            ):
                wrong_contact[step] = True
            if selected not in bodies:
                continue
            pawn = endpoint0 if endpoint0["body_id"] == selected else endpoint1
            jaw = endpoint1 if pawn is endpoint0 else endpoint0
            if pawn["kind"] != "geom" or jaw["body_id"] not in robot_ids:
                continue
            side = jaw["role"]
            if candidate_is_flex:
                if jaw["kind"] != "flex" or side not in {"fixed", "moving"}:
                    continue
            else:
                name = str(jaw["object_name"])
                side = (
                    "fixed"
                    if "rubber_tip_fixed_" in name
                    else "moving" if "rubber_tip_moving_" in name else None
                )
                if side is None:
                    continue
            normal = np.asarray(
                arrays["contact_frame"][contact_index, :3], dtype=np.float64
            )
            if jaw is endpoint1:
                normal = -normal
            norm = float(np.linalg.norm(normal))
            if norm > 0.0:
                normal = normal / norm
            row = {
                "position": np.asarray(
                    arrays["contact_pos"][contact_index], dtype=np.float64
                ),
                "normal": normal,
                "normal_force": max(
                    0.0, float(arrays["contact_force"][contact_index, 0])
                ),
            }
            (fixed if side == "fixed" else moving).append(row)
        for fixed_contact in fixed:
            for moving_contact in moving:
                span = float(
                    np.linalg.norm(
                        fixed_contact["position"] - moving_contact["position"]
                    )
                )
                opposition = float(
                    -np.dot(fixed_contact["normal"], moving_contact["normal"])
                )
                positive = min(
                    fixed_contact["normal_force"], moving_contact["normal_force"]
                ) > float(gates["minimum_positive_normal_force_n"])
                pair_span[step] = max(pair_span[step], span)
                pair_opposition[step] = max(pair_opposition[step], opposition)
                if (
                    positive
                    and span >= float(gates["minimum_contact_span_m"])
                    and opposition >= float(gates["minimum_opposing_normal_score"])
                ):
                    qualified[step] = True
    return {
        "qualified": qualified,
        "selected_robot": selected_robot,
        "board_support": board_support,
        "wrong_contact": wrong_contact,
        "pair_span": pair_span,
        "pair_opposition": pair_opposition,
    }


def _action_gates(
    arrays: Mapping[str, np.ndarray],
    source: Mapping[str, np.ndarray],
    contract: Mapping[str, Any],
    *,
    applied_control_excluded_phase_codes: frozenset[int] = frozenset(),
) -> tuple[dict[str, bool], dict[str, Any]]:
    actions = source["actions"]
    timestamps = source["timestamps"]
    indices = arrays["source_indices"]
    requested = arrays["requested_action"]
    applied = arrays["applied_ctrl"]
    if indices.shape != requested.shape or requested.shape != applied.shape:
        raise IndependentVerifierError("action trace shapes disagree")
    expected_requested = np.empty_like(requested)
    for row in range(len(requested)):
        for joint in range(6):
            source_index = int(indices[row, joint])
            if not 0 <= source_index < len(actions):
                raise IndependentVerifierError("source action index is out of range")
            expected_requested[row, joint] = actions[source_index, joint]
    phase = arrays["phase"]
    timestep = float(arrays["time"][1] - arrays["time"][0])
    delay = np.asarray(
        contract["action_invariance"]["per_joint_zoh_delay_seconds"],
        dtype=np.float64,
    )
    expected_indices = np.empty_like(indices)
    for row, elapsed in enumerate(arrays["time"]):
        if int(phase[row]) == 2:
            now = float(timestamps[-1])
        elif row == 0:
            now = float(timestamps[0])
        else:
            now = float(timestamps[0] + elapsed - timestep)
        expected_indices[row] = [
            max(0, int(np.searchsorted(timestamps, now - value, side="right") - 1))
            for value in delay
        ]
    applied_mask = ~np.isin(
        phase, np.asarray(sorted(applied_control_excluded_phase_codes), dtype=np.int8)
    )
    if not bool(np.any(applied_mask)):
        raise IndependentVerifierError("applied-control gate excludes every trace row")
    gates = {
        "source_indices_match_frozen_zoh_schedule": bool(
            np.array_equal(indices, expected_indices)
        ),
        "requested_actions_match_frozen_source_bytes": bool(
            np.array_equal(requested, expected_requested)
        ),
        "applied_ctrl_equals_requested_action": bool(
            np.array_equal(applied[applied_mask], requested[applied_mask])
        ),
    }
    metrics = {
        "source_action_sha256": _array_sha256(actions),
        "source_timestamp_sha256": _array_sha256(timestamps),
        "requested_action_trace_sha256": _array_sha256(requested),
        "applied_ctrl_trace_sha256": _array_sha256(applied),
        "source_index_trace_sha256": _array_sha256(indices),
        "maximum_applied_minus_requested_absolute_rad": float(
            np.max(np.abs(applied[applied_mask] - requested[applied_mask]))
        ),
        "applied_control_excluded_phase_codes": sorted(
            int(value) for value in applied_control_excluded_phase_codes
        ),
    }
    return gates, metrics


def verify_trace(
    *,
    trace_path: Path,
    metadata_path: Path,
    contract_path: Path = CONTRACT_PATH,
    contract_schema: str = SCHEMA,
    trace_schema: str = TRACE_SCHEMA,
    verdict_schema: str = VERDICT_SCHEMA,
    verifier_path: Path | None = None,
    applied_control_excluded_phase_codes: frozenset[int] = frozenset(),
    contract_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    contract = (
        _load_contract(contract_path, expected_schema=contract_schema)
        if contract_payload is None
        else _validate_contract(contract_payload, expected_schema=contract_schema)
    )
    arrays, metadata = _load_trace(
        trace_path, metadata_path, expected_schema=trace_schema
    )
    if metadata.get("recording_id") != contract["source_bindings"]["recording_id"]:
        raise IndependentVerifierError("trace recording identity drifted")
    candidate_ids = [row["candidate_id"] for row in contract["candidate_order"]]
    if metadata.get("candidate_id") not in candidate_ids:
        raise IndependentVerifierError("trace candidate is not preregistered")
    step_count = len(arrays["time"])
    if step_count != int(metadata["expected_step_count"]):
        raise IndependentVerifierError("full-step trace is incomplete")
    if arrays["contact_offsets"].shape != (step_count + 1,):
        raise IndependentVerifierError("contact offset length is invalid")
    timestep = float(metadata["timestep_seconds"])
    if not np.all(np.diff(arrays["time"]) > 0.0):
        raise IndependentVerifierError("full-step timestamps are not monotonic")
    source = _source_episode(contract)
    action_gates, action_metrics = _action_gates(
        arrays,
        source,
        contract,
        applied_control_excluded_phase_codes=applied_control_excluded_phase_codes,
    )
    contacts = _contact_step_semantics(arrays, metadata, contract)
    gates = contract["supplemental_gates"]
    selected_position = arrays["selected_position"]
    selected_tilt = _quaternion_tilt_degrees(
        arrays["selected_quaternion_wxyz"]
    )
    linear_speed = np.linalg.norm(arrays["selected_linear_velocity"], axis=1)
    angular_speed = np.linalg.norm(arrays["selected_angular_velocity"], axis=1)
    target = np.asarray(metadata["target_position_xyz_m"], dtype=np.float64)
    target_distance = np.linalg.norm(selected_position[:, :2] - target[:2], axis=1)
    initial_height = float(selected_position[0, 2])
    rise = selected_position[:, 2] - initial_height
    qualified = contacts["qualified"]
    board_support = contacts["board_support"]
    qualified_run, _qualified_start, _qualified_end = _maximum_run(qualified)
    lift_condition = (
        qualified
        & ~board_support
        & (rise >= float(gates["minimum_sustained_lift_m"]))
    )
    lift_run, lift_start, lift_end = _maximum_run(lift_condition)
    minimum_lift_steps = int(
        math.ceil(float(gates["minimum_sustained_lift_seconds"]) / timestep - 1e-12)
    )
    first_lift = lift_start if lift_run >= minimum_lift_steps else None
    carry_progress = 0.0
    maximum_gap_steps = int(
        math.floor(float(gates["maximum_contact_gap_seconds"]) / timestep + 1e-12)
    )
    carry_end = None
    if first_lift is not None:
        origin = selected_position[first_lift, :2]
        direction = target[:2] - origin
        norm = float(np.linalg.norm(direction))
        direction = direction / norm if norm > 0.0 else np.zeros(2)
        gap_steps = 0
        for index in range(first_lift, step_count):
            if board_support[index]:
                break
            if qualified[index]:
                gap_steps = 0
                carry_progress = max(
                    carry_progress,
                    float(np.dot(selected_position[index, :2] - origin, direction)),
                )
                carry_end = index
            else:
                gap_steps += 1
                if gap_steps > maximum_gap_steps:
                    break
    entry_index = None
    if first_lift is not None:
        end = step_count if carry_end is None else carry_end + maximum_gap_steps + 2
        candidates = np.flatnonzero(
            (np.arange(step_count) >= first_lift)
            & (np.arange(step_count) < min(step_count, end))
            & (target_distance <= float(gates["whole_base_entry_distance_m"]))
        )
        entry_index = int(candidates[0]) if len(candidates) else None
    release_index = None
    if entry_index is not None:
        for index in range(entry_index + 1, step_count):
            if not contacts["selected_robot"][index] and np.any(
                qualified[max(entry_index, index - maximum_gap_steps - 1) : index]
            ):
                release_index = index
                break
    settle_condition = (
        ~contacts["selected_robot"]
        & board_support
        & (target_distance <= float(gates["maximum_final_center_distance_m"]))
        & (selected_tilt <= float(gates["maximum_tilt_degrees_every_step"]))
        & (linear_speed <= float(gates["maximum_settled_linear_speed_m_s"]))
        & (angular_speed <= float(gates["maximum_settled_angular_speed_rad_s"]))
    )
    settle_run = 0
    settle_start = settle_end = None
    if release_index is not None:
        settle_run, relative_start, relative_end = _maximum_run(
            settle_condition[release_index:]
        )
        settle_start = (
            None if relative_start is None else release_index + relative_start
        )
        settle_end = None if relative_end is None else release_index + relative_end
    minimum_settle_steps = int(
        math.ceil(float(gates["minimum_post_release_settle_seconds"]) / timestep - 1e-12)
    )
    piece_positions = arrays["piece_positions"]
    piece_quaternions = arrays["piece_quaternions_wxyz"]
    selected_piece_index = metadata["piece_names"].index(
        metadata["selected_body_name"]
    )
    other_indices = [
        index for index in range(len(metadata["piece_names"]))
        if index != selected_piece_index
    ]
    other_translation = (
        np.linalg.norm(
            piece_positions[:, other_indices]
            - piece_positions[0:1, other_indices],
            axis=2,
        )
        if other_indices
        else np.zeros((step_count, 0))
    )
    other_orientation = (
        _quaternion_distance_degrees(
            piece_quaternions[0:1, other_indices],
            piece_quaternions[:, other_indices],
        )
        if other_indices
        else np.zeros((step_count, 0))
    )
    maximum_other_translation = float(np.max(other_translation, initial=0.0))
    maximum_other_orientation = float(np.max(other_orientation, initial=0.0))
    finite = all(
        bool(np.isfinite(arrays[name]).all())
        for name in (
            "qpos",
            "qvel",
            "requested_action",
            "applied_ctrl",
            "selected_position",
            "selected_quaternion_wxyz",
            "piece_positions",
            "piece_quaternions_wxyz",
            "contact_pos",
            "contact_frame",
            "contact_force",
        )
    )
    unstable_warnings = [
        row for row in metadata.get("warning_rows", [])
        if row.get("name") in UNSTABLE_WARNINGS
    ]
    final_distance = float(target_distance[-1])
    final_upright_cosine = float(math.cos(math.radians(selected_tilt[-1])))
    original_gates = {
        "piece_lifted": bool(np.max(rise) >= 0.04),
        "whole_base_inside_destination": final_distance <= 0.008425,
        "composable_center": final_distance <= 0.006,
        "upright": final_upright_cosine >= 0.95,
        "settled": float(linear_speed[-1]) <= 0.02,
        "collateral_within_limit": maximum_other_translation <= 0.006,
        "selected_piece_contact_observed": bool(np.any(contacts["selected_robot"])),
        "released": bool(
            np.any(contacts["selected_robot"])
            and not contacts["selected_robot"][-1]
        ),
        "no_wrong_piece_contact": not bool(np.any(contacts["wrong_contact"])),
        "finite_state": finite and not unstable_warnings,
    }
    gate_results = {
        **action_gates,
        "complete_full_step_trace": step_count
        == int(metadata["expected_step_count"]),
        "same_pair_bilateral_contact_dwell": qualified_run * timestep
        >= float(gates["minimum_same_pair_bilateral_contact_dwell_seconds"]),
        "sustained_qualified_lift_without_board_support": first_lift is not None,
        "genuine_contact_retained_carry": carry_progress
        >= float(gates["minimum_carry_toward_target_m"]),
        "whole_base_entry_after_lift_before_release": entry_index is not None
        and release_index is not None
        and first_lift is not None
        and first_lift <= entry_index < release_index,
        "continuous_upright": bool(
            np.max(selected_tilt)
            <= float(gates["maximum_tilt_degrees_every_step"])
        ),
        "proper_release": release_index is not None,
        "post_release_settle": settle_run >= minimum_settle_steps,
        "no_wrong_pawn_contact": not bool(np.any(contacts["wrong_contact"])),
        "collateral_translation": maximum_other_translation
        <= float(gates["maximum_other_pawn_translation_m"]),
        "collateral_orientation": maximum_other_orientation
        <= float(gates["maximum_other_pawn_orientation_change_degrees"]),
        "finite_stable_state": finite and not unstable_warnings,
        "original_reward_hard_gates": all(original_gates.values()),
    }
    metrics = {
        **action_metrics,
        "step_count": step_count,
        "contact_count": int(len(arrays["contact_step"])),
        "timestep_seconds": timestep,
        "maximum_tilt_degrees": float(np.max(selected_tilt)),
        "maximum_tilt_step": int(np.argmax(selected_tilt)),
        "maximum_rise_m": float(np.max(rise)),
        "maximum_qualified_contact_dwell_seconds": float(qualified_run * timestep),
        "maximum_qualified_lift_dwell_seconds": float(lift_run * timestep),
        "maximum_contact_retained_carry_m": float(carry_progress),
        "first_qualified_lift_step": first_lift,
        "first_target_entry_step": entry_index,
        "release_step": release_index,
        "settle_start_step": settle_start,
        "settle_end_step": settle_end,
        "maximum_post_release_settle_seconds": float(settle_run * timestep),
        "final_center_distance_m": final_distance,
        "final_tilt_degrees": float(selected_tilt[-1]),
        "final_linear_speed_m_s": float(linear_speed[-1]),
        "final_angular_speed_rad_s": float(angular_speed[-1]),
        "maximum_other_pawn_translation_m": maximum_other_translation,
        "maximum_other_pawn_orientation_change_degrees": maximum_other_orientation,
        "wrong_contact_step_count": int(np.count_nonzero(contacts["wrong_contact"])),
        "model_invariant_digest": metadata["model_invariant_digest"],
        "runtime_initial_original_body_pose_digest": metadata[
            "runtime_initial_original_body_pose_digest"
        ],
        "full_step_array_digest": metadata["array_digest"],
        "unstable_warning_rows": unstable_warnings,
        "original_reward_gate_results_recomputed": original_gates,
    }
    passed = all(gate_results.values())
    decision_payload = {
        "candidate_id": metadata["candidate_id"],
        "gate_results": gate_results,
        "metrics": metrics,
    }
    return {
        "schema_version": verdict_schema,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "candidate_id": metadata["candidate_id"],
        "passed": passed,
        "gate_results": gate_results,
        "metrics": metrics,
        "gate_digest": canonical_digest(decision_payload),
        "verifier": {
            "path": str(
                (verifier_path or Path(__file__)).resolve().relative_to(REPO_ROOT)
            ),
            "sha256": sha256_file((verifier_path or Path(__file__)).resolve()),
            "ignored_producer_summary_booleans": True,
            "reconstructed_source_action_and_schedule": True,
        },
        "inputs": {
            "contract_path": str(contract_path.relative_to(REPO_ROOT)),
            "contract_sha256": sha256_file(contract_path),
            "trace_path": str(trace_path.relative_to(REPO_ROOT)),
            "trace_sha256": sha256_file(trace_path),
            "metadata_path": str(metadata_path.relative_to(REPO_ROOT)),
            "metadata_sha256": sha256_file(metadata_path),
        },
        "authority": contract["authority"],
        "claim_boundary": contract["claim_boundary"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    args = parser.parse_args(argv)
    verdict = verify_trace(
        trace_path=args.trace.resolve(),
        metadata_path=args.metadata.resolve(),
        contract_path=args.contract.resolve(),
    )
    atomic_write_json(args.output.resolve(), verdict)
    print(json.dumps({"candidate_id": verdict["candidate_id"], "passed": verdict["passed"], "gate_digest": verdict["gate_digest"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["IndependentVerifierError", "verify_trace"]
