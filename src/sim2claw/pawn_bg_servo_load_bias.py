"""Cross-validated action-frozen servo deadband and elbow load-bias ablation."""

from __future__ import annotations

import itertools
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import mujoco
import numpy as np

from .grasp import _pinch_point
from .learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .paths import REPO_ROOT
from .pawn_bg_action_frozen_gap import _array_sha256, _load_partition, _reconstruct_stage_d
from .pawn_bg_demo_sim import BASELINE_PIECE_BY_FILE, _piece_bodies, _trace_row
from .pawn_bg_reward import load_reward_contract, score_episode
from .pawn_bg_timing_ablation import (
    BODY_JOINT_NAMES,
    _episode_metrics,
    _mapped_episode,
    _pool,
    _strip_arrays,
    _write_episode_trace,
)
from .pawn_bg_workcell_fit import _workcell_square_center, build_workcell_model


CONTRACT_PATH = REPO_ROOT / "configs" / "sysid" / "pawn_bg_servo_load_bias_v1.json"
SCHEMA = "sim2claw.pawn_bg_servo_load_bias.v1"
RECEIPT_SCHEMA = "sim2claw.pawn_bg_servo_load_bias_receipt.v1"
TARGET_JOINTS = ("shoulder_lift", "elbow_flex")


class ServoLoadBiasError(RuntimeError):
    """The load-bias experiment violates its frozen evidence boundary."""


def load_servo_load_bias_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ServoLoadBiasError(f"cannot read load-bias contract {path}: {error}") from error
    if contract.get("schema_version") != SCHEMA:
        raise ServoLoadBiasError("unexpected servo load-bias contract schema")
    if any(contract.get("authority", {}).values()):
        raise ServoLoadBiasError("load-bias authority widened")
    if not all(contract.get("action_invariance", {}).values()):
        raise ServoLoadBiasError("action invariance is not fail closed")
    grid = contract["candidate_grid"]
    coefficients = [float(value) for value in grid["elbow_load_bias_coefficient"]]
    if coefficients != sorted(set(coefficients)) or coefficients[-1] != 0.0:
        raise ServoLoadBiasError("load-bias coefficient grid is invalid")
    if coefficients[0] < -1.5:
        raise ServoLoadBiasError("load-bias coefficient bound widened")
    members = [
        str(recording_id)
        for fold in contract["grouped_cross_validation"]["folds"]
        for recording_id in fold
    ]
    if len(members) != 11 or len(set(members)) != 11:
        raise ServoLoadBiasError("grouped CV folds must cover 11 unique episodes")
    return contract


def _candidate_id(candidate: dict[str, float]) -> str:
    lift = int(round(candidate["shoulder_lift_deadband_degrees"] * 1000))
    elbow = int(round(candidate["elbow_flex_deadband_degrees"] * 1000))
    coefficient = int(round(candidate["elbow_load_bias_coefficient"] * 1000))
    return f"lift{lift:04d}_elbow{elbow:04d}_bias{coefficient:+05d}"


def _candidate_grid(contract: dict[str, Any]) -> list[dict[str, float]]:
    grid = contract["candidate_grid"]
    return [
        {
            "shoulder_lift_deadband_degrees": float(lift),
            "elbow_flex_deadband_degrees": float(elbow),
            "elbow_load_bias_coefficient": float(coefficient),
        }
        for lift, elbow, coefficient in itertools.product(
            grid["shoulder_lift_deadband_degrees"],
            grid["elbow_flex_deadband_degrees"],
            grid["elbow_load_bias_coefficient"],
        )
    ]


def _baseline_candidate(contract: dict[str, Any]) -> dict[str, float]:
    baseline = contract["source"]["baseline_deadband_degrees"]
    return {
        "shoulder_lift_deadband_degrees": float(baseline["shoulder_lift"]),
        "elbow_flex_deadband_degrees": float(baseline["elbow_flex"]),
        "elbow_load_bias_coefficient": 0.0,
    }


def _replay(
    mapped: dict[str, Any],
    workcell: Any,
    experiment: dict[str, Any],
    candidate: dict[str, float],
) -> tuple[np.ndarray, dict[str, Any], dict[str, float | int]]:
    binding = build_workcell_model(workcell)
    model, data = binding["model"], binding["data"]
    actuator_ids = binding["actuator_ids"]
    qpos_addresses = binding["qpos_addresses"]
    dof_addresses = [int(model.jnt_dofadr[joint_id]) for joint_id in binding["joint_ids"]]
    data.qpos[qpos_addresses] = mapped["measured"][0]
    data.ctrl[actuator_ids] = mapped["measured"][0]
    mujoco.mj_forward(model, data)
    settle_steps = int(experiment["candidate_grid"]["initial_settle_steps"])
    if settle_steps:
        mujoco.mj_step(model, data, nstep=settle_steps)
    nominal_gain = model.actuator_gainprm[:, 0].copy()
    nominal_bias = model.actuator_biasprm[:, 1].copy()
    times = mapped["timestamps"]
    actions = mapped["actions"]
    outputs = np.empty_like(mapped["measured"])
    timestep = float(model.opt.timestep)
    delay = float(experiment["source"]["required_application_delay_seconds"])
    transitions: list[list[float | int]] = []
    last_source_index: int | None = None
    active_steps = 0
    applied_values: list[float] = []
    for row_index, timestamp in enumerate(times):
        outputs[row_index] = data.qpos[qpos_addresses]
        if row_index == len(times) - 1:
            break
        interval = float(times[row_index + 1] - timestamp)
        for step in range(max(1, round(interval / timestep))):
            now = float(timestamp) + step * timestep
            source_index = max(
                0, int(np.searchsorted(times, now - delay, side="right") - 1)
            )
            if source_index != last_source_index:
                transitions.append([now, source_index])
                last_source_index = source_index
            action = actions[source_index]
            data.ctrl[actuator_ids] = action
            data.qfrc_applied[dof_addresses] = 0.0
            for joint_name, deadband_key in (
                ("shoulder_lift", "shoulder_lift_deadband_degrees"),
                ("elbow_flex", "elbow_flex_deadband_degrees"),
            ):
                joint_index = BODY_JOINT_NAMES.index(joint_name)
                actuator_id = actuator_ids[joint_index]
                inactive = abs(
                    float(action[joint_index] - data.qpos[qpos_addresses[joint_index]])
                ) <= math.radians(float(candidate[deadband_key]))
                scale = 0.0 if inactive else 1.0
                model.actuator_gainprm[actuator_id, 0] = nominal_gain[actuator_id] * scale
                model.actuator_biasprm[actuator_id, 1] = nominal_bias[actuator_id] * scale
                if joint_name == "elbow_flex" and inactive:
                    value = float(candidate["elbow_load_bias_coefficient"]) * float(
                        data.qfrc_bias[dof_addresses[joint_index]]
                    )
                    data.qfrc_applied[dof_addresses[joint_index]] = value
                    active_steps += 1
                    applied_values.append(value)
            mujoco.mj_step(model, data)
    schedule = {
        "semantics": "record_at_timestamp_then_apply_zoh_with_deadband_conditioned_elbow_load_bias",
        "application_delay_seconds": delay,
        "candidate": candidate,
        "source_index_transitions": transitions,
    }
    schedule["sha256"] = canonical_digest(schedule)
    torque = {
        "active_physics_steps": active_steps,
        "mean_applied_torque": float(np.mean(applied_values)) if applied_values else 0.0,
        "mean_absolute_applied_torque": float(np.mean(np.abs(applied_values))) if applied_values else 0.0,
        "maximum_absolute_applied_torque": float(np.max(np.abs(applied_values))) if applied_values else 0.0,
    }
    return outputs, schedule, torque


def _evaluate_partition(
    payloads: list[tuple[dict[str, Any], str, str, list[dict[str, Any]]]],
    workcell: Any,
    contract: dict[str, Any],
    candidates: list[dict[str, float]],
) -> tuple[
    dict[str, dict[str, dict[str, Any]]],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
]:
    results: dict[str, dict[str, dict[str, Any]]] = {}
    mapped_by_id: dict[str, dict[str, Any]] = {}
    schedules: dict[str, dict[str, Any]] = {}
    torques: dict[str, dict[str, Any]] = {}
    for payload in payloads:
        mapped = _mapped_episode(payload, workcell)
        recording_id = str(mapped["episode"]["recording_id"])
        mapped_by_id[recording_id] = mapped
        results[recording_id] = {}
        schedules[recording_id] = {}
        torques[recording_id] = {}
        for candidate in candidates:
            key = _candidate_id(candidate)
            states, schedule, torque = _replay(mapped, workcell, contract, candidate)
            results[recording_id][key] = _episode_metrics(
                mapped, states, workcell, contract
            )
            schedules[recording_id][key] = schedule
            torques[recording_id][key] = torque
    return results, mapped_by_id, schedules, torques


def _pooled(
    results: dict[str, dict[str, dict[str, Any]]],
    recording_ids: Iterable[str],
    candidate: dict[str, float],
) -> dict[str, Any]:
    key = _candidate_id(candidate)
    return _pool(results[recording_id][key] for recording_id in recording_ids)


def _row(
    results: dict[str, dict[str, dict[str, Any]]],
    ids: Iterable[str],
    candidate: dict[str, float],
) -> dict[str, Any]:
    return {
        "candidate_id": _candidate_id(candidate),
        "candidate": candidate,
        **_pooled(results, ids, candidate),
    }


def _eligible(
    row: dict[str, Any], baseline: dict[str, Any], contract: dict[str, Any]
) -> bool:
    acceptance = contract["acceptance"]
    minimum_stall = float(
        acceptance["fit_minimum_stall_reproduction_fraction_per_target_joint"]
    )
    ee_limit = float(acceptance["fit_maximum_ee_rms_relative_to_current_baseline"])
    return bool(
        row["ee_rms_m"] <= baseline["ee_rms_m"] * ee_limit
        and all(
            row["stall_reproduction_fraction"][name] >= minimum_stall
            for name in TARGET_JOINTS
        )
    )


def _select(
    rows: list[dict[str, Any]], baseline: dict[str, Any], contract: dict[str, Any]
) -> dict[str, Any]:
    eligible = [row for row in rows if _eligible(row, baseline, contract)]
    if not eligible:
        raise ServoLoadBiasError("no load-bias candidate satisfies fit constraints")
    return min(
        eligible,
        key=lambda row: (
            row["overall_joint_rms_degrees"],
            row["ee_rms_m"],
            row["candidate_id"],
        ),
    )


def _consequence_episode(
    *,
    mapped: dict[str, Any],
    workcell: Any,
    contract: dict[str, Any],
    candidate: dict[str, float],
    reward_contract: dict[str, Any],
) -> dict[str, Any]:
    binding = build_workcell_model(workcell)
    model, data = binding["model"], binding["data"]
    actuator_ids = binding["actuator_ids"]
    qpos_addresses = binding["qpos_addresses"]
    dof_addresses = [int(model.jnt_dofadr[joint_id]) for joint_id in binding["joint_ids"]]
    source, destination = str(mapped["source"]), str(mapped["destination"])
    selected_name = BASELINE_PIECE_BY_FILE[source[0]]
    selected_body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, selected_name)
    selected_joint = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, f"{selected_name}_free")
    if selected_body < 0 or selected_joint < 0:
        raise ServoLoadBiasError("selected pawn is missing from consequence replay")
    selected_qpos = int(model.jnt_qposadr[selected_joint])
    selected_dof = int(model.jnt_dofadr[selected_joint])
    source_xyz = np.asarray(
        _workcell_square_center(
            source,
            board_center_in_table_frame_xy_m=workcell.board_center_in_table_frame_xy_m,
            board_yaw_relative_to_table_degrees=workcell.board_yaw_relative_to_table_degrees,
            board_side_m=workcell.board_side_m,
        ),
        dtype=np.float64,
    )
    data.qpos[selected_qpos : selected_qpos + 3] = source_xyz
    data.qvel[selected_dof : selected_dof + 6] = 0.0
    data.qpos[qpos_addresses] = mapped["measured"][0]
    data.ctrl[actuator_ids] = mapped["measured"][0]
    mujoco.mj_forward(model, data)
    mujoco.mj_step(model, data, nstep=int(contract["candidate_grid"]["initial_settle_steps"]))
    piece_bodies = _piece_bodies(model)
    initial_positions = {
        name: np.asarray(data.xpos[body_id], dtype=np.float64).copy()
        for name, body_id in piece_bodies.items()
    }
    initial_height = float(data.xpos[selected_body][2])
    robot_body_ids = {
        body_id
        for body_id in range(model.nbody)
        if (mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id) or "").startswith("left_")
    }
    fixed_geom = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "left_fixed_jaw_box1")
    jaw_body_ids = {
        int(model.geom_bodyid[fixed_geom]),
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "left_moving_jaw_so101_v1"),
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

    nominal_gain = model.actuator_gainprm[:, 0].copy()
    nominal_bias = model.actuator_biasprm[:, 1].copy()

    def apply_response(action: np.ndarray) -> None:
        data.ctrl[actuator_ids] = action
        data.qfrc_applied[dof_addresses] = 0.0
        for joint_name, deadband_key in (
            ("shoulder_lift", "shoulder_lift_deadband_degrees"),
            ("elbow_flex", "elbow_flex_deadband_degrees"),
        ):
            index = BODY_JOINT_NAMES.index(joint_name)
            actuator_id = actuator_ids[index]
            inactive = abs(float(action[index] - data.qpos[qpos_addresses[index]])) <= math.radians(
                float(candidate[deadband_key])
            )
            scale = 0.0 if inactive else 1.0
            model.actuator_gainprm[actuator_id, 0] = nominal_gain[actuator_id] * scale
            model.actuator_biasprm[actuator_id, 1] = nominal_bias[actuator_id] * scale
            if joint_name == "elbow_flex" and inactive:
                data.qfrc_applied[dof_addresses[index]] = float(
                    candidate["elbow_load_bias_coefficient"]
                ) * float(data.qfrc_bias[dof_addresses[index]])

    pinch_local = binding["pinch_offset_local"]

    def pinch_distance() -> float:
        return float(
            np.linalg.norm(
                _pinch_point(model, data, "left", pinch_local)
                - np.asarray(data.xpos[selected_body])
            )
        )

    trace = [trace_row()]
    minimum_pinch = pinch_distance()
    actions, times = mapped["actions"], mapped["timestamps"]
    timestep = float(model.opt.timestep)
    delay = float(contract["source"]["required_application_delay_seconds"])
    for row_index, timestamp in enumerate(times[:-1]):
        interval = float(times[row_index + 1] - timestamp)
        for step in range(max(1, round(interval / timestep))):
            now = float(timestamp) + step * timestep
            source_index = max(
                0, int(np.searchsorted(times, now - delay, side="right") - 1)
            )
            apply_response(actions[source_index])
            mujoco.mj_step(model, data)
            minimum_pinch = min(minimum_pinch, pinch_distance())
        trace.append(trace_row())
    final_index = max(
        0, int(np.searchsorted(times, float(times[-1]) - delay, side="right") - 1)
    )
    apply_response(actions[final_index])
    for _ in range(200):
        apply_response(np.asarray(data.ctrl[actuator_ids], dtype=np.float64))
        mujoco.mj_step(model, data)
        minimum_pinch = min(minimum_pinch, pinch_distance())
    trace.append(trace_row())
    target_xyz = _workcell_square_center(
        destination,
        board_center_in_table_frame_xy_m=workcell.board_center_in_table_frame_xy_m,
        board_yaw_relative_to_table_degrees=workcell.board_yaw_relative_to_table_degrees,
        board_side_m=workcell.board_side_m,
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
        "candidate": candidate,
        "action_sha256": mapped["action_receipt"]["sha256"],
        "clipped_action_rows": 0,
        "minimum_pinch_to_selected_piece_m": minimum_pinch,
        "selected_piece_contact_observed": bool(score["gate_results"]["selected_piece_contact_observed"]),
        "piece_lifted": bool(score["gate_results"]["piece_lifted"]),
        "whole_base_inside_destination": bool(score["gate_results"]["whole_base_inside_destination"]),
        "released": bool(score["gate_results"]["released"]),
        "maximum_piece_rise_m": float(score["maximum_piece_rise_m"]),
        "final_target_distance_m": float(score["final_center_distance_m"]),
        "task_consequence_success": bool(score["task_consequence_success"]),
    }


def _consequence_summary(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    materialized = list(rows)
    return {
        "episode_count": len(materialized),
        "selected_piece_contact": sum(int(row["selected_piece_contact_observed"]) for row in materialized),
        "lifted": sum(int(row["piece_lifted"]) for row in materialized),
        "whole_base_inside_destination": sum(int(row["whole_base_inside_destination"]) for row in materialized),
        "released": sum(int(row["released"]) for row in materialized),
        "task_consequence_successes": sum(int(row["task_consequence_success"]) for row in materialized),
        "mean_minimum_pinch_to_selected_piece_m": float(np.mean([row["minimum_pinch_to_selected_piece_m"] for row in materialized])),
        "mean_maximum_piece_rise_m": float(np.mean([row["maximum_piece_rise_m"] for row in materialized])),
        "mean_final_target_distance_m": float(np.mean([row["final_target_distance_m"] for row in materialized])),
    }


def run_servo_load_bias_ablation(
    *, source_repository_root: Path, output_root: Path, contract_path: Path = CONTRACT_PATH
) -> dict[str, Any]:
    contract = load_servo_load_bias_contract(contract_path)
    upstream_path = source_repository_root / contract["source"]["upstream_deadband_receipt"]
    upstream = json.loads(upstream_path.read_text(encoding="utf-8"))
    if abs(float(upstream["selected_train_metrics"]["overall_joint_rms_degrees"]) - float(contract["source"]["baseline_joint_rms_degrees"])) > 1e-12:
        raise ServoLoadBiasError("upstream joint RMS baseline changed")
    if abs(float(upstream["selected_train_metrics"]["ee_rms_m"]) - float(contract["source"]["baseline_ee_rms_m"])) > 1e-12:
        raise ServoLoadBiasError("upstream EE RMS baseline changed")
    train_payloads, events = _load_partition(source_repository_root, "train")
    confirmation_payloads, _ = _load_partition(source_repository_root, "held_out")
    if len(train_payloads) != int(contract["source"]["expected_train_episode_count"]):
        raise ServoLoadBiasError("train episode inventory changed")
    if len(confirmation_payloads) != int(contract["source"]["expected_already_opened_confirmation_episode_count"]):
        raise ServoLoadBiasError("confirmation episode inventory changed")
    _parent, workcell, stage_d_parameters, _details = _reconstruct_stage_d(train_payloads, events)
    baseline_candidate = _baseline_candidate(contract)
    candidates = _candidate_grid(contract)
    evaluated = [baseline_candidate, *[candidate for candidate in candidates if candidate != baseline_candidate]]
    results, mapped_train, schedules, torques = _evaluate_partition(
        train_payloads, workcell, contract, evaluated
    )
    train_ids = sorted(results)
    baseline = _row(results, train_ids, baseline_candidate)
    rows = [_row(results, train_ids, candidate) for candidate in candidates]
    selected = _select(rows, baseline, contract)
    selected_candidate = selected["candidate"]
    folds = [list(map(str, fold)) for fold in contract["grouped_cross_validation"]["folds"]]
    if {recording_id for fold in folds for recording_id in fold} != set(train_ids):
        raise ServoLoadBiasError("CV fold identities differ from train episodes")
    cv_rows = []
    cv_selected_metrics = []
    for fold_index, validation_ids in enumerate(folds):
        fit_ids = [recording_id for recording_id in train_ids if recording_id not in validation_ids]
        fit_baseline = _row(results, fit_ids, baseline_candidate)
        fit_rows = [_row(results, fit_ids, candidate) for candidate in candidates]
        fold_selected = _select(fit_rows, fit_baseline, contract)
        validation_baseline = _row(results, validation_ids, baseline_candidate)
        validation_candidate = _row(results, validation_ids, fold_selected["candidate"])
        cv_selected_metrics.extend(
            results[recording_id][fold_selected["candidate_id"]]
            for recording_id in validation_ids
        )
        improvement = float(
            (validation_baseline["overall_joint_rms_degrees"] - validation_candidate["overall_joint_rms_degrees"])
            / validation_baseline["overall_joint_rms_degrees"]
        )
        cv_rows.append(
            {
                "fold_index": fold_index,
                "fit_episode_ids": fit_ids,
                "validation_episode_ids": validation_ids,
                "selected_candidate": fold_selected["candidate"],
                "selected_candidate_id": fold_selected["candidate_id"],
                "fit_baseline": fit_baseline,
                "fit_candidate": fold_selected,
                "validation_baseline": validation_baseline,
                "validation_candidate": validation_candidate,
                "validation_joint_rms_relative_improvement": improvement,
            }
        )
    cv_baseline = _pool(
        results[recording_id][_candidate_id(baseline_candidate)]
        for fold in folds for recording_id in fold
    )
    cv_candidate = _pool(cv_selected_metrics)
    cv_improvement = float(
        (cv_baseline["overall_joint_rms_degrees"] - cv_candidate["overall_joint_rms_degrees"])
        / cv_baseline["overall_joint_rms_degrees"]
    )
    acceptance = contract["acceptance"]
    action_invariant = all(
        mapped["action_receipt"]["sha256"] == _array_sha256(mapped["actions"])
        for mapped in mapped_train.values()
    )
    rms_gates = {
        "action_invariance_gate": action_invariant,
        "cross_validated_joint_rms_significance_gate": cv_improvement >= float(acceptance["minimum_cross_validated_joint_rms_relative_improvement"]),
        "cross_validated_ee_non_regression_gate": cv_candidate["ee_rms_m"] <= float(acceptance["maximum_cross_validated_ee_rms_m"]),
        "cross_validated_target_stall_gate": all(
            cv_candidate["stall_reproduction_fraction"][name]
            >= float(acceptance["minimum_cross_validated_stall_reproduction_fraction_per_target_joint"])
            for name in TARGET_JOINTS
        ),
        "all_validation_folds_improve_gate": all(row["validation_joint_rms_relative_improvement"] > 0.0 for row in cv_rows),
    }
    rms_advancement = all(rms_gates.values())

    reward_contract = load_reward_contract()
    consequences: dict[str, list[dict[str, Any]]] = {"current_baseline": [], "selected_load_bias": []}
    for recording_id in train_ids:
        mapped = mapped_train[recording_id]
        consequences["current_baseline"].append(
            _consequence_episode(mapped=mapped, workcell=workcell, contract=contract, candidate=baseline_candidate, reward_contract=reward_contract)
        )
        consequences["selected_load_bias"].append(
            _consequence_episode(mapped=mapped, workcell=workcell, contract=contract, candidate=selected_candidate, reward_contract=reward_contract)
        )
    consequence_receipt = {
        name: {"summary": _consequence_summary(value), "episodes": value}
        for name, value in consequences.items()
    }
    selected_summary = consequence_receipt["selected_load_bias"]["summary"]
    significance = acceptance["consequence_significance"]
    consequence_advancement = bool(
        selected_summary["task_consequence_successes"] >= int(significance["minimum_strict_successes"])
    )

    confirmation_results, mapped_confirmation, confirmation_schedules, confirmation_torques = _evaluate_partition(
        confirmation_payloads, workcell, contract, [baseline_candidate, selected_candidate]
    )
    confirmation_ids = sorted(confirmation_results)
    confirmation = {
        "selection_use": "none_already_opened_regression_only",
        "baseline": _row(confirmation_results, confirmation_ids, baseline_candidate),
        "selected": _row(confirmation_results, confirmation_ids, selected_candidate),
    }

    traces = []
    selected_key = _candidate_id(selected_candidate)
    baseline_key = _candidate_id(baseline_candidate)
    for recording_id in train_ids:
        path = output_root.resolve() / "traces" / f"{recording_id}.json"
        variants = {
            "current_baseline": results[recording_id][baseline_key],
            "selected_load_bias": results[recording_id][selected_key],
        }
        digest = _write_episode_trace(mapped=mapped_train[recording_id], variants=variants, output_path=path)
        traces.append(
            {
                "recording_id": recording_id,
                "action": mapped_train[recording_id]["action_receipt"],
                "trace_path": str(path),
                "trace_sha256": digest,
                "schedules": {
                    "current_baseline": schedules[recording_id][baseline_key],
                    "selected_load_bias": schedules[recording_id][selected_key],
                },
                "load_bias_torque": {
                    "current_baseline": torques[recording_id][baseline_key],
                    "selected_load_bias": torques[recording_id][selected_key],
                },
                "metrics": {name: _strip_arrays(metrics) for name, metrics in variants.items()},
            }
        )

    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "proof_class": "action_frozen_simulator_servo_load_bias_diagnostic",
        "contract": {"path": str(contract_path.resolve()), "sha256": sha256_file(contract_path)},
        "implementation": {"path": str(Path(__file__).resolve()), "sha256": sha256_file(Path(__file__).resolve())},
        "upstream_deadband_receipt": {"path": str(upstream_path.resolve()), "sha256": sha256_file(upstream_path)},
        "stage_d_parameters": stage_d_parameters,
        "residual_hypothesis": contract["residual_hypothesis"],
        "action_arrays_byte_identical_across_variants": action_invariant,
        "baseline": baseline,
        "candidate_count": len(candidates),
        "candidate_grid": rows,
        "selected_candidate": selected_candidate,
        "selected_candidate_id": selected["candidate_id"],
        "selected_train_metrics": selected,
        "grouped_cross_validation": {
            "folds": cv_rows,
            "pooled_baseline": cv_baseline,
            "pooled_candidate": cv_candidate,
            "pooled_joint_rms_relative_improvement": cv_improvement,
        },
        "advancement_gates": {
            "rms": rms_gates,
            "verified_significant_rms_advancement": rms_advancement,
            "verified_significant_consequence_advancement": consequence_advancement,
            "verified_significant_advancement": rms_advancement or consequence_advancement,
        },
        "action_frozen_consequence_replay": consequence_receipt,
        "already_opened_confirmation": confirmation,
        "confirmation_action_hashes": {recording_id: mapped["action_receipt"] for recording_id, mapped in mapped_confirmation.items()},
        "confirmation_schedules": confirmation_schedules,
        "confirmation_load_bias_torque": confirmation_torques,
        "traces": traces,
        "authority": contract["authority"],
        "claim_boundary": (
            "A passing result verifies an action-frozen simulator trace-fidelity advancement only. "
            "The load-bias coefficient is not physical torque, firmware, gravity compensation, "
            "contact calibration, policy improvement, composite simulator promotion, or transfer."
        ),
    }
    receipt["receipt_digest"] = canonical_digest(receipt)
    atomic_write_json(output_root.resolve() / "servo_load_bias_receipt.json", receipt)
    return receipt
