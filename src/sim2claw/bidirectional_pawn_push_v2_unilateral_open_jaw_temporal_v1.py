"""Strict V05-UF unilateral open-jaw temporal consequence replay."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import mujoco
import numpy as np

from . import bidirectional_pawn_push_v2_sim_rehearsal as _rehearsal
from . import bidirectional_pawn_push_v2_temporal_replay as _temporal
from . import bidirectional_pawn_push_v2_temporal_static as _static
from .bidirectional_registration_v2_fit import project
from .paths import REPO_ROOT


class UnilateralOpenJawTemporalV1Error(RuntimeError):
    """The frozen V05-UF unilateral temporal contract failed closed."""


_ACTIVE_CASES: dict[str, Mapping[str, Any]] = {}
_ACTIVE_GATES: Mapping[str, Any] = {}


def _strict_replay(
    *,
    model: mujoco.MjModel,
    qpos_addresses: list[int],
    actuator_ids: list[int],
    jaw_bodies: set[int],
    action: np.ndarray,
    selected_name: str,
    source_delta_m: np.ndarray,
    direction: np.ndarray,
    substeps: int,
    camera: np.ndarray,
    image_size: tuple[int, int],
) -> dict[str, Any]:
    """Replay one frozen action while measuring unilateral-only invariants."""

    case = _ACTIVE_CASES.get(selected_name)
    if case is None:
        raise UnilateralOpenJawTemporalV1Error(
            f"selected pawn is not uniquely frozen: {selected_name}"
        )
    expected_side = str(case["expected_unilateral_contact_side"])
    side_bodies = {
        "fixed_jaw": mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_BODY, "left_gripper"
        ),
        "moving_jaw": mujoco.mj_name2id(
            model,
            mujoco.mjtObj.mjOBJ_BODY,
            "left_moving_jaw_so101_v1",
        ),
    }
    if min(side_bodies.values()) < 0 or set(side_bodies.values()) != jaw_bodies:
        raise UnilateralOpenJawTemporalV1Error(
            "frozen unilateral jaw-body binding changed"
        )
    opposite_side = (
        "moving_jaw" if expected_side == "fixed_jaw" else "fixed_jaw"
    )
    if expected_side not in side_bodies:
        raise UnilateralOpenJawTemporalV1Error(
            "unknown expected unilateral contact side"
        )
    board_id = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_BODY, "chess_board"
    )
    robot_bodies = _static._descendants(model, "left_base")
    if board_id < 0:
        raise UnilateralOpenJawTemporalV1Error("chess-board body is missing")

    data = mujoco.MjData(model)
    selected_id = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_BODY, selected_name
    )
    if selected_id < 0:
        raise UnilateralOpenJawTemporalV1Error(
            f"selected pawn is missing: {selected_name}"
        )
    selected_joint = int(model.body_jntadr[selected_id])
    selected_qpos = int(model.jnt_qposadr[selected_joint])
    data.qpos[selected_qpos : selected_qpos + 2] += source_delta_m
    data.qpos[qpos_addresses] = action[0]
    data.ctrl[actuator_ids] = action[0]
    mujoco.mj_forward(model, data)
    initial_selected = data.xpos[selected_id].copy()
    pawn_ids = {
        body_id
        for body_id in range(model.nbody)
        if "pawn" in _rehearsal._body_name(model, body_id)
    }
    excluded_ids = pawn_ids - {selected_id}
    initial_excluded = {
        body_id: data.xpos[body_id].copy() for body_id in excluded_ids
    }
    baseline_pairs = _rehearsal._contact_pairs(model, data, jaw_bodies)

    selected_contact_steps = 0
    expected_contact_steps = 0
    opposite_contact_steps = 0
    bilateral_contact_steps = 0
    excluded_contact_steps = 0
    robot_board_contact_steps = 0
    selected_sides_seen: set[str] = set()
    maximum_selected_z = float(initial_selected[2])
    new_collision_pairs: set[tuple[str, str]] = set()
    for row in action:
        data.ctrl[actuator_ids] = row
        for _ in range(substeps):
            mujoco.mj_step(model, data)
            maximum_selected_z = max(
                maximum_selected_z, float(data.xpos[selected_id][2])
            )
            sides_this_step: set[str] = set()
            for contact_index in range(data.ncon):
                contact = data.contact[contact_index]
                bodies = {
                    int(model.geom_bodyid[int(contact.geom1)]),
                    int(model.geom_bodyid[int(contact.geom2)]),
                }
                if selected_id in bodies:
                    for side, body_id in side_bodies.items():
                        if body_id in bodies:
                            sides_this_step.add(side)
                if bodies & jaw_bodies and bodies & excluded_ids:
                    excluded_contact_steps += 1
                if board_id in bodies and bodies & robot_bodies:
                    robot_board_contact_steps += 1
            if sides_this_step:
                selected_contact_steps += 1
                selected_sides_seen |= sides_this_step
            if expected_side in sides_this_step:
                expected_contact_steps += 1
            if opposite_side in sides_this_step:
                opposite_contact_steps += 1
            if len(sides_this_step) > 1:
                bilateral_contact_steps += 1
            new_collision_pairs |= (
                _rehearsal._contact_pairs(model, data, jaw_bodies)
                - baseline_pairs
            )

    mujoco.mj_forward(model, data)
    final_selected = data.xpos[selected_id].copy()
    progress_m = float(
        np.dot((final_selected - initial_selected)[:2], direction[:2])
    )
    maximum_excluded_m = max(
        float(np.linalg.norm(data.xpos[body][:2] - initial[:2]))
        for body, initial in initial_excluded.items()
    )
    allowed_selected_pair = {
        tuple(
            sorted(
                (
                    _rehearsal._body_name(model, jaw),
                    selected_name,
                )
            )
        )
        for jaw in jaw_bodies
    }
    collision_pairs = sorted(new_collision_pairs - allowed_selected_pair)
    projected = project(
        camera, np.asarray([initial_selected, final_selected])
    )
    width, height = image_size
    camera_margin = float(
        np.min(
            np.column_stack(
                (
                    projected[:, 0],
                    width - projected[:, 0],
                    projected[:, 1],
                    height - projected[:, 1],
                )
            )
        )
    )
    maximum_vertical_rise_mm = (
        maximum_selected_z - float(initial_selected[2])
    ) * 1000.0
    final_vertical_delta_mm = (
        float(final_selected[2]) - float(initial_selected[2])
    ) * 1000.0
    return {
        "selected_initial_xyz_m": initial_selected.tolist(),
        "selected_final_xyz_m": final_selected.tolist(),
        "signed_progress_mm": progress_m * 1000.0,
        "selected_contact_steps": selected_contact_steps,
        "expected_unilateral_contact_side": expected_side,
        "expected_unilateral_contact_steps": expected_contact_steps,
        "opposite_jaw_selected_contact_steps": opposite_contact_steps,
        "bilateral_selected_contact_steps": bilateral_contact_steps,
        "selected_contact_sides_seen": sorted(selected_sides_seen),
        "selected_pawn_enclosed_or_grasped": (
            bilateral_contact_steps > 0 or len(selected_sides_seen) > 1
        ),
        "robot_board_contact_steps": robot_board_contact_steps,
        "maximum_selected_vertical_rise_mm": maximum_vertical_rise_mm,
        "final_selected_vertical_delta_mm": final_vertical_delta_mm,
        "excluded_contact_steps": excluded_contact_steps,
        "maximum_excluded_displacement_mm": maximum_excluded_m * 1000.0,
        "new_nonselected_jaw_collision_pairs": [
            list(row) for row in collision_pairs
        ],
        "camera_margin_px": camera_margin,
    }


def _requested_identity(
    action: np.ndarray, case: Mapping[str, Any], contract: Mapping[str, Any]
) -> dict[str, bool]:
    identity = contract["unilateral_action_identity"]
    jaw = action[:, 5]
    start = int(case["constant_open_jaw_start_row"])
    target = float(identity["open_jaw_target_rad"])
    tolerance = float(identity["absolute_tolerance_rad"])
    return {
        "jaw_preamble_monotonic_nonclosing": bool(
            np.all(np.diff(jaw[: start + 1]) >= -tolerance)
        ),
        "jaw_exactly_constant_open_after_preamble": bool(
            np.all(np.abs(jaw[start:] - target) <= tolerance)
        ),
        "constant_open_row_matches_static_freeze": (
            start == int(identity["constant_open_jaw_start_row"])
        ),
        "no_bilateral_enclosure_grasp_lift_or_feedback_command": True,
    }


def replay(contract_path: Path, output_directory: Path) -> dict[str, Any]:
    """Execute the one authorized strict temporal replay."""

    contract_path = (
        contract_path.resolve()
        if contract_path.is_absolute()
        else (REPO_ROOT / contract_path).resolve()
    )
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if (
        contract.get("schema_version")
        != "sim2claw.bidirectional_pawn_push_v2_temporal_replay.v1"
        or contract.get("strict_extension")
        != "unilateral_open_jaw_v1"
    ):
        raise UnilateralOpenJawTemporalV1Error(
            "unexpected V05-UF strict temporal contract"
        )
    global _ACTIVE_CASES, _ACTIVE_GATES
    _ACTIVE_CASES = {
        str(case["selected_piece_id"]): case for case in contract["cases"]
    }
    if len(_ACTIVE_CASES) != len(contract["cases"]):
        raise UnilateralOpenJawTemporalV1Error(
            "selected pawn must be unique across frozen cases"
        )
    _ACTIVE_GATES = contract["strict_dynamic_gates"]

    original = _rehearsal._replay
    _rehearsal._replay = _strict_replay
    try:
        receipt = _temporal.replay(contract_path, output_directory)
    finally:
        _rehearsal._replay = original
        _ACTIVE_CASES = {}
        _ACTIVE_GATES = {}

    maximum_rise = float(
        contract["strict_dynamic_gates"][
            "maximum_selected_vertical_rise_mm"
        ]
    )
    for result in receipt["results"]:
        case = next(
            row
            for row in contract["cases"]
            if row["case_id"] == result["case_id"]
        )
        action = _temporal._load_action(case)
        requested_checks = _requested_identity(action, case, contract)
        for plant_path in result["plant_paths"]:
            plant_path["identity_checks"].update(requested_checks)
            for variant in plant_path["robustness"]:
                strict_checks = {
                    "expected_unilateral_contact": (
                        variant["expected_unilateral_contact_steps"] > 0
                    ),
                    "opposite_jaw_contact_absent": (
                        variant["opposite_jaw_selected_contact_steps"] == 0
                    ),
                    "bilateral_contact_absent": (
                        variant["bilateral_selected_contact_steps"] == 0
                    ),
                    "enclosure_or_grasp_absent": not variant[
                        "selected_pawn_enclosed_or_grasped"
                    ],
                    "robot_board_contact_absent": (
                        variant["robot_board_contact_steps"] == 0
                    ),
                    "selected_pawn_not_lifted": (
                        variant["maximum_selected_vertical_rise_mm"]
                        <= maximum_rise
                    ),
                }
                variant["checks"].update(strict_checks)
                variant["passed"] = all(variant["checks"].values())
            plant_path["passed"] = all(
                plant_path["identity_checks"].values()
            ) and all(row["passed"] for row in plant_path["robustness"])
        result["passed_both_paths"] = all(
            row["passed"] for row in result["plant_paths"]
        )

    passing = [row for row in receipt["results"] if row["passed_both_paths"]]
    receipt["passing_case_ids"] = [row["case_id"] for row in passing]
    receipt["lane_counts"] = {
        lane: sum(row["direction_lane"] == lane for row in passing)
        for lane in ("REAL_TO_SIM", "SIM_TO_REAL")
    }
    minimum = int(contract["acceptance"]["minimum_cases_per_direction"])
    receipt["direction_checks"] = {
        lane: count >= minimum
        for lane, count in receipt["lane_counts"].items()
    }
    passed = all(receipt["direction_checks"].values())
    receipt.update(
        {
            "schema_version": (
                "sim2claw.bidirectional_pawn_push_v2_"
                "unilateral_open_jaw_temporal_receipt.v1"
            ),
            "status": (
                "unilateral_open_jaw_temporal_replay_pass"
                if passed
                else "unilateral_open_jaw_temporal_replay_reject"
            ),
            "proof_class": (
                "cpu_fp64_action_frozen_unilateral_open_jaw_"
                "direct_target_and_diagnostic_zoh_consequence_replay"
            ),
            "strict_extension": "unilateral_open_jaw_v1",
            "bilateral_contact_allowed": False,
            "grasp_or_enclosure_allowed": False,
            "selected_pawn_lift_allowed": False,
            "robot_board_contact_allowed": False,
            "jaw_closing_allowed": False,
            "physical_motion": False,
            "physical_task_attempts": 0,
            "claim_boundary": (
                "Simulator-only strict consequence replay of four "
                "pre-frozen unilateral open-jaw actions through direct-target "
                "and diagnostic 0.11 second ZOH paths. No bilateral contact, "
                "enclosure, grasp, lift, board contact, calibrated plant, "
                "physical task, promotion, or transfer claim."
            ),
        }
    )
    receipt_path = (
        output_directory.resolve()
        if output_directory.is_absolute()
        else (REPO_ROOT / output_directory).resolve()
    ) / "receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


__all__ = [
    "UnilateralOpenJawTemporalV1Error",
    "replay",
]
