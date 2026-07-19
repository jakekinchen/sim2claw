"""Review-only visuals for the bounded B-G source-fit diagnostic."""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import subprocess
from pathlib import Path
from typing import Any

import cv2
import mujoco
import numpy as np
from PIL import Image, ImageDraw

from .capture import load_capture_config
from .contact_prior import (
    apply_contact_variant,
    load_simulator_variant,
    read_contact_prior_snapshot,
)
from .paths import DEFAULT_CAPTURE_CONFIG, REPO_ROOT
from .pawn_bg_demo_sim import (
    BASELINE_PIECE_BY_FILE,
    JointAdapter,
    _id,
    physical_values_to_sim_with_adapter,
)
from .pawn_bg_reward import load_reward_contract, sha256_file
from .pawn_bg_source_fit import (
    EXPECTED_CONTRACT_SHA256,
    SourceFitError,
    _selected_training_episodes,
    extract_phase_indices,
    load_source_fit_contract,
)
from .scene import (
    CURRENT_TASK_PIECE_LAYOUT,
    ROBOT_JOINTS,
    _table_to_world,
    board_square_center,
    build_scene_spec,
    initialize_robot_poses,
    registered_board_center,
    scene_geometry,
)


VISUAL_SCHEMA = "sim2claw.pawn_bg_source_fit_visual_comparison.v3"
HISTORY_SCHEMA = "sim2claw.pawn_bg_source_fit_score_history.v1"
JOINT_TRACKING_SCHEMA = "sim2claw.pawn_bg_joint_tracking_visual.v1"
TRAJECTORY_MODES = ("command_driven_physics", "measured_actual_state")
PAWN_BG_VISUAL_PIECE_LAYOUT = "sparse_two_sided_pawns_bg_visual_v1"
PAWN_BG_VISUAL_LAYOUT_ID = "two_sided_sparse_pawns_bg_rows_1_2_7_8_visual_v1"
PAWN_BG_ROBOT_SIDE_SQUARES = ("b1", "c2", "d1", "e2", "f1", "g2")
_BEIGE_RGBA = np.asarray((0.83, 0.63, 0.36, 1.0), dtype=np.float64)
_BROWN_RGBA = np.asarray((0.27, 0.105, 0.025, 1.0), dtype=np.float64)
_TAN_PAWN_RGBA = np.asarray((0.78, 0.62, 0.40, 1.0), dtype=np.float64)
_BROWN_PAWN_RGBA = np.asarray((0.42, 0.24, 0.13, 1.0), dtype=np.float64)
C922_ANGLE_CONTRACT_PATH = (
    REPO_ROOT / "configs/experiments/pawn_bg_c922_angle_transfer_v1.json"
)
EXPECTED_C922_ANGLE_CONTRACT_SHA256 = (
    "4179694f20bc1e5aa6270bb20f0b2a616d99845d15cdb00773bac9f1aec24f71"
)


def _load_c922_angle_contract() -> dict[str, Any]:
    raw = C922_ANGLE_CONTRACT_PATH.read_bytes()
    digest = sha256_file(C922_ANGLE_CONTRACT_PATH)
    if digest != EXPECTED_C922_ANGLE_CONTRACT_SHA256:
        raise SourceFitError(
            "C922 angle-transfer contract digest rejected: "
            f"expected {EXPECTED_C922_ANGLE_CONTRACT_SHA256}, got {digest}"
        )
    try:
        contract = json.loads(raw)
    except json.JSONDecodeError as error:
        raise SourceFitError("C922 angle-transfer contract is invalid JSON") from error
    if set(contract) != {
        "schema_version", "camera_id", "purpose", "source_proposal",
        "pinhole_angle_transfer", "render_contract", "authority",
    }:
        raise SourceFitError("C922 angle-transfer contract keys drifted")
    if contract["schema_version"] != "sim2claw.pawn_bg_c922_angle_transfer.v1":
        raise SourceFitError("C922 angle-transfer schema drifted")
    source = contract["source_proposal"]
    homography = source.get("pixel_to_board_homography")
    if (
        type(homography) is not list
        or len(homography) != 3
        or any(type(row) is not list or len(row) != 3 for row in homography)
    ):
        raise SourceFitError("C922 angle-transfer homography must be 3x3")
    encoded = json.dumps(homography, separators=(",", ":")).encode("utf-8")
    if hashlib.sha256(encoded).hexdigest() != source.get("homography_sha256"):
        raise SourceFitError("C922 angle-transfer homography digest drifted")
    authority = contract["authority"]
    if (
        authority.get("visual_comparison_only") is not True
        or authority.get("physical_camera_calibration_claimed") is not False
        or authority.get("metric_pose_authority") is not False
        or authority.get("reward_or_evaluator_input") is not False
        or type(authority.get("training_rows_authorized")) is not int
        or authority.get("training_rows_authorized") != 0
        or type(authority.get("held_out_rows_used")) is not int
        or authority.get("held_out_rows_used") != 0
    ):
        raise SourceFitError("C922 angle-transfer authority drifted")
    return contract


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


def _c922_angle_camera(
    contract: dict[str, Any], board_center: tuple[float, float]
) -> dict[str, Any]:
    source = contract["source_proposal"]
    pinhole = contract["pinhole_angle_transfer"]
    homography_pixel_to_board = np.asarray(
        source["pixel_to_board_homography"], dtype=np.float64
    )
    if (
        homography_pixel_to_board.shape != (3, 3)
        or not np.isfinite(homography_pixel_to_board).all()
        or abs(float(np.linalg.det(homography_pixel_to_board))) <= 1e-12
    ):
        raise SourceFitError("C922 angle-transfer homography is singular")
    focal = float(pinhole["focal_length_px"])
    principal_x, principal_y = (
        float(value) for value in pinhole["principal_point_px"]
    )
    camera_matrix = np.asarray(
        [[focal, 0.0, principal_x], [0.0, focal, principal_y], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    homography_board_to_pixel = np.linalg.inv(homography_pixel_to_board)
    normalized = np.linalg.inv(camera_matrix) @ homography_board_to_pixel
    scale = 0.5 * (
        np.linalg.norm(normalized[:, 0]) + np.linalg.norm(normalized[:, 1])
    )
    if not math.isfinite(float(scale)) or scale <= 0.0:
        raise SourceFitError("C922 angle-transfer homography scale is invalid")
    first = normalized[:, 0] / scale
    second = normalized[:, 1] / scale
    initial_rotation = np.column_stack([first, second, np.cross(first, second)])
    left, _, right = np.linalg.svd(initial_rotation)
    board_to_camera_cv = left @ right
    if np.linalg.det(board_to_camera_cv) < 0.0:
        left[:, -1] *= -1.0
        board_to_camera_cv = left @ right
    translation_board_to_camera_cv = normalized[:, 2] / scale
    camera_position_board = (
        -board_to_camera_cv.T @ translation_board_to_camera_cv
    )

    capture = load_capture_config(DEFAULT_CAPTURE_CONFIG)
    geometry = scene_geometry(capture)
    board_surface_center_world = np.asarray(
        _table_to_world(
            geometry,
            float(board_center[0]),
            float(board_center[1]),
            geometry.table_top + geometry.board_thickness + 0.001,
        ),
        dtype=np.float64,
    )
    simulator_board_to_world = _rotation_z(geometry.board_yaw_degrees)
    axes_yaw = contract["render_contract"].get(
        "physical_board_axes_to_simulation_yaw_degrees"
    )
    if type(axes_yaw) is not float or axes_yaw != 180.0:
        raise SourceFitError("C922 physical-to-simulator board-axis mapping drifted")
    physical_board_to_simulator = _rotation_z(axes_yaw)
    physical_board_origin_simulator = physical_board_to_simulator @ np.asarray(
        [-geometry.board_side / 2.0, -geometry.board_side / 2.0, 0.0]
    )
    board_origin_world = (
        board_surface_center_world
        + simulator_board_to_world @ physical_board_origin_simulator
    )
    physical_board_to_world = (
        simulator_board_to_world @ physical_board_to_simulator
    )
    camera_position_world = (
        board_origin_world + physical_board_to_world @ camera_position_board
    )
    camera_cv_to_world = physical_board_to_world @ board_to_camera_cv.T

    corners_board = np.asarray(
        [
            [0.0, 0.0, 0.0],
            [geometry.board_side, 0.0, 0.0],
            [geometry.board_side, geometry.board_side, 0.0],
            [0.0, geometry.board_side, 0.0],
        ],
        dtype=np.float64,
    )
    projected = []
    for corner in corners_board:
        camera_point = board_to_camera_cv @ corner + translation_board_to_camera_cv
        pixel = camera_matrix @ camera_point
        projected.append((pixel[:2] / pixel[2]).tolist())
    expected = cv2.perspectiveTransform(
        corners_board[:, :2].reshape(1, -1, 2), homography_board_to_pixel
    )[0]
    residuals = np.asarray(projected) - expected
    return {
        "camera_position_world": camera_position_world,
        "camera_cv_to_world": camera_cv_to_world,
        "vertical_fov_degrees": float(pinhole["vertical_fov_degrees"]),
        "camera_matrix": camera_matrix,
        "expected_board_corners_raw_px": expected.tolist(),
        "projected_board_corners_raw_px": projected,
        "board_corner_reprojection_rms_px": float(
            np.sqrt(np.mean(np.sum(np.square(residuals), axis=1)))
        ),
        "board_corner_reprojection_max_px": float(
            np.max(np.linalg.norm(residuals, axis=1))
        ),
    }


def _configure_fixed_camera(
    model: mujoco.MjModel, data: mujoco.MjData, camera: dict[str, Any]
) -> None:
    camera_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, "workcell")
    if camera_id < 0:
        raise SourceFitError("current scene is missing the workcell camera")
    model.cam_mode[camera_id] = mujoco.mjtCamLight.mjCAMLIGHT_FIXED
    model.cam_pos[camera_id] = camera["camera_position_world"]
    camera_mujoco_to_world = camera["camera_cv_to_world"] @ np.diag(
        [1.0, -1.0, -1.0]
    )
    quaternion = np.empty(4, dtype=np.float64)
    mujoco.mju_mat2Quat(quaternion, camera_mujoco_to_world.reshape(-1))
    model.cam_quat[camera_id] = quaternion
    model.cam_fovy[camera_id] = camera["vertical_fov_degrees"]
    mujoco.mj_forward(model, data)


def _load_receipt(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SourceFitError(f"source-fit receipt is missing: {path}")
    try:
        receipt = json.loads(path.read_bytes())
    except json.JSONDecodeError as error:
        raise SourceFitError("source-fit receipt is invalid JSON") from error
    if receipt.get("source_fit_contract_sha256") != EXPECTED_CONTRACT_SHA256:
        raise SourceFitError("source-fit visual refuses a receipt from another contract")
    if receipt.get("schema_version") != "sim2claw.pawn_bg_source_fit_receipt.v1":
        raise SourceFitError("source-fit receipt schema drifted")
    return receipt


def _apply_bg_visual_layout(spec: mujoco.MjSpec) -> dict[str, Any]:
    """Apply the owner-corrected appearance without changing shared scene source."""

    bodies = {body.name: body for body in spec.bodies if body.name}
    removed = []
    for body_name in ("brown_pawn_a2", "brown_pawn_h1"):
        body = bodies.get(body_name)
        if body is None:
            raise SourceFitError(f"B-G visual layout is missing edge body {body_name}")
        spec.delete(body)
        removed.append(body_name)

    square_count = 0
    for geom in spec.geoms:
        if not geom.name.startswith("square_"):
            continue
        try:
            _, file_index, rank_index = geom.name.split("_")
            parity = int(file_index) + int(rank_index)
        except (ValueError, TypeError) as error:
            raise SourceFitError("B-G visual layout found an invalid square identity") from error
        geom.rgba = _BROWN_RGBA if parity % 2 == 0 else _BEIGE_RGBA
        square_count += 1
    if square_count != 64:
        raise SourceFitError(f"B-G visual layout requires 64 squares, found {square_count}")

    near_count = 0
    far_count = 0
    for body in spec.bodies:
        if body.name.startswith("brown_pawn_"):
            for geom in body.geoms:
                geom.rgba = _TAN_PAWN_RGBA
            near_count += 1
        elif body.name.startswith("tan_pawn_"):
            for geom in body.geoms:
                geom.rgba = _BROWN_PAWN_RGBA
            far_count += 1
    if near_count != 6 or far_count != 8:
        raise SourceFitError(
            f"B-G visual layout requires 6 robot-side and 8 far-side pawns, "
            f"found {near_count}/{far_count}"
        )
    return {
        "piece_layout": PAWN_BG_VISUAL_PIECE_LAYOUT,
        "piece_layout_id": PAWN_BG_VISUAL_LAYOUT_ID,
        "robot_side_semantic_piece_squares": list(PAWN_BG_ROBOT_SIDE_SQUARES),
        "removed_robot_side_edge_piece_bodies": removed,
        "robot_side_edge_files_present": False,
        "board_beige_brown_palette_swapped": True,
        "piece_render_palette_swapped_between_sides": True,
        "semantic_piece_ids_renamed": False,
        "shared_scene_source_modified": False,
        "frozen_evaluator_scene_changed": False,
    }


def _adapter_from_receipt(receipt: dict[str, Any]) -> JointAdapter:
    payload = receipt.get("best_candidate_adapter")
    if type(payload) is not dict:
        raise SourceFitError("source-fit receipt has no best candidate adapter")
    adapter = JointAdapter(
        adapter_id=payload["adapter_id"],
        body_joint_signs=tuple(payload["body_joint_signs"]),
        body_joint_zero_offsets_rad=tuple(payload["body_joint_zero_offsets_rad"]),
        evidence_class=payload["evidence_class"],
    )
    if adapter.sha256 != payload.get("adapter_sha256"):
        raise SourceFitError("best candidate adapter digest drifted")
    return adapter


def _episode_score(receipt: dict[str, Any], folder_label: str) -> dict[str, Any]:
    rows = receipt["final_contact_variants"]["nominal_uncalibrated"]["episodes"]
    matches = [row["score"] for row in rows if row["folder_label"] == folder_label]
    if len(matches) != 1:
        raise SourceFitError("source-fit receipt does not contain exactly one requested episode")
    return matches[0]


def _annotate_pair(
    physical_bgr: np.ndarray,
    simulation_rgb: np.ndarray,
    *,
    relative_time_seconds: float,
    score: dict[str, Any],
    simulation_header: str,
    trajectory_mode: str,
) -> np.ndarray:
    simulation_bgr = cv2.cvtColor(simulation_rgb, cv2.COLOR_RGB2BGR)
    if physical_bgr.shape[:2] != (480, 640):
        physical_bgr = cv2.resize(physical_bgr, (640, 480), interpolation=cv2.INTER_AREA)
    if simulation_bgr.shape[:2] != (480, 640):
        simulation_bgr = cv2.resize(simulation_bgr, (640, 480), interpolation=cv2.INTER_AREA)
    canvas = np.zeros((512, 1280, 3), dtype=np.uint8)
    canvas[32:, :640] = physical_bgr
    canvas[32:, 640:] = simulation_bgr
    cv2.putText(
        canvas,
        "PHYSICAL C922 SOURCE (owner-reviewed)",
        (10, 22),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        canvas,
        simulation_header,
        (650, 22),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.48,
        (120, 220, 255),
        1,
        cv2.LINE_AA,
    )
    if trajectory_mode == "command_driven_physics":
        footer = (
            f"t={relative_time_seconds:5.2f}s | frozen command-replay reward="
            f"{score['diagnostic_reward']:.3f} | "
            f"contact={int(score['gate_results']['selected_piece_contact_observed'])} | "
            f"success={int(score['task_consequence_success'])} | NOT CALIBRATED"
        )
    else:
        footer = (
            f"t={relative_time_seconds:5.2f}s | MEASURED ENCODER-STATE KINEMATIC REPLAY | "
            "reward/contact not recomputed | NOT CALIBRATED"
        )
    cv2.rectangle(canvas, (0, 486), (1280, 512), (0, 0, 0), -1)
    cv2.putText(
        canvas,
        footer,
        (10, 505),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.48,
        (255, 255, 255),
        1,
        cv2.LINE_AA,
    )
    return canvas


def _tracking_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise SourceFitError("joint tracking summary requires at least one row")
    body_errors = np.asarray(
        [row["simulation_minus_mapped_actual_degrees"] for row in rows],
        dtype=np.float64,
    )
    command_errors = np.asarray(
        [row["physical_command_minus_actual_degrees"][:5] for row in rows],
        dtype=np.float64,
    )
    gripper_errors = np.asarray(
        [row["simulation_minus_mapped_actual_gripper_actuator"] for row in rows],
        dtype=np.float64,
    )
    if body_errors.shape != (len(rows), 5) or command_errors.shape != (len(rows), 5):
        raise SourceFitError("joint tracking row shape drifted")
    timestamps = np.asarray(
        [row["timestamp_monotonic_seconds"] for row in rows], dtype=np.float64
    )
    actual_degrees = np.asarray(
        [row["physical_actual_position_degrees"][:5] for row in rows],
        dtype=np.float64,
    )
    if actual_degrees.shape != (len(rows), 5):
        raise SourceFitError("physical actual joint row shape drifted")
    if len(rows) > 1:
        delta_time = np.diff(timestamps)
        if np.any(~np.isfinite(delta_time)) or np.any(delta_time <= 0.0):
            raise SourceFitError("joint tracking timestamps must be finite and increasing")
        delta_actual = np.diff(actual_degrees, axis=0)
        velocity = delta_actual / delta_time[:, None]
        guard_like_stalls = (
            (np.abs(delta_actual) < 0.5)
            & (np.abs(command_errors[1:]) > 2.0)
        )
    else:
        velocity = np.zeros((0, 5), dtype=np.float64)
        guard_like_stalls = np.zeros((0, 5), dtype=bool)
    return {
        "sample_count": len(rows),
        "body_joints": {
            joint: {
                "physical_command_minus_actual_rms_degrees": float(
                    np.sqrt(np.mean(np.square(command_errors[:, index])))
                ),
                "simulation_minus_mapped_actual_rms_degrees": float(
                    np.sqrt(np.mean(np.square(body_errors[:, index])))
                ),
                "simulation_minus_mapped_actual_max_abs_degrees": float(
                    np.max(np.abs(body_errors[:, index]))
                ),
                "physical_actual_min_degrees": float(np.min(actual_degrees[:, index])),
                "physical_actual_max_degrees": float(np.max(actual_degrees[:, index])),
                "physical_actual_peak_abs_velocity_degrees_s": (
                    float(np.max(np.abs(velocity[:, index])))
                    if len(velocity)
                    else 0.0
                ),
                "guard_like_stall_sample_count": int(
                    np.count_nonzero(guard_like_stalls[:, index])
                ),
            }
            for index, joint in enumerate(ROBOT_JOINTS[:5])
        },
        "gripper_simulation_minus_mapped_actual_rms_actuator": float(
            np.sqrt(np.mean(np.square(gripper_errors)))
        ),
        "gripper_simulation_minus_mapped_actual_max_abs_actuator": float(
            np.max(np.abs(gripper_errors))
        ),
        "guard_like_stall_definition": (
            "absolute measured change below 0.5 degree per sample while absolute "
            "physical command-minus-actual error exceeds 2.0 degrees"
        ),
        "guard_like_stall_is_mechanical_guard_proof": False,
    }


def _sim_to_display_units(
    simulated: np.ndarray, adapter: JointAdapter, gripper_bounds: np.ndarray
) -> list[float]:
    result = np.empty(6, dtype=np.float64)
    result[:5] = np.rad2deg(
        (simulated[:5] - np.asarray(adapter.body_joint_zero_offsets_rad))
        / np.asarray(adapter.body_joint_signs)
    )
    low, high = (float(value) for value in gripper_bounds)
    result[5] = 100.0 * (simulated[5] - low) / (high - low)
    return result.tolist()


def _render_joint_tracking_evidence(
    *,
    rows: list[dict[str, Any]],
    summary: dict[str, Any],
    trajectory_mode: str,
    folder_label: str,
    output_directory: Path,
) -> dict[str, Any]:
    payload = {
        "schema_version": JOINT_TRACKING_SCHEMA,
        "folder_label": folder_label,
        "trajectory_mode": trajectory_mode,
        "joint_order": list(ROBOT_JOINTS),
        "rows": rows,
        "summary": summary,
        "authority": {
            "diagnostic_only": True,
            "command_driven_physics_executed": trajectory_mode == "command_driven_physics",
            "reward_authority": False,
            "physical_camera_calibration_claimed": False,
            "accepted_joint_registration": False,
        },
        "claim_boundary": (
            "The measured-state mode places simulator joints at hash-bound follower encoder "
            "states after applying the best rejected adapter. It visualizes carried-out joint "
            "motion but is not a dynamics replay, reward result, camera calibration, or accepted "
            "robot-to-simulator registration."
        ),
    }
    json_path = output_directory / f"{folder_label}_joint_tracking__{trajectory_mode}.json"
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )

    chart = Image.new("RGB", (1600, 1260), color=(19, 22, 27))
    draw = ImageDraw.Draw(chart)
    draw.text((35, 20), f"B1 source joint tracking — {trajectory_mode}", fill=(255, 255, 255))
    draw.text(
        (35, 44),
        "yellow: measured follower encoder | blue: simulator display pose | rejected adapter",
        fill=(180, 187, 196),
    )
    for joint_index, joint in enumerate(ROBOT_JOINTS):
        top = 82 + joint_index * 190
        bottom = top + 155
        actual = [float(row["physical_actual_display_units"][joint_index]) for row in rows]
        simulated = [float(row["simulation_display_units"][joint_index]) for row in rows]
        low = min(actual + simulated)
        high = max(actual + simulated)
        padding = max(1.0, 0.08 * max(1.0, high - low))
        low -= padding
        high += padding
        box = (35, top, 1565, bottom)
        draw.rectangle(box, outline=(75, 80, 88), width=1)
        draw.text((45, top + 8), joint, fill=(235, 235, 235))
        if joint_index < 5:
            metric = summary["body_joints"][joint]
            unit = "deg"
            label = (
                f"sim-actual RMS {metric['simulation_minus_mapped_actual_rms_degrees']:.3f} {unit} | "
                f"max {metric['simulation_minus_mapped_actual_max_abs_degrees']:.3f} {unit}"
            )
        else:
            label = (
                "sim-actual RMS "
                f"{summary['gripper_simulation_minus_mapped_actual_rms_actuator']:.5f} actuator"
            )
        draw.text((1050, top + 8), label, fill=(180, 187, 196))
        for values, color in ((actual, (255, 196, 70)), (simulated, (70, 176, 255))):
            points = []
            for index, value in enumerate(values):
                x = 45 + index * (1510.0 / max(1, len(values) - 1))
                y = bottom - 10 - (value - low) / (high - low) * (bottom - top - 38)
                points.append((x, y))
            if len(points) > 1:
                draw.line(points, fill=color, width=2)
    chart_path = output_directory / f"{folder_label}_joint_tracking__{trajectory_mode}.png"
    chart.save(chart_path)
    return {
        "json_path": str(json_path),
        "json_sha256": sha256_file(json_path),
        "chart_path": str(chart_path),
        "chart_sha256": sha256_file(chart_path),
        "summary": summary,
    }


def render_episode_comparison(
    *,
    source_repository_root: Path,
    source_fit_receipt_path: Path,
    folder_label: str,
    output_directory: Path,
    simulation_camera_mode: str = "c922_angle_transfer",
    trajectory_mode: str = "measured_actual_state",
) -> dict[str, Any]:
    contract = load_source_fit_contract()
    receipt = _load_receipt(source_fit_receipt_path)
    adapter = _adapter_from_receipt(receipt)
    selected, _ = _selected_training_episodes(contract, source_repository_root.resolve())
    matches = [row for row in selected if row[0]["folder_label"] == folder_label]
    if len(matches) != 1:
        raise SourceFitError("visual comparison requires one allowed training episode")
    episode, source, _, samples = matches[0]
    score = _episode_score(receipt, folder_label)
    if trajectory_mode not in TRAJECTORY_MODES:
        raise SourceFitError("unknown source-fit visual trajectory mode")

    reward = load_reward_contract()
    board_center = registered_board_center(reward["scene_binding"]["scene_id"])
    if simulation_camera_mode not in {"c922_angle_transfer", "scene_overhead"}:
        raise SourceFitError("unknown source-fit visual simulation camera mode")
    angle_contract: dict[str, Any] | None = None
    angle_camera: dict[str, Any] | None = None
    if simulation_camera_mode == "c922_angle_transfer":
        angle_contract = _load_c922_angle_contract()
        reference_frame = (
            source_repository_root
            / angle_contract["source_proposal"]["reference_frame_path"]
        )
        if (
            not reference_frame.is_file()
            or sha256_file(reference_frame)
            != angle_contract["source_proposal"]["reference_frame_sha256"]
        ):
            raise SourceFitError("C922 angle-transfer reference frame hash rejected")
        angle_camera = _c922_angle_camera(angle_contract, board_center)
    spec = build_scene_spec(
        piece_layout=CURRENT_TASK_PIECE_LAYOUT,
        board_center_in_table_frame_xy_m=board_center,
    )
    visual_layout_receipt = _apply_bg_visual_layout(spec)
    prior = read_contact_prior_snapshot()
    variant = load_simulator_variant("nominal_uncalibrated", contract_snapshot=prior)
    apply_contact_variant(spec, variant)
    model = spec.compile()
    data = mujoco.MjData(model)
    initialize_robot_poses(model, data)

    piece_name = BASELINE_PIECE_BY_FILE[source[0]]
    piece_joint = _id(model, mujoco.mjtObj.mjOBJ_JOINT, f"{piece_name}_free")
    piece_qpos = int(model.jnt_qposadr[piece_joint])
    data.qpos[piece_qpos : piece_qpos + 3] = board_square_center(
        source, board_center_in_table_frame_xy_m=board_center
    )
    actuator_ids = [
        _id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, f"left_{joint}")
        for joint in ROBOT_JOINTS
    ]
    joint_ids = [
        _id(model, mujoco.mjtObj.mjOBJ_JOINT, f"left_{joint}")
        for joint in ROBOT_JOINTS
    ]
    qpos_addresses = [int(model.jnt_qposadr[joint_id]) for joint_id in joint_ids]
    dof_addresses = [int(model.jnt_dofadr[joint_id]) for joint_id in joint_ids]
    bounds = np.asarray(model.actuator_ctrlrange[actuator_ids], dtype=np.float64)
    first_actual = physical_values_to_sim_with_adapter(
        samples[0]["follower_actual_position_degrees"], bounds[-1], adapter
    )
    if np.any(first_actual < bounds[:, 0]) or np.any(first_actual > bounds[:, 1]):
        raise SourceFitError("visual comparison refuses an initial command that would clip")
    data.qpos[qpos_addresses] = first_actual
    data.ctrl[actuator_ids] = first_actual
    mujoco.mj_forward(model, data)
    mujoco.mj_step(model, data, nstep=100)
    if angle_camera is not None:
        _configure_fixed_camera(model, data, angle_camera)

    source_receipt = json.loads(
        (source_repository_root / episode["assets"]["receipt"]).read_bytes()
    )
    video_metadata = source_receipt.get("overhead_video", {})
    video_path = source_repository_root / episode["assets"]["overhead_video"]
    if video_metadata.get("video_sha256") != episode["overhead_video_sha256"]:
        raise SourceFitError("overhead video identity drifted in source receipt")
    action_offset = float(video_metadata["action_start_video_offset_seconds"])
    rotation = int(video_metadata["orientation_rotation_degrees"])
    if rotation not in (0, 180):
        raise SourceFitError("visual comparison only supports frozen 0/180 orientation")
    if (
        angle_contract is not None
        and angle_contract["render_contract"][
            "apply_source_receipt_orientation_to_both_panels"
        ]
        is not True
    ):
        raise SourceFitError("C922 angle-transfer orientation contract drifted")

    output_directory.mkdir(parents=True, exist_ok=True)
    artifact_stem = f"{folder_label}_physical_vs_sim__{trajectory_mode}"
    raw_path = output_directory / f"{artifact_stem}.raw.mp4"
    video_output = output_directory / f"{artifact_stem}.mp4"
    poster_output = output_directory / f"{artifact_stem}_poster.png"
    writer = cv2.VideoWriter(
        str(raw_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        float(episode["sample_hz"]),
        (1280, 512),
    )
    if not writer.isOpened():
        raise SourceFitError("OpenCV could not open the diagnostic comparison writer")
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        writer.release()
        raise SourceFitError("OpenCV could not open the hash-bound overhead video")
    renderer = mujoco.Renderer(model, height=480, width=640)
    open_index, close_index, release_index = extract_phase_indices(samples, contract)
    poster_indices = {
        0: "start",
        open_index: "source open",
        close_index: "source near-close",
        (close_index + release_index) // 2: "transfer",
        release_index: "destination reopen",
        len(samples) - 1: "end",
    }
    poster_frames: list[tuple[str, np.ndarray]] = []
    previous_timestamp: float | None = None
    nominal_dt = 1.0 / float(episode["sample_hz"])
    tracking_rows: list[dict[str, Any]] = []
    try:
        for index, sample in enumerate(samples):
            timestamp = float(sample["timestamp_monotonic_seconds"])
            dt = nominal_dt if previous_timestamp is None else timestamp - previous_timestamp
            if not math.isfinite(dt) or dt <= 0.0 or dt > 1.0:
                dt = nominal_dt
            previous_timestamp = timestamp
            command = physical_values_to_sim_with_adapter(
                sample["follower_command_degrees"], bounds[-1], adapter
            )
            actual = physical_values_to_sim_with_adapter(
                sample["follower_actual_position_degrees"], bounds[-1], adapter
            )
            if np.any(command < bounds[:, 0]) or np.any(command > bounds[:, 1]):
                raise SourceFitError("comparison refuses to clip a source-fit command")
            if np.any(actual < bounds[:, 0]) or np.any(actual > bounds[:, 1]):
                raise SourceFitError("comparison refuses an out-of-range measured state")
            if trajectory_mode == "command_driven_physics":
                data.ctrl[actuator_ids] = command
                mujoco.mj_step(
                    model,
                    data,
                    nstep=max(1, round(dt / float(model.opt.timestep))),
                )
            else:
                data.qpos[qpos_addresses] = actual
                data.qvel[dof_addresses] = 0.0
                data.ctrl[actuator_ids] = actual
                mujoco.mj_forward(model, data)
            simulated = np.asarray(data.qpos[qpos_addresses], dtype=np.float64).copy()
            simulated_display = _sim_to_display_units(simulated, adapter, bounds[-1])
            tracking_rows.append({
                "sample_index": index,
                "timestamp_monotonic_seconds": timestamp,
                "physical_command_degrees": [
                    float(value) for value in sample["follower_command_degrees"]
                ],
                "physical_actual_position_degrees": [
                    float(value) for value in sample["follower_actual_position_degrees"]
                ],
                "physical_actual_display_units": [
                    float(value) for value in sample["follower_actual_position_degrees"]
                ],
                "mapped_command_sim_units": command.tolist(),
                "mapped_actual_sim_units": actual.tolist(),
                "simulation_qpos_units": simulated.tolist(),
                "simulation_display_units": simulated_display,
                "physical_command_minus_actual_degrees": (
                    np.asarray(sample["follower_command_degrees"], dtype=np.float64)
                    - np.asarray(sample["follower_actual_position_degrees"], dtype=np.float64)
                ).tolist(),
                "simulation_minus_mapped_actual_degrees": np.rad2deg(
                    simulated[:5] - actual[:5]
                ).tolist(),
                "simulation_minus_mapped_actual_gripper_actuator": float(
                    simulated[5] - actual[5]
                ),
            })
            renderer.update_scene(
                data,
                camera=(
                    angle_contract["render_contract"]["mujoco_camera_name"]
                    if angle_contract is not None
                    else "overhead"
                ),
            )
            simulation_rgb = renderer.render().copy()
            capture.set(cv2.CAP_PROP_POS_MSEC, (action_offset + timestamp) * 1000.0)
            ok, physical_bgr = capture.read()
            if not ok:
                raise SourceFitError(f"overhead frame decode failed at sample {index}")
            if rotation == 180:
                physical_bgr = cv2.rotate(physical_bgr, cv2.ROTATE_180)
                if angle_contract is not None:
                    simulation_rgb = cv2.rotate(simulation_rgb, cv2.ROTATE_180)
            paired = _annotate_pair(
                physical_bgr,
                simulation_rgb,
                relative_time_seconds=timestamp,
                score=score,
                simulation_header=(
                    "SIM MEASURED ENCODER-STATE KINEMATIC REPLAY"
                    if trajectory_mode == "measured_actual_state"
                    else "SIM COMMAND-DRIVEN PHYSICS + BEST REJECTED ADAPTER"
                ),
                trajectory_mode=trajectory_mode,
            )
            writer.write(paired)
            if index in poster_indices:
                poster_frames.append((poster_indices[index], paired.copy()))
    finally:
        renderer.close()
        capture.release()
        writer.release()

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise SourceFitError("ffmpeg is required to encode the diagnostic comparison")
    completed = subprocess.run(
        [
            ffmpeg, "-y", "-loglevel", "error", "-i", str(raw_path),
            "-c:v", "libx264", "-crf", "18", "-preset", "medium",
            "-pix_fmt", "yuv420p", str(video_output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise SourceFitError(f"ffmpeg comparison encoding failed: {completed.stderr[-500:]}")
    raw_path.unlink()

    poster = Image.new("RGB", (1280, 768), color=(18, 18, 18))
    for index, (label, paired_bgr) in enumerate(poster_frames):
        image = Image.fromarray(cv2.cvtColor(paired_bgr, cv2.COLOR_BGR2RGB))
        image = image.resize((640, 256), Image.Resampling.LANCZOS)
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, 180, 22), fill=(0, 0, 0))
        draw.text((6, 5), label, fill=(255, 255, 255))
        poster.paste(image, ((index % 2) * 640, (index // 2) * 256))
    poster.save(poster_output)
    tracking_summary = _tracking_summary(tracking_rows)
    tracking_evidence = _render_joint_tracking_evidence(
        rows=tracking_rows,
        summary=tracking_summary,
        trajectory_mode=trajectory_mode,
        folder_label=folder_label,
        output_directory=output_directory,
    )

    if angle_contract is not None and angle_camera is not None:
        camera_receipt = {
            "mode": angle_contract["render_contract"]["comparison_camera_mode"],
            "camera_id": angle_contract["camera_id"],
            "contract_path": str(C922_ANGLE_CONTRACT_PATH.relative_to(REPO_ROOT)),
            "contract_sha256": EXPECTED_C922_ANGLE_CONTRACT_SHA256,
            "proposal_calibration_id": angle_contract["source_proposal"][
                "calibration_id"
            ],
            "proposal_homography_sha256": angle_contract["source_proposal"][
                "homography_sha256"
            ],
            "reference_recording_id": angle_contract["source_proposal"][
                "reference_recording_id"
            ],
            "reference_frame_sha256": angle_contract["source_proposal"][
                "reference_frame_sha256"
            ],
            "focal_length_px": angle_contract["pinhole_angle_transfer"][
                "focal_length_px"
            ],
            "vertical_fov_degrees": angle_camera["vertical_fov_degrees"],
            "camera_position_world_m": angle_camera[
                "camera_position_world"
            ].tolist(),
            "expected_board_corners_raw_px": angle_camera[
                "expected_board_corners_raw_px"
            ],
            "projected_board_corners_raw_px": angle_camera[
                "projected_board_corners_raw_px"
            ],
            "board_corner_reprojection_rms_px": angle_camera[
                "board_corner_reprojection_rms_px"
            ],
            "board_corner_reprojection_max_px": angle_camera[
                "board_corner_reprojection_max_px"
            ],
            "source_orientation_rotation_degrees_applied_to_both_panels": rotation,
            "physical_board_axes_to_simulation_yaw_degrees": angle_contract[
                "render_contract"
            ]["physical_board_axes_to_simulation_yaw_degrees"],
            "visual_comparison_only": True,
            "physical_camera_calibration_claimed": False,
            "metric_pose_authority": False,
        }
    else:
        camera_receipt = {
            "mode": "scene_overhead_legacy_visual",
            "source_orientation_rotation_degrees_applied_to_simulation": 0,
            "visual_comparison_only": True,
            "physical_camera_calibration_claimed": False,
            "metric_pose_authority": False,
        }

    report = {
        "schema_version": VISUAL_SCHEMA,
        "folder_label": folder_label,
        "recording_id": episode["recording_id"],
        "frame_count": len(samples),
        "fps": episode["sample_hz"],
        "source_samples_sha256": episode["samples_sha256"],
        "source_overhead_video_sha256": episode["overhead_video_sha256"],
        "source_fit_receipt_sha256": sha256_file(source_fit_receipt_path),
        "source_fit_contract_sha256": EXPECTED_CONTRACT_SHA256,
        "best_candidate_adapter_sha256": adapter.sha256,
        "candidate_accepted": receipt["candidate_accepted"],
        "optimization_status": receipt["optimization_status"],
        "contact_variant": "nominal_uncalibrated",
        "trajectory_mode": trajectory_mode,
        "physics_trajectory_executed": trajectory_mode == "command_driven_physics",
        "measured_encoder_state_kinematic_replay": trajectory_mode == "measured_actual_state",
        "reward_recomputed_for_display_trajectory": False,
        "visual_piece_layout": visual_layout_receipt,
        "episode_score": score,
        "physical_orientation_rotation_degrees_applied": rotation,
        "simulation_camera": camera_receipt,
        "comparison_video_path": str(video_output),
        "comparison_video_sha256": sha256_file(video_output),
        "poster_path": str(poster_output),
        "poster_sha256": sha256_file(poster_output),
        "joint_tracking_evidence": tracking_evidence,
        "claim_boundary": "Review-only synchronized physical-source versus simulated diagnostic. Measured-state mode is kinematic display only; command-driven mode is unchanged simulator physics. The B-G visual layout does not rewrite the frozen evaluator scene. The C922 angle is a proposal-derived visual transfer, the simulator adapter was rejected, and none of these are physical calibration or ACT policy proof.",
    }
    report_path = output_directory / f"{artifact_stem}_receipt.json"
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return report


def _draw_series(
    draw: ImageDraw.ImageDraw,
    values: list[float],
    *,
    box: tuple[int, int, int, int],
    low: float,
    high: float,
    color: tuple[int, int, int],
) -> None:
    left, top, right, bottom = box
    draw.rectangle(box, outline=(90, 90, 90), width=1)
    points = []
    for index, value in enumerate(values):
        x = left + 80 + index * ((right - left - 160) / max(1, len(values) - 1))
        y = bottom - 35 - (value - low) / (high - low) * (bottom - top - 70)
        points.append((x, y))
    if len(points) > 1:
        draw.line(points, fill=color, width=4)
    for point, value in zip(points, values, strict=True):
        x, y = point
        draw.ellipse((x - 6, y - 6, x + 6, y + 6), fill=color)
        draw.text((x - 35, y - 26), f"{value:.3f}", fill=(235, 235, 235))


def render_score_history(
    *, source_fit_receipt_path: Path, output_directory: Path
) -> dict[str, Any]:
    contract = load_source_fit_contract()
    receipt = _load_receipt(source_fit_receipt_path)
    baseline = receipt["baseline"]
    rows = [
        {
            "configuration_sequence": 0,
            "iteration": "00_provisional_baseline",
            "adapter_sha256": baseline["adapter"]["adapter_sha256"],
            "contact_variant_id": "nominal_uncalibrated",
            "accepted": False,
            "reason": "provisional_adapter_clips_every_episode",
            "event_rms_m": baseline["kinematic"]["event_rms_distance_m"],
            **baseline["nominal_physics"]["aggregate"],
        }
    ]
    expected_variants = contract["selection"]["selected_adapter_final_contact_variants"]
    if set(receipt["final_contact_variants"]) != set(expected_variants):
        raise SourceFitError("source-fit receipt final contact variants drifted")
    for sequence, variant_id in enumerate(expected_variants, start=1):
        variant_result = receipt["final_contact_variants"][variant_id]
        rows.append({
            "configuration_sequence": sequence,
            "iteration": f"{sequence:02d}_best_candidate__{variant_id}",
            "adapter_sha256": receipt["best_candidate_adapter"]["adapter_sha256"],
            "contact_variant_id": variant_id,
            "accepted": receipt["candidate_accepted"],
            "reason": receipt["optimization_status"],
            "event_rms_m": receipt["best_candidate_kinematic"]["event_rms_distance_m"],
            **variant_result["aggregate"],
        })
    history = {
        "schema_version": HISTORY_SCHEMA,
        "source_fit_contract_sha256": receipt["source_fit_contract_sha256"],
        "reward_contract_sha256": receipt["reward_contract_sha256"],
        "contact_prior_sha256": receipt["contact_prior_sha256"],
        "source_fit_receipt_sha256": sha256_file(source_fit_receipt_path),
        "cohort": "same_11_existing_train_partition_owner_reviewed_product_episodes",
        "rows": rows,
        "claim_boundary": "These are source-fit configurations scored on the same training-side source replay and frozen simulator evaluator. They are not physical calibration history or held-out validation.",
    }
    output_directory.mkdir(parents=True, exist_ok=True)
    json_path = output_directory / "source_fit_score_history.json"
    json_path.write_text(
        json.dumps(history, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )

    chart = Image.new("RGB", (1600, 980), color=(20, 23, 28))
    draw = ImageDraw.Draw(chart)
    draw.text((45, 28), "B-G source-fit score history", fill=(255, 255, 255))
    draw.text(
        (45, 52),
        "Same 11 training-side source episodes | frozen reward/evaluator | no held-out validation",
        fill=(170, 178, 188),
    )
    draw.text((45, 93), "Mean diagnostic reward", fill=(220, 225, 230))
    rewards = [float(row["mean_diagnostic_reward"]) for row in rows]
    _draw_series(
        draw, rewards, box=(45, 120, 1555, 350), low=-1.0, high=1.0,
        color=(255, 166, 70),
    )
    draw.text((45, 385), "Pinch-point event RMS (millimeters; lower is better)", fill=(220, 225, 230))
    rms_mm = [1000.0 * float(row["event_rms_m"]) for row in rows]
    _draw_series(
        draw, rms_mm, box=(45, 412, 1555, 642), low=0.0,
        high=max(350.0, 1.1 * max(rms_mm)), color=(80, 196, 255),
    )
    for index, row in enumerate(rows):
        y = 666 + index * 48
        draw.text((45, y), row["iteration"], fill=(235, 235, 235))
        draw.text((500, y), f"reward {row['mean_diagnostic_reward']:.3f}", fill=(185, 190, 195))
        draw.text((655, y), f"RMS {1000.0 * row['event_rms_m']:.3f} mm", fill=(185, 190, 195))
        draw.text((850, y), f"clipped {row['recordings_with_clipped_commands']}/11", fill=(185, 190, 195))
        draw.text((1015, y), f"contact {row['selected_piece_contact_episode_count']}/11", fill=(185, 190, 195))
        draw.text((1175, y), f"success {row['task_consequence_success_count']}/11", fill=(185, 190, 195))
        draw.text(
            (1340, y),
            f"accepted {'yes' if row['accepted'] else 'no'}",
            fill=(90, 220, 130) if row["accepted"] else (255, 105, 105),
        )
    draw.text(
        (45, 930),
        "Result: geometry fit improved, consequence score worsened; contact variants were insensitive; no adapter accepted.",
        fill=(255, 190, 95),
    )
    chart_path = output_directory / "source_fit_score_history.png"
    chart.save(chart_path)
    history["history_json_path"] = str(json_path)
    history["history_json_sha256"] = sha256_file(json_path)
    history["chart_path"] = str(chart_path)
    history["chart_sha256"] = sha256_file(chart_path)
    return history


__all__ = ["render_episode_comparison", "render_score_history"]
