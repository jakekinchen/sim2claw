#!/usr/bin/env python3
"""Audit AprilTags in the coherent early IMG_5349 COLMAP component.

This diagnostic intentionally does not associate an old source-video tag with
a current arm-mounted tag merely because their integer IDs are equal.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterable

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
REGISTRATION = (
    ROOT / "configs/evaluations/img5349_3dgs_board_registration_v1.json"
)
SCHEMA = "sim2claw.img5349_apriltag_sfm_audit.v1"
EARLY_COMPONENT_MAX_FRAME = 25

# COLMAP camera model IDs and parameter counts from the public COLMAP format.
CAMERA_MODEL_PARAMETER_COUNTS = {
    0: 3,  # SIMPLE_PINHOLE
    1: 4,  # PINHOLE
    2: 4,  # SIMPLE_RADIAL
    3: 5,  # RADIAL
    4: 8,  # OPENCV
    5: 8,  # OPENCV_FISHEYE
    6: 12,  # FULL_OPENCV
    7: 5,  # FOV
    8: 4,  # SIMPLE_RADIAL_FISHEYE
    9: 5,  # RADIAL_FISHEYE
    10: 12,  # THIN_PRISM_FISHEYE
}


@dataclass(frozen=True)
class Camera:
    camera_id: int
    model_id: int
    width: int
    height: int
    parameters: np.ndarray


@dataclass(frozen=True)
class RegisteredImage:
    image_id: int
    camera_id: int
    name: str
    rotation_world_to_camera: np.ndarray
    translation_world_to_camera: np.ndarray

    @property
    def camera_center_world(self) -> np.ndarray:
        return -self.rotation_world_to_camera.T @ self.translation_world_to_camera


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _unpack(handle: BinaryIO, format_string: str) -> tuple:
    size = struct.calcsize("<" + format_string)
    data = handle.read(size)
    if len(data) != size:
        raise ValueError("truncated COLMAP binary model")
    return struct.unpack("<" + format_string, data)


def _read_c_string(handle: BinaryIO) -> str:
    value = bytearray()
    while True:
        byte = handle.read(1)
        if not byte:
            raise ValueError("truncated COLMAP image name")
        if byte == b"\0":
            return value.decode("utf-8")
        value.extend(byte)


def quaternion_to_rotation(qvec: Iterable[float]) -> np.ndarray:
    qw, qx, qy, qz = np.asarray(tuple(qvec), dtype=np.float64)
    norm = math.sqrt(qw * qw + qx * qx + qy * qy + qz * qz)
    if norm <= 0.0:
        raise ValueError("invalid zero COLMAP quaternion")
    qw, qx, qy, qz = (qw / norm, qx / norm, qy / norm, qz / norm)
    return np.asarray(
        (
            (
                1.0 - 2.0 * (qy * qy + qz * qz),
                2.0 * (qx * qy - qz * qw),
                2.0 * (qx * qz + qy * qw),
            ),
            (
                2.0 * (qx * qy + qz * qw),
                1.0 - 2.0 * (qx * qx + qz * qz),
                2.0 * (qy * qz - qx * qw),
            ),
            (
                2.0 * (qx * qz - qy * qw),
                2.0 * (qy * qz + qx * qw),
                1.0 - 2.0 * (qx * qx + qy * qy),
            ),
        ),
        dtype=np.float64,
    )


def read_cameras_binary(path: Path) -> dict[int, Camera]:
    cameras: dict[int, Camera] = {}
    with path.open("rb") as handle:
        (count,) = _unpack(handle, "Q")
        for _ in range(count):
            camera_id, model_id, width, height = _unpack(handle, "iiQQ")
            parameter_count = CAMERA_MODEL_PARAMETER_COUNTS.get(model_id)
            if parameter_count is None:
                raise ValueError(f"unsupported COLMAP camera model ID {model_id}")
            parameters = np.asarray(
                _unpack(handle, "d" * parameter_count), dtype=np.float64
            )
            cameras[camera_id] = Camera(
                camera_id=camera_id,
                model_id=model_id,
                width=width,
                height=height,
                parameters=parameters,
            )
    return cameras


def read_images_binary(path: Path) -> dict[str, RegisteredImage]:
    images: dict[str, RegisteredImage] = {}
    with path.open("rb") as handle:
        (count,) = _unpack(handle, "Q")
        for _ in range(count):
            image_id = _unpack(handle, "i")[0]
            qvec = _unpack(handle, "dddd")
            translation = np.asarray(_unpack(handle, "ddd"), dtype=np.float64)
            camera_id = _unpack(handle, "i")[0]
            name = _read_c_string(handle)
            (point_count,) = _unpack(handle, "Q")
            handle.seek(point_count * struct.calcsize("<ddQ"), 1)
            images[name] = RegisteredImage(
                image_id=image_id,
                camera_id=camera_id,
                name=name,
                rotation_world_to_camera=quaternion_to_rotation(qvec),
                translation_world_to_camera=translation,
            )
    return images


def detector() -> cv2.aruco.ArucoDetector:
    parameters = cv2.aruco.DetectorParameters()
    parameters.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    parameters.aprilTagQuadDecimate = 1.0
    parameters.aprilTagMinClusterPixels = 5
    parameters.minMarkerPerimeterRate = 0.005
    parameters.adaptiveThreshWinSizeMin = 3
    parameters.adaptiveThreshWinSizeMax = 53
    parameters.adaptiveThreshWinSizeStep = 4
    # Accept only exact dictionary codes. IDs are still not treated as
    # cross-capture physical identity.
    parameters.errorCorrectionRate = 0.0
    dictionary = cv2.aruco.getPredefinedDictionary(
        cv2.aruco.DICT_APRILTAG_36h11
    )
    return cv2.aruco.ArucoDetector(dictionary, parameters)


def frame_number(name: str) -> int:
    stem = Path(name).stem
    if not stem.startswith("frame-"):
        raise ValueError(f"unexpected COLMAP image name: {name}")
    return int(stem.removeprefix("frame-"))


def camera_matrix_and_distortion(
    camera: Camera,
) -> tuple[np.ndarray, np.ndarray]:
    if camera.model_id != 4 or camera.parameters.shape != (8,):
        raise ValueError("IMG_5349 audit requires the bound OPENCV camera")
    fx, fy, cx, cy, k1, k2, p1, p2 = camera.parameters
    matrix = np.asarray(
        ((fx, 0.0, cx), (0.0, fy, cy), (0.0, 0.0, 1.0)),
        dtype=np.float64,
    )
    return matrix, np.asarray((k1, k2, p1, p2), dtype=np.float64)


def project(
    point_world: np.ndarray,
    registered_image: RegisteredImage,
    camera: Camera,
) -> tuple[np.ndarray, float]:
    camera_point = (
        registered_image.rotation_world_to_camera @ point_world
        + registered_image.translation_world_to_camera
    )
    depth = float(camera_point[2])
    x = camera_point[0] / camera_point[2]
    y = camera_point[1] / camera_point[2]
    fx, fy, cx, cy, k1, k2, p1, p2 = camera.parameters
    radius_squared = x * x + y * y
    radial = 1.0 + k1 * radius_squared + k2 * radius_squared**2
    distorted_x = (
        x * radial + 2.0 * p1 * x * y + p2 * (radius_squared + 2.0 * x * x)
    )
    distorted_y = (
        y * radial + p1 * (radius_squared + 2.0 * y * y) + 2.0 * p2 * x * y
    )
    return np.asarray(
        (fx * distorted_x + cx, fy * distorted_y + cy), dtype=np.float64
    ), depth


def triangulate(
    pixels: list[np.ndarray],
    registered_images: list[RegisteredImage],
    camera: Camera,
) -> np.ndarray:
    if len(pixels) != len(registered_images) or len(pixels) < 2:
        raise ValueError("triangulation requires matching observations")
    matrix, distortion = camera_matrix_and_distortion(camera)
    rows: list[np.ndarray] = []
    for pixel, image in zip(pixels, registered_images, strict=True):
        normalized = cv2.undistortPoints(
            np.asarray(pixel, dtype=np.float64).reshape(1, 1, 2),
            matrix,
            distortion,
        ).reshape(2)
        projection = np.column_stack(
            (
                image.rotation_world_to_camera,
                image.translation_world_to_camera,
            )
        )
        rows.extend(
            (
                normalized[0] * projection[2] - projection[0],
                normalized[1] * projection[2] - projection[1],
            )
        )
    _, _, right_singular_vectors = np.linalg.svd(np.asarray(rows))
    homogeneous = right_singular_vectors[-1]
    if abs(float(homogeneous[3])) < 1e-12:
        raise ValueError("degenerate triangulation")
    return homogeneous[:3] / homogeneous[3]


def _parallax_degrees(
    point_world: np.ndarray, registered_images: list[RegisteredImage]
) -> list[float]:
    angles: list[float] = []
    for first_index, first in enumerate(registered_images):
        first_ray = point_world - first.camera_center_world
        for second in registered_images[first_index + 1 :]:
            second_ray = point_world - second.camera_center_world
            cosine = np.dot(first_ray, second_ray) / (
                np.linalg.norm(first_ray) * np.linalg.norm(second_ray)
            )
            angles.append(
                math.degrees(math.acos(float(np.clip(cosine, -1.0, 1.0))))
            )
    return angles


def triangulate_tag(
    observations: list[tuple[RegisteredImage, np.ndarray]],
    camera: Camera,
) -> dict:
    images = [row[0] for row in observations]
    corners = np.stack(
        [
            triangulate([row[1][corner] for row in observations], images, camera)
            for corner in range(4)
        ]
    )
    corner_errors: list[float] = []
    depths: list[float] = []
    for image, observed_corners in observations:
        for corner, observed in zip(corners, observed_corners, strict=True):
            predicted, depth = project(corner, image, camera)
            corner_errors.append(float(np.linalg.norm(predicted - observed)))
            depths.append(depth)
    center = np.mean(corners, axis=0)
    edges = np.asarray(
        [
            np.linalg.norm(corners[(index + 1) % 4] - corners[index])
            for index in range(4)
        ]
    )
    centered = corners - center
    _, _, right_singular_vectors = np.linalg.svd(centered)
    plane_distances = centered @ right_singular_vectors[-1]
    parallax = _parallax_degrees(center, images)
    metrics = {
        "corner_count": len(corner_errors),
        "corner_reprojection_rms_px": float(
            np.sqrt(np.mean(np.square(corner_errors)))
        ),
        "corner_reprojection_max_px": float(np.max(corner_errors)),
        "minimum_depth_sfm": float(np.min(depths)),
        "maximum_pair_parallax_deg": float(np.max(parallax)),
        "minimum_pair_parallax_deg": float(np.min(parallax)),
        "mean_side_sfm": float(np.mean(edges)),
        "side_coefficient_of_variation": float(np.std(edges) / np.mean(edges)),
        "plane_max_abs_residual_sfm": float(np.max(np.abs(plane_distances))),
    }
    gates = {
        "at_least_three_views": len(observations) >= 3,
        "all_positive_depth": bool(np.min(depths) > 0.0),
        "reprojection_rms_at_most_4px": metrics[
            "corner_reprojection_rms_px"
        ]
        <= 4.0,
        "reprojection_max_at_most_7px": metrics[
            "corner_reprojection_max_px"
        ]
        <= 7.0,
        "maximum_parallax_at_least_10deg": metrics[
            "maximum_pair_parallax_deg"
        ]
        >= 10.0,
        "side_cv_at_most_0_05": metrics["side_coefficient_of_variation"]
        <= 0.05,
    }
    return {
        "frames": [frame_number(image.name) for image in images],
        "corners_sfm": corners.tolist(),
        "center_sfm": center.tolist(),
        "metrics": metrics,
        "gates": gates,
        "accepted": all(gates.values()),
    }


def _distance_to_segment(
    point: np.ndarray, first: np.ndarray, second: np.ndarray
) -> float:
    direction = second - first
    fraction = np.dot(point - first, direction) / np.dot(direction, direction)
    closest = first + np.clip(fraction, 0.0, 1.0) * direction
    return float(np.linalg.norm(point - closest))


def run_audit(
    *,
    images_directory: Path,
    model_directory: Path,
    registration_path: Path = REGISTRATION,
) -> dict:
    contract = json.loads(registration_path.read_text(encoding="utf-8"))
    fit = contract["fit"]
    if fit.get("accepted_camera_component") != "registered_frames_1_through_25":
        raise ValueError("audit refuses a non-coherent camera component")
    binding = contract["source_binding"]
    cameras_path = model_directory / "cameras.bin"
    images_path = model_directory / "images.bin"
    if (
        sha256(cameras_path) != binding["sfm_cameras_sha256"]
        or sha256(images_path) != binding["sfm_images_sha256"]
    ):
        raise ValueError("COLMAP model does not match tracked registration")

    cameras = read_cameras_binary(cameras_path)
    registered = read_images_binary(images_path)
    accepted_images = {
        name: image
        for name, image in registered.items()
        if frame_number(name) <= EARLY_COMPONENT_MAX_FRAME
    }
    tag_detector = detector()
    detections: dict[int, list[tuple[RegisteredImage, np.ndarray]]] = {}
    detection_rows: list[dict] = []
    for name, image in sorted(
        accepted_images.items(), key=lambda row: frame_number(row[0])
    ):
        image_path = images_directory / name
        pixels = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
        if pixels is None:
            raise ValueError(f"missing registered source image: {image_path}")
        camera = cameras[image.camera_id]
        if pixels.shape != (camera.height, camera.width):
            raise ValueError(f"source image size mismatch: {image_path}")
        corners, identifiers, rejected = tag_detector.detectMarkers(pixels)
        per_id: dict[int, list[np.ndarray]] = {}
        if identifiers is not None:
            for identifier, marker in zip(
                identifiers.ravel(), corners, strict=True
            ):
                per_id.setdefault(int(identifier), []).append(
                    marker.reshape(4, 2).astype(np.float64)
                )
        unique = {
            tag_id: rows[0] for tag_id, rows in per_id.items() if len(rows) == 1
        }
        for tag_id, marker in sorted(unique.items()):
            detections.setdefault(tag_id, []).append((image, marker))
            detection_rows.append(
                {
                    "frame": frame_number(name),
                    "tag_id": tag_id,
                    "corners_pixels": marker.tolist(),
                    "image_sha256": sha256(image_path),
                }
            )

    camera_ids = {image.camera_id for image in accepted_images.values()}
    if len(camera_ids) != 1:
        raise ValueError("early IMG_5349 component must use one camera")
    camera = cameras[camera_ids.pop()]
    triangulated: dict[str, dict] = {}
    excluded: dict[str, dict] = {}
    for tag_id, rows in sorted(detections.items()):
        if len(rows) < 2:
            excluded[str(tag_id)] = {
                "detection_count": len(rows),
                "frames": [frame_number(row[0].name) for row in rows],
                "reason": "fewer_than_two_registered_views",
            }
            continue
        result = triangulate_tag(rows, camera)
        if not result["accepted"]:
            excluded[str(tag_id)] = {
                "detection_count": len(rows),
                "frames": result["frames"],
                "reason": "triangulation_failed_strict_gates",
                "metrics": result["metrics"],
                "gates": result["gates"],
            }
            continue
        triangulated[str(tag_id)] = result

    scale = float(fit["scale_m_per_sfm_unit"])
    rotation = np.asarray(fit["rotation_source_to_mujoco"], dtype=np.float64)
    translation = np.asarray(fit["translation_mujoco_m"], dtype=np.float64)
    for result in triangulated.values():
        source_corners = np.asarray(result["corners_sfm"], dtype=np.float64)
        mapped = scale * (rotation @ source_corners.T).T + translation
        mapped_center = np.mean(mapped, axis=0)
        mapped_edges = [
            float(np.linalg.norm(mapped[(index + 1) % 4] - mapped[index]))
            for index in range(4)
        ]
        board = contract["target_binding"]
        a8 = np.asarray(board["corners_mujoco_m"]["a8"][:2])
        h8 = np.asarray(board["corners_mujoco_m"]["h8"][:2])
        result["mapped_mujoco"] = {
            "corners_m": mapped.tolist(),
            "center_m": mapped_center.tolist(),
            "mean_side_m": float(np.mean(mapped_edges)),
            "playing_surface_vertical_delta_m": float(
                mapped_center[2] - board["playing_surface_z_m"]
            ),
            "distance_xy_to_a8_h8_playing_edge_m": _distance_to_segment(
                mapped_center[:2], a8, h8
            ),
        }

    detected_frames_by_id = {
        str(tag_id): [frame_number(row[0].name) for row in rows]
        for tag_id, rows in sorted(detections.items())
    }
    return {
        "schema_version": SCHEMA,
        "status": "completed_no_eligible_cross_capture_link_correspondence",
        "proof_class": "source_video_static_fiducial_sfm_diagnostic",
        "source_binding": {
            "source_video_sha256": binding["source_video_sha256"],
            "sfm_cameras_sha256": binding["sfm_cameras_sha256"],
            "sfm_images_sha256": binding["sfm_images_sha256"],
            "registration_schema": contract["schema_version"],
            "accepted_component": fit["accepted_camera_component"],
        },
        "input_counts": {
            "registered_early_frames": len(accepted_images),
            "exact_tag_detections": len(detection_rows),
            "detected_frames_by_id": detected_frames_by_id,
        },
        "detections": detection_rows,
        "triangulated_tags": triangulated,
        "excluded_tags": excluded,
        "fusion": {
            "legitimate_tag_to_link_correspondence_count": 0,
            "eligible_tag_ids": [],
            "reason": (
                "The source-video IDs are static table/board markers. Current "
                "same-numbered IDs have later arm-body attachment models; an "
                "integer ID does not preserve a physical tag-to-link transform "
                "across captures."
            ),
            "source_absent_current_arm_tag_ids": [2, 3],
        },
        "bounded_next_method": (
            "Use the source tag 0 only as a board-adjacent world check for the "
            "historical scene. Use current arm tags only with current captures "
            "and measured tag-to-link geometry; do not refit the historical "
            "3DGS from reused IDs."
        ),
        "authority": {
            "metric_scale": False,
            "tag_to_link_transform": False,
            "robot_geometry": False,
            "collision_or_contact": False,
            "physical_robot_control": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--registration", type=Path, default=REGISTRATION)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    result = run_audit(
        images_directory=arguments.images,
        model_directory=arguments.model,
        registration_path=arguments.registration,
    )
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if arguments.output is None:
        print(rendered, end="")
    else:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
