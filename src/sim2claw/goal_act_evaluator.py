"""Independent CPU/fp32 consequence evaluator for goal-conditioned ACT.

The evaluator opens a frozen cohort only after training, authenticates the
checkpoint and its training receipt, executes model-owned action chunks in
MuJoCo, and owns the resulting verdict.  Training and Studio never supply
success fields.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import mujoco
import numpy as np
import torch

from .act_model import load_act_checkpoint_snapshot, read_act_checkpoint_snapshot
from .act_pick_place import encode_observation, load_act_pick_place_task_contract, task_contract_sha256
from .grasp import _jaw_body_ids, _piece_bodies, _pinch_offset, _pinch_point
from .learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .learning_factory_goal_data import _relative_pose
from .goal_act_training import TRAINING_RECEIPT_SCHEMA
from .paths import REPO_ROOT
from .render import write_rgb_png
from .scene import (
    CURRENT_TASK_PIECE_LAYOUT,
    ROBOT_JOINTS,
    TELEOP_PAWN_SOURCE_SQUARES,
    board_square_center,
    build_scene_spec,
    initialize_robot_poses,
    registered_board_center,
)
from .source_episode import (
    CONTRACT_PATH_V4,
    CURRENT_BOARD_POSE_ID,
    CURRENT_SCENE_ID,
    EPISODE_SCHEMA,
    RECEIPT_SCHEMA,
    build_source_sample,
    load_source_episode,
    source_contract_sha256,
    tree_manifest,
)


COHORT_SCHEMA = "sim2claw.goal_act_evaluation_cohort.v1"
EVALUATION_SCHEMA = "sim2claw.goal_act_evaluation_receipt.v1"
SKILL_PATTERN = re.compile(r"^pawn_([b-g][12])_to_([b-g][12])$")


def _integration_state(model: mujoco.MjModel, data: mujoco.MjData) -> list[float]:
    size = mujoco.mj_stateSize(model, mujoco.mjtState.mjSTATE_INTEGRATION)
    state = np.empty(size, dtype=np.float64)
    mujoco.mj_getState(model, data, state, mujoco.mjtState.mjSTATE_INTEGRATION)
    return state.astype(float).tolist()


def _write_evaluation_reset_episode(
    *,
    output_directory: Path,
    runtime_skill_id: str,
    scene_piece_id: str,
) -> dict[str, Any]:
    """Create a sealed simulator reset, not a demonstration or success claim."""

    match = SKILL_PATTERN.fullmatch(runtime_skill_id)
    if match is None:
        raise ValueError("evaluation runtime skill identity is malformed")
    source_square, destination_square = match.groups()
    output_directory.mkdir(parents=True, exist_ok=False)
    model = build_scene_spec(piece_layout=CURRENT_TASK_PIECE_LAYOUT).compile()
    data = mujoco.MjData(model)
    initialize_robot_poses(model, data)
    piece_body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, scene_piece_id)
    piece_joint = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_JOINT, f"{scene_piece_id}_free"
    )
    if piece_body < 0 or piece_joint < 0:
        raise ValueError(f"evaluation carrier piece is missing: {scene_piece_id}")
    piece_qpos = int(model.jnt_qposadr[piece_joint])
    source_xyz = np.asarray(board_square_center(source_square), dtype=np.float64)
    source_xyz[2] = float(data.qpos[piece_qpos + 2])
    data.qpos[piece_qpos : piece_qpos + 3] = source_xyz
    data.qvel[int(model.jnt_dofadr[piece_joint]) : int(model.jnt_dofadr[piece_joint]) + 6] = 0.0
    mujoco.mj_forward(model, data)

    episode_id = f"evaluation-reset-{runtime_skill_id}"
    target_xyz = np.asarray(board_square_center(destination_square), dtype=np.float64)
    target_xyz[2] = source_xyz[2]
    target_pose = [*target_xyz.astype(float).tolist(), *data.xquat[piece_body].astype(float).tolist()]
    gripper_body = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_BODY, "left_gripper"
    )
    joint_ids = [
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, f"left_{name}")
        for name in ROBOT_JOINTS
    ]
    joint_qpos = [int(model.jnt_qposadr[joint]) for joint in joint_ids]
    joint_qvel = [int(model.jnt_dofadr[joint]) for joint in joint_ids]
    action = [float(data.qpos[address]) for address in joint_qpos]
    rgb: dict[str, dict[str, Any]] = {}
    for stream in ("top", "wrist"):
        frame = output_directory / "rgb" / stream / "000000.png"
        write_rgb_png(frame, np.zeros((2, 2, 3), dtype=np.uint8))
        rgb[stream] = {
            "available": True,
            "path": frame.relative_to(output_directory).as_posix(),
            "sha256": sha256_file(frame),
            "timestamp_monotonic_seconds": 0.0,
        }
    row = build_source_sample(
        episode_id=episode_id,
        sample_index=0,
        timestamp_monotonic_seconds=0.0,
        instruction=(
            f"Evaluate the pawn move from {source_square} to {destination_square}; "
            "this row supplies reset state only."
        ),
        raw_sample={
            "follower_actual_position_rad": action,
            "follower_actual_velocity_rad_s": [float(data.qvel[address]) for address in joint_qvel],
            "end_effector_pose_world": [
                *data.xpos[gripper_body].astype(float).tolist(),
                *data.xquat[gripper_body].astype(float).tolist(),
            ],
            "gripper_joint_position_rad": action[-1],
            "selected_piece_pose_world": [
                *data.xpos[piece_body].astype(float).tolist(),
                *data.xquat[piece_body].astype(float).tolist(),
            ],
            "continuous_target_pose_world": target_pose,
            "follower_command_rad": action,
            "contacts": [],
            "simulator_events": [{"type": "expert_phase", "phase": "stand_off"}],
        },
        rgb=rgb,
        action_owner="planner",
        assistance=False,
        intervention=False,
    )
    samples_path = output_directory / "samples.jsonl"
    samples_path.write_text(
        json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    integration = _integration_state(model, data)
    privileged = {
        "episode_id": episode_id,
        "sample_index": 0,
        "policy_adapter_access": False,
        "state": {"integration_state_float64": integration},
    }
    privileged_path = output_directory / "evaluator_privileged_state.jsonl"
    privileged_path.write_text(json.dumps(privileged, sort_keys=True) + "\n", encoding="utf-8")
    initial_path = output_directory / "initial_evaluator_privileged_state.json"
    atomic_write_json(
        initial_path,
        {
            "schema_version": "sim2claw.evaluator_initial_privileged_state.v1",
            "episode_id": episode_id,
            "policy_adapter_access": False,
            "state": {
                "available": True,
                "mj_state_spec": "mjSTATE_INTEGRATION",
                "integration_state_float64": integration,
            },
        },
    )
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "source_episode_schema": EPISODE_SCHEMA,
        "source_contract_sha256": source_contract_sha256(CONTRACT_PATH_V4),
        "task_id": "chess_pick_place_source_episode_v4",
        "scene_id": CURRENT_SCENE_ID,
        "board_pose_id": CURRENT_BOARD_POSE_ID,
        "recording_id": episode_id,
        "proof_class": "sealed_simulation_evaluation_reset_only",
        "piece_id": scene_piece_id,
        "source_square": source_square,
        "destination_square": destination_square,
        "sample_count": 1,
        "samples_sha256": sha256_file(samples_path),
        "evaluator_privileged_state_path": privileged_path.name,
        "evaluator_privileged_state_sha256": sha256_file(privileged_path),
        "initial_evaluator_privileged_state_path": initial_path.name,
        "initial_evaluator_privileged_state_sha256": sha256_file(initial_path),
        "rgb_streams": tree_manifest(output_directory / "rgb"),
        "training_rows_authorized": 0,
    }
    atomic_write_json(output_directory / "recording_receipt.json", receipt)
    return receipt


def generate_goal_act_evaluation_cohort(
    *,
    output_directory: Path,
    task_contract_path: Path = REPO_ROOT / "configs/tasks/chess_pick_place_act_state_v1.json",
    minimum_success_rate: float = 0.75,
) -> dict[str, Any]:
    """Generate one sealed simulator reset for every frozen B-G runtime skill."""

    task = load_act_pick_place_task_contract(task_contract_path)
    held_seeds = [int(value) for value in task["splits"]["held_out_seeds"]]
    held_layouts = list(task["splits"]["distractor_layouts"]["held_out"])
    carrier_by_file = {square[0]: f"brown_pawn_{square}" for square in TELEOP_PAWN_SOURCE_SQUARES}
    cases = []
    for index, skill_id in enumerate(task["runtime_scope"]["eligible_skill_ids"]):
        match = SKILL_PATTERN.fullmatch(skill_id)
        assert match is not None
        source_square, destination_square = match.groups()
        scene_piece_id = carrier_by_file[source_square[0]]
        episode_directory = output_directory / "episodes" / skill_id
        _write_evaluation_reset_episode(
            output_directory=episode_directory,
            runtime_skill_id=skill_id,
            scene_piece_id=scene_piece_id,
        )
        cases.append(
            {
                "case_id": f"heldout-{skill_id}",
                "candidate_seed": held_seeds[index % len(held_seeds)],
                "runtime_skill_id": skill_id,
                "object_destination_pair": (
                    f"brown_pawn_{source_square}:runtime_{destination_square}"
                ),
                "scene_piece_id": scene_piece_id,
                "distractor_layout": held_layouts[index % len(held_layouts)],
                "episode_directory": str(episode_directory),
                "object_dimensions_m": [0.03, 0.03, 0.053],
                "gripper_aperture_mapping": {
                    "mapping_id": "so101_parallel_jaw_affine_v1",
                    "scale_m_per_rad": 0.02,
                    "offset_m": 0.01,
                },
                "horizon_actions": 1,
            }
        )
    return freeze_goal_act_evaluation_cohort(
        cases=cases,
        output_path=output_directory / "cohort.json",
        minimum_success_rate=minimum_success_rate,
        task_contract_path=task_contract_path,
    )


def freeze_goal_act_evaluation_cohort(
    *,
    cases: list[dict[str, Any]],
    output_path: Path,
    minimum_success_rate: float = 0.75,
    task_contract_path: Path = REPO_ROOT / "configs/tasks/chess_pick_place_act_state_v1.json",
) -> dict[str, Any]:
    """Write a sealed held-out cohort before training begins."""

    task = load_act_pick_place_task_contract(task_contract_path)
    split = task["splits"]
    held_seeds = {int(value) for value in split["held_out_seeds"]}
    held_layouts = set(split["distractor_layouts"]["held_out"])
    runtime_skills = set(task["runtime_scope"]["eligible_skill_ids"])
    if not cases:
        raise ValueError("evaluation cohort requires at least one case")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for case in cases:
        case_id = str(case.get("case_id") or "")
        if not case_id or case_id in seen:
            raise ValueError("evaluation cases need unique identities")
        seen.add(case_id)
        seed = int(case.get("candidate_seed", -1))
        pair = str(case.get("object_destination_pair") or "")
        runtime_skill_id = str(case.get("runtime_skill_id") or "")
        layout = str(case.get("distractor_layout") or "")
        if seed not in held_seeds or runtime_skill_id not in runtime_skills or layout not in held_layouts:
            raise ValueError("evaluation case is not a member of the frozen held-out split")
        episode = Path(str(case.get("episode_directory") or "")).resolve()
        if not episode.is_dir():
            raise ValueError(f"evaluation episode is missing: {episode}")
        receipt, _ = load_source_episode(episode)
        piece_id, target_cell_id = pair.split(":", 1)
        scene_piece_id = str(case.get("scene_piece_id") or piece_id)
        if receipt.get("piece_id") != scene_piece_id:
            raise ValueError("evaluation reset carrier differs from its receipt")
        match = SKILL_PATTERN.fullmatch(runtime_skill_id)
        if match is None:
            raise ValueError("evaluation runtime skill identity is malformed")
        source_square, destination_square = match.groups()
        if (
            receipt.get("source_square") != source_square
            or receipt.get("destination_square") != destination_square
            or not piece_id.endswith(f"_{source_square}")
        ):
            raise ValueError("evaluation episode differs from the runtime skill scope")
        initial_payload = json.loads(
            (
                episode
                / str(receipt["initial_evaluator_privileged_state_path"])
            ).read_text(encoding="utf-8")
        )
        initial_state = initial_payload.get("state") or {}
        integration = initial_state.get("integration_state_float64")
        if initial_state.get("available") is not True or not isinstance(
            integration, list
        ):
            raise ValueError(
                "evaluation episode has no simulator integration-state reset"
            )
        dimensions = [float(value) for value in case.get("object_dimensions_m", [])]
        mapping = case.get("gripper_aperture_mapping")
        if len(dimensions) != 3 or not isinstance(mapping, dict):
            raise ValueError("evaluation case lacks observable object/aperture metadata")
        normalized.append(
            {
                "case_id": case_id,
                "candidate_seed": seed,
                "object_destination_pair": pair,
                "runtime_skill_id": runtime_skill_id,
                "piece_id": piece_id,
                "scene_piece_id": scene_piece_id,
                "target_cell_id": target_cell_id,
                "distractor_layout": layout,
                "episode_directory": str(episode),
                "source_recording_id": receipt["recording_id"],
                "source_receipt_sha256": sha256_file(episode / "recording_receipt.json"),
                "object_dimensions_m": dimensions,
                "gripper_aperture_mapping": mapping,
                "horizon_actions": int(case.get("horizon_actions", receipt["sample_count"])),
            }
        )
    if not 0.0 <= minimum_success_rate <= 1.0:
        raise ValueError("minimum success rate must be between zero and one")
    unsigned = {
        "schema_version": COHORT_SCHEMA,
        "task_id": task["task_id"],
        "task_contract_sha256": task_contract_sha256(task_contract_path),
        "proof_class": "sealed_simulation_goal_conditioned_evaluation",
        "frozen_before_training": True,
        "created_at": datetime.now(UTC).isoformat(),
        "role": "held_out_evaluator_only",
        "case_count": len(normalized),
        "cases": normalized,
        "minimum_success_rate": float(minimum_success_rate),
        "minimum_cases_per_runtime_skill": int(
            task["runtime_scope"]["minimum_held_out_cases_per_skill"]
        ),
        "training_rows": 0,
        "evaluator_owner": "separate_cpu_fp32_consequence_evaluator",
    }
    cohort = {**unsigned, "cohort_sha256": canonical_digest(unsigned)}
    atomic_write_json(output_path, cohort)
    return cohort


def load_goal_act_evaluation_cohort(
    path: Path,
    *,
    task_contract_path: Path = REPO_ROOT / "configs/tasks/chess_pick_place_act_state_v1.json",
) -> dict[str, Any]:
    cohort = json.loads(path.read_text(encoding="utf-8"))
    if cohort.get("schema_version") != COHORT_SCHEMA:
        raise ValueError("unsupported goal ACT evaluation cohort")
    unsigned = {key: value for key, value in cohort.items() if key != "cohort_sha256"}
    if cohort.get("cohort_sha256") != canonical_digest(unsigned):
        raise ValueError("evaluation cohort digest mismatch")
    if cohort.get("frozen_before_training") is not True or cohort.get("training_rows") != 0:
        raise ValueError("evaluation cohort is not sealed from training")
    if cohort.get("evaluator_owner") != "separate_cpu_fp32_consequence_evaluator":
        raise ValueError("evaluation cohort owner changed")
    if cohort.get("task_contract_sha256") != task_contract_sha256(task_contract_path):
        raise ValueError("evaluation cohort uses another task contract")
    return cohort


def _gate(measured: float | bool, comparison: str, threshold: float | bool) -> dict[str, Any]:
    if comparison == ">=":
        passed = measured >= threshold
    elif comparison == "<=":
        passed = measured <= threshold
    elif comparison == "==":
        passed = measured == threshold
    else:
        raise ValueError("unsupported evaluator comparison")
    return {"measured": measured, "comparison": comparison, "threshold": threshold, "passed": bool(passed)}


def _body_contact(model: mujoco.MjModel, data: mujoco.MjData, left: set[int], right: set[int]) -> bool:
    for index in range(data.ncon):
        contact = data.contact[index]
        bodies = {
            int(model.geom_bodyid[contact.geom1]),
            int(model.geom_bodyid[contact.geom2]),
        }
        if bodies & left and bodies & right:
            return True
    return False


def _skill_vector(
    *,
    pinch: np.ndarray,
    piece: np.ndarray,
    target: np.ndarray,
    initial_height: float,
    jaw_contact: bool,
    final_supported: bool,
) -> list[float]:
    if np.linalg.norm(pinch - piece) > 0.015:
        index = 0
    elif piece[2] - initial_height < 0.04:
        index = 1
    elif np.linalg.norm(piece[:2] - target[:2]) > 0.025:
        index = 2
    elif jaw_contact or not final_supported:
        index = 3
    else:
        index = 4
    return [float(value == index) for value in range(5)]


def _run_case(
    case: dict[str, Any],
    *,
    model_policy: torch.nn.Module,
    statistics: dict[str, torch.Tensor],
    checkpoint: dict[str, Any],
    task: dict[str, Any],
) -> dict[str, Any]:
    episode = Path(case["episode_directory"])
    receipt, source_rows = load_source_episode(episode)
    if sha256_file(episode / "recording_receipt.json") != case["source_receipt_sha256"]:
        raise ValueError("evaluation source receipt changed after cohort freeze")
    initial_payload = json.loads(
        (episode / receipt["initial_evaluator_privileged_state_path"]).read_text(encoding="utf-8")
    )
    initial_state = np.asarray(initial_payload["state"]["integration_state_float64"], dtype=np.float64)
    scene_id = str(receipt["scene_id"])
    model = build_scene_spec(
        piece_layout=CURRENT_TASK_PIECE_LAYOUT,
        board_center_in_table_frame_xy_m=registered_board_center(scene_id),
        include_visual_props=scene_id == CURRENT_SCENE_ID,
    ).compile()
    data = mujoco.MjData(model)
    expected_size = mujoco.mj_stateSize(model, mujoco.mjtState.mjSTATE_INTEGRATION)
    if initial_state.shape != (expected_size,):
        raise ValueError("evaluation initial state has the wrong simulator size")
    mujoco.mj_setState(model, data, initial_state, mujoco.mjtState.mjSTATE_INTEGRATION)
    mujoco.mj_forward(model, data)
    pieces = _piece_bodies(model)
    piece_id = str(case["scene_piece_id"])
    if piece_id not in pieces:
        raise ValueError("held-out piece is absent from the evaluation scene")
    piece_body = pieces[piece_id]
    other_bodies = set(pieces.values()) - {piece_body}
    jaw_bodies = _jaw_body_ids(model, "left")
    robot_bodies = {
        body_id
        for body_id in range(model.nbody)
        if str(mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id) or "").startswith("left_")
    }
    actuators = np.asarray(
        [mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, f"left_{joint}") for joint in ROBOT_JOINTS],
        dtype=np.int32,
    )
    joints = np.asarray(
        [mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, f"left_{joint}") for joint in ROBOT_JOINTS],
        dtype=np.int32,
    )
    qpos = np.asarray([model.jnt_qposadr[joint] for joint in joints], dtype=np.int32)
    qvel = np.asarray([model.jnt_dofadr[joint] for joint in joints], dtype=np.int32)
    gripper_body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "left_gripper")
    pinch_local = _pinch_offset(model, data, "left")
    initial_positions = {name: data.xpos[body].copy() for name, body in pieces.items()}
    initial_height = float(data.xpos[piece_body][2])
    target = np.asarray(source_rows[0]["goal"]["continuous_target_pose_world"], dtype=np.float64)
    maximum_height = initial_height
    wrong_piece_contact = False
    queue: deque[np.ndarray] = deque()
    actions: list[list[float]] = []
    aperture = case["gripper_aperture_mapping"]
    scale = float(aperture["scale_m_per_rad"])
    offset = float(aperture["offset_m"])
    dimensions = [float(value) for value in case["object_dimensions_m"]]
    horizon = min(int(case["horizon_actions"]), len(source_rows))
    n_action_steps = int(checkpoint["training"]["n_action_steps"])
    model_policy.eval()
    for _ in range(horizon):
        if not queue:
            piece_pose = np.asarray([*data.xpos[piece_body], *data.xquat[piece_body]], dtype=np.float64)
            end_effector = np.asarray([*data.xpos[gripper_body], *data.xquat[gripper_body]], dtype=np.float64)
            pinch = _pinch_point(model, data, "left", pinch_local)
            jaw_contact = _body_contact(model, data, jaw_bodies, {piece_body})
            final_supported = abs(float(piece_pose[2] - target[2])) <= float(task["evaluator"]["maximum_final_height_error_m"])
            features = {
                "robot_joint_position": data.qpos[qpos],
                "robot_joint_velocity": data.qvel[qvel],
                "end_effector_pose": end_effector,
                "gripper_aperture": [max(0.0, scale * float(data.qpos[qpos[-1]]) + offset)],
                "selected_piece_pose": piece_pose,
                "continuous_target_pose": target,
                "end_effector_in_piece_frame": _relative_pose(piece_pose, end_effector),
                "piece_in_target_frame": _relative_pose(target, piece_pose),
                "object_descriptor": [0.0, 1.0, 0.0, 0.0, *dimensions],
                "observable_skill_id": _skill_vector(
                    pinch=pinch,
                    piece=piece_pose[:3],
                    target=target[:3],
                    initial_height=initial_height,
                    jaw_contact=jaw_contact,
                    final_supported=final_supported,
                ),
                "selected_piece_contact": [float(jaw_contact)],
            }
            observation = torch.from_numpy(encode_observation(task, features)).unsqueeze(0)
            normalized = (
                observation - statistics["observation_mean"]
            ) / statistics["observation_std"]
            with torch.inference_mode():
                predicted = model_policy.predict_action_chunk(normalized).squeeze(0)
            decoded = (
                predicted * statistics["action_std"] + statistics["action_mean"]
            ).cpu().numpy()
            if decoded.shape[1] != 6 or not np.isfinite(decoded).all():
                raise ValueError("goal ACT policy emitted invalid actions")
            queue.extend(row.copy() for row in decoded[:n_action_steps])
        action = np.asarray(queue.popleft(), dtype=np.float32)
        bounds = model.actuator_ctrlrange[actuators]
        data.ctrl[actuators] = np.clip(action, bounds[:, 0], bounds[:, 1]).astype(np.float64)
        for _ in range(10):
            mujoco.mj_step(model, data)
            wrong_piece_contact = wrong_piece_contact or _body_contact(
                model, data, robot_bodies, other_bodies
            )
            maximum_height = max(maximum_height, float(data.xpos[piece_body][2]))
        actions.append(action.astype(float).tolist())

    final_position = data.xpos[piece_body].copy()
    final_rotation = data.xmat[piece_body].reshape(3, 3).copy()
    other_displacements = {
        name: float(np.linalg.norm(data.xpos[body] - initial_positions[name]))
        for name, body in pieces.items()
        if name != piece_id
    }
    evaluator = task["evaluator"]
    measurements = {
        "maximum_piece_rise_m": maximum_height - initial_height,
        "final_xy_error_m": float(np.linalg.norm(final_position[:2] - target[:2])),
        "final_height_error_m": float(abs(final_position[2] - target[2])),
        "final_upright_cosine": float(final_rotation[2, 2]),
        "final_linear_speed_m_s": float(np.linalg.norm(data.cvel[piece_body][3:])),
        "gripper_clearance_m": float(np.linalg.norm(_pinch_point(model, data, "left", pinch_local) - final_position)),
        "maximum_other_piece_displacement_m": max(other_displacements.values()),
        "wrong_piece_contact": wrong_piece_contact,
        "final_jaw_piece_contact": _body_contact(model, data, jaw_bodies, {piece_body}),
        "model_owned_action_count": len(actions),
        "expected_action_count": horizon,
        "assistance_frames": 0,
    }
    gates = {
        "maximum_piece_rise": _gate(measurements["maximum_piece_rise_m"], ">=", float(evaluator["minimum_piece_rise_m"])),
        "final_xy_error": _gate(measurements["final_xy_error_m"], "<=", float(evaluator["maximum_final_xy_error_m"])),
        "final_height_error": _gate(measurements["final_height_error_m"], "<=", float(evaluator["maximum_final_height_error_m"])),
        "final_upright": _gate(measurements["final_upright_cosine"], ">=", float(evaluator["minimum_final_upright_cosine"])),
        "final_linear_speed": _gate(measurements["final_linear_speed_m_s"], "<=", float(evaluator["maximum_final_linear_speed_m_s"])),
        "gripper_clearance": _gate(measurements["gripper_clearance_m"], ">=", float(evaluator["minimum_gripper_clearance_m"])),
        "other_piece_displacement": _gate(measurements["maximum_other_piece_displacement_m"], "<=", float(evaluator["maximum_other_piece_displacement_m"])),
        "wrong_piece_contact": _gate(measurements["wrong_piece_contact"], "==", False),
        "final_jaw_contact": _gate(measurements["final_jaw_piece_contact"], "==", False),
        "model_owned_actions": _gate(measurements["model_owned_action_count"], "==", horizon),
        "assistance_frames": _gate(measurements["assistance_frames"], "==", 0),
    }
    success = all(gate["passed"] for gate in gates.values())
    return {
        "case_id": case["case_id"],
        "candidate_seed": case["candidate_seed"],
        "object_destination_pair": case["object_destination_pair"],
        "runtime_skill_id": case["runtime_skill_id"],
        "distractor_layout": case["distractor_layout"],
        "source_recording_id": receipt["recording_id"],
        "measurements": measurements,
        "gates": gates,
        "strict_success": success,
        "failure_codes": sorted(name for name, gate in gates.items() if not gate["passed"]),
        "action_trace_sha256": canonical_digest(actions),
    }


def evaluate_goal_act(
    *,
    checkpoint_path: Path,
    training_receipt_path: Path,
    cohort_path: Path,
    output_path: Path,
    task_contract_path: Path = REPO_ROOT / "configs/tasks/chess_pick_place_act_state_v1.json",
) -> dict[str, Any]:
    """Run every sealed case and issue the evaluator-owned scorecard."""

    torch.set_num_threads(1)
    task = load_act_pick_place_task_contract(task_contract_path)
    cohort = load_goal_act_evaluation_cohort(cohort_path, task_contract_path=task_contract_path)
    training = json.loads(training_receipt_path.read_text(encoding="utf-8"))
    if training.get("schema_version") != TRAINING_RECEIPT_SCHEMA:
        raise ValueError("unsupported goal ACT training receipt")
    unsigned_training = {key: value for key, value in training.items() if key != "artifact_sha256"}
    if training.get("artifact_sha256") != canonical_digest(unsigned_training):
        raise ValueError("goal ACT training receipt digest mismatch")
    cohort_created = datetime.fromisoformat(str(cohort["created_at"]))
    training_started = datetime.fromisoformat(str(training["started_at"]))
    if cohort_created.tzinfo is None or training_started.tzinfo is None:
        raise ValueError("cohort/training timestamps must be timezone-aware")
    if cohort_created >= training_started:
        raise ValueError("evaluation cohort was not frozen before training")
    snapshot = read_act_checkpoint_snapshot(
        checkpoint_path, expected_sha256=str(training["checkpoint_sha256"])
    )
    model, statistics, checkpoint = load_act_checkpoint_snapshot(
        snapshot, device=torch.device("cpu")
    )
    if checkpoint.get("task_id") != task["task_id"]:
        raise ValueError("checkpoint uses another goal task")
    if checkpoint.get("task_contract_sha256") != task_contract_sha256(task_contract_path):
        raise ValueError("checkpoint uses another goal ACT contract")
    if checkpoint.get("training", {}).get("dataset_sha256") != training["dataset_sha256"]:
        raise ValueError("checkpoint dataset lineage differs from the training receipt")
    if next(model.parameters()).dtype != torch.float32:
        raise ValueError("independent goal ACT evaluator requires float32")
    case_results = [
        _run_case(
            case,
            model_policy=model,
            statistics=statistics,
            checkpoint=checkpoint,
            task=task,
        )
        for case in cohort["cases"]
    ]
    successes = sum(bool(case["strict_success"]) for case in case_results)
    success_rate = successes / len(case_results)
    by_pair = {
        skill_id: {
            "case_count": sum(row["runtime_skill_id"] == skill_id for row in case_results),
            "success_count": sum(row["runtime_skill_id"] == skill_id and row["strict_success"] for row in case_results),
        }
        for skill_id in task["runtime_scope"]["eligible_skill_ids"]
    }
    minimum_cases = int(cohort["minimum_cases_per_runtime_skill"])
    all_skills_pass = all(
        row["case_count"] >= minimum_cases
        and row["success_count"] == row["case_count"]
        for row in by_pair.values()
    )
    admitted = (
        success_rate >= float(cohort["minimum_success_rate"])
        and all_skills_pass
    )
    unsigned = {
        "schema_version": EVALUATION_SCHEMA,
        "task_id": task["task_id"],
        "task_contract_sha256": task_contract_sha256(task_contract_path),
        "checkpoint_sha256": snapshot.sha256,
        "training_receipt_sha256": sha256_file(training_receipt_path),
        "dataset_sha256": training["dataset_sha256"],
        "cohort_sha256": cohort["cohort_sha256"],
        "cohort_opened_after_training": True,
        "held_out_training_rows": 0,
        "evaluator_owner": "separate_cpu_fp32_consequence_evaluator",
        "device": "cpu",
        "dtype": "float32",
        "case_results": case_results,
        "success_count": successes,
        "case_count": len(case_results),
        "success_rate": success_rate,
        "minimum_success_rate": cohort["minimum_success_rate"],
        "b_g_scorecard": by_pair,
        "all_runtime_skills_pass": all_skills_pass,
        "verdict": "admitted" if admitted else "terminal_negative",
        "training_can_promote": False,
    }
    receipt = {**unsigned, "artifact_sha256": canonical_digest(unsigned)}
    atomic_write_json(output_path, receipt)
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--training-receipt", type=Path, required=True)
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--task-contract", type=Path, default=REPO_ROOT / "configs/tasks/chess_pick_place_act_state_v1.json")
    args = parser.parse_args(argv)
    result = evaluate_goal_act(
        checkpoint_path=args.checkpoint,
        training_receipt_path=args.training_receipt,
        cohort_path=args.cohort,
        output_path=args.output,
        task_contract_path=args.task_contract,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["verdict"] == "admitted" else 2


if __name__ == "__main__":
    raise SystemExit(main())
