"""Train-only Stage-E B-G workcell fit with bounded robot-base pose offsets."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import mujoco
import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

from .learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .paths import REPO_ROOT
from .pawn_bg_workcell_fit import (
    BODY_JOINT_NAMES,
    CATALOG_PATH,
    CALIBRATION_PATH,
    FITTED_OFFSET_JOINTS,
    SPLIT_PATH,
    WorkcellCandidate,
    WorkcellFitError,
    _episode_payloads,
    _event_targets,
    _extract_events,
    _fk_pinch_points,
    _split_membership,
    build_workcell_model,
    fit_candidate,
    load_workcell_contract,
    measured_range_envelope,
    replay_episode_with_candidate,
)
from .pawn_bg_reward import load_reward_contract
from .pawn_bg_source_fit import load_source_fit_contract


CONTRACT_PATH = REPO_ROOT / "configs" / "optimization" / "pawn_bg_workcell_fit_v2.json"
SCHEMA = "sim2claw.pawn_bg_workcell_fit.v2"


def load_workcell_v2_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    contract = json.loads(path.read_text(encoding="utf-8"))
    if contract.get("schema_version") != SCHEMA:
        raise WorkcellFitError("unexpected Stage-E workcell contract schema")
    authority = contract.get("authority")
    if not isinstance(authority, dict) or not authority or any(authority.values()):
        raise WorkcellFitError("Stage-E authority widened")
    parent = contract["parent_contract"]
    parent_path = (REPO_ROOT / parent["path"]).resolve()
    if sha256_file(parent_path) != parent["sha256"]:
        raise WorkcellFitError("Stage-E parent contract changed")
    return contract


def _set_base_pose(
    binding: Mapping[str, Any],
    *,
    nominal_position: np.ndarray,
    nominal_rotation: Rotation,
    roll_degrees: float,
    pitch_degrees: float,
    z_offset_m: float,
) -> None:
    model = binding["model"]
    base_body = int(binding["base_body_id"])
    model.body_pos[base_body] = nominal_position
    model.body_pos[base_body, 2] += float(z_offset_m)
    adjustment = Rotation.from_euler(
        "xy", [float(roll_degrees), float(pitch_degrees)], degrees=True
    )
    xyzw = (nominal_rotation * adjustment).as_quat()
    model.body_quat[base_body] = np.asarray(
        [xyzw[3], xyzw[0], xyzw[1], xyzw[2]], dtype=np.float64
    )


def _candidate_from_parameters(parameters: Mapping[str, Any]) -> WorkcellCandidate:
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
        base_z_offset_m=float(parameters.get("base_z_offset_m", 0.0)),
        base_roll_offset_degrees=float(
            parameters.get("base_roll_offset_degrees", 0.0)
        ),
        base_pitch_offset_degrees=float(
            parameters.get("base_pitch_offset_degrees", 0.0)
        ),
        board_side_m=(
            float(parameters["board_side_m"])
            if parameters.get("board_side_m") is not None
            else None
        ),
    )


def _metrics(points: np.ndarray, targets: np.ndarray) -> dict[str, float]:
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


def _summarize_replays(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise WorkcellFitError("Stage-E replay summary is empty")
    return {
        "episodes": len(rows),
        "clipped_episodes": sum(1 for row in rows if row["clipped_command_rows"]),
        "selected_piece_contact": sum(
            1 for row in rows if row["selected_piece_contact_observed"]
        ),
        "lifted": sum(1 for row in rows if row["piece_lifted"]),
        "successes": sum(1 for row in rows if row["task_consequence_success"]),
        "mean_maximum_piece_rise_m": float(
            np.mean([row["maximum_piece_rise_m"] for row in rows])
        ),
        "mean_final_target_distance_m": float(
            np.mean([row["final_target_distance_m"] for row in rows])
        ),
    }


def run_workcell_fit_v2(
    *, source_repository_root: Path, output_path: Path
) -> dict[str, Any]:
    """Fit and select Stage E using the frozen train episodes only."""

    contract = load_workcell_v2_contract()
    parent = load_workcell_contract()
    source_fit = load_source_fit_contract()
    reward = load_reward_contract()
    membership = _split_membership()
    train = _episode_payloads(source_repository_root, membership, "train")
    if len(train) != 11:
        raise WorkcellFitError(f"expected 11 product train episodes, found {len(train)}")
    events = [
        event
        for episode, source, destination, samples in train
        for event in _extract_events(episode, source, destination, samples, source_fit)
    ]
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
    base_body = mujoco.mj_name2id(
        binding["model"], mujoco.mjtObj.mjOBJ_BODY, "left_base"
    )
    if base_body < 0:
        raise WorkcellFitError("Stage-E scene is missing left_base")
    binding["base_body_id"] = base_body
    nominal_position = np.asarray(binding["model"].body_pos[base_body], dtype=np.float64).copy()
    nominal_wxyz = np.asarray(binding["model"].body_quat[base_body], dtype=np.float64)
    nominal_rotation = Rotation.from_quat(
        [nominal_wxyz[1], nominal_wxyz[2], nominal_wxyz[3], nominal_wxyz[0]]
    )

    parent_result = fit_candidate(events, binding, parent, envelope)
    stage_d_candidate = parent_result["candidate_lift"]
    stage_d_metrics = dict(parent_result["stage_d_lift_kinematic"])
    stage_d_parameters = dict(parent_result["stage_d_lift_parameters"])
    stage_d_reopen_bias = float(stage_d_parameters["reopen_timing_z_bias_m"])

    candidate_contract = contract["candidate"]
    base_center = np.asarray(
        parent_fit["frozen_board_center_in_table_frame_xy_m"], dtype=np.float64
    )
    relabeled_yaw = float(parent_fit["frozen_board_yaw_relative_to_table_degrees"]) + 180.0
    offset_indices = [BODY_JOINT_NAMES.index(name) for name in FITTED_OFFSET_JOINTS]
    stage_d_offsets = np.asarray(stage_d_candidate.joint_zero_offsets_rad)[offset_indices]
    x0 = np.asarray(
        [
            stage_d_candidate.board_center_in_table_frame_xy_m[0] - base_center[0],
            stage_d_candidate.board_center_in_table_frame_xy_m[1] - base_center[1],
            stage_d_candidate.board_yaw_relative_to_table_degrees - relabeled_yaw,
            *stage_d_offsets.tolist(),
            0.0,
            0.0,
            0.0,
            stage_d_reopen_bias,
        ],
        dtype=np.float64,
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
        [
            -0.08,
            -0.08,
            -15.0,
            *lower_offsets,
            -float(candidate_contract["base_roll_bound_degrees"]),
            -float(candidate_contract["base_pitch_bound_degrees"]),
            -float(candidate_contract["base_z_bound_m"]),
            0.0,
        ],
        dtype=np.float64,
    )
    upper = np.asarray(
        [
            0.08,
            0.08,
            15.0,
            *upper_offsets,
            float(candidate_contract["base_roll_bound_degrees"]),
            float(candidate_contract["base_pitch_bound_degrees"]),
            float(candidate_contract["base_z_bound_m"]),
            float(parent_fit["reopen_timing_z_bound_m"]),
        ],
        dtype=np.float64,
    )
    reopen_mask = np.asarray(
        [event.phase == "destination_reopen" for event in events], dtype=bool
    )
    tight_sigma = math.radians(float(parent_fit["stage_d_other_offset_prior_sigma_degrees"]))
    tilt_sigma = float(candidate_contract["base_roll_pitch_prior_sigma_degrees"])
    z_sigma = float(candidate_contract["base_z_prior_sigma_m"])
    normalizer = math.sqrt(len(events) * 3)
    other_positions = [index for index in range(4) if index != lift_position]

    def residual(parameters: np.ndarray) -> np.ndarray:
        center = tuple((base_center + parameters[:2]).tolist())
        yaw = relabeled_yaw + parameters[2]
        offsets = np.zeros(5)
        offsets[offset_indices] = parameters[3:7]
        _set_base_pose(
            binding,
            nominal_position=nominal_position,
            nominal_rotation=nominal_rotation,
            roll_degrees=parameters[7],
            pitch_degrees=parameters[8],
            z_offset_m=parameters[9],
        )
        points = _fk_pinch_points(binding, events, offsets)
        targets = _event_targets(
            events, center, yaw, float(parent_fit["estimated_pawn_neck_height_m"])
        )
        targets[reopen_mask, 2] += parameters[10]
        data_residual = (points - targets).ravel()
        offset_prior = parameters[3:7][other_positions] / tight_sigma / normalizer
        tilt_prior = parameters[7:9] / tilt_sigma / normalizer
        z_prior = np.asarray([parameters[9] / z_sigma / normalizer])
        return np.concatenate([data_residual, offset_prior, tilt_prior, z_prior])

    fit = least_squares(
        residual,
        x0=x0,
        bounds=(lower, upper),
        method="trf",
        diff_step=float(candidate_contract["finite_difference_step"]),
    )
    center = tuple((base_center + fit.x[:2]).astype(float).tolist())
    yaw = float(relabeled_yaw + fit.x[2])
    offsets = np.zeros(5)
    offsets[offset_indices] = fit.x[3:7]
    _set_base_pose(
        binding,
        nominal_position=nominal_position,
        nominal_rotation=nominal_rotation,
        roll_degrees=fit.x[7],
        pitch_degrees=fit.x[8],
        z_offset_m=fit.x[9],
    )
    points = _fk_pinch_points(binding, events, offsets)
    targets = _event_targets(
        events, center, yaw, float(parent_fit["estimated_pawn_neck_height_m"])
    )
    targets[reopen_mask, 2] += fit.x[10]
    stage_e_metrics = _metrics(points, targets)
    shifted_envelope = tuple(
        (low + float(delta), high + float(delta))
        for (low, high), delta in zip(envelope, offsets)
    )
    stage_e_candidate = WorkcellCandidate(
        board_yaw_relative_to_table_degrees=yaw,
        board_center_in_table_frame_xy_m=center,
        joint_zero_offsets_rad=tuple(float(value) for value in offsets),
        joint_range_envelope_rad=shifted_envelope,
        base_z_offset_m=float(fit.x[9]),
        base_roll_offset_degrees=float(fit.x[7]),
        base_pitch_offset_degrees=float(fit.x[8]),
    )
    stage_e_parameters = stage_e_candidate.as_dict()
    stage_e_parameters["reopen_timing_z_bias_m"] = float(fit.x[10])

    frozen_center = tuple(
        float(value) for value in parent_fit["frozen_board_center_in_table_frame_xy_m"]
    )
    frozen_yaw = float(parent_fit["frozen_board_yaw_relative_to_table_degrees"])
    replays: dict[str, list[dict[str, Any]]] = {"stage_d_lift": [], "stage_e_base_pose": []}
    for episode, source, destination, samples in train:
        for name, candidate in (
            ("stage_d_lift", stage_d_candidate),
            ("stage_e_base_pose", stage_e_candidate),
        ):
            replays[name].append(
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
            )
    summaries = {name: _summarize_replays(rows) for name, rows in replays.items()}
    acceptance = contract["train_acceptance"]
    relative_reduction = (
        stage_d_metrics["event_rms_distance_m"]
        - stage_e_metrics["event_rms_distance_m"]
    ) / stage_d_metrics["event_rms_distance_m"]
    gates = {
        "event_rms_relative_reduction": relative_reduction,
        "event_rms_gate": relative_reduction
        >= float(acceptance["minimum_event_rms_relative_reduction_from_stage_d"]),
        "zero_clipping_gate": summaries["stage_e_base_pose"]["clipped_episodes"] == 0,
        "contact_gate": summaries["stage_e_base_pose"]["selected_piece_contact"]
        >= int(acceptance["minimum_selected_piece_contact_episodes"]),
        "lift_gate": summaries["stage_e_base_pose"]["lifted"]
        >= int(acceptance["minimum_lifted_episodes"]),
        "success_gate": summaries["stage_e_base_pose"]["successes"]
        >= int(acceptance["minimum_task_successes"]),
    }
    accepted = all(value for key, value in gates.items() if key.endswith("_gate"))
    selected_name = "stage_e_base_pose" if accepted else "stage_d_lift"
    selected_parameters = stage_e_parameters if accepted else stage_d_parameters
    unsigned = {
        "schema_version": "sim2claw.pawn_bg_workcell_fit_v2_receipt.v1",
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
        },
        "stage_e_base_pose": {
            "kinematic": stage_e_metrics,
            "parameters": stage_e_parameters,
            "replay_summary": summaries["stage_e_base_pose"],
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
        "selected_parameters": selected_parameters,
        "held_out_used_for_selection": False,
        "claim_boundary": (
            "Stage E is selected from train-only event and source-replay evidence. "
            "Base pose and joint offsets are diagnostic simulator parameters, not physical calibration."
        ),
    }
    receipt = {**unsigned, "receipt_sha256": canonical_digest(unsigned)}
    atomic_write_json(output_path, receipt)
    return receipt


def run_workcell_v2_confirmation(
    *, source_repository_root: Path, receipt_path: Path, output_path: Path
) -> dict[str, Any]:
    """Compare frozen Stage D/E candidates on already-open evaluator episodes."""

    contract = load_workcell_v2_contract()
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("schema_version") != "sim2claw.pawn_bg_workcell_fit_v2_receipt.v1":
        raise WorkcellFitError("unexpected Stage-E fit receipt schema")
    if receipt.get("receipt_sha256") != canonical_digest(
        {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    ):
        raise WorkcellFitError("Stage-E fit receipt digest changed")
    parent = load_workcell_contract()
    source_fit = load_source_fit_contract()
    reward = load_reward_contract()
    membership = _split_membership()
    held_out = _episode_payloads(source_repository_root, membership, "held_out")
    if len(held_out) != 2:
        raise WorkcellFitError(f"expected 2 product held-out episodes, found {len(held_out)}")
    events = [
        event
        for episode, source, destination, samples in held_out
        for event in _extract_events(episode, source, destination, samples, source_fit)
    ]
    reopen_mask = np.asarray(
        [event.phase == "destination_reopen" for event in events], dtype=bool
    )
    neck = float(parent["fit"]["estimated_pawn_neck_height_m"])
    frozen_center = tuple(
        float(value)
        for value in parent["fit"]["frozen_board_center_in_table_frame_xy_m"]
    )
    frozen_yaw = float(parent["fit"]["frozen_board_yaw_relative_to_table_degrees"])
    comparisons: dict[str, Any] = {}
    for name in ("stage_d_lift", "stage_e_base_pose"):
        parameters = receipt[name]["parameters"]
        candidate = _candidate_from_parameters(parameters)
        binding = build_workcell_model(candidate)
        offsets = np.asarray(candidate.joint_zero_offsets_rad, dtype=np.float64)
        points = _fk_pinch_points(binding, events, offsets)
        targets = _event_targets(
            events,
            candidate.board_center_in_table_frame_xy_m,
            candidate.board_yaw_relative_to_table_degrees,
            neck,
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
        comparisons[name] = {
            "kinematic": _metrics(points, targets),
            "replay_summary": _summarize_replays(replays),
            "episodes": replays,
        }
    d_rms = comparisons["stage_d_lift"]["kinematic"]["event_rms_distance_m"]
    e_rms = comparisons["stage_e_base_pose"]["kinematic"]["event_rms_distance_m"]
    unsigned = {
        "schema_version": "sim2claw.pawn_bg_workcell_fit_v2_confirmation.v1",
        "fit_receipt_sha256": sha256_file(receipt_path),
        "confirmation_policy": contract["confirmation_policy"],
        "held_out_episode_count": len(held_out),
        "held_out_event_count": len(events),
        "comparisons": comparisons,
        "stage_e_event_rms_reduction_from_stage_d": (d_rms - e_rms) / d_rms,
        "selection_changed_from_confirmation": False,
        "claim_boundary": (
            "The evaluator episodes were already opened by the prior Stage-D study. "
            "This is post-selection confirmation only and cannot tune or select Stage E."
        ),
    }
    result = {**unsigned, "confirmation_sha256": canonical_digest(unsigned)}
    atomic_write_json(output_path, result)
    return result


__all__ = [
    "CONTRACT_PATH",
    "load_workcell_v2_contract",
    "run_workcell_fit_v2",
    "run_workcell_v2_confirmation",
]
