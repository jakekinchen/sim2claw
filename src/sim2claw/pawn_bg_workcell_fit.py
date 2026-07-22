"""Bounded B-G workcell calibration from recorded teleoperation evidence.

This module re-diagnoses the frozen source-fit terminal negative. The frozen
run fitted five free joint signs plus five zero offsets against labeled square
centers and was rejected. The residual structure of the same 22 training-side
events shows a different, physically consistent decomposition:

1. Every identity-mapped pinch point lands within ~2 cm of the square obtained
   by rotating the labeled square 180 degrees about the board center. The
   frozen scene's board labeling is rotated 180 degrees relative to the
   physical board (owner video review: the robot-side sparse row is
   B1/C2/D1/E2/F1/G2, while the frozen scene places ranks 7/8 there).
2. After that relabel, one small planar board correction plus small per-joint
   zero offsets (the LeRobot calibration middle pose is user-eyeballed, so a
   constant few-degree offset per joint is expected) explain the remainder.

The fit is therefore staged and bounded:

- stage A: categorical 180-degree board relabel (no free parameters);
- stage B: planar board center/yaw refit (3 parameters, xy residuals only);
- stage C: bounded per-joint zero offsets for shoulder pan/lift, elbow, and
  wrist flex (4 parameters, |delta| <= 15 degrees, ridge prior), jointly with
  the stage-B board parameters (full 3D residuals).

Joint signs are frozen at +1: the repeatable folded rest pose sits just
outside the vendored model's conservative ranges on exactly the joints that
clip, which is only consistent with the identity convention. Simulator
joint/ctrl ranges are widened in memory to the measured envelope (LeRobot
calibration sweep united with training-episode excursions plus margin), so the
no-clipping requirement no longer excludes the physically correct mapping.

Train episodes are the frozen sysid split's train partition intersected with
the owner-reviewed product scope. Held-out episodes are opened exactly once,
by `run_held_out_validation`, after the candidate is frozen. Consequence
scores reuse the frozen B-G reward thresholds diagnostically; nothing here
claims physical calibration, policy success, or promotion.
"""

from __future__ import annotations

import json
import math
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import mujoco
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

from .grasp import _pinch_offset, _pinch_point
from .mass_profile import DEFAULT_SO101_MASS_PROFILE
from .paths import REPO_ROOT
from .pawn_bg_demo_sim import (
    BASELINE_PIECE_BY_FILE,
    JointAdapter,
    ROBOT_JOINTS,
    _load_source,
    _piece_bodies,
    _trace_row,
    physical_values_to_sim_with_adapter,
)
from .pawn_bg_reward import load_reward_contract, score_episode, sha256_file
from .pawn_bg_source_fit import (
    _average_body_joints,
    extract_phase_indices,
    load_source_fit_contract,
)
from .scene import (
    board_square_center,
    build_scene_spec,
    initialize_robot_poses,
    load_capture_config,
    scene_geometry,
)

CONTRACT_PATH = REPO_ROOT / "configs" / "optimization" / "pawn_bg_workcell_fit_v1.json"
CALIBRATION_PATH = REPO_ROOT / "calibration" / "so101" / "follower_arm.json"
SPLIT_PATH = REPO_ROOT / "configs" / "sysid" / "physical_pawn_sysid_split_v1.json"
CATALOG_PATH = REPO_ROOT / "configs" / "data" / "physical_pawn_move_catalog_20260719.json"

BODY_JOINT_NAMES = ROBOT_JOINTS[:5]
FITTED_OFFSET_JOINTS = ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex")


class WorkcellFitError(RuntimeError):
    pass


def _workcell_square_center(
    square: str,
    *,
    board_center_in_table_frame_xy_m: tuple[float, float],
    board_yaw_relative_to_table_degrees: float,
    board_side_m: float | None = None,
) -> tuple[float, float, float]:
    """Resolve a candidate square without mutating the frozen scene API."""

    if board_side_m is None:
        return board_square_center(
            square,
            board_center_in_table_frame_xy_m=board_center_in_table_frame_xy_m,
            board_yaw_relative_to_table_degrees=board_yaw_relative_to_table_degrees,
        )
    if len(square) != 2 or square[0] not in "abcdefgh" or square[1] not in "12345678":
        raise ValueError(f"invalid chess square: {square}")
    if not math.isfinite(board_side_m) or board_side_m <= 0.0:
        raise ValueError("board_side_m must be finite and positive")
    config = load_capture_config()
    board = config["simulation_estimates"]["board"]
    board["center_in_table_frame_xy_m"] = list(board_center_in_table_frame_xy_m)
    board["yaw_relative_to_table_degrees"] = float(board_yaw_relative_to_table_degrees)
    board["side_m"] = float(board_side_m)
    geometry = scene_geometry(config)
    file_index = ord(square[0]) - ord("a")
    rank_index = int(square[1]) - 1
    local_x = (file_index - 3.5) * geometry.square_size
    local_y = (rank_index - 3.5) * geometry.square_size
    angle = math.radians(geometry.board_yaw_degrees)
    dx = math.cos(angle) * local_x - math.sin(angle) * local_y
    dy = math.sin(angle) * local_x + math.cos(angle) * local_y
    return (
        geometry.board_center[0] + dx,
        geometry.board_center[1] + dy,
        geometry.table_top + geometry.board_thickness + 0.001,
    )


def load_workcell_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    contract = json.loads(path.read_bytes())
    if contract.get("schema_version") != "sim2claw.pawn_bg_workcell_fit.v1":
        raise WorkcellFitError("unexpected workcell fit contract schema")
    return contract


@dataclass(frozen=True)
class WorkcellEvent:
    recording_id: str
    skill_id: str
    phase: str
    sample_index: int
    physical_body_joint_degrees: tuple[float, float, float, float, float]
    square: str
    gripper_value_at_event: float


@dataclass(frozen=True)
class WorkcellCandidate:
    """One frozen bounded calibration candidate."""

    board_yaw_relative_to_table_degrees: float
    board_center_in_table_frame_xy_m: tuple[float, float]
    joint_zero_offsets_rad: tuple[float, float, float, float, float]
    joint_range_envelope_rad: tuple[tuple[float, float], ...]
    base_z_offset_m: float = 0.0
    base_roll_offset_degrees: float = 0.0
    base_pitch_offset_degrees: float = 0.0
    board_side_m: float | None = None

    def as_dict(self) -> dict[str, Any]:
        result = {
            "board_yaw_relative_to_table_degrees": self.board_yaw_relative_to_table_degrees,
            "board_center_in_table_frame_xy_m": list(self.board_center_in_table_frame_xy_m),
            "joint_zero_offsets_rad": list(self.joint_zero_offsets_rad),
            "joint_zero_offsets_degrees": [
                math.degrees(value) for value in self.joint_zero_offsets_rad
            ],
            "joint_range_envelope_rad": [list(pair) for pair in self.joint_range_envelope_rad],
            "base_z_offset_m": self.base_z_offset_m,
            "base_roll_offset_degrees": self.base_roll_offset_degrees,
            "base_pitch_offset_degrees": self.base_pitch_offset_degrees,
            "body_joint_signs": [1, 1, 1, 1, 1],
        }
        if self.board_side_m is not None:
            result["board_side_m"] = self.board_side_m
        return result

    def adapter(self) -> JointAdapter:
        return JointAdapter(
            adapter_id="so101_workcell_fit_bounded_zero_offsets_v1",
            body_joint_signs=(1, 1, 1, 1, 1),
            body_joint_zero_offsets_rad=self.joint_zero_offsets_rad,
            evidence_class="bounded_zero_offset_candidate_not_physically_validated",
        )


def _split_membership(split_path: Path = SPLIT_PATH) -> dict[str, str]:
    split = json.loads(split_path.read_bytes())
    return {episode["episode_id"]: episode["split"] for episode in split["episodes"]}


def _product_episodes(catalog: dict[str, Any]) -> list[tuple[dict[str, Any], str, str]]:
    import re

    pattern = re.compile(r"^([b-g][12])-to-([b-g][12])(?:-redo)?$")
    selected = []
    for episode in catalog.get("episodes", []):
        match = pattern.fullmatch(str(episode.get("folder_label", "")))
        if match is None:
            continue
        source, destination = match.group(1), match.group(2)
        if source[0] != destination[0] or source[1] == destination[1]:
            continue
        selected.append((episode, source, destination))
    if len(selected) != 13:
        raise WorkcellFitError(f"product scope must contain 13 recordings, found {len(selected)}")
    return selected


def _extract_events(
    episode: dict[str, Any], source: str, destination: str,
    samples: list[dict[str, Any]], source_fit_contract: dict[str, Any],
) -> list[WorkcellEvent]:
    _, source_index, destination_index = extract_phase_indices(samples, source_fit_contract)
    signal = source_fit_contract["event_extraction"]["joint_signal"]
    gripper_index = source_fit_contract["event_extraction"]["gripper_joint_index"]
    events = []
    for phase, index, square in (
        ("source_near_close", source_index, source),
        ("destination_reopen", destination_index, destination),
    ):
        joints, _, _ = _average_body_joints(samples, index, source_fit_contract)
        events.append(WorkcellEvent(
            recording_id=episode["recording_id"],
            skill_id=f"pawn_{source}_to_{destination}",
            phase=phase,
            sample_index=index,
            physical_body_joint_degrees=joints,
            square=square,
            gripper_value_at_event=float(samples[index][signal][gripper_index]),
        ))
    return events


def measured_range_envelope(
    train_samples: list[list[dict[str, Any]]],
    *,
    calibration_path: Path = CALIBRATION_PATH,
    margin_degrees: float = 2.0,
) -> tuple[tuple[float, float], ...]:
    """Per-body-joint radian envelope: calibration sweep u train excursions."""

    calibration = json.loads(calibration_path.read_bytes())
    lows = np.empty(5)
    highs = np.empty(5)
    for index, joint in enumerate(BODY_JOINT_NAMES):
        entry = calibration[joint]
        lows[index] = (entry["range_min"] - 2048) * 360.0 / 4096.0
        highs[index] = (entry["range_max"] - 2048) * 360.0 / 4096.0
    for samples in train_samples:
        for row in samples:
            for key in ("follower_command_degrees", "follower_actual_position_degrees"):
                values = np.asarray(row[key][:5], dtype=np.float64)
                lows = np.minimum(lows, values)
                highs = np.maximum(highs, values)
    lows -= margin_degrees
    highs += margin_degrees
    return tuple(
        (math.radians(float(low)), math.radians(float(high)))
        for low, high in zip(lows, highs)
    )


def build_workcell_model(
    candidate: WorkcellCandidate,
    *,
    piece_layout: str = "sparse_two_sided_pawns",
    contact_variant: Any | None = None,
) -> dict[str, Any]:
    scene_kwargs = {
        "piece_layout": piece_layout,
        "board_center_in_table_frame_xy_m": candidate.board_center_in_table_frame_xy_m,
        "board_yaw_relative_to_table_degrees": candidate.board_yaw_relative_to_table_degrees,
        "mass_profile_path": DEFAULT_SO101_MASS_PROFILE,
    }
    if candidate.board_side_m is None:
        spec = build_scene_spec(**scene_kwargs)
    else:
        config = load_capture_config()
        config["simulation_estimates"]["board"]["side_m"] = candidate.board_side_m
        with tempfile.TemporaryDirectory(prefix="sim2claw-board-side-") as directory:
            config_path = Path(directory) / "capture.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            spec = build_scene_spec(config_path=config_path, **scene_kwargs)
    if contact_variant is not None:
        from .contact_prior import apply_contact_variant

        apply_contact_variant(spec, contact_variant)
    model = spec.compile()
    if (
        candidate.base_z_offset_m
        or candidate.base_roll_offset_degrees
        or candidate.base_pitch_offset_degrees
    ):
        base_body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "left_base")
        if base_body < 0:
            raise WorkcellFitError("scene is missing the left arm base body")
        model.body_pos[base_body, 2] += candidate.base_z_offset_m
        nominal_xyzw = np.asarray(
            [
                model.body_quat[base_body, 1],
                model.body_quat[base_body, 2],
                model.body_quat[base_body, 3],
                model.body_quat[base_body, 0],
            ],
            dtype=np.float64,
        )
        nominal_rotation = Rotation.from_quat(nominal_xyzw)
        local_adjustment = Rotation.from_euler(
            "xy",
            [
                candidate.base_roll_offset_degrees,
                candidate.base_pitch_offset_degrees,
            ],
            degrees=True,
        )
        adjusted_xyzw = (nominal_rotation * local_adjustment).as_quat()
        model.body_quat[base_body] = np.asarray(
            [
                adjusted_xyzw[3],
                adjusted_xyzw[0],
                adjusted_xyzw[1],
                adjusted_xyzw[2],
            ],
            dtype=np.float64,
        )
    joint_ids = [
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, f"left_{joint}")
        for joint in ROBOT_JOINTS
    ]
    actuator_ids = [
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, f"left_{joint}")
        for joint in ROBOT_JOINTS
    ]
    if min(joint_ids + actuator_ids) < 0:
        raise WorkcellFitError("scene is missing a required left-arm binding")
    for index, (low, high) in enumerate(candidate.joint_range_envelope_rad):
        joint_id = joint_ids[index]
        actuator_id = actuator_ids[index]
        model.jnt_range[joint_id, 0] = min(model.jnt_range[joint_id, 0], low)
        model.jnt_range[joint_id, 1] = max(model.jnt_range[joint_id, 1], high)
        model.actuator_ctrlrange[actuator_id, 0] = min(
            model.actuator_ctrlrange[actuator_id, 0], low
        )
        model.actuator_ctrlrange[actuator_id, 1] = max(
            model.actuator_ctrlrange[actuator_id, 1], high
        )
    data = mujoco.MjData(model)
    initialize_robot_poses(model, data)
    return {
        "model": model,
        "data": data,
        "joint_ids": joint_ids,
        "actuator_ids": actuator_ids,
        "qpos_addresses": [int(model.jnt_qposadr[joint_id]) for joint_id in joint_ids],
        "actuator_bounds": np.asarray(
            model.actuator_ctrlrange[actuator_ids], dtype=np.float64
        ),
        "pinch_offset_local": _pinch_offset(model, data, "left"),
    }


def _fk_pinch_points(
    binding: dict[str, Any], events: list[WorkcellEvent], offsets_rad: np.ndarray
) -> np.ndarray:
    model, data = binding["model"], binding["data"]
    qpos_addresses = binding["qpos_addresses"]
    points = []
    for event in events:
        converted = np.deg2rad(np.asarray(event.physical_body_joint_degrees)) + offsets_rad
        data.qpos[qpos_addresses[:5]] = converted
        mujoco.mj_forward(model, data)
        points.append(
            _pinch_point(model, data, "left", binding["pinch_offset_local"]).copy()
        )
    return np.asarray(points)


def _event_targets(
    events: list[WorkcellEvent],
    board_center: tuple[float, float],
    board_yaw_relative: float,
    neck_height_m: float,
    board_side_m: float | None = None,
) -> np.ndarray:
    targets = []
    for event in events:
        target = np.asarray(_workcell_square_center(
            event.square,
            board_center_in_table_frame_xy_m=board_center,
            board_yaw_relative_to_table_degrees=board_yaw_relative,
            board_side_m=board_side_m,
        ))
        target[2] += neck_height_m
        targets.append(target)
    return np.asarray(targets)


def fit_candidate(
    events: list[WorkcellEvent],
    binding: dict[str, Any],
    contract: dict[str, Any],
    envelope: tuple[tuple[float, float], ...],
) -> dict[str, Any]:
    """Stage A relabel, stage B planar board fit, stage C bounded joint offsets."""

    fit = contract["fit"]
    neck = float(fit["estimated_pawn_neck_height_m"])
    base_center = tuple(float(v) for v in fit["frozen_board_center_in_table_frame_xy_m"])
    frozen_yaw = float(fit["frozen_board_yaw_relative_to_table_degrees"])
    relabeled_yaw = frozen_yaw + 180.0
    offset_bound = math.radians(float(fit["joint_zero_offset_bound_degrees"]))
    prior_sigma = math.radians(float(fit["joint_zero_offset_prior_sigma_degrees"]))

    zero_offsets = np.zeros(5)
    pinch_identity = _fk_pinch_points(binding, events, zero_offsets)

    def stage_metrics(points: np.ndarray, center, yaw) -> dict[str, Any]:
        targets = _event_targets(events, center, yaw, neck)
        residual = points - targets
        distance = np.linalg.norm(residual, axis=1)
        return {
            "event_rms_distance_m": float(np.sqrt(np.mean(distance**2))),
            "event_mean_distance_m": float(np.mean(distance)),
            "event_maximum_distance_m": float(np.max(distance)),
            "xy_rms_m": float(np.sqrt(np.mean(np.sum(residual[:, :2] ** 2, axis=1)))),
            "z_mean_m": float(np.mean(residual[:, 2])),
            "z_rms_m": float(np.sqrt(np.mean(residual[:, 2] ** 2))),
        }

    stage_a = stage_metrics(pinch_identity, base_center, relabeled_yaw)
    frozen_baseline = stage_metrics(pinch_identity, base_center, frozen_yaw)

    def stage_b_residual(params: np.ndarray) -> np.ndarray:
        center = (base_center[0] + params[0], base_center[1] + params[1])
        targets = _event_targets(events, center, relabeled_yaw + params[2], neck)
        return (pinch_identity[:, :2] - targets[:, :2]).ravel()

    stage_b_fit = least_squares(
        stage_b_residual,
        x0=np.zeros(3),
        bounds=(np.asarray([-0.08, -0.08, -15.0]), np.asarray([0.08, 0.08, 15.0])),
        method="trf",
        diff_step=1e-3,
    )
    b_center = (base_center[0] + stage_b_fit.x[0], base_center[1] + stage_b_fit.x[1])
    b_yaw = relabeled_yaw + stage_b_fit.x[2]
    stage_b = stage_metrics(pinch_identity, b_center, b_yaw)

    offset_indices = [BODY_JOINT_NAMES.index(name) for name in FITTED_OFFSET_JOINTS]

    def stage_c_residual(params: np.ndarray) -> np.ndarray:
        center = (base_center[0] + params[0], base_center[1] + params[1])
        yaw = relabeled_yaw + params[2]
        offsets = np.zeros(5)
        offsets[offset_indices] = params[3:]
        points = _fk_pinch_points(binding, events, offsets)
        targets = _event_targets(events, center, yaw, neck)
        residual = (points - targets).ravel()
        prior = params[3:] / prior_sigma / math.sqrt(len(events) * 3)
        return np.concatenate([residual, prior])

    lower = np.concatenate([[-0.08, -0.08, -15.0], -offset_bound * np.ones(4)])
    upper = np.concatenate([[0.08, 0.08, 15.0], offset_bound * np.ones(4)])
    stage_c_fit = least_squares(
        stage_c_residual,
        x0=np.concatenate([stage_b_fit.x, np.zeros(4)]),
        bounds=(lower, upper),
        method="trf",
        diff_step=1e-3,
    )
    c_center = (base_center[0] + stage_c_fit.x[0], base_center[1] + stage_c_fit.x[1])
    c_yaw = relabeled_yaw + stage_c_fit.x[2]
    c_offsets = np.zeros(5)
    c_offsets[offset_indices] = stage_c_fit.x[3:]
    stage_c_points = _fk_pinch_points(binding, events, c_offsets)
    stage_c = stage_metrics(stage_c_points, c_center, c_yaw)

    # The envelope was measured on raw deg2rad values; the adapter adds the
    # fitted zero offsets, so the mapped no-clipping envelope shifts with them.
    shifted_envelope = tuple(
        (low + float(delta), high + float(delta))
        for (low, high), delta in zip(envelope, c_offsets)
    )
    candidate = WorkcellCandidate(
        board_yaw_relative_to_table_degrees=float(c_yaw),
        board_center_in_table_frame_xy_m=(float(c_center[0]), float(c_center[1])),
        joint_zero_offsets_rad=tuple(float(v) for v in c_offsets),
        joint_range_envelope_rad=shifted_envelope,
    )

    # Stage C': the base height was never observable in the overhead photo, so
    # allow a bounded base-z correction, and absorb the reopen-phase timing
    # bias (the extractor's reopen fires after retreat begins) in a bounded
    # non-negative nuisance term instead of corrupting calibration parameters.
    base_z_bound = float(fit["base_z_offset_bound_m"])
    reopen_bias_bound = float(fit["reopen_timing_z_bound_m"])
    reopen_mask = np.asarray([event.phase == "destination_reopen" for event in events])

    def stage_c_prime_residual(params: np.ndarray) -> np.ndarray:
        center = (base_center[0] + params[0], base_center[1] + params[1])
        yaw = relabeled_yaw + params[2]
        offsets = np.zeros(5)
        offsets[offset_indices] = params[3:7]
        base_z = params[7]
        reopen_bias = params[8]
        points = _fk_pinch_points(binding, events, offsets)
        points = points + np.asarray([0.0, 0.0, base_z])
        targets = _event_targets(events, center, yaw, neck)
        targets[reopen_mask, 2] += reopen_bias
        residual = (points - targets).ravel()
        prior = params[3:7] / prior_sigma / math.sqrt(len(events) * 3)
        return np.concatenate([residual, prior])

    lower_prime = np.concatenate([lower, [-base_z_bound, 0.0]])
    upper_prime = np.concatenate([upper, [base_z_bound, reopen_bias_bound]])
    stage_c_prime_fit = least_squares(
        stage_c_prime_residual,
        x0=np.concatenate([stage_c_fit.x, [0.0, 1e-6]]),
        bounds=(lower_prime, upper_prime),
        method="trf",
        diff_step=1e-3,
    )
    p_center = (
        base_center[0] + stage_c_prime_fit.x[0],
        base_center[1] + stage_c_prime_fit.x[1],
    )
    p_yaw = relabeled_yaw + stage_c_prime_fit.x[2]
    p_offsets = np.zeros(5)
    p_offsets[offset_indices] = stage_c_prime_fit.x[3:7]
    p_base_z = float(stage_c_prime_fit.x[7])
    p_reopen_bias = float(stage_c_prime_fit.x[8])
    prime_points = _fk_pinch_points(binding, events, p_offsets)
    prime_points = prime_points + np.asarray([0.0, 0.0, p_base_z])
    prime_targets = _event_targets(events, p_center, p_yaw, neck)
    prime_targets[reopen_mask, 2] += p_reopen_bias
    prime_residual = prime_points - prime_targets
    prime_distance = np.linalg.norm(prime_residual, axis=1)
    stage_c_prime = {
        "event_rms_distance_m": float(np.sqrt(np.mean(prime_distance**2))),
        "event_mean_distance_m": float(np.mean(prime_distance)),
        "event_maximum_distance_m": float(np.max(prime_distance)),
        "xy_rms_m": float(np.sqrt(np.mean(np.sum(prime_residual[:, :2] ** 2, axis=1)))),
        "z_mean_m": float(np.mean(prime_residual[:, 2])),
        "z_rms_m": float(np.sqrt(np.mean(prime_residual[:, 2] ** 2))),
        "close_event_z_mean_m": float(np.mean(prime_residual[~reopen_mask, 2])),
    }
    prime_envelope = tuple(
        (low + float(delta), high + float(delta))
        for (low, high), delta in zip(envelope, p_offsets)
    )
    candidate_prime = WorkcellCandidate(
        board_yaw_relative_to_table_degrees=float(p_yaw),
        board_center_in_table_frame_xy_m=(float(p_center[0]), float(p_center[1])),
        joint_zero_offsets_rad=tuple(float(v) for v in p_offsets),
        joint_range_envelope_rad=prime_envelope,
        base_z_offset_m=p_base_z,
    )
    stage_c_prime_parameters = candidate_prime.as_dict()
    stage_c_prime_parameters["reopen_timing_z_bias_m"] = p_reopen_bias

    # Stage D: lift-dominant hypothesis. A single shoulder-lift zero offset
    # explains the whole vertical residual (one horn-spline tooth reseat or a
    # badly eyeballed calibration middle on that joint); the other joints keep
    # a tight 3-degree prior. Fewer effective parameters than stage C'.
    lift_bound = math.radians(float(fit["stage_d_lift_offset_bound_degrees"]))
    tight_sigma = math.radians(float(fit["stage_d_other_offset_prior_sigma_degrees"]))
    lift_position = FITTED_OFFSET_JOINTS.index("shoulder_lift")
    other_positions = [
        position for position in range(4) if position != lift_position
    ]

    def stage_d_residual(params: np.ndarray) -> np.ndarray:
        center = (base_center[0] + params[0], base_center[1] + params[1])
        yaw = relabeled_yaw + params[2]
        offsets = np.zeros(5)
        offsets[offset_indices] = params[3:7]
        reopen_bias = params[7]
        points = _fk_pinch_points(binding, events, offsets)
        targets = _event_targets(events, center, yaw, neck)
        targets[reopen_mask, 2] += reopen_bias
        residual = (points - targets).ravel()
        prior = params[3:7][other_positions] / tight_sigma / math.sqrt(len(events) * 3)
        return np.concatenate([residual, prior])

    lower_d = np.concatenate([
        [-0.08, -0.08, -15.0],
        [-lift_bound if position == lift_position else -offset_bound for position in range(4)],
        [0.0],
    ])
    upper_d = np.concatenate([
        [0.08, 0.08, 15.0],
        [lift_bound if position == lift_position else offset_bound for position in range(4)],
        [reopen_bias_bound],
    ])
    stage_d_fit = least_squares(
        stage_d_residual,
        x0=np.concatenate([stage_b_fit.x, np.zeros(4), [1e-6]]),
        bounds=(lower_d, upper_d),
        method="trf",
        diff_step=1e-3,
    )
    d_center = (base_center[0] + stage_d_fit.x[0], base_center[1] + stage_d_fit.x[1])
    d_yaw = relabeled_yaw + stage_d_fit.x[2]
    d_offsets = np.zeros(5)
    d_offsets[offset_indices] = stage_d_fit.x[3:7]
    d_reopen_bias = float(stage_d_fit.x[7])
    d_points = _fk_pinch_points(binding, events, d_offsets)
    d_targets = _event_targets(events, d_center, d_yaw, neck)
    d_targets[reopen_mask, 2] += d_reopen_bias
    d_residual = d_points - d_targets
    d_distance = np.linalg.norm(d_residual, axis=1)
    stage_d = {
        "event_rms_distance_m": float(np.sqrt(np.mean(d_distance**2))),
        "event_mean_distance_m": float(np.mean(d_distance)),
        "event_maximum_distance_m": float(np.max(d_distance)),
        "xy_rms_m": float(np.sqrt(np.mean(np.sum(d_residual[:, :2] ** 2, axis=1)))),
        "z_mean_m": float(np.mean(d_residual[:, 2])),
        "z_rms_m": float(np.sqrt(np.mean(d_residual[:, 2] ** 2))),
        "close_event_z_mean_m": float(np.mean(d_residual[~reopen_mask, 2])),
        "close_event_z_std_m": float(np.std(d_residual[~reopen_mask, 2])),
    }
    d_envelope = tuple(
        (low + float(delta), high + float(delta))
        for (low, high), delta in zip(envelope, d_offsets)
    )
    candidate_lift = WorkcellCandidate(
        board_yaw_relative_to_table_degrees=float(d_yaw),
        board_center_in_table_frame_xy_m=(float(d_center[0]), float(d_center[1])),
        joint_zero_offsets_rad=tuple(float(v) for v in d_offsets),
        joint_range_envelope_rad=d_envelope,
    )
    stage_d_parameters = candidate_lift.as_dict()
    stage_d_parameters["reopen_timing_z_bias_m"] = d_reopen_bias

    return {
        "frozen_baseline_kinematic": frozen_baseline,
        "stage_a_relabel_kinematic": stage_a,
        "stage_b_planar_kinematic": stage_b,
        "stage_b_parameters": {
            "board_center_delta_m": stage_b_fit.x[:2].tolist(),
            "board_yaw_delta_degrees": float(stage_b_fit.x[2]),
        },
        "stage_c_kinematic": stage_c,
        "stage_c_parameters": candidate.as_dict(),
        "stage_c_prime_kinematic": stage_c_prime,
        "stage_c_prime_parameters": stage_c_prime_parameters,
        "stage_d_lift_kinematic": stage_d,
        "stage_d_lift_parameters": stage_d_parameters,
        "candidate": candidate,
        "candidate_prime": candidate_prime,
        "candidate_lift": candidate_lift,
    }


def replay_episode_with_candidate(
    *,
    reward_contract: dict[str, Any],
    episode: dict[str, Any],
    source: str,
    destination: str,
    samples: list[dict[str, Any]],
    candidate: WorkcellCandidate | None,
    frozen_board_center: tuple[float, float],
    frozen_board_yaw: float,
    contact_variant: Any | None = None,
) -> dict[str, Any]:
    """Command-driven physics replay scored with the frozen reward thresholds.

    candidate=None replays the frozen workcell with the identity adapter and
    frozen (clipping) ranges, reproducing the terminal-negative baseline.
    """

    if candidate is None:
        board_center = frozen_board_center
        board_yaw = frozen_board_yaw
        adapter = JointAdapter(
            adapter_id="so101_physical_degrees_to_current_scene_provisional_v1",
            body_joint_signs=(1, 1, 1, 1, 1),
            body_joint_zero_offsets_rad=(0.0, 0.0, 0.0, 0.0, 0.0),
            evidence_class="provisional_range_audit_blocked_not_calibrated",
        )
        binding = build_workcell_model(WorkcellCandidate(
            board_yaw_relative_to_table_degrees=board_yaw,
            board_center_in_table_frame_xy_m=board_center,
            joint_zero_offsets_rad=(0.0,) * 5,
            joint_range_envelope_rad=tuple((0.0, 0.0) for _ in range(5)),
        ), contact_variant=contact_variant)
    else:
        board_center = candidate.board_center_in_table_frame_xy_m
        board_yaw = candidate.board_yaw_relative_to_table_degrees
        adapter = candidate.adapter()
        binding = build_workcell_model(candidate, contact_variant=contact_variant)

    model, data = binding["model"], binding["data"]
    actuator_ids = binding["actuator_ids"]
    qpos_addresses = binding["qpos_addresses"]
    bounds = binding["actuator_bounds"]

    file_ = source[0]
    selected_name = BASELINE_PIECE_BY_FILE[file_]
    selected_body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, selected_name)
    selected_joint = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_JOINT, f"{selected_name}_free"
    )
    selected_qpos = int(model.jnt_qposadr[selected_joint])
    selected_dof = int(model.jnt_dofadr[selected_joint])
    source_xyz = np.asarray(_workcell_square_center(
        source,
        board_center_in_table_frame_xy_m=board_center,
        board_yaw_relative_to_table_degrees=board_yaw,
        board_side_m=None if candidate is None else candidate.board_side_m,
    ))
    data.qpos[selected_qpos : selected_qpos + 3] = source_xyz
    data.qvel[selected_dof : selected_dof + 6] = 0.0

    first_actual_raw = physical_values_to_sim_with_adapter(
        samples[0]["follower_actual_position_degrees"], bounds[-1], adapter
    )
    first_actual = np.clip(first_actual_raw, bounds[:, 0], bounds[:, 1])
    data.qpos[qpos_addresses] = first_actual
    data.ctrl[actuator_ids] = first_actual
    mujoco.mj_forward(model, data)
    mujoco.mj_step(model, data, nstep=100)

    piece_bodies = _piece_bodies(model)
    initial_positions = {
        name: np.asarray(data.xpos[body_id], dtype=float).copy()
        for name, body_id in piece_bodies.items()
    }
    initial_height = float(data.xpos[selected_body][2])
    robot_body_ids = {
        body_id for body_id in range(model.nbody)
        if (mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id) or "").startswith("left_")
    }
    fixed_geom = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "left_fixed_jaw_box1")
    jaw_body_ids = {
        int(model.geom_bodyid[fixed_geom]),
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "left_moving_jaw_so101_v1"),
    }
    trace = [_trace_row(
        model, data, selected_body=selected_body, selected_dof=selected_dof,
        piece_bodies=piece_bodies, initial_piece_positions=initial_positions,
        robot_body_ids=robot_body_ids, jaw_body_ids=jaw_body_ids,
    )]
    pinch_local = binding["pinch_offset_local"]

    def pinch_to_piece() -> float:
        pinch = _pinch_point(model, data, "left", pinch_local)
        return float(np.linalg.norm(pinch - np.asarray(data.xpos[selected_body])))

    minimum_pinch_to_piece = pinch_to_piece()
    clipped_command_rows = 0
    previous_timestamp: float | None = None
    nominal_dt = 1.0 / max(1, int(episode["sample_hz"]))
    for sample in samples:
        timestamp = float(sample["timestamp_monotonic_seconds"])
        dt = nominal_dt if previous_timestamp is None else timestamp - previous_timestamp
        if not math.isfinite(dt) or dt <= 0.0 or dt > 1.0:
            dt = nominal_dt
        previous_timestamp = timestamp
        raw_command = physical_values_to_sim_with_adapter(
            sample["follower_command_degrees"], bounds[-1], adapter
        )
        command = np.clip(raw_command, bounds[:, 0], bounds[:, 1])
        clipped_command_rows += int(not np.array_equal(raw_command, command))
        data.ctrl[actuator_ids] = command
        mujoco.mj_step(model, data, nstep=max(1, round(dt / float(model.opt.timestep))))
        minimum_pinch_to_piece = min(minimum_pinch_to_piece, pinch_to_piece())
        trace.append(_trace_row(
            model, data, selected_body=selected_body, selected_dof=selected_dof,
            piece_bodies=piece_bodies, initial_piece_positions=initial_positions,
            robot_body_ids=robot_body_ids, jaw_body_ids=jaw_body_ids,
        ))
    for _ in range(200):
        mujoco.mj_step(model, data)
    trace.append(_trace_row(
        model, data, selected_body=selected_body, selected_dof=selected_dof,
        piece_bodies=piece_bodies, initial_piece_positions=initial_positions,
        robot_body_ids=robot_body_ids, jaw_body_ids=jaw_body_ids,
    ))
    target_xyz = _workcell_square_center(
        destination,
        board_center_in_table_frame_xy_m=board_center,
        board_yaw_relative_to_table_degrees=board_yaw,
        board_side_m=None if candidate is None else candidate.board_side_m,
    )
    score = score_episode(
        reward_contract, skill_id=f"pawn_{source}_to_{destination}", trace=trace,
        target_position_xyz_m=target_xyz, initial_piece_height_m=initial_height,
        evaluation_mode="source_demonstration_replay",
        action_owner="physical_teleoperator", assistance_used=False,
    )
    contact_rows = sum(int(row["selected_piece_jaw_contact"]) for row in trace)
    return {
        "recording_id": episode["recording_id"],
        "folder_label": episode["folder_label"],
        "skill_id": f"pawn_{source}_to_{destination}",
        "clipped_command_rows": clipped_command_rows,
        "minimum_pinch_to_selected_piece_m": float(minimum_pinch_to_piece),
        "selected_piece_contact_rows": contact_rows,
        "selected_piece_contact_observed": bool(
            score["gate_results"]["selected_piece_contact_observed"]
        ),
        "piece_lifted": bool(score["gate_results"]["piece_lifted"]),
        "maximum_piece_rise_m": float(score["maximum_piece_rise_m"]),
        "final_target_distance_m": float(score["final_center_distance_m"]),
        "diagnostic_reward": float(score["diagnostic_reward"]),
        "task_consequence_success": bool(score["task_consequence_success"]),
    }


def _episode_payloads(
    source_root: Path, membership: dict[str, str], wanted_split: str
) -> list[tuple[dict[str, Any], str, str, list[dict[str, Any]]]]:
    catalog = json.loads(CATALOG_PATH.read_bytes())
    payloads = []
    for episode, source, destination in _product_episodes(catalog):
        if membership.get(episode["recording_id"]) != wanted_split:
            continue
        samples = _load_source(episode, source_root)
        payloads.append((episode, source, destination, samples))
    return payloads


def run_workcell_fit(
    *, source_repository_root: Path, output_path: Path
) -> dict[str, Any]:
    contract = load_workcell_contract()
    source_fit_contract = load_source_fit_contract()
    reward_contract = load_reward_contract()
    membership = _split_membership()
    train = _episode_payloads(source_repository_root, membership, "train")
    if len(train) != 11:
        raise WorkcellFitError(f"expected 11 product train episodes, found {len(train)}")

    events: list[WorkcellEvent] = []
    for episode, source, destination, samples in train:
        events.extend(_extract_events(episode, source, destination, samples, source_fit_contract))

    envelope = measured_range_envelope([samples for _, _, _, samples in train])
    fit = contract["fit"]
    scratch_candidate = WorkcellCandidate(
        board_yaw_relative_to_table_degrees=float(
            fit["frozen_board_yaw_relative_to_table_degrees"]
        ),
        board_center_in_table_frame_xy_m=tuple(
            float(v) for v in fit["frozen_board_center_in_table_frame_xy_m"]
        ),
        joint_zero_offsets_rad=(0.0,) * 5,
        joint_range_envelope_rad=envelope,
    )
    binding = build_workcell_model(scratch_candidate)
    result = fit_candidate(events, binding, contract, envelope)
    candidates = {
        "stage_c": result.pop("candidate"),
        "stage_c_prime": result.pop("candidate_prime"),
        "stage_d_lift": result.pop("candidate_lift"),
    }

    frozen_center = tuple(float(v) for v in fit["frozen_board_center_in_table_frame_xy_m"])
    frozen_yaw = float(fit["frozen_board_yaw_relative_to_table_degrees"])
    replays_baseline = []
    replays_by_name: dict[str, list[dict[str, Any]]] = {
        name: [] for name in candidates
    }
    for episode, source, destination, samples in train:
        replays_baseline.append(replay_episode_with_candidate(
            reward_contract=reward_contract, episode=episode, source=source,
            destination=destination, samples=samples, candidate=None,
            frozen_board_center=frozen_center, frozen_board_yaw=frozen_yaw,
        ))
        for name, current in candidates.items():
            replays_by_name[name].append(replay_episode_with_candidate(
                reward_contract=reward_contract, episode=episode, source=source,
                destination=destination, samples=samples, candidate=current,
                frozen_board_center=frozen_center, frozen_board_yaw=frozen_yaw,
            ))

    def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "episodes": len(rows),
            "clipped_episodes": sum(1 for r in rows if r["clipped_command_rows"]),
            "selected_piece_contact": sum(
                1 for r in rows if r["selected_piece_contact_observed"]
            ),
            "lifted": sum(1 for r in rows if r["piece_lifted"]),
            "successes": sum(1 for r in rows if r["task_consequence_success"]),
            "mean_maximum_piece_rise_m": float(
                np.mean([r["maximum_piece_rise_m"] for r in rows])
            ),
            "mean_final_target_distance_m": float(
                np.mean([r["final_target_distance_m"] for r in rows])
            ),
            "mean_diagnostic_reward": float(
                np.mean([r["diagnostic_reward"] for r in rows])
            ),
        }

    kinematic_key = {
        "stage_c": "stage_c_kinematic",
        "stage_c_prime": "stage_c_prime_kinematic",
        "stage_d_lift": "stage_d_lift_kinematic",
    }
    parameters_key = {
        "stage_c": "stage_c_parameters",
        "stage_c_prime": "stage_c_prime_parameters",
        "stage_d_lift": "stage_d_lift_parameters",
    }
    selected_name = max(
        candidates,
        key=lambda name: (
            sum(
                1 for r in replays_by_name[name]
                if r["selected_piece_contact_observed"]
            ),
            -result[kinematic_key[name]]["event_rms_distance_m"],
        ),
    )
    selected_parameters = dict(result[parameters_key[selected_name]])

    receipt = {
        "schema_version": "sim2claw.pawn_bg_workcell_fit_receipt.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "contract_sha256": sha256_file(CONTRACT_PATH),
        "calibration_sha256": sha256_file(CALIBRATION_PATH),
        "split_sha256": sha256_file(SPLIT_PATH),
        "catalog_sha256": sha256_file(CATALOG_PATH),
        "train_episode_count": len(train),
        "train_event_count": len(events),
        "kinematic": dict(result),
        "train_replay_frozen_baseline": {
            "summary": summarize(replays_baseline), "episodes": replays_baseline,
        },
        "train_replay_candidates": {
            name: {"summary": summarize(rows), "episodes": rows}
            for name, rows in replays_by_name.items()
        },
        "selection_rule": (
            "more train episodes with selected-piece contact wins; "
            "tie broken by lower train event RMS"
        ),
        "selected_candidate": selected_name,
        "selected_parameters": selected_parameters,
        "held_out_opened": False,
        "claim_boundary": (
            "Bounded workcell candidate fitted on the 11 training-side product "
            "episodes only. Board relabel is owner-video-consistent; planar board "
            "and joint zero offsets are simulator-frame estimates, not physical "
            "calibration. Consequence scores reuse frozen thresholds "
            "diagnostically. No promotion, training, policy, or physical claim."
        ),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return receipt


def run_held_out_validation(
    *, source_repository_root: Path, receipt_path: Path, output_path: Path
) -> dict[str, Any]:
    """Open the held-out product episodes exactly once against the frozen candidate."""

    receipt = json.loads(receipt_path.read_bytes())
    params = receipt["selected_parameters"]
    reopen_timing_bias = float(params.get("reopen_timing_z_bias_m", 0.0))
    candidate = WorkcellCandidate(
        board_yaw_relative_to_table_degrees=float(
            params["board_yaw_relative_to_table_degrees"]
        ),
        board_center_in_table_frame_xy_m=tuple(
            float(v) for v in params["board_center_in_table_frame_xy_m"]
        ),
        joint_zero_offsets_rad=tuple(float(v) for v in params["joint_zero_offsets_rad"]),
        joint_range_envelope_rad=tuple(
            (float(a), float(b)) for a, b in params["joint_range_envelope_rad"]
        ),
        base_z_offset_m=float(params.get("base_z_offset_m", 0.0)),
    )
    contract = load_workcell_contract()
    source_fit_contract = load_source_fit_contract()
    reward_contract = load_reward_contract()
    membership = _split_membership()
    held_out = _episode_payloads(source_repository_root, membership, "held_out")
    if len(held_out) != 2:
        raise WorkcellFitError(f"expected 2 product held-out episodes, found {len(held_out)}")

    fit = contract["fit"]
    neck = float(fit["estimated_pawn_neck_height_m"])
    frozen_center = tuple(float(v) for v in fit["frozen_board_center_in_table_frame_xy_m"])
    frozen_yaw = float(fit["frozen_board_yaw_relative_to_table_degrees"])

    binding = build_workcell_model(candidate)
    events: list[WorkcellEvent] = []
    for episode, source, destination, samples in held_out:
        events.extend(_extract_events(episode, source, destination, samples, source_fit_contract))
    offsets = np.asarray(candidate.joint_zero_offsets_rad)
    reopen_mask = np.asarray([event.phase == "destination_reopen" for event in events])
    points = _fk_pinch_points(binding, events, offsets)
    points = points + np.asarray([0.0, 0.0, candidate.base_z_offset_m])
    targets = _event_targets(
        events, candidate.board_center_in_table_frame_xy_m,
        candidate.board_yaw_relative_to_table_degrees, neck,
    )
    targets[reopen_mask, 2] += reopen_timing_bias
    identity_points = _fk_pinch_points(binding, events, np.zeros(5))
    identity_points = identity_points - np.asarray([0.0, 0.0, candidate.base_z_offset_m])
    frozen_targets = _event_targets(events, frozen_center, frozen_yaw, neck)

    def metrics(p: np.ndarray, t: np.ndarray) -> dict[str, float]:
        distance = np.linalg.norm(p - t, axis=1)
        return {
            "event_rms_distance_m": float(np.sqrt(np.mean(distance**2))),
            "event_mean_distance_m": float(np.mean(distance)),
            "event_maximum_distance_m": float(np.max(distance)),
        }

    replays_baseline = []
    replays_candidate = []
    for episode, source, destination, samples in held_out:
        replays_baseline.append(replay_episode_with_candidate(
            reward_contract=reward_contract, episode=episode, source=source,
            destination=destination, samples=samples, candidate=None,
            frozen_board_center=frozen_center, frozen_board_yaw=frozen_yaw,
        ))
        replays_candidate.append(replay_episode_with_candidate(
            reward_contract=reward_contract, episode=episode, source=source,
            destination=destination, samples=samples, candidate=candidate,
            frozen_board_center=frozen_center, frozen_board_yaw=frozen_yaw,
        ))

    admission = contract["admission"]
    held_out_rms = metrics(points, targets)["event_rms_distance_m"]
    validation = {
        "schema_version": "sim2claw.pawn_bg_workcell_held_out_validation.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "fit_receipt_sha256": sha256_file(receipt_path),
        "held_out_episode_count": len(held_out),
        "held_out_event_count": len(events),
        "held_out_kinematic_candidate": metrics(points, targets),
        "held_out_kinematic_frozen_baseline": metrics(identity_points, frozen_targets),
        "held_out_replay_frozen_baseline": replays_baseline,
        "held_out_replay_candidate": replays_candidate,
        "admission_rule": admission,
        "admitted": bool(
            held_out_rms <= float(admission["maximum_held_out_event_rms_m"])
            and all(r["clipped_command_rows"] == 0 for r in replays_candidate)
        ),
        "claim_boundary": (
            "Held-out product episodes opened exactly once against the frozen "
            "candidate. Admission is kinematic-generalization only; consequence "
            "deltas are diagnostic evidence, not physical-transfer proof."
        ),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(validation, indent=2), encoding="utf-8")
    return validation
