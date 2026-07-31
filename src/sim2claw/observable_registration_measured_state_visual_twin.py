"""Render one raw-measured-state, natural-dynamics visual twin.

This lane is observation-conditioned: every retained follower joint row drives
the simulated robot.  It is useful for visual and geometry diagnosis, but it is
not an action-only REAL-to-SIM transfer.
"""

from __future__ import annotations

import copy
import math
from pathlib import Path
from typing import Any

import cv2
import mujoco
import numpy as np

from .current_workcell import current_square_center
from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
    sha256_file,
)
from .observable_registration_belief_recalculation import (
    REPO_ROOT,
    _bound_json,
    _bound_path,
)
from .observable_registration_unilateral_push_dynamic_replay import (
    load_unilateral_push_dynamic_replay_contract,
)
from .observable_registration_visible_divergence_video import (
    _candidate_config,
    _motion,
    _phase,
    _project_world_to_registered_pixel,
    _scaled_camera,
    _write_h264,
    first_sustained_threshold_crossing,
    load_visible_divergence_video_contract,
)
from .pawn_bg_demo_sim import _piece_bodies
from .post_hackathon_home_workspace_geometry_camera import _candidate_spec
from .real_to_sim_transfer import _configure_camera
from .realized_action_outcome_mission import _contact_counts, _outcome


SCHEMA = (
    "sim2claw.observable_registration_measured_state_visual_twin_contract.v1"
)
RECEIPT_SCHEMA = (
    "sim2claw.observable_registration_measured_state_visual_twin_receipt.v1"
)
TRACE_SCHEMA = (
    "sim2claw.observable_registration_measured_state_visual_twin_trace.v1"
)
CURVES_SCHEMA = (
    "sim2claw.observable_registration_measured_state_visual_twin_curves.v1"
)
CONTRACT_PATH = (
    REPO_ROOT
    / "configs/evaluations/"
    "observable_registration_measured_state_visual_twin_v1.json"
)
OUTPUT_DIRECTORY = (
    REPO_ROOT
    / "outputs/observable_registration_measured_state_visual_twin_v1"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def load_measured_state_visual_twin_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="measured-state visual twin")
    _require(contract.get("schema_version") == SCHEMA, "unsupported contract")
    for name, binding in contract["sources"].items():
        _bound_path(binding, root=root, label=name)
    trajectory = contract["trajectory"]
    _require(
        trajectory["row_count"] == 531
        and trajectory["robot_driver"]
        == "raw_follower_actual_position_degrees"
        and trajectory["raw_tensor_source"] == "c6.source.initial_measured"
        and trajectory["preserve_source_row_order"] is True
        and trajectory["preserve_source_timestamps"] is True
        and trajectory[
            "interpolate_only_between_adjacent_measured_rows_at_native_mujoco_timestep"
        ]
        is True
        and trajectory["identified_applied_drives_robot"] is False
        and trajectory["requested_or_gateway_sent_drives_robot"] is False
        and trajectory["measured_state_is_observation_conditioned"] is True,
        "measured trajectory boundary widened",
    )
    simulation = contract["simulation"]
    _require(
        simulation["one_run_only"] is True
        and simulation["reuse_or19_scene_mapping_reset_and_parameters"] is True
        and simulation["natural_contact_only"] is True,
        "simulation identity widened",
    )
    forbidden = (
        "object_pose_injection_allowed",
        "grasp_or_release_mode_allowed",
        "latch_or_attachment_allowed",
        "endpoint_injection_allowed",
        "contact_or_object_parameter_change_allowed",
        "camera_or_display_refit_allowed",
        "action_or_measured_state_edit_allowed",
    )
    _require(
        all(simulation[name] is False for name in forbidden),
        "visual-twin assistance enabled",
    )
    limits = contract["claim_limits"]
    _require(
        limits and not any(limits.values()),
        "measured-state claim boundary widened",
    )
    authority = contract["authority"]
    _require(
        authority["simulator_replay"] is True
        and not any(
            value
            for name, value in authority.items()
            if name != "simulator_replay"
        ),
        "measured-state authority widened",
    )
    return contract


def _range_union(
    *,
    model: mujoco.MjModel,
    joint_ids: list[int],
    joint_names: list[str],
    measured_model: np.ndarray,
    historical_ranges: list[list[float]],
    maximum_gripper_expansion_rad: float,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, joint_id in enumerate(joint_ids):
        if not model.jnt_limited[joint_id]:
            continue
        observed_minimum = float(np.min(measured_model[:, index]))
        observed_maximum = float(np.max(measured_model[:, index]))
        original = model.jnt_range[joint_id].copy()
        if index < 5:
            effective = np.asarray(historical_ranges[index], dtype=np.float64)
            _require(
                effective.shape == (2,)
                and observed_minimum >= float(effective[0])
                and observed_maximum <= float(effective[1]),
                "raw measured trajectory exceeds historical range envelope",
            )
        else:
            effective = original.copy()
            effective[0] = min(float(effective[0]), observed_minimum)
            effective[1] = max(float(effective[1]), observed_maximum)
            _require(
                max(
                    0.0,
                    float(original[0] - effective[0]),
                    float(effective[1] - original[1]),
                )
                <= maximum_gripper_expansion_rad,
                "raw measured gripper exceeds bounded range union",
            )
        model.jnt_range[joint_id] = effective
        rows.append(
            {
                "joint": joint_names[index],
                "lower_expansion_rad": max(
                    0.0, float(original[0] - effective[0])
                ),
                "upper_expansion_rad": max(
                    0.0, float(effective[1] - original[1])
                ),
            }
        )
    return rows


def _end_effector_positions(
    model: mujoco.MjModel,
    *,
    qpos_addresses: np.ndarray,
    site_id: int,
    trajectory: np.ndarray,
) -> np.ndarray:
    data = mujoco.MjData(model)
    positions = np.empty((len(trajectory), 3), dtype=np.float64)
    for index, pose in enumerate(trajectory):
        data.qpos[qpos_addresses] = pose
        mujoco.mj_forward(model, data)
        positions[index] = data.site_xpos[site_id]
    return positions


def _tilt_degrees(quaternion_wxyz: np.ndarray) -> float:
    matrix = np.empty(9, dtype=np.float64)
    mujoco.mju_quat2Mat(matrix, quaternion_wxyz)
    rotation = matrix.reshape(3, 3)
    return math.degrees(
        math.acos(float(np.clip(rotation[2, 2], -1.0, 1.0)))
    )


def build_measured_state_visual_twin(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    _require(not receipt_path.exists(), "OR34 one-run receipt already exists")
    contract = load_measured_state_visual_twin_contract(
        contract_path, root=root
    )
    or19_path = _bound_path(
        contract["sources"]["or19_contract"],
        root=root,
        label="OR19 contract",
    )
    or19, c6 = load_unilateral_push_dynamic_replay_contract(
        or19_path, root=root
    )
    or19_receipt = _bound_json(
        contract["sources"]["or19_receipt"],
        root=root,
        label="OR19 receipt",
    )
    _require(
        or19_receipt["actions_changed"] is False
        and or19_receipt["source_identity"]["row_count"] == 531,
        "OR19 predecessor identity changed",
    )
    or26_path = _bound_path(
        contract["sources"]["or26_contract"],
        root=root,
        label="OR26 contract",
    )
    or26 = load_visible_divergence_video_contract(or26_path, root=root)
    or26_receipt = _bound_json(
        contract["sources"]["or26_receipt"],
        root=root,
        label="OR26 receipt",
    )
    _require(
        or26_receipt["status"]
        == "PASS_SYNCHRONIZED_VISIBLE_DIVERGENCE_VIDEO",
        "OR26 visual predecessor changed",
    )

    c6_loaded, candidate, measured_model, identified_model = _candidate_config(
        or19, root=root
    )
    _require(c6_loaded == c6, "C6 contract identity changed")
    source = c6["source"]
    measured_physical = np.fromfile(
        _bound_path(
            source["initial_measured"], root=root, label="raw measured"
        ),
        dtype=np.dtype(source["initial_measured"]["dtype"]),
    ).reshape(source["initial_measured"]["shape"])
    identified_physical = np.fromfile(
        _bound_path(
            source["identified_applied"], root=root, label="identified applied"
        ),
        dtype=np.dtype(source["identified_applied"]["dtype"]),
    ).reshape(source["identified_applied"]["shape"])
    timestamps = np.fromfile(
        _bound_path(source["timestamps"], root=root, label="timestamps"),
        dtype=np.dtype(source["timestamps"]["dtype"]),
    ).reshape(source["timestamps"]["shape"])
    _require(
        measured_physical.shape
        == identified_physical.shape
        == measured_model.shape
        == identified_model.shape
        == (531, 6)
        and timestamps.shape == (531,)
        and bool(np.all(np.diff(timestamps) > 0.0)),
        "raw measured tensor alignment changed",
    )

    scene_path = _bound_path(
        or19["sources"]["or18_scene"], root=root, label="OR18 scene"
    )
    model = _candidate_spec(
        scene_path, pawn_height_m=0.034, canonical_piece_reset=True
    ).compile()
    joint_names = candidate["bindings"]["joint_names"]
    actuator_names = candidate["bindings"]["actuator_names"]
    joint_ids = [
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        for name in joint_names
    ]
    actuator_ids = np.asarray(
        [
            mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, name)
            for name in actuator_names
        ],
        dtype=np.int64,
    )
    _require(
        min(joint_ids + actuator_ids.tolist()) >= 0,
        "robot binding is incomplete",
    )
    qpos_addresses = np.asarray(
        [int(model.jnt_qposadr[value]) for value in joint_ids],
        dtype=np.int64,
    )
    dof_addresses = np.asarray(
        [int(model.jnt_dofadr[value]) for value in joint_ids],
        dtype=np.int64,
    )
    historical = _bound_json(
        or19["sources"]["historical_mapping_receipt"],
        root=root,
        label="historical mapping",
    )
    range_expansions = _range_union(
        model=model,
        joint_ids=joint_ids,
        joint_names=joint_names,
        measured_model=measured_model,
        historical_ranges=historical["mapping"]["candidate"][
            "joint_range_envelope_rad"
        ],
        maximum_gripper_expansion_rad=float(
            c6["replay"]["maximum_joint_range_expansion_rad"]
        ),
    )
    site_id = mujoco.mj_name2id(
        model,
        mujoco.mjtObj.mjOBJ_SITE,
        candidate["bindings"]["end_effector_site"],
    )
    _require(site_id >= 0, "end-effector site is missing")
    measured_ee = _end_effector_positions(
        model,
        qpos_addresses=qpos_addresses,
        site_id=site_id,
        trajectory=measured_model,
    )
    identified_ee = _end_effector_positions(
        model,
        qpos_addresses=qpos_addresses,
        site_id=site_id,
        trajectory=identified_model,
    )
    joint_residual = identified_physical - measured_physical
    ee_error_mm = (
        np.linalg.norm(identified_ee - measured_ee, axis=1) * 1000.0
    )

    selected_name = c6["initialization"]["selected_piece"]
    selected_body = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_BODY, selected_name
    )
    selected_joint = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_JOINT, f"{selected_name}_free"
    )
    _require(
        selected_body >= 0 and selected_joint >= 0,
        "selected pawn binding is incomplete",
    )
    selected_qpos = int(model.jnt_qposadr[selected_joint])
    selected_dof = int(model.jnt_dofadr[selected_joint])
    data = mujoco.MjData(model)
    data.qpos[qpos_addresses] = measured_model[0]
    data.ctrl[actuator_ids] = measured_model[0]
    mujoco.mj_forward(model, data)
    mujoco.mj_step(model, data, nstep=100)
    support_z = float(data.qpos[selected_qpos + 2])
    upright = np.asarray(
        data.qpos[selected_qpos + 3 : selected_qpos + 7],
        dtype=np.float64,
    ).copy()
    initial_xy = np.asarray(
        c6["initialization"]["physical_d1_world_position_m"][:2],
        dtype=np.float64,
    )
    data.qpos[selected_qpos : selected_qpos + 2] = initial_xy
    data.qpos[selected_qpos + 2] = support_z
    data.qpos[selected_qpos + 3 : selected_qpos + 7] = upright
    data.qvel[selected_dof : selected_dof + 6] = 0.0
    data.qpos[qpos_addresses] = measured_model[0]
    data.qvel[dof_addresses] = 0.0
    data.ctrl[actuator_ids] = measured_model[0]
    mujoco.mj_forward(model, data)
    initial_position = np.asarray(
        data.xpos[selected_body], dtype=np.float64
    ).copy()
    initial_height = float(initial_position[2])
    pieces = _piece_bodies(model)
    initial_piece_positions = {
        name: np.asarray(data.xpos[body_id], dtype=np.float64).copy()
        for name, body_id in pieces.items()
    }

    camera, simulator_corners, camera_values, camera_report = _scaled_camera(
        or26, root=root
    )
    _configure_camera(model, data, camera)
    board_projection = _bound_json(
        or26["sources"]["physical_board_projection"],
        root=root,
        label="physical board projection",
    )
    physical_corners = np.asarray(
        board_projection["board_lattice"]["playing_corners_px"],
        dtype=np.float64,
    )
    display_homography = cv2.getPerspectiveTransform(
        simulator_corners.astype(np.float32),
        physical_corners.astype(np.float32),
    )
    warped_corners = cv2.perspectiveTransform(
        simulator_corners.reshape(1, 4, 2).astype(np.float32),
        display_homography,
    )[0]
    board_errors = np.linalg.norm(
        warped_corners - physical_corners, axis=1
    )

    recording = _bound_json(
        or26["sources"]["physical_recording_receipt"],
        root=root,
        label="physical recording",
    )
    video_path = _bound_path(
        or26["sources"]["physical_c922_video"],
        root=root,
        label="physical C922 video",
    )
    action_start = float(
        recording["overhead_video"]["action_start_video_offset_seconds"]
    )
    additional_lag = float(
        or26["timeline"]["additional_display_lag_seconds"]
    )
    analysis = or26["motion_analysis"]

    output_directory.mkdir(parents=True, exist_ok=False)
    raw_physical = output_directory / "physical.raw.mp4"
    raw_simulator = output_directory / "simulator.raw.mp4"
    raw_comparison = output_directory / "comparison.raw.mp4"
    physical_path = output_directory / "physical.mp4"
    simulator_path = output_directory / "simulator.mp4"
    comparison_path = output_directory / "comparison.mp4"
    fps = float(contract["visualization"]["output_fps"])
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

    kernel = int(analysis["grayscale_gaussian_kernel"])
    physical_threshold = int(
        analysis["physical_frame_difference_threshold"]
    )
    simulator_threshold = int(
        analysis["simulator_frame_difference_threshold"]
    )
    previous_physical: np.ndarray | None = None
    previous_simulator: np.ndarray | None = None
    physical_energies: list[float | None] = []
    simulator_energies: list[float] = []
    curve_rows: list[dict[str, Any]] = []
    trace_rows: list[dict[str, Any]] = []
    missing_frames = 0
    poster: np.ndarray | None = None
    selected_contact_steps = 0
    first_selected_contact_sample: int | None = None
    maximum_quantization_error = 0.0
    timestep = float(model.opt.timestep)

    def observe(sample_index: int) -> None:
        nonlocal selected_contact_steps, first_selected_contact_sample
        count, _ = _contact_counts(
            model, data, selected_body=selected_body
        )
        selected_contact_steps += count
        if count and first_selected_contact_sample is None:
            first_selected_contact_sample = sample_index

    try:
        for index in range(531):
            if index:
                dt = float(timestamps[index] - timestamps[index - 1])
                nstep = max(1, round(dt / timestep))
                maximum_quantization_error = max(
                    maximum_quantization_error, abs(nstep * timestep - dt)
                )
                previous = measured_model[index - 1]
                current = measured_model[index]
                velocity = (current - previous) / dt
                for step in range(nstep):
                    alpha = (step + 1) / nstep
                    pose = previous + alpha * (current - previous)
                    data.qpos[qpos_addresses] = pose
                    data.qvel[dof_addresses] = velocity
                    data.ctrl[actuator_ids] = pose
                    mujoco.mj_forward(model, data)
                    mujoco.mj_step(model, data)
                    observe(index)
            pawn_position = np.asarray(
                data.xpos[selected_body], dtype=np.float64
            ).copy()
            pawn_quaternion = np.asarray(
                data.xquat[selected_body], dtype=np.float64
            ).copy()
            trace_rows.append(
                {
                    "sample_index": index,
                    "source_timestamp_seconds": float(timestamps[index]),
                    "raw_measured_physical": (
                        measured_physical[index].astype(float).tolist()
                    ),
                    "identified_applied_physical": (
                        identified_physical[index].astype(float).tolist()
                    ),
                    "selected_pawn_position_m": pawn_position.tolist(),
                    "selected_pawn_quaternion_wxyz": pawn_quaternion.tolist(),
                    "selected_pawn_tilt_degrees": _tilt_degrees(
                        pawn_quaternion
                    ),
                }
            )

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
                display_physical = np.full(
                    (480, 640, 3), 18, dtype=np.uint8
                )
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
                previous_physical = None
            else:
                display_physical = physical
                physical_energy, _, _ = _motion(
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
            simulator_energy, _, _ = _motion(
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
            curve_rows.append(
                {
                    "sample_index": index,
                    "source_timestamp_seconds": float(timestamps[index]),
                    "physical_video_time_seconds": source_time,
                    "physical_frame_available": physical is not None,
                    "physical_motion_energy": physical_energy,
                    "simulator_motion_energy": simulator_energy,
                    "simulator_pawn_position_m": pawn_position.tolist(),
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
                "RAW FOLLOWER STATE + NATURAL MUJOCO OBJECT",
                (658, 28),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.53,
                (120, 225, 255),
                1,
                cv2.LINE_AA,
            )
            cv2.putText(
                composite,
                (
                    f"sample {index:03d}/530   t={timestamps[index]:05.2f}s"
                    f"   {_phase(index)}   observation-conditioned diagnostic"
                ),
                (18, 51),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.46,
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

    _require(poster is not None, "comparison poster was not produced")
    _write_h264(raw_physical, physical_path)
    _write_h264(raw_simulator, simulator_path)
    _write_h264(raw_comparison, comparison_path)
    poster_path = output_directory / "poster_sample_248.png"
    _require(cv2.imwrite(str(poster_path), poster), "poster write failed")

    data.qpos[qpos_addresses] = measured_model[-1]
    data.qvel[dof_addresses] = 0.0
    data.ctrl[actuator_ids] = measured_model[-1]
    mujoco.mj_forward(model, data)
    for _ in range(
        round(
            float(contract["simulation"]["post_action_settle_seconds"])
            / timestep
        )
    ):
        mujoco.mj_step(model, data)
        observe(530)

    positions = np.asarray(
        [row["selected_pawn_position_m"] for row in trace_rows],
        dtype=np.float64,
    )
    planar_displacement = np.linalg.norm(
        positions[:, :2] - initial_position[:2], axis=1
    )
    moving = np.flatnonzero(planar_displacement > 0.001)
    target = np.asarray(
        current_square_center(
            c6["initialization"]["destination_square"],
            config_path=scene_path,
        ),
        dtype=np.float64,
    )
    direction = target[:2] - initial_position[:2]
    direction /= np.linalg.norm(direction)
    final_position = np.asarray(
        data.xpos[selected_body], dtype=np.float64
    ).copy()
    progress = float((final_position[:2] - initial_position[:2]) @ direction)
    other_displacement = max(
        (
            float(
                np.linalg.norm(
                    np.asarray(data.xpos[body_id], dtype=np.float64)
                    - initial_piece_positions[name]
                )
            )
            for name, body_id in pieces.items()
            if name != selected_name
        ),
        default=0.0,
    )
    outcome = _outcome(
        data=data,
        model=model,
        selected_body=selected_body,
        selected_dof=selected_dof,
        initial_height=initial_height,
        target=target,
        other_displacement=other_displacement,
        selected_contact_steps=selected_contact_steps,
        evaluator=c6["evaluator"],
    )

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
    target_energy = np.asarray(
        [physical_energies[index] for index in fit_indices],
        dtype=np.float64,
    )
    coefficient, intercept = np.linalg.lstsq(
        design, target_energy, rcond=None
    )[0]
    residuals: list[float | None] = [
        (
            None
            if physical is None
            else abs(
                float(physical)
                - (float(coefficient) * simulator + float(intercept))
            )
        )
        for physical, simulator in zip(
            physical_energies, simulator_energies, strict=True
        )
    ]
    precontact_residuals = np.asarray(
        [float(residuals[index]) for index in fit_indices],
        dtype=np.float64,
    )
    median = float(np.median(precontact_residuals))
    mad = float(np.median(np.abs(precontact_residuals - median)))
    residual_threshold = max(
        median + float(analysis["robust_residual_mad_multiplier"]) * mad,
        float(analysis["minimum_energy_residual_fraction"]),
    )
    first_visual_divergence = first_sustained_threshold_crossing(
        residuals,
        threshold=residual_threshold,
        start=int(analysis["postcontact_search_sample_start"]),
        minimum_rows=int(analysis["minimum_sustained_rows"]),
    )
    for row, residual in zip(curve_rows, residuals, strict=True):
        row["affine_motion_energy_residual"] = residual
        row["motion_energy_residual_threshold"] = residual_threshold

    endpoint = _bound_json(
        contract["sources"]["physical_endpoint_receipt"],
        root=root,
        label="physical endpoint",
    )
    observed_initial = np.asarray(
        endpoint["observations"]["initial"]["pixel_base_center"],
        dtype=np.float64,
    )
    observed_terminal = np.asarray(
        endpoint["observations"]["terminal"]["pixel_base_center"],
        dtype=np.float64,
    )
    simulated_initial = _project_world_to_registered_pixel(
        positions[0],
        camera=camera,
        camera_values=camera_values,
        display_homography=display_homography,
    )
    simulated_terminal = _project_world_to_registered_pixel(
        final_position,
        camera=camera,
        camera_values=camera_values,
        display_homography=display_homography,
    )

    trace_path = output_directory / "trace.json"
    curves_path = output_directory / "motion_curves.json"
    atomic_write_json(
        trace_path,
        {"schema_version": TRACE_SCHEMA, "rows": trace_rows},
    )
    atomic_write_json(
        curves_path,
        {"schema_version": CURVES_SCHEMA, "rows": curve_rows},
    )
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "proof_class": contract["proof_class"],
        "status": "PASS_MEASURED_STATE_VISUAL_TWIN_DIAGNOSTIC",
        "source_identity": {
            "recording_id": source["recording_id"],
            "raw_measured_sha256": source["initial_measured"]["sha256"],
            "identified_applied_sha256": source["identified_applied"][
                "sha256"
            ],
            "timestamps_sha256": source["timestamps"]["sha256"],
            "row_count": 531,
            "row_order_preserved": True,
        },
        "trajectory_comparison": {
            "joint_order": contract["comparison"]["joint_order"],
            "identified_minus_measured_overall_joint_rms_degrees": float(
                np.sqrt(np.mean(np.square(joint_residual)))
            ),
            "identified_minus_measured_per_joint_rms_degrees": (
                np.sqrt(np.mean(np.square(joint_residual), axis=0)).tolist()
            ),
            "identified_minus_measured_per_joint_bias_degrees": (
                np.mean(joint_residual, axis=0).tolist()
            ),
            "identified_minus_measured_end_effector_rms_mm": float(
                np.sqrt(np.mean(np.square(ee_error_mm)))
            ),
            "identified_minus_measured_end_effector_p95_mm": float(
                np.percentile(ee_error_mm, 95)
            ),
        },
        "natural_dynamics": {
            "first_selected_jaw_contact_sample": (
                first_selected_contact_sample
            ),
            "selected_jaw_contact_steps": selected_contact_steps,
            "first_motion_over_1mm_sample": (
                int(moving[0]) if moving.size else None
            ),
            "maximum_planar_displacement_m": float(
                np.max(planar_displacement)
            ),
            "signed_progress_toward_d2_m": progress,
            "maximum_other_piece_displacement_m": other_displacement,
            "maximum_timestamp_quantization_error_seconds": (
                maximum_quantization_error
            ),
            "object_pose_injected": False,
            "latch_or_attachment_used": False,
            "outcome": outcome,
        },
        "identified_plant_predecessor": {
            "first_selected_jaw_contact_sample": or19_receipt["dynamics"][
                "first_selected_jaw_contact_sample"
            ],
            "first_motion_over_1mm_sample": or19_receipt["dynamics"][
                "first_motion_over_1mm_sample"
            ],
            "signed_progress_toward_d2_m": or19_receipt["dynamics"][
                "signed_progress_toward_d2_m"
            ],
            "outcome": or19_receipt["outcome"],
        },
        "camera_and_display_registration": {
            **camera_report,
            "display_homography": display_homography.tolist(),
            "post_warp_board_corner_rms_px": float(
                np.sqrt(np.mean(np.square(board_errors)))
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
        "visible_comparison": {
            "first_sustained_postcontact_motion_divergence_sample": (
                first_visual_divergence
            ),
            "first_sustained_postcontact_motion_divergence_seconds": (
                None
                if first_visual_divergence is None
                else float(timestamps[first_visual_divergence])
            ),
            "motion_energy_residual_threshold": residual_threshold,
            "registered_initial_pawn_error_px": float(
                np.linalg.norm(simulated_initial - observed_initial)
            ),
            "registered_terminal_pawn_error_px": float(
                np.linalg.norm(simulated_terminal - observed_terminal)
            ),
        },
        "outputs": {
            "physical_video_path": physical_path.name,
            "physical_video_sha256": sha256_file(physical_path),
            "simulator_video_path": simulator_path.name,
            "simulator_video_sha256": sha256_file(simulator_path),
            "comparison_video_path": comparison_path.name,
            "comparison_video_sha256": sha256_file(comparison_path),
            "poster_path": poster_path.name,
            "poster_sha256": sha256_file(poster_path),
            "trace_path": trace_path.name,
            "trace_sha256": sha256_file(trace_path),
            "motion_curves_path": curves_path.name,
            "motion_curves_sha256": sha256_file(curves_path),
        },
        "observation_conditioned": True,
        "action_only_transfer": False,
        "global_mapping_approved": False,
        "simulator_promoted": False,
        "task_success_claim": False,
        "transfer_claim": False,
        "authority": contract["authority"],
    }
    unsigned["artifact_sha256"] = canonical_digest(unsigned)
    atomic_write_json(receipt_path, unsigned)
    return unsigned


def main() -> int:
    build_measured_state_visual_twin()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
