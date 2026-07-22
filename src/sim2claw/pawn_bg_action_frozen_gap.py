"""Action-invariant B-G real-to-simulator gap attribution.

This module deliberately does not repair a policy.  It freezes an input action
array once and feeds the same bytes to each simulator variant.  Only simulator
geometry is fitted here.  Joint adapters, action offsets, IK corrections,
clipping, assistance, and corrective suffixes are outside this experiment.

Two evidence streams remain separate:

* physical teleoperation recordings: the Stage-D adapter is reconstructed on
  the train split, then frozen before commands are mapped exactly once;
* retained GR00T actions: the unassisted float64 ``applied_actions`` arrays are
  loaded from the prior rollout and replayed directly, without an adapter.

Neither stream is a new policy evaluation or physical-transfer result.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import mujoco
import numpy as np
from PIL import Image, ImageDraw
from scipy.optimize import least_squares

from .grasp import _pinch_point
from .learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .paths import REPO_ROOT
from .pawn_bg_demo_sim import (
    BASELINE_PIECE_BY_FILE,
    _piece_bodies,
    _trace_row,
    physical_values_to_sim_with_adapter,
)
from .pawn_bg_reward import load_reward_contract, score_episode
from .pawn_bg_source_fit import extract_phase_indices, load_source_fit_contract
from .pawn_bg_workcell_fit import (
    CALIBRATION_PATH,
    CATALOG_PATH,
    SPLIT_PATH,
    WorkcellCandidate,
    WorkcellEvent,
    WorkcellFitError,
    _episode_payloads,
    _event_targets,
    _extract_events,
    _fk_pinch_points,
    _split_membership,
    _workcell_square_center,
    build_workcell_model,
    fit_candidate,
    load_workcell_contract,
    measured_range_envelope,
)
from .pawn_bg_workcell_fit_v2 import _metrics
from .scene import load_capture_config


CONTRACT_PATH = (
    REPO_ROOT / "configs" / "optimization" / "pawn_bg_action_frozen_gap_v1.json"
)
IMPLEMENTATION_PATH = Path(__file__).resolve()
SCHEMA = "sim2claw.pawn_bg_action_frozen_gap.v1"
RECEIPT_SCHEMA = "sim2claw.pawn_bg_action_frozen_gap_receipt.v1"
CONFIRMATION_SCHEMA = "sim2claw.pawn_bg_action_frozen_gap_confirmation.v1"
POLICY_SCHEMA = "sim2claw.pawn_bg_action_frozen_policy_replay.v1"


def _array_sha256(value: np.ndarray) -> str:
    array = np.ascontiguousarray(value)
    return hashlib.sha256(array.tobytes()).hexdigest()


def load_action_frozen_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    contract = json.loads(path.read_text(encoding="utf-8"))
    if contract.get("schema_version") != SCHEMA:
        raise WorkcellFitError("unexpected action-frozen gap contract schema")
    authority = contract.get("authority")
    if not isinstance(authority, dict) or not authority or any(authority.values()):
        raise WorkcellFitError("action-frozen gap authority widened")
    invariance = contract.get("action_invariance")
    required_true = (
        "no_ik_corrections",
        "no_post_policy_offsets",
        "no_corrective_suffix",
        "no_assistance",
        "no_candidate_specific_action_mapping",
        "no_clipping",
        "require_identical_shape_dtype_and_sha256",
    )
    if not isinstance(invariance, dict) or any(
        invariance.get(key) is not True for key in required_true
    ):
        raise WorkcellFitError("action-invariance contract is not fail closed")
    parent = contract["parent_workcell_contract"]
    parent_path = (REPO_ROOT / parent["path"]).resolve()
    if sha256_file(parent_path) != parent["sha256"]:
        raise WorkcellFitError("action-frozen parent contract changed")
    if parent.get("fixed_action_adapter") != "stage_d_lift":
        raise WorkcellFitError("action-frozen contract requires the Stage-D adapter")
    geometry = contract["geometry_candidate"]
    if geometry.get("parameters") != [
        "board_center_in_table_frame_xy_m",
        "board_yaw_relative_to_table_degrees",
        "board_side_m",
    ]:
        raise WorkcellFitError("geometry-only parameter list changed")
    lower, upper = (float(value) for value in geometry["playing_side_bounds_m"])
    if not 0.0 < lower < upper:
        raise WorkcellFitError("invalid geometry-only board-side bounds")
    return contract


def _load_partition(
    source_root: Path, split_name: str
) -> tuple[list[tuple[dict[str, Any], str, str, list[dict[str, Any]]]], list[WorkcellEvent]]:
    membership = _split_membership()
    payloads = _episode_payloads(source_root, membership, split_name)
    source_fit = load_source_fit_contract()
    events = [
        event
        for episode, source, destination, samples in payloads
        for event in _extract_events(episode, source, destination, samples, source_fit)
    ]
    return payloads, events


def _reconstruct_stage_d(
    train: list[tuple[dict[str, Any], str, str, list[dict[str, Any]]]],
    events: list[WorkcellEvent],
) -> tuple[dict[str, Any], WorkcellCandidate, dict[str, Any], dict[str, Any]]:
    parent = load_workcell_contract()
    envelope = measured_range_envelope([samples for _, _, _, samples in train])
    fit = parent["fit"]
    scratch = WorkcellCandidate(
        board_yaw_relative_to_table_degrees=float(
            fit["frozen_board_yaw_relative_to_table_degrees"]
        ),
        board_center_in_table_frame_xy_m=tuple(
            float(value) for value in fit["frozen_board_center_in_table_frame_xy_m"]
        ),
        joint_zero_offsets_rad=(0.0,) * 5,
        joint_range_envelope_rad=envelope,
    )
    result = fit_candidate(events, build_workcell_model(scratch), parent, envelope)
    return parent, result["candidate_lift"], result["stage_d_lift_parameters"], result


def _fit_geometry_only(
    *,
    contract: dict[str, Any],
    parent: dict[str, Any],
    events: list[WorkcellEvent],
    stage_d: WorkcellCandidate,
    stage_d_parameters: dict[str, Any],
) -> tuple[WorkcellCandidate, dict[str, Any], dict[str, float], dict[str, Any]]:
    """Fit board center/yaw/side with the Stage-D joint mapping immutable."""

    parent_fit = parent["fit"]
    frozen_center = np.asarray(
        parent_fit["frozen_board_center_in_table_frame_xy_m"], dtype=np.float64
    )
    frozen_yaw = float(parent_fit["frozen_board_yaw_relative_to_table_degrees"])
    relabeled_yaw = frozen_yaw + 180.0
    neck = float(parent_fit["estimated_pawn_neck_height_m"])
    reopen_bias = float(stage_d_parameters["reopen_timing_z_bias_m"])
    reopen_mask = np.asarray(
        [event.phase == "destination_reopen" for event in events], dtype=bool
    )
    fixed_offsets = np.asarray(stage_d.joint_zero_offsets_rad, dtype=np.float64)
    binding = build_workcell_model(stage_d)
    points = _fk_pinch_points(binding, events, fixed_offsets)

    baseline_targets = _event_targets(
        events,
        stage_d.board_center_in_table_frame_xy_m,
        stage_d.board_yaw_relative_to_table_degrees,
        neck,
        stage_d.board_side_m,
    )
    baseline_targets[reopen_mask, 2] += reopen_bias
    baseline_metrics = _metrics(points, baseline_targets)

    board_default = float(
        load_capture_config()["simulation_estimates"]["board"]["side_m"]
    )
    x0 = np.asarray(
        [
            stage_d.board_center_in_table_frame_xy_m[0] - frozen_center[0],
            stage_d.board_center_in_table_frame_xy_m[1] - frozen_center[1],
            stage_d.board_yaw_relative_to_table_degrees - relabeled_yaw,
            board_default,
        ],
        dtype=np.float64,
    )
    lower_side, upper_side = (
        float(value)
        for value in contract["geometry_candidate"]["playing_side_bounds_m"]
    )

    def residual(parameters: np.ndarray) -> np.ndarray:
        center = tuple((frozen_center + parameters[:2]).tolist())
        targets = _event_targets(
            events,
            center,
            relabeled_yaw + parameters[2],
            neck,
            float(parameters[3]),
        )
        targets[reopen_mask, 2] += reopen_bias
        return (points - targets).ravel()

    fit = least_squares(
        residual,
        x0=x0,
        bounds=(
            np.asarray([-0.08, -0.08, -15.0, lower_side], dtype=np.float64),
            np.asarray([0.08, 0.08, 15.0, upper_side], dtype=np.float64),
        ),
        method="trf",
        diff_step=float(contract["geometry_candidate"]["finite_difference_step"]),
    )
    center = tuple((frozen_center + fit.x[:2]).astype(float).tolist())
    yaw = float(relabeled_yaw + fit.x[2])
    side = float(fit.x[3])
    candidate_targets = _event_targets(events, center, yaw, neck, side)
    candidate_targets[reopen_mask, 2] += reopen_bias
    candidate_metrics = _metrics(points, candidate_targets)
    candidate = WorkcellCandidate(
        board_yaw_relative_to_table_degrees=yaw,
        board_center_in_table_frame_xy_m=center,
        joint_zero_offsets_rad=stage_d.joint_zero_offsets_rad,
        joint_range_envelope_rad=stage_d.joint_range_envelope_rad,
        board_side_m=side,
    )
    parameters = candidate.as_dict()
    parameters["square_side_m"] = side / 8.0
    parameters["reopen_timing_z_bias_m"] = reopen_bias
    parameters["frozen_action_adapter_sha256"] = stage_d.adapter().sha256
    optimizer = {
        "success": bool(fit.success),
        "status": int(fit.status),
        "cost": float(fit.cost),
        "optimality": float(fit.optimality),
        "function_evaluations": int(fit.nfev),
    }
    if not np.array_equal(
        np.asarray(candidate.joint_zero_offsets_rad),
        np.asarray(stage_d.joint_zero_offsets_rad),
    ):
        raise WorkcellFitError("geometry fit changed the frozen joint adapter")
    return candidate, parameters, candidate_metrics, {
        "baseline_metrics": baseline_metrics,
        "optimizer": optimizer,
        "points": points,
        "baseline_targets": baseline_targets,
        "candidate_targets": candidate_targets,
    }


def _phase_labels(
    count: int, open_index: int, source_index: int, destination_index: int
) -> list[str]:
    labels = []
    for index in range(count):
        if index <= open_index:
            labels.append("initial_open")
        elif index <= source_index:
            labels.append("source_approach_close")
        elif index < destination_index:
            labels.append("transfer")
        else:
            labels.append("destination_reopen_release")
    return labels


def _point(binding: dict[str, Any]) -> np.ndarray:
    return _pinch_point(
        binding["model"],
        binding["data"],
        "left",
        binding["pinch_offset_local"],
    ).copy()


def _target(candidate: WorkcellCandidate, square: str, neck: float) -> np.ndarray:
    value = np.asarray(
        _workcell_square_center(
            square,
            board_center_in_table_frame_xy_m=candidate.board_center_in_table_frame_xy_m,
            board_yaw_relative_to_table_degrees=candidate.board_yaw_relative_to_table_degrees,
            board_side_m=candidate.board_side_m,
        ),
        dtype=np.float64,
    )
    value[2] += neck
    return value


def _assert_same_actions(
    source: np.ndarray, variants: dict[str, np.ndarray]
) -> dict[str, Any]:
    if source.dtype != np.float64 or source.ndim != 2 or source.shape[1] != 6:
        raise WorkcellFitError("frozen actions must be an Nx6 float64 array")
    source_hash = _array_sha256(source)
    rows: dict[str, Any] = {}
    for name, actions in variants.items():
        same = (
            actions.shape == source.shape
            and actions.dtype == source.dtype
            and np.array_equal(actions, source)
            and _array_sha256(actions) == source_hash
        )
        if not same:
            raise WorkcellFitError(f"{name} did not receive byte-identical actions")
        rows[name] = {
            "shape": list(actions.shape),
            "dtype": str(actions.dtype),
            "sha256": _array_sha256(actions),
            "identical_to_frozen_source": True,
        }
    return {
        "source": {
            "shape": list(source.shape),
            "dtype": str(source.dtype),
            "sha256": source_hash,
        },
        "variants": rows,
        "all_variants_byte_identical": True,
        "clipped_rows": 0,
        "post_policy_transform": None,
        "ik_correction": None,
        "corrective_suffix": None,
        "assistance_used": False,
    }


def _trace_summary(rows: list[dict[str, Any]], variant: str) -> dict[str, float]:
    errors = np.asarray(
        [row[variant]["end_effector_error_m"] for row in rows], dtype=np.float64
    )
    source_encoder = np.asarray(
        [row[variant]["mapped_encoder_to_source_neck_m"] for row in rows]
    )
    source_sim = np.asarray(
        [row[variant]["command_sim_to_source_neck_m"] for row in rows]
    )
    destination_encoder = np.asarray(
        [row[variant]["mapped_encoder_to_destination_neck_m"] for row in rows]
    )
    destination_sim = np.asarray(
        [row[variant]["command_sim_to_destination_neck_m"] for row in rows]
    )
    return {
        "time_aligned_end_effector_rms_m": float(np.sqrt(np.mean(errors**2))),
        "time_aligned_end_effector_mean_m": float(np.mean(errors)),
        "time_aligned_end_effector_max_m": float(np.max(errors)),
        "mapped_encoder_minimum_source_neck_distance_m": float(np.min(source_encoder)),
        "command_sim_minimum_source_neck_distance_m": float(np.min(source_sim)),
        "mapped_encoder_minimum_destination_neck_distance_m": float(
            np.min(destination_encoder)
        ),
        "command_sim_minimum_destination_neck_distance_m": float(np.min(destination_sim)),
    }


def _draw_plot(
    path: Path,
    *,
    title: str,
    series: list[tuple[str, Iterable[float], str]],
    y_label: str,
    event_indices: tuple[int, int],
) -> None:
    width, height = 1200, 650
    left, top, right, bottom = 90, 70, 40, 85
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.text((left, 20), title, fill="black")
    draw.text((10, top), y_label, fill="black")
    values = [np.asarray(list(items), dtype=np.float64) for _, items, _ in series]
    count = max(len(items) for items in values)
    y_min = min(float(np.min(items)) for items in values)
    y_max = max(float(np.max(items)) for items in values)
    if math.isclose(y_min, y_max):
        y_max = y_min + 1.0

    def xy(index: int, value: float) -> tuple[float, float]:
        x = left + index / max(1, count - 1) * (width - left - right)
        y = top + (y_max - value) / (y_max - y_min) * (height - top - bottom)
        return x, y

    draw.line((left, top, left, height - bottom), fill="black", width=2)
    draw.line((left, height - bottom, width - right, height - bottom), fill="black", width=2)
    for event_index in event_indices:
        x, _ = xy(event_index, y_min)
        draw.line((x, top, x, height - bottom), fill="#bbbbbb", width=2)
    legend_y = 45
    for (label, _, color), items in zip(series, values, strict=True):
        points = [xy(index, float(value)) for index, value in enumerate(items)]
        if len(points) > 1:
            draw.line(points, fill=color, width=3)
        draw.line((left + 500, legend_y + 6, left + 535, legend_y + 6), fill=color, width=3)
        draw.text((left + 545, legend_y), label, fill="black")
        legend_y += 20
    draw.text((left, height - 40), "sample index", fill="black")
    draw.text((left, height - bottom + 8), f"min={y_min:.4f}", fill="black")
    draw.text((left, top - 18), f"max={y_max:.4f}", fill="black")
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def _draw_xy_path(
    path: Path,
    *,
    title: str,
    paths: list[tuple[str, np.ndarray, str]],
    targets: list[tuple[str, np.ndarray, str]],
) -> None:
    width, height = 900, 800
    left, top, right, bottom = 80, 65, 40, 70
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    draw.text((left, 20), title, fill="black")
    all_points = [points[:, :2] for _, points, _ in paths] + [
        point[None, :2] for _, point, _ in targets
    ]
    joined = np.concatenate(all_points, axis=0)
    xy_min = np.min(joined, axis=0) - 0.01
    xy_max = np.max(joined, axis=0) + 0.01

    def pixel(point: np.ndarray) -> tuple[float, float]:
        x = left + (point[0] - xy_min[0]) / max(1e-12, xy_max[0] - xy_min[0]) * (
            width - left - right
        )
        y = top + (xy_max[1] - point[1]) / max(1e-12, xy_max[1] - xy_min[1]) * (
            height - top - bottom
        )
        return float(x), float(y)

    draw.rectangle((left, top, width - right, height - bottom), outline="black", width=2)
    legend_y = 45
    for label, points, color in paths:
        pixels = [pixel(point) for point in points]
        if len(pixels) > 1:
            draw.line(pixels, fill=color, width=3)
        draw.line((left + 420, legend_y + 6, left + 450, legend_y + 6), fill=color, width=3)
        draw.text((left + 460, legend_y), label, fill="black")
        legend_y += 20
    for label, point, color in targets:
        x, y = pixel(point)
        draw.ellipse((x - 7, y - 7, x + 7, y + 7), outline=color, width=3)
        draw.text((x + 9, y - 8), label, fill=color)
    draw.text((left, height - 35), "table-frame x/y path (m)", fill="black")
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def _replay_recorded_episode(
    *,
    output_root: Path,
    episode: dict[str, Any],
    source: str,
    destination: str,
    samples: list[dict[str, Any]],
    stage_d: WorkcellCandidate,
    geometry: WorkcellCandidate,
    neck: float,
) -> dict[str, Any]:
    """Replay one mapped action matrix unchanged in both simulator variants."""

    variants = {"stage_d": stage_d, "geometry_only": geometry}
    bindings = {name: build_workcell_model(candidate) for name, candidate in variants.items()}
    baseline_bounds = bindings["stage_d"]["actuator_bounds"]
    if not np.array_equal(baseline_bounds, bindings["geometry_only"]["actuator_bounds"]):
        raise WorkcellFitError("geometry candidate changed actuator bounds")
    adapter = stage_d.adapter()
    actions = np.ascontiguousarray(
        np.asarray(
            [
                physical_values_to_sim_with_adapter(
                    sample["follower_command_degrees"], baseline_bounds[-1], adapter
                )
                for sample in samples
            ],
            dtype=np.float64,
        )
    )
    mapped_actual = np.ascontiguousarray(
        np.asarray(
            [
                physical_values_to_sim_with_adapter(
                    sample["follower_actual_position_degrees"], baseline_bounds[-1], adapter
                )
                for sample in samples
            ],
            dtype=np.float64,
        )
    )
    if np.any(actions < baseline_bounds[:, 0]) or np.any(actions > baseline_bounds[:, 1]):
        raise WorkcellFitError("recorded action stream would require clipping")
    action_receipt = _assert_same_actions(
        actions, {name: actions for name in variants}
    )

    actual_binding = build_workcell_model(stage_d)
    actual_points: list[np.ndarray] = []
    for state in mapped_actual:
        actual_binding["data"].qpos[actual_binding["qpos_addresses"]] = state
        mujoco.mj_forward(actual_binding["model"], actual_binding["data"])
        actual_points.append(_point(actual_binding))
    actual_matrix = np.asarray(actual_points, dtype=np.float64)

    for name, binding in bindings.items():
        variant = variants[name]
        selected_name = BASELINE_PIECE_BY_FILE[source[0]]
        selected_joint = mujoco.mj_name2id(
            binding["model"],
            mujoco.mjtObj.mjOBJ_JOINT,
            f"{selected_name}_free",
        )
        if selected_joint < 0:
            raise WorkcellFitError("recorded replay is missing the selected pawn joint")
        selected_qpos = int(binding["model"].jnt_qposadr[selected_joint])
        selected_dof = int(binding["model"].jnt_dofadr[selected_joint])
        binding["data"].qpos[selected_qpos : selected_qpos + 3] = np.asarray(
            _workcell_square_center(
                source,
                board_center_in_table_frame_xy_m=variant.board_center_in_table_frame_xy_m,
                board_yaw_relative_to_table_degrees=variant.board_yaw_relative_to_table_degrees,
                board_side_m=variant.board_side_m,
            )
        )
        binding["data"].qvel[selected_dof : selected_dof + 6] = 0.0
        binding["data"].qpos[binding["qpos_addresses"]] = mapped_actual[0]
        binding["data"].ctrl[binding["actuator_ids"]] = mapped_actual[0]
        mujoco.mj_forward(binding["model"], binding["data"])
        mujoco.mj_step(binding["model"], binding["data"], nstep=100)

    targets = {
        name: {
            "source": _target(candidate, source, neck),
            "destination": _target(candidate, destination, neck),
        }
        for name, candidate in variants.items()
    }
    source_fit = load_source_fit_contract()
    open_index, source_index, destination_index = extract_phase_indices(samples, source_fit)
    phases = _phase_labels(len(samples), open_index, source_index, destination_index)
    first_timestamp = float(samples[0]["timestamp_monotonic_seconds"])
    previous_timestamp: float | None = None
    nominal_dt = 1.0 / max(1, int(episode["sample_hz"]))
    sim_points: dict[str, list[np.ndarray]] = {name: [] for name in variants}
    rows: list[dict[str, Any]] = []
    for index, (sample, action) in enumerate(zip(samples, actions, strict=True)):
        timestamp = float(sample["timestamp_monotonic_seconds"])
        dt = nominal_dt if previous_timestamp is None else timestamp - previous_timestamp
        if not math.isfinite(dt) or dt <= 0.0 or dt > 1.0:
            dt = nominal_dt
        previous_timestamp = timestamp
        row: dict[str, Any] = {
            "sample_index": index,
            "timestamp_monotonic_seconds": timestamp,
            "elapsed_seconds": timestamp - first_timestamp,
            "phase": phases[index],
            "applied_action": action.tolist(),
            "physical_requested_joint_degrees": list(sample["follower_requested_degrees"]),
            "physical_commanded_joint_degrees": list(sample["follower_command_degrees"]),
            "physical_measured_joint_degrees": list(
                sample["follower_actual_position_degrees"]
            ),
            "physical_measured_velocity_degrees_s": list(
                sample["follower_actual_velocity_degrees_s"]
            ),
            "physical_motor_current_raw": sample["available_motor_current_raw"],
            "mapped_encoder_joint_state": mapped_actual[index].tolist(),
            "mapped_encoder_end_effector_xyz_m": actual_matrix[index].tolist(),
        }
        for name, binding in bindings.items():
            binding["data"].ctrl[binding["actuator_ids"]] = action
            mujoco.mj_step(
                binding["model"],
                binding["data"],
                nstep=max(1, round(dt / float(binding["model"].opt.timestep))),
            )
            point = _point(binding)
            sim_points[name].append(point)
            row[name] = {
                "command_sim_joint_state": np.asarray(
                    binding["data"].qpos[binding["qpos_addresses"]], dtype=np.float64
                ).tolist(),
                "command_sim_end_effector_xyz_m": point.tolist(),
                "end_effector_error_m": float(np.linalg.norm(point - actual_matrix[index])),
                "mapped_encoder_to_source_neck_m": float(
                    np.linalg.norm(actual_matrix[index] - targets[name]["source"])
                ),
                "command_sim_to_source_neck_m": float(
                    np.linalg.norm(point - targets[name]["source"])
                ),
                "mapped_encoder_to_destination_neck_m": float(
                    np.linalg.norm(actual_matrix[index] - targets[name]["destination"])
                ),
                "command_sim_to_destination_neck_m": float(
                    np.linalg.norm(point - targets[name]["destination"])
                ),
            }
        rows.append(row)

    trace_path = output_root / "recorded_traces" / f"{episode['recording_id']}.json"
    trace_artifact = {
        "schema_version": "sim2claw.pawn_bg_action_frozen_recorded_trace.v1",
        "recording_id": episode["recording_id"],
        "folder_label": episode["folder_label"],
        "skill_id": f"pawn_{source}_to_{destination}",
        "event_indices": {
            "source_open": open_index,
            "source_near_close": source_index,
            "destination_reopen": destination_index,
        },
        "action_invariance": action_receipt,
        "targets": {
            name: {key: value.tolist() for key, value in target.items()}
            for name, target in targets.items()
        },
        "rows": rows,
    }
    atomic_write_json(trace_path, trace_artifact)
    visual_root = output_root / "visuals" / episode["recording_id"]
    distance_path = visual_root / "relative_distance_overlay.png"
    _draw_plot(
        distance_path,
        title=f"{episode['folder_label']}: end effector to source target",
        y_label="distance (m)",
        series=[
            (
                "mapped encoder / Stage-D target",
                [row["stage_d"]["mapped_encoder_to_source_neck_m"] for row in rows],
                "#1f77b4",
            ),
            (
                "sim / Stage-D target",
                [row["stage_d"]["command_sim_to_source_neck_m"] for row in rows],
                "#ff7f0e",
            ),
            (
                "mapped encoder / geometry target",
                [
                    row["geometry_only"]["mapped_encoder_to_source_neck_m"]
                    for row in rows
                ],
                "#2ca02c",
            ),
            (
                "sim / geometry target",
                [row["geometry_only"]["command_sim_to_source_neck_m"] for row in rows],
                "#d62728",
            ),
        ],
        event_indices=(source_index, destination_index),
    )
    xy_path = visual_root / "end_effector_xy_path.png"
    _draw_xy_path(
        xy_path,
        title=f"{episode['folder_label']}: time-aligned end-effector path",
        paths=[
            ("mapped encoder", actual_matrix, "#1f77b4"),
            ("Stage-D sim", np.asarray(sim_points["stage_d"]), "#ff7f0e"),
            ("geometry-only sim", np.asarray(sim_points["geometry_only"]), "#2ca02c"),
        ],
        targets=[
            ("D source", targets["stage_d"]["source"], "#ff7f0e"),
            ("G source", targets["geometry_only"]["source"], "#2ca02c"),
            ("G destination", targets["geometry_only"]["destination"], "#d62728"),
        ],
    )
    return {
        "recording_id": episode["recording_id"],
        "folder_label": episode["folder_label"],
        "skill_id": f"pawn_{source}_to_{destination}",
        "sample_count": len(samples),
        "action_invariance": action_receipt,
        "stage_d": _trace_summary(rows, "stage_d"),
        "geometry_only": _trace_summary(rows, "geometry_only"),
        "trace_path": str(trace_path.resolve()),
        "trace_sha256": sha256_file(trace_path),
        "relative_distance_overlay_png": str(distance_path.resolve()),
        "relative_distance_overlay_sha256": sha256_file(distance_path),
        "end_effector_xy_path_png": str(xy_path.resolve()),
        "end_effector_xy_path_sha256": sha256_file(xy_path),
    }


def _pooled_trace_summary(episodes: list[dict[str, Any]], variant: str) -> dict[str, Any]:
    weights = np.asarray([episode["sample_count"] for episode in episodes], dtype=np.float64)
    rms = np.asarray(
        [episode[variant]["time_aligned_end_effector_rms_m"] for episode in episodes]
    )
    return {
        "episode_count": len(episodes),
        "sample_count": int(np.sum(weights)),
        "pooled_time_aligned_end_effector_rms_m": float(
            np.sqrt(np.sum(weights * rms**2) / np.sum(weights))
        ),
        "mean_episode_minimum_mapped_encoder_source_neck_distance_m": float(
            np.mean(
                [
                    episode[variant]["mapped_encoder_minimum_source_neck_distance_m"]
                    for episode in episodes
                ]
            )
        ),
        "mean_episode_minimum_command_sim_source_neck_distance_m": float(
            np.mean(
                [
                    episode[variant]["command_sim_minimum_source_neck_distance_m"]
                    for episode in episodes
                ]
            )
        ),
    }


def _event_rows(
    events: list[WorkcellEvent],
    points: np.ndarray,
    baseline_targets: np.ndarray,
    candidate_targets: np.ndarray,
) -> list[dict[str, Any]]:
    rows = []
    for event, point, baseline, candidate in zip(
        events, points, baseline_targets, candidate_targets, strict=True
    ):
        rows.append(
            {
                "recording_id": event.recording_id,
                "skill_id": event.skill_id,
                "phase": event.phase,
                "sample_index": event.sample_index,
                "mapped_encoder_end_effector_xyz_m": point.tolist(),
                "stage_d_target_xyz_m": baseline.tolist(),
                "stage_d_distance_m": float(np.linalg.norm(point - baseline)),
                "geometry_only_target_xyz_m": candidate.tolist(),
                "geometry_only_distance_m": float(np.linalg.norm(point - candidate)),
            }
        )
    return rows


def run_action_frozen_gap_fit(
    *, source_repository_root: Path, output_root: Path
) -> dict[str, Any]:
    """Fit geometry and materialize byte-identical recorded-action replays."""

    contract = load_action_frozen_contract()
    train, events = _load_partition(source_repository_root, "train")
    if len(train) != 11 or len(events) != 22:
        raise WorkcellFitError("action-frozen fit requires 11 train episodes and 22 events")
    parent, stage_d, stage_d_parameters, _ = _reconstruct_stage_d(train, events)
    geometry, geometry_parameters, geometry_metrics, details = _fit_geometry_only(
        contract=contract,
        parent=parent,
        events=events,
        stage_d=stage_d,
        stage_d_parameters=stage_d_parameters,
    )
    baseline_metrics = details["baseline_metrics"]
    reduction = (
        baseline_metrics["event_rms_distance_m"]
        - geometry_metrics["event_rms_distance_m"]
    ) / baseline_metrics["event_rms_distance_m"]
    threshold = float(
        contract["geometry_candidate"]["minimum_train_event_rms_relative_reduction"]
    )
    neck = float(parent["fit"]["estimated_pawn_neck_height_m"])
    episode_rows = [
        _replay_recorded_episode(
            output_root=output_root,
            episode=episode,
            source=source,
            destination=destination,
            samples=samples,
            stage_d=stage_d,
            geometry=geometry,
            neck=neck,
        )
        for episode, source, destination, samples in train
    ]
    adapter_unchanged = (
        stage_d.adapter().sha256
        == geometry.adapter().sha256
        == geometry_parameters["frozen_action_adapter_sha256"]
    )
    if not adapter_unchanged:
        raise WorkcellFitError("geometry candidate changed the action adapter")
    all_action_invariant = all(
        row["action_invariance"]["all_variants_byte_identical"] for row in episode_rows
    )
    if not all_action_invariant:
        raise WorkcellFitError("recorded action invariance failed")
    accepted = bool(reduction >= threshold and adapter_unchanged and all_action_invariant)
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "proof_class": "recorded_action_frozen_open_loop_simulator_gap_diagnostic",
        "implementation": {
            "path": str(IMPLEMENTATION_PATH.relative_to(REPO_ROOT)),
            "sha256": sha256_file(IMPLEMENTATION_PATH),
        },
        "contract_sha256": sha256_file(CONTRACT_PATH),
        "catalog_sha256": sha256_file(CATALOG_PATH),
        "split_sha256": sha256_file(SPLIT_PATH),
        "calibration_sha256": sha256_file(CALIBRATION_PATH),
        "train_episode_count": len(train),
        "train_event_count": len(events),
        "action_invariance_contract": contract["action_invariance"],
        "frozen_adapter": stage_d.adapter().receipt(),
        "frozen_adapter_identical_for_all_variants": adapter_unchanged,
        "stage_d": {
            "parameters": stage_d_parameters,
            "event_metrics": baseline_metrics,
            "trace_summary": _pooled_trace_summary(episode_rows, "stage_d"),
        },
        "geometry_only": {
            "parameters": geometry_parameters,
            "event_metrics": geometry_metrics,
            "trace_summary": _pooled_trace_summary(episode_rows, "geometry_only"),
            "optimizer": details["optimizer"],
        },
        "event_audit": _event_rows(
            events,
            details["points"],
            details["baseline_targets"],
            details["candidate_targets"],
        ),
        "recorded_action_replays": episode_rows,
        "train_acceptance": {
            "event_rms_relative_reduction": reduction,
            "minimum_required": threshold,
            "event_rms_gate": reduction >= threshold,
            "frozen_adapter_gate": adapter_unchanged,
            "byte_identical_action_gate": all_action_invariant,
            "accepted_as_geometry_diagnostic": accepted,
        },
        "selected_simulator_candidate": (
            "geometry_only_board_pitch" if accepted else "stage_d"
        ),
        "held_out_used_for_selection": False,
        "excluded_prior_evidence": contract["excluded_evidence"],
        "authority": contract["authority"],
        "claim_boundary": (
            "The candidate changes simulator board geometry only. Every recorded action "
            "array is byte-identical across variants. The result is an open-loop "
            "diagnostic, not a repaired policy, new policy evaluation, or physical proof."
        ),
    }
    receipt = {**unsigned, "receipt_sha256": canonical_digest(unsigned)}
    atomic_write_json(output_root / "train_fit.json", receipt)
    return receipt


def _candidate_from_parameters(parameters: dict[str, Any]) -> WorkcellCandidate:
    return WorkcellCandidate(
        board_yaw_relative_to_table_degrees=float(
            parameters["board_yaw_relative_to_table_degrees"]
        ),
        board_center_in_table_frame_xy_m=tuple(
            float(value) for value in parameters["board_center_in_table_frame_xy_m"]
        ),
        joint_zero_offsets_rad=tuple(
            float(value) for value in parameters["joint_zero_offsets_rad"]
        ),
        joint_range_envelope_rad=tuple(
            (float(low), float(high))
            for low, high in parameters["joint_range_envelope_rad"]
        ),
        board_side_m=(
            float(parameters["board_side_m"])
            if parameters.get("board_side_m") is not None
            else None
        ),
    )


def run_action_frozen_confirmation(
    *, source_repository_root: Path, fit_receipt_path: Path, output_root: Path
) -> dict[str, Any]:
    """Apply the already-frozen geometry to the two previously opened episodes."""

    contract = load_action_frozen_contract()
    receipt = json.loads(fit_receipt_path.read_text(encoding="utf-8"))
    if receipt.get("schema_version") != RECEIPT_SCHEMA:
        raise WorkcellFitError("unexpected action-frozen fit receipt schema")
    unsigned_receipt = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    if receipt.get("receipt_sha256") != canonical_digest(unsigned_receipt):
        raise WorkcellFitError("action-frozen fit receipt digest changed")
    held_out, events = _load_partition(source_repository_root, "held_out")
    if len(held_out) != 2 or len(events) != 4:
        raise WorkcellFitError("confirmation requires two already-open episodes")
    stage_d = _candidate_from_parameters(receipt["stage_d"]["parameters"])
    geometry = _candidate_from_parameters(receipt["geometry_only"]["parameters"])
    parent = load_workcell_contract()
    neck = float(parent["fit"]["estimated_pawn_neck_height_m"])
    episode_rows = [
        _replay_recorded_episode(
            output_root=output_root / "confirmation",
            episode=episode,
            source=source,
            destination=destination,
            samples=samples,
            stage_d=stage_d,
            geometry=geometry,
            neck=neck,
        )
        for episode, source, destination, samples in held_out
    ]
    reopen_mask = np.asarray(
        [event.phase == "destination_reopen" for event in events], dtype=bool
    )
    points = _fk_pinch_points(
        build_workcell_model(stage_d),
        events,
        np.asarray(stage_d.joint_zero_offsets_rad),
    )
    comparisons = {}
    for name, candidate, parameters in (
        ("stage_d", stage_d, receipt["stage_d"]["parameters"]),
        ("geometry_only", geometry, receipt["geometry_only"]["parameters"]),
    ):
        targets = _event_targets(
            events,
            candidate.board_center_in_table_frame_xy_m,
            candidate.board_yaw_relative_to_table_degrees,
            neck,
            candidate.board_side_m,
        )
        targets[reopen_mask, 2] += float(parameters["reopen_timing_z_bias_m"])
        comparisons[name] = {
            "event_metrics": _metrics(points, targets),
            "trace_summary": _pooled_trace_summary(episode_rows, name),
        }
    d_rms = comparisons["stage_d"]["event_metrics"]["event_rms_distance_m"]
    g_rms = comparisons["geometry_only"]["event_metrics"]["event_rms_distance_m"]
    unsigned = {
        "schema_version": CONFIRMATION_SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "implementation": {
            "path": str(IMPLEMENTATION_PATH.relative_to(REPO_ROOT)),
            "sha256": sha256_file(IMPLEMENTATION_PATH),
        },
        "fit_receipt_sha256": sha256_file(fit_receipt_path),
        "confirmation_policy": contract["confirmation"],
        "episode_count": len(held_out),
        "event_count": len(events),
        "comparisons": comparisons,
        "geometry_event_rms_relative_reduction": (d_rms - g_rms) / d_rms,
        "recorded_action_replays": episode_rows,
        "all_actions_byte_identical": all(
            row["action_invariance"]["all_variants_byte_identical"]
            for row in episode_rows
        ),
        "selection_changed_from_confirmation": False,
        "authority": contract["authority"],
        "claim_boundary": (
            "These episodes were already opened before this fit. They are transparent "
            "post-selection confirmation and cannot tune or select the candidate."
        ),
    }
    result = {**unsigned, "confirmation_sha256": canonical_digest(unsigned)}
    atomic_write_json(output_root / "confirmation.json", result)
    return result


def _policy_binding(candidate: WorkcellCandidate, source: str, initial_state: np.ndarray) -> dict[str, Any]:
    binding = build_workcell_model(candidate)
    model, data = binding["model"], binding["data"]
    selected_name = BASELINE_PIECE_BY_FILE[source[0]]
    selected_body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, selected_name)
    selected_joint = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_JOINT, f"{selected_name}_free"
    )
    selected_qpos = int(model.jnt_qposadr[selected_joint])
    selected_dof = int(model.jnt_dofadr[selected_joint])
    data.qpos[selected_qpos : selected_qpos + 3] = np.asarray(
        _workcell_square_center(
            source,
            board_center_in_table_frame_xy_m=candidate.board_center_in_table_frame_xy_m,
            board_yaw_relative_to_table_degrees=candidate.board_yaw_relative_to_table_degrees,
            board_side_m=candidate.board_side_m,
        )
    )
    data.qvel[selected_dof : selected_dof + 6] = 0.0
    data.qpos[binding["qpos_addresses"]] = initial_state
    data.ctrl[binding["actuator_ids"]] = initial_state
    mujoco.mj_forward(model, data)
    mujoco.mj_step(model, data, nstep=100)
    piece_bodies = _piece_bodies(model)
    initial_positions = {
        name: np.asarray(data.xpos[body_id], dtype=np.float64).copy()
        for name, body_id in piece_bodies.items()
    }
    robot_bodies = {
        body_id
        for body_id in range(model.nbody)
        if (mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id) or "").startswith(
            "left_"
        )
    }
    fixed_geom = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_GEOM, "left_fixed_jaw_box1"
    )
    jaw_bodies = {
        int(model.geom_bodyid[fixed_geom]),
        mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_BODY, "left_moving_jaw_so101_v1"
        ),
    }
    binding.update(
        {
            "selected_body": selected_body,
            "selected_dof": selected_dof,
            "piece_bodies": piece_bodies,
            "initial_positions": initial_positions,
            "robot_bodies": robot_bodies,
            "jaw_bodies": jaw_bodies,
            "initial_height": float(data.xpos[selected_body][2]),
        }
    )
    return binding


def _policy_trace_row(binding: dict[str, Any]) -> dict[str, Any]:
    return _trace_row(
        binding["model"],
        binding["data"],
        selected_body=binding["selected_body"],
        selected_dof=binding["selected_dof"],
        piece_bodies=binding["piece_bodies"],
        initial_piece_positions=binding["initial_positions"],
        robot_body_ids=binding["robot_bodies"],
        jaw_body_ids=binding["jaw_bodies"],
    )


def run_frozen_policy_action_replay(
    *, fit_receipt_path: Path, policy_root: Path, output_root: Path
) -> dict[str, Any]:
    """Replay retained model actions unchanged; do not invoke the policy."""

    contract = load_action_frozen_contract()
    policy_contract = contract["retained_unassisted_policy_actions"]
    report_path = policy_root / policy_contract["report_relative_to_policy_root"]
    if sha256_file(report_path) != policy_contract["report_sha256"]:
        raise WorkcellFitError("retained unassisted policy report changed")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    results = report.get("results")
    if not isinstance(results, list) or len(results) != int(
        policy_contract["required_case_count"]
    ):
        raise WorkcellFitError("retained policy case count changed")
    receipt = json.loads(fit_receipt_path.read_text(encoding="utf-8"))
    if receipt.get("schema_version") != RECEIPT_SCHEMA:
        raise WorkcellFitError("policy replay requires an action-frozen fit receipt")
    geometry = _candidate_from_parameters(receipt["geometry_only"]["parameters"])
    parent_fit = load_workcell_contract()["fit"]
    pawn_neck_height_m = float(parent_fit["estimated_pawn_neck_height_m"])
    baseline = WorkcellCandidate(
        board_yaw_relative_to_table_degrees=float(
            parent_fit["frozen_board_yaw_relative_to_table_degrees"]
        ),
        board_center_in_table_frame_xy_m=tuple(
            float(value) for value in parent_fit["frozen_board_center_in_table_frame_xy_m"]
        ),
        joint_zero_offsets_rad=(0.0,) * 5,
        joint_range_envelope_rad=tuple((0.0, 0.0) for _ in range(5)),
    )
    geometry_policy = WorkcellCandidate(
        board_yaw_relative_to_table_degrees=geometry.board_yaw_relative_to_table_degrees,
        board_center_in_table_frame_xy_m=geometry.board_center_in_table_frame_xy_m,
        joint_zero_offsets_rad=(0.0,) * 5,
        joint_range_envelope_rad=tuple((0.0, 0.0) for _ in range(5)),
        board_side_m=geometry.board_side_m,
    )
    reward = load_reward_contract()
    case_rows = []
    for index, result in enumerate(results):
        skill_id = str(result["skill_id"])
        source = str(result["source_square"])
        destination = str(result["destination_square"])
        if result.get("assistance_used_for_frozen_policy_score") is not False:
            raise WorkcellFitError("assisted policy evidence is excluded")
        if int(result.get("action_rows_clipped", -1)) != int(
            policy_contract["required_action_rows_clipped"]
        ):
            raise WorkcellFitError("retained policy actions were clipped")
        case_dir = report_path.parent / f"{index:02d}-{skill_id}"
        with np.load(case_dir / "rollout.npz") as rollout:
            actions = np.ascontiguousarray(rollout["applied_actions"])
            states = np.ascontiguousarray(rollout["states"])
        required_shape = (
            int(policy_contract["required_action_rows_per_case"]),
            int(policy_contract["required_action_columns"]),
        )
        if actions.shape != required_shape or actions.dtype != np.float64:
            raise WorkcellFitError("retained applied-action array identity changed")
        action_hash = _array_sha256(actions)
        if action_hash != result["applied_actions_sha256"]:
            raise WorkcellFitError("retained applied-action hash changed")
        if states.shape != required_shape or not np.isfinite(states).all():
            raise WorkcellFitError("retained policy state array identity changed")
        variants = {
            "frozen_original_geometry": baseline,
            "geometry_only": geometry_policy,
        }
        action_receipt = _assert_same_actions(
            actions, {name: actions for name in variants}
        )
        bindings = {
            name: _policy_binding(candidate, source, states[0].astype(np.float64))
            for name, candidate in variants.items()
        }
        for name, binding in bindings.items():
            bounds = binding["actuator_bounds"]
            if np.any(actions < bounds[:, 0]) or np.any(actions > bounds[:, 1]):
                raise WorkcellFitError(f"{name} would clip frozen policy actions")
        traces = {name: [_policy_trace_row(binding)] for name, binding in bindings.items()}
        ee_paths = {name: [_point(binding)] for name, binding in bindings.items()}
        for action in actions:
            for name, binding in bindings.items():
                binding["data"].ctrl[binding["actuator_ids"]] = action
                mujoco.mj_step(binding["model"], binding["data"], nstep=10)
                traces[name].append(_policy_trace_row(binding))
                ee_paths[name].append(_point(binding))
        for name, binding in bindings.items():
            mujoco.mj_step(binding["model"], binding["data"], nstep=200)
            traces[name].append(_policy_trace_row(binding))
        scores = {}
        for name, candidate in variants.items():
            target = _workcell_square_center(
                destination,
                board_center_in_table_frame_xy_m=candidate.board_center_in_table_frame_xy_m,
                board_yaw_relative_to_table_degrees=candidate.board_yaw_relative_to_table_degrees,
                board_side_m=candidate.board_side_m,
            )
            score = score_episode(
                reward,
                skill_id=skill_id,
                trace=traces[name],
                target_position_xyz_m=target,
                initial_piece_height_m=bindings[name]["initial_height"],
                evaluation_mode="source_demonstration_replay",
                action_owner="retained_model_open_loop_actions",
                assistance_used=False,
            )
            square_side = (
                candidate.board_side_m / 8.0
                if candidate.board_side_m is not None
                else float(reward["scene_binding"]["square_side_m"])
            )
            scores[name] = {
                "task_consequence_success": bool(score["task_consequence_success"]),
                "selected_piece_contact_observed": bool(
                    score["gate_results"]["selected_piece_contact_observed"]
                ),
                "piece_lifted": bool(score["gate_results"]["piece_lifted"]),
                "maximum_piece_rise_m": float(score["maximum_piece_rise_m"]),
                "final_center_distance_m": float(score["final_center_distance_m"]),
                "final_center_distance_in_square_sides": float(
                    score["final_center_distance_m"] / square_side
                ),
                "diagnostic_reward": float(score["diagnostic_reward"]),
                "minimum_end_effector_to_source_neck_m": float(
                    np.min(
                        np.linalg.norm(
                            np.asarray(ee_paths[name])
                            - _target(candidate, source, pawn_neck_height_m),
                            axis=1,
                        )
                    )
                ),
            }
        case_rows.append(
            {
                "case_index": index,
                "skill_id": skill_id,
                "source_square": source,
                "destination_square": destination,
                "action_invariance": action_receipt,
                "scores": scores,
            }
        )

    def aggregate(name: str) -> dict[str, Any]:
        return {
            "case_count": len(case_rows),
            "task_consequence_successes": sum(
                int(row["scores"][name]["task_consequence_success"]) for row in case_rows
            ),
            "contact_cases": sum(
                int(row["scores"][name]["selected_piece_contact_observed"])
                for row in case_rows
            ),
            "lift_cases": sum(
                int(row["scores"][name]["piece_lifted"]) for row in case_rows
            ),
            "mean_final_center_distance_in_square_sides": float(
                np.mean(
                    [
                        row["scores"][name]["final_center_distance_in_square_sides"]
                        for row in case_rows
                    ]
                )
            ),
            "mean_minimum_end_effector_to_source_neck_m": float(
                np.mean(
                    [
                        row["scores"][name]["minimum_end_effector_to_source_neck_m"]
                        for row in case_rows
                    ]
                )
            ),
        }

    unsigned = {
        "schema_version": POLICY_SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "proof_class": "retained_model_action_frozen_open_loop_simulator_diagnostic",
        "implementation": {
            "path": str(IMPLEMENTATION_PATH.relative_to(REPO_ROOT)),
            "sha256": sha256_file(IMPLEMENTATION_PATH),
        },
        "fit_receipt_sha256": sha256_file(fit_receipt_path),
        "retained_policy_report_path": str(report_path.resolve()),
        "retained_policy_report_sha256": sha256_file(report_path),
        "policy_invoked": False,
        "policy_checkpoint_or_code_changed": False,
        "action_adapter_applied": False,
        "post_policy_transform_applied": False,
        "case_count": len(case_rows),
        "all_actions_byte_identical": all(
            row["action_invariance"]["all_variants_byte_identical"] for row in case_rows
        ),
        "comparisons": {
            "frozen_original_geometry": aggregate("frozen_original_geometry"),
            "geometry_only": aggregate("geometry_only"),
        },
        "cases": case_rows,
        "authority": contract["authority"],
        "claim_boundary": (
            "This is open-loop replay of retained model-produced action arrays. The policy "
            "was not invoked, and no action was transformed. It cannot report a new "
            "closed-loop policy result or physical transfer."
        ),
    }
    replay = {**unsigned, "replay_sha256": canonical_digest(unsigned)}
    atomic_write_json(output_root / "policy_action_replay.json", replay)
    return replay


__all__ = [
    "CONTRACT_PATH",
    "load_action_frozen_contract",
    "run_action_frozen_gap_fit",
    "run_action_frozen_confirmation",
    "run_frozen_policy_action_replay",
]
