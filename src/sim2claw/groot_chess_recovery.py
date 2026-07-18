"""Recovery-focused GR00T demonstrations and frozen robustness evaluation."""

from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import mujoco
import numpy as np

from .chess_task import ChessRookLiftEnv, _goal_vector
from .grasp import (
    JAW_OPEN_RAD,
    JAW_SHUT_RAD,
    NECK_HEIGHT_M,
    _piece_bodies,
    _pinch_point,
    _solve_reach,
)
from .groot_chess import (
    _apply_sparse_board_curriculum,
    _diagnostic_reward,
    _episode_shim,
    _sha256_file,
    _stats,
    _write_json,
    _write_jsonl,
    _write_video,
    evaluate_episode,
    groot_task_contract_sha256,
    load_groot_task_contract,
)
from .paths import REPO_ROOT
from .scene import ROBOT_JOINTS, board_square_center


DEFAULT_RECOVERY_TASK_CONFIG = (
    REPO_ROOT / "configs" / "tasks" / "chess_pick_place_groot_recovery_v2.json"
)
RECOVERY_FAMILIES = {
    "nominal",
    "pose_error",
    "distractor_proximity",
    "contact_recovery",
}


def load_recovery_task_contract(
    path: Path = DEFAULT_RECOVERY_TASK_CONFIG,
) -> dict[str, Any]:
    contract = json.loads(path.read_text(encoding="utf-8"))
    if (
        contract.get("schema_version")
        != "sim2claw.chess_pick_place_groot_recovery_task.v2"
    ):
        raise ValueError("unsupported GR00T recovery task contract")
    if not contract.get("frozen_before_training"):
        raise ValueError("GR00T recovery task must be frozen before training")
    if not contract["coordination"]["nominal_v1_must_remain_unchanged"]:
        raise ValueError("recovery task must preserve the frozen v1 contract")
    if contract["base_task"]["contract_sha256"] != groot_task_contract_sha256():
        raise ValueError("frozen v1 task identity does not match recovery contract")

    base = load_groot_task_contract()
    training_cases = {str(row["case_id"]) for row in base["training_cases"]}
    held_out_cases = {str(row["case_id"]) for row in base["held_out_cases"]}
    training = contract["training_episodes"]
    held_out = contract["held_out_episodes"]
    if len(training) < 48 or len(held_out) < 24:
        raise ValueError("recovery contract does not meet its frozen episode counts")
    if {int(row["seed"]) for row in training} & {
        int(row["seed"]) for row in held_out
    }:
        raise ValueError("recovery training and held-out seeds must be disjoint")
    if any(str(row["case_id"]) not in training_cases for row in training):
        raise ValueError("recovery training row references a non-training case")
    if any(str(row["case_id"]) not in held_out_cases for row in held_out):
        raise ValueError("recovery held-out row references a non-held-out case")
    if any(int(row.get("training_rows", -1)) != 0 for row in held_out):
        raise ValueError("recovery held-out rows must contribute zero training rows")
    for split_rows in (training, held_out):
        families = {str(row["family"]) for row in split_rows}
        if families != RECOVERY_FAMILIES:
            raise ValueError("each recovery split must cover every frozen family")
        for row in split_rows:
            _validate_episode_row(row)

    train_signatures = {_perturbation_signature(row) for row in training}
    held_out_signatures = {_perturbation_signature(row) for row in held_out}
    if train_signatures & held_out_signatures:
        raise ValueError("held-out perturbation combinations overlap training")
    return contract


def _validate_episode_row(row: dict[str, Any]) -> None:
    family = str(row["family"])
    if family not in RECOVERY_FAMILIES:
        raise ValueError(f"unsupported recovery family: {family}")
    offset = row["piece_planar_offset_m"]
    if len(offset) != 2 or not all(math.isfinite(float(value)) for value in offset):
        raise ValueError("piece planar offset must be a finite two-vector")
    if abs(float(row["piece_yaw_deg"])) > 25.0:
        raise ValueError("piece yaw exceeds the frozen robustness envelope")
    spacing = row["distractor_spacing_m"]
    slip = float(row["slip_m"])
    if family == "distractor_proximity":
        if spacing is None or not 0.05 <= float(spacing) <= 0.07:
            raise ValueError("distractor spacing is outside the frozen envelope")
        if int(row["distractor_side"]) not in {-1, 1}:
            raise ValueError("distractor side must be signed")
    elif spacing is not None or int(row["distractor_side"]) != 0:
        raise ValueError("only distractor episodes may reposition the other piece")
    if family == "contact_recovery":
        if not 0.003 <= slip <= 0.006 or int(row["slip_side"]) not in {-1, 1}:
            raise ValueError("contact recovery slip is outside the frozen envelope")
    elif slip != 0.0 or int(row["slip_side"]) != 0:
        raise ValueError("only contact recovery episodes may inject slip")


def _perturbation_signature(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        str(row["family"]),
        tuple(float(value) for value in row["piece_planar_offset_m"]),
        float(row["piece_yaw_deg"]),
        None
        if row["distractor_spacing_m"] is None
        else float(row["distractor_spacing_m"]),
        int(row["distractor_side"]),
        float(row["slip_m"]),
        int(row["slip_side"]),
    )


def recovery_task_contract_sha256(
    path: Path = DEFAULT_RECOVERY_TASK_CONFIG,
) -> str:
    payload = json.dumps(
        load_recovery_task_contract(path),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass
class GrootRecoveryEpisode:
    case_id: str
    instruction: str
    piece: str
    target_square: str
    seed: int
    perturbation: dict[str, Any]
    states: np.ndarray
    actions: np.ndarray
    rewards: np.ndarray
    phases: list[str]
    frames: list[np.ndarray]
    verdict: dict[str, Any]
    maximum_ik_residual_m: float
    contact_metrics: dict[str, Any]


def _free_joint_addresses(env: ChessRookLiftEnv, piece_name: str) -> tuple[int, int]:
    joint_id = mujoco.mj_name2id(
        env.model,
        mujoco.mjtObj.mjOBJ_JOINT,
        f"{piece_name}_free",
    )
    if joint_id < 0:
        raise ValueError(f"piece has no free joint: {piece_name}")
    return int(env.model.jnt_qposadr[joint_id]), int(env.model.jnt_dofadr[joint_id])


def _set_piece_yaw(env: ChessRookLiftEnv, yaw_deg: float) -> None:
    if yaw_deg == 0.0:
        return
    qpos_address, dof_address = _free_joint_addresses(env, env.piece_name)
    yaw = math.radians(yaw_deg)
    delta = np.asarray(
        [math.cos(yaw / 2.0), 0.0, 0.0, math.sin(yaw / 2.0)],
        dtype=np.float64,
    )
    current = np.asarray(
        env.data.qpos[qpos_address + 3 : qpos_address + 7],
        dtype=np.float64,
    ).copy()
    rotated = np.empty(4, dtype=np.float64)
    mujoco.mju_mulQuat(rotated, delta, current)
    env.data.qpos[qpos_address + 3 : qpos_address + 7] = rotated
    env.data.qvel[dof_address : dof_address + 6] = 0.0
    mujoco.mj_forward(env.model, env.data)


def _lateral_direction(env: ChessRookLiftEnv) -> np.ndarray:
    piece_xy = env.piece_position()[:2]
    away = env.mount[:2] - piece_xy
    away /= max(float(np.linalg.norm(away)), 1e-9)
    return np.asarray([-away[1], away[0]], dtype=np.float64)


def _place_distractor(
    env: ChessRookLiftEnv,
    contract: dict[str, Any],
    spacing_m: float,
    side: int,
    target_xy: np.ndarray,
) -> str:
    active = [
        name
        for name in contract["scene"]["active_pieces"]
        if name != env.piece_name
    ]
    if len(active) != 1:
        raise ValueError("recovery curriculum requires exactly one distractor")
    distractor = active[0]
    qpos_address, dof_address = _free_joint_addresses(env, distractor)
    board_center = 0.5 * (
        np.asarray(board_square_center("d4"), dtype=np.float64)[:2]
        + np.asarray(board_square_center("e5"), dtype=np.float64)[:2]
    )
    inward = board_center - env.piece_position()[:2]
    inward /= max(float(np.linalg.norm(inward)), 1e-9)
    travel = np.asarray(target_xy, dtype=np.float64) - env.piece_position()[:2]
    travel /= max(float(np.linalg.norm(travel)), 1e-9)
    direction = float(side) * np.asarray([-travel[1], travel[0]]) + 0.25 * inward
    direction /= max(float(np.linalg.norm(direction)), 1e-9)
    xy = env.piece_position()[:2] + spacing_m * direction
    env.data.qpos[qpos_address : qpos_address + 2] = xy
    env.data.qvel[dof_address : dof_address + 6] = 0.0
    mujoco.mj_forward(env.model, env.data)
    return distractor


def _inject_target_slip(env: ChessRookLiftEnv, slip_m: float, side: int) -> None:
    qpos_address, dof_address = _free_joint_addresses(env, env.piece_name)
    env.data.qpos[qpos_address : qpos_address + 2] += (
        float(side) * slip_m * _lateral_direction(env)
    )
    env.data.qvel[dof_address : dof_address + 6] = 0.0
    mujoco.mj_forward(env.model, env.data)


def _jaw_piece_contacts(env: ChessRookLiftEnv) -> tuple[set[str], set[int]]:
    pieces = _piece_bodies(env.model)
    body_to_name = {body_id: name for name, body_id in pieces.items()}
    names: set[str] = set()
    target_jaws: set[int] = set()
    for contact_index in range(env.data.ncon):
        contact = env.data.contact[contact_index]
        bodies = {
            int(env.model.geom_bodyid[contact.geom1]),
            int(env.model.geom_bodyid[contact.geom2]),
        }
        jaw_hits = bodies & env.jaw_bodies
        piece_hits = bodies & set(body_to_name)
        if not jaw_hits or not piece_hits:
            continue
        for body_id in piece_hits:
            names.add(body_to_name[body_id])
            if body_id == env.piece_body:
                target_jaws.update(jaw_hits)
    return names, target_jaws


def finalize_recovery_verdict(
    base_verdict: dict[str, Any],
    recovery_contract: dict[str, Any],
    *,
    perturbation_family: str,
    target_piece: str,
    contact_metrics: dict[str, Any],
) -> dict[str, Any]:
    verdict = copy.deepcopy(base_verdict)
    evaluator = recovery_contract["robustness_evaluator"]
    gates = verdict["gates"]
    maximum_other = float(contact_metrics["maximum_other_piece_displacement_m"])
    gates["maximum_other_piece_displacement"]["measured"] = maximum_other
    gates["maximum_other_piece_displacement"]["threshold"] = float(
        evaluator["maximum_other_piece_displacement_m"]
    )
    gates["maximum_other_piece_displacement"]["passed"] = (
        maximum_other <= float(evaluator["maximum_other_piece_displacement_m"])
    )
    gates["first_piece_contact_is_target"] = {
        "measured": contact_metrics["first_piece_contact"],
        "comparison": "==",
        "threshold": target_piece,
        "passed": contact_metrics["first_piece_contact"] == target_piece,
    }
    gates["wrong_piece_jaw_contacts"] = {
        "measured": len(contact_metrics["wrong_piece_contacts"]),
        "comparison": "==",
        "threshold": 0,
        "passed": not contact_metrics["wrong_piece_contacts"],
    }
    expected_faults = (
        int(recovery_contract["recovery_episode"]["fault_injection_count"])
        if perturbation_family == "contact_recovery"
        else 0
    )
    gates["declared_fault_injections"] = {
        "measured": int(contact_metrics["fault_injection_count"]),
        "comparison": "==",
        "threshold": expected_faults,
        "passed": int(contact_metrics["fault_injection_count"]) == expected_faults,
    }
    if perturbation_family == "contact_recovery":
        minimum_events = int(
            recovery_contract["recovery_episode"][
                "minimum_recovery_target_contact_events"
            ]
        )
        gates["recovery_target_contact_events"] = {
            "measured": int(contact_metrics["recovery_target_contact_events"]),
            "comparison": ">=",
            "threshold": minimum_events,
            "passed": int(contact_metrics["recovery_target_contact_events"])
            >= minimum_events,
        }
    verdict.update(
        {
            "schema_version": "sim2claw.groot_chess_recovery_verdict.v2",
            "evaluator_owner": evaluator["owner"],
            "perturbation_family": perturbation_family,
            "contact_metrics": contact_metrics,
        }
    )
    verdict["success"] = all(bool(gate["passed"]) for gate in gates.values())
    verdict["terminal_outcome"] = (
        "recovery_pick_place_consequence_passed"
        if verdict["success"]
        else "recovery_pick_place_consequence_gate_failed"
    )
    return verdict


def collect_recovery_expert_episode(
    recovery_contract: dict[str, Any],
    *,
    split: str,
    episode_index: int,
    render_frames: bool = True,
) -> GrootRecoveryEpisode:
    if split not in {"training", "held_out"}:
        raise ValueError("split must be training or held_out")
    base = load_groot_task_contract()
    episode_row = recovery_contract[f"{split}_episodes"][episode_index]
    case_by_id = {
        str(case["case_id"]): case for case in base[f"{split}_cases"]
    }
    case = case_by_id[str(episode_row["case_id"])]
    family = str(episode_row["family"])
    offset = tuple(float(value) for value in episode_row["piece_planar_offset_m"])
    env = ChessRookLiftEnv(
        _episode_shim(base, case),
        seed=int(episode_row["seed"]),
        piece_offset_xy_m=offset,
    )
    _apply_sparse_board_curriculum(env, base)
    _set_piece_yaw(env, float(episode_row["piece_yaw_deg"]))
    target = np.asarray(board_square_center(str(case["target_square"])), dtype=np.float64)
    distractor = None
    if family == "distractor_proximity":
        distractor = _place_distractor(
            env,
            base,
            float(episode_row["distractor_spacing_m"]),
            int(episode_row["distractor_side"]),
            target[:2],
        )
    piece_start = env.piece_position()
    initial_height = float(piece_start[2])
    all_piece_ids = _piece_bodies(env.model)
    initial_other_positions = {
        name: np.asarray(env.data.xpos[body_id], dtype=np.float64).copy()
        for name, body_id in all_piece_ids.items()
    }
    transport_target = target.copy()
    active_other_positions = [
        position
        for name, position in initial_other_positions.items()
        if name != env.piece_name and name in base["scene"]["active_pieces"]
    ]
    if active_other_positions:
        nearest_other = min(
            active_other_positions,
            key=lambda position: float(np.linalg.norm(target[:2] - position[:2])),
        )
        target_clearance = float(np.linalg.norm(target[:2] - nearest_other[:2]))
        if target_clearance < 0.14:
            away_from_other = target[:2] - nearest_other[:2]
            away_from_other /= max(float(np.linalg.norm(away_from_other)), 1e-9)
            transport_target[:2] += 0.004 * away_from_other
    max_other_displacements = {
        name: 0.0
        for name in base["scene"]["active_pieces"]
        if name != env.piece_name
    }
    kind = env.piece_name.split("_")[1]
    away = env.mount[:2] - piece_start[:2]
    away /= max(float(np.linalg.norm(away)), 1e-9)
    neck = np.asarray(
        [piece_start[0], piece_start[1], initial_height + NECK_HEIGHT_M[kind]],
        dtype=np.float64,
    )
    stand_off = neck + np.asarray([away[0] * 0.055, away[1] * 0.055, 0.03])

    renderer = (
        mujoco.Renderer(
            env.model,
            height=int(base["episode"]["render_height"]),
            width=int(base["episode"]["render_width"]),
        )
        if render_frames
        else None
    )
    states: list[np.ndarray] = []
    actions: list[np.ndarray] = []
    rewards: list[float] = []
    phases: list[str] = []
    frames: list[np.ndarray] = []
    ik_residuals: list[float] = []
    physics_step = 0
    maximum_height = initial_height
    sample_stride = int(base["episode"]["sample_every_physics_steps"])
    first_piece_contact: str | None = None
    wrong_piece_contacts: set[str] = set()
    wrong_piece_contact_phases: dict[str, set[str]] = {}
    bilateral_target_contact_observed = False
    recovery_target_contact_events = 0
    fault_injection_steps: list[int] = []
    after_fault = False
    phase_end_metrics: list[dict[str, Any]] = []

    def solve(target_point: np.ndarray, jaw: float) -> np.ndarray:
        pose, residual = _solve_reach(
            env.model,
            env.data,
            env.arm,
            target_point,
            env.pinch_local,
        )
        ik_residuals.append(float(residual))
        maximum_residual = float(
            recovery_contract["recovery_episode"]["maximum_ik_residual_m"]
        )
        if residual > maximum_residual:
            raise RuntimeError(
                "recovery expert IK residual too large: "
                f"{residual:.6f}; phase={current_phase}; target={target_point.tolist()}; "
                f"piece={env.piece_position().tolist()}; "
                f"pinch={_pinch_point(env.model, env.data, env.arm, env.pinch_local).tolist()}; "
                f"phase_ends={phase_end_metrics}"
            )
        return _goal_vector(pose, jaw)

    def record(action: np.ndarray, phase: str) -> None:
        states.append(
            np.asarray(env.data.qpos[env.qpos_addresses], dtype=np.float32).copy()
        )
        actions.append(np.asarray(action, dtype=np.float32).copy())
        rewards.append(_diagnostic_reward(env, base, target, initial_height, phase))
        phases.append(phase)
        if renderer is not None:
            renderer.update_scene(env.data, camera=str(base["scene"]["camera"]))
            frames.append(renderer.render().copy())

    def monitor_contacts_and_displacement() -> None:
        nonlocal first_piece_contact
        nonlocal bilateral_target_contact_observed
        nonlocal recovery_target_contact_events
        names, target_jaws = _jaw_piece_contacts(env)
        if names and first_piece_contact is None:
            first_piece_contact = sorted(names)[0]
        for name in names:
            if name != env.piece_name:
                wrong_piece_contacts.add(name)
                wrong_piece_contact_phases.setdefault(name, set()).add(current_phase)
        if len(target_jaws) == len(env.jaw_bodies) and target_jaws:
            bilateral_target_contact_observed = True
        if after_fault and env.piece_name in names:
            recovery_target_contact_events += 1
        for name in max_other_displacements:
            body_id = all_piece_ids[name]
            displacement = float(
                np.linalg.norm(env.data.xpos[body_id] - initial_other_positions[name])
            )
            max_other_displacements[name] = max(
                max_other_displacements[name], displacement
            )

    current_phase = "reset"

    def execute_phase(name: str, goal: np.ndarray, count: int) -> None:
        nonlocal current_phase, physics_step, maximum_height
        current_phase = name
        start = env.controls()
        ramp = max(1, min(count // 2, 160))
        for phase_step in range(count):
            blend = min(1.0, float(phase_step + 1) / float(ramp))
            action = start + blend * (goal - start)
            if physics_step % sample_stride == 0:
                record(action, name)
            env.step(action)
            monitor_contacts_and_displacement()
            maximum_height = max(maximum_height, float(env.piece_position()[2]))
            physics_step += 1
        contact_names, contact_jaws = _jaw_piece_contacts(env)
        phase_end_metrics.append(
            {
                "phase": name,
                "physics_step": physics_step,
                "piece_position_m": env.piece_position().tolist(),
                "pinch_position_m": _pinch_point(
                    env.model, env.data, env.arm, env.pinch_local
                ).tolist(),
                "piece_contacts": sorted(contact_names),
                "target_jaw_contact_count": len(contact_jaws),
                "controls_rad": env.controls().tolist(),
            }
        )

    base_phase_steps = base["episode"]["phase_physics_steps"]
    try:
        execute_phase(
            "stand_off",
            solve(stand_off, JAW_OPEN_RAD),
            int(base_phase_steps["stand_off"]),
        )
        advance_goal = solve(neck, JAW_OPEN_RAD)
        execute_phase("advance", advance_goal, int(base_phase_steps["advance"]))

        if family == "contact_recovery":
            recovery_steps = recovery_contract["recovery_episode"][
                "phase_physics_steps"
            ]
            # Model a bounded pre-lift miss while the jaws are still open. A
            # fault injected into a clamped piece adds unrealistic impulse
            # energy; moving the target before capture isolates reacquisition.
            _inject_target_slip(
                env,
                float(episode_row["slip_m"]),
                int(episode_row["slip_side"]),
            )
            fault_injection_steps.append(physics_step)
            after_fault = True
            clear_point = _pinch_point(
                env.model, env.data, env.arm, env.pinch_local
            ) + np.asarray([0.0, 0.0, 0.07])
            clear_goal = solve(clear_point, JAW_OPEN_RAD)
            execute_phase(
                "recover_clear",
                clear_goal,
                int(recovery_steps["recover_clear"]),
            )
            execute_phase(
                "fault_settle",
                clear_goal,
                int(recovery_steps["fault_settle"]),
            )
            recovered_piece = env.piece_position()
            recovered_neck = np.asarray(
                [
                    recovered_piece[0],
                    recovered_piece[1],
                    recovered_piece[2] + NECK_HEIGHT_M[kind],
                ],
                dtype=np.float64,
            )
            recover_stand_off = recovered_neck + np.asarray(
                [away[0] * 0.055, away[1] * 0.055, 0.03]
            )
            execute_phase(
                "recover_stand_off",
                solve(recover_stand_off, JAW_OPEN_RAD),
                int(recovery_steps["recover_stand_off"]),
            )
            recover_advance_goal = solve(recovered_neck, JAW_OPEN_RAD)
            execute_phase(
                "recover_advance",
                recover_advance_goal,
                int(recovery_steps["recover_advance"]),
            )
            close_goal = recover_advance_goal.copy()
            close_goal[-1] = JAW_SHUT_RAD
            execute_phase(
                "recover_close",
                close_goal,
                int(recovery_steps["recover_close"]),
            )
            neck = recovered_neck
        else:
            close_goal = advance_goal.copy()
            close_goal[-1] = JAW_SHUT_RAD
            execute_phase("close", close_goal, int(base_phase_steps["close"]))

        execute_phase(
            "lift",
            solve(
                neck + np.asarray([0.0, 0.0, base["episode"]["lift_height_m"]]),
                JAW_SHUT_RAD,
            ),
            int(base_phase_steps["lift"]),
        )
        grasp_offset = (
            _pinch_point(env.model, env.data, env.arm, env.pinch_local)
            - env.piece_position()
        )
        transit_height = (
            float(recovery_contract["recovery_episode"]["transit_height_m"])
            if family == "contact_recovery"
            else float(base["episode"]["lift_height_m"])
        )
        carry_point = transport_target + grasp_offset + np.asarray(
            [0.0, 0.0, transit_height]
        )
        execute_phase(
            "transit",
            solve(carry_point, JAW_SHUT_RAD),
            int(base_phase_steps["transit"]),
        )
        grasp_offset = (
            _pinch_point(env.model, env.data, env.arm, env.pinch_local)
            - env.piece_position()
        )
        release_point = transport_target + grasp_offset + np.asarray(
            [0.0, 0.0, base["episode"]["release_height_m"]]
        )
        lower_goal = solve(release_point, JAW_SHUT_RAD)
        execute_phase("lower", lower_goal, int(base_phase_steps["lower"]))
        release_goal = lower_goal.copy()
        release_goal[-1] = JAW_OPEN_RAD
        execute_phase("release", release_goal, int(base_phase_steps["release"]))
        current_pinch = _pinch_point(env.model, env.data, env.arm, env.pinch_local)
        # Clear the released piece and the board vertically.  Reusing the
        # approach direction here can sweep a jaw through a non-target piece
        # when the destination is on the opposite side of the board.
        retreat_point = current_pinch + np.asarray([0.0, 0.0, 0.08])
        retreat_goal = solve(retreat_point, JAW_OPEN_RAD)
        execute_phase("retreat", retreat_goal, int(base_phase_steps["retreat"]))
        execute_phase(
            "settle",
            retreat_goal,
            int(base["episode"]["settle_steps_after"]),
        )
    finally:
        if renderer is not None:
            renderer.close()

    evaluation_contract = copy.deepcopy(base)
    if family == "contact_recovery":
        evaluation_contract["episode"]["phase_physics_steps"]["close"] = 0
        evaluation_contract["episode"]["phase_physics_steps"].update(
            recovery_contract["recovery_episode"]["phase_physics_steps"]
        )
    base_verdict = evaluate_episode(
        env,
        evaluation_contract,
        target=target,
        initial_height=initial_height,
        maximum_height=maximum_height,
        initial_other_positions=initial_other_positions,
        action_count=physics_step,
    )
    maximum_other = max(max_other_displacements.values(), default=0.0)
    contact_metrics = {
        "first_piece_contact": first_piece_contact,
        "wrong_piece_contacts": sorted(wrong_piece_contacts),
        "wrong_piece_contact_phases": {
            name: sorted(contact_phases)
            for name, contact_phases in sorted(wrong_piece_contact_phases.items())
        },
        "bilateral_target_contact_observed": bilateral_target_contact_observed,
        "recovery_target_contact_events": recovery_target_contact_events,
        "fault_injection_count": len(fault_injection_steps),
        "fault_injection_physics_steps": fault_injection_steps,
        "assistance_frames": 0,
        "maximum_other_piece_displacement_m": maximum_other,
        "maximum_other_piece_displacements_m": max_other_displacements,
        "distractor_piece": distractor,
        "last_phase_reached": phases[-1] if phases else None,
        "phase_end_metrics": phase_end_metrics,
        "planned_placement_offset_m": (
            transport_target[:2] - target[:2]
        ).tolist(),
    }
    verdict = finalize_recovery_verdict(
        base_verdict,
        recovery_contract,
        perturbation_family=family,
        target_piece=env.piece_name,
        contact_metrics=contact_metrics,
    )
    state_array = np.asarray(states, dtype=np.float32)
    action_array = np.asarray(actions, dtype=np.float32)
    if state_array.shape != action_array.shape or state_array.shape[1] != len(
        ROBOT_JOINTS
    ):
        raise RuntimeError("recovery state/action samples drifted from the contract")
    if render_frames and len(frames) != len(states):
        raise RuntimeError("recovery video and samples diverged")
    return GrootRecoveryEpisode(
        case_id=str(case["case_id"]),
        instruction=str(case["instruction"]),
        piece=str(case["piece"]),
        target_square=str(case["target_square"]),
        seed=int(episode_row["seed"]),
        perturbation={
            key: episode_row[key]
            for key in (
                "family",
                "piece_planar_offset_m",
                "piece_yaw_deg",
                "distractor_spacing_m",
                "distractor_side",
                "slip_m",
                "slip_side",
            )
        },
        states=state_array,
        actions=action_array,
        rewards=np.asarray(rewards, dtype=np.float32),
        phases=phases,
        frames=frames,
        verdict=verdict,
        maximum_ik_residual_m=max(ik_residuals),
        contact_metrics=contact_metrics,
    )


def export_recovery_dataset(
    output: Path,
    *,
    split: str = "training",
    max_episodes: int | None = None,
) -> dict[str, Any]:
    """Export the frozen recovery split as a GR00T LeRobot v2 dataset."""

    import pyarrow as pa
    import pyarrow.parquet as pq

    recovery = load_recovery_task_contract()
    base = load_groot_task_contract()
    if split not in {"training", "held_out"}:
        raise ValueError("split must be training or held_out")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty dataset: {output}")
    meta_dir = output / "meta"
    data_dir = output / "data" / "chunk-000"
    video_key = str(base["observation"]["video_original_key"])
    video_dir = output / "videos" / "chunk-000" / video_key
    for directory in (meta_dir, data_dir, video_dir):
        directory.mkdir(parents=True, exist_ok=True)

    episode_rows = recovery[f"{split}_episodes"]
    if max_episodes is not None:
        episode_rows = episode_rows[:max_episodes]
    cases = base[f"{split}_cases"]
    task_index_by_case = {
        str(case["case_id"]): index for index, case in enumerate(cases)
    }
    _write_jsonl(
        meta_dir / "tasks.jsonl",
        [
            {"task_index": index, "task": str(case["instruction"])}
            for index, case in enumerate(cases)
        ],
    )

    episodes_meta: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    all_states: list[np.ndarray] = []
    all_actions: list[np.ndarray] = []
    all_rewards: list[np.ndarray] = []
    all_timestamps: list[np.ndarray] = []
    global_index = 0
    fps = int(base["episode"]["sample_fps"])
    state_type = pa.list_(pa.float32(), len(ROBOT_JOINTS))

    for dataset_episode_index, _ in enumerate(episode_rows):
        episode = collect_recovery_expert_episode(
            recovery,
            split=split,
            episode_index=dataset_episode_index,
            render_frames=True,
        )
        if not episode.verdict["success"]:
            raise RuntimeError(
                f"recovery expert episode {dataset_episode_index} failed frozen gates"
            )
        length = int(episode.states.shape[0])
        frame_indices = np.arange(length, dtype=np.int64)
        timestamps = frame_indices.astype(np.float32) / float(fps)
        task_index = task_index_by_case[episode.case_id]
        table = pa.Table.from_arrays(
            [
                pa.array(episode.states.tolist(), type=state_type),
                pa.array(episode.actions.tolist(), type=state_type),
                pa.array(timestamps, type=pa.float32()),
                pa.array(frame_indices, type=pa.int64()),
                pa.array(np.full(length, dataset_episode_index), type=pa.int64()),
                pa.array(np.arange(global_index, global_index + length), type=pa.int64()),
                pa.array(np.full(length, task_index), type=pa.int64()),
                pa.array(episode.rewards, type=pa.float32()),
                pa.array(frame_indices == length - 1, type=pa.bool_()),
            ],
            names=[
                "observation.state",
                "action",
                "timestamp",
                "frame_index",
                "episode_index",
                "index",
                "task_index",
                "next.reward",
                "next.done",
            ],
        )
        parquet_path = data_dir / f"episode_{dataset_episode_index:06d}.parquet"
        video_path = video_dir / f"episode_{dataset_episode_index:06d}.mp4"
        pq.write_table(table, parquet_path, compression="zstd")
        _write_video(video_path, episode.frames, fps)
        episodes_meta.append(
            {
                "episode_index": dataset_episode_index,
                "tasks": [episode.instruction],
                "length": length,
            }
        )
        evidence.append(
            {
                "episode_index": dataset_episode_index,
                "case_id": episode.case_id,
                "seed": episode.seed,
                "perturbation": episode.perturbation,
                "verdict": episode.verdict,
                "maximum_ik_residual_m": episode.maximum_ik_residual_m,
            }
        )
        all_states.append(episode.states)
        all_actions.append(episode.actions)
        all_rewards.append(episode.rewards)
        all_timestamps.append(timestamps)
        global_index += length

    _write_jsonl(meta_dir / "episodes.jsonl", episodes_meta)
    _write_json(
        meta_dir / "modality.json",
        {
            "state": {
                "single_arm": {"start": 0, "end": 5},
                "gripper": {"start": 5, "end": 6},
            },
            "action": {
                "single_arm": {"start": 0, "end": 5},
                "gripper": {"start": 5, "end": 6},
            },
            "video": {"front": {"original_key": video_key}},
            "annotation": {
                "human.task_description": {"original_key": "task_index"}
            },
        },
    )
    height = int(base["episode"]["render_height"])
    width = int(base["episode"]["render_width"])
    info = {
        "codebase_version": "v2.1",
        "robot_type": "sim2claw_so101_simulation",
        "total_episodes": len(episodes_meta),
        "total_frames": global_index,
        "total_tasks": len(cases),
        "chunks_size": 1000,
        "fps": fps,
        "splits": {"train": f"0:{len(episodes_meta)}"},
        "data_path": "data/chunk-{episode_chunk:03d}/episode_{episode_index:06d}.parquet",
        "video_path": "videos/chunk-{episode_chunk:03d}/{video_key}/episode_{episode_index:06d}.mp4",
        "features": {
            "action": {
                "dtype": "float32",
                "shape": [6],
                "names": list(base["action"]["features"]),
            },
            "observation.state": {
                "dtype": "float32",
                "shape": [6],
                "names": list(base["observation"]["state_features"]),
            },
            video_key: {
                "dtype": "video",
                "shape": [height, width, 3],
                "names": ["height", "width", "channels"],
                "info": {
                    "video.height": height,
                    "video.width": width,
                    "video.codec": "h264",
                    "video.pix_fmt": "yuv420p",
                    "video.is_depth_map": False,
                    "video.fps": fps,
                    "video.channels": 3,
                    "has_audio": False,
                },
            },
            "timestamp": {"dtype": "float32", "shape": [1], "names": None},
            "frame_index": {"dtype": "int64", "shape": [1], "names": None},
            "episode_index": {"dtype": "int64", "shape": [1], "names": None},
            "index": {"dtype": "int64", "shape": [1], "names": None},
            "task_index": {"dtype": "int64", "shape": [1], "names": None},
            "next.reward": {"dtype": "float32", "shape": [1], "names": None},
            "next.done": {"dtype": "bool", "shape": [1], "names": None},
        },
        "total_chunks": 1,
        "total_videos": len(episodes_meta),
    }
    _write_json(meta_dir / "info.json", info)
    _write_json(
        meta_dir / "stats.json",
        {
            "observation.state": _stats(np.concatenate(all_states)),
            "action": _stats(np.concatenate(all_actions)),
            "timestamp": _stats(np.concatenate(all_timestamps)),
            "next.reward": _stats(np.concatenate(all_rewards)),
        },
    )
    file_hashes = {
        str(path.relative_to(output)): _sha256_file(path)
        for path in sorted(output.rglob("*"))
        if path.is_file()
    }
    receipt = {
        "schema_version": "sim2claw.groot_recovery_lerobot_dataset_receipt.v2",
        "task_id": recovery["task_id"],
        "recovery_task_contract_sha256": recovery_task_contract_sha256(),
        "base_task_contract_sha256": groot_task_contract_sha256(),
        "split": split,
        "proof_class": "simulation_synthetic_vla_recovery_demonstration_dataset",
        "format": "GR00T LeRobot v2.1",
        "model_source_commit": base["model"]["source_commit"],
        "episode_count": len(episodes_meta),
        "frame_count": global_index,
        "all_expert_episodes_passed_frozen_evaluator": True,
        "diagnostic_reward_has_promotion_authority": False,
        "training_cannot_promote_itself": True,
        "physical_authority": False,
        "files": file_hashes,
        "episode_evidence": evidence,
    }
    _write_json(output / "dataset_receipt.json", receipt)
    return receipt
