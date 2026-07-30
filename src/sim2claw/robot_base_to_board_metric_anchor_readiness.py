"""Fail-closed readiness receipt for an independent board-to-base metric anchor."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
)
from .paths import REPO_ROOT


SCHEMA = "sim2claw.robot_base_to_board_metric_anchor_readiness_contract.v1"
MEASUREMENT_SCHEMA = "sim2claw.robot_base_to_board_metric_anchor_measurement.v1"
RECEIPT_SCHEMA = "sim2claw.robot_base_to_board_metric_anchor_readiness_receipt.v1"
CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "robot_base_to_board_metric_anchor_readiness_v1.json"
)
OUTPUT_PATH = (
    REPO_ROOT
    / "outputs"
    / "robot_base_to_board_metric_anchor_readiness_v1"
    / "receipt.json"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def load_metric_anchor_contract(
    path: Path = CONTRACT_PATH,
) -> dict[str, Any]:
    contract = load_json_object(path, label="metric anchor readiness contract")
    _require(contract.get("schema_version") == SCHEMA, "unsupported contract")
    _require(
        contract.get("proof_class")
        == "prospective_no_contact_metric_board_to_base_measurement_readiness",
        "proof class changed",
    )

    target = contract.get("target_transform")
    _require(
        isinstance(target, dict)
        and target.get("name") == "world_T_left_base"
        and target.get("candidate_family") == "robot_base_se3_only",
        "target transform changed",
    )
    measurement = contract.get("measurement")
    _require(
        isinstance(measurement, dict)
        and int(measurement.get("minimum_non_collinear_points", 0)) >= 3
        and measurement.get("known_base_to_fixture_transform_required") is True
        and measurement.get("model_base_origin_and_axes_definition_required")
        is True
        and measurement.get("metric_units_required") is True
        and measurement.get("measurement_covariance_required") is True
        and measurement.get("repeat_observations_required") is True
        and measurement.get("task_episode_allowed") is False
        and measurement.get("pawn_contact_allowed") is False
        and measurement.get("robot_motion_required") is False,
        "measurement boundary changed",
    )
    admission = contract.get("admission")
    _require(
        isinstance(admission, dict)
        and float(admission.get("maximum_translation_uncertainty_m", math.inf))
        == 0.003
        and float(
            admission.get("maximum_rotation_uncertainty_degrees", math.inf)
        )
        == 0.5
        and admission.get("one_candidate_change_only") is True
        and admission.get("task_outcome_allowed_for_selection") is False
        and admission.get("static_no_refit_validation_required") is True
        and admission.get("exact_contact_phase_gate_required") is True,
        "admission boundary changed",
    )
    authority = contract.get("authority")
    _require(
        isinstance(authority, dict) and authority and not any(authority.values()),
        "authority widened",
    )
    return contract


def _validate_measurement(
    measurement: dict[str, Any],
    *,
    contract: dict[str, Any],
) -> tuple[int, bool, list[str]]:
    checks: list[str] = []
    _require(
        measurement.get("schema_version") == MEASUREMENT_SCHEMA,
        "unsupported measurement",
    )
    _require(
        measurement.get("measurement_id")
        == contract["measurement"]["measurement_id"],
        "measurement identity changed",
    )
    _require(
        measurement.get("task_episode_used") is False
        and measurement.get("pawn_contact_used") is False
        and measurement.get("robot_motion_used") is False,
        "measurement crossed the no-contact boundary",
    )
    rows = measurement.get("correspondences")
    _require(isinstance(rows, list), "measurement correspondences are missing")
    row_count = len(rows)
    minimum = int(contract["measurement"]["minimum_non_collinear_points"])
    enough_rows = row_count >= minimum
    checks.append(f"correspondence_count={row_count}>={minimum}:{enough_rows}")

    candidate = measurement.get("candidate_world_T_left_base")
    candidate_present = (
        isinstance(candidate, dict)
        and isinstance(candidate.get("translation_m"), list)
        and len(candidate["translation_m"]) == 3
        and isinstance(candidate.get("quaternion_wxyz"), list)
        and len(candidate["quaternion_wxyz"]) == 4
    )
    checks.append(f"candidate_transform_present:{candidate_present}")

    uncertainty = measurement.get("uncertainty")
    uncertainty_pass = False
    if isinstance(uncertainty, dict):
        translation = float(uncertainty.get("translation_m", math.inf))
        rotation = float(uncertainty.get("rotation_degrees", math.inf))
        uncertainty_pass = (
            math.isfinite(translation)
            and math.isfinite(rotation)
            and translation
            <= float(contract["admission"]["maximum_translation_uncertainty_m"])
            and rotation
            <= float(
                contract["admission"][
                    "maximum_rotation_uncertainty_degrees"
                ]
            )
        )
    checks.append(f"uncertainty_within_frozen_limits:{uncertainty_pass}")

    required_metadata = (
        "known_base_to_fixture_transform",
        "model_base_frame_definition",
        "measurement_covariance",
        "repeat_observations",
        "metric_units",
    )
    metadata_pass = all(measurement.get(key) for key in required_metadata)
    checks.append(f"required_metric_metadata_present:{metadata_pass}")
    admitted = enough_rows and candidate_present and uncertainty_pass and metadata_pass
    return row_count, admitted, checks


def build_metric_anchor_readiness_receipt(
    contract_path: Path = CONTRACT_PATH,
    output_path: Path = OUTPUT_PATH,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    contract = load_metric_anchor_contract(contract_path)
    measurement_path = root / str(contract["measurement"]["expected_path"])
    measurement_rows = 0
    candidate_transform_produced = False
    design_checks = [
        "independent_board_to_left_base_metric_anchor",
        "task_episode_excluded",
        "pawn_contact_excluded",
        "robot_motion_not_required",
        "single_robot_base_se3_candidate_only",
        "static_no_refit_and_exact_contact_phase_gates_required",
    ]

    if measurement_path.is_file():
        measurement = load_json_object(
            measurement_path, label="metric anchor measurement"
        )
        (
            measurement_rows,
            candidate_transform_produced,
            measurement_checks,
        ) = _validate_measurement(measurement, contract=contract)
        design_checks.extend(measurement_checks)
        result = (
            "METRIC_ANCHOR_CANDIDATE_READY_FOR_STATIC_NO_REFIT_GATE"
            if candidate_transform_produced
            else "MEASUREMENT_REJECTED_BY_FROZEN_METRIC_ANCHOR_GATE"
        )
    else:
        result = "DESIGN_READY_BLOCKED_EXTERNAL_METRIC_ANCHOR"
        design_checks.append("external_measurement_missing:true")

    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "proof_class": contract["proof_class"],
        "result": result,
        "contract_digest": canonical_digest(contract),
        "measurement_path": str(
            measurement_path.relative_to(root)
            if root.resolve() in measurement_path.resolve().parents
            else measurement_path
        ),
        "measurement_rows": measurement_rows,
        "candidate_transform_produced": candidate_transform_produced,
        "design_checks": design_checks,
        "physical_motion": False,
        "task_attempts": 0,
        "simulator_dynamic_replays": 0,
        "global_mapping_approved": False,
        "authority": dict(contract["authority"]),
    }
    receipt["artifact_digest"] = canonical_digest(receipt)
    atomic_write_json(output_path, receipt)
    return receipt
