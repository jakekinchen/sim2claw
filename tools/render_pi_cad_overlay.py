#!/usr/bin/env python3
"""Render the exact MuJoCo follower geometry into a torque-on Pi frame."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import cv2
import mujoco
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

from sim2claw.paths import SO101_MODEL_PATH
from sim2claw.physical_canary import _physical_to_model_position
from sim2claw.recorded_replay import _compile_model


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = (
    ROOT
    / "runs/physical_excitation/20260725-follower-only-v1/"
    "simulation-canary-v1/candidate_manifest.json"
)
BODY_COLORS = {
    "left_edge_clamp": (40, 170, 255),
    "left_base": (40, 210, 255),
    "left_shoulder": (70, 210, 255),
    "left_upper_arm": (70, 255, 120),
    "left_lower_arm": (255, 210, 60),
    "left_wrist": (255, 100, 80),
    "left_gripper": (220, 80, 255),
    "left_camera_mount": (190, 70, 230),
    "left_moving_jaw_so101_v1": (180, 80, 255),
}
APRILTAG_DICTIONARY = cv2.aruco.getPredefinedDictionary(
    cv2.aruco.DICT_APRILTAG_36h11
)
THREE_LINK_TAG_PARAMETER_START = {2: 6, 1: 12, 0: 18}
THREE_LINK_OFFSET_START = 24


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def transform(rotation_vector: list[float], translation: list[float]) -> np.ndarray:
    value = np.eye(4)
    value[:3, :3] = Rotation.from_rotvec(rotation_vector).as_matrix()
    value[:3, 3] = translation
    return value


def box_points(size: np.ndarray) -> np.ndarray:
    return np.asarray(
        [
            [x * size[0], y * size[1], z * size[2]]
            for x in (-1.0, 1.0)
            for y in (-1.0, 1.0)
            for z in (-1.0, 1.0)
        ],
        dtype=np.float64,
    )


def primitive_points(geom_type: int, size: np.ndarray) -> np.ndarray:
    if geom_type == int(mujoco.mjtGeom.mjGEOM_BOX):
        return box_points(size)
    if geom_type == int(mujoco.mjtGeom.mjGEOM_SPHERE):
        radius = float(size[0])
        return np.asarray(
            [
                [radius * np.cos(a) * np.sin(b), radius * np.sin(a) * np.sin(b), radius * np.cos(b)]
                for a in np.linspace(0, 2 * np.pi, 16, endpoint=False)
                for b in np.linspace(0, np.pi, 8)
            ]
        )
    radius = float(size[0])
    half = float(size[1])
    return np.asarray(
        [
            [radius * np.cos(a), radius * np.sin(a), z]
            for a in np.linspace(0, 2 * np.pi, 20, endpoint=False)
            for z in (-half, half)
        ],
        dtype=np.float64,
    )


def geom_points(model: mujoco.MjModel, data: mujoco.MjData, geom_id: int) -> np.ndarray:
    geom_type = int(model.geom_type[geom_id])
    if geom_type == int(mujoco.mjtGeom.mjGEOM_MESH):
        mesh_id = int(model.geom_dataid[geom_id])
        start = int(model.mesh_vertadr[mesh_id])
        count = int(model.mesh_vertnum[mesh_id])
        local = np.asarray(model.mesh_vert[start : start + count], dtype=np.float64)
    else:
        local = primitive_points(geom_type, np.asarray(model.geom_size[geom_id]))
    rotation = data.geom_xmat[geom_id].reshape(3, 3)
    return local @ rotation.T + data.geom_xpos[geom_id]


def follower_visual_bodies(model: mujoco.MjModel) -> list[str]:
    result = []
    for body_id in range(model.nbody):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id)
        if not name or not name.startswith("left_"):
            continue
        has_visual_mesh = any(
            int(model.geom_bodyid[geom_id]) == body_id
            and int(model.geom_group[geom_id]) == 2
            and int(model.geom_type[geom_id])
            == int(mujoco.mjtGeom.mjGEOM_MESH)
            for geom_id in range(model.ngeom)
        )
        if has_visual_mesh:
            result.append(name)
    return result


def project(points: np.ndarray, camera_world: np.ndarray, focal: float) -> np.ndarray:
    homogeneous = np.column_stack([points, np.ones(len(points))])
    camera = (camera_world @ homogeneous.T)[:3]
    valid = camera[2] > 1e-5
    normalized = camera[:2, valid] / camera[2:3, valid]
    return np.column_stack(
        [focal * normalized[0] + 768.0, focal * normalized[1] + 432.0]
    )


def detect_tags(image: np.ndarray) -> dict[int, np.ndarray]:
    detector = cv2.aruco.ArucoDetector(APRILTAG_DICTIONARY)
    corners, identifiers, _ = detector.detectMarkers(image)
    matches: dict[int, list[np.ndarray]] = {}
    if identifiers is not None:
        for identifier, corner in zip(identifiers.ravel(), corners, strict=True):
            tag_id = int(identifier)
            matches.setdefault(tag_id, []).append(corner[0].astype(np.float64))
    return {
        tag_id: values[0]
        for tag_id, values in matches.items()
        if len(values) == 1
    }


def body_transform(data: mujoco.MjData, body_id: int) -> np.ndarray:
    value = np.eye(4)
    value[:3, :3] = data.xmat[body_id].reshape(3, 3)
    value[:3, 3] = data.xpos[body_id]
    return value


def tag_world_corners(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    tag_model: dict[str, Any],
    parameters: dict[str, Any],
) -> dict[int, np.ndarray]:
    half = float(tag_model["black_edge_m"]) / 2.0
    local = np.asarray(
        [
            [-half, half, 0.0, 1.0],
            [half, half, 0.0, 1.0],
            [half, -half, 0.0, 1.0],
            [-half, -half, 0.0, 1.0],
        ],
        dtype=np.float64,
    ).T
    result = {}
    for tag_id_text, specification in tag_model["tags"].items():
        tag_id = int(tag_id_text)
        body_id = mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_BODY, specification["body"]
        )
        mount = parameters["tag_mounts"][tag_id_text]
        body_tag = transform(
            mount["body_tag_rotation_vector_radians"],
            mount["body_tag_translation_m"],
        )
        result[tag_id] = (
            body_transform(data, body_id) @ body_tag @ local
        )[:3].T
    return result


def normalized_calibration(
    candidate: dict[str, Any],
    body_map_family: str | None,
) -> tuple[dict[str, Any], dict[str, Any], float, str]:
    schema = candidate.get("schema_version")
    if schema == "sim2claw.pi_current_three_link_candidate.v1":
        if body_map_family is None:
            body_map_family = str(candidate["body_selection"]["selected"])
            vector = np.asarray(
                candidate["parameters"]["parameter_vector"],
                dtype=np.float64,
            )
            body_map = {
                int(tag_id): specification["body"]
                for tag_id, specification in candidate["tag_model"][
                    "tags"
                ].items()
            }
        else:
            choices = candidate["body_selection"]["candidates"]
            if body_map_family not in choices:
                raise RuntimeError(
                    f"unknown body-map family {body_map_family!r}; "
                    f"expected one of {sorted(choices)}"
                )
            selection = choices[body_map_family]
            vector = np.asarray(
                selection["full_training_parameter_vector"],
                dtype=np.float64,
            )
            body_map = {
                int(tag_id): body
                for tag_id, body in selection["body_map"].items()
            }
        parameters = {
            "camera_world_rotation_vector_radians": vector[:3].tolist(),
            "camera_world_translation_m": vector[3:6].tolist(),
            "tag_mounts": {
                str(tag_id): {
                    "body_tag_rotation_vector_radians": vector[
                        start : start + 3
                    ].tolist(),
                    "body_tag_translation_m": vector[
                        start + 3 : start + 6
                    ].tolist(),
                }
                for tag_id, start in THREE_LINK_TAG_PARAMETER_START.items()
            },
            "joint_zero_offsets_degrees": vector[
                THREE_LINK_OFFSET_START : THREE_LINK_OFFSET_START + 5
            ].tolist(),
        }
        tag_model = {
            "family": candidate["tag_model"]["family"],
            "black_edge_m": candidate["tag_model"]["black_edge_m"],
            "tags": {
                str(tag_id): {"body": body}
                for tag_id, body in body_map.items()
            },
        }
        return (
            parameters,
            tag_model,
            float(candidate["intrinsics"]["focal_pixels"]),
            body_map_family,
        )
    if body_map_family is not None:
        raise RuntimeError(
            "--body-map-family requires a current three-link candidate"
        )
    if schema != "sim2claw.pi_dual_link_tag_candidate.v1":
        raise RuntimeError(f"unsupported candidate schema {schema!r}")
    parameters = candidate["parameters"]
    tag_model = {
        "family": candidate["tag_model"]["family"],
        "black_edge_m": candidate["tag_model"]["black_edge_m"],
        "tags": {},
    }
    mounts = {}
    for role, prefix in (("proximal", "proximal"), ("distal", "distal")):
        specification = candidate["tag_model"][role]
        tag_id = str(specification["id"])
        tag_model["tags"][tag_id] = {"body": specification["body"]}
        mounts[tag_id] = {
            "body_tag_rotation_vector_radians": parameters[
                f"{prefix}_body_tag_rotation_vector_radians"
            ],
            "body_tag_translation_m": parameters[
                f"{prefix}_body_tag_translation_m"
            ],
        }
    normalized = dict(parameters)
    normalized["tag_mounts"] = mounts
    return (
        normalized,
        tag_model,
        float(candidate["camera_model"]["focal_pixels"]),
        "legacy_two_link",
    )


def tag_errors(
    camera_world: np.ndarray,
    tag_world: dict[int, np.ndarray],
    observed: dict[int, np.ndarray],
    focal: float,
) -> tuple[np.ndarray, dict[int, np.ndarray]]:
    projected = {
        tag_id: project(tag_world[tag_id], camera_world, focal)
        for tag_id in sorted(observed)
    }
    errors = np.concatenate(
        [
            (projected[tag_id] - observed[tag_id]).ravel()
            for tag_id in sorted(observed)
        ]
    )
    return errors, projected


def align_camera_to_tags(
    camera_world: np.ndarray,
    tag_world: dict[int, np.ndarray],
    observed: dict[int, np.ndarray],
    focal: float,
) -> tuple[np.ndarray, dict[str, Any]]:
    if sorted(observed) != [1, 2]:
        raise RuntimeError("tag alignment requires unique visible tags 1 and 2")
    seed = np.concatenate(
        [
            Rotation.from_matrix(camera_world[:3, :3]).as_rotvec(),
            camera_world[:3, 3],
        ]
    )

    def residual(parameters: np.ndarray) -> np.ndarray:
        value = transform(parameters[:3].tolist(), parameters[3:6].tolist())
        errors, _ = tag_errors(value, tag_world, observed, focal)
        return errors

    limits = np.asarray([0.35, 0.35, 0.35, 0.15, 0.15, 0.15])
    result = least_squares(
        residual,
        seed,
        bounds=(seed - limits, seed + limits),
        loss="soft_l1",
        f_scale=2.0,
        max_nfev=3000,
    )
    fitted = transform(result.x[:3].tolist(), result.x[3:6].tolist())
    before, before_projected = tag_errors(
        camera_world, tag_world, observed, focal
    )
    after, after_projected = tag_errors(fitted, tag_world, observed, focal)
    before_norms = np.linalg.norm(before.reshape(-1, 2), axis=1)
    after_norms = np.linalg.norm(after.reshape(-1, 2), axis=1)
    delta_rotation = fitted[:3, :3] @ camera_world[:3, :3].T
    return fitted, {
        "method": "bounded_six_dof_camera_only_tag_corner_fit",
        "observed_tag_ids": sorted(observed),
        "joint_or_geometry_parameters_changed": False,
        "fitted_camera_world_rotation_vector_radians": Rotation.from_matrix(
            fitted[:3, :3]
        )
        .as_rotvec()
        .tolist(),
        "fitted_camera_world_translation_m": fitted[:3, 3].tolist(),
        "initial_corner_rmse_px": float(
            np.sqrt(np.mean(before_norms**2))
        ),
        "initial_corner_max_px": float(np.max(before_norms)),
        "aligned_corner_rmse_px": float(np.sqrt(np.mean(after_norms**2))),
        "aligned_corner_max_px": float(np.max(after_norms)),
        "camera_rotation_delta_degrees": float(
            np.degrees(Rotation.from_matrix(delta_rotation).magnitude())
        ),
        "camera_translation_delta_m": float(
            np.linalg.norm(fitted[:3, 3] - camera_world[:3, 3])
        ),
        "optimizer_optimality": float(result.optimality),
        "observed_corners_pixels": {
            str(tag_id): observed[tag_id].tolist() for tag_id in sorted(observed)
        },
        "initial_projected_corners_pixels": {
            str(tag_id): before_projected[tag_id].tolist()
            for tag_id in sorted(observed)
        },
        "aligned_projected_corners_pixels": {
            str(tag_id): after_projected[tag_id].tolist()
            for tag_id in sorted(observed)
        },
    }


def draw_tag_polygon(
    image: np.ndarray,
    corners: np.ndarray,
    color: tuple[int, int, int],
    label: str,
    thickness: int,
) -> None:
    polygon = np.rint(corners).astype(np.int32).reshape(-1, 1, 2)
    cv2.polylines(image, [polygon], True, color, thickness, cv2.LINE_AA)
    anchor = tuple(np.rint(corners[0]).astype(int))
    cv2.putText(
        image,
        label,
        (anchor[0] + 5, anchor[1] - 5),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.52,
        color,
        2,
        cv2.LINE_AA,
    )


def draw_virtual_tag(
    image: np.ndarray,
    corners: np.ndarray,
    tag_id: int,
    *,
    opacity: float = 0.48,
) -> None:
    marker_size = 160
    marker = cv2.aruco.generateImageMarker(
        APRILTAG_DICTIONARY, tag_id, marker_size
    )
    marker_bgr = cv2.cvtColor(marker, cv2.COLOR_GRAY2BGR)
    source = np.asarray(
        [
            [0.0, 0.0],
            [marker_size - 1.0, 0.0],
            [marker_size - 1.0, marker_size - 1.0],
            [0.0, marker_size - 1.0],
        ],
        dtype=np.float32,
    )
    destination = corners.astype(np.float32)
    homography = cv2.getPerspectiveTransform(source, destination)
    warped = cv2.warpPerspective(
        marker_bgr,
        homography,
        (image.shape[1], image.shape[0]),
        flags=cv2.INTER_NEAREST,
    )
    mask = cv2.warpPerspective(
        np.full((marker_size, marker_size), 255, dtype=np.uint8),
        homography,
        (image.shape[1], image.shape[0]),
        flags=cv2.INTER_NEAREST,
    )
    alpha = (mask.astype(np.float32) / 255.0 * opacity)[..., None]
    image[:] = np.rint(
        warped.astype(np.float32) * alpha
        + image.astype(np.float32) * (1.0 - alpha)
    ).astype(np.uint8)


def draw_corner_residuals(
    image: np.ndarray,
    observed: np.ndarray,
    projected: np.ndarray,
) -> None:
    for actual, estimate in zip(observed, projected, strict=True):
        cv2.line(
            image,
            tuple(np.rint(actual).astype(int)),
            tuple(np.rint(estimate).astype(int)),
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--output-receipt", type=Path, required=True)
    parser.add_argument("--align-tags", action="store_true")
    parser.add_argument("--camera-override-receipt", type=Path)
    parser.add_argument("--body-map-family")
    arguments = parser.parse_args()
    if arguments.align_tags and arguments.camera_override_receipt is not None:
        raise RuntimeError(
            "--align-tags and --camera-override-receipt are mutually exclusive"
        )
    if arguments.output.exists() or arguments.output_receipt.exists():
        raise RuntimeError("refusing to overwrite CAD overlay output")

    candidate = json.loads(arguments.candidate.read_text(encoding="utf-8"))
    parameters, tag_model, focal, body_map_family = normalized_calibration(
        candidate, arguments.body_map_family
    )
    execution = json.loads(arguments.receipt.read_text(encoding="utf-8"))
    image = cv2.imread(str(arguments.image))
    if image is None or image.shape[:2] != (864, 1536):
        raise RuntimeError("expected one 1536x864 Pi image")
    if (
        execution.get("status") != "completed_wrist_view_reposition_stage"
        or (execution.get("pi_hold_still") or {}).get("sha256")
        != sha256(arguments.image)
    ):
        raise RuntimeError("image is not bound to an admitted torque-on receipt")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    config = manifest["candidate_config"]
    model, _ = _compile_model(config, base_directory=None)
    data = mujoco.MjData(model)
    actual = np.asarray(execution["final_actual_degrees"], dtype=np.float64)
    offsets = np.asarray(
        candidate["parameters"]["joint_zero_offsets_degrees"], dtype=np.float64
    )
    calibrated_physical = actual.copy()
    calibrated_physical[:5] += offsets
    qpos = _physical_to_model_position(
        calibrated_physical[None, :], config
    )[0]
    for index, name in enumerate(config["bindings"]["joint_names"]):
        joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        data.qpos[int(model.jnt_qposadr[joint_id])] = qpos[index]
    data.qvel[:] = 0
    mujoco.mj_forward(model, data)

    camera_world = transform(
        parameters["camera_world_rotation_vector_radians"],
        parameters["camera_world_translation_m"],
    )
    detected_tags = detect_tags(image)
    follower_tag_ids = sorted(int(tag_id) for tag_id in tag_model["tags"])
    observed_tags = {
        tag_id: detected_tags[tag_id]
        for tag_id in follower_tag_ids
        if tag_id in detected_tags
    }
    if not observed_tags:
        raise RuntimeError("no unique follower tags detected")
    world_tags = tag_world_corners(model, data, tag_model, parameters)
    _, initial_projected_tags = tag_errors(
        camera_world,
        world_tags,
        {tag_id: observed_tags[tag_id] for tag_id in observed_tags},
        focal,
    )
    alignment = None
    if arguments.align_tags:
        camera_world, alignment = align_camera_to_tags(
            camera_world, world_tags, observed_tags, focal
        )
    elif arguments.camera_override_receipt is not None:
        source_receipt = json.loads(
            arguments.camera_override_receipt.read_text(encoding="utf-8")
        )
        source_alignment = source_receipt.get("tag_alignment") or {}
        if (
            source_receipt.get("schema_version")
            != "sim2claw.pi_cad_overlay.v3"
            or source_receipt.get("candidate", {}).get("sha256")
            != sha256(arguments.candidate)
            or source_alignment.get("method")
            != "bounded_six_dof_camera_only_tag_corner_fit"
        ):
            raise RuntimeError("invalid shared-camera overlay receipt")
        camera_world = transform(
            source_alignment[
                "fitted_camera_world_rotation_vector_radians"
            ],
            source_alignment["fitted_camera_world_translation_m"],
        )
        alignment = {
            "method": "shared_camera_from_overlay_receipt",
            "source_receipt_path": str(arguments.camera_override_receipt),
            "source_receipt_sha256": sha256(
                arguments.camera_override_receipt
            ),
            "per_frame_fit_performed": False,
            "fitted_camera_world_rotation_vector_radians": source_alignment[
                "fitted_camera_world_rotation_vector_radians"
            ],
            "fitted_camera_world_translation_m": source_alignment[
                "fitted_camera_world_translation_m"
            ],
        }
    _, projected_tags = tag_errors(
        camera_world,
        world_tags,
        {tag_id: observed_tags[tag_id] for tag_id in observed_tags},
        focal,
    )
    projected_corner_errors = np.concatenate(
        [
            np.linalg.norm(
                projected_tags[tag_id] - observed_tags[tag_id], axis=1
            )
            for tag_id in sorted(observed_tags)
        ]
    )
    layer = image.copy()
    projected_bodies: dict[str, dict[str, Any]] = {}
    visual_bodies = follower_visual_bodies(model)
    for body_name in visual_bodies:
        color = BODY_COLORS.get(body_name, (180, 180, 180))
        body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, body_name)
        body_pixels = []
        geom_count = 0
        for geom_id in range(model.ngeom):
            if int(model.geom_bodyid[geom_id]) != body_id:
                continue
            if (
                int(model.geom_group[geom_id]) != 2
                or int(model.geom_type[geom_id])
                != int(mujoco.mjtGeom.mjGEOM_MESH)
            ):
                continue
            pixels = project(geom_points(model, data, geom_id), camera_world, focal)
            pixels = pixels[
                (pixels[:, 0] >= -100)
                & (pixels[:, 0] <= 1636)
                & (pixels[:, 1] >= -100)
                & (pixels[:, 1] <= 964)
            ]
            if len(pixels) < 3:
                continue
            hull = cv2.convexHull(np.rint(pixels).astype(np.int32))
            cv2.fillConvexPoly(layer, hull, color)
            cv2.polylines(image, [hull], True, color, 2, cv2.LINE_AA)
            body_pixels.append(pixels)
            geom_count += 1
        if body_pixels:
            pixels = np.concatenate(body_pixels)
            projected_bodies[body_name] = {
                "geom_count": geom_count,
                "pixel_bounds": [
                    float(np.min(pixels[:, 0])),
                    float(np.min(pixels[:, 1])),
                    float(np.max(pixels[:, 0])),
                    float(np.max(pixels[:, 1])),
                ],
            }
    overlay = cv2.addWeighted(layer, 0.28, image, 0.72, 0.0)
    for tag_id in sorted(observed_tags):
        draw_virtual_tag(overlay, projected_tags[tag_id], tag_id)
        draw_corner_residuals(
            overlay, observed_tags[tag_id], projected_tags[tag_id]
        )
        draw_tag_polygon(
            overlay,
            observed_tags[tag_id],
            (70, 255, 70),
            f"observed {tag_id}",
            4,
        )
        draw_tag_polygon(
            overlay,
            initial_projected_tags[tag_id],
            (0, 215, 255),
            f"initial {tag_id}",
            2,
        )
        draw_tag_polygon(
            overlay,
            projected_tags[tag_id],
            (255, 255, 255),
            f"aligned {tag_id}",
            2,
        )
    for tag_id in sorted(set(detected_tags) - set(observed_tags)):
        draw_tag_polygon(
            overlay,
            detected_tags[tag_id],
            (170, 170, 170),
            f"excluded other-arm tag {tag_id}",
            2,
        )
    cv2.putText(
        overlay,
        "VISUAL CAD + virtual tags | green observed | white aligned",
        (28, 42),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(arguments.output), overlay):
        raise RuntimeError("failed to write CAD overlay")
    receipt = {
        "schema_version": "sim2claw.pi_cad_overlay.v4",
        "proof_class": "physical_image_cad_projection_diagnostic_only",
        "status": "rendered",
        "candidate": {
            "path": str(arguments.candidate),
            "sha256": sha256(arguments.candidate),
        },
        "execution_receipt": {
            "path": str(arguments.receipt),
            "sha256": sha256(arguments.receipt),
        },
        "physical_image": {
            "path": str(arguments.image),
            "sha256": sha256(arguments.image),
        },
        "output": {
            "path": str(arguments.output),
            "sha256": sha256(arguments.output),
        },
        "focal_pixels": focal,
        "body_map_family": body_map_family,
        "source_model": {
            "path": str(SO101_MODEL_PATH),
            "sha256": sha256(SO101_MODEL_PATH),
            "compiled_scene_manifest_path": str(MANIFEST),
            "compiled_scene_manifest_sha256": sha256(MANIFEST),
        },
        "joint_degrees": execution["final_actual_degrees"],
        "joint_zero_offsets_degrees": offsets.tolist(),
        "calibrated_joint_degrees": calibrated_physical.tolist(),
        "joint_offsets_applied_to_cad": True,
        "tag_alignment": alignment,
        "tag_projection_metrics": {
            "observed_tag_ids": sorted(observed_tags),
            "corner_rmse_px": float(
                np.sqrt(np.mean(projected_corner_errors**2))
            ),
            "corner_max_px": float(np.max(projected_corner_errors)),
        },
        "fiducials": {
            "family": tag_model["family"],
            "follower_tag_ids": sorted(observed_tags),
            "excluded_detected_tag_ids": sorted(
                set(detected_tags) - set(observed_tags)
            ),
            "virtual_tag_texture_rendered": True,
            "virtual_tag_mount_source": "candidate_shared_body_tag_transform",
        },
        "full_follower_visual_model": {
            "selection": "all MuJoCo bodies with left_ prefix and group-2 visual meshes",
            "body_names": visual_bodies,
            "body_count": len(visual_bodies),
            "visual_mesh_geom_count": int(
                sum(
                    int(model.geom_group[geom_id]) == 2
                    and int(model.geom_type[geom_id])
                    == int(mujoco.mjtGeom.mjGEOM_MESH)
                    and (
                        mujoco.mj_id2name(
                            model,
                            mujoco.mjtObj.mjOBJ_BODY,
                            int(model.geom_bodyid[geom_id]),
                        )
                        or ""
                    ).startswith("left_")
                    for geom_id in range(model.ngeom)
                )
            ),
            "omitted_visual_bodies": [],
            "excluded_non_visual_fixture_bodies": ["left_edge_clamp"],
        },
        "projected_bodies": projected_bodies,
        "limitations": {
            "visual_mesh_geoms_only": True,
            "collision_proxy_geoms_excluded": True,
            "silhouette_fit_performed": False,
            "occlusion_reasoning_performed": False,
            "second_arm_segmented": False,
            "per_frame_tag_alignment_is_global_camera_calibration": False,
            "simulator_parameter_promotion": False,
            "task_or_policy_evidence": False,
        },
    }
    arguments.output_receipt.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
