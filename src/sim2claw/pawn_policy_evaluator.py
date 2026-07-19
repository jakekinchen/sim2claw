"""Independent CPU/fp32 replay evaluator for the frozen pawn GR00T rollout.

The policy runner owns model queries and records actions.  This module rebuilds
the frozen 100 mm scene, verifies the exact reset, reconstructs every executed
action from the saved model chunks, replays the float32 sample-hold trajectory,
and applies the already-frozen pawn consequence gates.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import mujoco
import numpy as np

from .grasp import _jaw_body_ids, _piece_bodies, _pinch_offset, _pinch_point
from .groot_execution import aggregate_temporal_action
from .paths import REPO_ROOT
from .pawn_source_evaluator import (
    EVALUATOR_PATH,
    load_pawn_evaluator_contract,
    pawn_evaluator_sha256,
    score_pawn_consequences,
)
from .scene import (
    CURRENT_TASK_PIECE_LAYOUT,
    ROBOT_JOINTS,
    board_square_center,
    build_scene_spec,
    initialize_robot_poses,
    registered_board_center,
)
from .source_episode import CONTRACT_PATH_V3, load_source_contract, sha256_file


ROLLOUT_SCHEMA = "sim2claw.groot_n17_pawn_100mm_rollout.v1"
EVALUATION_SCHEMA = "sim2claw.groot_n17_pawn_100mm_evaluation.v1"
TARGET_PIECE_ID = "tan_pawn_c8"
DESTINATION_SQUARE = "a6"
SAMPLE_COUNT = 562
PHYSICS_STEPS_PER_ACTION = 10


@dataclass
class PawnDevelopmentRuntime:
    model: mujoco.MjModel
    data: mujoco.MjData
    actuator_ids: np.ndarray
    qpos_addresses: np.ndarray
    piece_bodies: dict[str, int]
    initial_state: np.ndarray


def integration_state(model: mujoco.MjModel, data: mujoco.MjData) -> np.ndarray:
    size = mujoco.mj_stateSize(model, mujoco.mjtState.mjSTATE_INTEGRATION)
    state = np.empty(size, dtype=np.float64)
    mujoco.mj_getState(model, data, state, mujoco.mjtState.mjSTATE_INTEGRATION)
    return state


def build_frozen_pawn_development_runtime() -> PawnDevelopmentRuntime:
    source = load_source_contract(CONTRACT_PATH_V3)
    reset = source["simulation_reset"]
    model = build_scene_spec(
        piece_layout=CURRENT_TASK_PIECE_LAYOUT,
        board_center_in_table_frame_xy_m=registered_board_center(
            source["scene"]["scene_id"]
        ),
    ).compile()
    if not np.isclose(float(model.opt.timestep), 0.005, atol=1e-12):
        raise ValueError("pawn development runtime timestep drifted")
    data = mujoco.MjData(model)
    initialize_robot_poses(model, data)

    actuator_ids: list[int] = []
    qpos_addresses: list[int] = []
    reset_pose = np.asarray(reset["left_arm_joint_pose_radians"], dtype=np.float64)
    if reset_pose.shape != (6,) or not np.isfinite(reset_pose).all():
        raise ValueError("pawn development reset pose is invalid")
    for joint_name, value in zip(ROBOT_JOINTS, reset_pose, strict=True):
        full_name = f"left_{joint_name}"
        joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, full_name)
        actuator_id = mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_ACTUATOR, full_name
        )
        if joint_id < 0 or actuator_id < 0:
            raise ValueError(f"pawn runtime is missing {full_name}")
        address = int(model.jnt_qposadr[joint_id])
        data.qpos[address] = value
        data.ctrl[actuator_id] = value
        actuator_ids.append(actuator_id)
        qpos_addresses.append(address)
    mujoco.mj_forward(model, data)

    piece_bodies = _piece_bodies(model)
    if len(piece_bodies) != 16 or TARGET_PIECE_ID not in piece_bodies:
        raise ValueError("pawn runtime inventory changed")
    before = {
        name: np.asarray(data.xpos[body_id], dtype=np.float64).copy()
        for name, body_id in piece_bodies.items()
    }
    robot_ids = {
        body_id
        for body_id in range(model.nbody)
        if str(mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id) or "")
        .startswith(("left_", "right_"))
    }
    piece_ids = set(piece_bodies.values())
    robot_piece_contact = False
    for _ in range(int(reset["settle_physics_steps"])):
        mujoco.mj_step(model, data)
        for contact_index in range(data.ncon):
            contact = data.contact[contact_index]
            bodies = {
                int(model.geom_bodyid[contact.geom1]),
                int(model.geom_bodyid[contact.geom2]),
            }
            robot_piece_contact = robot_piece_contact or bool(
                bodies & robot_ids and bodies & piece_ids
            )
    if robot_piece_contact:
        raise RuntimeError("pawn development reset contacted a pawn")
    displacements = {
        name: float(np.linalg.norm(data.xpos[body_id] - before[name]))
        for name, body_id in piece_bodies.items()
    }
    if max(displacements.values()) > float(
        reset["maximum_piece_displacement_after_settle_m"]
    ):
        raise RuntimeError("pawn development reset displaced a pawn")
    upright = [
        float(np.asarray(data.xmat[body_id]).reshape(3, 3)[2, 2])
        for body_id in piece_bodies.values()
    ]
    if min(upright) < 0.95:
        raise RuntimeError("pawn development reset toppled a pawn")

    return PawnDevelopmentRuntime(
        model=model,
        data=data,
        actuator_ids=np.asarray(actuator_ids, dtype=np.int32),
        qpos_addresses=np.asarray(qpos_addresses, dtype=np.int32),
        piece_bodies=piece_bodies,
        initial_state=integration_state(model, data),
    )


def _robot_piece_contact(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    robot_body_ids: set[int],
    piece_body_ids: set[int],
) -> bool:
    for contact_index in range(data.ncon):
        contact = data.contact[contact_index]
        bodies = {
            int(model.geom_bodyid[contact.geom1]),
            int(model.geom_bodyid[contact.geom2]),
        }
        if bodies & robot_body_ids and bodies & piece_body_ids:
            return True
    return False


def _jaw_piece_contact(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    jaw_body_ids: set[int],
    piece_body_ids: set[int],
) -> bool:
    for contact_index in range(data.ncon):
        contact = data.contact[contact_index]
        bodies = {
            int(model.geom_bodyid[contact.geom1]),
            int(model.geom_bodyid[contact.geom2]),
        }
        if bodies & jaw_body_ids and bodies & piece_body_ids:
            return True
    return False


def evaluate_policy_rollout(
    rollout_directory: Path,
    *,
    output_path: Path,
) -> dict[str, Any]:
    rollout_directory = rollout_directory.resolve()
    receipt_path = rollout_directory / "rollout_receipt.json"
    trajectory_path = rollout_directory / "trajectory.npz"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("schema_version") != ROLLOUT_SCHEMA:
        raise ValueError("unsupported pawn rollout receipt")
    if receipt.get("piece_id") != TARGET_PIECE_ID:
        raise ValueError("pawn rollout selected the wrong piece")
    if receipt.get("destination_square") != DESTINATION_SQUARE:
        raise ValueError("pawn rollout selected the wrong destination")
    if receipt.get("action_owner") != "learned_policy":
        raise ValueError("pawn rollout action ownership changed")
    if receipt.get("all_actions_model_derived") is not True:
        raise ValueError("pawn rollout did not assert model-derived actions")
    if int(receipt.get("assistance_frames", -1)) != 0:
        raise ValueError("pawn rollout used assistance")
    if receipt.get("render_backend") != "osmesa":
        raise ValueError("pawn rollout render backend changed")

    with np.load(trajectory_path) as arrays:
        actions = np.asarray(arrays["actions"], dtype=np.float32)
        initial_state = np.asarray(arrays["initial_integration_state"], dtype=np.float64)
        final_state = np.asarray(arrays["final_integration_state"], dtype=np.float64)
        query_starts = np.asarray(arrays["query_starts"], dtype=np.int64)
        query_chunks = np.asarray(arrays["query_chunks"], dtype=np.float32)
    if actions.shape != (SAMPLE_COUNT, 6) or not np.isfinite(actions).all():
        raise ValueError("pawn rollout actions have the wrong shape")
    if query_chunks.ndim != 3 or query_chunks.shape[1:] != (16, 6):
        raise ValueError("pawn rollout query chunks have the wrong shape")
    expected_starts = np.arange(0, SAMPLE_COUNT, 8, dtype=np.int64)
    if not np.array_equal(query_starts, expected_starts):
        raise ValueError("pawn rollout query schedule changed")
    chunks = [
        (int(start), chunk)
        for start, chunk in zip(query_starts, query_chunks, strict=True)
    ]
    for sample_step, recorded in enumerate(actions):
        expected, info = aggregate_temporal_action(
            chunks,
            sample_step=sample_step,
            method="mean",
        )
        if info["assistance_frames"] != 0 or not np.array_equal(expected, recorded):
            raise ValueError(
                f"executed action {sample_step} is not the frozen model-chunk mean"
            )

    runtime = build_frozen_pawn_development_runtime()
    model, data = runtime.model, runtime.data
    if not np.array_equal(runtime.initial_state, initial_state):
        raise ValueError("pawn rollout initial state differs from the frozen reset")
    piece_bodies = runtime.piece_bodies
    target_body = piece_bodies[TARGET_PIECE_ID]
    other_body_ids = {
        body_id for name, body_id in piece_bodies.items() if name != TARGET_PIECE_ID
    }
    initial_positions = {
        name: np.asarray(data.xpos[body_id], dtype=np.float64).copy()
        for name, body_id in piece_bodies.items()
    }
    initial_target = initial_positions[TARGET_PIECE_ID]
    maximum_height = float(initial_target[2])
    left_robot_ids = {
        body_id
        for body_id in range(model.nbody)
        if str(mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id) or "")
        .startswith("left_")
    }
    wrong_piece_contact = False
    bounds = model.actuator_ctrlrange[runtime.actuator_ids]
    clipped_coordinates = 0
    for action in actions:
        clipped = np.clip(action, bounds[:, 0], bounds[:, 1]).astype(np.float64)
        clipped_coordinates += int(np.count_nonzero(clipped != action))
        data.ctrl[runtime.actuator_ids] = clipped
        for _ in range(PHYSICS_STEPS_PER_ACTION):
            mujoco.mj_step(model, data)
            wrong_piece_contact = wrong_piece_contact or _robot_piece_contact(
                model, data, left_robot_ids, other_body_ids
            )
            maximum_height = max(maximum_height, float(data.xpos[target_body][2]))

    replay_final_state = integration_state(model, data)
    exact_replay = np.array_equal(replay_final_state, final_state)
    final_position = np.asarray(data.xpos[target_body], dtype=np.float64)
    target_position = np.asarray(
        board_square_center(
            DESTINATION_SQUARE,
            board_center_in_table_frame_xy_m=registered_board_center(
                load_source_contract(CONTRACT_PATH_V3)["scene"]["scene_id"]
            ),
        ),
        dtype=np.float64,
    )
    other_displacements = {
        name: float(np.linalg.norm(data.xpos[body_id] - initial_positions[name]))
        for name, body_id in piece_bodies.items()
        if name != TARGET_PIECE_ID
    }
    worst_other_piece = max(other_displacements, key=other_displacements.get)
    rotation = np.asarray(data.xmat[target_body], dtype=np.float64).reshape(3, 3)
    pinch_local = _pinch_offset(model, data, "left")
    evaluator = load_pawn_evaluator_contract(EVALUATOR_PATH)
    measurements = {
        "selected_piece_identity": True,
        "maximum_piece_rise_m": maximum_height - float(initial_target[2]),
        "final_xy_error_m": float(np.linalg.norm(final_position[:2] - target_position[:2])),
        "final_height_error_m": float(abs(final_position[2] - target_position[2])),
        "final_upright_cosine": float(rotation[2, 2]),
        "final_linear_speed_m_s": float(
            np.linalg.norm(np.asarray(data.cvel[target_body][3:], dtype=np.float64))
        ),
        "gripper_clearance_m": float(
            np.linalg.norm(
                _pinch_point(model, data, "left", pinch_local) - final_position
            )
        ),
        "maximum_other_piece_displacement_m": other_displacements[worst_other_piece],
        "target_displacement_m": float(np.linalg.norm(final_position - initial_target)),
        "wrong_piece_contact": wrong_piece_contact,
        "final_jaw_piece_contact": _jaw_piece_contact(
            model, data, _jaw_body_ids(model, "left"), set(piece_bodies.values())
        ),
        "assistance_frames": 0,
        "declared_action_owner": True,
        "executed_action_count": len(actions),
        "recorded_action_count": SAMPLE_COUNT,
        "exact_sample_hold_state_replay": exact_replay,
    }
    scored = score_pawn_consequences(measurements, evaluator)
    failed_gates = [name for name, gate in scored["gates"].items() if not gate["passed"]]
    result = {
        "schema_version": EVALUATION_SCHEMA,
        "proof_class": "learned_policy_simulation",
        "rollout_receipt_sha256": sha256_file(receipt_path),
        "trajectory_sha256": sha256_file(trajectory_path),
        "evaluator_contract_sha256": pawn_evaluator_sha256(EVALUATOR_PATH),
        "evaluator_module_sha256": sha256_file(Path(__file__)),
        "groot_execution_module_sha256": sha256_file(
            REPO_ROOT / "src/sim2claw/groot_execution.py"
        ),
        "piece_id": TARGET_PIECE_ID,
        "destination_square": DESTINATION_SQUARE,
        "sample_count": SAMPLE_COUNT,
        "physics_action_count": SAMPLE_COUNT * PHYSICS_STEPS_PER_ACTION,
        "query_count": len(query_starts),
        "action_clipped_coordinate_count": clipped_coordinates,
        "all_actions_model_derived": True,
        "assistance_frames": 0,
        "exact_final_mjstate_replay": exact_replay,
        "protected_other_piece_count": 15,
        "worst_displaced_other_piece": worst_other_piece,
        "other_piece_displacements_m": other_displacements,
        "measurements": measurements,
        "gates": scored["gates"],
        "strict_success": bool(scored["success"]),
        "failed_gates": failed_gates,
        "terminal_outcome": (
            "pawn_released_upright_on_target"
            if scored["success"]
            else "pawn_pick_place_consequence_gate_failed"
        ),
        "physical_reach_authority": False,
        "rank_1_2_generalization_authority": False,
        "held_out_rows_used": 0,
        "created_at": datetime.now(UTC).isoformat(),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    result["receipt_path"] = str(output_path)
    result["receipt_sha256"] = sha256_file(output_path)
    return result
