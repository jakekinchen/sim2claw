"""Evaluator-owned comparison of current and calibrated SO-101 joint ranges.

Both MuJoCo variants receive the same contiguous float64 command tensor. The
baseline retains the current model's internal control limits. The candidate
changes only joint and actuator ranges to the endpoint ranges independently
declared by the hash-bound follower calibration. No external clipping,
resampling, action assistance, task scoring, or parameter promotion occurs.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import mujoco
import numpy as np

from .learning_factory_artifacts import (
    atomic_write_json,
    canonical_digest,
    sha256_file,
)
from .paths import REPO_ROOT
from .scene import CURRENT_TASK_PIECE_LAYOUT, ROBOT_JOINTS, build_scene_spec


CONTRACT_SCHEMA = "sim2claw.overnight_joint_limit_comparison_contract.v1"
RAW_SCHEMA = "sim2claw.joint_limit_comparison_raw.v1"
EVALUATION_SCHEMA = "sim2claw.joint_limit_comparison_evaluation.v1"
RECEIPT_SCHEMA = "sim2claw.joint_limit_comparison_receipt.v1"
DEFAULT_CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "overnight_joint_limit_comparison_v1.json"
)


class JointLimitComparisonError(RuntimeError):
    """A contract, identity, action, execution, or evaluator gate failed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise JointLimitComparisonError(message)


def _repo_path(value: str) -> Path:
    path = (REPO_ROOT / value).resolve()
    _require(path.is_relative_to(REPO_ROOT.resolve()), "Path escapes the repository.")
    return path


def _array_sha256(values: np.ndarray) -> str:
    _require(
        values.dtype == np.dtype("<f8") and values.flags.c_contiguous,
        "Action tensor must be contiguous little-endian float64.",
    )
    return hashlib.sha256(values.tobytes(order="C")).hexdigest()


def load_joint_limit_contract(
    path: Path = DEFAULT_CONTRACT_PATH,
) -> dict[str, Any]:
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise JointLimitComparisonError(
            f"Could not load joint-limit comparison contract: {error}"
        ) from error
    _require(isinstance(contract, dict), "Comparison contract must be an object.")
    _require(
        contract.get("schema_version") == CONTRACT_SCHEMA,
        "Unsupported joint-limit comparison contract.",
    )
    _require(
        contract.get("status") == "frozen_before_simulator_execution",
        "Joint-limit comparison is not frozen.",
    )
    simulator = contract.get("simulator")
    authority = contract.get("authority")
    _require(isinstance(simulator, dict), "Simulator contract is missing.")
    _require(isinstance(authority, dict), "Authority contract is missing.")
    _require(
        int(simulator.get("simulator_replays_maximum", -1)) == 2
        and int(simulator.get("candidate_families", -1)) == 1
        and int(simulator.get("adaptive_retries", -1)) == 0,
        "Simulator comparison budget changed.",
    )
    variants = simulator.get("variants")
    _require(
        isinstance(variants, list)
        and [row.get("id") for row in variants]
        == ["current_declared_ranges", "follower_calibrated_ranges_v1"],
        "Simulator variants changed.",
    )
    _require(
        simulator.get("action_tensor_must_be_byte_identical") is True
        and simulator.get("external_preclip_allowed") is False,
        "Action identity or preclip boundary changed.",
    )
    _require(
        all(value is False for value in authority.values()),
        "Joint-limit comparison widened authority.",
    )
    return contract


def _load_source(
    contract: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], np.ndarray, np.ndarray, np.ndarray]:
    source = contract["source"]
    recording_root = _repo_path(str(source["recording_directory"]))
    samples_path = recording_root / "samples.jsonl"
    _require(
        sha256_file(samples_path) == source["samples_sha256"],
        "Source sample bytes changed.",
    )
    diagnostic_path = _repo_path(str(source["derived_diagnostic"]))
    receipt_path = _repo_path(str(source["derived_receipt"]))
    _require(
        sha256_file(diagnostic_path) == source["derived_diagnostic_sha256"],
        "Derived diagnostic bytes changed.",
    )
    _require(
        sha256_file(receipt_path) == source["derived_receipt_sha256"],
        "Derived diagnostic receipt bytes changed.",
    )
    diagnostic = json.loads(diagnostic_path.read_text(encoding="utf-8"))
    _require(
        diagnostic.get("source_recording_id") == source["recording_id"],
        "Derived diagnostic binds another recording.",
    )
    rows = [
        json.loads(line)
        for line in samples_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    _require(len(rows) == int(source["action_shape"][0]), "Action row count changed.")
    try:
        actions = np.ascontiguousarray(
            [row[source["action_field"]] for row in rows], dtype="<f8"
        )
        actual = np.ascontiguousarray(
            [row["follower_actual_position_degrees"] for row in rows], dtype="<f8"
        )
        timestamps = np.asarray(
            [row["timestamp_monotonic_seconds"] for row in rows], dtype="<f8"
        )
    except (KeyError, TypeError, ValueError) as error:
        raise JointLimitComparisonError("Source action tensor is invalid.") from error
    expected_shape = tuple(int(value) for value in source["action_shape"])
    _require(
        actions.shape == expected_shape
        and actual.shape == expected_shape
        and bool(np.all(np.isfinite(actions)))
        and bool(np.all(np.isfinite(actual))),
        "Source action or actual tensor shape changed.",
    )
    _require(
        bool(np.all(np.diff(timestamps) > 0.0)),
        "Source timestamps are not strictly increasing.",
    )
    _require(
        _array_sha256(actions) == source["action_sha256"],
        "Exact source action tensor changed.",
    )
    return rows, actions, actual, timestamps


def _verify_calibration(contract: Mapping[str, Any]) -> dict[str, list[float]]:
    identity = contract["calibration_identity"]
    calibration_path = Path(str(identity["standard_path"])).expanduser().resolve()
    _require(calibration_path.is_file(), "Follower calibration file is unavailable.")
    _require(
        sha256_file(calibration_path) == identity["sha256"],
        "Follower calibration identity changed.",
    )
    calibration = json.loads(calibration_path.read_text(encoding="utf-8"))
    ranges = identity["frozen_range_counts"]
    resolution = float(identity["motor_resolution_counts"])
    derived: dict[str, list[float]] = {}
    for joint in ROBOT_JOINTS:
        observed = calibration.get(joint)
        expected = ranges[joint]
        _require(isinstance(observed, dict), f"Calibration is missing {joint}.")
        _require(
            [int(observed["range_min"]), int(observed["range_max"])] == expected,
            f"Calibration endpoint changed: {joint}.",
        )
        if joint == "gripper":
            continue
        half_range = (float(expected[1]) - float(expected[0])) * 180.0 / resolution
        derived[joint] = [-half_range, half_range]
        frozen = [float(value) for value in identity["derived_body_ranges_degrees"][joint]]
        _require(
            bool(np.allclose(derived[joint], frozen, atol=1e-12, rtol=0.0)),
            f"Derived calibration range changed: {joint}.",
        )
    return derived


def _model_binding(model: mujoco.MjModel) -> tuple[list[int], list[int], np.ndarray]:
    actuator_ids: list[int] = []
    joint_ids: list[int] = []
    qpos_addresses: list[int] = []
    for joint in ROBOT_JOINTS:
        name = f"left_{joint}"
        actuator_id = mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_ACTUATOR, name
        )
        joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        _require(
            actuator_id >= 0 and joint_id >= 0,
            f"Current simulator is missing {name}.",
        )
        actuator_ids.append(actuator_id)
        joint_ids.append(joint_id)
        qpos_addresses.append(int(model.jnt_qposadr[joint_id]))
    return actuator_ids, joint_ids, np.asarray(qpos_addresses, dtype=np.int32)


def _physical_to_sim(values: np.ndarray, gripper_bounds: np.ndarray) -> np.ndarray:
    _require(
        values.ndim == 2
        and values.shape[1] == len(ROBOT_JOINTS)
        and bool(np.all(np.isfinite(values))),
        "Physical tensor must be finite [N, 6].",
    )
    _require(
        bool(np.all((values[:, -1] >= 0.0) & (values[:, -1] <= 100.0))),
        "Gripper action is outside its exact 0-100 representation.",
    )
    converted = np.empty_like(values, dtype="<f8")
    converted[:, :-1] = np.deg2rad(values[:, :-1])
    converted[:, -1] = gripper_bounds[0] + (values[:, -1] / 100.0) * (
        gripper_bounds[1] - gripper_bounds[0]
    )
    return converted


def _apply_calibrated_ranges(
    model: mujoco.MjModel,
    actuator_ids: Sequence[int],
    joint_ids: Sequence[int],
    calibrated_ranges_degrees: Mapping[str, Sequence[float]],
) -> None:
    for index, joint in enumerate(ROBOT_JOINTS[:-1]):
        limits = np.deg2rad(
            np.asarray(calibrated_ranges_degrees[joint], dtype=np.float64)
        )
        model.jnt_range[joint_ids[index]] = limits
        model.actuator_ctrlrange[actuator_ids[index]] = limits


def _metrics(error: np.ndarray) -> dict[str, Any]:
    body_error_degrees = np.rad2deg(error[:, :-1])
    body_rmse = np.sqrt(np.mean(np.square(body_error_degrees), axis=0))
    gripper_rmse = float(np.sqrt(np.mean(np.square(error[:, -1]))))
    return {
        "body_joint_rmse_degrees": body_rmse.tolist(),
        "aggregate_body_joint_rmse_degrees": float(
            np.sqrt(np.mean(np.square(body_error_degrees)))
        ),
        "maximum_body_joint_error_degrees": float(
            np.max(np.abs(body_error_degrees))
        ),
        "gripper_rmse_actuator_rad": gripper_rmse,
    }


def _cycle_metrics(
    error: np.ndarray,
    diagnostic: Mapping[str, Any],
) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for cycle in diagnostic["segmentation"]["cycles"]:
        start = int(cycle["high_sample_index"])
        stop = int(cycle["low_sample_index"]) + 1
        summaries.append(
            {
                "cycle_id": int(cycle["cycle_id"]),
                **_metrics(error[start:stop]),
            }
        )
    return summaries


def _execute_variant(
    *,
    variant_id: str,
    actions: np.ndarray,
    actual: np.ndarray,
    timestamps: np.ndarray,
    calibrated_ranges_degrees: Mapping[str, Sequence[float]],
    mutate_ranges: bool,
    output_path: Path,
    diagnostic: Mapping[str, Any],
) -> dict[str, Any]:
    model = build_scene_spec(piece_layout=CURRENT_TASK_PIECE_LAYOUT).compile()
    actuator_ids, joint_ids, qpos_addresses = _model_binding(model)
    baseline_joint_ranges = model.jnt_range[joint_ids].astype(float).copy()
    baseline_ctrlranges = model.actuator_ctrlrange[actuator_ids].astype(float).copy()
    if mutate_ranges:
        _apply_calibrated_ranges(
            model, actuator_ids, joint_ids, calibrated_ranges_degrees
        )
    final_joint_ranges = model.jnt_range[joint_ids].astype(float).copy()
    final_ctrlranges = model.actuator_ctrlrange[actuator_ids].astype(float).copy()
    gripper_bounds = baseline_ctrlranges[-1]
    action_sim = _physical_to_sim(actions, gripper_bounds)
    actual_sim = _physical_to_sim(actual, gripper_bounds)
    data = mujoco.MjData(model)
    data.qpos[qpos_addresses] = actual_sim[0]
    data.ctrl[actuator_ids] = action_sim[0]
    mujoco.mj_forward(model, data)
    errors: list[np.ndarray] = []
    nominal_dt = float(np.median(np.diff(timestamps)))
    previous: float | None = None
    action_sha256 = _array_sha256(actions)
    with output_path.open("w", encoding="utf-8") as handle:
        for index in range(len(actions)):
            timestamp = float(timestamps[index])
            dt = nominal_dt if previous is None else timestamp - previous
            if not math.isfinite(dt) or dt <= 0.0 or dt > 1.0:
                dt = nominal_dt
            previous = timestamp
            raw_action = action_sim[index]
            data.ctrl[actuator_ids] = raw_action
            steps = max(1, round(dt / float(model.opt.timestep)))
            mujoco.mj_step(model, data, nstep=steps)
            simulated = data.qpos[qpos_addresses].astype(float)
            error = simulated - actual_sim[index]
            errors.append(error.copy())
            handle.write(
                json.dumps(
                    {
                        "schema_version": RAW_SCHEMA,
                        "variant_id": variant_id,
                        "sample_index": index,
                        "source_timestamp_seconds": timestamp,
                        "dt_seconds": dt,
                        "input_action_sim_units": raw_action.tolist(),
                        "input_action_sha256": action_sha256,
                        "simulated_position": simulated.tolist(),
                        "physical_actual_sim_units": actual_sim[index].tolist(),
                        "sim_minus_physical_error": error.tolist(),
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                )
                + "\n"
            )
    error_array = np.asarray(errors, dtype="<f8")
    return {
        "variant_id": variant_id,
        "range_mutation": mutate_ranges,
        "input_action_sha256": action_sha256,
        "input_action_shape": list(actions.shape),
        "input_action_dtype": "float64",
        "external_preclip_applied": False,
        "simulator_engine_internal_control_limits_active": True,
        "baseline_joint_ranges_rad": baseline_joint_ranges.tolist(),
        "baseline_actuator_ctrlranges_rad": baseline_ctrlranges.tolist(),
        "executed_joint_ranges_rad": final_joint_ranges.tolist(),
        "executed_actuator_ctrlranges_rad": final_ctrlranges.tolist(),
        "raw_trace_path": output_path.name,
        "raw_trace_sha256": sha256_file(output_path),
        "sample_count": len(actions),
        "metrics": _metrics(error_array),
        "cycle_metrics": _cycle_metrics(error_array, diagnostic),
    }


def _evaluate(
    baseline: Mapping[str, Any],
    candidate: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    gates = contract["evaluation"]
    baseline_metrics = baseline["metrics"]
    candidate_metrics = candidate["metrics"]
    baseline_rmse = float(baseline_metrics["aggregate_body_joint_rmse_degrees"])
    candidate_rmse = float(candidate_metrics["aggregate_body_joint_rmse_degrees"])
    improvement = (
        (baseline_rmse - candidate_rmse) / baseline_rmse
        if baseline_rmse > 0.0
        else 0.0
    )
    per_joint_regressions = (
        np.asarray(candidate_metrics["body_joint_rmse_degrees"], dtype=float)
        - np.asarray(baseline_metrics["body_joint_rmse_degrees"], dtype=float)
    )
    action_identical = (
        baseline["input_action_sha256"] == candidate["input_action_sha256"]
        and baseline["input_action_shape"] == candidate["input_action_shape"]
        and baseline["input_action_dtype"] == candidate["input_action_dtype"]
    )
    aggregate_gate = improvement >= float(
        gates["aggregate_body_joint_rmse_improvement_minimum_fraction"]
    )
    joint_gate = bool(
        np.all(
            per_joint_regressions
            <= float(gates["maximum_per_joint_rmse_regression_degrees"])
        )
    )
    gripper_gate = float(candidate_metrics["gripper_rmse_actuator_rad"]) <= float(
        baseline_metrics["gripper_rmse_actuator_rad"]
    ) + 1e-12
    diagnostic_gain = action_identical and aggregate_gate and joint_gate and gripper_gate
    return {
        "schema_version": EVALUATION_SCHEMA,
        "evaluator_owner": gates["owner"],
        "action_tensor_byte_identical": action_identical,
        "baseline_aggregate_body_joint_rmse_degrees": baseline_rmse,
        "candidate_aggregate_body_joint_rmse_degrees": candidate_rmse,
        "aggregate_body_joint_rmse_improvement_fraction": improvement,
        "per_joint_rmse_regression_degrees": per_joint_regressions.tolist(),
        "baseline_gripper_rmse_actuator_rad": float(
            baseline_metrics["gripper_rmse_actuator_rad"]
        ),
        "candidate_gripper_rmse_actuator_rad": float(
            candidate_metrics["gripper_rmse_actuator_rad"]
        ),
        "gates": {
            "action_identity": action_identical,
            "aggregate_body_improvement": aggregate_gate,
            "per_joint_nonregression": joint_gate,
            "gripper_nonregression": gripper_gate,
            "strict_task_consequence": False,
        },
        "diagnostic_gain": diagnostic_gain,
        "simulator_parameter_promoted": False,
        "task_score_changed": False,
        "verdict": (
            "diagnostic_joint_range_gain_no_promotion"
            if diagnostic_gain
            else "diagnostic_joint_range_tie_or_loss_no_promotion"
        ),
        "claim_boundary": (
            "Calibration-endpoint joint ranges are evaluated only as an "
            "action-identical current-workcell joint-response diagnostic; "
            "strict task consequence is unavailable, so no simulator or "
            "task-score promotion is permitted."
        ),
    }


def run_joint_limit_comparison(
    output_root: Path,
    *,
    contract_path: Path = DEFAULT_CONTRACT_PATH,
) -> dict[str, Any]:
    """Execute the single frozen two-variant simulator comparison once."""

    contract = load_joint_limit_contract(contract_path)
    _require(
        not output_root.exists() or not any(output_root.iterdir()),
        "Comparison output root is not empty; replay/overwrite is refused.",
    )
    output_root.mkdir(parents=True, exist_ok=True)
    scene_path = _repo_path(str(contract["simulator"]["scene_source"]))
    _require(
        sha256_file(scene_path) == contract["simulator"]["scene_source_sha256"],
        "Simulator scene implementation changed.",
    )
    _, actions, actual, timestamps = _load_source(contract)
    calibrated_ranges = _verify_calibration(contract)
    diagnostic = json.loads(
        _repo_path(str(contract["source"]["derived_diagnostic"])).read_text(
            encoding="utf-8"
        )
    )
    baseline = _execute_variant(
        variant_id="current_declared_ranges",
        actions=actions,
        actual=actual,
        timestamps=timestamps,
        calibrated_ranges_degrees=calibrated_ranges,
        mutate_ranges=False,
        output_path=output_root / "current_declared_ranges.jsonl",
        diagnostic=diagnostic,
    )
    candidate = _execute_variant(
        variant_id="follower_calibrated_ranges_v1",
        actions=actions,
        actual=actual,
        timestamps=timestamps,
        calibrated_ranges_degrees=calibrated_ranges,
        mutate_ranges=True,
        output_path=output_root / "follower_calibrated_ranges_v1.jsonl",
        diagnostic=diagnostic,
    )
    evaluation = _evaluate(baseline, candidate, contract)
    raw = {
        "schema_version": RAW_SCHEMA,
        "comparison_id": contract["comparison_id"],
        "source_recording_id": contract["source"]["recording_id"],
        "source_samples_sha256": contract["source"]["samples_sha256"],
        "exact_action_sha256": contract["source"]["action_sha256"],
        "simulator_replays_used": 2,
        "simulator_replays_maximum": 2,
        "adaptive_retries": 0,
        "variants": [baseline, candidate],
        "calibration_identity": copy.deepcopy(contract["calibration_identity"]),
        "authority": copy.deepcopy(contract["authority"]),
    }
    raw_path = output_root / "raw_comparison.json"
    evaluation_path = output_root / "evaluation.json"
    atomic_write_json(raw_path, raw)
    atomic_write_json(evaluation_path, evaluation)
    unsigned_receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "contract_path": str(contract_path.resolve()),
        "contract_sha256": sha256_file(contract_path),
        "source_recording_id": contract["source"]["recording_id"],
        "source_samples_sha256": contract["source"]["samples_sha256"],
        "exact_action_sha256": contract["source"]["action_sha256"],
        "raw_comparison_sha256": sha256_file(raw_path),
        "evaluation_sha256": sha256_file(evaluation_path),
        "simulator_replays_used": 2,
        "adaptive_retries": 0,
        "proof_class": "action_frozen_simulator_joint_range_diagnostic",
        "verdict": evaluation["verdict"],
        "simulator_parameter_promoted": False,
        "task_score_changed": False,
        "authority": copy.deepcopy(contract["authority"]),
    }
    receipt = {
        **unsigned_receipt,
        "receipt_sha256": canonical_digest(unsigned_receipt),
    }
    atomic_write_json(output_root / "receipt.json", receipt)
    return receipt


__all__ = [
    "CONTRACT_SCHEMA",
    "DEFAULT_CONTRACT_PATH",
    "EVALUATION_SCHEMA",
    "JointLimitComparisonError",
    "RAW_SCHEMA",
    "RECEIPT_SCHEMA",
    "load_joint_limit_contract",
    "run_joint_limit_comparison",
]
