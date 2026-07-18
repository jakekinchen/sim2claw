"""Frozen simulation task and expert demonstrations for a single chess-rook lift."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import mujoco
import numpy as np

from .grasp import (
    JAW_OPEN_RAD,
    JAW_SHUT_RAD,
    LIFT_HEIGHT_M,
    NECK_HEIGHT_M,
    _actuator_map,
    _jaw_body_ids,
    _named_id,
    _pinch_offset,
    _pinch_point,
    _select_piece,
    _solve_reach,
)
from .paths import DEFAULT_CHESS_TASK_CONFIG
from .scene import ROBOT_JOINTS, build_scene_spec, initialize_robot_poses


def load_task_contract(path: Path = DEFAULT_CHESS_TASK_CONFIG) -> dict[str, Any]:
    contract = json.loads(path.read_text(encoding="utf-8"))
    if contract.get("schema_version") != "sim2claw.chess_rook_lift_task.v3":
        raise ValueError("unsupported chess-rook task contract")
    train = contract["training_split"]
    held_out = contract["held_out_split"]
    if set(train["seeds"]) & set(held_out["seeds"]):
        raise ValueError("training and held-out seeds must be disjoint")
    if len(train["seeds"]) != len(train["piece_planar_offsets_m"]):
        raise ValueError("training seeds and offsets must have equal length")
    if len(held_out["seeds"]) != len(held_out["piece_planar_offsets_m"]):
        raise ValueError("held-out seeds and offsets must have equal length")
    phase_total = sum(contract["episode"]["phase_control_steps"].values())
    if phase_total != contract["episode"]["control_horizon"]:
        raise ValueError("phase control steps do not match the frozen horizon")
    if contract["observation"]["n_obs_steps"] != 1:
        raise ValueError("the first ACT task is frozen at one observation step")
    return contract


def task_contract_sha256(path: Path = DEFAULT_CHESS_TASK_CONFIG) -> str:
    payload = json.dumps(
        load_task_contract(path), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass
class ExpertEpisode:
    seed: int
    piece_offset_xy_m: tuple[float, float]
    observations: np.ndarray
    actions: np.ndarray
    phases: list[str]
    piece_heights_m: np.ndarray
    jaw_piece_contacts: np.ndarray
    initial_piece_height_m: float
    final_piece_height_m: float
    maximum_piece_rise_m: float


class ChessRookLiftEnv:
    """Narrow task wrapper; defaults to the frozen pre-mass-profile dynamics."""

    def __init__(
        self,
        contract: dict[str, Any],
        *,
        seed: int,
        piece_offset_xy_m: tuple[float, float],
        mass_profile_path: Path | None = None,
    ) -> None:
        self.contract = contract
        self.seed = int(seed)
        self.arm = str(contract["scene"]["arm"])
        np.random.seed(self.seed)

        # The default stays None because the v3 rook-lift and GR00T contracts
        # were frozen before the mass profile existed. New requalification runs
        # may pass the profile explicitly without moving the legacy evaluator.
        self.model = build_scene_spec(mass_profile_path=mass_profile_path).compile()
        self.data = mujoco.MjData(self.model)
        initialize_robot_poses(self.model, self.data)
        for _ in range(int(contract["episode"]["settle_steps"])):
            mujoco.mj_step(self.model, self.data)

        mount_body = _named_id(
            self.model, mujoco.mjtObj.mjOBJ_BODY, f"{self.arm}_base"
        )
        self.mount = np.array(self.data.xpos[mount_body], dtype=np.float64)
        self.piece_name, self.piece_body = _select_piece(
            self.model,
            self.data,
            self.mount,
            str(contract["scene"]["piece"]),
        )
        piece_joint = _named_id(
            self.model,
            mujoco.mjtObj.mjOBJ_JOINT,
            f"{self.piece_name}_free",
        )
        qpos_address = int(self.model.jnt_qposadr[piece_joint])
        dof_address = int(self.model.jnt_dofadr[piece_joint])
        if piece_offset_xy_m != (0.0, 0.0):
            self.data.qpos[qpos_address] += float(piece_offset_xy_m[0])
            self.data.qpos[qpos_address + 1] += float(piece_offset_xy_m[1])
            self.data.qvel[dof_address : dof_address + 6] = 0.0
            mujoco.mj_forward(self.model, self.data)

        self.actuators = _actuator_map(self.model, self.arm)
        self.actuator_ids = np.asarray(
            [self.actuators[joint] for joint in ROBOT_JOINTS], dtype=np.int32
        )
        self.joint_ids = np.asarray(
            [
                _named_id(
                    self.model,
                    mujoco.mjtObj.mjOBJ_JOINT,
                    f"{self.arm}_{joint}",
                )
                for joint in ROBOT_JOINTS
            ],
            dtype=np.int32,
        )
        self.qpos_addresses = np.asarray(
            [self.model.jnt_qposadr[joint_id] for joint_id in self.joint_ids],
            dtype=np.int32,
        )
        self.dof_addresses = np.asarray(
            [self.model.jnt_dofadr[joint_id] for joint_id in self.joint_ids],
            dtype=np.int32,
        )
        self.jaw_bodies = _jaw_body_ids(self.model, self.arm)
        self.pinch_local = _pinch_offset(self.model, self.data, self.arm)
        self.initial_piece_height_m = float(self.data.xpos[self.piece_body][2])
        self.control_interval = int(
            contract["episode"]["control_interval_physics_steps"]
        )
        self.horizon = int(contract["episode"]["control_horizon"])

    def controls(self) -> np.ndarray:
        return np.asarray(self.data.ctrl[self.actuator_ids], dtype=np.float64).copy()

    def piece_position(self) -> np.ndarray:
        return np.asarray(self.data.xpos[self.piece_body], dtype=np.float64).copy()

    def observation(self, control_step: int) -> np.ndarray:
        progress = min(1.0, max(0.0, float(control_step) / float(self.horizon - 1)))
        phase_one_hot = np.zeros(5, dtype=np.float64)
        phase_progress = 1.0
        cursor = 0
        for phase_index, count in enumerate(
            self.contract["episode"]["phase_control_steps"].values()
        ):
            if control_step < cursor + count:
                phase_one_hot[phase_index] = 1.0
                phase_progress = float(control_step - cursor) / float(max(1, count - 1))
                break
            cursor += count
        return np.concatenate(
            [
                np.asarray(self.data.qpos[self.qpos_addresses], dtype=np.float64),
                np.asarray(self.data.qvel[self.dof_addresses], dtype=np.float64),
                self.controls(),
                self.piece_position(),
                _pinch_point(
                    self.model, self.data, self.arm, self.pinch_local
                ).astype(np.float64),
                np.asarray([progress], dtype=np.float64),
                phase_one_hot,
                np.asarray([phase_progress], dtype=np.float64),
            ]
        ).astype(np.float32)

    def step(self, action: np.ndarray) -> None:
        action = np.asarray(action, dtype=np.float64)
        if action.shape != (len(ROBOT_JOINTS),) or not np.isfinite(action).all():
            raise ValueError("task action must be a finite six-vector")
        low = self.model.actuator_ctrlrange[self.actuator_ids, 0]
        high = self.model.actuator_ctrlrange[self.actuator_ids, 1]
        target = np.clip(action, low, high)
        self.data.ctrl[self.actuator_ids] = target
        for _ in range(self.control_interval):
            mujoco.mj_step(self.model, self.data)

    def jaw_piece_contact(self) -> bool:
        for contact_index in range(self.data.ncon):
            contact = self.data.contact[contact_index]
            bodies = {
                int(self.model.geom_bodyid[contact.geom1]),
                int(self.model.geom_bodyid[contact.geom2]),
            }
            if self.piece_body in bodies and bodies & self.jaw_bodies:
                return True
        return False

    def render(self, renderer: mujoco.Renderer) -> np.ndarray:
        renderer.update_scene(self.data, camera="workcell")
        return renderer.render().copy()


def _goal_vector(reach: dict[str, float], jaw: float) -> np.ndarray:
    return np.asarray(
        [jaw if joint == "gripper" else reach[joint] for joint in ROBOT_JOINTS],
        dtype=np.float64,
    )


def collect_expert_episode(
    contract: dict[str, Any],
    *,
    seed: int,
    piece_offset_xy_m: tuple[float, float],
) -> ExpertEpisode:
    """Create one fresh synthetic expert episode without opening any hardware path."""

    env = ChessRookLiftEnv(
        contract, seed=seed, piece_offset_xy_m=piece_offset_xy_m
    )
    phase_counts = contract["episode"]["phase_control_steps"]
    observations: list[np.ndarray] = []
    actions: list[np.ndarray] = []
    phases: list[str] = []
    heights: list[float] = []
    contacts: list[bool] = []
    control_step = 0

    piece_xy = env.piece_position()[:2]
    away = env.mount[:2] - piece_xy
    away /= max(float(np.linalg.norm(away)), 1e-9)
    kind = env.piece_name.split("_")[1]
    neck = np.asarray(
        [
            piece_xy[0],
            piece_xy[1],
            env.initial_piece_height_m + NECK_HEIGHT_M[kind],
        ],
        dtype=np.float64,
    )
    stand_off = neck + np.asarray([away[0] * 0.055, away[1] * 0.055, 0.03])

    def execute_phase(name: str, goal: np.ndarray, count: int) -> None:
        nonlocal control_step
        start = env.controls()
        ramp = max(1, min(count // 2, 160))
        for phase_step in range(count):
            blend = min(1.0, float(phase_step + 1) / float(ramp))
            action = start + blend * (goal - start)
            observations.append(env.observation(control_step))
            actions.append(action.astype(np.float32))
            phases.append(name)
            env.step(action)
            heights.append(float(env.piece_position()[2]))
            contacts.append(env.jaw_piece_contact())
            control_step += 1

    stand_pose, stand_error = _solve_reach(
        env.model, env.data, env.arm, stand_off, env.pinch_local
    )
    if stand_error > 0.003:
        raise RuntimeError(f"expert stand-off IK residual is too large: {stand_error}")
    execute_phase(
        "stand_off",
        _goal_vector(stand_pose, JAW_OPEN_RAD),
        int(phase_counts["stand_off"]),
    )

    advance_pose, advance_error = _solve_reach(
        env.model, env.data, env.arm, neck, env.pinch_local
    )
    if advance_error > 0.003:
        raise RuntimeError(f"expert advance IK residual is too large: {advance_error}")
    execute_phase(
        "advance",
        _goal_vector(advance_pose, JAW_OPEN_RAD),
        int(phase_counts["advance"]),
    )
    execute_phase(
        "close",
        _goal_vector(advance_pose, JAW_SHUT_RAD),
        int(phase_counts["close"]),
    )

    lifted = neck + np.asarray([0.0, 0.0, LIFT_HEIGHT_M])
    lift_pose, lift_error = _solve_reach(
        env.model, env.data, env.arm, lifted, env.pinch_local
    )
    if lift_error > 0.003:
        raise RuntimeError(f"expert lift IK residual is too large: {lift_error}")
    lift_goal = _goal_vector(lift_pose, JAW_SHUT_RAD)
    execute_phase("lift", lift_goal, int(phase_counts["lift"]))
    execute_phase("hold", lift_goal, int(phase_counts["hold"]))

    observation_array = np.asarray(observations, dtype=np.float32)
    action_array = np.asarray(actions, dtype=np.float32)
    if observation_array.shape != (
        env.horizon,
        int(contract["observation"]["dimension"]),
    ):
        raise RuntimeError("expert observation shape drifted from the task contract")
    if action_array.shape != (env.horizon, int(contract["action"]["dimension"])):
        raise RuntimeError("expert action shape drifted from the task contract")

    height_array = np.asarray(heights, dtype=np.float64)
    return ExpertEpisode(
        seed=seed,
        piece_offset_xy_m=piece_offset_xy_m,
        observations=observation_array,
        actions=action_array,
        phases=phases,
        piece_heights_m=height_array,
        jaw_piece_contacts=np.asarray(contacts, dtype=np.bool_),
        initial_piece_height_m=env.initial_piece_height_m,
        final_piece_height_m=float(height_array[-1]),
        maximum_piece_rise_m=float(height_array.max() - env.initial_piece_height_m),
    )
