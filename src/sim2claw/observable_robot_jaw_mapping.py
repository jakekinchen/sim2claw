"""Fit robot/jaw mapping under an immutable bounded C922 camera."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import mujoco
import numpy as np
from scipy.optimize import least_squares

from .bidirectional_registration_v2_fit import _hold_means
from .grasp import _jaw_tip_point
from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
    sha256_file,
)
from .paths import REPO_ROOT
from .physical_canary import _physical_to_model_position
from .recorded_replay import _compile_model


SCHEMA = "sim2claw.observable_robot_jaw_mapping_contract.v1"
RECEIPT_SCHEMA = "sim2claw.observable_robot_jaw_mapping_receipt.v1"
CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "observable_robot_jaw_mapping_v1.json"
)
OUTPUT_PATH = (
    REPO_ROOT / "outputs" / "observable_robot_jaw_mapping_v1" / "receipt.json"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def _bound_path(binding: dict[str, Any], *, root: Path, label: str) -> Path:
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


def load_mapping_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="observable robot jaw mapping")
    _require(contract.get("schema_version") == SCHEMA, "unsupported mapping schema")
    sources = contract.get("sources")
    _require(isinstance(sources, dict) and sources, "mapping sources are missing")
    for source_id, binding in sources.items():
        _require(isinstance(binding, dict), f"invalid mapping source: {source_id}")
        _bound_path(binding, root=root, label=source_id)
    split = contract.get("split")
    _require(
        isinstance(split, dict)
        and int(split.get("fit_count", 0)) == 6
        and int(split.get("validation_count", 0)) == 4
        and split.get("fit_validation_overlap_allowed") is False
        and split.get("sealed_d1_to_d2_episode_used") is False,
        "mapping split changed",
    )
    camera = contract.get("camera_policy")
    _require(
        isinstance(camera, dict)
        and camera.get("refit_allowed") is False
        and camera.get("intrinsics_change_allowed") is False
        and camera.get("extrinsics_change_allowed") is False
        and camera.get("distortion_change_allowed") is False,
        "camera immutability changed",
    )
    family = contract.get("model_family")
    _require(
        isinstance(family, dict)
        and family.get("fit_parameters")
        == [
            "robot_board_yaw_rad",
            "translation_x_m",
            "translation_y_m",
            "translation_z_m",
        ],
        "mapping family changed",
    )
    _require(
        all(
            family.get(field) is False
            for field in (
                "joint_mapping_change_allowed",
                "jaw_geometry_change_allowed",
                "camera_change_allowed",
                "contact_parameter_change_allowed",
            )
        ),
        "mapping family widened",
    )
    boundaries = contract.get("proof_boundaries")
    authority = contract.get("authority")
    _require(
        isinstance(boundaries, dict) and boundaries and not any(boundaries.values()),
        "mapping proof boundary widened",
    )
    _require(
        isinstance(authority, dict) and authority and not any(authority.values()),
        "mapping authority widened",
    )
    return contract


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as error:
        raise FactoryArtifactError(f"cannot read joint samples: {error}") from error
    _require(rows and all(isinstance(row, dict) for row in rows), "joint samples are empty")
    return rows


def _annotation_points(
    rows: list[dict[str, Any]], *, id_field: str
) -> tuple[dict[str, np.ndarray], dict[str, dict[str, float]]]:
    points: dict[str, np.ndarray] = {}
    metrics: dict[str, dict[str, float]] = {}
    for row in rows:
        row_id = str(row[id_field])
        first = np.asarray(row["pass_a_tip_pixels"], dtype=np.float64)
        second = np.asarray(row["pass_b_tip_pixels"], dtype=np.float64)
        _require(first.shape == (2, 2) and second.shape == (2, 2), "jaw annotation shape changed")
        _require(row_id not in points, "duplicate jaw annotation")
        points[row_id] = (first + second) / 2.0
        metrics[row_id] = {
            "maximum_tip_disagreement_px": float(
                np.max(np.linalg.norm(first - second, axis=1))
            ),
            "midpoint_disagreement_px": float(
                np.linalg.norm(np.mean(first, axis=0) - np.mean(second, axis=0))
            ),
        }
    return points, metrics


def _model_jaw_tips(
    physical: np.ndarray, candidate: dict[str, Any]
) -> np.ndarray:
    model, _ = _compile_model(candidate, base_directory=None)
    data = mujoco.MjData(model)
    addresses = []
    for name in candidate["bindings"]["joint_names"]:
        joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        _require(joint_id >= 0, f"missing model joint: {name}")
        addresses.append(int(model.jnt_qposadr[joint_id]))
    moving_tips = [
        mujoco.mj_name2id(
            model,
            mujoco.mjtObj.mjOBJ_GEOM,
            f"left_moving_jaw_sph_tip{index}",
        )
        for index in (1, 2, 3)
    ]
    _require(all(item >= 0 for item in moving_tips), "moving jaw tip geometry is incomplete")
    model_positions = _physical_to_model_position(physical, candidate)
    result = []
    for row in model_positions:
        data.qpos[addresses] = row
        data.qvel[:] = 0.0
        mujoco.mj_forward(model, data)
        fixed = _jaw_tip_point(model, data, "left")
        moving = np.mean(data.geom_xpos[moving_tips], axis=0)
        result.append(np.stack((fixed, moving)))
    return np.asarray(result, dtype=np.float64)


def project_world_points(
    points_world: np.ndarray, camera_receipt: dict[str, Any]
) -> tuple[np.ndarray, np.ndarray]:
    camera = camera_receipt["physical_pinhole"]
    extrinsic = camera["task_world_extrinsic"]
    rotation = np.asarray(extrinsic["rotation_world_to_camera"], dtype=np.float64)
    translation = np.asarray(
        extrinsic["translation_world_to_camera_m"], dtype=np.float64
    )
    points = np.asarray(points_world, dtype=np.float64)
    camera_points = points @ rotation.T + translation
    focal = float(camera["focal_px"])
    principal = np.asarray(camera["principal_point_px"], dtype=np.float64)
    pixels = camera_points[..., :2] / camera_points[..., 2:3] * focal + principal
    return pixels, camera_points[..., 2]


def apply_planar_rigid(points: np.ndarray, values: np.ndarray) -> np.ndarray:
    yaw = float(values[0])
    cosine, sine = np.cos(yaw), np.sin(yaw)
    rotation = np.asarray(
        [[cosine, -sine, 0.0], [sine, cosine, 0.0], [0.0, 0.0, 1.0]]
    )
    return np.asarray(points, dtype=np.float64) @ rotation.T + values[1:4]


def fit_planar_rigid_mapping(
    model_points_world: np.ndarray,
    observed_pixels: np.ndarray,
    camera_receipt: dict[str, Any],
    *,
    lower: np.ndarray,
    upper: np.ndarray,
) -> dict[str, Any]:
    model_points = np.asarray(model_points_world, dtype=np.float64)
    observed = np.asarray(observed_pixels, dtype=np.float64)
    _require(
        model_points.ndim == 3
        and model_points.shape[1:] == (2, 3)
        and observed.shape == model_points.shape[:2] + (2,),
        "jaw fit shape changed",
    )

    def residual(values: np.ndarray) -> np.ndarray:
        corrected = apply_planar_rigid(model_points, values)
        projected, _ = project_world_points(corrected, camera_receipt)
        return (projected - observed).ravel()

    result = least_squares(
        residual,
        np.zeros(4, dtype=np.float64),
        bounds=(np.asarray(lower, dtype=np.float64), np.asarray(upper, dtype=np.float64)),
        x_scale="jac",
        max_nfev=20_000,
        ftol=1e-13,
        xtol=1e-13,
        gtol=1e-13,
    )
    _require(bool(result.success), "bounded robot jaw fit did not converge")
    corrected = apply_planar_rigid(model_points, result.x)
    projected, depths = project_world_points(corrected, camera_receipt)
    tip_errors = np.linalg.norm(projected - observed, axis=2)
    midpoint_error = np.linalg.norm(
        np.mean(projected, axis=1) - np.mean(observed, axis=1), axis=1
    )
    singular = np.linalg.svd(result.jac, compute_uv=False)
    return {
        "parameters": {
            "robot_board_yaw_rad": float(result.x[0]),
            "robot_board_yaw_degrees": float(np.degrees(result.x[0])),
            "translation_xyz_m": result.x[1:4].tolist(),
        },
        "projected_tip_pixels": projected.tolist(),
        "corrected_tip_world_m": corrected.tolist(),
        "depths_m": depths.tolist(),
        "tip_errors_px": tip_errors.tolist(),
        "tip_reprojection_rms_px": float(np.sqrt(np.mean(tip_errors**2))),
        "tip_reprojection_max_px": float(np.max(tip_errors)),
        "midpoint_errors_px": midpoint_error.tolist(),
        "midpoint_reprojection_rms_px": float(
            np.sqrt(np.mean(midpoint_error**2))
        ),
        "solver": {
            "success": bool(result.success),
            "cost": float(result.cost),
            "optimality": float(result.optimality),
            "jacobian_rank": int(np.linalg.matrix_rank(result.jac)),
            "jacobian_singular_values": singular.tolist(),
            "jacobian_condition_number": float(singular[0] / singular[-1]),
            "active_mask": result.active_mask.tolist(),
        },
    }


def _validation_physical_rows(
    open_receipt: dict[str, Any],
    annotations: dict[str, Any],
    joint_rows: list[dict[str, Any]],
) -> tuple[list[str], np.ndarray, np.ndarray, dict[str, dict[str, float]]]:
    observed, metrics = _annotation_points(annotations["members"], id_field="opaque_id")
    opened = {str(row["opaque_id"]): row for row in open_receipt["members"]}
    ordered = [str(row["opaque_id"]) for row in annotations["members"]]
    _require(set(ordered) == set(opened), "validation annotation membership changed")
    physical = []
    pixels = []
    for opaque_id in ordered:
        capture_path = Path(str(opened[opaque_id]["capture_receipt_path"]))
        _require(capture_path.is_file(), "validation capture receipt is missing")
        _require(
            sha256_file(capture_path)
            == opened[opaque_id]["capture_receipt_sha256"],
            "validation capture receipt changed",
        )
        capture = load_json_object(capture_path, label="validation capture")
        first = int(capture["scored_hold_first_host_continuous_ns"])
        last = int(capture["scored_hold_last_host_continuous_ns"])
        values = [
            row["actual_physical_units"]
            for row in joint_rows
            if first <= int(row["host_continuous_ns"]) <= last
        ]
        _require(
            len(values) == int(capture["scored_hold_sample_count"]),
            "validation hold sample count changed",
        )
        physical.append(np.mean(np.asarray(values, dtype=np.float64), axis=0))
        pixels.append(observed[opaque_id])
    return ordered, np.asarray(physical), np.asarray(pixels), metrics


def _score_fixed_candidate(
    model_points: np.ndarray,
    observed: np.ndarray,
    camera_receipt: dict[str, Any],
    parameters: dict[str, Any],
) -> dict[str, Any]:
    values = np.asarray(
        [
            parameters["robot_board_yaw_rad"],
            *parameters["translation_xyz_m"],
        ],
        dtype=np.float64,
    )
    corrected = apply_planar_rigid(model_points, values)
    projected, depths = project_world_points(corrected, camera_receipt)
    tip_errors = np.linalg.norm(projected - observed, axis=2)
    midpoint_error = np.linalg.norm(
        np.mean(projected, axis=1) - np.mean(observed, axis=1), axis=1
    )
    return {
        "candidate_refit": False,
        "projected_tip_pixels": projected.tolist(),
        "corrected_tip_world_m": corrected.tolist(),
        "depths_m": depths.tolist(),
        "tip_errors_px": tip_errors.tolist(),
        "tip_reprojection_rms_px": float(np.sqrt(np.mean(tip_errors**2))),
        "tip_reprojection_max_px": float(np.max(tip_errors)),
        "midpoint_errors_px": midpoint_error.tolist(),
        "midpoint_reprojection_rms_px": float(
            np.sqrt(np.mean(midpoint_error**2))
        ),
    }


def evaluate_mapping(
    contract: dict[str, Any], *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    sources = contract["sources"]
    camera_receipt = _bound_json(
        sources["or1_receipt"], root=root, label="OR1 receipt"
    )
    _require(
        camera_receipt.get("artifact_sha256")
        == contract["camera_policy"]["or1_artifact_sha256"],
        "OR1 camera artifact changed",
    )
    fit_annotations = _bound_json(
        sources["fit_annotations"], root=root, label="fit annotations"
    )
    fit_manifest = _bound_json(
        sources["fit_manifest"], root=root, label="fit manifest"
    )
    candidate_wrapper = _bound_json(
        sources["candidate_manifest"], root=root, label="candidate manifest"
    )
    candidate = candidate_wrapper["candidate_config"]
    fit_points, fit_annotation_metrics = _annotation_points(
        fit_annotations["jaw_endpoint_annotations"]["targets"],
        id_field="target_id",
    )
    fit_ids = [str(row["target_id"]) for row in fit_manifest["members"]]
    _require(
        len(fit_ids) == int(contract["split"]["fit_count"])
        and set(fit_ids) == set(fit_points),
        "fit membership changed",
    )
    hold_means = _hold_means(fit_annotations, fit_manifest)
    fit_physical = np.asarray([hold_means[target_id] for target_id in fit_ids])
    fit_model_tips = _model_jaw_tips(fit_physical, candidate)
    fit_observed = np.asarray([fit_points[target_id] for target_id in fit_ids])
    family = contract["model_family"]
    lower = np.asarray(
        [family["minimum_yaw_rad"], *family["minimum_translation_xyz_m"]]
    )
    upper = np.asarray(
        [family["maximum_yaw_rad"], *family["maximum_translation_xyz_m"]]
    )
    fit = fit_planar_rigid_mapping(
        fit_model_tips,
        fit_observed,
        camera_receipt,
        lower=lower,
        upper=upper,
    )
    annotation_gate = contract["annotation_gates"]
    fit_gates = contract["fit_gates"]
    parameter_values = np.asarray(
        [
            fit["parameters"]["robot_board_yaw_rad"],
            *fit["parameters"]["translation_xyz_m"],
        ]
    )
    bound_margin = np.minimum(parameter_values - lower, upper - parameter_values)
    fit_checks = {
        "annotation_tip_agreement": max(
            row["maximum_tip_disagreement_px"]
            for row in fit_annotation_metrics.values()
        )
        <= float(annotation_gate["maximum_tip_disagreement_px"]),
        "annotation_midpoint_agreement": max(
            row["midpoint_disagreement_px"]
            for row in fit_annotation_metrics.values()
        )
        <= float(annotation_gate["maximum_midpoint_disagreement_px"]),
        "tip_rms": fit["tip_reprojection_rms_px"]
        <= float(fit_gates["maximum_tip_reprojection_rms_px"]),
        "tip_max": fit["tip_reprojection_max_px"]
        <= float(fit_gates["maximum_tip_reprojection_max_px"]),
        "midpoint_rms": fit["midpoint_reprojection_rms_px"]
        <= float(fit_gates["maximum_midpoint_reprojection_rms_px"]),
        "jacobian_rank": int(fit["solver"]["jacobian_rank"])
        >= int(fit_gates["minimum_jacobian_rank"]),
        "jacobian_condition": float(fit["solver"]["jacobian_condition_number"])
        <= float(fit_gates["maximum_jacobian_condition_number"]),
        "parameter_bounds": float(np.min(bound_margin))
        >= float(fit_gates["minimum_parameter_bound_margin"]),
        "positive_depth": bool(np.all(np.asarray(fit["depths_m"]) > 0.0)),
    }
    fit["checks"] = fit_checks
    fit["accepted"] = bool(all(fit_checks.values()))

    validation_annotations = _bound_json(
        sources["validation_annotations"],
        root=root,
        label="validation annotations",
    )
    open_receipt = _bound_json(
        sources["validation_open_receipt"],
        root=root,
        label="validation open receipt",
    )
    joint_rows = _load_jsonl(
        _bound_path(sources["joint_samples"], root=root, label="joint samples")
    )
    validation_ids, validation_physical, validation_observed, validation_metrics = (
        _validation_physical_rows(
            open_receipt, validation_annotations, joint_rows
        )
    )
    _require(
        len(validation_ids) == int(contract["split"]["validation_count"])
        and not set(validation_ids) & set(fit_ids),
        "fit/validation split leaked",
    )
    validation_model_tips = _model_jaw_tips(validation_physical, candidate)
    validation = _score_fixed_candidate(
        validation_model_tips,
        validation_observed,
        camera_receipt,
        fit["parameters"],
    )
    validation_gates = contract["validation_gates"]
    validation_checks = {
        "annotation_tip_agreement": max(
            row["maximum_tip_disagreement_px"]
            for row in validation_metrics.values()
        )
        <= float(annotation_gate["maximum_tip_disagreement_px"]),
        "annotation_midpoint_agreement": max(
            row["midpoint_disagreement_px"]
            for row in validation_metrics.values()
        )
        <= float(annotation_gate["maximum_midpoint_disagreement_px"]),
        "tip_rms": validation["tip_reprojection_rms_px"]
        <= float(validation_gates["maximum_tip_reprojection_rms_px"]),
        "tip_max": validation["tip_reprojection_max_px"]
        <= float(validation_gates["maximum_tip_reprojection_max_px"]),
        "midpoint_rms": validation["midpoint_reprojection_rms_px"]
        <= float(validation_gates["maximum_midpoint_reprojection_rms_px"]),
        "candidate_refit_false": validation["candidate_refit"] is False,
        "positive_depth": bool(
            np.all(np.asarray(validation["depths_m"]) > 0.0)
        ),
    }
    validation["checks"] = validation_checks
    validation["accepted"] = bool(all(validation_checks.values()))
    validation["status"] = contract["split"]["validation_status"]

    static = _bound_json(
        sources["static_geometry_receipt"], root=root, label="static geometry"
    )
    channels = static["channels"]
    global_channels = {
        "board_camera": bool(
            camera_receipt["bounded_camera_world_model_accepted"]
        ),
        "fixed_base_robot": channels["fixed_base_robot"]["status"].startswith(
            "accepted"
        ),
        "articulated_upper_arm": bool(
            channels["articulated_keypoint_differential"]["upper_arm"]["passed"]
        ),
        "articulated_wrist": bool(
            channels["articulated_keypoint_differential"]["wrist"]["passed"]
        ),
        "robot_silhouette": bool(
            channels["robot_silhouette"]["all_diagnostic_gates_passed"]
        ),
        "jaw_tips": bool(fit["accepted"] and validation["accepted"]),
        "floor_support": channels["floor_and_support_plane"][
            "metric_scale_authority"
        ]
        is True,
    }
    _require(
        set(global_channels)
        == set(contract["global_mapping_mandatory_channels"]),
        "global mandatory channels changed",
    )
    global_approved = bool(all(global_channels.values()))
    task_bounded = bool(fit["accepted"] and validation["accepted"])
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "contract_sha256": (
            sha256_file(CONTRACT_PATH)
            if root == REPO_ROOT and CONTRACT_PATH.is_file()
            else canonical_digest(contract)
        ),
        "camera": {
            "artifact_sha256": camera_receipt["artifact_sha256"],
            "refit": False,
            "exact_intrinsics_approved": camera_receipt[
                "exact_intrinsic_calibration_approved"
            ],
        },
        "fit": {
            "ids": fit_ids,
            "model_tip_world_m": fit_model_tips.tolist(),
            "observed_tip_pixels": fit_observed.tolist(),
            **fit,
        },
        "validation": {
            "ids": validation_ids,
            "model_tip_world_m": validation_model_tips.tolist(),
            "observed_tip_pixels": validation_observed.tolist(),
            **validation,
        },
        "task_bounded_jaw_mapping_accepted": task_bounded,
        "global_channels": global_channels,
        "global_physical_model_mapping_approved": global_approved,
        "result": (
            "TASK_BOUNDED_JAW_MAPPING_ACCEPTED_GLOBAL_MAPPING_FALSE"
            if task_bounded and not global_approved
            else (
                "GLOBAL_MAPPING_APPROVED"
                if global_approved
                else "TERMINAL_JAW_MAPPING_NEGATIVE_GLOBAL_MAPPING_FALSE"
            )
        ),
        "proof_boundaries": contract["proof_boundaries"],
        "authority": contract["authority"],
    }
    return {**unsigned, "artifact_sha256": canonical_digest(unsigned)}


def build_mapping_receipt(
    contract_path: Path = CONTRACT_PATH,
    output_path: Path = OUTPUT_PATH,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    contract = load_mapping_contract(contract_path, root=root)
    receipt = evaluate_mapping(contract, root=root)
    atomic_write_json(output_path, receipt)
    return receipt


__all__ = [
    "CONTRACT_PATH",
    "OUTPUT_PATH",
    "apply_planar_rigid",
    "build_mapping_receipt",
    "evaluate_mapping",
    "fit_planar_rigid_mapping",
    "load_mapping_contract",
    "project_world_points",
]
