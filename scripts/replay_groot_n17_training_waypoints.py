#!/usr/bin/env python3
"""Compare GR00T waypoint execution adapters on training-only expert rows."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import mujoco
import numpy as np

from sim2claw.chess_task import ChessRookLiftEnv
from sim2claw.groot_chess import (
    _apply_sparse_board_curriculum,
    _case_map,
    _episode_shim,
    _piece_bodies,
    collect_groot_expert_episode,
    evaluate_episode,
    groot_task_contract_sha256,
    load_groot_task_contract,
)
from sim2claw.groot_execution import physics_targets_from_waypoints
from sim2claw.scene import board_square_center


def array_sha256(value: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(value).tobytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--episode-index",
        type=int,
        action="append",
        dest="episode_indices",
        help="Training episode to replay; repeat this option. Defaults to all.",
    )
    args = parser.parse_args()

    contract = load_groot_task_contract()
    episode_indices = (
        list(range(len(contract["training_episodes"])))
        if args.episode_indices is None
        else args.episode_indices
    )
    if not episode_indices or len(set(episode_indices)) != len(episode_indices):
        parser.error("episode indices must be a nonempty unique list")

    results = []
    adapters = ("sample_hold", "linear_same_phase")
    for episode_index in episode_indices:
        if not 0 <= episode_index < len(contract["training_episodes"]):
            parser.error(f"training episode index out of range: {episode_index}")
        episode_row = contract["training_episodes"][episode_index]
        case = _case_map(contract, "training")[episode_row["case_id"]]
        source = collect_groot_expert_episode(
            contract,
            split="training",
            episode_index=episode_index,
            render_frames=False,
        )
        adapter_results = []
        for adapter in adapters:
            env = ChessRookLiftEnv(
                _episode_shim(contract, case),
                seed=int(episode_row["seed"]),
                piece_offset_xy_m=tuple(
                    float(value) for value in episode_row["piece_planar_offset_m"]
                ),
            )
            _apply_sparse_board_curriculum(env, contract)
            target = np.asarray(
                board_square_center(str(case["target_square"])),
                dtype=np.float64,
            )
            initial_height = float(env.piece_position()[2])
            initial_other_positions = {
                name: np.asarray(env.data.xpos[body_id], dtype=np.float64).copy()
                for name, body_id in _piece_bodies(env.model).items()
            }
            maximum_height = initial_height
            physics_actions = 0
            physics_digest = hashlib.sha256()
            interpolated_intervals = 0
            for sample_step, current in enumerate(source.actions):
                next_waypoint = (
                    source.actions[sample_step + 1]
                    if sample_step + 1 < len(source.actions)
                    else None
                )
                physics_targets, adapter_info = physics_targets_from_waypoints(
                    contract,
                    sample_step=sample_step,
                    current=current,
                    next_waypoint=next_waypoint,
                    adapter=adapter,
                )
                interpolated_intervals += int(
                    bool(adapter_info["interpolated_to_next_waypoint"])
                )
                for physics_target in physics_targets:
                    physics_digest.update(
                        np.ascontiguousarray(physics_target).tobytes()
                    )
                    env.step(physics_target)
                    physics_actions += 1
                    maximum_height = max(
                        maximum_height,
                        float(env.piece_position()[2]),
                    )
            verdict = evaluate_episode(
                env,
                contract,
                target=target,
                initial_height=initial_height,
                maximum_height=maximum_height,
                initial_other_positions=initial_other_positions,
                action_count=physics_actions,
            )
            adapter_results.append(
                {
                    "adapter": adapter,
                    "interpolated_sample_intervals": interpolated_intervals,
                    "physics_controls_sha256": physics_digest.hexdigest(),
                    "verdict": verdict,
                }
            )
        results.append(
            {
                "episode_index": episode_index,
                "case_id": str(episode_row["case_id"]),
                "source_actions_sha256": array_sha256(source.actions),
                "source_verdict": source.verdict,
                "adapter_replays": adapter_results,
            }
        )

    pass_counts = {
        adapter: sum(
            next(
                replay["verdict"]["success"]
                for replay in row["adapter_replays"]
                if replay["adapter"] == adapter
            )
            for row in results
        )
        for adapter in adapters
    }
    result = {
        "schema_version": "sim2claw.groot_n17_training_waypoint_replay.v1",
        "proof_class": "training_only_simulation_diagnostic",
        "promotion_authority": False,
        "split": "training",
        "held_out_rows_accessed": 0,
        "task_contract_sha256": groot_task_contract_sha256(),
        "mujoco_version": mujoco.__version__,
        "source_episode_pass_count": sum(
            bool(row["source_verdict"]["success"]) for row in results
        ),
        "adapter_pass_counts": pass_counts,
        "episode_count": len(results),
        "results": results,
    }
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
