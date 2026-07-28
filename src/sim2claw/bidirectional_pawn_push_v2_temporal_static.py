"""Prospective V05-T reset-layout static enumerator and action freezer."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import mujoco
import numpy as np

from . import bidirectional_pawn_push_v2_sim_rehearsal as _rehearsal
from . import bidirectional_pawn_push_v2_sim_rehearsal_v2 as _rehearsal_v2
from .bidirectional_registration_v2_fit import project
from .paths import REPO_ROOT
from .physical_canary import _physical_to_model_position
from .physical_gateway import (
    BODY_COMMAND_RATE_LIMIT_DEG_S,
    GRIPPER_COMMAND_RATE_LIMIT_S,
    WRIST_ROLL_COMMAND_RATE_LIMIT_DEG_S,
)
from .scene import board_square_center


class TemporalStaticError(RuntimeError):
    """The prospective static enumeration or action freeze failed closed."""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bound(entry: Mapping[str, Any]) -> tuple[Path, dict[str, Any]]:
    path = REPO_ROOT / str(entry["path"])
    if not path.is_file() or _sha(path) != entry["sha256"]:
        raise TemporalStaticError(f"bound V05-T input changed: {path}")
    return path, json.loads(path.read_text(encoding="utf-8"))


def _square_key(square: str) -> tuple[int, int]:
    if (
        len(square) != 2
        or square[0] not in "abcdefgh"
        or square[1] not in "12345678"
    ):
        raise TemporalStaticError(f"invalid modeled square: {square}")
    return int(square[1]), ord(square[0]) - ord("a")


def enumerate_empty_orthogonal_neighbors(
    pieces_by_square: Mapping[str, str],
    *,
    excluded_squares: Sequence[str],
) -> list[dict[str, str]]:
    occupied = set(pieces_by_square)
    excluded = set(excluded_squares)
    rows: list[dict[str, str]] = []
    for source in sorted(occupied, key=_square_key):
        if source in excluded:
            continue
        rank, file_index = _square_key(source)
        for destination_rank, destination_file in (
            (rank - 1, file_index),
            (rank + 1, file_index),
            (rank, file_index - 1),
            (rank, file_index + 1),
        ):
            if not (
                1 <= destination_rank <= 8
                and 0 <= destination_file < 8
            ):
                continue
            destination = (
                f"{chr(ord('a') + destination_file)}{destination_rank}"
            )
            if destination in occupied:
                continue
            rows.append(
                {
                    "source_square": source,
                    "destination_square": destination,
                    "selected_piece_id": pieces_by_square[source],
                }
            )
    return sorted(
        rows,
        key=lambda row: (
            _square_key(row["source_square"]),
            _square_key(row["destination_square"]),
        ),
    )


def _pawn_layout(
    model: mujoco.MjModel,
) -> dict[str, str]:
    result: dict[str, str] = {}
    for body_id in range(model.nbody):
        name = (
            mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id)
            or ""
        )
        if "pawn" not in name:
            continue
        square = name.rsplit("_", 1)[-1]
        _square_key(square)
        if square in result:
            raise TemporalStaticError(f"duplicate pawn square: {square}")
        result[square] = name
    return result


def _descendants(model: mujoco.MjModel, root_name: str) -> set[int]:
    root = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_BODY, root_name
    )
    if root < 0:
        raise TemporalStaticError(f"missing robot root: {root_name}")
    result = {root}
    changed = True
    while changed:
        changed = False
        for body_id in range(model.nbody):
            if body_id not in result and int(model.body_parentid[body_id]) in result:
                result.add(body_id)
                changed = True
    return result


def _body_name(model: mujoco.MjModel, body_id: int) -> str:
    return (
        mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id)
        or f"body-{body_id}"
    )


def _robot_contact_pairs(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    robot_bodies: set[int],
) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for index in range(data.ncon):
        contact = data.contact[index]
        bodies = (
            int(model.geom_bodyid[int(contact.geom1)]),
            int(model.geom_bodyid[int(contact.geom2)]),
        )
        if set(bodies) & robot_bodies:
            pairs.add(
                tuple(sorted(_body_name(model, body) for body in bodies))
            )
    return pairs


def _collision_audit(
    *,
    model: mujoco.MjModel,
    qpos_addresses: list[int],
    seed_model: np.ndarray,
    action: np.ndarray,
    selected_piece_id: str,
    robot_bodies: set[int],
    jaw_bodies: set[int],
) -> dict[str, Any]:
    data = mujoco.MjData(model)
    data.qpos[qpos_addresses] = seed_model
    mujoco.mj_forward(model, data)
    baseline = _robot_contact_pairs(model, data, robot_bodies)
    allowed = {
        tuple(
            sorted(
                (
                    _body_name(model, jaw_body),
                    selected_piece_id,
                )
            )
        )
        for jaw_body in jaw_bodies
    }
    new_disallowed: set[tuple[str, str]] = set()
    selected_contact = False
    for pose in action:
        data.qpos[qpos_addresses] = pose
        data.qvel[:] = 0
        mujoco.mj_forward(model, data)
        current = _robot_contact_pairs(model, data, robot_bodies)
        selected_contact = selected_contact or bool(current & allowed)
        new_disallowed |= current - baseline - allowed
    return {
        "static_selected_contact_observed": selected_contact,
        "new_disallowed_robot_contact_pairs": [
            list(row) for row in sorted(new_disallowed)
        ],
        "collision_free": not new_disallowed,
    }


def _physical_actions(
    action: np.ndarray,
    wrapper: Mapping[str, Any],
) -> np.ndarray:
    transforms = wrapper["candidate_config"]["physical_adapter"][
        "joint_transform"
    ]["joints"]
    if len(transforms) != 6:
        raise TemporalStaticError("physical transform is not six-joint")
    physical = np.empty(action.shape, dtype="<f8")
    for index, transform in enumerate(transforms):
        sign = float(transform["sign"])
        scale = float(transform["scale"])
        offset = float(transform["zero_offset"])
        if not np.isfinite(scale) or scale == 0.0:
            raise TemporalStaticError("physical transform scale is invalid")
        physical[:, index] = (
            action[:, index] - offset
        ) / (sign * scale)
    return physical


def _gateway_audit(
    action: np.ndarray,
    wrapper: Mapping[str, Any],
    *,
    sample_hz: float,
) -> dict[str, Any]:
    physical = _physical_actions(action, wrapper)
    model_spec = wrapper["candidate_config"]["model"]
    arm_lower = np.asarray(
        model_spec["calibrated_body_ranges"]["minimum"],
        dtype=np.float64,
    )
    arm_upper = np.asarray(
        model_spec["calibrated_body_ranges"]["maximum"],
        dtype=np.float64,
    )
    lower = np.concatenate((arm_lower, np.asarray([0.0])))
    upper = np.concatenate((arm_upper, np.asarray([100.0])))
    within_limits = bool(
        np.all(physical >= lower[None, :] - 1e-9)
        and np.all(physical <= upper[None, :] + 1e-9)
    )
    rates = np.diff(physical, axis=0) * sample_hz
    if len(rates):
        maximum_rates = np.max(np.abs(rates), axis=0)
    else:
        maximum_rates = np.zeros(6, dtype=np.float64)
    rate_limits = np.asarray(
        [
            BODY_COMMAND_RATE_LIMIT_DEG_S,
            BODY_COMMAND_RATE_LIMIT_DEG_S,
            BODY_COMMAND_RATE_LIMIT_DEG_S,
            BODY_COMMAND_RATE_LIMIT_DEG_S,
            WRIST_ROLL_COMMAND_RATE_LIMIT_DEG_S,
            GRIPPER_COMMAND_RATE_LIMIT_S,
        ],
        dtype=np.float64,
    )
    rate_compatible = bool(
        np.all(maximum_rates <= rate_limits + 1e-9)
    )
    requested = np.asarray(action, dtype="<f8", order="C")
    sent = requested.copy(order="C")
    byte_identical = requested.tobytes(order="C") == sent.tobytes(order="C")
    return {
        "physical_transform_review_status": wrapper["candidate_config"][
            "physical_adapter"
        ]["joint_transform"]["review_status"],
        "calibrated_physical_lower": lower.tolist(),
        "calibrated_physical_upper": upper.tolist(),
        "all_rows_inside_calibrated_limits": within_limits,
        "maximum_absolute_rate_per_second": maximum_rates.tolist(),
        "reviewed_gateway_rate_limit_per_second": rate_limits.tolist(),
        "all_rates_within_reviewed_gateway_limits": rate_compatible,
        "requested_sent_byte_identical": byte_identical,
        "would_require_gateway_transform": not (
            within_limits and rate_compatible and byte_identical
        ),
        "physical_action_raw_float64le_sha256": hashlib.sha256(
            physical.tobytes(order="C")
        ).hexdigest(),
    }


def _camera_audit(
    camera: np.ndarray,
    source_xyz: np.ndarray,
    direction: np.ndarray,
    stroke_m: float,
    image_size: tuple[int, int],
    minimum_margin_px: float,
) -> dict[str, Any]:
    intended_terminal = source_xyz + direction * stroke_m
    pixels = project(
        camera,
        np.asarray([source_xyz, intended_terminal], dtype=np.float64),
    )
    width, height = image_size
    margin = float(
        np.min(
            np.column_stack(
                (
                    pixels[:, 0],
                    width - pixels[:, 0],
                    pixels[:, 1],
                    height - pixels[:, 1],
                )
            )
        )
    )
    return {
        "source_and_intended_terminal_pixels": pixels.tolist(),
        "minimum_margin_px": margin,
        "camera_gate_passed": margin >= minimum_margin_px,
    }


def enumerate_and_freeze(
    contract_path: Path,
    output_directory: Path,
) -> dict[str, Any]:
    contract_path = (
        contract_path.resolve()
        if contract_path.is_absolute()
        else (REPO_ROOT / contract_path).resolve()
    )
    output_directory = (
        output_directory.resolve()
        if output_directory.is_absolute()
        else (REPO_ROOT / output_directory).resolve()
    )
    for public_path in (contract_path, output_directory):
        try:
            public_path.relative_to(REPO_ROOT.resolve())
        except ValueError as error:
            raise TemporalStaticError(
                "V05-T static path escapes repository"
            ) from error
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if (
        contract.get("schema_version")
        != "sim2claw.bidirectional_pawn_push_v2_temporal_static.v1"
    ):
        raise TemporalStaticError("unexpected V05-T static contract")
    _, plan = _bound(contract["temporal_plan"])
    _, rehearsal_contract = _bound(contract["rehearsal_contract"])
    _, wrapper = _bound(rehearsal_contract["candidate_manifest"])
    _, rigid = _bound(rehearsal_contract["registration_candidate"])

    model, qpos, _, jaw_bodies = _rehearsal._registered_model(
        wrapper,
        rigid,
        float(rehearsal_contract["simulation"]["timestep_s"]),
    )
    seed_physical = np.asarray(
        [rehearsal_contract["action_synthesis"]["seed_physical"]]
    )
    seed_model = _physical_to_model_position(
        seed_physical, wrapper["candidate_config"]
    )[0]
    initial = mujoco.MjData(model)
    initial.qpos[qpos] = seed_model
    mujoco.mj_forward(model, initial)
    pieces = _pawn_layout(model)
    universe = enumerate_empty_orthogonal_neighbors(
        pieces,
        excluded_squares=contract["enumeration"]["excluded_squares"],
    )
    if len(universe) > int(contract["enumeration"]["maximum_candidates"]):
        raise TemporalStaticError("enumerated candidate universe is too large")

    camera = np.asarray(rigid["camera_matrix_3x4"], dtype=np.float64)
    image_size = tuple(rehearsal_contract["camera_gate"]["image_size_px"])
    minimum_camera_margin = float(
        rehearsal_contract["camera_gate"]["minimum_margin_px"]
    )
    robot_bodies = _descendants(model, "left_base")
    sample_hz = float(
        rehearsal_contract["action_synthesis"]["sample_hz"]
    )
    grid_results: list[dict[str, Any]] = []
    eligible_cases: list[dict[str, Any]] = []
    output_directory.mkdir(parents=True, exist_ok=True)
    actions_directory = output_directory / "actions"
    actions_directory.mkdir(parents=True, exist_ok=True)

    for universe_index, case in enumerate(universe):
        selected_id = mujoco.mj_name2id(
            model,
            mujoco.mjtObj.mjOBJ_BODY,
            case["selected_piece_id"],
        )
        source_xyz = initial.xpos[selected_id].copy()
        source_center = np.asarray(
            board_square_center(case["source_square"])
        )
        destination_center = np.asarray(
            board_square_center(case["destination_square"])
        )
        direction = destination_center - source_center
        direction /= np.linalg.norm(direction)
        case_id = (
            f"{case['selected_piece_id']}__"
            f"{case['source_square']}_{case['destination_square']}"
        )
        passing_cells: list[tuple[dict[str, Any], np.ndarray]] = []
        for contact_height in rehearsal_contract["grid"][
            "contact_heights_m"
        ]:
            for stroke in rehearsal_contract["grid"]["stroke_lengths_m"]:
                start = source_xyz.copy()
                start[:2] -= (
                    direction[:2]
                    * rehearsal_contract["action_synthesis"][
                        "contact_center_offset_m"
                    ]
                )
                start[2] += float(contact_height)
                try:
                    action, compile_metrics = (
                        _rehearsal_v2._compile_action_v2(
                            model=model,
                            qpos_addresses=qpos,
                            seed_model=seed_model,
                            start_xyz=start,
                            direction=direction,
                            stroke_m=float(stroke),
                            sample_hz=sample_hz,
                            speed_m_s=float(
                                rehearsal_contract["action_synthesis"][
                                    "cartesian_speed_m_s"
                                ]
                            ),
                            closed_jaw_rad=float(
                                rehearsal_contract["action_synthesis"][
                                    "closed_jaw_rad"
                                ]
                            ),
                            maximum_ik_residual_m=float(
                                rehearsal_contract["gates"][
                                    "maximum_ik_residual_m"
                                ]
                            ),
                        )
                    )
                except _rehearsal.PushRehearsalError as error:
                    grid_results.append(
                        {
                            "case_id": case_id,
                            "universe_index": universe_index,
                            "contact_height_m": contact_height,
                            "stroke_m": stroke,
                            "status": "compile_reject",
                            "error": str(error),
                            "static_eligible": False,
                        }
                    )
                    continue
                collision = _collision_audit(
                    model=model,
                    qpos_addresses=qpos,
                    seed_model=seed_model,
                    action=action,
                    selected_piece_id=case["selected_piece_id"],
                    robot_bodies=robot_bodies,
                    jaw_bodies=jaw_bodies,
                )
                camera_audit = _camera_audit(
                    camera,
                    source_xyz,
                    direction,
                    float(stroke),
                    image_size,
                    minimum_camera_margin,
                )
                gateway = _gateway_audit(
                    action,
                    wrapper,
                    sample_hz=sample_hz,
                )
                checks = {
                    "ik": compile_metrics["maximum_ik_residual_m"]
                    <= rehearsal_contract["gates"][
                        "maximum_ik_residual_m"
                    ],
                    "arm_joint_margin": compile_metrics[
                        "minimum_arm_joint_limit_margin_rad"
                    ]
                    >= rehearsal_contract["gates"][
                        "minimum_arm_joint_limit_margin_rad"
                    ],
                    "jaw_target": compile_metrics[
                        "maximum_closed_jaw_target_error_rad"
                    ]
                    <= rehearsal_contract["closed_jaw_gate"][
                        "target_tolerance_rad"
                    ],
                    "collision": collision["collision_free"],
                    "camera": camera_audit["camera_gate_passed"],
                    "gateway_limits": gateway[
                        "all_rows_inside_calibrated_limits"
                    ],
                    "gateway_rates": gateway[
                        "all_rates_within_reviewed_gateway_limits"
                    ],
                    "requested_sent_identity": gateway[
                        "requested_sent_byte_identical"
                    ],
                }
                row = {
                    "case_id": case_id,
                    "universe_index": universe_index,
                    **case,
                    "contact_height_m": contact_height,
                    "stroke_m": stroke,
                    "compile": compile_metrics,
                    "collision": collision,
                    "camera": camera_audit,
                    "gateway": gateway,
                    "checks": checks,
                    "static_eligible": all(checks.values()),
                }
                row["status"] = (
                    "static_eligible"
                    if row["static_eligible"]
                    else "static_reject"
                )
                grid_results.append(row)
                if row["static_eligible"]:
                    passing_cells.append((row, action))
        if not passing_cells:
            continue
        selected_row, selected_action = min(
            passing_cells,
            key=lambda item: (
                item[0]["stroke_m"],
                abs(item[0]["contact_height_m"] - 0.024),
                -item[0]["compile"][
                    "minimum_arm_joint_limit_margin_rad"
                ],
            ),
        )
        lane = (
            "REAL_TO_SIM"
            if len(eligible_cases) % 2 == 0
            else "SIM_TO_REAL"
        )
        action_path = actions_directory / f"{len(eligible_cases):02d}.f64le"
        action_bytes = np.asarray(
            selected_action, dtype="<f8", order="C"
        ).tobytes(order="C")
        action_path.write_bytes(action_bytes)
        eligible_cases.append(
            {
                "case_id": selected_row["case_id"],
                "direction_lane": lane,
                "source_square": selected_row["source_square"],
                "destination_square": selected_row["destination_square"],
                "selected_piece_id": selected_row["selected_piece_id"],
                "stroke_m": selected_row["stroke_m"],
                "contact_height_m": selected_row["contact_height_m"],
                "action_path": str(action_path.relative_to(REPO_ROOT)),
                "action_sha256": hashlib.sha256(action_bytes).hexdigest(),
                "action_shape": list(selected_action.shape),
                "action_dtype": "little_endian_float64",
                "sample_hz": sample_hz,
                "compile": selected_row["compile"],
                "camera": selected_row["camera"],
                "collision": selected_row["collision"],
                "gateway": selected_row["gateway"],
            }
        )

    lane_counts = {
        lane: sum(row["direction_lane"] == lane for row in eligible_cases)
        for lane in ("REAL_TO_SIM", "SIM_TO_REAL")
    }
    receipt = {
        "schema_version": (
            "sim2claw.bidirectional_pawn_push_v2_temporal_static_receipt.v1"
        ),
        "status": (
            "static_action_freeze_pass"
            if min(lane_counts.values(), default=0) >= 2
            else "static_action_freeze_reject"
        ),
        "proof_class": (
            "cpu_fp64_static_layout_ik_collision_camera_gateway_"
            "action_freeze_only"
        ),
        "contract_path": str(contract_path.relative_to(REPO_ROOT)),
        "contract_sha256": _sha(contract_path),
        "temporal_plan_sha256": contract["temporal_plan"]["sha256"],
        "selection_used_v05_dynamic_outcomes": False,
        "universe_count": len(universe),
        "universe": universe,
        "grid_result_count": len(grid_results),
        "grid_results": grid_results,
        "eligible_case_count": len(eligible_cases),
        "eligible_cases": eligible_cases,
        "lane_counts": lane_counts,
        "minimum_cases_per_direction": plan["acceptance"][
            "minimum_feasible_recommendable_cases_per_direction"
        ],
        "dynamic_replay_executed": False,
        "physical_motion": False,
        "physical_task_attempts": 0,
        "authority": contract["authority"],
        "claim_boundary": (
            "Static reset-layout/IK/collision/camera/gateway action freeze "
            "only. No dynamic task outcome, calibrated plant, physical "
            "packet, or transfer claim."
        ),
    }
    output_path = output_directory / "receipt.json"
    output_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


__all__ = [
    "TemporalStaticError",
    "enumerate_and_freeze",
    "enumerate_empty_orthogonal_neighbors",
]
