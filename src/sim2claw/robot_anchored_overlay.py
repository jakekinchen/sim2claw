"""Robot-frame camera registration and physical/simulation comparison overlays.

The physical C922 videos in the 2026-07-18 intake cohort describe the frozen
72 mm board pose.  This module uses one hash-bound physical frame to estimate a
diagnostic pinhole camera, stores that camera relative to the fixed left robot
mount, and renders both the historical scene and the current 100 mm scene from
the same robot-relative pose.  It never promotes the video to metric, contact,
collision, task-success, or imitation-data authority.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import cv2
import mujoco
import numpy as np

from .capture import load_capture_config
from .paths import DEFAULT_CAPTURE_CONFIG
from .physical_sim_replay import physical_values_to_sim
from .scene import (
    CURRENT_TASK_PIECE_LAYOUT,
    ROBOT_JOINTS,
    _table_to_world,
    build_scene_spec,
    initialize_robot_poses,
    registered_board_center,
    scene_geometry,
)


DEFAULT_OVERLAY_CONFIG = Path(
    "configs/experiments/robot_anchored_camera_overlay_v1.json"
)
OVERLAY_RECEIPT_SCHEMA = "sim2claw.robot_anchored_camera_overlay_receipt.v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _line_homogeneous(row: dict[str, Any]) -> np.ndarray:
    first = np.asarray([*row["p1_px"], 1.0], dtype=np.float64)
    second = np.asarray([*row["p2_px"], 1.0], dtype=np.float64)
    line = np.cross(first, second)
    if not np.all(np.isfinite(line)) or np.linalg.norm(line[:2]) <= 0.0:
        raise ValueError("camera overlay line segment is degenerate")
    return line


def _line_intersection(first: dict[str, Any], second: dict[str, Any]) -> np.ndarray:
    point = np.cross(_line_homogeneous(first), _line_homogeneous(second))
    if abs(float(point[2])) <= 1e-12:
        raise ValueError("camera overlay grid lines are parallel")
    return point[:2] / point[2]


def calibration_correspondences(
    contract: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray, list[dict[str, Any]]]:
    grid = contract["board_grid_fit"]
    square = float(grid["playing_side_m"]) / 8.0
    object_points: list[list[float]] = []
    image_points: list[list[float]] = []
    evidence: list[dict[str, Any]] = []
    for horizontal in grid["horizontal_lines"]:
        rank_boundary = int(horizontal["grid_index"])
        for vertical in grid["vertical_lines"]:
            file_boundary = int(vertical["grid_index"])
            pixel = _line_intersection(vertical, horizontal)
            board_point = [
                (file_boundary - 4) * square,
                (4 - rank_boundary) * square,
                0.0,
            ]
            object_points.append(board_point)
            image_points.append(pixel.tolist())
            evidence.append(
                {
                    "file_boundary_index": file_boundary,
                    "rank_boundary_index": rank_boundary,
                    "board_point_m": board_point,
                    "source_pixel": pixel.tolist(),
                }
            )
    expected = int(grid["fit_point_count"])
    if len(object_points) != expected:
        raise ValueError(
            f"camera overlay expected {expected} correspondences, got {len(object_points)}"
        )
    return (
        np.asarray(object_points, dtype=np.float32),
        np.asarray(image_points, dtype=np.float32),
        evidence,
    )


def fit_board_camera(contract: dict[str, Any]) -> dict[str, Any]:
    object_points, image_points, evidence = calibration_correspondences(contract)
    width, height = (int(value) for value in contract["physical_source"]["image_size_px"])
    principal_x, principal_y = (
        float(value) for value in contract["camera_model"]["principal_point_px"]
    )
    initial_focal = float(contract["camera_model"]["initial_focal_length_px"])
    camera_matrix = np.asarray(
        [
            [initial_focal, 0.0, principal_x],
            [0.0, initial_focal, principal_y],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    distortion = np.zeros(8, dtype=np.float64)
    flags = (
        cv2.CALIB_USE_INTRINSIC_GUESS
        | cv2.CALIB_FIX_PRINCIPAL_POINT
        | cv2.CALIB_FIX_ASPECT_RATIO
        | cv2.CALIB_ZERO_TANGENT_DIST
        | cv2.CALIB_FIX_K1
        | cv2.CALIB_FIX_K2
        | cv2.CALIB_FIX_K3
        | cv2.CALIB_FIX_K4
        | cv2.CALIB_FIX_K5
        | cv2.CALIB_FIX_K6
    )
    rms, fitted_matrix, _, rotation_vectors, translation_vectors = cv2.calibrateCamera(
        [object_points],
        [image_points],
        (width, height),
        camera_matrix,
        distortion,
        flags=flags,
        criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 1000, 1e-12),
    )
    rotation_vector = rotation_vectors[0].reshape(3)
    translation_vector = translation_vectors[0].reshape(3)
    projected, _ = cv2.projectPoints(
        object_points,
        rotation_vector,
        translation_vector,
        fitted_matrix,
        np.zeros(8, dtype=np.float64),
    )
    residuals = projected.reshape(-1, 2) - image_points
    residual_norms = np.linalg.norm(residuals, axis=1)
    focal = float(fitted_matrix[0, 0])
    vertical_fov = math.degrees(2.0 * math.atan(height / (2.0 * focal)))
    return {
        "camera_matrix": fitted_matrix,
        "rotation_vector_board_to_camera_cv": rotation_vector,
        "translation_board_to_camera_cv_m": translation_vector,
        "opencv_rms_source_px": float(rms),
        "reprojection_rms_source_px": float(
            np.sqrt(np.mean(np.square(residual_norms)))
        ),
        "reprojection_max_source_px": float(np.max(residual_norms)),
        "focal_length_px": focal,
        "vertical_fov_degrees": vertical_fov,
        "correspondence_evidence": evidence,
        "projected_correspondence_pixels": projected.reshape(-1, 2).tolist(),
    }


def _rotation_z(angle_degrees: float) -> np.ndarray:
    angle = math.radians(angle_degrees)
    return np.asarray(
        [
            [math.cos(angle), -math.sin(angle), 0.0],
            [math.sin(angle), math.cos(angle), 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )


def _robot_mount_transform(
    capture_config: dict[str, Any], robot_name: str
) -> tuple[np.ndarray, np.ndarray]:
    geometry = scene_geometry(capture_config)
    robot = next(
        row
        for row in capture_config["simulation_estimates"]["robots"]
        if row["name"] == robot_name
    )
    position = np.asarray(
        _table_to_world(
            geometry,
            *(float(value) for value in robot["mount_in_table_frame_xyz_m"]),
        ),
        dtype=np.float64,
    )
    rotation = _rotation_z(
        geometry.table_yaw_degrees
        + float(robot["yaw_relative_to_table_degrees"])
    )
    return position, rotation


def camera_pose_in_robot_frame(
    contract: dict[str, Any], fit: dict[str, Any]
) -> dict[str, Any]:
    capture = load_capture_config(DEFAULT_CAPTURE_CONFIG)
    geometry = scene_geometry(capture)
    source_scene = str(contract["physical_source"]["recorded_scene_id"])
    board_center = registered_board_center(source_scene)
    board_x, board_y, _ = _table_to_world(
        geometry, board_center[0], board_center[1], geometry.table_top
    )
    board_origin_world = np.asarray(
        [
            board_x,
            board_y,
            geometry.table_top + geometry.board_thickness + 0.001,
        ],
        dtype=np.float64,
    )
    board_to_world = _rotation_z(geometry.board_yaw_degrees)
    board_to_camera, _ = cv2.Rodrigues(
        fit["rotation_vector_board_to_camera_cv"]
    )
    translation = fit["translation_board_to_camera_cv_m"]
    camera_position_board = -board_to_camera.T @ translation
    camera_position_world = board_origin_world + board_to_world @ camera_position_board
    camera_cv_to_world = board_to_world @ board_to_camera.T

    robot_name = str(contract["robot_anchor"]["robot"])
    robot_position_world, robot_to_world = _robot_mount_transform(capture, robot_name)
    camera_position_robot = robot_to_world.T @ (
        camera_position_world - robot_position_world
    )
    camera_cv_to_robot = robot_to_world.T @ camera_cv_to_world
    return {
        "robot": robot_name,
        "frame": str(contract["robot_anchor"]["frame"]),
        "camera_position_robot_m": camera_position_robot,
        "camera_cv_to_robot_rotation": camera_cv_to_robot,
        "camera_position_world_m": camera_position_world,
        "camera_cv_to_world_rotation": camera_cv_to_world,
        "historical_board_origin_world_m": board_origin_world,
    }


def _verified_source(
    contract: dict[str, Any], recording_directory: Path
) -> tuple[dict[str, Any], list[dict[str, Any]], Path]:
    physical = contract["physical_source"]
    ledger_path = Path(physical["ledger_path"])
    if sha256_file(ledger_path) != physical["ledger_sha256"]:
        raise ValueError("physical intake ledger hash drifted")
    ledger = _load_json(ledger_path)
    episode = next(
        row
        for row in ledger["episodes"]
        if row["recording_id"] == physical["recording_id"]
    )
    receipt_path = recording_directory / "recording_receipt.json"
    samples_path = recording_directory / physical["samples_name"]
    video_path = recording_directory / physical["video_name"]
    expected = {
        receipt_path: episode["receipt_sha256"],
        samples_path: episode["samples_sha256"],
        video_path: episode["overhead_video_sha256"],
    }
    for path, digest in expected.items():
        if not path.is_file():
            raise FileNotFoundError(f"camera overlay source is missing {path}")
        if sha256_file(path) != digest:
            raise ValueError(f"camera overlay source hash drifted: {path}")
    receipt = _load_json(receipt_path)
    if receipt["recording_id"] != physical["recording_id"]:
        raise ValueError("camera overlay recording identity drifted")
    samples = [
        json.loads(line)
        for line in samples_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not samples:
        raise ValueError("camera overlay sample stream is empty")
    return receipt, samples, video_path


def _read_video_frame(
    video_path: Path, video_time_seconds: float, expected_size: tuple[int, int]
) -> tuple[np.ndarray, int, float]:
    capture = cv2.VideoCapture(str(video_path))
    try:
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        if not math.isfinite(fps) or fps <= 0.0:
            raise ValueError("camera overlay video has no finite FPS")
        frame_index = int(round(video_time_seconds * fps))
        capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
        ok, frame = capture.read()
        if not ok or frame is None:
            raise ValueError("camera overlay could not decode the selected frame")
    finally:
        capture.release()
    height, width = frame.shape[:2]
    if (width, height) != expected_size:
        raise ValueError(
            f"camera overlay frame expected {expected_size}, got {(width, height)}"
        )
    return frame, frame_index, fps


def _nearest_sample(
    samples: list[dict[str, Any]], video_time_seconds: float
) -> dict[str, Any]:
    return min(
        samples,
        key=lambda row: abs(
            float(row["overhead_video_time_seconds"]) - video_time_seconds
        ),
    )


def _apply_robot_pose(
    model: mujoco.MjModel, data: mujoco.MjData, sample: dict[str, Any]
) -> None:
    actuator_ids: list[int] = []
    qpos_addresses: list[int] = []
    for joint in ROBOT_JOINTS:
        name = f"left_{joint}"
        actuator_ids.append(
            mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, name)
        )
        joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        qpos_addresses.append(int(model.jnt_qposadr[joint_id]))
    bounds = model.actuator_ctrlrange[actuator_ids]
    pose = physical_values_to_sim(
        sample["follower_actual_position_degrees"], bounds[-1]
    )
    pose = np.clip(pose, bounds[:, 0], bounds[:, 1])
    data.qpos[qpos_addresses] = pose
    data.ctrl[actuator_ids] = pose


def _camera_world_from_robot(
    contract: dict[str, Any], pose: dict[str, Any]
) -> tuple[np.ndarray, np.ndarray]:
    capture = load_capture_config(DEFAULT_CAPTURE_CONFIG)
    robot_position, robot_to_world = _robot_mount_transform(
        capture, str(contract["robot_anchor"]["robot"])
    )
    camera_position = robot_position + robot_to_world @ pose["camera_position_robot_m"]
    camera_cv_to_world = robot_to_world @ pose["camera_cv_to_robot_rotation"]
    return camera_position, camera_cv_to_world


def _configure_camera(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    camera_position_world: np.ndarray,
    camera_cv_to_world: np.ndarray,
    vertical_fov_degrees: float,
) -> None:
    camera_id = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_CAMERA, "workcell"
    )
    model.cam_mode[camera_id] = mujoco.mjtCamLight.mjCAMLIGHT_FIXED
    model.cam_pos[camera_id] = camera_position_world
    camera_mujoco_to_world = camera_cv_to_world @ np.diag([1.0, -1.0, -1.0])
    quaternion = np.empty(4, dtype=np.float64)
    mujoco.mju_mat2Quat(quaternion, camera_mujoco_to_world.reshape(-1))
    model.cam_quat[camera_id] = quaternion
    model.cam_fovy[camera_id] = vertical_fov_degrees
    mujoco.mj_forward(model, data)


def _render_scene(
    contract: dict[str, Any],
    pose: dict[str, Any],
    fit: dict[str, Any],
    sample: dict[str, Any],
    board_center: tuple[float, float] | None,
) -> tuple[np.ndarray, mujoco.MjModel, mujoco.MjData]:
    width, height = (int(value) for value in contract["physical_source"]["image_size_px"])
    model = build_scene_spec(
        piece_layout=CURRENT_TASK_PIECE_LAYOUT,
        board_center_in_table_frame_xy_m=board_center,
    ).compile()
    data = mujoco.MjData(model)
    initialize_robot_poses(model, data)
    _apply_robot_pose(model, data, sample)
    camera_position, camera_cv_to_world = _camera_world_from_robot(contract, pose)
    _configure_camera(
        model,
        data,
        camera_position,
        camera_cv_to_world,
        float(fit["vertical_fov_degrees"]),
    )
    renderer = mujoco.Renderer(model, height=height, width=width)
    try:
        renderer.update_scene(data, camera="workcell")
        rgb = renderer.render().copy()
    finally:
        renderer.close()
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), model, data


def _project_world_point(
    point_world: np.ndarray,
    camera_position_world: np.ndarray,
    camera_cv_to_world: np.ndarray,
    camera_matrix: np.ndarray,
) -> np.ndarray:
    point_camera = camera_cv_to_world.T @ (point_world - camera_position_world)
    if float(point_camera[2]) <= 0.0:
        raise ValueError("robot anchor marker is behind the fitted camera")
    pixel = camera_matrix @ point_camera
    return pixel[:2] / pixel[2]


def _detect_robot_marker(
    physical_frame: np.ndarray, contract: dict[str, Any]
) -> dict[str, Any]:
    marker = contract["robot_anchor"]["diagnostic_marker"]
    hsv = cv2.cvtColor(physical_frame, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(
        hsv,
        np.asarray(marker["hsv_low"], dtype=np.uint8),
        np.asarray(marker["hsv_high"], dtype=np.uint8),
    )
    count, _, stats, centroids = cv2.connectedComponentsWithStats(mask)
    candidates: list[dict[str, Any]] = []
    for index in range(1, count):
        area = int(stats[index, cv2.CC_STAT_AREA])
        if not (
            int(marker["minimum_component_area_px"])
            <= area
            <= int(marker["maximum_component_area_px"])
        ):
            continue
        candidates.append(
            {
                "area_px": area,
                "centroid_px": centroids[index].astype(float).tolist(),
                "bounding_box_xywh_px": stats[index, :4].astype(int).tolist(),
            }
        )
    if not candidates:
        raise ValueError("robot anchor marker was not detected in the physical frame")
    selected = max(candidates, key=lambda row: row["area_px"])
    selected["candidate_count"] = len(candidates)
    return selected


def _annotate_marker(
    image: np.ndarray,
    physical_pixel: np.ndarray,
    simulated_pixel: np.ndarray,
) -> np.ndarray:
    annotated = image.copy()
    physical = tuple(np.rint(physical_pixel).astype(int))
    simulated = tuple(np.rint(simulated_pixel).astype(int))
    cv2.circle(annotated, physical, 8, (0, 165, 255), 2, cv2.LINE_AA)
    cv2.circle(annotated, simulated, 8, (0, 232, 171), 2, cv2.LINE_AA)
    cv2.line(annotated, physical, simulated, (255, 64, 110), 2, cv2.LINE_AA)
    return annotated


def _write_bgr(path: Path, image: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), image):
        raise ValueError(f"failed to write camera overlay image: {path}")


def _comparison_strip(images: list[tuple[str, np.ndarray]]) -> np.ndarray:
    panels: list[np.ndarray] = []
    for label, image in images:
        panel = image.copy()
        cv2.rectangle(panel, (0, 0), (panel.shape[1], 32), (8, 12, 18), -1)
        cv2.putText(
            panel,
            label,
            (10, 22),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.52,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
        panels.append(panel)
    return np.concatenate(panels, axis=1)


def build_robot_anchored_overlay(
    *,
    config_path: Path = DEFAULT_OVERLAY_CONFIG,
    recording_directory: Path | None = None,
    output_directory: Path = Path("outputs/sim_real_bridge/robot_anchored_overlay"),
) -> dict[str, Any]:
    contract = _load_json(config_path)
    physical = contract["physical_source"]
    if recording_directory is None:
        recording_directory = Path(physical["recording_directory"])
    receipt, samples, video_path = _verified_source(contract, recording_directory)
    width, height = (int(value) for value in physical["image_size_px"])
    video_time = float(physical["video_time_seconds"])
    physical_frame, video_frame_index, video_fps = _read_video_frame(
        video_path, video_time, (width, height)
    )
    sample = _nearest_sample(samples, video_time)
    fit = fit_board_camera(contract)
    pose = camera_pose_in_robot_frame(contract, fit)

    historical_center = registered_board_center(str(physical["recorded_scene_id"]))
    historical_sim, historical_model, historical_data = _render_scene(
        contract, pose, fit, sample, historical_center
    )
    current_sim, _, _ = _render_scene(contract, pose, fit, sample, None)
    historical_overlay = cv2.addWeighted(physical_frame, 0.5, historical_sim, 0.5, 0.0)
    current_overlay = cv2.addWeighted(physical_frame, 0.5, current_sim, 0.5, 0.0)

    detected_marker = _detect_robot_marker(physical_frame, contract)
    marker_body = str(
        contract["robot_anchor"]["diagnostic_marker"]["simulator_body"]
    )
    marker_body_id = mujoco.mj_name2id(
        historical_model, mujoco.mjtObj.mjOBJ_BODY, marker_body
    )
    camera_position_world, camera_cv_to_world = _camera_world_from_robot(
        contract, pose
    )
    simulated_marker = _project_world_point(
        historical_data.xpos[marker_body_id],
        camera_position_world,
        camera_cv_to_world,
        fit["camera_matrix"],
    )
    physical_marker = np.asarray(detected_marker["centroid_px"], dtype=np.float64)
    marker_residual = float(np.linalg.norm(simulated_marker - physical_marker))
    marker_threshold = float(
        contract["robot_anchor"]["diagnostic_marker"][
            "maximum_validation_residual_px"
        ]
    )
    marker_overlay = _annotate_marker(
        historical_overlay, physical_marker, simulated_marker
    )

    output_directory.mkdir(parents=True, exist_ok=True)
    artifact_images = {
        "physical_frame": physical_frame,
        "historical_72mm_sim": historical_sim,
        "historical_72mm_overlay": marker_overlay,
        "current_100mm_sim": current_sim,
        "current_100mm_transfer_preview": current_overlay,
    }
    artifact_paths: dict[str, Path] = {}
    for name, image in artifact_images.items():
        path = output_directory / f"{name}.png"
        _write_bgr(path, image)
        artifact_paths[name] = path
    strip = _comparison_strip(
        [
            ("physical v2", physical_frame),
            ("sim v2", historical_sim),
            ("50% overlay + robot residual", marker_overlay),
            ("sim current v3 / 100 mm", current_sim),
        ]
    )
    strip_path = output_directory / "comparison_strip.png"
    _write_bgr(strip_path, strip)
    artifact_paths["comparison_strip"] = strip_path

    current_center = np.asarray(
        load_capture_config(DEFAULT_CAPTURE_CONFIG)["simulation_estimates"]["board"][
            "center_in_table_frame_xy_m"
        ],
        dtype=np.float64,
    )
    historical_center_array = np.asarray(historical_center, dtype=np.float64)
    board_delta = current_center - historical_center_array
    expected_increment = float(
        contract["transfer_preview"]["expected_increment_from_recording_m"]
    )
    if not math.isclose(
        float(np.linalg.norm(board_delta)), expected_increment, abs_tol=1e-12
    ):
        raise ValueError("historical-to-current board increment drifted")
    report: dict[str, Any] = {
        "schema_version": OVERLAY_RECEIPT_SCHEMA,
        "created_at": datetime.now(UTC).isoformat(),
        "registration_id": contract["registration_id"],
        "config_path": str(config_path),
        "config_sha256": sha256_file(config_path),
        "module_sha256": sha256_file(Path(__file__)),
        "source": {
            "recording_id": receipt["recording_id"],
            "recording_receipt_sha256": sha256_file(
                recording_directory / "recording_receipt.json"
            ),
            "samples_sha256": sha256_file(recording_directory / physical["samples_name"]),
            "video_sha256": sha256_file(video_path),
            "video_frame_index": video_frame_index,
            "video_time_seconds_requested": video_time,
            "video_fps": video_fps,
            "matched_sample_index": int(sample["sample_index"]),
            "matched_sample_video_time_seconds": float(
                sample["overhead_video_time_seconds"]
            ),
            "recorded_scene_id": physical["recorded_scene_id"],
            "recorded_board_pose_id": physical["recorded_board_pose_id"],
        },
        "board_derived_camera_fit": {
            "fit_point_count": len(fit["correspondence_evidence"]),
            "camera_matrix": fit["camera_matrix"].tolist(),
            "focal_length_px": fit["focal_length_px"],
            "vertical_fov_degrees": fit["vertical_fov_degrees"],
            "opencv_rms_source_px": fit["opencv_rms_source_px"],
            "reprojection_rms_source_px": fit["reprojection_rms_source_px"],
            "reprojection_max_source_px": fit["reprojection_max_source_px"],
            "rotation_vector_board_to_camera_cv": fit[
                "rotation_vector_board_to_camera_cv"
            ].tolist(),
            "translation_board_to_camera_cv_m": fit[
                "translation_board_to_camera_cv_m"
            ].tolist(),
            "correspondence_evidence": fit["correspondence_evidence"],
            "projected_correspondence_pixels": fit[
                "projected_correspondence_pixels"
            ],
        },
        "robot_anchor": {
            "robot": pose["robot"],
            "frame": pose["frame"],
            "camera_position_robot_m": pose["camera_position_robot_m"].tolist(),
            "camera_cv_to_robot_rotation": pose[
                "camera_cv_to_robot_rotation"
            ].tolist(),
            "robot_geometry_moved_to_hide_residual": False,
            "diagnostic_marker": {
                **detected_marker,
                "simulator_body": marker_body,
                "simulated_pixel": simulated_marker.tolist(),
                "residual_px": marker_residual,
                "maximum_validation_residual_px": marker_threshold,
                "validation_passed": marker_residual <= marker_threshold,
                "interpretation": (
                    "unresolved physical-to-simulator joint-zero or landmark "
                    "correspondence; camera fit is visual-only"
                ),
            },
        },
        "transfer_preview": {
            "historical_board_center_in_table_frame_xy_m": historical_center_array.tolist(),
            "current_board_center_in_table_frame_xy_m": current_center.tolist(),
            "historical_to_current_board_delta_m": board_delta.tolist(),
            "historical_to_current_board_distance_m": float(np.linalg.norm(board_delta)),
            **contract["transfer_preview"],
            "current_100mm_spatially_validated_by_this_video": False,
        },
        "artifacts": {
            name: {"path": str(path), "sha256": sha256_file(path)}
            for name, path in artifact_paths.items()
        },
        "authority": {
            **contract["authority"],
            "joint_response_receipt_used_as_spatial_authority": False,
            "task_success_inferred_from_overlay": False,
        },
    }
    receipt_path = output_directory / "receipt.json"
    receipt_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    report["receipt_path"] = str(receipt_path)
    report["receipt_sha256"] = sha256_file(receipt_path)
    return report
