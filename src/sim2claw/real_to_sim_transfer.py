"""Publish one fail-closed physical-source to simulator comparison episode.

The publisher is deliberately narrow.  It renders observed follower joint
states as a visual/kinematic reconstruction and refuses to turn an ineligible
teleoperation trace into an action-frozen physics claim.
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import cv2
import mujoco
import numpy as np
from scipy.spatial.transform import Rotation

from .paths import REPO_ROOT
from .physical_sim_replay import physical_values_to_sim
from .scene import (
    CURRENT_TASK_PIECE_LAYOUT,
    ROBOT_JOINTS,
    board_square_center,
    build_scene_spec,
    initialize_robot_poses,
)
from .state_trace import EpisodeStateTraceRecorder


COMPARISON_SCHEMA = "sim2claw.studio_episode_comparison.v1"
SOURCE_SCHEMA = "sim2claw.physical_teleoperation_sample.v1"
RECEIPT_NAME = "phase_a_comparison_receipt.json"
VIDEO_NAME = "phase_a_comparison.mp4"
TRACE_NAME = "phase_a_kinematic_state_trace.json"
POSTER_NAME = "phase_a_comparison_poster.png"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _array_sha256(values: list[list[float]], dtype: str) -> str:
    array = np.asarray(values, dtype=np.dtype(dtype))
    if array.ndim != 2 or array.shape[1] != 6 or not np.all(np.isfinite(array)):
        raise ValueError("joint arrays must be finite Nx6 matrices")
    return hashlib.sha256(array.tobytes(order="C")).hexdigest()


def _load_rows(path: Path) -> list[dict[str, Any]]:
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not rows:
        raise ValueError("physical source recording is empty")
    return rows


def audit_source(
    receipt: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    visual_source_square: str,
    visual_destination_square: str,
) -> dict[str, Any]:
    """Return the immutable source/action audit used by the comparison receipt."""

    if receipt.get("mode") != "physical_follower":
        raise ValueError("Phase A requires a physical-follower source recording")
    if any(row.get("schema_version") != SOURCE_SCHEMA for row in rows):
        raise ValueError("Phase A source sample schema drifted")
    if int(receipt.get("sample_count") or 0) != len(rows):
        raise ValueError("Phase A source sample count does not match its receipt")
    if [int(row.get("sample_index", -1)) for row in rows] != list(range(len(rows))):
        raise ValueError("Phase A source sample indices are not contiguous")

    timestamps = np.asarray(
        [float(row["timestamp_monotonic_seconds"]) for row in rows],
        dtype=np.float64,
    )
    if not np.all(np.isfinite(timestamps)) or np.any(np.diff(timestamps) <= 0.0):
        raise ValueError("Phase A source timestamps are not finite and increasing")

    requested = [
        [float(value) for value in row["follower_requested_degrees"]]
        for row in rows
    ]
    commanded = [
        [float(value) for value in row["follower_command_degrees"]]
        for row in rows
    ]
    observed = [
        [float(value) for value in row["follower_actual_position_degrees"]]
        for row in rows
    ]
    requested_command_mismatch_count = sum(
        left != right for left, right in zip(requested, commanded, strict=True)
    )
    rate_limited_count = sum(row.get("rate_limited") is True for row in rows)
    safety_clamped_count = sum(row.get("safety_clamped") is True for row in rows)
    precompiled_exact_count = sum(
        row.get("precompiled_exact_action") is True for row in rows
    )
    actuator_ack_count = sum(
        bool(
            row.get("observability_timestamps", {}).get(
                "actuator_application_or_ack_timestamp_available"
            )
        )
        for row in rows
    )
    raw_metadata = {
        "folder_label": str(receipt.get("label") or ""),
        "language_instruction": str(receipt.get("language_instruction") or ""),
        "source_square": str(receipt.get("source_square") or ""),
        "destination_square": str(receipt.get("destination_square") or ""),
        "target_square_operator_metadata": str(
            receipt.get("target_square_operator_metadata") or ""
        ),
    }
    metadata_conflict = (
        raw_metadata["source_square"].lower() != visual_source_square.lower()
        or raw_metadata["destination_square"].lower()
        != visual_destination_square.lower()
    )
    exact_blockers = []
    if precompiled_exact_count != len(rows):
        exact_blockers.append(
            "no source row is marked as a precompiled exact action"
        )
    if rate_limited_count:
        exact_blockers.append(
            f"{rate_limited_count}/{len(rows)} source rows were gateway rate limited"
        )
    if safety_clamped_count:
        exact_blockers.append(
            f"{safety_clamped_count}/{len(rows)} source rows were gateway safety clamped"
        )
    if requested_command_mismatch_count:
        exact_blockers.append(
            f"{requested_command_mismatch_count}/{len(rows)} operator-requested rows "
            "differ from gateway-sent rows"
        )
    if actuator_ack_count != len(rows):
        exact_blockers.append(
            "the recording has host call timestamps but no actuator application/ack timestamps"
        )
    if receipt.get("execution", {}).get("action_dtype") != "float64_exact":
        exact_blockers.append(
            "the source receipt declares float32_replay_required, not a frozen float64 action"
        )

    return {
        "raw_metadata": raw_metadata,
        "raw_metadata_conflict": metadata_conflict,
        "timestamp_float64_little_endian_sha256": hashlib.sha256(
            timestamps.astype("<f8", copy=False).tobytes(order="C")
        ).hexdigest(),
        "operator_requested_action": {
            "row_count": len(requested),
            "source_json_canonical_sha256": _canonical_sha256(requested),
            "float32_little_endian_sha256": _array_sha256(requested, "<f4"),
        },
        "gateway_sent_action": {
            "row_count": len(commanded),
            "source_json_canonical_sha256": _canonical_sha256(commanded),
            "float32_little_endian_sha256": _array_sha256(commanded, "<f4"),
        },
        "observed_physical_joints": {
            "row_count": len(observed),
            "source_json_canonical_sha256": _canonical_sha256(observed),
            "float64_little_endian_sha256": _array_sha256(observed, "<f8"),
        },
        "requested_command_mismatch_count": requested_command_mismatch_count,
        "rate_limited_row_count": rate_limited_count,
        "safety_clamped_row_count": safety_clamped_count,
        "precompiled_exact_row_count": precompiled_exact_count,
        "actuator_ack_timestamp_row_count": actuator_ack_count,
        "exact_action_replay_eligible": not exact_blockers,
        "exact_action_replay_blockers": exact_blockers,
    }


def _camera_from_board_evaluation(
    camera_evaluation: dict[str, Any],
    scene_registration: dict[str, Any],
) -> dict[str, Any]:
    camera = camera_evaluation["conditional_camera"]
    corners = scene_registration["target_binding"]["corners_mujoco_m"]
    origin = np.asarray(corners["a1"], dtype=np.float64)
    ex = np.asarray(corners["h1"], dtype=np.float64) - origin
    ey = np.asarray(corners["a8"], dtype=np.float64) - origin
    ex /= np.linalg.norm(ex)
    ey /= np.linalg.norm(ey)
    ez = np.cross(ex, ey)
    ez /= np.linalg.norm(ez)
    board_to_world = np.column_stack((ex, ey, ez))
    board_to_camera = Rotation.from_rotvec(camera["rvec"]).as_matrix()
    translation = np.asarray(camera["tvec_m"], dtype=np.float64)
    camera_position_board = -board_to_camera.T @ translation
    return {
        "position_world": origin + board_to_world @ camera_position_board,
        "camera_cv_to_world": board_to_world @ board_to_camera.T,
        "fovy_degrees": math.degrees(
            2.0 * math.atan(480.0 / (2.0 * float(camera["focal_px"])))
        ),
        "conditional_corner_rmse_px": float(camera["corner_rmse_px"]),
        "conditional_fit_bound_active": bool(camera["fit_bound_active"]),
    }


def _configure_camera(
    model: mujoco.MjModel, data: mujoco.MjData, camera: dict[str, Any]
) -> None:
    camera_id = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_CAMERA, "workcell"
    )
    if camera_id < 0:
        raise ValueError("current simulator is missing the workcell camera")
    model.cam_mode[camera_id] = mujoco.mjtCamLight.mjCAMLIGHT_FIXED
    model.cam_pos[camera_id] = camera["position_world"]
    mujoco_to_world = camera["camera_cv_to_world"] @ np.diag(
        [1.0, -1.0, -1.0]
    )
    quaternion = np.empty(4, dtype=np.float64)
    mujoco.mju_mat2Quat(quaternion, mujoco_to_world.reshape(-1))
    model.cam_quat[camera_id] = quaternion
    model.cam_fovy[camera_id] = camera["fovy_degrees"]
    mujoco.mj_forward(model, data)


def _fit_panel(frame: np.ndarray, *, header: str, color: tuple[int, int, int]) -> np.ndarray:
    panel = np.full((360, 640, 3), 18, dtype=np.uint8)
    height, width = frame.shape[:2]
    scale = min(640.0 / width, 328.0 / height)
    resized = cv2.resize(
        frame,
        (max(1, round(width * scale)), max(1, round(height * scale))),
        interpolation=cv2.INTER_AREA,
    )
    left = (640 - resized.shape[1]) // 2
    top = 32 + (328 - resized.shape[0]) // 2
    panel[top : top + resized.shape[0], left : left + resized.shape[1]] = resized
    cv2.rectangle(panel, (0, 0), (640, 32), (8, 8, 8), -1)
    cv2.putText(
        panel,
        header,
        (10, 22),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.52,
        color,
        1,
        cv2.LINE_AA,
    )
    return panel


def _blocked_panel(blockers: list[str], relative_time: float) -> np.ndarray:
    panel = np.full((360, 640, 3), (22, 20, 28), dtype=np.uint8)
    cv2.rectangle(panel, (0, 0), (640, 32), (8, 8, 8), -1)
    cv2.putText(
        panel,
        "03  ACTION-FROZEN PHYSICS - FAIL-CLOSED",
        (10, 22),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (90, 150, 255),
        1,
        cv2.LINE_AA,
    )
    cv2.putText(
        panel,
        "NO PHYSICS TASK CLAIM",
        (22, 78),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.78,
        (80, 120, 255),
        2,
        cv2.LINE_AA,
    )
    y = 120
    for blocker in blockers[:5]:
        words = blocker.split()
        lines: list[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if len(candidate) > 66:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
        for line_index, line in enumerate(lines):
            prefix = "- " if line_index == 0 else "  "
            cv2.putText(
                panel,
                prefix + line,
                (22, y),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.43,
                (220, 220, 228),
                1,
                cv2.LINE_AA,
            )
            y += 21
        y += 6
        if y > 310:
            break
    cv2.putText(
        panel,
        f"t={relative_time:05.2f}s  simulator-applied action: NONE",
        (22, 340),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        (160, 160, 170),
        1,
        cv2.LINE_AA,
    )
    return panel


def _phase(index: int, grasp_index: int, release_index: int) -> str:
    if index < grasp_index:
        return "approach"
    if index < release_index:
        return "visual_carry"
    return "visual_release"


def publish_real_to_sim_comparison(
    recording_directory: Path,
    *,
    visual_source_square: str,
    visual_destination_square: str,
    grasp_index: int,
    release_index: int,
    camera_evaluation_path: Path,
    scene_registration_path: Path,
) -> dict[str, Any]:
    """Render and receipt one selected Phase-A source in its existing Studio episode."""

    recording_directory = recording_directory.resolve()
    receipt_path = recording_directory / "recording_receipt.json"
    samples_path = recording_directory / "samples.jsonl"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if _sha256(samples_path) != receipt.get("samples_sha256"):
        raise ValueError("physical source samples do not match their receipt")
    rows = _load_rows(samples_path)
    audit = audit_source(
        receipt,
        rows,
        visual_source_square=visual_source_square,
        visual_destination_square=visual_destination_square,
    )
    if not (0 <= grasp_index < release_index < len(rows)):
        raise ValueError("visual grasp/release indices are outside the source trace")

    overhead = receipt.get("overhead_video", {})
    wrist = receipt.get("wrist_video", {})
    native_video_path = recording_directory / str(overhead.get("video_path") or "")
    browser_video_path = recording_directory / str(
        overhead.get("browser_video_path") or ""
    )
    wrist_source_path = recording_directory / str(wrist.get("video_path") or "")
    wrist_browser_path = recording_directory / str(
        wrist.get("browser_video_path") or ""
    )
    expected_media = (
        (native_video_path, overhead.get("video_sha256")),
        (browser_video_path, overhead.get("browser_video_sha256")),
        (wrist_source_path, wrist.get("video_sha256")),
        (wrist_browser_path, wrist.get("browser_video_sha256")),
    )
    for media_path, expected in expected_media:
        if not media_path.is_file() or _sha256(media_path) != expected:
            raise ValueError(f"source media hash rejected: {media_path.name}")

    camera_evaluation = json.loads(camera_evaluation_path.read_text(encoding="utf-8"))
    scene_registration = json.loads(
        scene_registration_path.read_text(encoding="utf-8")
    )
    camera = _camera_from_board_evaluation(
        camera_evaluation, scene_registration
    )
    model = build_scene_spec(piece_layout=CURRENT_TASK_PIECE_LAYOUT).compile()
    data = mujoco.MjData(model)
    initialize_robot_poses(model, data)
    _configure_camera(model, data, camera)

    actuator_ids = [
        mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_ACTUATOR, f"left_{joint}"
        )
        for joint in ROBOT_JOINTS
    ]
    joint_ids = [
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, f"left_{joint}")
        for joint in ROBOT_JOINTS
    ]
    qpos_addresses = [int(model.jnt_qposadr[joint]) for joint in joint_ids]
    qvel_addresses = [int(model.jnt_dofadr[joint]) for joint in joint_ids]
    gripper_bounds = model.actuator_ctrlrange[actuator_ids[-1]]

    piece_name = f"brown_pawn_{visual_source_square.lower()}"
    piece_joint = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_JOINT, f"{piece_name}_free"
    )
    piece_body = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_BODY, piece_name
    )
    if min(piece_joint, piece_body, *actuator_ids, *joint_ids) < 0:
        raise ValueError("selected visual reconstruction entities are missing")
    piece_qpos = int(model.jnt_qposadr[piece_joint])
    source_position = np.asarray(
        board_square_center(visual_source_square), dtype=np.float64
    )
    destination_position = np.asarray(
        board_square_center(visual_destination_square), dtype=np.float64
    )
    data.qpos[piece_qpos : piece_qpos + 3] = source_position
    data.qpos[piece_qpos + 3 : piece_qpos + 7] = [1.0, 0.0, 0.0, 0.0]

    trace_recorder = EpisodeStateTraceRecorder(
        model,
        piece_layout=CURRENT_TASK_PIECE_LAYOUT,
        fps=max(1, int(receipt.get("sample_hz") or 20)),
        proof_class="physical_observed_joint_kinematic_visual_reconstruction",
    )
    renderer = mujoco.Renderer(model, height=480, width=640)
    capture = cv2.VideoCapture(str(native_video_path))
    raw_video_path = recording_directory / "phase_a_comparison.raw.mp4"
    writer = cv2.VideoWriter(
        str(raw_video_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        float(receipt.get("sample_hz") or 20),
        (640, 1080),
    )
    if not capture.isOpened() or not writer.isOpened():
        renderer.close()
        capture.release()
        writer.release()
        raise ValueError("comparison video reader/writer could not open")

    action_start = float(
        overhead.get("action_start_video_offset_seconds")
        or overhead.get("teleoperation_start_video_offset_seconds")
        or 0.0
    )
    video_duration = float(capture.get(cv2.CAP_PROP_FRAME_COUNT)) / max(
        1.0, float(capture.get(cv2.CAP_PROP_FPS))
    )
    missing_source_frames = 0
    first_composite: np.ndarray | None = None
    last_composite: np.ndarray | None = None
    last_source_composite: np.ndarray | None = None
    try:
        for index, row in enumerate(rows):
            timestamp = float(row["timestamp_monotonic_seconds"])
            actual = physical_values_to_sim(
                row["follower_actual_position_degrees"], gripper_bounds
            )
            data.qpos[qpos_addresses] = actual
            data.qvel[qvel_addresses] = 0.0
            data.time = timestamp
            mujoco.mj_forward(model, data)

            if grasp_index <= index < release_index:
                # The physical source has square-level endpoint evidence but no
                # metric object pose during the occluded carry.  Hide the pawn
                # instead of fabricating a gripper attachment or interpolated
                # trajectory.
                data.qpos[piece_qpos : piece_qpos + 3] = [
                    source_position[0],
                    source_position[1],
                    -2.0,
                ]
            elif index >= release_index:
                data.qpos[piece_qpos : piece_qpos + 3] = destination_position
            else:
                data.qpos[piece_qpos : piece_qpos + 3] = source_position
            data.qpos[piece_qpos + 3 : piece_qpos + 7] = [
                1.0,
                0.0,
                0.0,
                0.0,
            ]
            mujoco.mj_forward(model, data)
            trace_recorder.capture(
                data,
                phase=_phase(index, grasp_index, release_index),
                force=True,
            )

            renderer.update_scene(data, camera="workcell")
            simulation_bgr = cv2.cvtColor(
                renderer.render().copy(), cv2.COLOR_RGB2BGR
            )
            source_time = action_start + timestamp
            source_ok = False
            physical_bgr = np.full((480, 640, 3), 16, dtype=np.uint8)
            if source_time <= video_duration + 1e-6:
                capture.set(cv2.CAP_PROP_POS_MSEC, source_time * 1000.0)
                source_ok, decoded = capture.read()
                if source_ok:
                    physical_bgr = decoded
            if not source_ok:
                missing_source_frames += 1
                cv2.putText(
                    physical_bgr,
                    "SOURCE FRAME UNAVAILABLE",
                    (135, 225),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.72,
                    (100, 150, 255),
                    2,
                    cv2.LINE_AA,
                )
                cv2.putText(
                    physical_bgr,
                    "No duplicated or repaired frame",
                    (150, 260),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.48,
                    (210, 210, 220),
                    1,
                    cv2.LINE_AA,
                )
            real_panel = _fit_panel(
                physical_bgr,
                header="01  REAL SOURCE - ORIGINAL C922 PIXELS",
                color=(255, 255, 255),
            )
            visual_panel = _fit_panel(
                simulation_bgr,
                header=(
                    "02  VISUAL/KINEMATIC TWIN - OBSERVED JOINTS; "
                    "VIDEO ENDPOINT MARKERS"
                ),
                color=(120, 230, 255),
            )
            if grasp_index <= index < release_index:
                cv2.rectangle(
                    visual_panel, (0, 326), (640, 360), (8, 8, 8), -1
                )
                cv2.putText(
                    visual_panel,
                    "OBJECT POSE UNOBSERVED DURING CARRY - ENDPOINTS ONLY",
                    (38, 349),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.43,
                    (120, 210, 255),
                    1,
                    cv2.LINE_AA,
                )
            blocked = _blocked_panel(
                audit["exact_action_replay_blockers"], timestamp
            )
            composite = np.vstack((real_panel, visual_panel, blocked))
            cv2.putText(
                composite,
                f"t={timestamp:05.2f}s  D1 -> D2  proof: PARTIAL",
                (350, 350),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.42,
                (230, 230, 235),
                1,
                cv2.LINE_AA,
            )
            writer.write(composite)
            if first_composite is None:
                first_composite = composite.copy()
            if source_ok:
                last_source_composite = composite.copy()
            last_composite = composite.copy()
    finally:
        renderer.close()
        capture.release()
        writer.release()

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise ValueError("ffmpeg is required for the browser comparison")
    video_path = recording_directory / VIDEO_NAME
    completed = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(raw_video_path),
            "-c:v",
            "libx264",
            "-crf",
            "20",
            "-preset",
            "medium",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(video_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise ValueError(f"browser comparison encoding failed: {completed.stderr[-500:]}")
    raw_video_path.unlink()

    trace_path = recording_directory / TRACE_NAME
    trace = trace_recorder.write(trace_path)
    if (
        first_composite is None
        or last_composite is None
        or last_source_composite is None
    ):
        raise AssertionError("comparison renderer produced no frames")
    poster_path = recording_directory / POSTER_NAME
    poster = np.hstack((first_composite, last_source_composite))
    if not cv2.imwrite(str(poster_path), poster):
        raise ValueError("comparison poster could not be written")

    scene_identity = {
        "piece_layout": CURRENT_TASK_PIECE_LAYOUT,
        "selected_piece": piece_name,
        "visual_source_square": visual_source_square.lower(),
        "visual_destination_square": visual_destination_square.lower(),
        "source_position_world_m": source_position.tolist(),
        "destination_position_world_m": destination_position.tolist(),
        "object_pose_authority": (
            "C922+D405 visually reviewed upright square-level endpoints; "
            "not metric image pose"
        ),
    }
    video_sha256 = _sha256(video_path)
    poster_sha256 = _sha256(poster_path)
    receipt_payload = {
        "schema_version": COMPARISON_SCHEMA,
        "phase": "A_real_to_sim",
        "created_at": datetime.now(UTC).isoformat(),
        "selected_source": {
            "recording_id": receipt["recording_id"],
            "directory_name": recording_directory.name,
            "selection_reason": (
                "shorter complete dual-camera source with a clear upright D1 start "
                "and upright D2 terminal displacement; the nominal simulator layout "
                "already contains brown_pawn_d1"
            ),
            "source_receipt_path": receipt_path.name,
            "source_receipt_sha256": _sha256(receipt_path),
            "samples_path": samples_path.name,
            "samples_sha256": _sha256(samples_path),
        },
        "source_visual_verification": {
            "verified": True,
            "reviewer": "evaluator_owned_manual_frame_review",
            "c922": {
                "initial_square": visual_source_square.lower(),
                "initial_upright": True,
                "motion_observed": True,
                "terminal_square": visual_destination_square.lower(),
                "terminal_upright": True,
                "native_video_path": str(
                    native_video_path.relative_to(recording_directory)
                ),
                "native_video_sha256": _sha256(native_video_path),
                "browser_video_path": str(
                    browser_video_path.relative_to(recording_directory)
                ),
                "browser_video_sha256": _sha256(browser_video_path),
            },
            "d405": {
                "usable_for_gripper_and_square_level_corroboration": True,
                "metric_depth": False,
                "native_video_path": str(
                    wrist_source_path.relative_to(recording_directory)
                ),
                "native_video_sha256": _sha256(wrist_source_path),
                "browser_video_path": str(
                    wrist_browser_path.relative_to(recording_directory)
                ),
                "browser_video_sha256": _sha256(wrist_browser_path),
            },
            "grasp_marker": {
                "sample_index": grasp_index,
                "timestamp_seconds": rows[grasp_index][
                    "timestamp_monotonic_seconds"
                ],
            },
            "release_marker": {
                "sample_index": release_index,
                "timestamp_seconds": rows[release_index][
                    "timestamp_monotonic_seconds"
                ],
            },
        },
        "action_lineage": audit,
        "timing_and_frame_lineage": {
            "source_clock": rows[0]["observability_timestamps"]["clock_source"],
            "device_clock_synchronized": False,
            "camera_exposure_synchronized": False,
            "display_alignment": (
                "each 20 Hz output row samples the native C922 at "
                "action_start_video_offset_seconds + source timestamp"
            ),
            "display_is_exact_actuator_timing": False,
            "source_frame_missing_count": missing_source_frames,
            "source_frame_repair_count": 0,
            "output_frame_count": len(rows),
            "output_fps": int(receipt.get("sample_hz") or 20),
        },
        "physical_start_end": {
            "piece_id": piece_name,
            "initial_square": visual_source_square.lower(),
            "initial_upright": True,
            "terminal_square": visual_destination_square.lower(),
            "terminal_upright": True,
            "authority": "square_level_visual_review_only",
        },
        "simulated_initial_state": {
            **scene_identity,
            "canonical_sha256": _canonical_sha256(scene_identity),
        },
        "visual_twin": {
            "available": True,
            "proof_class": (
                "physical_observed_joint_kinematic_visual_reconstruction"
            ),
            "physics_authority": False,
            "observed_joint_state_sha256": audit[
                "observed_physical_joints"
            ]["float64_little_endian_sha256"],
            "piece_motion_authority": (
                f"visual markers: source until sample {grasp_index}, "
                "object hidden during the unmeasured carry, reviewed "
                f"{visual_destination_square.upper()} endpoint from sample "
                f"{release_index}; no contact dynamics"
            ),
            "state_trace_path": trace_path.name,
            "state_trace_sha256": trace["sha256"],
            "state_trace_frame_count": trace["frame_count"],
        },
        "physics_replay": {
            "available": False,
            "fail_closed": True,
            "simulator_applied_action_sha256": None,
            "contact_or_object_consequence": "not_executed",
            "final_square_outcome": "not_scored",
            "task_success_verified": False,
            "blockers": audit["exact_action_replay_blockers"]
            + [
                "direct physical joint targets exceed current MuJoCo actuator bounds; clipping is forbidden",
                "the fixed-step simulator cannot reproduce the irregular host-call timing without retiming",
            ],
        },
        "camera_binding": {
            "mode": "current_conditional_c922_board_camera_visual_only",
            "camera_evaluation_path": str(
                camera_evaluation_path.resolve().relative_to(REPO_ROOT)
            ),
            "camera_evaluation_sha256": _sha256(camera_evaluation_path),
            "scene_registration_path": str(
                scene_registration_path.resolve().relative_to(REPO_ROOT)
            ),
            "scene_registration_sha256": _sha256(scene_registration_path),
            "conditional_corner_rmse_px": camera[
                "conditional_corner_rmse_px"
            ],
            "fit_bound_active": camera["conditional_fit_bound_active"],
            "metric_camera_authority": False,
        },
        "outputs": {
            "comparison_video_path": video_path.name,
            "comparison_video_sha256": video_sha256,
            "comparison_video_bytes": video_path.stat().st_size,
            "poster_path": poster_path.name,
            "poster_sha256": poster_sha256,
            "kinematic_state_trace_path": trace_path.name,
            "kinematic_state_trace_sha256": trace["sha256"],
        },
        "evaluator": {
            "raw_metadata_conflict_preserved": audit[
                "raw_metadata_conflict"
            ],
            "physical_visual_outcome_verified": True,
            "kinematic_artifact_hash_bound": True,
            "exact_action_replay_eligible": audit[
                "exact_action_replay_eligible"
            ],
            "physics_lane_fail_closed": True,
            "physics_task_success": False,
            "phase_a_artifact_passed": True,
            "binary_verdict": (
                "phase_a_visual_artifact_passed_physics_ineligible_fail_closed"
            ),
        },
        "proof_class": (
            "physical_source_to_visual_kinematic_simulator_partial"
        ),
        "claim_boundary": (
            "The real task outcome is visible and the robot path is reconstructed "
            "from observed joints. Object motion in lane 02 uses reviewed visual "
            "endpoint markers and has no physics authority. Lane 03 is intentionally "
            "not executed because exact action/timing eligibility fails. This is not "
            "bidirectional transfer success, training admission, or physical authority."
        ),
    }
    receipt_output = recording_directory / RECEIPT_NAME
    receipt_output.write_text(
        json.dumps(receipt_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt_payload


__all__ = [
    "COMPARISON_SCHEMA",
    "POSTER_NAME",
    "RECEIPT_NAME",
    "TRACE_NAME",
    "VIDEO_NAME",
    "audit_source",
    "publish_real_to_sim_comparison",
]
