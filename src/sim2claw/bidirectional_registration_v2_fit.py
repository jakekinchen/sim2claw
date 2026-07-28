"""Fit-only evaluator for bidirectional pawn-push v2 registration capture v1."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import mujoco
import numpy as np

from .bidirectional_registration_v2_route import _board_world_corners
from .grasp import _jaw_tip_point
from .paths import REPO_ROOT
from .physical_canary import _physical_to_model_position
from .recorded_replay import _compile_model


class RegistrationV2FitError(RuntimeError):
    """Raised when a frozen fit-only input or invariant is invalid."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_bytes())


def _bound(entry: Mapping[str, Any]) -> Path:
    path = REPO_ROOT / str(entry["path"])
    if not path.is_file() or sha256_file(path) != entry["sha256"]:
        raise RegistrationV2FitError(f"bound input changed: {path}")
    return path


def _normalize(points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    dimension = points.shape[1]
    center = np.mean(points, axis=0)
    rms = float(
        np.sqrt(np.mean(np.sum(np.square(points - center), axis=1)))
    )
    if not np.isfinite(rms) or rms <= 0.0:
        raise RegistrationV2FitError("normalization points are degenerate")
    scale = np.sqrt(float(dimension)) / rms
    transform = np.eye(dimension + 1, dtype=np.float64)
    transform[:dimension, :dimension] *= scale
    transform[:dimension, dimension] = -scale * center
    homogeneous = np.column_stack((points, np.ones(len(points)))) @ transform.T
    return homogeneous[:, :dimension], transform


def normalized_projective_dlt(
    world_xyz: np.ndarray,
    image_uv: np.ndarray,
) -> tuple[np.ndarray, float]:
    if world_xyz.shape != (8, 3) or image_uv.shape != (8, 2):
        raise RegistrationV2FitError("v1 DLT requires exactly eight 3D-to-2D pairs")
    world_normalized, world_transform = _normalize(world_xyz)
    image_normalized, image_transform = _normalize(image_uv)
    rows: list[np.ndarray] = []
    for xyz, uv in zip(world_normalized, image_normalized, strict=True):
        homogeneous = np.append(xyz, 1.0)
        u, v = uv
        rows.append(
            np.concatenate(
                (np.zeros(4, dtype=np.float64), -homogeneous, v * homogeneous)
            )
        )
        rows.append(
            np.concatenate(
                (homogeneous, np.zeros(4, dtype=np.float64), -u * homogeneous)
            )
        )
    design = np.asarray(rows, dtype=np.float64)
    _, singular, right = np.linalg.svd(design)
    # The final singular vector is the homogeneous DLT solution itself.
    # Conditioning therefore uses the largest-to-second-smallest ratio.
    condition = float(singular[0] / singular[-2])
    normalized_camera = right[-1].reshape(3, 4)
    camera = (
        np.linalg.inv(image_transform)
        @ normalized_camera
        @ world_transform
    )
    camera /= float(np.linalg.norm(camera[2, :3]))
    return camera, condition


def project(camera: np.ndarray, world_xyz: np.ndarray) -> np.ndarray:
    homogeneous = np.column_stack((world_xyz, np.ones(len(world_xyz))))
    pixels = homogeneous @ camera.T
    if np.any(np.abs(pixels[:, 2]) <= 1e-12):
        raise RegistrationV2FitError("candidate projects a point at infinity")
    return pixels[:, :2] / pixels[:, 2, None]


def _hold_means(
    annotations: Mapping[str, Any],
    fit_manifest: Mapping[str, Any],
) -> dict[str, np.ndarray]:
    telemetry_path = _bound(annotations["joint_samples"])
    samples = [
        json.loads(line)
        for line in telemetry_path.read_text().splitlines()
        if line.strip()
    ]
    result: dict[str, np.ndarray] = {}
    for member in fit_manifest["members"]:
        receipt_path = REPO_ROOT / member["capture_receipt_path"]
        if sha256_file(receipt_path) != member["capture_receipt_sha256"]:
            raise RegistrationV2FitError("fit capture receipt changed")
        receipt = _json(receipt_path)
        first = int(receipt["scored_hold_first_host_continuous_ns"])
        last = int(receipt["scored_hold_last_host_continuous_ns"])
        rows = [
            row["actual_physical_units"]
            for row in samples
            if first <= int(row["host_continuous_ns"]) <= last
        ]
        if len(rows) != int(receipt["scored_hold_sample_count"]):
            raise RegistrationV2FitError("scored hold sample count changed")
        result[member["target_id"]] = np.mean(
            np.asarray(rows, dtype=np.float64), axis=0
        )
    return result


def _model_jaw_midpoints(
    physical: np.ndarray,
    candidate: Mapping[str, Any],
) -> np.ndarray:
    model, _ = _compile_model(candidate, base_directory=None)
    data = mujoco.MjData(model)
    addresses = []
    for name in candidate["bindings"]["joint_names"]:
        joint_id = mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_JOINT, name
        )
        if joint_id < 0:
            raise RegistrationV2FitError(f"missing model joint: {name}")
        addresses.append(int(model.jnt_qposadr[joint_id]))
    moving_tips = [
        mujoco.mj_name2id(
            model,
            mujoco.mjtObj.mjOBJ_GEOM,
            f"left_moving_jaw_sph_tip{index}",
        )
        for index in (1, 2, 3)
    ]
    if any(item < 0 for item in moving_tips):
        raise RegistrationV2FitError("moving distal tip geometry is incomplete")
    model_positions = _physical_to_model_position(physical, candidate)
    midpoints = []
    for row in model_positions:
        data.qpos[addresses] = row
        data.qvel[:] = 0.0
        mujoco.mj_forward(model, data)
        fixed = _jaw_tip_point(model, data, "left")
        moving = np.mean(data.geom_xpos[moving_tips], axis=0)
        midpoints.append((fixed + moving) / 2.0)
    return np.asarray(midpoints, dtype=np.float64)


def evaluate_fit(
    annotation_path: Path,
    output_directory: Path,
) -> dict[str, Any]:
    annotations = _json(annotation_path)
    contract_path = _bound(annotations["acquisition_contract"])
    contract = _json(contract_path)
    fit_manifest_path = _bound(annotations["fit_manifest"])
    fit_manifest = _json(fit_manifest_path)
    candidate_manifest_path = _bound(annotations["candidate_manifest"])
    candidate_wrapper = _json(candidate_manifest_path)
    candidate = candidate_wrapper["candidate_config"]

    annotated = {
        item["target_id"]: item
        for item in annotations["jaw_endpoint_annotations"]["targets"]
    }
    members = {item["target_id"]: item for item in fit_manifest["members"]}
    expected = [item["target_id"] for item in contract["split"]["fit_targets"]]
    if set(expected) != set(annotated) or set(expected) != set(members):
        raise RegistrationV2FitError("fit split membership changed")
    for target_id in expected:
        image_path = REPO_ROOT / members[target_id]["image_path"]
        digest = sha256_file(image_path)
        if digest != members[target_id]["image_sha256"]:
            raise RegistrationV2FitError("fit image changed")
        if digest != annotated[target_id]["image_sha256"]:
            raise RegistrationV2FitError("annotation image binding changed")

    hold_means = _hold_means(annotations, fit_manifest)
    physical = np.asarray([hold_means[item] for item in expected])
    jaw_world = _model_jaw_midpoints(physical, candidate)
    pass_midpoints: list[np.ndarray] = []
    tip_disagreements: list[float] = []
    midpoint_disagreements: list[float] = []
    annotation_rows: list[dict[str, Any]] = []
    for target_id in expected:
        item = annotated[target_id]
        pass_a = np.asarray(item["pass_a_tip_pixels"], dtype=np.float64)
        pass_b = np.asarray(item["pass_b_tip_pixels"], dtype=np.float64)
        tip_delta = np.linalg.norm(pass_a - pass_b, axis=1)
        midpoint_a = np.mean(pass_a, axis=0)
        midpoint_b = np.mean(pass_b, axis=0)
        midpoint_delta = float(np.linalg.norm(midpoint_a - midpoint_b))
        tip_disagreements.extend(tip_delta.tolist())
        midpoint_disagreements.append(midpoint_delta)
        midpoint = (midpoint_a + midpoint_b) / 2.0
        pass_midpoints.append(midpoint)
        annotation_rows.append(
            {
                "target_id": target_id,
                "pass_a_midpoint_px": midpoint_a.tolist(),
                "pass_b_midpoint_px": midpoint_b.tolist(),
                "frozen_midpoint_px": midpoint.tolist(),
                "maximum_tip_disagreement_px": float(np.max(tip_delta)),
                "midpoint_disagreement_px": midpoint_delta,
                "physical_hold_mean_degrees_percent": hold_means[target_id].tolist(),
                "model_distal_jaw_midpoint_world_m": jaw_world[
                    len(annotation_rows)
                ].tolist(),
            }
        )

    board = annotations["board_lattice"]
    board_image = np.asarray(board["playing_corners_px"], dtype=np.float64)
    side_m = float(contract["board_model"]["playing_side_design_prior_mm"]) / 1000.0
    board_world = _board_world_corners(candidate, side_m)[
        np.asarray([1, 0, 3, 2], dtype=np.int32)
    ]
    world = np.vstack((board_world, jaw_world))
    image = np.vstack((board_image, np.asarray(pass_midpoints)))
    camera, condition = normalized_projective_dlt(world, image)
    projected = project(camera, world)
    errors = np.linalg.norm(projected - image, axis=1)

    gates = contract["gates"]
    checks = {
        "annotation_tip_agreement": max(tip_disagreements)
        <= float(gates["maximum_annotation_tip_disagreement_px"]),
        "annotation_midpoint_agreement": max(midpoint_disagreements)
        <= float(gates["maximum_annotation_midpoint_disagreement_px"]),
        "board_lattice_rms": float(board["residual_rms_px"])
        <= float(gates["maximum_board_lattice_fit_rms_px"]),
        "board_lattice_max": float(board["residual_max_px"])
        <= float(gates["maximum_board_lattice_fit_max_px"]),
        "fit_hover_reprojection_rms": float(
            np.sqrt(np.mean(np.square(errors[4:])))
        )
        <= float(gates["maximum_fit_hover_reprojection_rms_px"]),
        "fit_hover_reprojection_max": float(np.max(errors[4:]))
        <= float(gates["maximum_fit_hover_reprojection_max_px"]),
        "dlt_design_condition": condition
        <= float(gates["maximum_dlt_design_condition_number"]),
    }
    admitted = all(checks.values())
    candidate_payload = {
        "schema_version": "sim2claw.bidirectional_pawn_push_v2_registration_candidate.v1",
        "family_id": contract["candidate_family"]["family_id"],
        "annotation_sha256": sha256_file(annotation_path),
        "fit_manifest_sha256": annotations["fit_manifest"]["sha256"],
        "candidate_manifest_sha256": annotations["candidate_manifest"]["sha256"],
        "camera_matrix_3x4": camera.tolist(),
        "board_world_corner_permutation": [1, 0, 3, 2],
        "model_feature": contract["gripper_reference"]["model_feature"],
        "fit_only": True,
        "heldout_open_count": 0,
    }
    output_directory.mkdir(parents=True, exist_ok=False)
    candidate_path = output_directory / "candidate.json"
    candidate_path.write_text(
        json.dumps(candidate_payload, indent=2, sort_keys=True) + "\n"
    )
    receipt = {
        "schema_version": "sim2claw.bidirectional_pawn_push_v2_registration_fit_receipt.v1",
        "status": "fit_candidate_frozen" if admitted else "rejected_before_heldout",
        "proof_class": "fit_split_registration_diagnostic_only",
        "annotation_path": str(annotation_path),
        "annotation_sha256": sha256_file(annotation_path),
        "fit_manifest_path": str(fit_manifest_path),
        "fit_manifest_sha256": sha256_file(fit_manifest_path),
        "candidate_path": str(candidate_path),
        "candidate_sha256": sha256_file(candidate_path),
        "candidate_family": contract["candidate_family"],
        "heldout_open_count": 0,
        "heldout_inputs_read": False,
        "board_lattice": board,
        "jaw_annotations": annotation_rows,
        "fit_projection": {
            "observed_pixels": image.tolist(),
            "projected_pixels": projected.tolist(),
            "errors_px": errors.tolist(),
            "board_reprojection_rms_px": float(
                np.sqrt(np.mean(np.square(errors[:4])))
            ),
            "board_reprojection_max_px": float(np.max(errors[:4])),
            "hover_reprojection_rms_px": float(
                np.sqrt(np.mean(np.square(errors[4:])))
            ),
            "hover_reprojection_max_px": float(np.max(errors[4:])),
            "design_condition_number": condition,
        },
        "checks": checks,
        "fit_admitted_for_heldout_open": admitted,
        "fallback": (
            "none"
            if admitted
            else contract["recapture_fallback"]["action"]
        ),
        "claim_boundary": (
            "Fit-only registration candidate; held-out remains sealed and this "
            "receipt grants no metric registration, task, motion, or transfer success."
        ),
    }
    receipt_path = output_directory / "fit_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return receipt
