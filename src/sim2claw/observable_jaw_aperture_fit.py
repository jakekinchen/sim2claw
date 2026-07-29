"""Fit and no-refit validate the OR5 gripper aperture offset."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import least_squares

from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
    sha256_file,
)
from .observable_jaw_aperture_mechanism import (
    _bound_json,
    _bound_path,
    _candidate_with_offset,
    _load_jsonl,
    _physical_hold_means,
    _projected_apertures,
)
from .observable_robot_jaw_mapping import (
    _annotation_points,
    _model_jaw_tips,
    apply_planar_rigid,
    project_world_points,
)
from .paths import REPO_ROOT


SCHEMA = "sim2claw.observable_jaw_aperture_fit_contract.v1"
RECEIPT_SCHEMA = "sim2claw.observable_jaw_aperture_fit_receipt.v1"
CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "observable_jaw_aperture_fit_v1.json"
)
OUTPUT_DIRECTORY = REPO_ROOT / "outputs" / "observable_jaw_aperture_fit_v1"
OUTPUT_PATH = OUTPUT_DIRECTORY / "receipt.json"
CANDIDATE_PATH = OUTPUT_DIRECTORY / "candidate_manifest.json"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def load_aperture_fit_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="observable jaw aperture fit")
    _require(contract.get("schema_version") == SCHEMA, "unsupported aperture fit schema")
    sources = contract.get("sources")
    _require(isinstance(sources, dict) and sources, "aperture fit sources are missing")
    for source_id, binding in sources.items():
        _require(isinstance(binding, dict), f"invalid fit source: {source_id}")
        _bound_path(binding, root=root, label=source_id)
    split = contract.get("split")
    _require(
        isinstance(split, dict)
        and int(split.get("fit_count", 0)) == 6
        and int(split.get("validation_count", 0)) == 4
        and split.get("fit_validation_overlap_allowed") is False
        and split.get("validation_open_after_candidate_fit_only") is True
        and split.get("validation_candidate_refit_allowed") is False
        and split.get("sealed_c6_contact_or_outcome_may_be_read") is False
        and split.get("quarantined_v4_heldout_used") is False,
        "aperture fit split widened",
    )
    optimizer = contract.get("optimizer")
    _require(
        isinstance(optimizer, dict)
        and optimizer.get("objective")
        == "per_pose_projected_jaw_tip_pair_separation_error_px"
        and float(optimizer["minimum_value"]) == -0.174533
        and float(optimizer["maximum_value"]) == 0.174533,
        "aperture optimizer changed",
    )
    mechanisms = contract.get("frozen_mechanisms")
    _require(
        isinstance(mechanisms, dict)
        and mechanisms.get("fit_parameter") == "gripper_zero_offset_rad"
        and all(
            mechanisms.get(field) is False
            for field in (
                "or1_camera_change_allowed",
                "or2_robot_board_transform_change_allowed",
                "body_joint_mapping_change_allowed",
                "jaw_mesh_or_collision_geometry_change_allowed",
                "actuator_plant_change_allowed",
                "contact_parameter_change_allowed",
                "object_parameter_change_allowed",
                "initialization_change_allowed",
                "action_or_timing_change_allowed",
            )
        ),
        "aperture fit mechanism widened",
    )
    promotion = contract.get("promotion")
    _require(
        isinstance(promotion, dict)
        and promotion.get("requires_all_checks") is True
        and promotion.get("global_mapping_approved") is False
        and promotion.get("dynamic_replay_authorized") is False,
        "aperture fit promotion widened",
    )
    boundaries = contract.get("proof_boundaries")
    authority = contract.get("authority")
    _require(
        isinstance(boundaries, dict) and boundaries and not any(boundaries.values()),
        "aperture fit proof boundary widened",
    )
    _require(
        isinstance(authority, dict) and authority and not any(authority.values()),
        "aperture fit authority widened",
    )
    return contract


def _observed_from_v4(
    annotations: dict[str, Any], ids: list[str]
) -> np.ndarray:
    points, _ = _annotation_points(
        annotations["jaw_endpoint_annotations"]["targets"],
        id_field="target_id",
    )
    _require(set(points) == set(ids), "v4 fit annotation membership changed")
    return np.asarray([points[target_id] for target_id in ids], dtype=np.float64)


def _observed_from_v3(
    annotations: dict[str, Any], ids: list[str]
) -> np.ndarray:
    points, _ = _annotation_points(
        annotations["fit_targets"], id_field="target_id"
    )
    _require(set(points) == set(ids), "v3 validation annotation membership changed")
    return np.asarray([points[target_id] for target_id in ids], dtype=np.float64)


def _projected_tips(
    physical: np.ndarray,
    candidate: dict[str, Any],
    camera: dict[str, Any],
    mapping: dict[str, Any],
    *,
    offset_rad: float,
) -> np.ndarray:
    values = np.asarray(
        [
            mapping["robot_board_yaw_rad"],
            *mapping["translation_xyz_m"],
        ],
        dtype=np.float64,
    )
    tips = _model_jaw_tips(
        physical, _candidate_with_offset(candidate, offset_rad)
    )
    pixels, _ = project_world_points(apply_planar_rigid(tips, values), camera)
    return pixels


def _score(
    physical: np.ndarray,
    observed: np.ndarray,
    candidate: dict[str, Any],
    camera: dict[str, Any],
    mapping: dict[str, Any],
    *,
    offset_rad: float,
) -> dict[str, Any]:
    projected = _projected_tips(
        physical,
        candidate,
        camera,
        mapping,
        offset_rad=offset_rad,
    )
    observed_aperture = np.linalg.norm(observed[:, 1] - observed[:, 0], axis=1)
    projected_aperture = np.linalg.norm(
        projected[:, 1] - projected[:, 0], axis=1
    )
    aperture_errors = projected_aperture - observed_aperture
    midpoint_errors = np.linalg.norm(
        np.mean(projected, axis=1) - np.mean(observed, axis=1), axis=1
    )
    return {
        "offset_rad": float(offset_rad),
        "observed_aperture_px": observed_aperture.tolist(),
        "projected_aperture_px": projected_aperture.tolist(),
        "aperture_errors_px": aperture_errors.tolist(),
        "aperture_rms_px": float(np.sqrt(np.mean(aperture_errors**2))),
        "midpoint_errors_px": midpoint_errors.tolist(),
        "midpoint_rms_px": float(np.sqrt(np.mean(midpoint_errors**2))),
        "projected_tip_pixels": projected.tolist(),
    }


def _relative_improvement(baseline: float, candidate: float) -> float:
    _require(baseline > 0.0, "baseline residual is not positive")
    return float((baseline - candidate) / baseline)


def _joint_range(
    physical_values: np.ndarray,
    *,
    scale: float,
    offset: float,
    minimum: float,
    maximum: float,
) -> dict[str, Any]:
    model_values = np.asarray(physical_values, dtype=np.float64) * scale + offset
    return {
        "minimum_model_rad": float(np.min(model_values)),
        "maximum_model_rad": float(np.max(model_values)),
        "passed": bool(
            np.all(model_values >= minimum) and np.all(model_values <= maximum)
        ),
    }


def evaluate_aperture_fit(
    contract: dict[str, Any], *, root: Path = REPO_ROOT
) -> tuple[dict[str, Any], dict[str, Any]]:
    sources = contract["sources"]
    camera = _bound_json(
        sources["or1_receipt"], root=root, label="OR1 receipt"
    )
    or2 = _bound_json(
        sources["or2_receipt"], root=root, label="OR2 receipt"
    )
    candidate_wrapper = _bound_json(
        sources["candidate_manifest"], root=root, label="candidate manifest"
    )
    base_candidate = candidate_wrapper["candidate_config"]

    fit_manifest = _bound_json(
        sources["fit_manifest"], root=root, label="fit manifest"
    )
    fit_rows = _load_jsonl(
        _bound_path(
            sources["fit_joint_samples"], root=root, label="fit joint samples"
        ),
        label="fit joint samples",
    )
    fit_ids, fit_physical = _physical_hold_means(
        fit_manifest, fit_rows, root=root
    )
    fit_observed = _observed_from_v4(
        _bound_json(
            sources["fit_annotations"], root=root, label="fit annotations"
        ),
        fit_ids,
    )
    mapping = or2["fit"]["parameters"]
    optimizer = contract["optimizer"]
    lower = float(optimizer["minimum_value"])
    upper = float(optimizer["maximum_value"])
    initial = float(optimizer["initial_value"])

    def residual(value: np.ndarray) -> np.ndarray:
        projected = _projected_apertures(
            fit_physical,
            base_candidate,
            camera,
            mapping,
            offset_rad=float(value[0]),
        )
        observed = np.linalg.norm(
            fit_observed[:, 1] - fit_observed[:, 0], axis=1
        )
        return projected - observed

    result = least_squares(
        residual,
        np.asarray([initial], dtype=np.float64),
        bounds=(
            np.asarray([lower], dtype=np.float64),
            np.asarray([upper], dtype=np.float64),
        ),
        max_nfev=int(optimizer["maximum_function_evaluations"]),
        ftol=float(optimizer["function_tolerance"]),
        xtol=float(optimizer["step_tolerance"]),
        gtol=float(optimizer["gradient_tolerance"]),
    )
    _require(bool(result.success), "jaw aperture fit did not converge")
    fitted_offset = float(result.x[0])
    fit_baseline = _score(
        fit_physical,
        fit_observed,
        base_candidate,
        camera,
        mapping,
        offset_rad=initial,
    )
    fit_candidate = _score(
        fit_physical,
        fit_observed,
        base_candidate,
        camera,
        mapping,
        offset_rad=fitted_offset,
    )
    fit_improvement = _relative_improvement(
        fit_baseline["aperture_rms_px"],
        fit_candidate["aperture_rms_px"],
    )

    # The candidate is fixed before the validation annotation object is opened.
    validation_manifest = _bound_json(
        sources["validation_manifest"], root=root, label="validation manifest"
    )
    validation_rows = _load_jsonl(
        _bound_path(
            sources["validation_joint_samples"],
            root=root,
            label="validation joint samples",
        ),
        label="validation joint samples",
    )
    validation_ids, validation_physical = _physical_hold_means(
        validation_manifest, validation_rows, root=root
    )
    _require(
        not set(fit_ids) & set(validation_ids),
        "fit/validation membership overlaps",
    )
    validation_observed = _observed_from_v3(
        _bound_json(
            sources["validation_annotations"],
            root=root,
            label="validation annotations",
        ),
        validation_ids,
    )
    validation_baseline = _score(
        validation_physical,
        validation_observed,
        base_candidate,
        camera,
        mapping,
        offset_rad=initial,
    )
    validation_candidate = _score(
        validation_physical,
        validation_observed,
        base_candidate,
        camera,
        mapping,
        offset_rad=fitted_offset,
    )
    validation_improvement = _relative_improvement(
        validation_baseline["aperture_rms_px"],
        validation_candidate["aperture_rms_px"],
    )

    range_gate = contract["joint_range_gate"]
    scale = float(contract["frozen_mechanisms"]["gripper_scale_rad_per_physical_unit"])
    joint_minimum = float(range_gate["model_gripper_minimum_rad"])
    joint_maximum = float(range_gate["model_gripper_maximum_rad"])
    c6_rows = _load_jsonl(
        _bound_path(
            sources["sealed_c6_physical_samples_for_range_only"],
            root=root,
            label="C6 physical samples",
        ),
        label="C6 physical samples",
    )
    c6_physical = np.asarray(
        [
            row[str(range_gate["c6_source_field"])][-1]
            for row in c6_rows
        ],
        dtype=np.float64,
    )
    range_checks = {
        "fit": _joint_range(
            fit_physical[:, -1],
            scale=scale,
            offset=fitted_offset,
            minimum=joint_minimum,
            maximum=joint_maximum,
        ),
        "validation": _joint_range(
            validation_physical[:, -1],
            scale=scale,
            offset=fitted_offset,
            minimum=joint_minimum,
            maximum=joint_maximum,
        ),
        "c6": _joint_range(
            c6_physical,
            scale=scale,
            offset=fitted_offset,
            minimum=joint_minimum,
            maximum=joint_maximum,
        ),
    }
    fit_gates = contract["fit_gates"]
    validation_gates = contract["validation_gates"]
    bound_margin = min(fitted_offset - lower, upper - fitted_offset)
    checks = {
        "fit_aperture_rms": fit_candidate["aperture_rms_px"]
        <= float(fit_gates["maximum_aperture_separation_rms_px"]),
        "fit_relative_improvement": fit_improvement
        >= float(fit_gates["minimum_relative_improvement"]),
        "parameter_bound_margin": bound_margin
        >= float(fit_gates["minimum_parameter_bound_margin_rad"]),
        "fit_midpoint_nonregression": (
            fit_candidate["midpoint_rms_px"]
            - fit_baseline["midpoint_rms_px"]
        )
        <= float(fit_gates["maximum_midpoint_rms_regression_px"]),
        "validation_aperture_rms": validation_candidate["aperture_rms_px"]
        <= float(validation_gates["maximum_aperture_separation_rms_px"]),
        "validation_relative_improvement": validation_improvement
        >= float(validation_gates["minimum_relative_improvement"]),
        "validation_midpoint_nonregression": (
            validation_candidate["midpoint_rms_px"]
            - validation_baseline["midpoint_rms_px"]
        )
        <= float(validation_gates["maximum_midpoint_rms_regression_px"]),
        "validation_candidate_refit_false": True,
        "fit_joint_range": range_checks["fit"]["passed"],
        "validation_joint_range": range_checks["validation"]["passed"],
        "c6_joint_range": range_checks["c6"]["passed"],
    }
    accepted = bool(all(checks.values()))
    candidate_config = _candidate_with_offset(base_candidate, fitted_offset)
    base_for_identity = copy.deepcopy(base_candidate)
    candidate_for_identity = copy.deepcopy(candidate_config)
    base_for_identity["physical_adapter"]["joint_transform"]["joints"][-1][
        "zero_offset"
    ] = fitted_offset
    only_parameter_changed = base_for_identity == candidate_for_identity
    checks["only_gripper_zero_offset_changed"] = only_parameter_changed
    accepted = bool(accepted and only_parameter_changed)
    candidate_manifest = {
        "schema_version": "sim2claw.observable_jaw_aperture_candidate.v1",
        "candidate_id": "observable-jaw-aperture-offset-v1",
        "base_candidate_sha256": canonical_digest(base_candidate),
        "candidate_config": candidate_config,
        "candidate_config_sha256": canonical_digest(candidate_config),
        "changed_parameter": {
            "name": "gripper_zero_offset_rad",
            "baseline": initial,
            "candidate": fitted_offset,
        },
        "scope": "task_bounded_gripper_aperture_mapping_only",
        "global_mapping_approved": False,
        "dynamic_replay_authorized": False,
    }
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "contract_sha256": (
            sha256_file(CONTRACT_PATH)
            if root == REPO_ROOT and CONTRACT_PATH.is_file()
            else canonical_digest(contract)
        ),
        "optimizer": {
            "success": bool(result.success),
            "status": int(result.status),
            "function_evaluations": int(result.nfev),
            "cost": float(result.cost),
            "optimality": float(result.optimality),
            "candidate_fixed_before_validation_open": True,
        },
        "parameter": {
            "name": "gripper_zero_offset_rad",
            "baseline_value": initial,
            "fitted_value": fitted_offset,
            "bound_margin_rad": float(bound_margin),
            "fit_from_task_outcome": False,
        },
        "fit": {
            "ids": fit_ids,
            "baseline": fit_baseline,
            "candidate": fit_candidate,
            "relative_improvement": fit_improvement,
        },
        "validation": {
            "ids": validation_ids,
            "opened_after_candidate_fit": True,
            "candidate_refit": False,
            "baseline": validation_baseline,
            "candidate": validation_candidate,
            "relative_improvement": validation_improvement,
        },
        "joint_range": range_checks,
        "candidate_manifest_sha256": canonical_digest(candidate_manifest),
        "checks": checks,
        "accepted": accepted,
        "result": (
            "TASK_BOUNDED_JAW_APERTURE_CANDIDATE_PROMOTED_GLOBAL_MAPPING_FALSE"
            if accepted
            else "JAW_APERTURE_CANDIDATE_REJECTED_GLOBAL_MAPPING_FALSE"
        ),
        "proof_boundaries": contract["proof_boundaries"],
        "authority": contract["authority"],
    }
    return {**unsigned, "artifact_sha256": canonical_digest(unsigned)}, candidate_manifest


def build_aperture_fit_receipt(
    contract_path: Path = CONTRACT_PATH,
    output_path: Path = OUTPUT_PATH,
    candidate_path: Path = CANDIDATE_PATH,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    contract = load_aperture_fit_contract(contract_path, root=root)
    receipt, candidate = evaluate_aperture_fit(contract, root=root)
    atomic_write_json(candidate_path, candidate)
    atomic_write_json(output_path, receipt)
    return receipt


__all__ = [
    "CANDIDATE_PATH",
    "CONTRACT_PATH",
    "OUTPUT_PATH",
    "build_aperture_fit_receipt",
    "evaluate_aperture_fit",
    "load_aperture_fit_contract",
]
