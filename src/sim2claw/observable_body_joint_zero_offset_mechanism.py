"""Audit a bounded body-joint zero-offset mechanism and validation reservation."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import numpy as np

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
    _load_jsonl,
    _physical_hold_means,
)
from .observable_robot_jaw_mapping import (
    _model_jaw_tips,
    apply_planar_rigid,
    project_world_points,
)
from .paths import REPO_ROOT


SCHEMA = "sim2claw.observable_body_joint_zero_offset_mechanism_contract.v1"
RECEIPT_SCHEMA = (
    "sim2claw.observable_body_joint_zero_offset_mechanism_receipt.v1"
)
CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "observable_body_joint_zero_offset_mechanism_v1.json"
)
OUTPUT_PATH = (
    REPO_ROOT
    / "outputs"
    / "observable_body_joint_zero_offset_mechanism_v1"
    / "receipt.json"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def load_body_joint_mechanism_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="body joint zero offset mechanism")
    _require(
        contract.get("schema_version") == SCHEMA,
        "unsupported body joint mechanism schema",
    )
    sources = contract.get("sources")
    _require(
        isinstance(sources, dict) and sources,
        "body joint mechanism sources are missing",
    )
    for source_id, binding in sources.items():
        _require(
            isinstance(binding, dict),
            f"invalid body joint mechanism source: {source_id}",
        )
        _bound_path(binding, root=root, label=source_id)
    family = contract.get("model_family")
    _require(
        isinstance(family, dict)
        and family.get("fit_parameters")
        == [
            "shoulder_pan_zero_offset_rad",
            "shoulder_lift_zero_offset_rad",
        ]
        and family.get("baseline_values_rad") == [0.0, 0.0]
        and all(
            family.get(field) is False
            for field in (
                "camera_change_allowed",
                "robot_board_rigid_change_allowed",
                "other_body_joint_change_allowed",
                "jaw_geometry_change_allowed",
                "contact_or_object_change_allowed",
                "action_or_timing_change_allowed",
            )
        ),
        "body joint mechanism family widened",
    )
    validation = contract.get("validation_policy")
    _require(
        isinstance(validation, dict)
        and validation.get("admissible_members") == []
        and validation.get("images_opened_by_this_evaluator") is False
        and validation.get("annotation_values_opened_by_this_evaluator")
        is False
        and validation.get("candidate_fit_authorized_if_reservation_fails")
        is False,
        "validation reservation widened",
    )
    promotion = contract.get("promotion")
    _require(
        isinstance(promotion, dict)
        and promotion.get(
            "requires_fit_identifiability_and_admissible_unopened_validation"
        )
        is True
        and all(
            promotion.get(field) is False
            for field in (
                "fit_parameter_values_authorized",
                "validation_open_authorized",
                "dynamic_replay_authorized",
                "global_mapping_approved",
            )
        ),
        "body joint mechanism promotion widened",
    )
    boundaries = contract.get("proof_boundaries")
    authority = contract.get("authority")
    _require(
        isinstance(boundaries, dict) and boundaries and not any(boundaries.values()),
        "body joint mechanism proof boundary widened",
    )
    _require(
        isinstance(authority, dict) and authority and not any(authority.values()),
        "body joint mechanism authority widened",
    )
    return contract


def _candidate_with_body_offsets(
    candidate: dict[str, Any], offsets_rad: np.ndarray
) -> dict[str, Any]:
    result = copy.deepcopy(candidate)
    joints = result["physical_adapter"]["joint_transform"]["joints"]
    _require(
        [joint["simulator_joint"] for joint in joints[:2]]
        == ["left_shoulder_pan", "left_shoulder_lift"],
        "body joint order changed",
    )
    for index, value in enumerate(np.asarray(offsets_rad, dtype=np.float64)):
        joints[index]["zero_offset"] = float(value)
    return result


def _projected_midpoints(
    physical: np.ndarray,
    candidate: dict[str, Any],
    camera: dict[str, Any],
    mapping: dict[str, Any],
    offsets_rad: np.ndarray,
) -> np.ndarray:
    values = np.asarray(
        [
            mapping["robot_board_yaw_rad"],
            *mapping["translation_xyz_m"],
        ],
        dtype=np.float64,
    )
    tips = _model_jaw_tips(
        physical,
        _candidate_with_body_offsets(candidate, offsets_rad),
    )
    pixels, _ = project_world_points(
        apply_planar_rigid(tips, values),
        camera,
    )
    return np.mean(pixels, axis=1)


def evaluate_body_joint_mechanism(
    contract: dict[str, Any], *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    sources = contract["sources"]
    or7a = _bound_json(
        sources["or7a_closeout"], root=root, label="OR7A closeout"
    )
    _require(
        or7a.get("result")
        == "LARGE_JAW_CENTER_OR_GLOBAL_WRIST_SPATIAL_GAP_REMAINS",
        "OR7A result changed",
    )
    fit_manifest = _bound_json(
        sources["fit_manifest"], root=root, label="fit manifest"
    )
    fit_rows = _load_jsonl(
        _bound_path(
            sources["fit_joint_samples"],
            root=root,
            label="fit joint samples",
        ),
        label="fit joint samples",
    )
    fit_ids, fit_physical = _physical_hold_means(
        fit_manifest, fit_rows, root=root
    )
    camera = _bound_json(
        sources["or1_receipt"], root=root, label="OR1 receipt"
    )
    or2 = _bound_json(
        sources["or2_receipt"], root=root, label="OR2 receipt"
    )
    candidate_wrapper = _bound_json(
        sources["or6_candidate"], root=root, label="OR6 candidate"
    )
    candidate = candidate_wrapper["candidate_config"]
    family = contract["model_family"]
    baseline = np.asarray(family["baseline_values_rad"], dtype=np.float64)
    step = float(family["static_sensitivity_step_rad"])
    jacobian_columns = []
    for index in range(2):
        delta = np.zeros(2, dtype=np.float64)
        delta[index] = step
        lower = _projected_midpoints(
            fit_physical,
            candidate,
            camera,
            or2["fit"]["parameters"],
            baseline - delta,
        )
        upper = _projected_midpoints(
            fit_physical,
            candidate,
            camera,
            or2["fit"]["parameters"],
            baseline + delta,
        )
        jacobian_columns.append(((upper - lower) / (2.0 * step)).ravel())
    jacobian = np.column_stack(jacobian_columns)
    singular_values = np.linalg.svd(jacobian, compute_uv=False)
    rank = int(np.linalg.matrix_rank(jacobian))
    condition = float(singular_values[0] / singular_values[-1])
    pan_span = float(np.ptp(fit_physical[:, 0]))
    lift_span = float(np.ptp(fit_physical[:, 1]))
    fit_design = contract["fit_design"]
    fit_checks = {
        "fit_pose_count": len(fit_ids) == int(fit_design["pose_count"]),
        "shoulder_pan_excitation": pan_span
        >= float(fit_design["minimum_shoulder_pan_span_degrees"]),
        "shoulder_lift_excitation": lift_span
        >= float(fit_design["minimum_shoulder_lift_span_degrees"]),
        "parameter_rank": rank >= int(fit_design["minimum_parameter_rank"]),
        "smallest_singular_value": float(singular_values[-1])
        >= float(fit_design["minimum_smallest_singular_value_px_per_rad"]),
        "jacobian_condition": condition
        <= float(fit_design["maximum_jacobian_condition_number"]),
        "fit_annotation_values_unopened": True,
        "sealed_task_contact_and_outcome_unused": True,
    }
    inventory = contract["validation_inventory"]
    admissible = [item for item in inventory if item["admissible"]]
    policy = contract["validation_policy"]
    validation_checks = {
        "minimum_admissible_unopened_pose_count": sum(
            int(item["pose_count"]) for item in admissible
        )
        >= int(policy["minimum_admissible_unopened_pose_count"]),
        "admissible_member_reservation_nonempty": bool(
            policy["admissible_members"]
        ),
        "images_unopened": policy["images_opened_by_this_evaluator"] is False,
        "annotation_values_unopened": (
            policy["annotation_values_opened_by_this_evaluator"] is False
        ),
        "reuse_forbidden_or_outcome_known_cohorts_excluded": all(
            item["admissible"] is False for item in inventory
        ),
    }
    fit_identifiable = bool(all(fit_checks.values()))
    validation_reserved = bool(all(validation_checks.values()))
    accepted = fit_identifiable and validation_reserved
    if accepted:
        result = "BODY_JOINT_ZERO_OFFSET_MECHANISM_DECLARED"
    elif fit_identifiable:
        result = (
            "FIT_IDENTIFIABLE_BUT_NO_ADMISSIBLE_UNOPENED_VALIDATION_COHORT"
        )
    else:
        result = "BODY_JOINT_ZERO_OFFSET_MECHANISM_NOT_IDENTIFIABLE"
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "contract_sha256": (
            sha256_file(CONTRACT_PATH)
            if root == REPO_ROOT and CONTRACT_PATH.is_file()
            else canonical_digest(contract)
        ),
        "declared_model_family": family,
        "fit_identifiability": {
            "ids": fit_ids,
            "pose_count": len(fit_ids),
            "shoulder_pan_span_degrees": pan_span,
            "shoulder_lift_span_degrees": lift_span,
            "jacobian_rank": rank,
            "jacobian_singular_values_px_per_rad": singular_values.tolist(),
            "jacobian_condition_number": condition,
            "checks": fit_checks,
            "accepted": fit_identifiable,
            "visual_annotation_values_opened": False,
        },
        "validation_reservation": {
            "inventory": inventory,
            "admissible_members": policy["admissible_members"],
            "admissible_pose_count": sum(
                int(item["pose_count"]) for item in admissible
            ),
            "checks": validation_checks,
            "accepted": validation_reserved,
            "images_opened": False,
            "annotation_values_opened": False,
        },
        "accepted": accepted,
        "result": result,
        "fit_parameter_values_produced": False,
        "proof_boundaries": contract["proof_boundaries"],
        "authority": contract["authority"],
    }
    return {**unsigned, "artifact_sha256": canonical_digest(unsigned)}


def build_body_joint_mechanism_receipt(
    contract_path: Path = CONTRACT_PATH,
    output_path: Path = OUTPUT_PATH,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    contract = load_body_joint_mechanism_contract(contract_path, root=root)
    receipt = evaluate_body_joint_mechanism(contract, root=root)
    atomic_write_json(output_path, receipt)
    return receipt
