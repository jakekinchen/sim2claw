"""Read-only static factor isolation for observable robot registration.

This diagnostic deliberately fits independent camera-frozen mechanism blocks.
It cannot promote a canonical camera, robot mapping, replay, or transfer claim.
"""

from __future__ import annotations

import copy
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import mujoco
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

from .bidirectional_registration_v2_fit import _hold_means
from .grasp import _jaw_tip_point
from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
    sha256_file,
)
from .observable_robot_jaw_mapping import (
    _annotation_points,
    _load_jsonl,
    _validation_physical_rows,
    apply_planar_rigid,
    project_world_points,
)
from .paths import REPO_ROOT
from .physical_canary import _physical_to_model_position
from .recorded_replay import _compile_model


SCHEMA = "sim2claw.observable_registration_factor_isolation_contract.v1"
RECEIPT_SCHEMA = "sim2claw.observable_registration_factor_isolation_receipt.v1"
CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "observable_registration_factor_isolation_v1.json"
)
OUTPUT_PATH = (
    REPO_ROOT
    / "outputs"
    / "observable_registration_factor_isolation_v1"
    / "receipt.json"
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
        _bound_path(binding, root=root, label=label),
        label=label,
    )


def load_factor_isolation_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="registration factor isolation")
    _require(contract.get("schema_version") == SCHEMA, "unsupported contract")
    _require(
        contract.get("proof_class")
        == "retrospective_known_outcome_static_factor_isolation_diagnostic",
        "proof class changed",
    )
    sources = contract.get("sources")
    expected_sources = {
        "or1_receipt",
        "or10_receipt",
        "or2_receipt",
        "or6_candidate",
        "fit_annotations",
        "fit_manifest",
        "validation_annotations",
        "validation_open_receipt",
        "joint_samples",
    }
    _require(
        isinstance(sources, dict) and set(sources) == expected_sources,
        "factor-isolation sources changed",
    )
    for source_id, binding in sources.items():
        _require(isinstance(binding, dict), f"invalid source: {source_id}")
        _bound_path(binding, root=root, label=source_id)
    _require(
        not any(
            token in str(binding.get("path", "")).lower()
            for binding in sources.values()
            for token in ("d1-to-d2", "c6", "rp04", "action", "outcome")
        ),
        "task action or outcome source entered static factor isolation",
    )

    split = contract.get("split")
    _require(
        isinstance(split, dict)
        and split.get("fit_pose_count") == 6
        and split.get("known_outcome_validation_pose_count") == 4
        and split.get("fit_validation_overlap_allowed") is False
        and split.get("validation_refit_allowed") is False
        and split.get("promotion_grade_heldout") is False
        and split.get("sealed_task_episode_used") is False,
        "split or evidence role changed",
    )
    cameras = contract.get("camera_candidates")
    _require(
        isinstance(cameras, list)
        and [item.get("camera_id") for item in cameras] == ["or1", "or10"]
        and all(item.get("refit_allowed") is False for item in cameras),
        "camera candidate policy changed",
    )
    families = contract.get("factor_blocks")
    _require(
        isinstance(families, list)
        and [item.get("block_id") for item in families]
        == ["base_b6", "joint_j2", "tool_w6"],
        "factor blocks changed",
    )
    _require(
        all(item.get("task_endpoint_in_objective") is False for item in families),
        "task endpoint entered a static objective",
    )
    promotion = contract.get("promotion")
    _require(
        isinstance(promotion, dict)
        and promotion.get("diagnostic_only") is True
        and promotion.get("canonical_parameter_update_allowed") is False
        and promotion.get("dynamic_replay_allowed") is False
        and promotion.get("global_mapping_approved") is False,
        "diagnostic promotion boundary widened",
    )
    boundaries = contract.get("proof_boundaries")
    authority = contract.get("authority")
    _require(
        isinstance(boundaries, dict) and boundaries and not any(boundaries.values()),
        "proof boundary widened",
    )
    _require(
        isinstance(authority, dict) and authority and not any(authority.values()),
        "authority widened",
    )
    return contract


def table_delta_to_world(
    delta_table_m: np.ndarray, *, table_yaw_degrees: float
) -> np.ndarray:
    """Convert a table-frame translation to the world frame.

    The frozen table convention is +X left, +Y backward/robotward, +Z up.
    """

    delta = np.asarray(delta_table_m, dtype=np.float64)
    _require(delta.shape == (3,), "table delta must have shape (3,)")
    yaw = math.radians(float(table_yaw_degrees))
    cosine, sine = math.cos(yaw), math.sin(yaw)
    rotation = np.asarray(
        [[cosine, -sine, 0.0], [sine, cosine, 0.0], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    return rotation @ delta


def apply_world_se3(
    points_world: np.ndarray,
    values: np.ndarray,
    *,
    table_yaw_degrees: float,
    pivot_world: np.ndarray | None = None,
) -> np.ndarray:
    """Apply a table-frame SE(3) correction about the named base pivot."""

    points = np.asarray(points_world, dtype=np.float64)
    parameters = np.asarray(values, dtype=np.float64)
    _require(parameters.shape == (6,), "base SE(3) values must have shape (6,)")
    table_rotation = Rotation.from_euler(
        "z", float(table_yaw_degrees), degrees=True
    ).as_matrix()
    local_rotation = Rotation.from_euler(
        "xyz", parameters[3:6], degrees=False
    ).as_matrix()
    world_rotation = table_rotation @ local_rotation @ table_rotation.T
    translation = table_delta_to_world(
        parameters[:3], table_yaw_degrees=table_yaw_degrees
    )
    pivot = (
        np.zeros(3, dtype=np.float64)
        if pivot_world is None
        else np.asarray(pivot_world, dtype=np.float64)
    )
    _require(pivot.shape == (3,), "base pivot must have shape (3,)")
    return (points - pivot) @ world_rotation.T + pivot + translation


def apply_gripper_local_se3(
    points_world: np.ndarray,
    gripper_origins_world: np.ndarray,
    gripper_rotations_world: np.ndarray,
    values: np.ndarray,
) -> np.ndarray:
    """Apply one rigid correction in each pose's modeled gripper frame."""

    points = np.asarray(points_world, dtype=np.float64)
    origins = np.asarray(gripper_origins_world, dtype=np.float64)
    rotations = np.asarray(gripper_rotations_world, dtype=np.float64)
    parameters = np.asarray(values, dtype=np.float64)
    _require(points.ndim == 3 and points.shape[1:] == (2, 3), "tip shape changed")
    _require(origins.shape == (len(points), 3), "gripper origin shape changed")
    _require(
        rotations.shape == (len(points), 3, 3),
        "gripper rotation shape changed",
    )
    _require(parameters.shape == (6,), "tool SE(3) values must have shape (6,)")
    local_rotation = Rotation.from_euler(
        "xyz", parameters[3:6], degrees=False
    ).as_matrix()
    local = np.einsum(
        "npj,njk->npk",
        points - origins[:, None, :],
        rotations,
    )
    corrected_local = local @ local_rotation.T + parameters[:3]
    return (
        np.einsum("npj,nkj->npk", corrected_local, rotations)
        + origins[:, None, :]
    )


@dataclass
class _KinematicDataset:
    candidate: dict[str, Any]

    def __post_init__(self) -> None:
        self.model, _ = _compile_model(self.candidate, base_directory=None)
        self.data = mujoco.MjData(self.model)
        self.addresses = []
        for name in self.candidate["bindings"]["joint_names"]:
            joint_id = mujoco.mj_name2id(
                self.model, mujoco.mjtObj.mjOBJ_JOINT, name
            )
            _require(joint_id >= 0, f"missing model joint: {name}")
            self.addresses.append(int(self.model.jnt_qposadr[joint_id]))
        self.moving_tips = [
            mujoco.mj_name2id(
                self.model,
                mujoco.mjtObj.mjOBJ_GEOM,
                f"left_moving_jaw_sph_tip{index}",
            )
            for index in (1, 2, 3)
        ]
        _require(
            all(item >= 0 for item in self.moving_tips),
            "moving jaw tip geometry is incomplete",
        )
        self.gripper_body = mujoco.mj_name2id(
            self.model, mujoco.mjtObj.mjOBJ_BODY, "left_gripper"
        )
        _require(self.gripper_body >= 0, "left gripper body is missing")
        self.base_body = mujoco.mj_name2id(
            self.model, mujoco.mjtObj.mjOBJ_BODY, "left_base"
        )
        _require(self.base_body >= 0, "left base body is missing")
        mujoco.mj_forward(self.model, self.data)
        self.base_origin_world = self.data.xpos[self.base_body].copy()

    def evaluate(
        self, physical: np.ndarray, *, body_offsets_rad: np.ndarray | None = None
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        candidate = self.candidate
        if body_offsets_rad is not None:
            offsets = np.asarray(body_offsets_rad, dtype=np.float64)
            _require(offsets.shape == (2,), "body offsets must have shape (2,)")
            candidate = copy.deepcopy(self.candidate)
            joints = candidate["physical_adapter"]["joint_transform"]["joints"]
            _require(
                [joint["simulator_joint"] for joint in joints[:2]]
                == ["left_shoulder_pan", "left_shoulder_lift"],
                "body joint order changed",
            )
            for index, value in enumerate(offsets):
                joints[index]["zero_offset"] = float(value)
        model_positions = _physical_to_model_position(
            np.asarray(physical, dtype=np.float64), candidate
        )
        tips = []
        origins = []
        rotations = []
        for row in model_positions:
            self.data.qpos[self.addresses] = row
            self.data.qvel[:] = 0.0
            mujoco.mj_forward(self.model, self.data)
            fixed = _jaw_tip_point(self.model, self.data, "left")
            moving = np.mean(self.data.geom_xpos[self.moving_tips], axis=0)
            tips.append(np.stack((fixed, moving)))
            origins.append(self.data.xpos[self.gripper_body].copy())
            rotations.append(
                self.data.xmat[self.gripper_body].reshape(3, 3).copy()
            )
        return (
            np.asarray(tips, dtype=np.float64),
            np.asarray(origins, dtype=np.float64),
            np.asarray(rotations, dtype=np.float64),
        )


def _camera_from_or10(receipt: dict[str, Any]) -> dict[str, Any]:
    camera = receipt["diagnostic_simulator_camera"]
    pooled = receipt["pooled_board_plane_candidate"]
    return {
        "physical_pinhole": {
            "focal_px": float(pooled["focal_px"]),
            "principal_point_px": list(pooled["principal_point_px"]),
            "task_world_extrinsic": {
                "rotation_world_to_camera": camera[
                    "rotation_world_to_camera_cv"
                ],
                "translation_world_to_camera_m": camera[
                    "translation_world_to_camera_cv_m"
                ],
            },
        }
    }


def _apply_mapping(
    points_world: np.ndarray, mapping: dict[str, Any]
) -> np.ndarray:
    values = np.asarray(
        [
            mapping["robot_board_yaw_rad"],
            *mapping["translation_xyz_m"],
        ],
        dtype=np.float64,
    )
    return apply_planar_rigid(points_world, values)


def _project(
    tips_model_world: np.ndarray,
    *,
    mapping: dict[str, Any],
    camera: dict[str, Any],
) -> np.ndarray:
    pixels, _ = project_world_points(
        _apply_mapping(tips_model_world, mapping),
        camera,
    )
    return pixels


def _rms(values: np.ndarray) -> float:
    array = np.asarray(values, dtype=np.float64)
    return float(np.sqrt(np.mean(array**2)))


def _score_pixels(
    projected: np.ndarray, observed: np.ndarray
) -> dict[str, float]:
    projected_array = np.asarray(projected, dtype=np.float64)
    observed_array = np.asarray(observed, dtype=np.float64)
    tip_distances = np.linalg.norm(projected_array - observed_array, axis=2)
    midpoint_delta = np.mean(projected_array, axis=1) - np.mean(
        observed_array, axis=1
    )
    separation_delta = (
        projected_array[:, 1] - projected_array[:, 0]
    ) - (observed_array[:, 1] - observed_array[:, 0])
    centered_projected = projected_array - np.mean(
        projected_array.reshape(-1, 2), axis=0
    )
    centered_observed = observed_array - np.mean(
        observed_array.reshape(-1, 2), axis=0
    )
    centered_delta = centered_projected - centered_observed
    tool_objective = np.concatenate(
        (centered_delta.ravel(), separation_delta.ravel())
    )
    return {
        "tip_rms_px": _rms(tip_distances),
        "midpoint_rms_px": _rms(np.linalg.norm(midpoint_delta, axis=1)),
        "separation_vector_rms_px": _rms(separation_delta),
        "centered_tip_coordinate_rms_px": _rms(centered_delta),
        "tool_objective_rms_px": _rms(tool_objective),
    }


def _midpoint_residual(
    projected: np.ndarray, observed: np.ndarray
) -> np.ndarray:
    return (
        np.mean(projected, axis=1) - np.mean(observed, axis=1)
    ).ravel()


def _tool_residual(
    projected: np.ndarray, observed: np.ndarray
) -> np.ndarray:
    centered_projected = projected - np.mean(
        projected.reshape(-1, 2), axis=0
    )
    centered_observed = observed - np.mean(
        observed.reshape(-1, 2), axis=0
    )
    separation_delta = (
        projected[:, 1] - projected[:, 0]
    ) - (observed[:, 1] - observed[:, 0])
    return np.concatenate(
        (
            (centered_projected - centered_observed).ravel(),
            separation_delta.ravel(),
        )
    )


def _fit_block(
    residual: Callable[[np.ndarray], np.ndarray],
    *,
    lower: np.ndarray,
    upper: np.ndarray,
) -> tuple[np.ndarray, dict[str, Any]]:
    lower_values = np.asarray(lower, dtype=np.float64)
    upper_values = np.asarray(upper, dtype=np.float64)
    result = least_squares(
        residual,
        np.zeros_like(lower_values),
        bounds=(lower_values, upper_values),
        x_scale="jac",
        max_nfev=10_000,
        ftol=1e-12,
        xtol=1e-12,
        gtol=1e-12,
    )
    _require(bool(result.success), "factor block fit did not converge")
    singular = np.linalg.svd(result.jac, compute_uv=False)
    rank = int(np.linalg.matrix_rank(result.jac))
    condition = (
        float(singular[0] / singular[-1])
        if singular.size and singular[-1] > 0.0
        else float("inf")
    )
    span = upper_values - lower_values
    margin_fraction = np.minimum(
        (result.x - lower_values) / span,
        (upper_values - result.x) / span,
    )
    return result.x, {
        "success": bool(result.success),
        "cost": float(result.cost),
        "optimality": float(result.optimality),
        "jacobian_rank": rank,
        "jacobian_singular_values": singular.tolist(),
        "jacobian_condition_number": condition,
        "active_mask": result.active_mask.tolist(),
        "minimum_bound_margin_fraction": float(np.min(margin_fraction)),
    }


def _effective_composed_base(
    *,
    or2_mapping: dict[str, Any],
    residual_values: np.ndarray,
    base_pivot_model_world: np.ndarray,
    table_yaw_degrees: float,
) -> dict[str, Any]:
    """Return the OR2-plus-residual transform relative to canonical model world."""

    yaw = float(or2_mapping["robot_board_yaw_rad"])
    cosine, sine = math.cos(yaw), math.sin(yaw)
    or2_rotation = np.asarray(
        [[cosine, -sine, 0.0], [sine, cosine, 0.0], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    or2_translation = np.asarray(
        or2_mapping["translation_xyz_m"], dtype=np.float64
    )
    table_rotation = Rotation.from_euler(
        "z", float(table_yaw_degrees), degrees=True
    ).as_matrix()
    residual_rotation_local = Rotation.from_euler(
        "xyz", np.asarray(residual_values, dtype=np.float64)[3:6]
    ).as_matrix()
    residual_rotation = (
        table_rotation @ residual_rotation_local @ table_rotation.T
    )
    residual_translation = table_delta_to_world(
        np.asarray(residual_values, dtype=np.float64)[:3],
        table_yaw_degrees=table_yaw_degrees,
    )
    pivot_after_or2 = (
        np.asarray(base_pivot_model_world, dtype=np.float64) @ or2_rotation.T
        + or2_translation
    )
    effective_rotation = residual_rotation @ or2_rotation
    effective_translation = (
        residual_rotation @ or2_translation
        - residual_rotation @ pivot_after_or2
        + pivot_after_or2
        + residual_translation
    )
    effective_rotation_table = (
        table_rotation.T @ effective_rotation @ table_rotation
    )
    effective_euler_table = Rotation.from_matrix(
        effective_rotation_table
    ).as_euler("xyz")
    return {
        "translation_world_xyz_m": effective_translation.tolist(),
        "rotation_table_rpy_rad": effective_euler_table.tolist(),
        "rotation_world_matrix": effective_rotation.tolist(),
        "pivot_after_or2_world_m": pivot_after_or2.tolist(),
    }


def _relative_improvement(baseline: float, candidate: float) -> float:
    _require(baseline > 0.0, "baseline residual must be positive")
    return float((baseline - candidate) / baseline)


def _block_bounds(
    contract: dict[str, Any], block_id: str
) -> tuple[np.ndarray, np.ndarray]:
    block = next(
        item for item in contract["factor_blocks"] if item["block_id"] == block_id
    )
    return (
        np.asarray(block["minimum_values"], dtype=np.float64),
        np.asarray(block["maximum_values"], dtype=np.float64),
    )


def _load_observations(
    contract: dict[str, Any], *, root: Path
) -> dict[str, Any]:
    sources = contract["sources"]
    fit_annotations = _bound_json(
        sources["fit_annotations"], root=root, label="fit annotations"
    )
    fit_manifest = _bound_json(
        sources["fit_manifest"], root=root, label="fit manifest"
    )
    fit_points, _ = _annotation_points(
        fit_annotations["jaw_endpoint_annotations"]["targets"],
        id_field="target_id",
    )
    fit_ids = [str(row["target_id"]) for row in fit_manifest["members"]]
    _require(
        len(fit_ids) == contract["split"]["fit_pose_count"]
        and set(fit_ids) == set(fit_points),
        "fit membership changed",
    )
    fit_physical_by_id = _hold_means(fit_annotations, fit_manifest)
    fit_physical = np.asarray(
        [fit_physical_by_id[target_id] for target_id in fit_ids],
        dtype=np.float64,
    )
    fit_observed = np.asarray(
        [fit_points[target_id] for target_id in fit_ids],
        dtype=np.float64,
    )
    validation_annotations = _bound_json(
        sources["validation_annotations"],
        root=root,
        label="validation annotations",
    )
    validation_open = _bound_json(
        sources["validation_open_receipt"],
        root=root,
        label="validation open receipt",
    )
    joint_rows = _load_jsonl(
        _bound_path(
            sources["joint_samples"], root=root, label="joint samples"
        )
    )
    validation_ids, validation_physical, validation_observed, _ = (
        _validation_physical_rows(
            validation_open,
            validation_annotations,
            joint_rows,
        )
    )
    _require(
        len(validation_ids)
        == contract["split"]["known_outcome_validation_pose_count"]
        and not set(validation_ids) & set(fit_ids),
        "fit/validation split leaked",
    )
    return {
        "fit_ids": fit_ids,
        "fit_physical": fit_physical,
        "fit_observed": fit_observed,
        "validation_ids": validation_ids,
        "validation_physical": validation_physical,
        "validation_observed": validation_observed,
    }


def _evaluate_camera(
    contract: dict[str, Any],
    *,
    camera_id: str,
    camera: dict[str, Any],
    mapping: dict[str, Any],
    kinematics: _KinematicDataset,
    observations: dict[str, Any],
) -> dict[str, Any]:
    fit_physical = observations["fit_physical"]
    validation_physical = observations["validation_physical"]
    fit_observed = observations["fit_observed"]
    validation_observed = observations["validation_observed"]
    fit_tips, fit_origins, fit_rotations = kinematics.evaluate(fit_physical)
    validation_tips, validation_origins, validation_rotations = (
        kinematics.evaluate(validation_physical)
    )
    fit_baseline_pixels = _project(
        fit_tips, mapping=mapping, camera=camera
    )
    validation_baseline_pixels = _project(
        validation_tips, mapping=mapping, camera=camera
    )
    fit_baseline = _score_pixels(fit_baseline_pixels, fit_observed)
    validation_baseline = _score_pixels(
        validation_baseline_pixels, validation_observed
    )
    gates = contract["acceptance_gates"]
    table_yaw = float(contract["coordinate_frame"]["table_yaw_degrees"])
    mapped_base_pivot = _apply_mapping(
        kinematics.base_origin_world.reshape(1, 3), mapping
    )[0]

    base_lower, base_upper = _block_bounds(contract, "base_b6")

    def base_fit_pixels(values: np.ndarray) -> np.ndarray:
        corrected = apply_world_se3(
            _apply_mapping(fit_tips, mapping),
            values,
            table_yaw_degrees=table_yaw,
            pivot_world=mapped_base_pivot,
        )
        return project_world_points(corrected, camera)[0]

    base_values, base_solver = _fit_block(
        lambda values: _midpoint_residual(
            base_fit_pixels(values), fit_observed
        ),
        lower=base_lower,
        upper=base_upper,
    )
    base_fit_projected = base_fit_pixels(base_values)
    base_validation_projected = project_world_points(
        apply_world_se3(
            _apply_mapping(validation_tips, mapping),
            base_values,
            table_yaw_degrees=table_yaw,
            pivot_world=mapped_base_pivot,
        ),
        camera,
    )[0]

    joint_lower, joint_upper = _block_bounds(contract, "joint_j2")

    def joint_projected(
        physical: np.ndarray, values: np.ndarray
    ) -> np.ndarray:
        tips, _, _ = kinematics.evaluate(
            physical, body_offsets_rad=values
        )
        return _project(tips, mapping=mapping, camera=camera)

    joint_values, joint_solver = _fit_block(
        lambda values: _midpoint_residual(
            joint_projected(fit_physical, values), fit_observed
        ),
        lower=joint_lower,
        upper=joint_upper,
    )
    joint_fit_projected = joint_projected(fit_physical, joint_values)
    joint_validation_projected = joint_projected(
        validation_physical, joint_values
    )

    tool_lower, tool_upper = _block_bounds(contract, "tool_w6")

    def tool_projected(
        tips: np.ndarray,
        origins: np.ndarray,
        rotations: np.ndarray,
        values: np.ndarray,
    ) -> np.ndarray:
        corrected = apply_gripper_local_se3(
            tips, origins, rotations, values
        )
        return _project(corrected, mapping=mapping, camera=camera)

    tool_values, tool_solver = _fit_block(
        lambda values: _tool_residual(
            tool_projected(
                fit_tips,
                fit_origins,
                fit_rotations,
                values,
            ),
            fit_observed,
        ),
        lower=tool_lower,
        upper=tool_upper,
    )
    tool_fit_projected = tool_projected(
        fit_tips, fit_origins, fit_rotations, tool_values
    )
    tool_validation_projected = tool_projected(
        validation_tips,
        validation_origins,
        validation_rotations,
        tool_values,
    )

    branch_data = {
        "base_b6": (
            base_values,
            base_solver,
            base_fit_projected,
            base_validation_projected,
            "midpoint_rms_px",
            "separation_vector_rms_px",
        ),
        "joint_j2": (
            joint_values,
            joint_solver,
            joint_fit_projected,
            joint_validation_projected,
            "midpoint_rms_px",
            "separation_vector_rms_px",
        ),
        "tool_w6": (
            tool_values,
            tool_solver,
            tool_fit_projected,
            tool_validation_projected,
            "tool_objective_rms_px",
            "midpoint_rms_px",
        ),
    }
    branches: dict[str, Any] = {}
    for block_id, (
        values,
        solver,
        fit_projected,
        validation_projected,
        objective_key,
        regression_key,
    ) in branch_data.items():
        fit_score = _score_pixels(fit_projected, fit_observed)
        validation_score = _score_pixels(
            validation_projected, validation_observed
        )
        fit_improvement = _relative_improvement(
            fit_baseline[objective_key], fit_score[objective_key]
        )
        validation_improvement = _relative_improvement(
            validation_baseline[objective_key],
            validation_score[objective_key],
        )
        regression = (
            validation_score[regression_key]
            - validation_baseline[regression_key]
        )
        parameter_count = len(values)
        checks = {
            "fit_improvement": fit_improvement
            >= float(gates["minimum_fit_improvement_fraction"]),
            "known_outcome_validation_improvement": validation_improvement
            >= float(
                gates["minimum_known_outcome_validation_improvement_fraction"]
            ),
            "jacobian_full_rank": int(solver["jacobian_rank"])
            == parameter_count,
            "jacobian_condition": float(
                solver["jacobian_condition_number"]
            )
            <= float(gates["maximum_jacobian_condition_number"]),
            "bound_margin": float(
                solver["minimum_bound_margin_fraction"]
            )
            >= float(gates["minimum_bound_margin_fraction"]),
            "orthogonal_channel_regression": regression
            <= float(gates["maximum_orthogonal_regression_px"]),
        }
        effective_base = None
        if block_id == "base_b6":
            effective_base = _effective_composed_base(
                or2_mapping=mapping,
                residual_values=values,
                base_pivot_model_world=kinematics.base_origin_world,
                table_yaw_degrees=table_yaw,
            )
            effective_translation = np.asarray(
                effective_base["translation_world_xyz_m"],
                dtype=np.float64,
            )
            effective_rpy = np.asarray(
                effective_base["rotation_table_rpy_rad"],
                dtype=np.float64,
            )
            effective_limits = gates["effective_composed_base_limits"]
            checks["effective_translation_bounds"] = bool(
                np.all(
                    effective_translation
                    >= np.asarray(
                        effective_limits["minimum_translation_world_xyz_m"],
                        dtype=np.float64,
                    )
                )
                and np.all(
                    effective_translation
                    <= np.asarray(
                        effective_limits["maximum_translation_world_xyz_m"],
                        dtype=np.float64,
                    )
                )
            )
            checks["effective_rotation_bounds"] = bool(
                np.all(
                    effective_rpy
                    >= np.asarray(
                        effective_limits["minimum_rotation_table_rpy_rad"],
                        dtype=np.float64,
                    )
                )
                and np.all(
                    effective_rpy
                    <= np.asarray(
                        effective_limits["maximum_rotation_table_rpy_rad"],
                        dtype=np.float64,
                    )
                )
            )
        branches[block_id] = {
            "parameters": values.tolist(),
            "parameter_count": parameter_count,
            "objective_metric": objective_key,
            "orthogonal_regression_metric": regression_key,
            "fit": fit_score,
            "known_outcome_validation": {
                **validation_score,
                "pristine_heldout": False,
                "promotion_eligible": False,
            },
            "fit_improvement_fraction": fit_improvement,
            "known_outcome_validation_improvement_fraction": (
                validation_improvement
            ),
            "orthogonal_validation_regression_px": regression,
            "solver": solver,
            "checks": checks,
            "numerically_accepted": bool(all(checks.values())),
            "candidate_refit_on_validation": False,
            "canonical_parameter_update_authorized": False,
            "effective_composed_base": effective_base,
        }
    numeric_ranking = sorted(
        branches,
        key=lambda block_id: branches[block_id][
            "known_outcome_validation_improvement_fraction"
        ],
        reverse=True,
    )
    return {
        "camera_id": camera_id,
        "baseline": {
            "fit": fit_baseline,
            "known_outcome_validation": validation_baseline,
        },
        "branches": branches,
        "numeric_argmin_ranking": numeric_ranking,
        "numeric_argmin_candidate": numeric_ranking[0],
        "cross_family_objectives_directly_comparable": False,
        "admissible_candidates": [],
        "admissible_winner": None,
    }


def evaluate_factor_isolation(
    contract: dict[str, Any], *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    sources = contract["sources"]
    or1 = _bound_json(
        sources["or1_receipt"], root=root, label="OR1 receipt"
    )
    or10 = _bound_json(
        sources["or10_receipt"], root=root, label="OR10 receipt"
    )
    _require(
        or10.get("simulator_canonical_camera_replaced") is False,
        "OR10 was incorrectly promoted to canonical camera",
    )
    or2 = _bound_json(
        sources["or2_receipt"], root=root, label="OR2 receipt"
    )
    candidate_wrapper = _bound_json(
        sources["or6_candidate"], root=root, label="OR6 candidate"
    )
    candidate = candidate_wrapper["candidate_config"]
    observations = _load_observations(contract, root=root)
    kinematics = _KinematicDataset(candidate)
    cameras = {
        "or1": or1,
        "or10": _camera_from_or10(or10),
    }
    results = {
        camera_id: _evaluate_camera(
            contract,
            camera_id=camera_id,
            camera=camera,
            mapping=or2["fit"]["parameters"],
            kinematics=kinematics,
            observations=observations,
        )
        for camera_id, camera in cameras.items()
    }
    camera_metrics = {
        "or1": {
            "board_rms_px": float(
                or1["physical_pinhole"]["reprojection_rms_px"]
            ),
            "board_max_px": float(
                or1["physical_pinhole"]["reprojection_max_px"]
            ),
        },
        "or10": {
            "board_rms_px": float(
                or10["pooled_board_plane_candidate"][
                    "reprojection_rms_px"
                ]
            ),
            "board_max_px": float(
                or10["pooled_board_plane_candidate"][
                    "reprojection_max_px"
                ]
            ),
        },
    }
    gates = contract["acceptance_gates"]
    for metrics in camera_metrics.values():
        metrics["board_gate_passed"] = bool(
            metrics["board_rms_px"]
            <= float(gates["maximum_camera_board_rms_px"])
            and metrics["board_max_px"]
            <= float(gates["maximum_camera_board_max_px"])
        )
    for camera_id, camera_result in results.items():
        camera_passed = camera_metrics[camera_id]["board_gate_passed"]
        camera_result["camera_prerequisite_passed"] = camera_passed
        admissible = [
            block_id
            for block_id, branch in camera_result["branches"].items()
            if camera_passed and branch["numerically_accepted"]
        ]
        camera_result["admissible_candidates"] = admissible
        # Orthogonal objectives with unequal parameter counts are not reduced
        # to one common scalar model-selection score.
        camera_result["admissible_winner"] = (
            admissible[0] if len(admissible) == 1 else None
        )
        camera_result["numeric_argmin_status"] = (
            "numeric_argmin_inadmissible_camera_prerequisite"
            if not camera_passed
            else (
                "numeric_argmin_admissible"
                if camera_result["numeric_argmin_candidate"] in admissible
                else "numeric_argmin_invalid_failed_block_gates"
            )
        )
    admissible_winners = [
        results[camera_id]["admissible_winner"]
        for camera_id in ("or1", "or10")
    ]
    same_admissible_winner = (
        admissible_winners[0] is not None
        and admissible_winners[0] == admissible_winners[1]
    )
    result = "CONFOUNDED_NO_PROMOTION"
    or2_world_translation = np.asarray(
        or2["fit"]["parameters"]["translation_xyz_m"], dtype=np.float64
    )
    table_yaw = float(contract["coordinate_frame"]["table_yaw_degrees"])
    table_rotation = Rotation.from_euler(
        "z", table_yaw, degrees=True
    ).as_matrix()
    or2_table_translation = table_rotation.T @ or2_world_translation
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "contract_sha256": (
            sha256_file(CONTRACT_PATH)
            if root == REPO_ROOT and CONTRACT_PATH.is_file()
            else canonical_digest(contract)
        ),
        "proof_class": contract["proof_class"],
        "source_roles": {
            "fit_pose_count": len(observations["fit_ids"]),
            "known_outcome_validation_pose_count": len(
                observations["validation_ids"]
            ),
            "promotion_grade_heldout_pose_count": 0,
            "sealed_task_episode_used": False,
            "action_or_outcome_data_used": False,
        },
        "coordinate_frame": {
            **contract["coordinate_frame"],
            "or2_world_translation_xyz_m": or2_world_translation.tolist(),
            "or2_translation_left_backward_up_m": (
                or2_table_translation.tolist()
            ),
        },
        "camera_board_metrics": camera_metrics,
        "camera_results": results,
        "cross_camera_attribution": {
            "numeric_argmin_candidates": [
                results[camera_id]["numeric_argmin_candidate"]
                for camera_id in ("or1", "or10")
            ],
            "admissible_winners": admissible_winners,
            "same_admissible_winner": same_admissible_winner,
            "uniquely_attributed": False,
            "reason": (
                "orthogonal objectives and unequal parameter counts are not "
                "a common model-selection score; OR1 also fails its camera "
                "prerequisite"
            ),
        },
        "result": result,
        "canonical_parameter_update_authorized": False,
        "dynamic_replay_authorized": False,
        "global_mapping_approved": False,
        "proof_boundaries": contract["proof_boundaries"],
        "authority": contract["authority"],
    }
    return {**unsigned, "artifact_sha256": canonical_digest(unsigned)}


def build_factor_isolation_receipt(
    contract_path: Path = CONTRACT_PATH,
    output_path: Path = OUTPUT_PATH,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    contract = load_factor_isolation_contract(contract_path, root=root)
    receipt = evaluate_factor_isolation(contract, root=root)
    atomic_write_json(output_path, receipt)
    return receipt


__all__ = [
    "apply_gripper_local_se3",
    "apply_world_se3",
    "build_factor_isolation_receipt",
    "evaluate_factor_isolation",
    "load_factor_isolation_contract",
    "table_delta_to_world",
]
