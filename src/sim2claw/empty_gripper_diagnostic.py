"""Deterministic, non-promoting evaluation of an empty-gripper observation.

The evaluator verifies immutable source bytes, segments every observed
close/open excursion, reports timing/current/tracking diagnostics, and checks
whether the exact float64 command tensor is admissible to the current
simulator. It never rewrites the raw recording, silently drops a cycle, clips
an action, executes robot motion, or promotes a simulator parameter.
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


CONTRACT_SCHEMA = "sim2claw.overnight_empty_gripper_diagnostic_contract.v1"
DIAGNOSTIC_SCHEMA = "sim2claw.empty_gripper_cycle_diagnostic.v1"
RECEIPT_SCHEMA = "sim2claw.empty_gripper_cycle_diagnostic_receipt.v1"
DEFAULT_CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "overnight_empty_gripper_diagnostic_v1.json"
)


class EmptyGripperDiagnosticError(RuntimeError):
    """A source-integrity, schema, or evaluator boundary failed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise EmptyGripperDiagnosticError(message)


def _repo_path(value: str) -> Path:
    path = (REPO_ROOT / value).resolve()
    _require(path.is_relative_to(REPO_ROOT.resolve()), "Path escapes the repository.")
    return path


def load_empty_gripper_contract(
    path: Path = DEFAULT_CONTRACT_PATH,
) -> dict[str, Any]:
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise EmptyGripperDiagnosticError(
            f"Could not load the empty-gripper contract: {error}"
        ) from error
    _require(isinstance(contract, dict), "Diagnostic contract must be an object.")
    _require(
        contract.get("schema_version") == CONTRACT_SCHEMA,
        "Unsupported empty-gripper diagnostic contract.",
    )
    _require(
        contract.get("status") == "frozen_before_derived_materialization",
        "Diagnostic contract is not frozen.",
    )
    source = contract.get("source")
    segmentation = contract.get("segmentation")
    simulator = contract.get("simulator_binding")
    authority = contract.get("authority")
    _require(isinstance(source, dict), "Source binding is missing.")
    _require(isinstance(segmentation, dict), "Segmentation contract is missing.")
    _require(isinstance(simulator, dict), "Simulator binding is missing.")
    _require(isinstance(authority, dict), "Authority contract is missing.")
    _require(
        int(simulator.get("candidate_variants", -1)) == 0
        and int(simulator.get("simulator_replays_maximum", -1)) == 1,
        "Simulator budget changed.",
    )
    _require(
        simulator.get("action_mutation_allowed") is False
        and simulator.get("preclip_allowed") is False,
        "Action mutation or preclipping was enabled.",
    )
    _require(
        all(value is False for value in authority.values()),
        "Diagnostic contract widened authority.",
    )
    return contract


def _verify_source_artifacts(
    source_root: Path,
    expected: Mapping[str, str],
) -> dict[str, str]:
    observed: dict[str, str] = {}
    for name, digest in sorted(expected.items()):
        path = source_root / name
        _require(path.is_file(), f"Source artifact is missing: {name}.")
        observed[name] = sha256_file(path)
        _require(observed[name] == digest, f"Source artifact hash changed: {name}.")
    return observed


def _load_samples(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                _require(isinstance(row, dict), "A sample row is not an object.")
                rows.append(row)
    except (OSError, json.JSONDecodeError) as error:
        raise EmptyGripperDiagnosticError(
            f"Could not load source samples: {error}"
        ) from error
    _require(rows, "Source samples are empty.")
    return rows


def _matrix(
    rows: Sequence[Mapping[str, Any]],
    field: str,
) -> np.ndarray:
    try:
        values = np.asarray([row[field] for row in rows], dtype="<f8")
    except (KeyError, TypeError, ValueError) as error:
        raise EmptyGripperDiagnosticError(
            f"Invalid sample vector field: {field}."
        ) from error
    _require(
        values.shape == (len(rows), len(ROBOT_JOINTS))
        and bool(np.all(np.isfinite(values))),
        f"{field} must be a finite [N, 6] tensor.",
    )
    return np.ascontiguousarray(values, dtype="<f8")


def _vector(
    rows: Sequence[Mapping[str, Any]],
    field: str,
) -> np.ndarray:
    try:
        values = np.asarray([row[field] for row in rows], dtype="<f8")
    except (KeyError, TypeError, ValueError) as error:
        raise EmptyGripperDiagnosticError(
            f"Invalid sample scalar field: {field}."
        ) from error
    _require(
        values.shape == (len(rows),) and bool(np.all(np.isfinite(values))),
        f"{field} must be a finite [N] vector.",
    )
    return values


def _action_sha256(actions: np.ndarray) -> str:
    _require(
        actions.dtype == np.dtype("<f8") and actions.flags.c_contiguous,
        "Action tensor must be contiguous little-endian float64.",
    )
    return hashlib.sha256(actions.tobytes(order="C")).hexdigest()


def _current_matrix(rows: Sequence[Mapping[str, Any]]) -> np.ndarray:
    values: list[list[float]] = []
    for row in rows:
        current = row.get("available_motor_current_raw")
        _require(isinstance(current, Mapping), "A sample is missing raw current.")
        try:
            values.append([float(current[joint]) for joint in ROBOT_JOINTS])
        except (KeyError, TypeError, ValueError) as error:
            raise EmptyGripperDiagnosticError(
                "A sample has invalid raw motor current."
            ) from error
    result = np.asarray(values, dtype="<f8")
    _require(bool(np.all(np.isfinite(result))), "Raw current must be finite.")
    return result


def _segment_excursions(
    timestamps: np.ndarray,
    requested: np.ndarray,
    *,
    low_threshold: float,
    high_threshold: float,
) -> list[tuple[int, int]]:
    _require(low_threshold < high_threshold, "Gripper thresholds are not ordered.")
    _require(
        float(requested[0, -1]) <= low_threshold,
        "The gripper trace does not begin in the declared low state.",
    )
    state = "low"
    high_index: int | None = None
    cycles: list[tuple[int, int]] = []
    for index, value in enumerate(requested[:, -1]):
        if state == "low" and float(value) >= high_threshold:
            high_index = index
            state = "high"
        elif state == "high" and float(value) <= low_threshold:
            _require(high_index is not None, "Excursion high boundary is missing.")
            _require(
                float(timestamps[index]) > float(timestamps[high_index]),
                "Excursion duration is not positive.",
            )
            cycles.append((high_index, index))
            high_index = None
            state = "low"
    _require(high_index is None, "The final gripper excursion is incomplete.")
    return cycles


def _best_lag(
    requested: np.ndarray,
    actual: np.ndarray,
    *,
    median_dt: float,
    minimum_seconds: float,
    maximum_seconds: float,
) -> tuple[float, float]:
    minimum_steps = max(0, int(math.ceil(minimum_seconds / median_dt)))
    maximum_steps = max(minimum_steps, int(math.floor(maximum_seconds / median_dt)))
    candidates: list[tuple[float, int]] = []
    for lag in range(minimum_steps, maximum_steps + 1):
        if lag == 0:
            source = requested
            observed = actual
        else:
            source = requested[:-lag]
            observed = actual[lag:]
        if len(source) < 2:
            continue
        rmse = float(np.sqrt(np.mean(np.square(source - observed))))
        candidates.append((rmse, lag))
    _require(candidates, "Lag search has no valid candidate.")
    rmse, lag = min(candidates, key=lambda row: (row[0], row[1]))
    return float(lag * median_dt), rmse


def _summarize_cycles(
    rows: Sequence[Mapping[str, Any]],
    timestamps: np.ndarray,
    requested: np.ndarray,
    actual: np.ndarray,
    currents: np.ndarray,
    cycles: Sequence[tuple[int, int]],
    contract: Mapping[str, Any],
) -> list[dict[str, Any]]:
    segmentation = contract["segmentation"]
    gates = contract["measurement_gates"]
    median_dt = float(np.median(np.diff(timestamps)))
    _require(median_dt > 0.0, "Sample timestamps are not increasing.")
    margin = float(segmentation["analysis_margin_seconds"])
    summaries: list[dict[str, Any]] = []
    for cycle_id, (high_index, low_index) in enumerate(cycles, start=1):
        start_time = float(timestamps[high_index]) - margin
        stop_time = float(timestamps[low_index]) + margin
        start = int(np.searchsorted(timestamps, start_time, side="left"))
        stop = int(np.searchsorted(timestamps, stop_time, side="right"))
        lag_seconds, aligned_rmse = _best_lag(
            requested[start:stop, -1],
            actual[start:stop, -1],
            median_dt=median_dt,
            minimum_seconds=float(segmentation["lag_search_min_seconds"]),
            maximum_seconds=float(segmentation["lag_search_max_seconds"]),
        )
        body_range = np.ptp(requested[start:stop, :-1], axis=0)
        gripper_current = currents[start:stop, -1]
        maximum_body_range = float(np.max(body_range))
        summaries.append(
            {
                "cycle_id": cycle_id,
                "high_sample_index": high_index,
                "low_sample_index": low_index,
                "high_time_seconds": float(timestamps[high_index]),
                "low_time_seconds": float(timestamps[low_index]),
                "high_to_low_duration_seconds": float(
                    timestamps[low_index] - timestamps[high_index]
                ),
                "analysis_sample_count": stop - start,
                "best_gripper_lag_seconds": lag_seconds,
                "lag_aligned_gripper_rmse_degrees": aligned_rmse,
                "maximum_gripper_tracking_error_degrees": float(
                    np.max(np.abs(requested[start:stop, -1] - actual[start:stop, -1]))
                ),
                "body_requested_peak_to_peak_degrees": body_range.tolist(),
                "maximum_body_requested_peak_to_peak_degrees": maximum_body_range,
                "gripper_current_raw_maximum": float(np.max(gripper_current)),
                "gripper_current_raw_median": float(np.median(gripper_current)),
                "stable_body_envelope": maximum_body_range
                <= float(gates["maximum_stable_cycle_body_peak_to_peak_degrees"]),
                "stable_lag_envelope": lag_seconds
                <= float(gates["maximum_stable_cycle_gripper_lag_seconds"]),
                "source_rows_nonstale_current": all(
                    row.get("current_telemetry_stale") is False
                    for row in rows[start:stop]
                ),
            }
        )
    return summaries


def _aggregate_cycles(cycles: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    _require(cycles, "Cycle aggregate cannot be empty.")
    return {
        "cycle_count": len(cycles),
        "median_best_gripper_lag_seconds": float(
            np.median([row["best_gripper_lag_seconds"] for row in cycles])
        ),
        "maximum_best_gripper_lag_seconds": float(
            max(row["best_gripper_lag_seconds"] for row in cycles)
        ),
        "median_lag_aligned_gripper_rmse_degrees": float(
            np.median([row["lag_aligned_gripper_rmse_degrees"] for row in cycles])
        ),
        "maximum_body_requested_peak_to_peak_degrees": float(
            max(row["maximum_body_requested_peak_to_peak_degrees"] for row in cycles)
        ),
        "gripper_current_raw_maximum": float(
            max(row["gripper_current_raw_maximum"] for row in cycles)
        ),
        "all_cycles_within_stable_body_and_lag_envelopes": all(
            row["stable_body_envelope"] and row["stable_lag_envelope"]
            for row in cycles
        ),
    }


def _simulator_binding(
    actions: np.ndarray,
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    simulator = contract["simulator_binding"]
    scene_path = _repo_path(str(simulator["scene_source"]))
    replay_path = _repo_path(str(simulator["replay_source"]))
    _require(
        sha256_file(scene_path) == simulator["scene_source_sha256"],
        "Simulator scene implementation changed.",
    )
    _require(
        sha256_file(replay_path) == simulator["replay_source_sha256"],
        "Simulator replay implementation changed.",
    )
    model = build_scene_spec(piece_layout=CURRENT_TASK_PIECE_LAYOUT).compile()
    actuator_ids: list[int] = []
    actuator_rows: list[dict[str, Any]] = []
    for joint in ROBOT_JOINTS:
        actuator_id = mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_ACTUATOR, f"left_{joint}"
        )
        _require(actuator_id >= 0, f"Current simulator is missing left_{joint}.")
        actuator_ids.append(actuator_id)
        actuator_rows.append(
            {
                "joint": joint,
                "ctrlrange": model.actuator_ctrlrange[actuator_id].astype(float).tolist(),
                "forcerange": model.actuator_forcerange[actuator_id]
                .astype(float)
                .tolist(),
                "gainprm": model.actuator_gainprm[actuator_id, :3]
                .astype(float)
                .tolist(),
                "biasprm": model.actuator_biasprm[actuator_id, :3]
                .astype(float)
                .tolist(),
            }
        )
    bounds = np.asarray(model.actuator_ctrlrange[actuator_ids], dtype="<f8")
    _require(
        bool(np.all((actions[:, -1] >= 0.0) & (actions[:, -1] <= 100.0))),
        "Physical gripper action is outside the declared 0-100 representation.",
    )
    converted = np.empty_like(actions)
    converted[:, :-1] = np.deg2rad(actions[:, :-1])
    converted[:, -1] = bounds[-1, 0] + (actions[:, -1] / 100.0) * (
        bounds[-1, 1] - bounds[-1, 0]
    )
    violations = (converted < bounds[:, 0]) | (converted > bounds[:, 1])
    counts = {
        joint: int(np.count_nonzero(violations[:, index]))
        for index, joint in enumerate(ROBOT_JOINTS)
    }
    violating_rows = int(np.count_nonzero(np.any(violations, axis=1)))
    identity_payload = {
        "scene_source_sha256": simulator["scene_source_sha256"],
        "replay_source_sha256": simulator["replay_source_sha256"],
        "mujoco_timestep_seconds": float(model.opt.timestep),
        "actuators": actuator_rows,
    }
    return {
        "simulator_identity": identity_payload,
        "simulator_identity_sha256": canonical_digest(identity_payload),
        "exact_input_action_sha256": _action_sha256(actions),
        "action_shape": list(actions.shape),
        "action_dtype": "float64",
        "preclip_applied": False,
        "action_mutated": False,
        "rows_outside_declared_ctrlrange": violating_rows,
        "violations_by_joint": counts,
        "simulator_replays_maximum": int(simulator["simulator_replays_maximum"]),
        "simulator_replays_used": 0,
        "candidate_variants": 0,
        "verdict": (
            "abstain_exact_action_outside_declared_simulator_ctrlrange"
            if violating_rows
            else "eligible_for_separately_authorized_exact_baseline_replay"
        ),
    }


def derive_empty_gripper_diagnostic(
    output_root: Path,
    *,
    contract_path: Path = DEFAULT_CONTRACT_PATH,
) -> dict[str, Any]:
    """Materialize one deterministic derived packet without simulator execution."""

    contract = load_empty_gripper_contract(contract_path)
    source = contract["source"]
    source_root = _repo_path(str(source["recording_directory"]))
    _require(
        not output_root.exists() or not any(output_root.iterdir()),
        "Diagnostic output root is not empty; overwrite/replay is refused.",
    )
    output_root.mkdir(parents=True, exist_ok=True)
    source_hashes = _verify_source_artifacts(
        source_root, source["artifacts_sha256"]
    )
    receipt = json.loads(
        (source_root / "recording_receipt.json").read_text(encoding="utf-8")
    )
    _require(
        receipt.get("recording_id") == source["recording_id"],
        "Recording identity changed.",
    )
    _require(receipt.get("mode") == source["expected_mode"], "Recording mode changed.")
    _require(
        receipt.get("proof_class") == source["expected_proof_class"],
        "Recording proof class changed.",
    )
    for field, value in source["expected_raw_label"].items():
        _require(receipt.get(field) == value, f"Raw label changed: {field}.")
    rows = _load_samples(source_root / "samples.jsonl")
    _require(
        len(rows) == int(receipt.get("sample_count", -1)),
        "Sample count does not match the recording receipt.",
    )
    _require(
        all(row.get("recording_id") == source["recording_id"] for row in rows),
        "A sample belongs to another recording.",
    )
    _require(
        all(int(row.get("assistance", -1)) == 0 for row in rows),
        "Assisted action row is not admissible.",
    )
    _require(
        all(int(row.get("intervention", -1)) == 0 for row in rows),
        "Intervened action row is not admissible.",
    )
    _require(
        all(row.get("current_telemetry_stale") is False for row in rows),
        "At least one current row is marked stale.",
    )
    timestamps = _vector(rows, "timestamp_monotonic_seconds")
    _require(
        bool(np.all(np.diff(timestamps) > 0.0)),
        "Sample timestamps must be strictly increasing.",
    )
    requested = _matrix(rows, "follower_requested_degrees")
    actions = _matrix(rows, "follower_command_degrees")
    actual = _matrix(rows, "follower_actual_position_degrees")
    currents = _current_matrix(rows)
    segmentation = contract["segmentation"]
    cycle_bounds = _segment_excursions(
        timestamps,
        requested,
        low_threshold=float(segmentation["low_threshold_degrees"]),
        high_threshold=float(segmentation["high_threshold_degrees"]),
    )
    _require(
        len(cycle_bounds) == int(segmentation["expected_observed_excursions"]),
        "Observed excursion count changed.",
    )
    cycles = _summarize_cycles(
        rows, timestamps, requested, actual, currents, cycle_bounds, contract
    )
    sensitivity_ids = set(
        int(value) for value in segmentation["owner_intended_sensitivity_cycle_ids"]
    )
    sensitivity_cycles = [
        row for row in cycles if int(row["cycle_id"]) in sensitivity_ids
    ]
    _require(
        len(sensitivity_cycles) == int(segmentation["owner_intended_excursions"]),
        "Owner-intended sensitivity view is incomplete.",
    )
    simulator = _simulator_binding(actions, contract)
    intended_summary = _aggregate_cycles(sensitivity_cycles)
    procedure_count_match = len(cycles) == int(
        segmentation["owner_intended_excursions"]
    )
    diagnostic = {
        "schema_version": DIAGNOSTIC_SCHEMA,
        "contract_id": contract["contract_id"],
        "source_recording_id": source["recording_id"],
        "source_recording_directory": source["recording_directory"],
        "source_artifacts_sha256": source_hashes,
        "proof_class": "derived_empty_gripper_cycle_diagnostic",
        "raw_proof_class": receipt["proof_class"],
        "raw_label_preserved": copy.deepcopy(source["expected_raw_label"]),
        "raw_label_is_not_measurement_admission": True,
        "sample_count": len(rows),
        "duration_seconds": float(timestamps[-1] - timestamps[0]),
        "sample_interval_median_seconds": float(np.median(np.diff(timestamps))),
        "current_telemetry": {
            "declared_hz": float(rows[0].get("current_telemetry_hz", 0.0)),
            "rows_with_nonstale_current": len(rows),
            "rows_marked_stale": 0,
            "independent_current_read_timestamp_per_row_available": False,
            "current_values_are_raw_device_units": True,
            "joint_order": list(ROBOT_JOINTS),
            "maximum_raw_current_by_joint": np.max(currents, axis=0).tolist(),
            "median_raw_current_by_joint": np.median(currents, axis=0).tolist(),
        },
        "camera_coverage": {
            "c922_frames": int(
                receipt["overhead_video"]["observed_video"]["streams"][0]["nb_frames"]
            ),
            "c922_duration_seconds": float(
                receipt["overhead_video"]["observed_video"]["format"]["duration"]
            ),
            "d405_browser_frames": int(
                receipt["wrist_video"]["browser_observed_video"]["streams"][0][
                    "nb_frames"
                ]
            ),
            "d405_duration_seconds": float(
                receipt["wrist_video"]["browser_observed_video"]["format"]["duration"]
            ),
            "metric_depth_available": False,
        },
        "segmentation": {
            "signal": segmentation["signal"],
            "low_threshold_degrees": float(
                segmentation["low_threshold_degrees"]
            ),
            "high_threshold_degrees": float(
                segmentation["high_threshold_degrees"]
            ),
            "observed_excursion_count": len(cycles),
            "owner_intended_excursion_count": int(
                segmentation["owner_intended_excursions"]
            ),
            "procedure_count_matches": procedure_count_match,
            "cycles": cycles,
        },
        "all_cycle_summary": _aggregate_cycles(cycles),
        "owner_intended_five_cycle_sensitivity": {
            "cycle_ids": sorted(sensitivity_ids),
            "retrospective_non_promoting_view": True,
            "summary": intended_summary,
        },
        "simulator_binding": simulator,
        "unavailable_observables": list(contract["unavailable_observables"]),
        "measurement_admission": {
            "admitted": False,
            "reason": (
                "observed_six_excursions_do_not_match_the_preregistered_five_cycle_procedure"
            ),
        },
        "calibration_decision": {
            "simulator_parameter_changed": False,
            "simulator_parameter_promoted": False,
            "task_score_changed": False,
            "verdict": (
                "diagnostic_only_procedure_count_mismatch_and_"
                "exact_action_simulator_range_abstention"
            ),
            "identified_signal": (
                "cycles_2_through_6_have_consistent_gripper_response_lag"
                if intended_summary[
                    "all_cycles_within_stable_body_and_lag_envelopes"
                ]
                else "no_stable_gripper_response_signal"
            ),
        },
        "authority": copy.deepcopy(contract["authority"]),
    }
    diagnostic_path = output_root / "diagnostic.json"
    atomic_write_json(diagnostic_path, diagnostic)
    unsigned_receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "contract_path": str(contract_path.resolve()),
        "contract_sha256": sha256_file(contract_path),
        "source_recording_id": source["recording_id"],
        "source_manifest_sha256": canonical_digest(source_hashes),
        "diagnostic_path": diagnostic_path.name,
        "diagnostic_sha256": sha256_file(diagnostic_path),
        "proof_class": diagnostic["proof_class"],
        "measurement_admitted": False,
        "simulator_replays_used": 0,
        "simulator_parameter_promoted": False,
        "task_score_changed": False,
        "verdict": diagnostic["calibration_decision"]["verdict"],
        "authority": copy.deepcopy(contract["authority"]),
    }
    final_receipt = {
        **unsigned_receipt,
        "receipt_sha256": canonical_digest(unsigned_receipt),
    }
    atomic_write_json(output_root / "receipt.json", final_receipt)
    return final_receipt


__all__ = [
    "CONTRACT_SCHEMA",
    "DEFAULT_CONTRACT_PATH",
    "DIAGNOSTIC_SCHEMA",
    "EmptyGripperDiagnosticError",
    "RECEIPT_SCHEMA",
    "derive_empty_gripper_diagnostic",
    "load_empty_gripper_contract",
]
