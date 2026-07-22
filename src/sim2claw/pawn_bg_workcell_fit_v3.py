"""Train-derived Stage-F board-pitch fit and already-open confirmation."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import mujoco
from scipy.optimize import least_squares

from .learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .paths import REPO_ROOT
from .grasp import _pinch_point
from .pawn_bg_demo_sim import physical_values_to_sim_with_adapter
from .pawn_bg_source_fit import load_source_fit_contract
from .pawn_bg_workcell_fit import (
    BODY_JOINT_NAMES,
    CALIBRATION_PATH,
    CATALOG_PATH,
    FITTED_OFFSET_JOINTS,
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
    replay_episode_with_candidate,
)
from .pawn_bg_workcell_fit_v2 import _candidate_from_parameters, _metrics, _summarize_replays
from .pawn_bg_reward import load_reward_contract


CONTRACT_PATH = REPO_ROOT / "configs" / "optimization" / "pawn_bg_workcell_fit_v3.json"
SCHEMA = "sim2claw.pawn_bg_workcell_fit.v3"


def load_workcell_v3_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    contract = json.loads(path.read_text(encoding="utf-8"))
    if contract.get("schema_version") != SCHEMA:
        raise WorkcellFitError("unexpected Stage-F workcell contract schema")
    authority = contract.get("authority")
    if not isinstance(authority, dict) or not authority or any(authority.values()):
        raise WorkcellFitError("Stage-F authority widened")
    parent = contract["parent_contract"]
    parent_path = (REPO_ROOT / parent["path"]).resolve()
    if sha256_file(parent_path) != parent["sha256"]:
        raise WorkcellFitError("Stage-F parent contract changed")
    lower, upper = (float(value) for value in contract["candidate"]["playing_side_bounds_m"])
    frozen = float(contract["candidate"]["frozen_playing_side_m"])
    if not 0.0 < lower < frozen < upper:
        raise WorkcellFitError("invalid Stage-F board-side bounds")
    return contract


def _event_audit_rows(
    events: list[WorkcellEvent], points: np.ndarray, targets: np.ndarray
) -> list[dict[str, Any]]:
    rows = []
    for event, point, target in zip(events, points, targets, strict=True):
        residual = point - target
        rows.append(
            {
                "recording_id": event.recording_id,
                "skill_id": event.skill_id,
                "phase": event.phase,
                "square": event.square,
                "sample_index": event.sample_index,
                "predicted_pinch_xyz_m": point.astype(float).tolist(),
                "target_xyz_m": target.astype(float).tolist(),
                "residual_xyz_m": residual.astype(float).tolist(),
                "distance_m": float(np.linalg.norm(residual)),
            }
        )
    return rows


def _load_partition(
    source_repository_root: Path, split_name: str
) -> tuple[list[tuple[dict[str, Any], str, str, list[dict[str, Any]]]], list[WorkcellEvent]]:
    membership = _split_membership()
    payloads = _episode_payloads(source_repository_root, membership, split_name)
    source_fit = load_source_fit_contract()
    events = [
        event
        for episode, source, destination, samples in payloads
        for event in _extract_events(episode, source, destination, samples, source_fit)
    ]
    return payloads, events


def _source_approach_trace_probe(
    *,
    candidate: WorkcellCandidate,
    episode: dict[str, Any],
    source: str,
    samples: list[dict[str, Any]],
    neck_height_m: float,
) -> dict[str, Any]:
    """Compare mapped encoder FK with command-driven simulator FK at source approach."""

    actual_binding = build_workcell_model(candidate)
    simulated_binding = build_workcell_model(candidate)
    adapter = candidate.adapter()
    target = np.asarray(
        _workcell_square_center(
            source,
            board_center_in_table_frame_xy_m=candidate.board_center_in_table_frame_xy_m,
            board_yaw_relative_to_table_degrees=candidate.board_yaw_relative_to_table_degrees,
            board_side_m=candidate.board_side_m,
        ),
        dtype=np.float64,
    )
    target[2] += float(neck_height_m)

    actual_distances: list[float] = []
    actual_states: list[np.ndarray] = []
    actual_model, actual_data = actual_binding["model"], actual_binding["data"]
    for sample in samples:
        state = physical_values_to_sim_with_adapter(
            sample["follower_actual_position_degrees"],
            actual_binding["actuator_bounds"][-1],
            adapter,
        )
        actual_data.qpos[actual_binding["qpos_addresses"]] = state
        mujoco.mj_forward(actual_model, actual_data)
        actual_states.append(np.asarray(state, dtype=np.float64))
        actual_distances.append(
            float(
                np.linalg.norm(
                    _pinch_point(
                        actual_model,
                        actual_data,
                        "left",
                        actual_binding["pinch_offset_local"],
                    )
                    - target
                )
            )
        )

    simulated_model, simulated_data = simulated_binding["model"], simulated_binding["data"]
    first_actual = actual_states[0]
    simulated_data.qpos[simulated_binding["qpos_addresses"]] = first_actual
    simulated_data.ctrl[simulated_binding["actuator_ids"]] = first_actual
    mujoco.mj_forward(simulated_model, simulated_data)
    mujoco.mj_step(simulated_model, simulated_data, nstep=100)
    simulated_distances: list[float] = []
    simulated_states: list[np.ndarray] = []
    previous_timestamp: float | None = None
    nominal_dt = 1.0 / max(1, int(episode["sample_hz"]))
    for sample in samples:
        timestamp = float(sample["timestamp_monotonic_seconds"])
        dt = nominal_dt if previous_timestamp is None else timestamp - previous_timestamp
        if not math.isfinite(dt) or dt <= 0.0 or dt > 1.0:
            dt = nominal_dt
        previous_timestamp = timestamp
        command = physical_values_to_sim_with_adapter(
            sample["follower_command_degrees"],
            simulated_binding["actuator_bounds"][-1],
            adapter,
        )
        simulated_data.ctrl[simulated_binding["actuator_ids"]] = command
        mujoco.mj_step(
            simulated_model,
            simulated_data,
            nstep=max(1, round(dt / float(simulated_model.opt.timestep))),
        )
        state = np.asarray(
            simulated_data.qpos[simulated_binding["qpos_addresses"]], dtype=np.float64
        ).copy()
        simulated_states.append(state)
        simulated_distances.append(
            float(
                np.linalg.norm(
                    _pinch_point(
                        simulated_model,
                        simulated_data,
                        "left",
                        simulated_binding["pinch_offset_local"],
                    )
                    - target
                )
            )
        )
    actual_matrix = np.asarray(actual_states)
    simulated_matrix = np.asarray(simulated_states)
    body_error_degrees = np.rad2deg(simulated_matrix[:, :5] - actual_matrix[:, :5])
    return {
        "recording_id": episode["recording_id"],
        "folder_label": episode["folder_label"],
        "source_square": source,
        "target_source_neck_xyz_m": target.tolist(),
        "mapped_encoder_minimum_source_neck_distance_m": float(min(actual_distances)),
        "mapped_encoder_minimum_sample_index": int(np.argmin(actual_distances)),
        "command_sim_minimum_source_neck_distance_m": float(min(simulated_distances)),
        "command_sim_minimum_sample_index": int(np.argmin(simulated_distances)),
        "command_sim_minus_encoder_minimum_distance_m": float(
            min(simulated_distances) - min(actual_distances)
        ),
        "command_sim_minus_mapped_encoder_body_joint_rms_degrees": float(
            np.sqrt(np.mean(body_error_degrees**2))
        ),
        "command_sim_minus_mapped_encoder_body_joint_max_abs_degrees": float(
            np.max(np.abs(body_error_degrees))
        ),
        "sample_count": len(samples),
    }


def _summarize_trace_probes(rows: list[dict[str, Any]]) -> dict[str, Any]:
    encoder = np.asarray(
        [row["mapped_encoder_minimum_source_neck_distance_m"] for row in rows]
    )
    simulated = np.asarray(
        [row["command_sim_minimum_source_neck_distance_m"] for row in rows]
    )
    return {
        "episodes": len(rows),
        "mapped_encoder_mean_minimum_source_neck_distance_m": float(np.mean(encoder)),
        "mapped_encoder_maximum_of_minimum_source_neck_distances_m": float(np.max(encoder)),
        "mapped_encoder_episodes_within_10mm": int(np.sum(encoder <= 0.010)),
        "command_sim_mean_minimum_source_neck_distance_m": float(np.mean(simulated)),
        "command_sim_maximum_of_minimum_source_neck_distances_m": float(np.max(simulated)),
        "command_sim_episodes_within_10mm": int(np.sum(simulated <= 0.010)),
        "mean_command_sim_minus_encoder_minimum_distance_m": float(
            np.mean(simulated - encoder)
        ),
        "pooled_body_joint_tracking_rms_degrees": float(
            np.sqrt(
                np.mean(
                    np.square(
                        [
                            row["command_sim_minus_mapped_encoder_body_joint_rms_degrees"]
                            for row in rows
                        ]
                    )
                )
            )
        ),
    }


def run_workcell_fit_v3(
    *, source_repository_root: Path, output_path: Path
) -> dict[str, Any]:
    """Fit and select board playing-side length using train episodes only."""

    contract = load_workcell_v3_contract()
    parent = load_workcell_contract()
    reward = load_reward_contract()
    train, events = _load_partition(source_repository_root, "train")
    if len(train) != 11 or len(events) != 22:
        raise WorkcellFitError(
            f"expected 11 train episodes and 22 events, found {len(train)} and {len(events)}"
        )
    envelope = measured_range_envelope([samples for _, _, _, samples in train])
    parent_fit = parent["fit"]
    scratch = WorkcellCandidate(
        board_yaw_relative_to_table_degrees=float(
            parent_fit["frozen_board_yaw_relative_to_table_degrees"]
        ),
        board_center_in_table_frame_xy_m=tuple(
            float(value)
            for value in parent_fit["frozen_board_center_in_table_frame_xy_m"]
        ),
        joint_zero_offsets_rad=(0.0,) * 5,
        joint_range_envelope_rad=envelope,
    )
    binding = build_workcell_model(scratch)
    parent_result = fit_candidate(events, binding, parent, envelope)
    stage_d_candidate = parent_result["candidate_lift"]
    stage_d_metrics = dict(parent_result["stage_d_lift_kinematic"])
    stage_d_parameters = dict(parent_result["stage_d_lift_parameters"])

    frozen_center = np.asarray(
        parent_fit["frozen_board_center_in_table_frame_xy_m"], dtype=np.float64
    )
    frozen_yaw = float(parent_fit["frozen_board_yaw_relative_to_table_degrees"])
    relabeled_yaw = frozen_yaw + 180.0
    offset_indices = [BODY_JOINT_NAMES.index(name) for name in FITTED_OFFSET_JOINTS]
    stage_d_offsets = np.asarray(stage_d_candidate.joint_zero_offsets_rad)[offset_indices]
    stage_d_reopen_bias = float(stage_d_parameters["reopen_timing_z_bias_m"])
    candidate_contract = contract["candidate"]
    x0 = np.asarray(
        [
            stage_d_candidate.board_center_in_table_frame_xy_m[0] - frozen_center[0],
            stage_d_candidate.board_center_in_table_frame_xy_m[1] - frozen_center[1],
            stage_d_candidate.board_yaw_relative_to_table_degrees - relabeled_yaw,
            float(candidate_contract["frozen_playing_side_m"]),
            *stage_d_offsets.tolist(),
            stage_d_reopen_bias,
        ],
        dtype=np.float64,
    )
    playing_side_lower, playing_side_upper = (
        float(value) for value in candidate_contract["playing_side_bounds_m"]
    )
    lift_bound = math.radians(float(parent_fit["stage_d_lift_offset_bound_degrees"]))
    other_bound = math.radians(float(parent_fit["joint_zero_offset_bound_degrees"]))
    lift_position = FITTED_OFFSET_JOINTS.index("shoulder_lift")
    lower_offsets = [
        -lift_bound if index == lift_position else -other_bound for index in range(4)
    ]
    upper_offsets = [
        lift_bound if index == lift_position else other_bound for index in range(4)
    ]
    lower = np.asarray(
        [-0.08, -0.08, -15.0, playing_side_lower, *lower_offsets, 0.0],
        dtype=np.float64,
    )
    upper = np.asarray(
        [
            0.08,
            0.08,
            15.0,
            playing_side_upper,
            *upper_offsets,
            float(parent_fit["reopen_timing_z_bound_m"]),
        ],
        dtype=np.float64,
    )
    reopen_mask = np.asarray(
        [event.phase == "destination_reopen" for event in events], dtype=bool
    )
    neck = float(parent_fit["estimated_pawn_neck_height_m"])
    tight_sigma = math.radians(float(parent_fit["stage_d_other_offset_prior_sigma_degrees"]))
    normalizer = math.sqrt(len(events) * 3)
    other_positions = [index for index in range(4) if index != lift_position]

    def residual(parameters: np.ndarray) -> np.ndarray:
        center = tuple((frozen_center + parameters[:2]).tolist())
        yaw = relabeled_yaw + parameters[2]
        board_side = float(parameters[3])
        offsets = np.zeros(5)
        offsets[offset_indices] = parameters[4:8]
        points = _fk_pinch_points(binding, events, offsets)
        targets = _event_targets(events, center, yaw, neck, board_side)
        targets[reopen_mask, 2] += parameters[8]
        data_residual = (points - targets).ravel()
        offset_prior = parameters[4:8][other_positions] / tight_sigma / normalizer
        return np.concatenate([data_residual, offset_prior])

    fit = least_squares(
        residual,
        x0=x0,
        bounds=(lower, upper),
        method="trf",
        diff_step=float(candidate_contract["finite_difference_step"]),
    )
    center = tuple((frozen_center + fit.x[:2]).astype(float).tolist())
    yaw = float(relabeled_yaw + fit.x[2])
    board_side = float(fit.x[3])
    offsets = np.zeros(5)
    offsets[offset_indices] = fit.x[4:8]
    points = _fk_pinch_points(binding, events, offsets)
    targets = _event_targets(events, center, yaw, neck, board_side)
    targets[reopen_mask, 2] += fit.x[8]
    stage_f_metrics = _metrics(points, targets)
    shifted_envelope = tuple(
        (low + float(delta), high + float(delta))
        for (low, high), delta in zip(envelope, offsets, strict=True)
    )
    stage_f_candidate = WorkcellCandidate(
        board_yaw_relative_to_table_degrees=yaw,
        board_center_in_table_frame_xy_m=center,
        joint_zero_offsets_rad=tuple(float(value) for value in offsets),
        joint_range_envelope_rad=shifted_envelope,
        board_side_m=board_side,
    )
    stage_f_parameters = stage_f_candidate.as_dict()
    stage_f_parameters["square_side_m"] = board_side / 8.0
    stage_f_parameters["reopen_timing_z_bias_m"] = float(fit.x[8])

    frozen_center_tuple = tuple(float(value) for value in frozen_center)
    replays: dict[str, list[dict[str, Any]]] = {
        "stage_d_lift": [],
        "stage_f_board_pitch": [],
    }
    trace_probes: dict[str, list[dict[str, Any]]] = {
        "stage_d_lift": [],
        "stage_f_board_pitch": [],
    }
    for episode, source, destination, samples in train:
        for name, candidate in (
            ("stage_d_lift", stage_d_candidate),
            ("stage_f_board_pitch", stage_f_candidate),
        ):
            replays[name].append(
                replay_episode_with_candidate(
                    reward_contract=reward,
                    episode=episode,
                    source=source,
                    destination=destination,
                    samples=samples,
                    candidate=candidate,
                    frozen_board_center=frozen_center_tuple,
                    frozen_board_yaw=frozen_yaw,
                )
            )
            trace_probes[name].append(
                _source_approach_trace_probe(
                    candidate=candidate,
                    episode=episode,
                    source=source,
                    samples=samples,
                    neck_height_m=neck,
                )
            )
    summaries = {name: _summarize_replays(rows) for name, rows in replays.items()}
    trace_summaries = {
        name: _summarize_trace_probes(rows) for name, rows in trace_probes.items()
    }
    acceptance = contract["train_acceptance"]
    relative_reduction = (
        stage_d_metrics["event_rms_distance_m"]
        - stage_f_metrics["event_rms_distance_m"]
    ) / stage_d_metrics["event_rms_distance_m"]
    gates = {
        "event_rms_relative_reduction": relative_reduction,
        "event_rms_gate": relative_reduction
        >= float(acceptance["minimum_event_rms_relative_reduction_from_stage_d"]),
        "zero_clipping_gate": summaries["stage_f_board_pitch"]["clipped_episodes"] == 0,
        "contact_gate": summaries["stage_f_board_pitch"]["selected_piece_contact"]
        >= int(acceptance["minimum_selected_piece_contact_episodes"]),
        "lift_gate": summaries["stage_f_board_pitch"]["lifted"]
        >= int(acceptance["minimum_lifted_episodes"]),
        "success_gate": summaries["stage_f_board_pitch"]["successes"]
        >= int(acceptance["minimum_task_successes"]),
    }
    accepted = all(value for key, value in gates.items() if key.endswith("_gate"))
    selected_name = "stage_f_board_pitch" if accepted else "stage_d_lift"
    selected_parameters = stage_f_parameters if accepted else stage_d_parameters
    unsigned = {
        "schema_version": "sim2claw.pawn_bg_workcell_fit_v3_receipt.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "contract_sha256": sha256_file(CONTRACT_PATH),
        "catalog_sha256": sha256_file(CATALOG_PATH),
        "split_sha256": sha256_file(SPLIT_PATH),
        "calibration_sha256": sha256_file(CALIBRATION_PATH),
        "train_episode_count": len(train),
        "train_event_count": len(events),
        "stage_d_lift": {
            "kinematic": stage_d_metrics,
            "parameters": stage_d_parameters,
            "replay_summary": summaries["stage_d_lift"],
            "episodes": replays["stage_d_lift"],
            "source_approach_trace_summary": trace_summaries["stage_d_lift"],
            "source_approach_trace_episodes": trace_probes["stage_d_lift"],
        },
        "stage_f_board_pitch": {
            "kinematic": stage_f_metrics,
            "parameters": stage_f_parameters,
            "replay_summary": summaries["stage_f_board_pitch"],
            "episodes": replays["stage_f_board_pitch"],
            "source_approach_trace_summary": trace_summaries["stage_f_board_pitch"],
            "source_approach_trace_episodes": trace_probes["stage_f_board_pitch"],
            "event_audit": _event_audit_rows(events, points, targets),
            "optimizer": {
                "success": bool(fit.success),
                "status": int(fit.status),
                "cost": float(fit.cost),
                "optimality": float(fit.optimality),
                "function_evaluations": int(fit.nfev),
            },
        },
        "train_acceptance": {"gates": gates, "accepted": accepted},
        "selected_candidate": selected_name,
        "kinematic_error_candidate": (
            "stage_f_board_pitch" if gates["event_rms_gate"] else "stage_d_lift"
        ),
        "physics_replay_candidate": selected_name,
        "selected_parameters": selected_parameters,
        "held_out_used_for_selection": False,
        "exploratory_disclosure": candidate_contract["exploratory_disclosure"],
        "claim_boundary": (
            "Stage F is a train-derived simulator geometry candidate. A lower train trace error "
            "and retained source-replay consequences do not establish the physical board dimension, "
            "policy success, or physical transfer."
        ),
    }
    receipt = {**unsigned, "receipt_sha256": canonical_digest(unsigned)}
    atomic_write_json(output_path, receipt)
    return receipt


def run_workcell_v3_confirmation(
    *, source_repository_root: Path, receipt_path: Path, output_path: Path
) -> dict[str, Any]:
    """Compare Stage D/F on evaluator episodes already opened by earlier work."""

    contract = load_workcell_v3_contract()
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("schema_version") != "sim2claw.pawn_bg_workcell_fit_v3_receipt.v1":
        raise WorkcellFitError("unexpected Stage-F fit receipt schema")
    unsigned_receipt = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    if receipt.get("receipt_sha256") != canonical_digest(unsigned_receipt):
        raise WorkcellFitError("Stage-F fit receipt digest changed")
    parent = load_workcell_contract()
    reward = load_reward_contract()
    held_out, events = _load_partition(source_repository_root, "held_out")
    if len(held_out) != 2 or len(events) != 4:
        raise WorkcellFitError(
            f"expected 2 confirmation episodes and 4 events, found {len(held_out)} and {len(events)}"
        )
    reopen_mask = np.asarray(
        [event.phase == "destination_reopen" for event in events], dtype=bool
    )
    parent_fit = parent["fit"]
    neck = float(parent_fit["estimated_pawn_neck_height_m"])
    frozen_center = tuple(
        float(value) for value in parent_fit["frozen_board_center_in_table_frame_xy_m"]
    )
    frozen_yaw = float(parent_fit["frozen_board_yaw_relative_to_table_degrees"])
    comparisons: dict[str, Any] = {}
    for name in ("stage_d_lift", "stage_f_board_pitch"):
        parameters = receipt[name]["parameters"]
        candidate = _candidate_from_parameters(parameters)
        binding = build_workcell_model(candidate)
        points = _fk_pinch_points(
            binding, events, np.asarray(candidate.joint_zero_offsets_rad, dtype=np.float64)
        )
        targets = _event_targets(
            events,
            candidate.board_center_in_table_frame_xy_m,
            candidate.board_yaw_relative_to_table_degrees,
            neck,
            candidate.board_side_m,
        )
        targets[reopen_mask, 2] += float(parameters["reopen_timing_z_bias_m"])
        replays = [
            replay_episode_with_candidate(
                reward_contract=reward,
                episode=episode,
                source=source,
                destination=destination,
                samples=samples,
                candidate=candidate,
                frozen_board_center=frozen_center,
                frozen_board_yaw=frozen_yaw,
            )
            for episode, source, destination, samples in held_out
        ]
        trace_probes = [
            _source_approach_trace_probe(
                candidate=candidate,
                episode=episode,
                source=source,
                samples=samples,
                neck_height_m=neck,
            )
            for episode, source, destination, samples in held_out
        ]
        comparisons[name] = {
            "kinematic": _metrics(points, targets),
            "replay_summary": _summarize_replays(replays),
            "episodes": replays,
            "source_approach_trace_summary": _summarize_trace_probes(trace_probes),
            "source_approach_trace_episodes": trace_probes,
            "event_audit": _event_audit_rows(events, points, targets),
        }
    d_rms = comparisons["stage_d_lift"]["kinematic"]["event_rms_distance_m"]
    f_rms = comparisons["stage_f_board_pitch"]["kinematic"]["event_rms_distance_m"]
    unsigned = {
        "schema_version": "sim2claw.pawn_bg_workcell_fit_v3_confirmation.v1",
        "fit_receipt_sha256": sha256_file(receipt_path),
        "confirmation_policy": contract["confirmation"],
        "held_out_episode_count": len(held_out),
        "held_out_event_count": len(events),
        "comparisons": comparisons,
        "stage_f_event_rms_reduction_from_stage_d": (d_rms - f_rms) / d_rms,
        "selection_changed_from_confirmation": False,
        "claim_boundary": (
            "These evaluator episodes were already opened. This is transparent post-selection "
            "confirmation and cannot tune or select Stage F."
        ),
    }
    result = {**unsigned, "confirmation_sha256": canonical_digest(unsigned)}
    atomic_write_json(output_path, result)
    return result


__all__ = [
    "CONTRACT_PATH",
    "load_workcell_v3_contract",
    "run_workcell_fit_v3",
    "run_workcell_v3_confirmation",
]
