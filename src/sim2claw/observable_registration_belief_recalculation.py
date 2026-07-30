"""Recalculate bounded robot-side registration beliefs under OR13 geometry."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import mujoco
import numpy as np
from scipy.optimize import least_squares

from .grasp import _jaw_tip_point
from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
    sha256_file,
)
from .observable_registration_factor_isolation import (
    _load_observations,
    _score_pixels,
    apply_gripper_local_se3,
)
from .observable_robot_jaw_mapping import project_world_points
from .paths import REPO_ROOT
from .physical_canary import _physical_to_model_position
from .post_hackathon_home_workspace_geometry_camera import _candidate_spec
from .scene import scene_geometry


SCHEMA = "sim2claw.observable_registration_belief_recalculation_contract.v1"
RECEIPT_SCHEMA = (
    "sim2claw.observable_registration_belief_recalculation_receipt.v1"
)
CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "observable_registration_belief_recalculation_v1.json"
)
OUTPUT_PATH = (
    REPO_ROOT
    / "outputs"
    / "observable_registration_belief_recalculation_v1"
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
        _bound_path(binding, root=root, label=label),
        label=label,
    )


def load_belief_recalculation_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="belief recalculation contract")
    _require(contract.get("schema_version") == SCHEMA, "unsupported contract")
    sources = contract.get("sources")
    _require(isinstance(sources, dict) and len(sources) == 8, "sources changed")
    for source_id, binding in sources.items():
        _require(isinstance(binding, dict), f"invalid source: {source_id}")
        _bound_path(binding, root=root, label=source_id)
    split = contract.get("split")
    _require(
        isinstance(split, dict)
        and split.get("fit_pose_count") == 6
        and split.get("known_outcome_validation_pose_count") == 4
        and split.get("fit_validation_overlap_allowed") is False
        and split.get("validation_refit_allowed") is False
        and split.get("validation_is_pristine_heldout") is False,
        "split policy widened",
    )
    expected_families = [
        "base_height_residual_z_v1",
        "shoulder_pan_lift_zero_offsets_v1",
        "wrist_flex_roll_zero_offsets_v1",
        "gripper_local_height_v1",
    ]
    families = contract.get("candidate_families")
    _require(
        isinstance(families, list)
        and [row.get("family_id") for row in families] == expected_families,
        "candidate family set changed",
    )
    selection = contract.get("selection_policy")
    _require(
        isinstance(selection, dict)
        and selection.get("task_rows_allowed_in_fit") is False
        and selection.get("task_outcome_allowed_in_fit") is False
        and selection.get("contact_timing_allowed_in_fit") is False
        and selection.get("one_family_may_be_selected") is True
        and selection.get("selected_candidate_may_enter_dynamics") is False,
        "selection policy widened",
    )
    authority = contract.get("authority")
    promotion = contract.get("promotion")
    _require(
        isinstance(authority, dict) and authority and not any(authority.values()),
        "authority widened",
    )
    _require(
        isinstance(promotion, dict)
        and promotion.get("global_mapping_approved") is False
        and promotion.get("canonical_scene_replacement_allowed") is False,
        "promotion boundary widened",
    )
    return contract


@dataclass
class _Dataset:
    scene_path: Path
    candidate: dict[str, Any]
    pawn_height_m: float

    def __post_init__(self) -> None:
        self.model = _candidate_spec(
            self.scene_path,
            pawn_height_m=self.pawn_height_m,
        ).compile()
        self.data = mujoco.MjData(self.model)
        names = self.candidate["bindings"]["joint_names"]
        self.addresses = []
        for name in names:
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
            all(index >= 0 for index in self.moving_tips),
            "moving jaw tips are incomplete",
        )
        self.gripper_body = mujoco.mj_name2id(
            self.model, mujoco.mjtObj.mjOBJ_BODY, "left_gripper"
        )
        _require(self.gripper_body >= 0, "left gripper body is missing")

    def evaluate(
        self,
        physical: np.ndarray,
        *,
        zero_offset_updates: dict[int, float] | None = None,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        candidate = copy.deepcopy(self.candidate)
        if zero_offset_updates:
            joints = candidate["physical_adapter"]["joint_transform"]["joints"]
            for index, value in zero_offset_updates.items():
                joints[index]["zero_offset"] = float(value)
        model_positions = _physical_to_model_position(
            np.asarray(physical, dtype=np.float64),
            candidate,
        )
        tips: list[np.ndarray] = []
        origins: list[np.ndarray] = []
        rotations: list[np.ndarray] = []
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


def _camera_from_or13(receipt: dict[str, Any]) -> dict[str, Any]:
    pose = receipt["camera"]["world_pose"]
    diagnostic = receipt["camera"]["retained_pixel_orientation"]
    pooled = diagnostic["pooled_fit"]
    return {
        "physical_pinhole": {
            "focal_px": float(pooled["focal_px"]),
            "principal_point_px": list(diagnostic["principal_point_px"]),
            "task_world_extrinsic": {
                "rotation_world_to_camera": pose[
                    "rotation_world_to_camera_cv"
                ],
                "translation_world_to_camera_m": pose[
                    "translation_world_to_camera_cv_m"
                ],
            },
        }
    }


def _project(points: np.ndarray, camera: dict[str, Any]) -> np.ndarray:
    return project_world_points(points, camera)[0]


def _midpoint_residual(
    projected: np.ndarray, observed: np.ndarray
) -> np.ndarray:
    return (
        np.mean(projected, axis=1) - np.mean(observed, axis=1)
    ).reshape(-1)


def _relative_improvement(baseline: float, candidate: float) -> float:
    if baseline <= 1e-12:
        return 0.0
    return float((baseline - candidate) / baseline)


def _solver_summary(result: Any) -> dict[str, Any]:
    singular = np.linalg.svd(np.asarray(result.jac), compute_uv=False)
    tolerance = (
        np.finfo(np.float64).eps
        * max(np.asarray(result.jac).shape)
        * singular[0]
        if len(singular)
        else 0.0
    )
    rank = int(np.sum(singular > tolerance))
    condition = (
        float(singular[0] / singular[-1])
        if len(singular) and singular[-1] > 0.0
        else float("inf")
    )
    return {
        "success": bool(result.success),
        "cost": float(result.cost),
        "jacobian_rank": rank,
        "jacobian_singular_values": singular.tolist(),
        "jacobian_condition_number": condition,
        "active_mask": np.asarray(result.active_mask, dtype=int).tolist(),
    }


def _fit(
    residual: Any, lower: np.ndarray, upper: np.ndarray
) -> tuple[np.ndarray, dict[str, Any]]:
    result = least_squares(
        residual,
        np.zeros(len(lower), dtype=np.float64),
        bounds=(lower, upper),
        method="trf",
        x_scale="jac",
        max_nfev=500,
    )
    _require(bool(result.success), "static family fit did not converge")
    summary = _solver_summary(result)
    span = upper - lower
    margin = np.minimum(result.x - lower, upper - result.x)
    summary["minimum_bound_margin_fraction"] = float(np.min(margin / span))
    return np.asarray(result.x, dtype=np.float64), summary


def _family_points(
    family_id: str,
    values: np.ndarray,
    *,
    dataset: _Dataset,
    physical: np.ndarray,
) -> np.ndarray:
    tips, origins, rotations = dataset.evaluate(physical)
    if family_id == "base_height_residual_z_v1":
        return tips + np.asarray([0.0, 0.0, float(values[0])])
    if family_id == "shoulder_pan_lift_zero_offsets_v1":
        return dataset.evaluate(
            physical,
            zero_offset_updates={0: float(values[0]), 1: float(values[1])},
        )[0]
    if family_id == "wrist_flex_roll_zero_offsets_v1":
        return dataset.evaluate(
            physical,
            zero_offset_updates={3: float(values[0]), 4: float(values[1])},
        )[0]
    if family_id == "gripper_local_height_v1":
        correction = np.asarray(
            [0.0, 0.0, float(values[0]), 0.0, 0.0, 0.0],
            dtype=np.float64,
        )
        return apply_gripper_local_se3(
            tips, origins, rotations, correction
        )
    raise FactoryArtifactError(f"unknown family: {family_id}")


def _base_support_stack(
    dataset: _Dataset,
    scene: dict[str, Any],
) -> dict[str, Any]:
    model = dataset.model
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    base_body = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_BODY, "left_base"
    )
    clamp_body = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_BODY, "left_edge_clamp"
    )
    _require(base_body >= 0 and clamp_body >= 0, "support bodies missing")
    base_vertices: list[float] = []
    clamp_plate_tops: list[float] = []
    for geom_id in range(model.ngeom):
        body_id = int(model.geom_bodyid[geom_id])
        geom_type = int(model.geom_type[geom_id])
        if body_id == base_body and geom_type == int(
            mujoco.mjtGeom.mjGEOM_MESH
        ):
            mesh_id = int(model.geom_dataid[geom_id])
            start = int(model.mesh_vertadr[mesh_id])
            count = int(model.mesh_vertnum[mesh_id])
            vertices = np.asarray(model.mesh_vert[start : start + count])
            rotation = np.asarray(data.geom_xmat[geom_id]).reshape(3, 3)
            world = (
                vertices @ rotation.T
                + np.asarray(data.geom_xpos[geom_id])
            )
            base_vertices.extend(world[:, 2].tolist())
        if body_id == clamp_body and geom_type == int(
            mujoco.mjtGeom.mjGEOM_BOX
        ):
            size = np.asarray(model.geom_size[geom_id])
            if size[2] <= 0.02 and size[0] * size[1] >= 0.002:
                clamp_plate_tops.append(
                    float(data.geom_xpos[geom_id, 2] + size[2])
                )
    _require(base_vertices and clamp_plate_tops, "support geometry incomplete")
    base_minimum = float(min(base_vertices))
    clamp_top = float(max(clamp_plate_tops))
    geometry = scene_geometry(scene)
    return {
        "table_top_world_z_m": float(geometry.table_top),
        "clamp_plate_top_world_z_m": clamp_top,
        "base_mesh_minimum_world_z_m": base_minimum,
        "base_mesh_to_clamp_support_error_m": base_minimum - clamp_top,
        "left_base_origin_world_z_m": float(data.xpos[base_body, 2]),
    }


def _evaluate_family(
    family: dict[str, Any],
    *,
    dataset: _Dataset,
    camera: dict[str, Any],
    observations: dict[str, Any],
    gates: dict[str, Any],
    baseline_fit: dict[str, Any],
    baseline_validation: dict[str, Any],
) -> dict[str, Any]:
    family_id = str(family["family_id"])
    lower = np.asarray(family["minimum_values"], dtype=np.float64)
    upper = np.asarray(family["maximum_values"], dtype=np.float64)
    fit_physical = observations["fit_physical"]
    fit_observed = observations["fit_observed"]
    validation_physical = observations["validation_physical"]
    validation_observed = observations["validation_observed"]

    def projected(physical: np.ndarray, values: np.ndarray) -> np.ndarray:
        return _project(
            _family_points(
                family_id,
                values,
                dataset=dataset,
                physical=physical,
            ),
            camera,
        )

    values, solver = _fit(
        lambda row: _midpoint_residual(
            projected(fit_physical, row), fit_observed
        ),
        lower,
        upper,
    )
    fit_score = _score_pixels(projected(fit_physical, values), fit_observed)
    validation_score = _score_pixels(
        projected(validation_physical, values),
        validation_observed,
    )
    fit_improvement = _relative_improvement(
        baseline_fit["midpoint_rms_px"], fit_score["midpoint_rms_px"]
    )
    validation_improvement = _relative_improvement(
        baseline_validation["midpoint_rms_px"],
        validation_score["midpoint_rms_px"],
    )
    separation_regression = (
        validation_score["separation_vector_rms_px"]
        - baseline_validation["separation_vector_rms_px"]
    )

    lopo_rows: list[dict[str, Any]] = []
    for index, pose_id in enumerate(observations["fit_ids"]):
        mask = np.arange(len(fit_physical)) != index
        lopo_values, _ = _fit(
            lambda row, m=mask: _midpoint_residual(
                projected(fit_physical[m], row), fit_observed[m]
            ),
            lower,
            upper,
        )
        baseline_pixels = _project(
            dataset.evaluate(fit_physical[index : index + 1])[0],
            camera,
        )
        candidate_pixels = projected(
            fit_physical[index : index + 1], lopo_values
        )
        baseline_error = float(
            np.linalg.norm(
                np.mean(baseline_pixels[0], axis=0)
                - np.mean(fit_observed[index], axis=0)
            )
        )
        candidate_error = float(
            np.linalg.norm(
                np.mean(candidate_pixels[0], axis=0)
                - np.mean(fit_observed[index], axis=0)
            )
        )
        lopo_rows.append(
            {
                "pose_id": pose_id,
                "baseline_midpoint_error_px": baseline_error,
                "candidate_midpoint_error_px": candidate_error,
                "improvement_fraction": _relative_improvement(
                    baseline_error, candidate_error
                ),
            }
        )
    lopo_improvements = np.asarray(
        [row["improvement_fraction"] for row in lopo_rows],
        dtype=np.float64,
    )
    checks = {
        "fit_midpoint_improvement": fit_improvement
        >= float(gates["minimum_fit_midpoint_improvement_fraction"]),
        "validation_midpoint_improvement": validation_improvement
        >= float(gates["minimum_validation_midpoint_improvement_fraction"]),
        "validation_separation_regression": separation_regression
        <= float(gates["maximum_validation_separation_regression_px"]),
        "jacobian_full_rank": int(solver["jacobian_rank"]) == len(values),
        "jacobian_condition": float(solver["jacobian_condition_number"])
        <= float(gates["maximum_jacobian_condition_number"]),
        "bound_margin": float(solver["minimum_bound_margin_fraction"])
        >= float(gates["minimum_bound_margin_fraction"]),
        "lopo_improved_pose_count": int(np.sum(lopo_improvements > 0.0))
        >= int(gates["minimum_lopo_improved_pose_count"]),
        "lopo_median_improvement": float(np.median(lopo_improvements))
        >= float(gates["minimum_lopo_median_improvement_fraction"]),
    }
    return {
        "family_id": family_id,
        "parameter_names": list(family["parameter_names"]),
        "parameter_values": values.tolist(),
        "fit": fit_score,
        "known_outcome_validation": {
            **validation_score,
            "pristine_heldout": False,
            "promotion_eligible": False,
        },
        "fit_midpoint_improvement_fraction": fit_improvement,
        "validation_midpoint_improvement_fraction": validation_improvement,
        "validation_separation_regression_px": separation_regression,
        "leave_one_fit_pose_out": {
            "rows": lopo_rows,
            "improved_pose_count": int(np.sum(lopo_improvements > 0.0)),
            "median_improvement_fraction": float(
                np.median(lopo_improvements)
            ),
        },
        "solver": solver,
        "checks": checks,
        "accepted_for_one_static_contact_gate": bool(all(checks.values())),
        "canonical_parameter_update_authorized": False,
        "dynamic_replay_authorized": False,
    }


def evaluate_belief_recalculation(
    contract: dict[str, Any], *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    sources = contract["sources"]
    or13 = _bound_json(
        sources["or13_receipt"], root=root, label="OR13 receipt"
    )
    scene_path = _bound_path(
        sources["or13_scene"], root=root, label="OR13 scene"
    )
    scene = load_json_object(scene_path, label="OR13 scene")
    manifest = _bound_json(
        sources["or6_candidate"], root=root, label="OR6 candidate"
    )
    candidate = manifest["candidate_config"]
    dataset = _Dataset(
        scene_path,
        candidate,
        float(or13["board_object_geometry"]["pawn_height_m"]),
    )
    observations = _load_observations(contract, root=root)
    camera = _camera_from_or13(or13)
    fit_tips = dataset.evaluate(observations["fit_physical"])[0]
    validation_tips = dataset.evaluate(
        observations["validation_physical"]
    )[0]
    baseline_fit = _score_pixels(
        _project(fit_tips, camera), observations["fit_observed"]
    )
    baseline_validation = _score_pixels(
        _project(validation_tips, camera),
        observations["validation_observed"],
    )
    support = _base_support_stack(dataset, scene)
    support["gate_passed"] = abs(
        support["base_mesh_to_clamp_support_error_m"]
    ) <= float(
        contract["acceptance_gates"][
            "maximum_base_mesh_to_clamp_support_error_m"
        ]
    )
    results = [
        _evaluate_family(
            family,
            dataset=dataset,
            camera=camera,
            observations=observations,
            gates=contract["acceptance_gates"],
            baseline_fit=baseline_fit,
            baseline_validation=baseline_validation,
        )
        for family in contract["candidate_families"]
    ]
    accepted = [
        row
        for row in results
        if row["accepted_for_one_static_contact_gate"]
    ]
    selected = (
        min(
            accepted,
            key=lambda row: row["known_outcome_validation"][
                "midpoint_rms_px"
            ],
        )
        if accepted
        else None
    )
    status = (
        "PASS_ONE_STATIC_FAMILY_SELECTED_NO_PROMOTION"
        if selected is not None
        else "TERMINAL_NEGATIVE_NO_STABLE_STATIC_FAMILY"
    )
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "proof_class": contract["proof_class"],
        "status": status,
        "source_hashes": {
            source_id: binding["sha256"]
            for source_id, binding in sources.items()
        },
        "observation_split": {
            "fit_ids": observations["fit_ids"],
            "known_outcome_validation_ids": observations["validation_ids"],
            "fit_pose_count": len(observations["fit_ids"]),
            "known_outcome_validation_pose_count": len(
                observations["validation_ids"]
            ),
            "task_rows_used_for_fit": 0,
            "task_outcome_used_for_fit": False,
            "validation_refit_performed": False,
        },
        "camera": {
            "source": "OR13",
            "focal_px": camera["physical_pinhole"]["focal_px"],
            "center_fixed_from_owner_metrology": True,
            "refit_performed": False,
            "exact_intrinsics_approved": False,
        },
        "base_support_stack": support,
        "baseline": {
            "fit": baseline_fit,
            "known_outcome_validation": baseline_validation,
        },
        "families": results,
        "accepted_family_ids": [
            row["family_id"] for row in accepted
        ],
        "selected_family": (
            {
                "family_id": selected["family_id"],
                "parameter_names": selected["parameter_names"],
                "parameter_values": selected["parameter_values"],
                "selection_metric": "known_outcome_validation_midpoint_rms_px",
                "selection_value": selected["known_outcome_validation"][
                    "midpoint_rms_px"
                ],
            }
            if selected is not None
            else None
        ),
        "belief_updates": {
            "or13_geometry_retained": True,
            "large_global_base_height_shift_rejected_by_support_stack": bool(
                support["gate_passed"]
            ),
            "one_static_family_may_enter_frozen_contact_gate": selected
            is not None,
            "camera_intrinsics_remain_unapproved": True,
            "global_mapping_approved": False,
            "dynamic_replay_authorized": False,
        },
        "authority": contract["authority"],
        "promotion": contract["promotion"],
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    return receipt


def build_belief_recalculation_receipt(
    contract_path: Path = CONTRACT_PATH,
    output_path: Path = OUTPUT_PATH,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    contract = load_belief_recalculation_contract(
        contract_path, root=root
    )
    receipt = evaluate_belief_recalculation(contract, root=root)
    atomic_write_json(output_path, receipt)
    return receipt


def main() -> int:
    build_belief_recalculation_receipt()
    return 0

