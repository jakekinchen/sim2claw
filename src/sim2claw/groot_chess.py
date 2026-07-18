"""Dynamic language-conditioned chess demonstrations for GR00T N1.7.

The dense reward in this module is a diagnostic signal for curriculum design.
Only the separately computed consequence gates in ``evaluate_episode`` own a
success verdict. All data produced here is synthetic simulation evidence.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import shutil
import subprocess
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
from .paths import DEFAULT_GROOT_CHESS_TASK_CONFIG
from .scene import ROBOT_JOINTS, board_square_center


def load_groot_task_contract(
    path: Path = DEFAULT_GROOT_CHESS_TASK_CONFIG,
) -> dict[str, Any]:
    contract = json.loads(path.read_text(encoding="utf-8"))
    if contract.get("schema_version") != "sim2claw.chess_pick_place_groot_task.v1":
        raise ValueError("unsupported GR00T chess task contract")
    if not contract.get("frozen_before_training"):
        raise ValueError("GR00T chess task must be frozen before training")
    if contract["model"]["embodiment_tag"] != "NEW_EMBODIMENT":
        raise ValueError("custom simulated SO-101 must use NEW_EMBODIMENT")
    if contract["observation"]["state_dimension"] != len(ROBOT_JOINTS):
        raise ValueError("state dimension must match the simulated arm")
    if contract["action"]["dimension"] != len(ROBOT_JOINTS):
        raise ValueError("action dimension must match the simulated arm")

    timestep = float(contract["episode"]["physics_timestep_seconds"])
    stride = int(contract["episode"]["sample_every_physics_steps"])
    fps = int(contract["episode"]["sample_fps"])
    if not math.isclose(timestep * stride, 1.0 / fps, abs_tol=1e-12):
        raise ValueError("dataset sampling cadence does not match its declared FPS")

    training_cases = {case["case_id"] for case in contract["training_cases"]}
    held_out_cases = {case["case_id"] for case in contract["held_out_cases"]}
    if training_cases & held_out_cases:
        raise ValueError("training and held-out case IDs must be disjoint")
    training_seeds = {int(row["seed"]) for row in contract["training_episodes"]}
    held_out_seeds = {int(row["seed"]) for row in contract["held_out_episodes"]}
    if training_seeds & held_out_seeds:
        raise ValueError("training and held-out seeds must be disjoint")
    if any(row["case_id"] not in training_cases for row in contract["training_episodes"]):
        raise ValueError("training episode references a non-training case")
    if any(row["case_id"] not in held_out_cases for row in contract["held_out_episodes"]):
        raise ValueError("held-out episode references a non-held-out case")
    if any(int(row.get("training_rows", -1)) != 0 for row in contract["held_out_episodes"]):
        raise ValueError("held-out episodes must contribute zero training rows")
    for case in (*contract["training_cases"], *contract["held_out_cases"]):
        board_square_center(str(case["target_square"]))
    return contract


def groot_task_contract_sha256(
    path: Path = DEFAULT_GROOT_CHESS_TASK_CONFIG,
) -> str:
    payload = json.dumps(
        load_groot_task_contract(path),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _case_map(contract: dict[str, Any], split: str) -> dict[str, dict[str, Any]]:
    return {
        str(case["case_id"]): case
        for case in contract[f"{split}_cases"]
    }


def _episode_shim(
    contract: dict[str, Any],
    case: dict[str, Any],
) -> dict[str, Any]:
    phase_steps = contract["episode"]["phase_physics_steps"]
    return {
        "scene": {
            "arm": contract["scene"]["arm"],
            "piece": case["piece"],
        },
        "episode": {
            "settle_steps": contract["episode"]["settle_steps_before"],
            "control_interval_physics_steps": 1,
            "control_horizon": sum(int(value) for value in phase_steps.values())
            + int(contract["episode"]["settle_steps_after"]),
        },
    }


def _body_upright_cosine(data: mujoco.MjData, body_id: int) -> float:
    rotation = np.asarray(data.xmat[body_id], dtype=np.float64).reshape(3, 3)
    return float(rotation[2, 2])


def _piece_linear_speed(env: ChessRookLiftEnv) -> float:
    joint_id = mujoco.mj_name2id(
        env.model,
        mujoco.mjtObj.mjOBJ_JOINT,
        f"{env.piece_name}_free",
    )
    dof_address = int(env.model.jnt_dofadr[joint_id])
    return float(np.linalg.norm(env.data.qvel[dof_address : dof_address + 3]))


def _apply_sparse_board_curriculum(
    env: ChessRookLiftEnv,
    contract: dict[str, Any],
) -> None:
    """Park non-curriculum pieces below the world with collisions disabled."""

    if contract["scene"]["board_occupancy_mode"] != "sparse_two_piece_curriculum":
        raise ValueError("unsupported board occupancy mode")
    active = set(contract["scene"]["active_pieces"])
    pieces = _piece_bodies(env.model)
    if env.piece_name not in active or not active <= set(pieces):
        raise ValueError("active piece set does not contain the requested piece")
    for name, body_id in pieces.items():
        if name in active:
            continue
        joint_id = mujoco.mj_name2id(
            env.model,
            mujoco.mjtObj.mjOBJ_JOINT,
            f"{name}_free",
        )
        qpos_address = int(env.model.jnt_qposadr[joint_id])
        dof_address = int(env.model.jnt_dofadr[joint_id])
        env.data.qpos[qpos_address + 2] = -2.0
        env.data.qvel[dof_address : dof_address + 6] = 0.0
        env.model.body_gravcomp[body_id] = 1.0
        for geom_id in range(env.model.ngeom):
            if int(env.model.geom_bodyid[geom_id]) == body_id:
                env.model.geom_contype[geom_id] = 0
                env.model.geom_conaffinity[geom_id] = 0
    mujoco.mj_forward(env.model, env.data)


@dataclass
class GrootExpertEpisode:
    case_id: str
    instruction: str
    piece: str
    target_square: str
    seed: int
    piece_offset_xy_m: tuple[float, float]
    states: np.ndarray
    actions: np.ndarray
    rewards: np.ndarray
    phases: list[str]
    frames: list[np.ndarray]
    verdict: dict[str, Any]
    maximum_ik_residual_m: float


def _diagnostic_reward(
    env: ChessRookLiftEnv,
    contract: dict[str, Any],
    target: np.ndarray,
    initial_height: float,
    phase: str,
) -> float:
    reward = contract["diagnostic_reward"]
    weights = reward["weights"]
    piece = env.piece_position()
    lift_progress = float(
        np.clip(
            (piece[2] - initial_height)
            / float(contract["evaluator"]["minimum_piece_rise_m"]),
            0.0,
            1.0,
        )
    )
    destination_proximity = 1.0 - float(
        np.clip(
            np.linalg.norm(piece[:2] - target[:2])
            / float(reward["destination_distance_scale_m"]),
            0.0,
            1.0,
        )
    )
    released = float(
        phase in {"release", "retreat", "settle"} and not env.jaw_piece_contact()
    )
    upright = float(np.clip(_body_upright_cosine(env.data, env.piece_body), 0.0, 1.0))
    settled = float(
        phase == "settle"
        and np.linalg.norm(piece[:2] - target[:2])
        <= float(contract["evaluator"]["maximum_final_xy_error_m"])
        and _piece_linear_speed(env)
        <= float(contract["evaluator"]["maximum_final_linear_speed_m_s"])
    )
    return float(
        weights["lift_progress"] * lift_progress
        + weights["destination_proximity"] * destination_proximity
        + weights["released"] * released
        + weights["upright"] * upright
        + weights["settled"] * settled
    )


def evaluate_episode(
    env: ChessRookLiftEnv,
    contract: dict[str, Any],
    *,
    target: np.ndarray,
    initial_height: float,
    maximum_height: float,
    initial_other_positions: dict[str, np.ndarray],
    action_count: int,
) -> dict[str, Any]:
    evaluator = contract["evaluator"]
    final_position = env.piece_position()
    final_xy_error = float(np.linalg.norm(final_position[:2] - target[:2]))
    final_height_error = float(abs(final_position[2] - target[2]))
    final_upright = _body_upright_cosine(env.data, env.piece_body)
    final_linear_speed = _piece_linear_speed(env)
    gripper_clearance = float(
        np.linalg.norm(
            _pinch_point(env.model, env.data, env.arm, env.pinch_local)
            - final_position
        )
    )
    current_pieces = _piece_bodies(env.model)
    protected_pieces = set(contract["scene"]["active_pieces"])
    other_displacements = {
        name: float(np.linalg.norm(env.data.xpos[body_id] - initial_other_positions[name]))
        for name, body_id in current_pieces.items()
        if name != env.piece_name and name in protected_pieces
    }
    worst_other_piece = (
        max(other_displacements, key=other_displacements.get)
        if other_displacements
        else None
    )
    maximum_other_displacement = (
        other_displacements[worst_other_piece] if worst_other_piece is not None else 0.0
    )
    expected_physics_actions = (
        sum(int(value) for value in contract["episode"]["phase_physics_steps"].values())
        + int(contract["episode"]["settle_steps_after"])
    )
    gates = {
        "minimum_piece_rise": {
            "measured": float(maximum_height - initial_height),
            "comparison": ">=",
            "threshold": evaluator["minimum_piece_rise_m"],
        },
        "final_xy_error": {
            "measured": final_xy_error,
            "comparison": "<=",
            "threshold": evaluator["maximum_final_xy_error_m"],
        },
        "final_height_error": {
            "measured": final_height_error,
            "comparison": "<=",
            "threshold": evaluator["maximum_final_height_error_m"],
        },
        "final_upright_cosine": {
            "measured": final_upright,
            "comparison": ">=",
            "threshold": evaluator["minimum_final_upright_cosine"],
        },
        "final_linear_speed": {
            "measured": final_linear_speed,
            "comparison": "<=",
            "threshold": evaluator["maximum_final_linear_speed_m_s"],
        },
        "gripper_clearance": {
            "measured": gripper_clearance,
            "comparison": ">=",
            "threshold": evaluator["minimum_gripper_clearance_m"],
        },
        "maximum_other_piece_displacement": {
            "measured": maximum_other_displacement,
            "comparison": "<=",
            "threshold": evaluator["maximum_other_piece_displacement_m"],
        },
        "no_final_jaw_contact": {
            "measured": env.jaw_piece_contact(),
            "comparison": "==",
            "threshold": False,
        },
        "model_owned_actions": {
            "measured": action_count,
            "comparison": "==",
            "threshold": expected_physics_actions,
        },
        "assistance_frames": {
            "measured": 0,
            "comparison": "==",
            "threshold": 0,
        },
    }
    for gate in gates.values():
        if gate["comparison"] == ">=":
            gate["passed"] = gate["measured"] >= gate["threshold"]
        elif gate["comparison"] == "<=":
            gate["passed"] = gate["measured"] <= gate["threshold"]
        else:
            gate["passed"] = gate["measured"] == gate["threshold"]
    success = all(bool(gate["passed"]) for gate in gates.values())
    return {
        "schema_version": "sim2claw.groot_chess_consequence_verdict.v1",
        "evaluator_owner": evaluator["owner"],
        "gates": gates,
        "success": success,
        "terminal_outcome": (
            "piece_released_upright_on_target_square"
            if success
            else "pick_place_consequence_gate_failed"
        ),
        "diagnostic_reward_has_promotion_authority": False,
        "worst_displaced_other_piece": worst_other_piece,
        "physical_authority": False,
    }


def collect_groot_expert_episode(
    contract: dict[str, Any],
    *,
    split: str,
    episode_index: int,
    render_frames: bool = True,
) -> GrootExpertEpisode:
    if split not in {"training", "held_out"}:
        raise ValueError("split must be training or held_out")
    episode_row = contract[f"{split}_episodes"][episode_index]
    case = _case_map(contract, split)[episode_row["case_id"]]
    offset = tuple(float(value) for value in episode_row["piece_planar_offset_m"])
    env = ChessRookLiftEnv(
        _episode_shim(contract, case),
        seed=int(episode_row["seed"]),
        piece_offset_xy_m=offset,
    )
    _apply_sparse_board_curriculum(env, contract)
    target = np.asarray(board_square_center(str(case["target_square"])), dtype=np.float64)
    piece_start = env.piece_position()
    initial_height = float(piece_start[2])
    all_piece_ids = _piece_bodies(env.model)
    initial_other_positions = {
        name: np.asarray(env.data.xpos[body_id], dtype=np.float64).copy()
        for name, body_id in all_piece_ids.items()
    }
    kind = env.piece_name.split("_")[1]
    away = env.mount[:2] - piece_start[:2]
    away /= max(float(np.linalg.norm(away)), 1e-9)
    neck = np.asarray(
        [piece_start[0], piece_start[1], initial_height + NECK_HEIGHT_M[kind]],
        dtype=np.float64,
    )
    stand_off = neck + np.asarray([away[0] * 0.055, away[1] * 0.055, 0.03])

    render_width = int(contract["episode"]["render_width"])
    render_height = int(contract["episode"]["render_height"])
    renderer = (
        mujoco.Renderer(env.model, height=render_height, width=render_width)
        if render_frames
        else None
    )
    states: list[np.ndarray] = []
    actions: list[np.ndarray] = []
    rewards: list[float] = []
    phases: list[str] = []
    frames: list[np.ndarray] = []
    physics_step = 0
    maximum_height = initial_height
    ik_residuals: list[float] = []
    sample_stride = int(contract["episode"]["sample_every_physics_steps"])

    def solve(target_point: np.ndarray, jaw: float) -> np.ndarray:
        pose, residual = _solve_reach(
            env.model,
            env.data,
            env.arm,
            target_point,
            env.pinch_local,
        )
        ik_residuals.append(float(residual))
        if residual > 0.003:
            raise RuntimeError(f"expert IK residual is too large: {residual:.6f}")
        return _goal_vector(pose, jaw)

    def record(action: np.ndarray, phase: str) -> None:
        states.append(
            np.asarray(env.data.qpos[env.qpos_addresses], dtype=np.float32).copy()
        )
        actions.append(np.asarray(action, dtype=np.float32).copy())
        rewards.append(
            _diagnostic_reward(env, contract, target, initial_height, phase)
        )
        phases.append(phase)
        if renderer is not None:
            renderer.update_scene(env.data, camera=contract["scene"]["camera"])
            frames.append(renderer.render().copy())

    def execute_phase(name: str, goal: np.ndarray, count: int) -> None:
        nonlocal physics_step, maximum_height
        start = env.controls()
        ramp = max(1, min(count // 2, 160))
        for phase_step in range(count):
            blend = min(1.0, float(phase_step + 1) / float(ramp))
            action = start + blend * (goal - start)
            if physics_step % sample_stride == 0:
                record(action, name)
            env.step(action)
            maximum_height = max(maximum_height, float(env.piece_position()[2]))
            physics_step += 1

    phase_steps = contract["episode"]["phase_physics_steps"]
    try:
        execute_phase(
            "stand_off",
            solve(stand_off, JAW_OPEN_RAD),
            int(phase_steps["stand_off"]),
        )
        advance_goal = solve(neck, JAW_OPEN_RAD)
        execute_phase("advance", advance_goal, int(phase_steps["advance"]))
        close_goal = advance_goal.copy()
        close_goal[-1] = JAW_SHUT_RAD
        execute_phase("close", close_goal, int(phase_steps["close"]))
        execute_phase(
            "lift",
            solve(
                neck
                + np.asarray([0.0, 0.0, contract["episode"]["lift_height_m"]]),
                JAW_SHUT_RAD,
            ),
            int(phase_steps["lift"]),
        )

        grasp_offset = (
            _pinch_point(env.model, env.data, env.arm, env.pinch_local)
            - env.piece_position()
        )
        carry_point = target + grasp_offset + np.asarray(
            [0.0, 0.0, contract["episode"]["lift_height_m"]]
        )
        execute_phase(
            "transit",
            solve(carry_point, JAW_SHUT_RAD),
            int(phase_steps["transit"]),
        )

        grasp_offset = (
            _pinch_point(env.model, env.data, env.arm, env.pinch_local)
            - env.piece_position()
        )
        release_point = target + grasp_offset + np.asarray(
            [0.0, 0.0, contract["episode"]["release_height_m"]]
        )
        lower_goal = solve(release_point, JAW_SHUT_RAD)
        execute_phase("lower", lower_goal, int(phase_steps["lower"]))
        release_goal = lower_goal.copy()
        release_goal[-1] = JAW_OPEN_RAD
        execute_phase("release", release_goal, int(phase_steps["release"]))

        current_pinch = _pinch_point(env.model, env.data, env.arm, env.pinch_local)
        retreat_point = current_pinch + np.asarray(
            [away[0] * 0.05, away[1] * 0.05, 0.06]
        )
        retreat_goal = solve(retreat_point, JAW_OPEN_RAD)
        execute_phase("retreat", retreat_goal, int(phase_steps["retreat"]))
        execute_phase(
            "settle",
            retreat_goal,
            int(contract["episode"]["settle_steps_after"]),
        )
    finally:
        if renderer is not None:
            renderer.close()

    verdict = evaluate_episode(
        env,
        contract,
        target=target,
        initial_height=initial_height,
        maximum_height=maximum_height,
        initial_other_positions=initial_other_positions,
        action_count=physics_step,
    )
    state_array = np.asarray(states, dtype=np.float32)
    action_array = np.asarray(actions, dtype=np.float32)
    if state_array.shape != action_array.shape or state_array.shape[1] != len(ROBOT_JOINTS):
        raise RuntimeError("sampled state/action shape drifted from the contract")
    if render_frames and len(frames) != len(states):
        raise RuntimeError("video and low-dimensional sample counts diverged")
    return GrootExpertEpisode(
        case_id=str(case["case_id"]),
        instruction=str(case["instruction"]),
        piece=str(case["piece"]),
        target_square=str(case["target_square"]),
        seed=int(episode_row["seed"]),
        piece_offset_xy_m=offset,
        states=state_array,
        actions=action_array,
        rewards=np.asarray(rewards, dtype=np.float32),
        phases=phases,
        frames=frames,
        verdict=verdict,
        maximum_ik_residual_m=max(ik_residuals),
    )


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _write_video(path: Path, frames: list[np.ndarray], fps: int) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg is required to encode the GR00T dataset")
    height, width, channels = frames[0].shape
    if channels != 3:
        raise RuntimeError("GR00T video frames must be RGB")
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pixel_format",
        "rgb24",
        "-video_size",
        f"{width}x{height}",
        "-framerate",
        str(fps),
        "-i",
        "-",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(path),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    assert process.stdin is not None
    try:
        for frame in frames:
            process.stdin.write(np.ascontiguousarray(frame, dtype=np.uint8).tobytes())
    finally:
        process.stdin.close()
    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError(f"ffmpeg failed with exit code {return_code}")


def _stats(values: np.ndarray) -> dict[str, list[float]]:
    matrix = np.asarray(values, dtype=np.float32)
    if matrix.ndim == 1:
        matrix = matrix[:, None]
    return {
        "mean": matrix.mean(axis=0).tolist(),
        "std": matrix.std(axis=0).tolist(),
        "min": matrix.min(axis=0).tolist(),
        "max": matrix.max(axis=0).tolist(),
        "q01": np.quantile(matrix, 0.01, axis=0).tolist(),
        "q99": np.quantile(matrix, 0.99, axis=0).tolist(),
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def export_groot_dataset(
    output: Path,
    *,
    contract_path: Path = DEFAULT_GROOT_CHESS_TASK_CONFIG,
    max_episodes: int | None = None,
) -> dict[str, Any]:
    """Export evaluator-accepted training demonstrations as GR00T LeRobot v2."""

    import pyarrow as pa
    import pyarrow.parquet as pq

    contract = load_groot_task_contract(contract_path)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"refusing to overwrite non-empty dataset: {output}")
    meta_dir = output / "meta"
    data_dir = output / "data" / "chunk-000"
    video_key = str(contract["observation"]["video_original_key"])
    video_dir = output / "videos" / "chunk-000" / video_key
    for directory in (meta_dir, data_dir, video_dir):
        directory.mkdir(parents=True, exist_ok=True)

    episode_rows = contract["training_episodes"]
    if max_episodes is not None:
        episode_rows = episode_rows[:max_episodes]
    task_index_by_case = {
        str(case["case_id"]): index
        for index, case in enumerate(contract["training_cases"])
    }
    task_rows = [
        {"task_index": index, "task": str(case["instruction"])}
        for index, case in enumerate(contract["training_cases"])
    ]
    _write_jsonl(meta_dir / "tasks.jsonl", task_rows)

    episodes_meta: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    all_states: list[np.ndarray] = []
    all_actions: list[np.ndarray] = []
    all_rewards: list[np.ndarray] = []
    all_timestamps: list[np.ndarray] = []
    global_index = 0
    fps = int(contract["episode"]["sample_fps"])
    state_type = pa.list_(pa.float32(), len(ROBOT_JOINTS))

    for dataset_episode_index, _ in enumerate(episode_rows):
        episode = collect_groot_expert_episode(
            contract,
            split="training",
            episode_index=dataset_episode_index,
            render_frames=True,
        )
        if not episode.verdict["success"]:
            raise RuntimeError(
                f"expert episode {dataset_episode_index} failed frozen gates"
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
                pa.array(frame_indices == (length - 1), type=pa.bool_()),
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
                "piece_offset_xy_m": list(episode.piece_offset_xy_m),
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
    modality = {
        "state": {
            "single_arm": {"start": 0, "end": 5},
            "gripper": {"start": 5, "end": 6},
        },
        "action": {
            "single_arm": {"start": 0, "end": 5},
            "gripper": {"start": 5, "end": 6},
        },
        "video": {
            "front": {"original_key": video_key},
        },
        "annotation": {
            "human.task_description": {"original_key": "task_index"},
        },
    }
    _write_json(meta_dir / "modality.json", modality)

    feature_names = list(contract["observation"]["state_features"])
    action_names = list(contract["action"]["features"])
    height = int(contract["episode"]["render_height"])
    width = int(contract["episode"]["render_width"])
    info = {
        "codebase_version": "v2.1",
        "robot_type": "sim2claw_so101_simulation",
        "total_episodes": len(episodes_meta),
        "total_frames": global_index,
        "total_tasks": len(task_rows),
        "chunks_size": 1000,
        "fps": fps,
        "splits": {"train": f"0:{len(episodes_meta)}"},
        "data_path": "data/chunk-{episode_chunk:03d}/episode_{episode_index:06d}.parquet",
        "video_path": "videos/chunk-{episode_chunk:03d}/{video_key}/episode_{episode_index:06d}.mp4",
        "features": {
            "action": {"dtype": "float32", "shape": [6], "names": action_names},
            "observation.state": {
                "dtype": "float32",
                "shape": [6],
                "names": feature_names,
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
        "schema_version": "sim2claw.groot_lerobot_dataset_receipt.v1",
        "task_id": contract["task_id"],
        "task_contract_sha256": groot_task_contract_sha256(contract_path),
        "proof_class": "simulation_synthetic_vla_demonstration_dataset",
        "format": "GR00T LeRobot v2.1",
        "model_source_commit": contract["model"]["source_commit"],
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
