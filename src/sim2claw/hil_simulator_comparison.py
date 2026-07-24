"""Action-identical external validation of the shoulder range hypothesis."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from .hil_identifiability import action_tensor_sha256
from .joint_limit_comparison import _execute_variant, _verify_calibration
from .learning_factory_artifacts import (
    atomic_write_json,
    canonical_digest,
    sha256_file,
)
from .paths import REPO_ROOT
from .scene import ROBOT_JOINTS


CONTRACT_SCHEMA = "sim2claw.hil_shoulder_range_external_validation.v1"
RAW_SCHEMA = "sim2claw.hil_shoulder_range_comparison_raw.v1"
EVALUATION_SCHEMA = "sim2claw.hil_shoulder_range_comparison_evaluation.v1"
RECEIPT_SCHEMA = "sim2claw.hil_shoulder_range_comparison_receipt.v1"


class HILSimulatorComparisonError(RuntimeError):
    """A source, action, budget, simulator, or evaluator gate failed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise HILSimulatorComparisonError(message)


def _repo_path(value: str) -> Path:
    path = (REPO_ROOT / value).resolve()
    _require(path.is_relative_to(REPO_ROOT.resolve()), "Path escapes the repository.")
    return path


def load_hil_simulator_contract(path: Path) -> dict[str, Any]:
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HILSimulatorComparisonError(
            f"HIL simulator comparison contract is unreadable: {error}"
        ) from error
    _require(
        contract.get("schema_version") == CONTRACT_SCHEMA,
        "HIL simulator comparison schema is unsupported.",
    )
    _require(
        contract.get("status") == "frozen_before_simulator_execution",
        "HIL simulator comparison is not frozen.",
    )
    variants = contract.get("simulator", {}).get("variants")
    _require(
        isinstance(variants, list)
        and [row.get("id") for row in variants]
        == ["current_declared_ranges", "follower_shoulder_lift_range_v1"],
        "HIL simulator variants changed.",
    )
    _require(
        variants[0].get("mutated_joints") == []
        and variants[1].get("mutated_joints") == ["shoulder_lift"],
        "HIL simulator affected-factor scope changed.",
    )
    _require(
        int(contract["budget"]["simulator_replays"]) == 2
        and int(contract["budget"]["adaptive_retries"]) == 0
        and int(contract["budget"]["provider_calls"]) == 0,
        "HIL simulator comparison budget changed.",
    )
    _require(
        all(value is False for value in contract["authority"].values()),
        "HIL simulator comparison widened authority.",
    )
    lineage = contract.get("candidate_lineage") or {}
    prior_contract = _repo_path(str(lineage.get("prior_comparison_contract") or ""))
    _require(
        prior_contract.is_file()
        and sha256_file(prior_contract)
        == lineage.get("prior_comparison_contract_sha256"),
        "Pre-existing candidate lineage changed.",
    )
    _require(
        lineage.get("new_parameter_value_fit_from_hil_packet") is False,
        "HIL packet cannot fit the candidate value it externally evaluates.",
    )
    return contract


def _load_source(
    contract: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    source = contract["source"]
    root = _repo_path(source["packet_directory"])
    raw_path = root / "raw_receipt.json"
    evaluation_path = root / "evaluation.json"
    action_path = root / source["action_tensor_path"]
    samples_path = root / source["replay_samples_path"]
    _require(
        sha256_file(raw_path) == source["raw_receipt_sha256"],
        "HIL raw receipt changed.",
    )
    _require(
        sha256_file(evaluation_path) == source["evaluation_sha256"],
        "HIL evaluation changed.",
    )
    evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
    _require(
        evaluation.get("verdict") == source["evaluation_verdict"]
        and evaluation.get("admitted") is True,
        "HIL packet is not evaluator-admitted.",
    )
    _require(
        sha256_file(action_path) == source["action_tensor_file_sha256"],
        "HIL action tensor file changed.",
    )
    _require(
        sha256_file(samples_path) == source["replay_samples_sha256"],
        "HIL physical replay samples changed.",
    )
    try:
        actions = np.ascontiguousarray(np.load(action_path, allow_pickle=False), dtype="<f8")
        rows = [
            json.loads(line)
            for line in samples_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        source_rows = [
            row
            for row in rows
            if row.get("replay_phase", "source_trace") == "source_trace"
        ]
        requested = np.ascontiguousarray(
            [row["requested_source_command_degrees"] for row in source_rows],
            dtype="<f8",
        )
        actual = np.ascontiguousarray(
            [row["follower_actual_position_degrees"] for row in source_rows],
            dtype="<f8",
        )
        timestamps = np.asarray(
            [row["source_elapsed_seconds"] for row in source_rows],
            dtype="<f8",
        )
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise HILSimulatorComparisonError(
            f"HIL simulator source is invalid: {error}"
        ) from error
    expected_shape = tuple(int(value) for value in source["action_shape"])
    _require(
        actions.shape == requested.shape == actual.shape == expected_shape,
        "HIL simulator source tensor shape changed.",
    )
    _require(
        actions.dtype == np.dtype("<f8") and actions.flags.c_contiguous,
        "HIL simulator actions must remain contiguous little-endian float64.",
    )
    _require(np.array_equal(actions, requested), "HIL requested action bytes changed.")
    _require(
        action_tensor_sha256(actions) == source["action_tensor_sha256"],
        "HIL action tensor digest changed.",
    )
    _require(
        bool(np.all(np.isfinite(actual))) and bool(np.all(np.diff(timestamps) > 0)),
        "HIL actual positions or timestamps are invalid.",
    )
    return actions, actual, timestamps


def _evaluate(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    evaluator = contract["evaluation"]
    target_index = list(ROBOT_JOINTS).index(evaluator["target_joint"])
    baseline_body = np.asarray(
        baseline["metrics"]["body_joint_rmse_degrees"], dtype=np.float64
    )
    candidate_body = np.asarray(
        candidate["metrics"]["body_joint_rmse_degrees"], dtype=np.float64
    )
    baseline_target = float(baseline_body[target_index])
    candidate_target = float(candidate_body[target_index])
    target_improvement = (
        (baseline_target - candidate_target) / baseline_target
        if baseline_target > 0.0
        else 0.0
    )
    regressions = candidate_body - baseline_body
    non_target = np.delete(regressions, target_index)
    action_identical = bool(
        baseline["input_action_sha256"] == candidate["input_action_sha256"]
        and baseline["input_action_shape"] == candidate["input_action_shape"]
        and baseline["input_action_dtype"] == candidate["input_action_dtype"]
    )
    target_gate = target_improvement >= float(
        evaluator["target_joint_rmse_improvement_minimum_fraction"]
    )
    non_target_gate = bool(
        np.all(
            non_target
            <= float(evaluator["maximum_non_target_joint_rmse_regression_degrees"])
        )
    )
    gripper_gate = float(candidate["metrics"]["gripper_rmse_actuator_rad"]) <= float(
        baseline["metrics"]["gripper_rmse_actuator_rad"]
    ) + 1e-12
    diagnostic_gain = action_identical and target_gate and non_target_gate and gripper_gate
    return {
        "schema_version": EVALUATION_SCHEMA,
        "evaluator_owner": evaluator["owner"],
        "action_tensor_byte_identical": action_identical,
        "target_joint": evaluator["target_joint"],
        "baseline_target_joint_rmse_degrees": baseline_target,
        "candidate_target_joint_rmse_degrees": candidate_target,
        "target_joint_rmse_improvement_fraction": target_improvement,
        "body_joint_rmse_regression_degrees": regressions.tolist(),
        "target_improvement_gate_passed": target_gate,
        "non_target_regression_gate_passed": non_target_gate,
        "gripper_nonregression_gate_passed": gripper_gate,
        "diagnostic_gain": diagnostic_gain,
        "strict_task_consequence_available": False,
        "simulator_parameter_promoted": False,
        "task_score_changed": False,
        "verdict": (
            "diagnostic_shoulder_range_external_gain_no_promotion"
            if diagnostic_gain
            else "diagnostic_shoulder_range_external_tie_or_loss_no_promotion"
        ),
    }


def run_hil_simulator_comparison(
    output_root: Path,
    *,
    contract_path: Path,
) -> dict[str, Any]:
    output_root = output_root.resolve()
    _require(not output_root.exists(), "HIL simulator output already exists.")
    output_root.mkdir(parents=True)
    contract = load_hil_simulator_contract(contract_path)
    _require(
        sha256_file(_repo_path(contract["simulator"]["scene_source"]))
        == contract["simulator"]["scene_source_sha256"],
        "Current simulator implementation changed after freeze.",
    )
    actions, actual, timestamps = _load_source(contract)
    calibrated_ranges = _verify_calibration(contract)
    diagnostic = {"segmentation": {"cycles": []}}
    baseline = _execute_variant(
        variant_id="current_declared_ranges",
        actions=actions,
        actual=actual,
        timestamps=timestamps,
        calibrated_ranges_degrees=calibrated_ranges,
        mutate_ranges=False,
        output_path=output_root / "current_declared_ranges.jsonl",
        diagnostic=diagnostic,
        mutated_joints=(),
    )
    candidate = _execute_variant(
        variant_id="follower_shoulder_lift_range_v1",
        actions=actions,
        actual=actual,
        timestamps=timestamps,
        calibrated_ranges_degrees=calibrated_ranges,
        mutate_ranges=True,
        output_path=output_root / "follower_shoulder_lift_range_v1.jsonl",
        diagnostic=diagnostic,
        mutated_joints=("shoulder_lift",),
    )
    _require(
        baseline["input_action_sha256"] == candidate["input_action_sha256"],
        "Simulator variants did not receive identical actions.",
    )
    raw = {
        "schema_version": RAW_SCHEMA,
        "validation_id": contract["validation_id"],
        "source_packet_id": contract["source"]["packet_id"],
        "source_action_sha256": contract["source"]["action_tensor_sha256"],
        "simulator_replays_used": 2,
        "adaptive_retries": 0,
        "baseline": baseline,
        "candidate": candidate,
    }
    atomic_write_json(output_root / "raw_comparison.json", raw)
    evaluation = _evaluate(baseline, candidate, contract)
    atomic_write_json(output_root / "evaluation.json", evaluation)
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "proof_class": "action_frozen_hil_simulator_comparison",
        "contract_path": str(contract_path.resolve()),
        "contract_sha256": sha256_file(contract_path),
        "raw_comparison_sha256": sha256_file(output_root / "raw_comparison.json"),
        "evaluation_sha256": sha256_file(output_root / "evaluation.json"),
        "trace_sha256": {
            "current_declared_ranges.jsonl": sha256_file(
                output_root / "current_declared_ranges.jsonl"
            ),
            "follower_shoulder_lift_range_v1.jsonl": sha256_file(
                output_root / "follower_shoulder_lift_range_v1.jsonl"
            ),
        },
        "action_tensor_sha256": contract["source"]["action_tensor_sha256"],
        "simulator_replays_used": 2,
        "adaptive_retries": 0,
        "provider_calls": 0,
        "verdict": evaluation["verdict"],
        "authority": {
            "diagnostic_simulator_gain": evaluation["diagnostic_gain"],
            "simulator_parameter_promotion": False,
            "task_score_change": False,
            "training": False,
            "physical_transfer": False,
        },
    }
    receipt["receipt_digest"] = canonical_digest(receipt)
    atomic_write_json(output_root / "receipt.json", receipt)
    return receipt
