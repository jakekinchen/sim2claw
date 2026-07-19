"""Evaluator-owned reward guidance for stochastic GR00T action proposals."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import mujoco
import numpy as np

from .chess_task import ChessRookLiftEnv
from .grasp import (
    JAW_OPEN_RAD,
    JAW_SHUT_RAD,
    NECK_HEIGHT_M,
    _piece_bodies,
    _pinch_point,
)
from .groot_chess import (
    _body_upright_cosine,
    _piece_linear_speed,
    groot_task_contract_sha256,
)
from .paths import DEFAULT_GROOT_GUIDANCE_CONFIG


def load_guidance_contract(
    path: Path = DEFAULT_GROOT_GUIDANCE_CONFIG,
) -> dict[str, Any]:
    contract = json.loads(path.read_text(encoding="utf-8"))
    if contract.get("schema_version") != "sim2claw.groot_chess_reward_guidance.v2":
        raise ValueError("unsupported GR00T guidance contract")
    if not contract.get("frozen_before_held_out"):
        raise ValueError("guidance contract must be frozen before held-out evaluation")
    if contract.get("base_task_contract_sha256") != groot_task_contract_sha256():
        raise ValueError("guidance contract references a different base task")
    selection = contract["selection"]
    if int(selection["proposal_count"]) < 2:
        raise ValueError("guided selection requires at least two proposals")
    if int(selection["execution_horizon"]) < 1:
        raise ValueError("guided execution horizon must be positive")
    if not contract["authority"].get("guided_selection_counts_as_assistance"):
        raise ValueError("guided proposal selection must be classified as assistance")
    return contract


def guidance_contract_sha256(
    path: Path = DEFAULT_GROOT_GUIDANCE_CONFIG,
) -> str:
    payload = json.dumps(
        load_guidance_contract(path),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class GuidanceContext:
    initial_piece_position: np.ndarray
    target_position: np.ndarray
    stand_off_position: np.ndarray
    neck_position: np.ndarray
    initial_other_positions: dict[str, np.ndarray]


def make_guidance_context(
    env: ChessRookLiftEnv,
    base_contract: dict[str, Any],
    target_position: np.ndarray,
) -> GuidanceContext:
    piece = env.piece_position()
    away = env.mount[:2] - piece[:2]
    away /= max(float(np.linalg.norm(away)), 1e-9)
    kind = env.piece_name.split("_")[1]
    neck = np.asarray(
        [piece[0], piece[1], piece[2] + NECK_HEIGHT_M[kind]],
        dtype=np.float64,
    )
    stand_off = neck + np.asarray(
        [away[0] * 0.055, away[1] * 0.055, 0.03], dtype=np.float64
    )
    active = set(base_contract["scene"]["active_pieces"])
    others = {
        name: np.asarray(env.data.xpos[body_id], dtype=np.float64).copy()
        for name, body_id in _piece_bodies(env.model).items()
        if name != env.piece_name and name in active
    }
    return GuidanceContext(
        initial_piece_position=piece,
        target_position=np.asarray(target_position, dtype=np.float64).copy(),
        stand_off_position=stand_off,
        neck_position=neck,
        initial_other_positions=others,
    )


def phase_for_sample_step(base_contract: dict[str, Any], sample_step: int) -> str:
    if sample_step < 0:
        raise ValueError("sample step must be non-negative")
    stride = int(base_contract["episode"]["sample_every_physics_steps"])
    cursor = 0
    for phase, physics_steps in base_contract["episode"]["phase_physics_steps"].items():
        count = int(physics_steps) // stride
        if sample_step < cursor + count:
            return str(phase)
        cursor += count
    return "settle"


def _proximity(distance: float, scale: float) -> float:
    return 1.0 - float(np.clip(distance / scale, 0.0, 1.0))


def guidance_metrics(
    env: ChessRookLiftEnv,
    base_contract: dict[str, Any],
    guidance_contract: dict[str, Any],
    context: GuidanceContext,
    phase: str,
) -> dict[str, float | bool | str]:
    reward = guidance_contract["reward"]
    safety = guidance_contract["safety"]
    evaluator = base_contract["evaluator"]
    piece = env.piece_position()
    pinch = _pinch_point(env.model, env.data, env.arm, env.pinch_local)
    rise = float(piece[2] - context.initial_piece_position[2])
    lift_progress = float(
        np.clip(rise / float(evaluator["minimum_piece_rise_m"]), 0.0, 1.0)
    )
    destination_distance = float(
        np.linalg.norm(piece[:2] - context.target_position[:2])
    )
    target_planar_displacement = float(
        np.linalg.norm(piece[:2] - context.initial_piece_position[:2])
    )
    height_distance = float(abs(piece[2] - context.target_position[2]))
    destination_proximity = _proximity(
        destination_distance, float(reward["destination_distance_scale_m"])
    )
    height_proximity = _proximity(
        height_distance, float(reward["height_distance_scale_m"])
    )
    clearance = float(np.linalg.norm(pinch - piece))
    clearance_progress = float(
        np.clip(clearance / float(reward["clearance_distance_scale_m"]), 0.0, 1.0)
    )
    upright = _body_upright_cosine(env.data, env.piece_body)
    speed = _piece_linear_speed(env)
    speed_progress = _proximity(speed, float(reward["linear_speed_scale_m_s"]))
    jaw_contact = env.jaw_piece_contact()
    jaw_control = float(env.controls()[-1])

    desired_pinch = (
        context.stand_off_position if phase == "stand_off" else context.neck_position
    )
    pinch_distance = float(np.linalg.norm(pinch - desired_pinch))
    phase_goal_proximity = _proximity(
        pinch_distance, float(reward["pinch_distance_scale_m"])
    )
    other_displacements = {
        name: float(
            np.linalg.norm(
                env.data.xpos[body_id] - context.initial_other_positions[name]
            )
        )
        for name, body_id in _piece_bodies(env.model).items()
        if name in context.initial_other_positions
    }
    maximum_other_displacement = max(other_displacements.values(), default=0.0)
    return {
        "phase": phase,
        "piece_rise_m": rise,
        "piece_height_m": float(piece[2]),
        "initial_piece_height_m": float(context.initial_piece_position[2]),
        "lift_progress": lift_progress,
        "destination_distance_m": destination_distance,
        "target_planar_displacement_m": target_planar_displacement,
        "destination_proximity": destination_proximity,
        "height_distance_m": height_distance,
        "height_proximity": height_proximity,
        "pinch_distance_m": pinch_distance,
        "phase_goal_proximity": phase_goal_proximity,
        "jaw_contact": jaw_contact,
        "jaw_control_rad": jaw_control,
        "jaw_open_proximity": _proximity(abs(jaw_control - JAW_OPEN_RAD), 1.35),
        "jaw_shut_proximity": _proximity(abs(jaw_control - JAW_SHUT_RAD), 1.35),
        "released": not jaw_contact,
        "upright_cosine": upright,
        "linear_speed_m_s": speed,
        "settled_progress": speed_progress,
        "gripper_clearance_m": clearance,
        "clearance_progress": clearance_progress,
        "maximum_other_piece_displacement_m": maximum_other_displacement,
        "other_piece_soft_limit_exceeded": maximum_other_displacement
        > float(safety["other_piece_displacement_soft_limit_m"]),
    }


def guidance_score(
    metrics: dict[str, float | bool | str],
    guidance_contract: dict[str, Any],
    *,
    control_delta_rad: float,
) -> float:
    phase = str(metrics["phase"])
    weights = guidance_contract["reward"]["weights"]
    safety = guidance_contract["safety"]
    score = 0.0
    if phase == "stand_off":
        score += weights["phase_goal"] * float(metrics["phase_goal_proximity"])
        score += float(metrics["jaw_open_proximity"])
    elif phase == "advance":
        score += weights["phase_goal"] * float(metrics["phase_goal_proximity"])
        score += float(metrics["jaw_open_proximity"])
    elif phase == "close":
        score += weights["phase_goal"] * float(metrics["phase_goal_proximity"])
        score += 2.0 * float(metrics["jaw_shut_proximity"])
        score += weights["jaw_contact"] * float(bool(metrics["jaw_contact"]))
    elif phase == "lift":
        score += weights["lift_progress"] * float(metrics["lift_progress"])
        score += weights["jaw_contact"] * float(bool(metrics["jaw_contact"]))
        score += weights["upright"] * float(metrics["upright_cosine"])
    elif phase == "transit":
        score += weights["destination_proximity"] * float(
            metrics["destination_proximity"]
        )
        score += weights["lift_progress"] * float(metrics["lift_progress"])
        score += weights["jaw_contact"] * float(bool(metrics["jaw_contact"]))
        score += weights["upright"] * float(metrics["upright_cosine"])
    elif phase == "lower":
        score += weights["destination_proximity"] * float(
            metrics["destination_proximity"]
        )
        score += weights["height_proximity"] * float(metrics["height_proximity"])
        score += weights["jaw_contact"] * float(bool(metrics["jaw_contact"]))
        score += weights["upright"] * float(metrics["upright_cosine"])
    else:
        score += weights["destination_proximity"] * float(
            metrics["destination_proximity"]
        )
        score += weights["height_proximity"] * float(metrics["height_proximity"])
        score += weights["released"] * float(bool(metrics["released"]))
        score += weights["upright"] * float(metrics["upright_cosine"])
        score += weights["settled"] * float(metrics["settled_progress"])
        score += weights["clearance"] * float(metrics["clearance_progress"])

    score -= weights["control_smoothness"] * float(
        control_delta_rad / guidance_contract["reward"]["control_delta_scale_rad"]
    )
    other_displacement = float(metrics["maximum_other_piece_displacement_m"])
    soft_limit = float(safety["other_piece_displacement_soft_limit_m"])
    hard_limit = float(safety["other_piece_displacement_hard_limit_m"])
    if other_displacement > soft_limit:
        score -= 10.0 * (other_displacement - soft_limit) / max(soft_limit, 1e-9)
    if other_displacement > hard_limit:
        score -= float(safety["hard_penalty"])
    if phase in {"stand_off", "advance", "close"}:
        target_displacement = float(metrics["target_planar_displacement_m"])
        target_limit = float(safety["pre_grasp_target_displacement_hard_limit_m"])
        if target_displacement > target_limit:
            score -= float(safety["hard_penalty"]) * (
                1.0 + (target_displacement - target_limit) / max(target_limit, 1e-9)
            )
        upright = float(metrics["upright_cosine"])
        upright_minimum = float(safety["pre_grasp_upright_minimum"])
        if upright < upright_minimum:
            score -= float(safety["hard_penalty"]) * (upright_minimum - upright)
    if phase in {"lift", "transit", "lower"} and not bool(metrics["jaw_contact"]):
        score -= float(safety["hard_penalty"])
    if phase in {"transit", "lower"}:
        minimum_rise = float(safety["carry_minimum_rise_m"])
        rise = float(metrics["piece_rise_m"])
        if rise < minimum_rise:
            score -= (
                float(safety["hard_penalty"])
                * (minimum_rise - rise)
                / max(minimum_rise, 1e-9)
            )
    if phase in {"release", "retreat", "settle"}:
        destination_limit = float(safety["release_destination_hard_limit_m"])
        destination_distance = float(metrics["destination_distance_m"])
        if destination_distance > destination_limit:
            score -= (
                float(safety["hard_penalty"])
                * (destination_distance - destination_limit)
                / max(destination_limit, 1e-9)
            )
    if float(metrics["piece_height_m"]) < (
        float(metrics["initial_piece_height_m"]) - float(safety["piece_floor_margin_m"])
    ):
        score -= float(safety["hard_penalty"])
    if phase in {"lift", "transit", "lower", "release", "retreat", "settle"}:
        upright = float(metrics["upright_cosine"])
        if upright < float(safety["upright_soft_minimum"]):
            score -= float(safety["hard_penalty"]) * (
                float(safety["upright_soft_minimum"]) - upright
            )
    return float(score)


def simulate_candidate(
    env: ChessRookLiftEnv,
    base_contract: dict[str, Any],
    guidance_contract: dict[str, Any],
    context: GuidanceContext,
    action_chunk: np.ndarray,
    *,
    sample_step: int,
    execution_horizon: int,
) -> dict[str, Any]:
    action_chunk = np.asarray(action_chunk, dtype=np.float64)
    if action_chunk.ndim != 2 or action_chunk.shape[1] != len(env.actuator_ids):
        raise ValueError(f"unexpected candidate action shape: {action_chunk.shape}")
    if action_chunk.shape[0] < execution_horizon:
        raise ValueError("candidate is shorter than the execution horizon")
    if not np.isfinite(action_chunk).all():
        raise ValueError("candidate contains a non-finite action")

    state_spec = mujoco.mjtState.mjSTATE_INTEGRATION
    state = np.empty(mujoco.mj_stateSize(env.model, state_spec), dtype=np.float64)
    mujoco.mj_getState(env.model, env.data, state, state_spec)
    start_control = env.controls()
    maximum_height = float(env.piece_position()[2])
    try:
        stride = int(base_contract["episode"]["sample_every_physics_steps"])
        for action in action_chunk[:execution_horizon]:
            for _ in range(stride):
                env.step(action)
                maximum_height = max(maximum_height, float(env.piece_position()[2]))
        terminal_step = sample_step + execution_horizon - 1
        phase = phase_for_sample_step(base_contract, terminal_step)
        metrics = guidance_metrics(
            env, base_contract, guidance_contract, context, phase
        )
        metrics["candidate_maximum_piece_height_m"] = maximum_height
        control_delta = float(
            np.mean(
                np.linalg.norm(action_chunk[:execution_horizon] - start_control, axis=1)
            )
        )
        score = guidance_score(
            metrics,
            guidance_contract,
            control_delta_rad=control_delta,
        )
        return {
            "score": score,
            "control_delta_rad": control_delta,
            "metrics": metrics,
        }
    finally:
        mujoco.mj_setState(env.model, env.data, state, state_spec)
        mujoco.mj_forward(env.model, env.data)
