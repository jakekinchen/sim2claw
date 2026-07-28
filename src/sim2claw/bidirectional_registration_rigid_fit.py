"""Fit the V4 projective camera plus one shared rigid robot-board correction."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import cv2
import numpy as np
from scipy.optimize import least_squares

from .bidirectional_registration_v2_fit import (
    _hold_means,
    _model_jaw_midpoints,
    _normalize,
    project,
)
from .bidirectional_registration_v2_route import _board_world_corners
from .paths import REPO_ROOT


class RigidRegistrationFitError(RuntimeError):
    """A fit-only input, seal, solver, or gate changed."""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bound(entry: Mapping[str, Any]) -> Path:
    raw = str(entry["path"])
    if "heldout" in raw.lower():
        raise RigidRegistrationFitError("heldout path is forbidden in fit")
    path = REPO_ROOT / raw
    if not path.is_file() or _sha(path) != entry["sha256"]:
        raise RigidRegistrationFitError(f"bound fit input changed: {path}")
    return path


def _json(entry: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(_bound(entry).read_text(encoding="utf-8"))


def _normalized_dlt(world: np.ndarray, image: np.ndarray) -> np.ndarray:
    if len(world) < 6 or world.shape[1] != 3 or image.shape != (len(world), 2):
        raise RigidRegistrationFitError("DLT correspondence shape changed")
    normalized_world, world_transform = _normalize(world)
    normalized_image, image_transform = _normalize(image)
    rows = []
    for xyz, uv in zip(normalized_world, normalized_image, strict=True):
        homogeneous = np.append(xyz, 1.0)
        u, v = uv
        rows.append(
            np.concatenate(
                (np.zeros(4), -homogeneous, v * homogeneous)
            )
        )
        rows.append(
            np.concatenate(
                (homogeneous, np.zeros(4), -u * homogeneous)
            )
        )
    _, _, right = np.linalg.svd(np.asarray(rows))
    normalized = right[-1].reshape(3, 4)
    camera = np.linalg.inv(image_transform) @ normalized @ world_transform
    if abs(float(camera[2, 3])) <= 1e-9:
        raise RigidRegistrationFitError("DLT scale anchor is degenerate")
    return camera / float(camera[2, 3])


def _lattice(
    annotations: Mapping[str, Any],
    candidate: Mapping[str, Any],
) -> tuple[np.ndarray, np.ndarray]:
    spec = annotations["board_lattice"]
    corners = np.asarray(spec["playing_corners_px"], dtype=np.float32)
    normalized_corners = np.asarray(
        [[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float32
    )
    homography = cv2.getPerspectiveTransform(normalized_corners, corners)
    indices = np.asarray(spec["direct_fit_intersection_indices"], dtype=int)
    normalized = np.column_stack((indices[:, 0] / 8.0, indices[:, 1] / 8.0))
    image = cv2.perspectiveTransform(
        normalized.astype(np.float32).reshape(-1, 1, 2),
        homography,
    ).reshape(-1, 2).astype(np.float64)
    corners_world = _board_world_corners(candidate, 0.3556)[
        np.asarray([1, 0, 3, 2])
    ]
    world = np.asarray(
        [
            (1 - u) * (1 - v) * corners_world[0]
            + u * (1 - v) * corners_world[1]
            + u * v * corners_world[2]
            + (1 - u) * v * corners_world[3]
            for u, v in normalized
        ],
        dtype=np.float64,
    )
    return world, image


def _task_plane_errors(
    camera: np.ndarray,
    observed: np.ndarray,
    corrected_world: np.ndarray,
) -> np.ndarray:
    errors = []
    for pixel, world in zip(observed, corrected_world, strict=True):
        u, v = pixel
        z = world[2]
        matrix = np.asarray(
            [
                [
                    camera[0, 0] - u * camera[2, 0],
                    camera[0, 1] - u * camera[2, 1],
                ],
                [
                    camera[1, 0] - v * camera[2, 0],
                    camera[1, 1] - v * camera[2, 1],
                ],
            ]
        )
        rhs = -np.asarray(
            [
                (camera[0, 2] - u * camera[2, 2]) * z
                + camera[0, 3]
                - u * camera[2, 3],
                (camera[1, 2] - v * camera[2, 2]) * z
                + camera[1, 3]
                - v * camera[2, 3],
            ]
        )
        xy = np.linalg.solve(matrix, rhs)
        errors.append(np.linalg.norm(xy - world[:2]) * 1000.0)
    return np.asarray(errors)


def evaluate(annotation_path: Path, output_root: Path) -> dict[str, Any]:
    annotations = json.loads(annotation_path.read_text(encoding="utf-8"))
    acquisition = _json(annotations["acquisition_contract"])
    inherited = _json(annotations["inherited_unchanged_gate_contract"])
    _json(annotations["prior_fit_only_board_lattice_seed"])
    fit_manifest = _json(annotations["fit_manifest"])
    candidate_wrapper = _json(annotations["candidate_manifest"])
    candidate = candidate_wrapper["candidate_config"]
    targets = annotations["jaw_endpoint_annotations"]["targets"]
    annotated = {str(row["target_id"]): row for row in targets}
    members = {str(row["target_id"]): row for row in fit_manifest["members"]}
    expected = [
        str(row["target_id"]) for row in acquisition["split"]["fit_targets"]
    ]
    if set(expected) != set(annotated) or set(expected) != set(members):
        raise RigidRegistrationFitError("fit split membership changed")
    for target_id in expected:
        member = members[target_id]
        image_path = Path(str(member["image_path"]))
        receipt_path = Path(str(member["capture_receipt_path"]))
        if (
            "heldout" in image_path.as_posix().lower()
            or "heldout" in receipt_path.as_posix().lower()
            or _sha(image_path) != member["image_sha256"]
            or _sha(receipt_path) != member["capture_receipt_sha256"]
            or member["image_sha256"] != annotated[target_id]["image_sha256"]
        ):
            raise RigidRegistrationFitError("fit member changed or crossed seal")

    helper_manifest = {
        "members": [
            {
                **members[target_id],
                "capture_receipt_path": str(
                    Path(members[target_id]["capture_receipt_path"]).resolve()
                ),
            }
            for target_id in expected
        ]
    }
    hold_means = _hold_means(annotations, helper_manifest)
    physical = np.asarray([hold_means[target_id] for target_id in expected])
    jaw_world = _model_jaw_midpoints(physical, candidate)
    observed = []
    tip_disagreements = []
    midpoint_disagreements = []
    annotation_rows = []
    for target_id in expected:
        row = annotated[target_id]
        first = np.asarray(row["pass_a_tip_pixels"], dtype=float)
        second = np.asarray(row["pass_b_tip_pixels"], dtype=float)
        tip_delta = np.linalg.norm(first - second, axis=1)
        midpoint_a = np.mean(first, axis=0)
        midpoint_b = np.mean(second, axis=0)
        midpoint = (midpoint_a + midpoint_b) / 2.0
        observed.append(midpoint)
        tip_disagreements.extend(tip_delta.tolist())
        midpoint_disagreements.append(float(np.linalg.norm(midpoint_a - midpoint_b)))
        annotation_rows.append(
            {
                "target_id": target_id,
                "frozen_midpoint_px": midpoint.tolist(),
                "maximum_tip_disagreement_px": float(np.max(tip_delta)),
                "midpoint_disagreement_px": midpoint_disagreements[-1],
                "physical_hold_mean_degrees_percent": hold_means[target_id].tolist(),
                "uncorrected_model_midpoint_world_m": jaw_world[
                    len(annotation_rows)
                ].tolist(),
            }
        )
    observed_array = np.asarray(observed)
    board_world, board_image = _lattice(annotations, candidate)
    initial_camera = _normalized_dlt(
        np.vstack((board_world, jaw_world)),
        np.vstack((board_image, observed_array)),
    )

    def unpack(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        camera = np.append(values[:11], 1.0).reshape(3, 4)
        yaw = values[11]
        cosine, sine = np.cos(yaw), np.sin(yaw)
        rotation = np.asarray(
            [[cosine, -sine, 0], [sine, cosine, 0], [0, 0, 1.0]]
        )
        corrected = jaw_world @ rotation.T + values[12:15]
        return camera, corrected

    def residual(values: np.ndarray) -> np.ndarray:
        camera, corrected = unpack(values)
        return np.concatenate(
            (
                (project(camera, board_world) - board_image).ravel(),
                (project(camera, corrected) - observed_array).ravel(),
            )
        )

    initial = np.concatenate((initial_camera.ravel()[:11], np.zeros(4)))
    lower = np.concatenate(
        (
            np.full(11, -1e5),
            [-np.deg2rad(20), -0.15, -0.15, -0.1],
        )
    )
    upper = np.concatenate(
        (
            np.full(11, 1e5),
            [np.deg2rad(20), 0.15, 0.15, 0.1],
        )
    )
    result = least_squares(
        residual,
        initial,
        bounds=(lower, upper),
        x_scale="jac",
        max_nfev=20000,
        ftol=1e-13,
        xtol=1e-13,
        gtol=1e-13,
    )
    if not result.success:
        raise RigidRegistrationFitError("bounded rigid fit did not converge")
    camera, corrected = unpack(result.x)
    pairs = residual(result.x).reshape(-1, 2)
    board_error = np.linalg.norm(pairs[: len(board_world)], axis=1)
    hover_error = np.linalg.norm(pairs[len(board_world) :], axis=1)
    task_error = _task_plane_errors(camera, observed_array, corrected)
    singular = np.linalg.svd(result.jac, compute_uv=False)
    rank = int(np.linalg.matrix_rank(result.jac))
    condition = float(singular[0] / singular[-1])
    yaw_degrees = float(np.rad2deg(result.x[11]))
    translation = result.x[12:15]
    inherited_gates = inherited["gates"]
    gates = acquisition["gates"]
    checks = {
        "annotation_tip_agreement": max(tip_disagreements)
        <= float(gates["maximum_annotation_tip_disagreement_px"]),
        "annotation_midpoint_agreement": max(midpoint_disagreements)
        <= float(gates["maximum_annotation_midpoint_disagreement_px"]),
        "board_lattice_rms": float(np.sqrt(np.mean(board_error**2)))
        <= float(inherited_gates["maximum_board_lattice_fit_rms_px"]),
        "board_lattice_max": float(np.max(board_error))
        <= float(inherited_gates["maximum_board_lattice_fit_max_px"]),
        "fit_hover_rms": float(np.sqrt(np.mean(hover_error**2)))
        <= float(gates["maximum_fit_hover_reprojection_rms_px"]),
        "fit_hover_max": float(np.max(hover_error))
        <= float(gates["maximum_fit_hover_reprojection_max_px"]),
        "fit_task_plane_rms": float(np.sqrt(np.mean(task_error**2)))
        < float(gates["maximum_fit_task_plane_rms_mm_exclusive"]),
        "fit_task_plane_max": float(np.max(task_error))
        < float(inherited_gates["maximum_fit_task_plane_max_mm_exclusive"]),
        "jacobian_full_rank": rank == 15,
        "jacobian_condition": condition
        <= float(inherited_gates["maximum_refinement_jacobian_condition_number"]),
        "yaw_bound": abs(yaw_degrees)
        <= float(inherited_gates["maximum_absolute_robot_board_yaw_degrees"]),
        "translation_xy_component_bounds": float(
            np.max(np.abs(translation[:2])) * 1000.0
        )
        <= float(inherited_gates["maximum_robot_board_translation_xy_mm"]),
        "translation_z_bound": abs(float(translation[2]) * 1000.0)
        <= float(inherited_gates["maximum_absolute_robot_board_translation_z_mm"])
        + 1e-6,
    }
    admitted = all(checks.values())
    output_root.mkdir(parents=True, exist_ok=False)
    candidate_payload = {
        "schema_version": "sim2claw.bidirectional_pawn_push_v2_rigid_registration_candidate.v1",
        "status": "fit_candidate_frozen" if admitted else "fit_candidate_rejected",
        "proof_class": "fit_only_registration_candidate",
        "annotation_sha256": _sha(annotation_path),
        "fit_manifest_sha256": annotations["fit_manifest"]["sha256"],
        "candidate_manifest_sha256": annotations["candidate_manifest"]["sha256"],
        "family_id": acquisition["candidate_family"]["family_id"],
        "camera_matrix_3x4": camera.tolist(),
        "robot_board_yaw_radians": float(result.x[11]),
        "robot_board_translation_xyz_m": translation.tolist(),
        "heldout_open_count": 0,
        "fit_only": True,
    }
    candidate_path = output_root / "candidate.json"
    candidate_path.write_text(
        json.dumps(candidate_payload, indent=2, sort_keys=True) + "\n"
    )
    receipt = {
        "schema_version": "sim2claw.bidirectional_pawn_push_v2_rigid_registration_fit_receipt.v1",
        "status": "fit_candidate_frozen" if admitted else "rejected_before_heldout",
        "proof_class": "fit_only_registration_candidate_evaluation",
        "annotation_path": str(annotation_path.relative_to(REPO_ROOT)),
        "annotation_sha256": _sha(annotation_path),
        "fit_manifest_sha256": annotations["fit_manifest"]["sha256"],
        "candidate_path": str(candidate_path),
        "candidate_sha256": _sha(candidate_path),
        "heldout_open_count": 0,
        "heldout_content_read": False,
        "annotations": {
            "targets": annotation_rows,
            "maximum_tip_disagreement_px": max(tip_disagreements),
            "maximum_midpoint_disagreement_px": max(midpoint_disagreements),
        },
        "board_fit": {
            "correspondence_count": len(board_world),
            "generation": annotations["board_lattice"]["intersection_generation"],
            "rms_px": float(np.sqrt(np.mean(board_error**2))),
            "max_px": float(np.max(board_error)),
        },
        "hover_fit": {
            "correspondence_count": len(jaw_world),
            "errors_px": hover_error.tolist(),
            "rms_px": float(np.sqrt(np.mean(hover_error**2))),
            "max_px": float(np.max(hover_error)),
        },
        "task_plane_fit": {
            "errors_mm": task_error.tolist(),
            "rms_mm": float(np.sqrt(np.mean(task_error**2))),
            "max_mm": float(np.max(task_error)),
        },
        "parameters": {
            "camera_matrix_3x4": camera.tolist(),
            "robot_board_yaw_degrees": yaw_degrees,
            "robot_board_translation_xyz_mm": (translation * 1000.0).tolist(),
            "active_bound_parameters": [
                "robot_board_translation_z"
                if abs(abs(float(translation[2])) - 0.1) <= 1e-6
                else None
            ],
        },
        "solver": {
            "success": bool(result.success),
            "cost": float(result.cost),
            "optimality": float(result.optimality),
            "jacobian_shape": list(result.jac.shape),
            "jacobian_rank": rank,
            "jacobian_singular_values": singular.tolist(),
            "jacobian_condition_number": condition,
        },
        "checks": checks,
        "fit_admitted_for_sealed_heldout_open": admitted,
        "claim_boundary": "Fit-only candidate; heldouts remain sealed and this grants no metric registration, simulator promotion, task, motion, or transfer success.",
    }
    receipt_path = output_root / "fit_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt
