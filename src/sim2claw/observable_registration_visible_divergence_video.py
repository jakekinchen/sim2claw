"""Render and score the retained physical versus exact-physics trace video."""

from __future__ import annotations

import copy
import json
import math
import subprocess
from pathlib import Path
from typing import Any

import cv2
import mujoco
import numpy as np

from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
    sha256_file,
)
from .observable_c922_pixel_lattice_refinement import project_camera_family
from .observable_registration_belief_recalculation import (
    REPO_ROOT,
    _bound_json,
    _bound_path,
)
from .post_hackathon_home_workspace_geometry_camera import _candidate_spec
from .real_to_sim_transfer import _configure_camera
from .realized_action_outcome_mission import (
    _tensor,
    load_contract as load_c6_contract,
    physical_to_model,
)

SCHEMA = (
    "sim2claw.observable_registration_visible_divergence_video_contract.v1"
)
RECEIPT_SCHEMA = (
    "sim2claw.observable_registration_visible_divergence_video_receipt.v1"
)
CURVES_SCHEMA = (
    "sim2claw.observable_registration_visible_divergence_curves.v1"
)
CONTRACT_PATH = (
    REPO_ROOT
    / "configs/evaluations/"
    "observable_registration_visible_divergence_video_v1.json"
)
OUTPUT_DIRECTORY = (
    REPO_ROOT / "outputs/observable_registration_visible_divergence_video_v1"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def load_visible_divergence_video_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="visible divergence video")
    _require(contract.get("schema_version") == SCHEMA, "unsupported contract")
    for name, binding in contract["sources"].items():
        _bound_path(binding, root=root, label=name)
    timeline = contract["timeline"]
    _require(
        timeline["source_row_count"] == 531
        and timeline["output_fps"] == 20
        and timeline["use_source_timestamps"] is True
        and timeline["use_recorded_action_start_video_offset"] is True
        and timeline["additional_display_lag_seconds"] == 0.0
        and timeline["camera_exposure_synchronized"] is False
        and timeline["missing_frames_must_remain_missing"] is True,
        "timeline boundary widened",
    )
    registration = contract["camera_and_display_registration"]
    _require(
        registration["measured_playing_side_m"] == 0.324
        and registration["or10_playing_side_m"] == 0.3556
        and registration["scale_or10_board_translation_only"] is True
        and registration["preserve_or10_rotation_focal_and_principal_point"]
        is True
        and registration["apply_one_board_plane_display_homography"] is True
        and registration["display_homography_is_metric_camera_calibration"]
        is False
        and registration["simulator_camera_promotion_allowed"] is False,
        "display registration boundary widened",
    )
    playback = contract["trace_playback"]
    _require(
        playback["physics_rerun_allowed"] is False
        and playback["action_change_allowed"] is False
        and playback["state_fit_allowed"] is False
        and playback["contact_or_object_parameter_change_allowed"] is False
        and playback["selected_pawn_pose_from_or21_internal_trace"] is True
        and playback["robot_pose_from_or19_identified_applied_actions"] is True,
        "trace playback boundary widened",
    )
    _require(
        not any(contract["authority"].values()),
        "visible divergence authority widened",
    )
    return contract


def first_sustained_threshold_crossing(
    values: list[float | None],
    *,
    threshold: float,
    start: int,
    minimum_rows: int,
) -> int | None:
    run = 0
    run_start = start
    for index in range(start, len(values)):
        value = values[index]
        if value is not None and float(value) > threshold:
            if run == 0:
                run_start = index
            run += 1
            if run >= minimum_rows:
                return run_start
        else:
            run = 0
    return None


def _candidate_config(
    or19: dict[str, Any], *, root: Path
) -> tuple[dict[str, Any], dict[str, Any], np.ndarray, np.ndarray]:
    c6 = load_c6_contract(
        _bound_path(
            or19["sources"]["c6_contract"],
            root=root,
            label="C6 contract",
        ),
        root=root,
    )
    source = c6["source"]
    measured = _tensor(
        _bound_path(source["initial_measured"], root=root, label="measured"),
        source["initial_measured"],
    )
    applied = _tensor(
        _bound_path(
            source["identified_applied"], root=root, label="applied"
        ),
        source["identified_applied"],
    )
    manifest = _bound_json(
        or19["sources"]["or6_candidate"],
        root=root,
        label="OR6 candidate",
    )
    historical = _bound_json(
        or19["sources"]["historical_mapping_receipt"],
        root=root,
        label="historical mapping",
    )
    candidate = copy.deepcopy(manifest["candidate_config"])
    joints = candidate["physical_adapter"]["joint_transform"]["joints"]
    offsets = historical["mapping"]["candidate"]["joint_zero_offsets_rad"]
    _require(len(offsets) == 5, "historical mapping width changed")
    for index, value in enumerate(offsets):
        joints[index]["zero_offset"] = float(value)
    joints[5]["zero_offset"] = float(
        or19["candidate"]["gripper_zero_offset_rad"]
    )
    replay_manifest = {"candidate_config": candidate}
    return (
        c6,
        candidate,
        physical_to_model(measured, replay_manifest),
        physical_to_model(applied, replay_manifest),
    )


def _scaled_camera(
    contract: dict[str, Any], *, root: Path
) -> tuple[dict[str, Any], np.ndarray, np.ndarray, dict[str, Any]]:
    or10 = _bound_json(
        contract["sources"]["or10_camera_receipt"],
        root=root,
        label="OR10 camera",
    )
    or1 = _bound_json(
        contract["sources"]["or1_camera_receipt"],
        root=root,
        label="OR1 camera",
    )
    or13 = _bound_json(
        contract["sources"]["or13_geometry_receipt"],
        root=root,
        label="OR13 geometry",
    )
    registration = contract["camera_and_display_registration"]
    scale = float(registration["measured_playing_side_m"]) / float(
        registration["or10_playing_side_m"]
    )
    candidate = or10["pooled_board_plane_candidate"]
    values = np.asarray(candidate["parameter_values"], dtype=np.float64).copy()
    values[4:7] *= scale
    board_frame = or1["fit"]["board_frame"]
    board_to_world = np.asarray(
        board_frame["rotation_board_to_world"], dtype=np.float64
    )
    board_origin_world = np.asarray(
        or13["camera"]["world_pose"]["board_origin_world_m"],
        dtype=np.float64,
    )
    board_to_camera, _ = cv2.Rodrigues(values[1:4])
    world_to_camera = board_to_camera @ board_to_world.T
    world_translation = values[4:7] - world_to_camera @ board_origin_world
    camera_center_world = -world_to_camera.T @ world_translation
    focal = float(values[0])
    camera = {
        "position_world": camera_center_world,
        "camera_cv_to_world": world_to_camera.T,
        "fovy_degrees": math.degrees(2.0 * math.atan(480.0 / (2.0 * focal))),
    }
    side = float(registration["measured_playing_side_m"])
    board_points = np.asarray(
        [[0.0, 0.0, 0.0], [side, 0.0, 0.0], [side, side, 0.0], [0.0, side, 0.0]],
        dtype=np.float64,
    )
    projected, _ = project_camera_family(
        board_points,
        values,
        principal_point_px=np.asarray(
            candidate["principal_point_px"], dtype=np.float64
        ),
        radial_term_count=0,
    )
    return camera, projected, values, {
        "scale": scale,
        "camera_center_world_m": camera_center_world.tolist(),
        "vertical_fov_degrees": camera["fovy_degrees"],
        "focal_px": focal,
        "board_origin_world_m": board_origin_world.tolist(),
    }


def _source_pose_by_sample(
    internal_trace: dict[str, Any],
    source_trace: dict[str, Any],
) -> dict[int, tuple[np.ndarray, np.ndarray]]:
    internal_rows = internal_trace["rows"]
    _require(internal_rows, "OR21 internal trace is empty")
    poses: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    first_quaternion = np.asarray(
        internal_rows[0]["selected_pawn_quaternion_wxyz"],
        dtype=np.float64,
    )
    source_rows = source_trace["rows"]
    poses[0] = (
        np.asarray(source_rows[0]["selected_pawn_position_m"], dtype=np.float64),
        first_quaternion,
    )
    for row in internal_rows:
        if row.get("phase") != "task":
            continue
        index = int(row["source_sample_index"])
        poses[index] = (
            np.asarray(row["selected_pawn_position_m"], dtype=np.float64),
            np.asarray(
                row["selected_pawn_quaternion_wxyz"], dtype=np.float64
            ),
        )
    _require(
        set(range(531)).issubset(poses),
        "OR21 trace does not cover every source row",
    )
    return poses


def _project_world_to_registered_pixel(
    world_position: np.ndarray,
    *,
    camera: dict[str, Any],
    camera_values: np.ndarray,
    display_homography: np.ndarray,
) -> np.ndarray:
    world_to_camera = np.asarray(
        camera["camera_cv_to_world"], dtype=np.float64
    ).T
    camera_center = np.asarray(camera["position_world"], dtype=np.float64)
    camera_point = world_to_camera @ (
        np.asarray(world_position, dtype=np.float64) - camera_center
    )
    _require(camera_point[2] > 0.0, "pawn projects behind the camera")
    focal = float(camera_values[0])
    pixel = np.asarray(
        [
            focal * camera_point[0] / camera_point[2] + 320.0,
            focal * camera_point[1] / camera_point[2] + 240.0,
        ],
        dtype=np.float32,
    )
    return cv2.perspectiveTransform(
        pixel.reshape(1, 1, 2), display_homography
    )[0, 0].astype(np.float64)


def _motion(
    previous: np.ndarray | None,
    current: np.ndarray,
    *,
    threshold: int,
    kernel: int,
) -> tuple[float, np.ndarray, list[float] | None]:
    gray = cv2.cvtColor(current, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (kernel, kernel), 0.0)
    if previous is None:
        return 0.0, np.zeros_like(gray), None
    delta = cv2.absdiff(previous, gray)
    mask = (delta >= threshold).astype(np.uint8)
    energy = float(np.mean(delta) / 255.0)
    coordinates = np.argwhere(mask > 0)
    centroid = (
        None
        if not len(coordinates)
        else [
            float(np.mean(coordinates[:, 1])),
            float(np.mean(coordinates[:, 0])),
        ]
    )
    return energy, mask, centroid


def _write_h264(raw: Path, destination: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(raw),
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(destination),
        ],
        check=True,
    )
    raw.unlink()


def _phase(sample: int) -> str:
    if sample < 228:
        return "approach"
    if sample < 248:
        return "contact"
    if sample < 260:
        return "lift onset"
    if sample < 400:
        return "carry"
    if sample < 408:
        return "release"
    return "settle"


def build_visible_divergence_video(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    _require(not receipt_path.exists(), "OR26 output already exists")
    contract = load_visible_divergence_video_contract(
        contract_path, root=root
    )
    or19 = _bound_json(
        contract["sources"]["or19_contract"],
        root=root,
        label="OR19 contract",
    )
    c6, candidate, measured_model, applied_model = _candidate_config(
        or19, root=root
    )
    timestamps = _tensor(
        _bound_path(
            c6["source"]["timestamps"], root=root, label="timestamps"
        ),
        c6["source"]["timestamps"],
    )
    _require(
        timestamps.shape == (531,)
        and measured_model.shape == applied_model.shape == (531, 6),
        "source tensor shape changed",
    )
    internal_trace = _bound_json(
        contract["sources"]["or21_internal_trace"],
        root=root,
        label="OR21 internal trace",
    )
    source_trace = _bound_json(
        contract["sources"]["or21_source_trace"],
        root=root,
        label="OR21 source trace",
    )
    poses = _source_pose_by_sample(internal_trace, source_trace)

    scene_path = _bound_path(
        contract["sources"]["or18_scene"], root=root, label="OR18 scene"
    )
    model = _candidate_spec(
        scene_path, pawn_height_m=0.034, canonical_piece_reset=True
    ).compile()
    data = mujoco.MjData(model)
    joint_ids = [
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        for name in candidate["bindings"]["joint_names"]
    ]
    _require(min(joint_ids) >= 0, "robot joint binding is incomplete")
    qpos_addresses = np.asarray(
        [int(model.jnt_qposadr[item]) for item in joint_ids],
        dtype=np.int64,
    )
    selected_name = c6["initialization"]["selected_piece"]
    selected_joint = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_JOINT, f"{selected_name}_free"
    )
    _require(selected_joint >= 0, "selected pawn binding is incomplete")
    selected_qpos = int(model.jnt_qposadr[selected_joint])

    camera, simulator_corners, camera_values, camera_report = _scaled_camera(
        contract, root=root
    )
    _configure_camera(model, data, camera)
    board_projection = _bound_json(
        contract["sources"]["physical_board_projection"],
        root=root,
        label="physical board projection",
    )
    physical_corners = np.asarray(
        board_projection["board_lattice"]["playing_corners_px"],
        dtype=np.float64,
    )
    _require(
        simulator_corners.shape == physical_corners.shape == (4, 2),
        "board corner shape changed",
    )
    display_homography = cv2.getPerspectiveTransform(
        simulator_corners.astype(np.float32),
        physical_corners.astype(np.float32),
    )
    warped_corners = cv2.perspectiveTransform(
        simulator_corners.reshape(1, 4, 2).astype(np.float32),
        display_homography,
    )[0]
    board_errors = np.linalg.norm(warped_corners - physical_corners, axis=1)
    endpoint_receipt = _bound_json(
        contract["sources"]["physical_endpoint_receipt"],
        root=root,
        label="physical endpoint receipt",
    )
    observed_initial_pixel = np.asarray(
        endpoint_receipt["observations"]["initial"]["pixel_base_center"],
        dtype=np.float64,
    )
    observed_terminal_pixel = np.asarray(
        endpoint_receipt["observations"]["terminal"]["pixel_base_center"],
        dtype=np.float64,
    )
    simulated_initial_pixel = _project_world_to_registered_pixel(
        poses[0][0],
        camera=camera,
        camera_values=camera_values,
        display_homography=display_homography,
    )
    simulated_terminal_pixel = _project_world_to_registered_pixel(
        poses[530][0],
        camera=camera,
        camera_values=camera_values,
        display_homography=display_homography,
    )

    recording = _bound_json(
        contract["sources"]["physical_recording_receipt"],
        root=root,
        label="physical recording",
    )
    video_path = _bound_path(
        contract["sources"]["physical_c922_video"],
        root=root,
        label="physical C922 video",
    )
    action_start = float(
        recording["overhead_video"]["action_start_video_offset_seconds"]
    )
    additional_lag = float(
        contract["timeline"]["additional_display_lag_seconds"]
    )

    output_directory.mkdir(parents=True, exist_ok=False)
    raw_physical = output_directory / "physical.raw.mp4"
    raw_simulator = output_directory / "simulator.raw.mp4"
    raw_comparison = output_directory / "comparison.raw.mp4"
    physical_path = output_directory / "physical.mp4"
    simulator_path = output_directory / "simulator.mp4"
    comparison_path = output_directory / "comparison.mp4"
    fps = float(contract["timeline"]["output_fps"])
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    physical_writer = cv2.VideoWriter(
        str(raw_physical), fourcc, fps, (640, 480)
    )
    simulator_writer = cv2.VideoWriter(
        str(raw_simulator), fourcc, fps, (640, 480)
    )
    comparison_writer = cv2.VideoWriter(
        str(raw_comparison), fourcc, fps, (1280, 540)
    )
    capture = cv2.VideoCapture(str(video_path))
    renderer = mujoco.Renderer(model, height=480, width=640)
    _require(
        capture.isOpened()
        and physical_writer.isOpened()
        and simulator_writer.isOpened()
        and comparison_writer.isOpened(),
        "video reader or writer did not open",
    )
    video_duration = float(capture.get(cv2.CAP_PROP_FRAME_COUNT)) / max(
        float(capture.get(cv2.CAP_PROP_FPS)), 1.0
    )

    analysis = contract["motion_analysis"]
    kernel = int(analysis["grayscale_gaussian_kernel"])
    physical_threshold = int(
        analysis["physical_frame_difference_threshold"]
    )
    simulator_threshold = int(
        analysis["simulator_frame_difference_threshold"]
    )
    previous_physical: np.ndarray | None = None
    previous_simulator: np.ndarray | None = None
    curve_rows: list[dict[str, Any]] = []
    physical_energies: list[float | None] = []
    simulator_energies: list[float | None] = []
    missing_frames = 0
    poster: np.ndarray | None = None
    try:
        for index in range(531):
            data.qpos[qpos_addresses] = applied_model[index]
            pawn_position, pawn_quaternion = poses[index]
            data.qpos[selected_qpos : selected_qpos + 3] = pawn_position
            data.qpos[selected_qpos + 3 : selected_qpos + 7] = pawn_quaternion
            mujoco.mj_forward(model, data)
            renderer.update_scene(data, camera="workcell")
            simulator = cv2.cvtColor(
                renderer.render().copy(), cv2.COLOR_RGB2BGR
            )
            simulator = cv2.warpPerspective(
                simulator,
                display_homography,
                (640, 480),
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=(205, 205, 205),
            )

            source_time = (
                action_start + float(timestamps[index]) + additional_lag
            )
            physical: np.ndarray | None = None
            if source_time <= video_duration + 1e-9:
                capture.set(cv2.CAP_PROP_POS_MSEC, source_time * 1000.0)
                ok, decoded = capture.read()
                if ok:
                    physical = decoded
            if physical is None:
                missing_frames += 1
                display_physical = np.full((480, 640, 3), 18, dtype=np.uint8)
                cv2.putText(
                    display_physical,
                    "SOURCE FRAME UNAVAILABLE",
                    (145, 235),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (90, 150, 255),
                    2,
                    cv2.LINE_AA,
                )
                physical_energy = None
                physical_mask = np.zeros((480, 640), dtype=np.uint8)
                physical_centroid = None
                previous_physical = None
            else:
                display_physical = physical
                physical_energy, physical_mask, physical_centroid = _motion(
                    previous_physical,
                    physical,
                    threshold=physical_threshold,
                    kernel=kernel,
                )
                previous_physical = cv2.GaussianBlur(
                    cv2.cvtColor(physical, cv2.COLOR_BGR2GRAY),
                    (kernel, kernel),
                    0.0,
                )
            simulator_energy, simulator_mask, simulator_centroid = _motion(
                previous_simulator,
                simulator,
                threshold=simulator_threshold,
                kernel=kernel,
            )
            previous_simulator = cv2.GaussianBlur(
                cv2.cvtColor(simulator, cv2.COLOR_BGR2GRAY),
                (kernel, kernel),
                0.0,
            )
            physical_energies.append(physical_energy)
            simulator_energies.append(simulator_energy)
            union = np.logical_or(physical_mask, simulator_mask)
            intersection = np.logical_and(physical_mask, simulator_mask)
            motion_iou = (
                None
                if physical is None or not np.any(union)
                else float(np.sum(intersection) / np.sum(union))
            )
            curve_rows.append(
                {
                    "sample_index": index,
                    "source_timestamp_seconds": float(timestamps[index]),
                    "physical_video_time_seconds": source_time,
                    "physical_frame_available": physical is not None,
                    "physical_motion_energy": physical_energy,
                    "simulator_motion_energy": simulator_energy,
                    "physical_motion_centroid_px": physical_centroid,
                    "simulator_motion_centroid_px": simulator_centroid,
                    "motion_mask_iou": motion_iou,
                    "simulator_pawn_position_m": pawn_position.tolist(),
                    "simulator_pawn_quaternion_wxyz": pawn_quaternion.tolist(),
                    "simulator_pawn_registered_pixel": (
                        _project_world_to_registered_pixel(
                            pawn_position,
                            camera=camera,
                            camera_values=camera_values,
                            display_homography=display_homography,
                        ).tolist()
                    ),
                }
            )

            physical_writer.write(display_physical)
            simulator_writer.write(simulator)
            composite = np.full((540, 1280, 3), 14, dtype=np.uint8)
            composite[60:540, :640] = display_physical
            composite[60:540, 640:1280] = simulator
            cv2.putText(
                composite,
                "PHYSICAL C922",
                (18, 28),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.62,
                (245, 245, 245),
                1,
                cv2.LINE_AA,
            )
            cv2.putText(
                composite,
                "EXACT OR21 PHYSICS TRACE - BOARD-REGISTERED",
                (658, 28),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.56,
                (120, 225, 255),
                1,
                cv2.LINE_AA,
            )
            cv2.putText(
                composite,
                (
                    f"sample {index:03d}/530   t={timestamps[index]:05.2f}s"
                    f"   {_phase(index)}   visual diagnostic only"
                ),
                (18, 51),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.48,
                (170, 180, 190),
                1,
                cv2.LINE_AA,
            )
            comparison_writer.write(composite)
            if index == 248:
                poster = composite.copy()
    finally:
        renderer.close()
        capture.release()
        physical_writer.release()
        simulator_writer.release()
        comparison_writer.release()

    _require(poster is not None, "comparison poster frame was not produced")
    _write_h264(raw_physical, physical_path)
    _write_h264(raw_simulator, simulator_path)
    _write_h264(raw_comparison, comparison_path)
    poster_path = output_directory / "poster_sample_248.png"
    _require(cv2.imwrite(str(poster_path), poster), "poster write failed")

    fit_start = int(analysis["precontact_affine_fit_sample_start"])
    fit_end = int(analysis["precontact_affine_fit_sample_end"])
    fit_indices = [
        index
        for index in range(fit_start, fit_end + 1)
        if physical_energies[index] is not None
    ]
    _require(len(fit_indices) >= 100, "insufficient precontact motion rows")
    design = np.column_stack(
        (
            np.asarray(
                [simulator_energies[index] for index in fit_indices],
                dtype=np.float64,
            ),
            np.ones(len(fit_indices), dtype=np.float64),
        )
    )
    target = np.asarray(
        [physical_energies[index] for index in fit_indices], dtype=np.float64
    )
    coefficient, intercept = np.linalg.lstsq(
        design, target, rcond=None
    )[0]
    residuals: list[float | None] = []
    for physical, simulator in zip(
        physical_energies, simulator_energies, strict=True
    ):
        residuals.append(
            None
            if physical is None
            else abs(float(physical) - (coefficient * simulator + intercept))
        )
    precontact_residuals = np.asarray(
        [float(residuals[index]) for index in fit_indices], dtype=np.float64
    )
    median = float(np.median(precontact_residuals))
    mad = float(np.median(np.abs(precontact_residuals - median)))
    residual_threshold = max(
        median + float(analysis["robust_residual_mad_multiplier"]) * mad,
        float(analysis["minimum_energy_residual_fraction"]),
    )
    first_motion_divergence = first_sustained_threshold_crossing(
        residuals,
        threshold=residual_threshold,
        start=int(analysis["postcontact_search_sample_start"]),
        minimum_rows=int(analysis["minimum_sustained_rows"]),
    )
    for row, residual in zip(curve_rows, residuals, strict=True):
        row["affine_motion_energy_residual"] = residual
        row["motion_energy_residual_threshold"] = residual_threshold

    curves = {
        "schema_version": CURVES_SCHEMA,
        "rows": curve_rows,
    }
    curves_path = output_directory / "motion_curves.json"
    atomic_write_json(curves_path, curves)
    physical_episode = _bound_json(
        contract["sources"]["physical_episode_receipt"],
        root=root,
        label="physical episode",
    )
    events = physical_episode["events"]
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "proof_class": contract["proof_class"],
        "status": "PASS_SYNCHRONIZED_VISIBLE_DIVERGENCE_VIDEO",
        "source_identity": {
            "row_count": 531,
            "timestamps_sha256": c6["source"]["timestamps"]["sha256"],
            "identified_applied_sha256": c6["source"]["identified_applied"][
                "sha256"
            ],
            "or21_internal_trace_sha256": contract["sources"][
                "or21_internal_trace"
            ]["sha256"],
            "physical_c922_sha256": contract["sources"][
                "physical_c922_video"
            ]["sha256"],
        },
        "camera_and_display_registration": {
            **camera_report,
            "or10_board_plane_reprojection_rms_px": float(
                _bound_json(
                    contract["sources"]["or10_camera_receipt"],
                    root=root,
                    label="OR10 camera",
                )["pooled_board_plane_candidate"]["reprojection_rms_px"]
            ),
            "simulator_playing_corners_before_warp_px": (
                simulator_corners.tolist()
            ),
            "physical_playing_corners_px": physical_corners.tolist(),
            "display_homography": display_homography.tolist(),
            "post_warp_board_corner_rms_px": float(
                np.sqrt(np.mean(board_errors**2))
            ),
            "display_homography_is_metric_camera_calibration": False,
            "global_mapping_approved": False,
        },
        "timeline": {
            "output_fps": int(fps),
            "frame_count": 531,
            "action_start_video_offset_seconds": action_start,
            "additional_display_lag_seconds": additional_lag,
            "missing_physical_frame_count": missing_frames,
            "camera_exposure_synchronized": False,
        },
        "visible_divergence": {
            "precontact_motion_energy_affine_coefficient": float(coefficient),
            "precontact_motion_energy_affine_intercept": float(intercept),
            "precontact_motion_energy_residual_median": median,
            "precontact_motion_energy_residual_mad": mad,
            "motion_energy_residual_threshold": residual_threshold,
            "first_sustained_postcontact_motion_divergence_sample": (
                first_motion_divergence
            ),
            "first_sustained_postcontact_motion_divergence_seconds": (
                None
                if first_motion_divergence is None
                else float(timestamps[first_motion_divergence])
            ),
            "simulator_first_unilateral_contact_sample": 231,
            "simulator_first_tilt_over_5_degrees_sample": 248,
            "simulator_first_bilateral_contact_sample": 255,
            "simulator_first_sustained_support_loss_sample": 260,
            "physical_contact_interval_samples": events[
                "candidate_contact_interval_samples"
            ]["sample_indices"],
            "physical_lift_interval_samples": events[
                "candidate_lift_interval_samples"
            ]["sample_indices"],
            "physical_carry_interval_samples": events[
                "definite_carried_motion_interval_samples"
            ]["sample_indices"],
            "physical_pawn_axis_orientation_available": False,
            "registered_planar_endpoints": {
                "initial": {
                    "physical_base_center_px": observed_initial_pixel.tolist(),
                    "simulator_pawn_root_px": simulated_initial_pixel.tolist(),
                    "pixel_error": float(
                        np.linalg.norm(
                            simulated_initial_pixel - observed_initial_pixel
                        )
                    ),
                },
                "terminal": {
                    "physical_base_center_px": observed_terminal_pixel.tolist(),
                    "simulator_pawn_root_px": simulated_terminal_pixel.tolist(),
                    "pixel_error": float(
                        np.linalg.norm(
                            simulated_terminal_pixel - observed_terminal_pixel
                        )
                    ),
                },
                "interpretation": "planar image endpoints are close; the remaining task failure is dominated by pawn orientation, height, support/load path, and collateral consequence rather than failure to approach D2"
            },
            "earliest_contact_consequence_divergence_boundary": {
                "sample_interval": [248, 260],
                "seconds": [
                    float(timestamps[248]),
                    float(timestamps[260]),
                ],
                "interpretation": "simulator tilt begins while the physical source enters its lift-to-carry interval; physical pawn axis is occluded, so exact orientation divergence inside this interval remains bounded rather than directly observed"
            },
            "frame_zero_static_appearance_identical": False,
            "frame_zero_difference_channels": [
                "renderer materials and lighting",
                "background and cables",
                "unmodeled camera distortion",
                "CAD and physical surface appearance",
                "nonselected piece pose and appearance"
            ],
        },
        "outputs": {
            "physical_video_path": physical_path.name,
            "physical_video_sha256": sha256_file(physical_path),
            "simulator_video_path": simulator_path.name,
            "simulator_video_sha256": sha256_file(simulator_path),
            "comparison_video_path": comparison_path.name,
            "comparison_video_sha256": sha256_file(comparison_path),
            "comparison_video_bytes": comparison_path.stat().st_size,
            "poster_path": poster_path.name,
            "poster_sha256": sha256_file(poster_path),
            "motion_curves_path": curves_path.name,
            "motion_curves_sha256": sha256_file(curves_path),
        },
        "trace_playback": {
            "physics_rerun": False,
            "actions_changed": False,
            "state_fit": False,
            "contact_or_object_parameters_changed": False,
            "selected_pawn_pose_source": "OR21 internal exact-physics trace",
            "robot_pose_source": "OR19 identified-applied action mapped through the unchanged OR19 adapter",
            "other_piece_dynamic_pose_available": False,
        },
        "global_mapping_approved": False,
        "physics_success_claim": False,
        "task_success_claim": False,
        "transfer_claim": False,
        "authority": contract["authority"],
    }
    receipt = {**unsigned, "artifact_sha256": canonical_digest(unsigned)}
    atomic_write_json(receipt_path, receipt)
    return receipt


def main() -> int:
    receipt = build_visible_divergence_video()
    print(receipt["status"])
    return 0


__all__ = [
    "build_visible_divergence_video",
    "first_sustained_threshold_crossing",
    "load_visible_divergence_video_contract",
    "main",
]
