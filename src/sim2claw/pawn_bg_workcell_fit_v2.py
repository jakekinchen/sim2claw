"""Move-suite workcell calibration across every recorded pawn move (v2).

The v1 workcell fit constrained board pose and joint zero offsets with 22
events from same-file rank moves only. The frozen catalog also holds three
cross-file recordings and one diagonal training recording that the v1
product-scope filter discarded, plus one never-opened diagonal held-out
recording. Cross-file and diagonal moves sweep the arm laterally across the
board, so their gripper-close/reopen events constrain board yaw and center
far better than rank moves alone, and they probe whether the v1 candidate's
large shoulder-lift zero offset survives arm poses it was never fitted on.

This module widens the data scope only. The staged bounded parameterization,
event extractor, envelope construction, and candidate-selection rule are the
frozen v1 machinery, reused unchanged. Replay consequences for moves outside
the frozen 12-skill reward table are computed diagnostically from the same
trace-row schema and the same frozen thresholds, but no frozen gate result or
task-success claim is emitted for them. Nothing here claims physical
calibration, policy success, training admission, or promotion.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import mujoco
import numpy as np

from .paths import REPO_ROOT
from .pawn_bg_demo_sim import (
    BASELINE_PIECE_BY_FILE,
    _load_source,
    _piece_bodies,
    _trace_row,
    physical_values_to_sim_with_adapter,
)
from .pawn_bg_reward import load_reward_contract, sha256_file
from .pawn_bg_source_fit import load_source_fit_contract
from .pawn_bg_workcell_fit import (
    CALIBRATION_PATH,
    CATALOG_PATH,
    SPLIT_PATH,
    WorkcellCandidate,
    WorkcellFitError,
    _event_targets,
    _extract_events,
    _fk_pinch_points,
    _split_membership,
    build_workcell_model,
    fit_candidate,
    measured_range_envelope,
)
from .grasp import _pinch_point
from .scene import board_square_center

CONTRACT_V2_PATH = REPO_ROOT / "configs" / "optimization" / "pawn_bg_workcell_fit_v2.json"

MOVE_LABEL_PATTERN = re.compile(r"^([a-h][1-8])-to-([a-h][1-8])(?:-redo)?$")

BASELINE_PIECE_BY_SQUARE = {
    name.rsplit("_", 1)[-1]: name for name in BASELINE_PIECE_BY_FILE.values()
}


def load_workcell_contract_v2(path: Path = CONTRACT_V2_PATH) -> dict[str, Any]:
    contract = json.loads(path.read_bytes())
    if contract.get("schema_version") != "sim2claw.pawn_bg_workcell_fit.v2":
        raise WorkcellFitError("unexpected v2 workcell fit contract schema")
    return contract


def classify_move(source: str, destination: str) -> tuple[str, int]:
    """Return (move class, span in squares) for one square-to-square move."""

    if source == destination:
        raise WorkcellFitError(f"move cannot start and end on {source}")
    file_delta = abs(ord(source[0]) - ord(destination[0]))
    rank_delta = abs(int(source[1]) - int(destination[1]))
    if file_delta == 0:
        move_class = "rank"
    elif rank_delta == 0:
        move_class = "file"
    else:
        move_class = "diagonal"
    return move_class, max(file_delta, rank_delta)


@dataclass(frozen=True)
class MoveSuiteEntry:
    episode: dict[str, Any]
    source: str
    destination: str
    move_class: str
    span_squares: int
    replay_supported: bool
    baseline_destination_square_occupied: bool


def move_suite_episodes(catalog: dict[str, Any]) -> list[MoveSuiteEntry]:
    """Every catalog recording whose label parses as a square-to-square move."""

    entries = []
    for episode in catalog.get("episodes", []):
        match = MOVE_LABEL_PATTERN.fullmatch(str(episode.get("folder_label", "")))
        if match is None:
            continue
        source, destination = match.group(1), match.group(2)
        if source == destination:
            continue
        move_class, span = classify_move(source, destination)
        selected_name = BASELINE_PIECE_BY_FILE.get(source[0])
        occupant = BASELINE_PIECE_BY_SQUARE.get(destination)
        entries.append(MoveSuiteEntry(
            episode=episode,
            source=source,
            destination=destination,
            move_class=move_class,
            span_squares=span,
            replay_supported=selected_name is not None,
            baseline_destination_square_occupied=(
                occupant is not None and occupant != selected_name
            ),
        ))
    return entries


def _enforce_minimum_scope(
    entries: list[MoveSuiteEntry], contract: dict[str, Any]
) -> dict[str, int]:
    counts = {"rank": 0, "file": 0, "diagonal": 0}
    for entry in entries:
        counts[entry.move_class] += 1
    minimums = contract["data_binding"]["minimum_train_scope"]
    for move_class, minimum in minimums.items():
        if counts.get(move_class, 0) < int(minimum):
            raise WorkcellFitError(
                f"train scope requires at least {minimum} {move_class} episodes, "
                f"found {counts.get(move_class, 0)}"
            )
    return counts


def _split_entries(
    entries: list[MoveSuiteEntry], membership: dict[str, str], wanted_split: str
) -> list[MoveSuiteEntry]:
    return [
        entry for entry in entries
        if membership.get(entry.episode["recording_id"]) == wanted_split
    ]


def fresh_held_out_entries(
    entries: list[MoveSuiteEntry],
    membership: dict[str, str],
    contract: dict[str, Any],
) -> list[MoveSuiteEntry]:
    """Held-out scope minus the recordings the v1 fit already opened."""

    opened = set(contract["data_binding"]["previously_opened_held_out_recording_ids"])
    held_out = _split_entries(entries, membership, "held_out")
    fresh = [
        entry for entry in held_out
        if entry.episode["recording_id"] not in opened
    ]
    minimum = int(contract["data_binding"]["fresh_held_out_minimum_episodes"])
    if len(fresh) < minimum:
        raise WorkcellFitError(
            f"fresh held-out scope requires at least {minimum} episodes, found {len(fresh)}"
        )
    return fresh


def replay_move_with_candidate(
    *,
    entry: MoveSuiteEntry,
    samples: list[dict[str, Any]],
    candidate: WorkcellCandidate | None,
    frozen_board_center: tuple[float, float],
    frozen_board_yaw: float,
    thresholds: dict[str, Any],
    sample_hz: int,
) -> dict[str, Any]:
    """Command-driven physics replay with diagnostic-only consequence metrics.

    candidate=None replays the frozen workcell with the identity adapter,
    reproducing the terminal-negative baseline configuration. Thresholds are
    the frozen reward hard gates, applied diagnostically; no frozen gate
    verdict or task-success claim is produced.
    """

    if not entry.replay_supported:
        raise WorkcellFitError(
            f"no baseline piece exists for source file {entry.source[0]!r}"
        )
    from .pawn_bg_demo_sim import JointAdapter

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
        ))
    else:
        board_center = candidate.board_center_in_table_frame_xy_m
        board_yaw = candidate.board_yaw_relative_to_table_degrees
        adapter = candidate.adapter()
        binding = build_workcell_model(candidate)

    model, data = binding["model"], binding["data"]
    actuator_ids = binding["actuator_ids"]
    qpos_addresses = binding["qpos_addresses"]
    bounds = binding["actuator_bounds"]

    selected_name = BASELINE_PIECE_BY_FILE[entry.source[0]]
    selected_body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, selected_name)
    selected_joint = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_JOINT, f"{selected_name}_free"
    )
    selected_qpos = int(model.jnt_qposadr[selected_joint])
    selected_dof = int(model.jnt_dofadr[selected_joint])
    source_xyz = np.asarray(board_square_center(
        entry.source,
        board_center_in_table_frame_xy_m=board_center,
        board_yaw_relative_to_table_degrees=board_yaw,
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

    def observe() -> dict[str, Any]:
        return _trace_row(
            model, data, selected_body=selected_body, selected_dof=selected_dof,
            piece_bodies=piece_bodies, initial_piece_positions=initial_positions,
            robot_body_ids=robot_body_ids, jaw_body_ids=jaw_body_ids,
        )

    trace = [observe()]
    pinch_local = binding["pinch_offset_local"]

    def pinch_to_piece() -> float:
        pinch = _pinch_point(model, data, "left", pinch_local)
        return float(np.linalg.norm(pinch - np.asarray(data.xpos[selected_body])))

    minimum_pinch_to_piece = pinch_to_piece()
    clipped_command_rows = 0
    previous_timestamp: float | None = None
    nominal_dt = 1.0 / max(1, int(sample_hz))
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
        trace.append(observe())
    for _ in range(200):
        mujoco.mj_step(model, data)
    trace.append(observe())

    target_xyz = np.asarray(board_square_center(
        entry.destination,
        board_center_in_table_frame_xy_m=board_center,
        board_yaw_relative_to_table_degrees=board_yaw,
    ))
    max_rise = max(
        float(row["piece_position_xyz_m"][2]) - initial_height for row in trace
    )
    final = trace[-1]
    final_xyz = np.asarray(final["piece_position_xyz_m"], dtype=np.float64)
    contact_rows = sum(int(row["selected_piece_jaw_contact"]) for row in trace)
    return {
        "recording_id": entry.episode["recording_id"],
        "folder_label": entry.episode["folder_label"],
        "skill_id": f"pawn_{entry.source}_to_{entry.destination}",
        "move_class": entry.move_class,
        "span_squares": entry.span_squares,
        "baseline_destination_square_occupied": entry.baseline_destination_square_occupied,
        "clipped_command_rows": clipped_command_rows,
        "minimum_pinch_to_selected_piece_m": float(minimum_pinch_to_piece),
        "selected_piece_contact_rows": contact_rows,
        "selected_piece_contact_observed": contact_rows > 0,
        "piece_lifted": max_rise >= float(thresholds["minimum_piece_rise_m"]),
        "maximum_piece_rise_m": float(max_rise),
        "final_target_distance_m": float(
            np.linalg.norm(final_xyz[:2] - target_xyz[:2])
        ),
        "wrong_piece_contact_observed": any(
            bool(row["wrong_piece_robot_contact"]) for row in trace
        ),
        "maximum_other_piece_displacement_m": float(
            max(row["maximum_other_piece_displacement_m"] for row in trace)
        ),
        "finite_state": all(bool(row["finite_state"]) for row in trace),
        "scoring": "diagnostic_only_no_frozen_gate_claim",
    }


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"episodes": 0}
    return {
        "episodes": len(rows),
        "clipped_episodes": sum(1 for r in rows if r["clipped_command_rows"]),
        "selected_piece_contact": sum(
            1 for r in rows if r["selected_piece_contact_observed"]
        ),
        "lifted": sum(1 for r in rows if r["piece_lifted"]),
        "mean_maximum_piece_rise_m": float(
            np.mean([r["maximum_piece_rise_m"] for r in rows])
        ),
        "mean_final_target_distance_m": float(
            np.mean([r["final_target_distance_m"] for r in rows])
        ),
    }


def _grouped_summaries(rows: list[dict[str, Any]]) -> dict[str, Any]:
    clean = [r for r in rows if not r["baseline_destination_square_occupied"]]
    flagged = [r for r in rows if r["baseline_destination_square_occupied"]]
    by_class: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_class.setdefault(row["move_class"], []).append(row)
    return {
        "all_episodes": _summarize(rows),
        "modeled_board_state_only": _summarize(clean),
        "unmodeled_destination_occupancy": _summarize(flagged),
        "by_move_class": {
            move_class: _summarize(class_rows)
            for move_class, class_rows in sorted(by_class.items())
        },
    }


def _candidate_from_parameters(params: dict[str, Any]) -> WorkcellCandidate:
    return WorkcellCandidate(
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


def _kinematic_breakdown(
    binding: dict[str, Any],
    events: list[Any],
    event_classes: list[str],
    parameters: dict[str, Any],
    neck_height_m: float,
) -> dict[str, Any]:
    """Per-move-class event distances for one frozen candidate parameter set."""

    offsets = np.asarray([float(v) for v in parameters["joint_zero_offsets_rad"]])
    base_z = float(parameters.get("base_z_offset_m", 0.0))
    reopen_bias = float(parameters.get("reopen_timing_z_bias_m", 0.0))
    reopen_mask = np.asarray([event.phase == "destination_reopen" for event in events])
    points = _fk_pinch_points(binding, events, offsets)
    points = points + np.asarray([0.0, 0.0, base_z])
    targets = _event_targets(
        events,
        tuple(float(v) for v in parameters["board_center_in_table_frame_xy_m"]),
        float(parameters["board_yaw_relative_to_table_degrees"]),
        neck_height_m,
    )
    targets[reopen_mask, 2] += reopen_bias
    distance = np.linalg.norm(points - targets, axis=1)
    by_class: dict[str, list[float]] = {}
    for value, move_class in zip(distance, event_classes):
        by_class.setdefault(move_class, []).append(float(value))
    return {
        "overall_event_rms_distance_m": float(np.sqrt(np.mean(distance**2))),
        "by_move_class": {
            move_class: {
                "events": len(values),
                "event_rms_distance_m": float(
                    np.sqrt(np.mean(np.asarray(values) ** 2))
                ),
                "event_maximum_distance_m": float(np.max(values)),
            }
            for move_class, values in sorted(by_class.items())
        },
    }


def run_move_suite_fit(
    *, source_repository_root: Path, output_path: Path
) -> dict[str, Any]:
    contract = load_workcell_contract_v2()
    source_fit_contract = load_source_fit_contract()
    reward_contract = load_reward_contract()
    thresholds = reward_contract["hard_gates"]
    membership = _split_membership()
    catalog = json.loads(CATALOG_PATH.read_bytes())
    scope = move_suite_episodes(catalog)
    train_entries = _split_entries(scope, membership, "train")
    _enforce_minimum_scope(train_entries, contract)

    train: list[tuple[MoveSuiteEntry, list[dict[str, Any]]]] = []
    for entry in train_entries:
        train.append((entry, _load_source(entry.episode, source_repository_root)))

    events = []
    event_classes: list[str] = []
    for entry, samples in train:
        extracted = _extract_events(
            entry.episode, entry.source, entry.destination, samples, source_fit_contract
        )
        events.extend(extracted)
        event_classes.extend([entry.move_class] * len(extracted))

    envelope = measured_range_envelope([samples for _, samples in train])
    fit = contract["fit"]
    neck = float(fit["estimated_pawn_neck_height_m"])
    frozen_center = tuple(float(v) for v in fit["frozen_board_center_in_table_frame_xy_m"])
    frozen_yaw = float(fit["frozen_board_yaw_relative_to_table_degrees"])
    scratch_candidate = WorkcellCandidate(
        board_yaw_relative_to_table_degrees=frozen_yaw,
        board_center_in_table_frame_xy_m=frozen_center,
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
    parameters_key = {
        "stage_c": "stage_c_parameters",
        "stage_c_prime": "stage_c_prime_parameters",
        "stage_d_lift": "stage_d_lift_parameters",
    }
    kinematic_key = {
        "stage_c": "stage_c_kinematic",
        "stage_c_prime": "stage_c_prime_kinematic",
        "stage_d_lift": "stage_d_lift_kinematic",
    }

    replays_baseline = []
    replays_by_name: dict[str, list[dict[str, Any]]] = {name: [] for name in candidates}
    for entry, samples in train:
        if not entry.replay_supported:
            continue
        sample_hz = int(entry.episode["sample_hz"])
        replays_baseline.append(replay_move_with_candidate(
            entry=entry, samples=samples, candidate=None,
            frozen_board_center=frozen_center, frozen_board_yaw=frozen_yaw,
            thresholds=thresholds, sample_hz=sample_hz,
        ))
        for name, current in candidates.items():
            replays_by_name[name].append(replay_move_with_candidate(
                entry=entry, samples=samples, candidate=current,
                frozen_board_center=frozen_center, frozen_board_yaw=frozen_yaw,
                thresholds=thresholds, sample_hz=sample_hz,
            ))

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

    breakdowns = {
        name: _kinematic_breakdown(
            binding, events, event_classes, result[parameters_key[name]], neck
        )
        for name in candidates
    }

    receipt = {
        "schema_version": "sim2claw.pawn_bg_workcell_fit_receipt.v2",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "contract_sha256": sha256_file(CONTRACT_V2_PATH),
        "calibration_sha256": sha256_file(CALIBRATION_PATH),
        "split_sha256": sha256_file(SPLIT_PATH),
        "catalog_sha256": sha256_file(CATALOG_PATH),
        "train_scope": [
            {
                "recording_id": entry.episode["recording_id"],
                "folder_label": entry.episode["folder_label"],
                "move_class": entry.move_class,
                "span_squares": entry.span_squares,
                "baseline_destination_square_occupied": (
                    entry.baseline_destination_square_occupied
                ),
            }
            for entry, _ in train
        ],
        "train_episode_count": len(train),
        "train_event_count": len(events),
        "kinematic": dict(result),
        "kinematic_by_move_class": breakdowns,
        "train_replay_frozen_baseline": {
            "summary": _grouped_summaries(replays_baseline),
            "episodes": replays_baseline,
        },
        "train_replay_candidates": {
            name: {"summary": _grouped_summaries(rows), "episodes": rows}
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
            "Bounded workcell candidate fitted on every in-scope training "
            "recording, including cross-file and diagonal moves. Consequence "
            "metrics are diagnostic only; episodes with unmodeled destination "
            "occupancy are flagged and summarized separately. No promotion, "
            "training, policy, or physical-calibration claim."
        ),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return receipt


def run_move_suite_held_out(
    *, source_repository_root: Path, receipt_path: Path, output_path: Path
) -> dict[str, Any]:
    """Open the fresh (never-opened) held-out recordings exactly once."""

    receipt = json.loads(receipt_path.read_bytes())
    candidate = _candidate_from_parameters(receipt["selected_parameters"])
    reopen_bias = float(receipt["selected_parameters"].get("reopen_timing_z_bias_m", 0.0))
    contract = load_workcell_contract_v2()
    source_fit_contract = load_source_fit_contract()
    reward_contract = load_reward_contract()
    thresholds = reward_contract["hard_gates"]
    membership = _split_membership()
    catalog = json.loads(CATALOG_PATH.read_bytes())
    scope = move_suite_episodes(catalog)
    fresh = fresh_held_out_entries(scope, membership, contract)
    opened = set(contract["data_binding"]["previously_opened_held_out_recording_ids"])
    reference = [
        entry for entry in _split_entries(scope, membership, "held_out")
        if entry.episode["recording_id"] in opened
    ]

    fit = contract["fit"]
    neck = float(fit["estimated_pawn_neck_height_m"])
    frozen_center = tuple(float(v) for v in fit["frozen_board_center_in_table_frame_xy_m"])
    frozen_yaw = float(fit["frozen_board_yaw_relative_to_table_degrees"])

    binding = build_workcell_model(candidate)
    events = []
    event_classes: list[str] = []
    payloads: list[tuple[MoveSuiteEntry, list[dict[str, Any]]]] = []
    for entry in fresh:
        samples = _load_source(entry.episode, source_repository_root)
        payloads.append((entry, samples))
        extracted = _extract_events(
            entry.episode, entry.source, entry.destination, samples, source_fit_contract
        )
        events.extend(extracted)
        event_classes.extend([entry.move_class] * len(extracted))

    candidate_parameters = dict(receipt["selected_parameters"])
    kinematic_candidate = _kinematic_breakdown(
        binding, events, event_classes, candidate_parameters, neck
    )
    identity_parameters = {
        "board_yaw_relative_to_table_degrees": frozen_yaw,
        "board_center_in_table_frame_xy_m": list(frozen_center),
        "joint_zero_offsets_rad": [0.0] * 5,
    }
    kinematic_frozen = _kinematic_breakdown(
        binding, events, event_classes, identity_parameters, neck
    )

    replays_baseline = []
    replays_candidate = []
    for entry, samples in payloads:
        sample_hz = int(entry.episode["sample_hz"])
        replays_baseline.append(replay_move_with_candidate(
            entry=entry, samples=samples, candidate=None,
            frozen_board_center=frozen_center, frozen_board_yaw=frozen_yaw,
            thresholds=thresholds, sample_hz=sample_hz,
        ))
        replays_candidate.append(replay_move_with_candidate(
            entry=entry, samples=samples, candidate=candidate,
            frozen_board_center=frozen_center, frozen_board_yaw=frozen_yaw,
            thresholds=thresholds, sample_hz=sample_hz,
        ))

    reference_rows = []
    for entry in reference:
        samples = _load_source(entry.episode, source_repository_root)
        reference_rows.append(replay_move_with_candidate(
            entry=entry, samples=samples, candidate=candidate,
            frozen_board_center=frozen_center, frozen_board_yaw=frozen_yaw,
            thresholds=thresholds, sample_hz=int(entry.episode["sample_hz"]),
        ))

    admission = contract["admission"]
    fresh_rms = kinematic_candidate["overall_event_rms_distance_m"]
    validation = {
        "schema_version": "sim2claw.pawn_bg_workcell_held_out_validation.v2",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "fit_receipt_sha256": sha256_file(receipt_path),
        "fresh_held_out_episodes": [
            {
                "recording_id": entry.episode["recording_id"],
                "folder_label": entry.episode["folder_label"],
                "move_class": entry.move_class,
            }
            for entry in fresh
        ],
        "fresh_held_out_event_count": len(events),
        "held_out_kinematic_candidate": kinematic_candidate,
        "held_out_kinematic_frozen_baseline": kinematic_frozen,
        "held_out_replay_frozen_baseline": replays_baseline,
        "held_out_replay_candidate": replays_candidate,
        "previously_opened_reference": {
            "note": (
                "these episodes were opened by the v1 workcell fit and carry "
                "no fresh-evidence weight; rows are context only"
            ),
            "episodes": reference_rows,
        },
        "admission_rule": admission,
        "admitted": bool(
            fresh_rms <= float(admission["maximum_held_out_event_rms_m"])
            and all(r["clipped_command_rows"] == 0 for r in replays_candidate)
        ),
        "claim_boundary": (
            "Fresh held-out recordings opened exactly once against the frozen "
            "move-suite candidate. Admission is kinematic-generalization only; "
            "consequence deltas are diagnostic evidence, not physical-transfer "
            "proof."
        ),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(validation, indent=2), encoding="utf-8")
    return validation
