#!/usr/bin/env python3
"""Fit AprilTag mounts constrained to measured CAD body surfaces."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

from tools.fit_pi_dual_link_tag_bundle import (
    HELDOUT,
    TAG1_TRAIN_NAMES,
    TAG2_TRAIN,
    Bundle,
    observation,
    public_row,
    transform,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE_CANDIDATE = (
    ROOT
    / "runs/pi-link-tag-calibration/"
    "20260726-dual-link-fit-v4-wrist-body/candidate.json"
)
TAG_SIZE_M = 0.020
OFFSET_BOUND_DEGREES = 8.0
TAG_RMSE_GATE_PX = 8.0
TAG_MAX_GATE_PX = 15.0
PARAMETER_ORDER = (
    "camera_rotvec_x",
    "camera_rotvec_y",
    "camera_rotvec_z",
    "camera_translation_x_m",
    "camera_translation_y_m",
    "camera_translation_z_m",
    "tag1_surface_x_m",
    "tag1_surface_y_m",
    "tag1_in_plane_rotation_rad",
    "tag2_surface_x_m",
    "tag2_surface_y_m",
    "tag2_in_plane_rotation_rad",
    "shoulder_pan_zero_offset_deg",
    "shoulder_lift_zero_offset_deg",
    "elbow_flex_zero_offset_deg",
    "wrist_flex_zero_offset_deg",
    "wrist_roll_zero_offset_deg",
)
SURFACES = {
    1: {
        "body": "left_upper_arm",
        "visual_mesh": "left_sts3215_03a_v1",
        "normal_axis_body": [0.0, 0.0, -1.0],
        "plane_z_body_m": -0.0015,
        "center_x_bounds_m": [-0.11497, -0.11017],
        "center_y_bounds_m": [-0.0282, -0.0028],
        "source": "visual-mesh bounds inset by the 10 mm tag half-edge",
    },
    2: {
        "body": "left_wrist",
        "visual_mesh": "left_sts3215_03a_no_horn_v1",
        "normal_axis_body": [0.0, 0.0, -1.0],
        "plane_z_body_m": 0.0079,
        "center_x_bounds_m": [-0.0024, 0.0024],
        "center_y_bounds_m": [-0.0526, -0.0330],
        "source": "visual-mesh bounds inset by the 10 mm tag half-edge",
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def surface_mount(tag_id: int, parameters: np.ndarray) -> np.ndarray:
    start = 6 if tag_id == 1 else 9
    center_x, center_y, angle = parameters[start : start + 3]
    cosine = math.cos(float(angle))
    sine = math.sin(float(angle))
    tag_x = np.asarray([-cosine, sine, 0.0])
    tag_y = np.asarray([sine, cosine, 0.0])
    value = np.eye(4)
    value[:3, :3] = np.column_stack(
        [tag_x, tag_y, np.asarray([0.0, 0.0, -1.0])]
    )
    value[:3, 3] = [
        center_x,
        center_y,
        SURFACES[tag_id]["plane_z_body_m"],
    ]
    return value


def project_row(
    bundle: Bundle, parameters: np.ndarray, row: dict[str, Any]
) -> np.ndarray:
    body = SURFACES[row["tag_id"]]["body"]
    camera_points = (
        transform(parameters[:3], parameters[3:6])
        @ bundle.body_pose(body, row["joint_degrees"], parameters[12:17])
        @ surface_mount(row["tag_id"], parameters)
        @ bundle.tag_points
    )[:3]
    normalized = camera_points[:2] / camera_points[2:3]
    return np.column_stack(
        [
            bundle.focal * normalized[0] + 768.0,
            bundle.focal * normalized[1] + 432.0,
        ]
    )


def pixel_residual(
    bundle: Bundle,
    parameters: np.ndarray,
    rows: list[dict[str, Any]],
) -> np.ndarray:
    return np.concatenate(
        [
            (project_row(bundle, parameters, row) - row["corners"]).ravel()
            for row in rows
        ]
    )


def parameter_bounds(seed_camera: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    lower = np.asarray(
        (seed_camera[:3] - 0.8).tolist()
        + (seed_camera[3:6] - 0.6).tolist()
        + [
            SURFACES[1]["center_x_bounds_m"][0],
            SURFACES[1]["center_y_bounds_m"][0],
            -math.pi,
            SURFACES[2]["center_x_bounds_m"][0],
            SURFACES[2]["center_y_bounds_m"][0],
            -math.pi,
        ]
        + [-OFFSET_BOUND_DEGREES] * 5
    )
    upper = np.asarray(
        (seed_camera[:3] + 0.8).tolist()
        + (seed_camera[3:6] + 0.6).tolist()
        + [
            SURFACES[1]["center_x_bounds_m"][1],
            SURFACES[1]["center_y_bounds_m"][1],
            math.pi,
            SURFACES[2]["center_x_bounds_m"][1],
            SURFACES[2]["center_y_bounds_m"][1],
            math.pi,
        ]
        + [OFFSET_BOUND_DEGREES] * 5
    )
    return lower, upper


def fit(
    bundle: Bundle,
    rows: list[dict[str, Any]],
    seed_camera: np.ndarray,
    *,
    seed_count: int = 16,
) -> tuple[np.ndarray, dict[str, float]]:
    lower, upper = parameter_bounds(seed_camera)
    rng = np.random.default_rng(20260726)
    best: tuple[float, np.ndarray, np.ndarray, float] | None = None

    def residual(parameters: np.ndarray) -> np.ndarray:
        return np.concatenate(
            [
                pixel_residual(bundle, parameters, rows),
                parameters[12:17] / 2.0,
            ]
        )

    for seed_index in range(seed_count):
        initial = np.asarray(
            seed_camera.tolist()
            + [
                np.mean(SURFACES[1]["center_x_bounds_m"]),
                np.mean(SURFACES[1]["center_y_bounds_m"]),
                rng.uniform(-math.pi, math.pi),
                np.mean(SURFACES[2]["center_x_bounds_m"]),
                np.mean(SURFACES[2]["center_y_bounds_m"]),
                rng.uniform(-math.pi, math.pi),
            ]
            + [0.0] * 5
        )
        if seed_index:
            initial[:3] += rng.normal(0.0, 0.15, 3)
            initial[3:6] += rng.normal(0.0, 0.08, 3)
        result = least_squares(
            residual,
            np.clip(initial, lower + 1e-8, upper - 1e-8),
            bounds=(lower, upper),
            loss="soft_l1",
            f_scale=2.0,
            max_nfev=8000,
        )
        corner_errors = np.concatenate(
            [
                np.linalg.norm(
                    project_row(bundle, result.x, row) - row["corners"], axis=1
                )
                for row in rows
            ]
        )
        score = float(np.sqrt(np.mean(corner_errors**2)))
        if best is None or score < best[0]:
            best = (
                score,
                result.x.copy(),
                corner_errors,
                float(result.optimality),
            )
    assert best is not None
    score, parameters, errors, optimality = best
    return parameters, {
        "corner_rmse_px": score,
        "corner_max_px": float(np.max(errors)),
        "optimizer_optimality": optimality,
        "seed_count": seed_count,
    }


def numerical_jacobian(
    bundle: Bundle,
    parameters: np.ndarray,
    rows: list[dict[str, Any]],
) -> np.ndarray:
    baseline = pixel_residual(bundle, parameters, rows)
    result = np.empty((len(baseline), len(parameters)), dtype=np.float64)
    for index in range(len(parameters)):
        step = 1e-6 * max(1.0, abs(float(parameters[index])))
        plus = parameters.copy()
        minus = parameters.copy()
        plus[index] += step
        minus[index] -= step
        result[:, index] = (
            pixel_residual(bundle, plus, rows)
            - pixel_residual(bundle, minus, rows)
        ) / (2.0 * step)
    return result


def identifiability(
    bundle: Bundle,
    parameters: np.ndarray,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    jacobian = numerical_jacobian(bundle, parameters, rows)
    singular_values = np.linalg.svd(jacobian, compute_uv=False)
    tolerance = singular_values[0] * max(jacobian.shape) * np.finfo(float).eps
    column_norms = np.linalg.norm(jacobian, axis=0)
    rank = int(np.sum(singular_values > tolerance))
    return {
        "parameter_count": len(parameters),
        "measurement_count": int(jacobian.shape[0]),
        "numerical_rank": rank,
        "full_column_rank": rank == len(parameters),
        "singular_values": singular_values.tolist(),
        "condition_number_nonzero": float(
            singular_values[0] / singular_values[rank - 1]
        ),
        "column_norms": {
            name: float(value)
            for name, value in zip(PARAMETER_ORDER, column_norms, strict=True)
        },
        "zero_sensitivity_parameters": [
            name
            for name, value in zip(PARAMETER_ORDER, column_norms, strict=True)
            if value < 1e-9
        ],
    }


def legacy_mount_parameters(parameters: np.ndarray, tag_id: int) -> dict[str, Any]:
    value = surface_mount(tag_id, parameters)
    prefix = "proximal" if tag_id == 1 else "distal"
    return {
        f"{prefix}_body_tag_rotation_vector_radians": Rotation.from_matrix(
            value[:3, :3]
        )
        .as_rotvec()
        .tolist(),
        f"{prefix}_body_tag_translation_m": value[:3, 3].tolist(),
    }


def freeze(output: Path) -> None:
    if output.exists():
        raise RuntimeError(f"refusing to overwrite {output}")
    source = json.loads(SOURCE_CANDIDATE.read_text(encoding="utf-8"))
    bundle = Bundle()
    bundle.set_focal(float(source["camera_model"]["focal_pixels"]))
    rows = [
        observation(name, directory, 2)
        for name, directory in TAG2_TRAIN.items()
    ]
    rows.extend(
        observation(name, TAG2_TRAIN[name], 1)
        for name in sorted(TAG1_TRAIN_NAMES)
    )
    source_parameters = source["parameters"]
    seed_camera = np.asarray(
        source_parameters["camera_world_rotation_vector_radians"]
        + source_parameters["camera_world_translation_m"]
    )
    parameters, metrics = fit(bundle, rows, seed_camera)
    candidate = {
        "schema_version": "sim2claw.pi_surface_tag_candidate.v1",
        "proof_class": "physical_static_cad_surface_tag_training_diagnostic_only",
        "status": "training_candidate_frozen_heldouts_unopened",
        "source_candidate": {
            "path": str(SOURCE_CANDIDATE),
            "sha256": sha256(SOURCE_CANDIDATE),
        },
        "camera_model": source["camera_model"],
        "tag_model": {
            "family": "tag36h11",
            "black_edge_m": TAG_SIZE_M,
            "proximal": {"id": 1, "body": SURFACES[1]["body"]},
            "distal": {"id": 2, "body": SURFACES[2]["body"]},
        },
        "surface_constraints": {
            str(tag_id): specification
            for tag_id, specification in SURFACES.items()
        },
        "training": [public_row(row) for row in rows],
        "training_metrics": metrics,
        "parameters": {
            "camera_world_rotation_vector_radians": parameters[:3].tolist(),
            "camera_world_translation_m": parameters[3:6].tolist(),
            **legacy_mount_parameters(parameters, 1),
            **legacy_mount_parameters(parameters, 2),
            "joint_zero_offsets_degrees": parameters[12:17].tolist(),
            "surface_parameter_vector": parameters.tolist(),
            "surface_parameter_order": list(PARAMETER_ORDER),
        },
        "identifiability": identifiability(bundle, parameters, rows),
        "frozen_gates": {
            "per_pose_corner_rmse_max_px": TAG_RMSE_GATE_PX,
            "per_pose_corner_max_px": TAG_MAX_GATE_PX,
            "full_column_rank_required": True,
            "all_heldout_poses_must_pass": True,
        },
        "authority": {
            "simulator_parameter_promotion": False,
            "policy": False,
            "physical_task": False,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(candidate, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(candidate, indent=2, sort_keys=True))


def evaluate(candidate_path: Path, output: Path) -> None:
    if output.exists():
        raise RuntimeError(f"refusing to overwrite {output}")
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    if (
        candidate.get("schema_version")
        != "sim2claw.pi_surface_tag_candidate.v1"
        or candidate.get("status")
        != "training_candidate_frozen_heldouts_unopened"
    ):
        raise RuntimeError("invalid frozen surface candidate")
    bundle = Bundle()
    bundle.set_focal(float(candidate["camera_model"]["focal_pixels"]))
    parameters = np.asarray(
        candidate["parameters"]["surface_parameter_vector"], dtype=np.float64
    )
    pose_results = []
    heldout_rows = []
    for pose_name in ("pose_h", "pose_l"):
        rows = [
            observation(pose_name, HELDOUT[pose_name], tag_id)
            for tag_id in (1, 2)
        ]
        heldout_rows.extend(rows)
        errors = np.concatenate(
            [
                np.linalg.norm(
                    project_row(bundle, parameters, row) - row["corners"], axis=1
                )
                for row in rows
            ]
        )
        rmse = float(np.sqrt(np.mean(errors**2)))
        maximum = float(np.max(errors))
        pose_results.append(
            {
                "name": pose_name,
                "corner_rmse_px": rmse,
                "corner_max_px": maximum,
                "passed": rmse <= TAG_RMSE_GATE_PX
                and maximum <= TAG_MAX_GATE_PX,
            }
        )
    passed = (
        all(row["passed"] for row in pose_results)
        and candidate["identifiability"]["full_column_rank"]
    )
    receipt = {
        "schema_version": "sim2claw.pi_surface_tag_evaluation.v1",
        "proof_class": "physical_static_cad_surface_tag_heldout_diagnostic_only",
        "status": (
            "heldout_gates_passed_no_automatic_promotion"
            if passed
            else "heldout_rejected_no_promotion"
        ),
        "candidate": {
            "path": str(candidate_path),
            "sha256": sha256(candidate_path),
        },
        "heldout": [public_row(row) for row in heldout_rows],
        "pose_results": pose_results,
        "full_column_rank": candidate["identifiability"]["full_column_rank"],
        "all_gates_passed": passed,
        "selection": {
            "promoted": False,
            "reason": (
                "All frozen gates passed, but this diagnostic has no promotion authority."
                if passed
                else "Heldout reprojection or identifiability failed."
            ),
        },
        "authority": {
            "simulator_parameter_promotion": False,
            "policy": False,
            "physical_task": False,
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("freeze", "evaluate"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--candidate", type=Path)
    arguments = parser.parse_args()
    if arguments.phase == "freeze":
        if arguments.candidate is not None:
            raise RuntimeError("--candidate is evaluation-only")
        freeze(arguments.output)
    else:
        if arguments.candidate is None:
            raise RuntimeError("--candidate is required for evaluation")
        evaluate(arguments.candidate, arguments.output)


if __name__ == "__main__":
    main()
