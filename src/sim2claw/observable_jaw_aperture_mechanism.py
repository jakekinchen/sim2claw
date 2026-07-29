"""Declare an identifiable single-parameter jaw-aperture mechanism."""

from __future__ import annotations

import copy
import json
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
from .observable_robot_jaw_mapping import (
    _annotation_points,
    _model_jaw_tips,
    apply_planar_rigid,
    project_world_points,
)
from .paths import REPO_ROOT


SCHEMA = "sim2claw.observable_jaw_aperture_mechanism_contract.v1"
RECEIPT_SCHEMA = "sim2claw.observable_jaw_aperture_mechanism_receipt.v1"
CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "observable_jaw_aperture_mechanism_v1.json"
)
OUTPUT_PATH = (
    REPO_ROOT
    / "outputs"
    / "observable_jaw_aperture_mechanism_v1"
    / "receipt.json"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def _bound_path(
    binding: dict[str, Any], *, root: Path, label: str
) -> Path:
    path = root / str(binding.get("path", ""))
    expected = str(binding.get("sha256", ""))
    _require(path.is_file(), f"{label} source is missing")
    _require(
        len(expected) == 64 and sha256_file(path) == expected,
        f"{label} hash drifted",
    )
    return path


def _bound_json(
    binding: dict[str, Any], *, root: Path, label: str
) -> dict[str, Any]:
    return load_json_object(
        _bound_path(binding, root=root, label=label), label=label
    )


def _load_jsonl(path: Path, *, label: str) -> list[dict[str, Any]]:
    try:
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as error:
        raise FactoryArtifactError(f"cannot read {label}: {error}") from error
    _require(rows and all(isinstance(row, dict) for row in rows), f"{label} is empty")
    return rows


def _resolve(path_value: str, *, root: Path) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else root / path


def _physical_hold_means(
    manifest: dict[str, Any],
    joint_rows: list[dict[str, Any]],
    *,
    root: Path,
) -> tuple[list[str], np.ndarray]:
    ids: list[str] = []
    physical: list[np.ndarray] = []
    for member in manifest["members"]:
        target_id = str(member.get("target_id", ""))
        _require(target_id and target_id not in ids, "hold target identity changed")
        receipt_path = _resolve(
            str(member["capture_receipt_path"]), root=root
        )
        _require(receipt_path.is_file(), "hold capture receipt is missing")
        _require(
            sha256_file(receipt_path)
            == str(member["capture_receipt_sha256"]),
            "hold capture receipt changed",
        )
        receipt = load_json_object(receipt_path, label="hold capture receipt")
        first = int(receipt["scored_hold_first_host_continuous_ns"])
        last = int(receipt["scored_hold_last_host_continuous_ns"])
        values = [
            row["actual_physical_units"]
            for row in joint_rows
            if first <= int(row["host_continuous_ns"]) <= last
        ]
        _require(
            len(values) == int(receipt["scored_hold_sample_count"]),
            "hold sample count changed",
        )
        ids.append(target_id)
        physical.append(np.mean(np.asarray(values, dtype=np.float64), axis=0))
    result = np.asarray(physical, dtype=np.float64)
    _require(result.shape == (len(ids), 6), "hold joint shape changed")
    return ids, result


def _candidate_with_offset(
    candidate: dict[str, Any], offset_rad: float
) -> dict[str, Any]:
    result = copy.deepcopy(candidate)
    joints = result["physical_adapter"]["joint_transform"]["joints"]
    _require(
        joints[-1]["simulator_joint"] == "left_gripper",
        "gripper transform order changed",
    )
    joints[-1]["zero_offset"] = float(offset_rad)
    return result


def _projected_apertures(
    physical: np.ndarray,
    candidate: dict[str, Any],
    camera_receipt: dict[str, Any],
    mapping_parameters: dict[str, Any],
    *,
    offset_rad: float,
) -> np.ndarray:
    values = np.asarray(
        [
            mapping_parameters["robot_board_yaw_rad"],
            *mapping_parameters["translation_xyz_m"],
        ],
        dtype=np.float64,
    )
    tips = _model_jaw_tips(
        physical, _candidate_with_offset(candidate, offset_rad)
    )
    corrected = apply_planar_rigid(tips, values)
    pixels, _ = project_world_points(corrected, camera_receipt)
    return np.linalg.norm(pixels[:, 1] - pixels[:, 0], axis=1)


def load_mechanism_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="observable jaw mechanism")
    _require(contract.get("schema_version") == SCHEMA, "unsupported mechanism schema")
    sources = contract.get("sources")
    _require(isinstance(sources, dict) and sources, "mechanism sources are missing")
    for source_id, binding in sources.items():
        _require(isinstance(binding, dict), f"invalid mechanism source: {source_id}")
        _bound_path(binding, root=root, label=source_id)
    split = contract.get("split")
    _require(
        isinstance(split, dict)
        and int(split.get("fit_count", 0)) == 6
        and int(split.get("validation_count", 0)) == 4
        and split.get("fit_validation_overlap_allowed") is False
        and split.get("validation_annotations_may_open_in_or5") is False
        and split.get("validation_candidate_refit_allowed") is False
        and split.get("sealed_d1_to_d2_task_outcome_used_for_fit") is False
        and split.get("outcome_informed_v4_heldout_is_promotion_eligible") is False,
        "mechanism split widened",
    )
    family = contract.get("model_family")
    _require(
        isinstance(family, dict)
        and family.get("fit_parameters") == ["gripper_zero_offset_rad"]
        and family.get("fit_objective") == "jaw_tip_pair_separation_pixels_only"
        and all(
            family.get(field) is False
            for field in (
                "camera_change_allowed",
                "robot_board_transform_change_allowed",
                "jaw_mesh_or_collision_geometry_change_allowed",
                "gripper_gain_change_allowed",
                "body_joint_mapping_change_allowed",
                "actuator_plant_change_allowed",
                "contact_parameter_change_allowed",
                "object_parameter_change_allowed",
            )
        ),
        "mechanism family widened",
    )
    rejected = contract.get("rejected_families")
    _require(
        isinstance(rejected, dict)
        and rejected
        and all(row.get("selected") is False for row in rejected.values()),
        "alternative family selection changed",
    )
    boundaries = contract.get("proof_boundaries")
    authority = contract.get("authority")
    _require(
        isinstance(boundaries, dict) and boundaries and not any(boundaries.values()),
        "mechanism proof boundary widened",
    )
    _require(
        isinstance(authority, dict) and authority and not any(authority.values()),
        "mechanism authority widened",
    )
    return contract


def evaluate_mechanism_declaration(
    contract: dict[str, Any], *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    sources = contract["sources"]
    fit_annotations = _bound_json(
        sources["fit_annotations"], root=root, label="fit annotations"
    )
    fit_manifest = _bound_json(
        sources["fit_manifest"], root=root, label="fit manifest"
    )
    fit_joint_rows = _load_jsonl(
        _bound_path(
            sources["fit_joint_samples"], root=root, label="fit joint samples"
        ),
        label="fit joint samples",
    )
    fit_ids, fit_physical = _physical_hold_means(
        fit_manifest, fit_joint_rows, root=root
    )
    annotated, _ = _annotation_points(
        fit_annotations["jaw_endpoint_annotations"]["targets"],
        id_field="target_id",
    )
    _require(set(fit_ids) == set(annotated), "fit annotations changed")

    validation_manifest = _bound_json(
        sources["validation_manifest"], root=root, label="validation manifest"
    )
    validation_joint_rows = _load_jsonl(
        _bound_path(
            sources["validation_joint_samples"],
            root=root,
            label="validation joint samples",
        ),
        label="validation joint samples",
    )
    validation_ids, validation_physical = _physical_hold_means(
        validation_manifest, validation_joint_rows, root=root
    )
    _require(
        not set(fit_ids) & set(validation_ids),
        "fit/validation membership overlaps",
    )

    camera = _bound_json(
        sources["or1_receipt"], root=root, label="OR1 receipt"
    )
    or2 = _bound_json(
        sources["or2_receipt"], root=root, label="OR2 receipt"
    )
    candidate_wrapper = _bound_json(
        sources["candidate_manifest"], root=root, label="candidate manifest"
    )
    candidate = candidate_wrapper["candidate_config"]
    family = contract["model_family"]
    baseline = float(family["baseline_gripper_zero_offset_rad"])
    step = float(family["static_sensitivity_step_rad"])
    lower_apertures = _projected_apertures(
        fit_physical,
        candidate,
        camera,
        or2["fit"]["parameters"],
        offset_rad=baseline - step,
    )
    upper_apertures = _projected_apertures(
        fit_physical,
        candidate,
        camera,
        or2["fit"]["parameters"],
        offset_rad=baseline + step,
    )
    sensitivity = (upper_apertures - lower_apertures) / (2.0 * step)
    fit_span = float(np.ptp(fit_physical[:, -1]))
    validation_span = float(np.ptp(validation_physical[:, -1]))
    gates = contract["or5_identifiability_gates"]
    checks = {
        "fit_pose_count": len(fit_ids) >= int(gates["minimum_fit_pose_count"]),
        "fit_validation_disjoint": not bool(set(fit_ids) & set(validation_ids)),
        "gain_unidentifiable_from_fit_span": fit_span
        <= float(gates["maximum_fit_gripper_span_physical_units"]),
        "offset_aperture_sensitivity": float(np.min(np.abs(sensitivity)))
        >= float(gates["minimum_absolute_aperture_sensitivity_px_per_rad"]),
        "same_sign_sensitivity": max(
            float(np.mean(sensitivity > 0.0)),
            float(np.mean(sensitivity < 0.0)),
        )
        >= float(gates["minimum_same_sign_sensitivity_fraction"]),
        "parameter_rank": 1 >= int(gates["minimum_parameter_rank"]),
        "validation_annotations_unopened": True,
        "sealed_task_outcome_unused": True,
    }
    accepted = bool(all(checks.values()))
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "contract_sha256": (
            sha256_file(CONTRACT_PATH)
            if root == REPO_ROOT and CONTRACT_PATH.is_file()
            else canonical_digest(contract)
        ),
        "fit": {
            "ids": fit_ids,
            "pose_count": len(fit_ids),
            "gripper_values_physical_units": fit_physical[:, -1].tolist(),
            "gripper_span_physical_units": fit_span,
            "minimum_aperture_sensitivity_px_per_rad": float(
                np.min(np.abs(sensitivity))
            ),
            "mean_aperture_sensitivity_px_per_rad": float(
                np.mean(sensitivity)
            ),
            "same_sign_sensitivity_fraction": float(
                max(np.mean(sensitivity > 0.0), np.mean(sensitivity < 0.0))
            ),
        },
        "validation_reservation": {
            "ids": validation_ids,
            "pose_count": len(validation_ids),
            "gripper_values_physical_units": validation_physical[:, -1].tolist(),
            "gripper_span_physical_units": validation_span,
            "annotations_opened": False,
            "candidate_refit_allowed": False,
        },
        "declared_model_family": family,
        "rejected_families": contract["rejected_families"],
        "checks": checks,
        "accepted": accepted,
        "result": (
            "SINGLE_GRIPPER_ZERO_OFFSET_APERTURE_MAPPING_IDENTIFIABLE"
            if accepted
            else "NO_IDENTIFIABLE_STATIC_JAW_APERTURE_MECHANISM"
        ),
        "proof_boundaries": contract["proof_boundaries"],
        "authority": contract["authority"],
    }
    return {**unsigned, "artifact_sha256": canonical_digest(unsigned)}


def build_mechanism_receipt(
    contract_path: Path = CONTRACT_PATH,
    output_path: Path = OUTPUT_PATH,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    contract = load_mechanism_contract(contract_path, root=root)
    receipt = evaluate_mechanism_declaration(contract, root=root)
    atomic_write_json(output_path, receipt)
    return receipt


__all__ = [
    "CONTRACT_PATH",
    "OUTPUT_PATH",
    "build_mechanism_receipt",
    "evaluate_mechanism_declaration",
    "load_mechanism_contract",
]
