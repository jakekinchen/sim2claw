#!/usr/bin/env python3
"""Compare a GR00T closed-loop rollout with its nominal expert by task phase."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

from sim2claw.groot_chess import load_groot_task_contract


def _matrix(table: pq.Table, column: str) -> np.ndarray:
    return np.asarray(table[column].combine_chunks().to_pylist(), dtype=np.float32)


def _errors(actual: np.ndarray, reference: np.ndarray) -> dict[str, object]:
    delta = actual - reference
    row_l2 = np.linalg.norm(delta, axis=1)
    crossings: dict[str, int | None] = {}
    for threshold in (0.05, 0.1, 0.25, 0.5):
        rows = np.flatnonzero(row_l2 >= threshold)
        crossings[f"{threshold:g}"] = int(rows[0]) if len(rows) else None
    return {
        "mae": float(np.mean(np.abs(delta))),
        "rmse": float(np.sqrt(np.mean(np.square(delta)))),
        "per_dimension_mae": np.mean(np.abs(delta), axis=0).tolist(),
        "first_row_l2": float(row_l2[0]),
        "final_row_l2": float(row_l2[-1]),
        "maximum_row_l2": float(np.max(row_l2)),
        "first_local_row_at_or_above_l2": crossings,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expert-parquet", type=Path, required=True)
    parser.add_argument("--rollout", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    contract = load_groot_task_contract()
    stride = int(contract["episode"]["sample_every_physics_steps"])
    phase_steps = contract["episode"]["phase_physics_steps"]

    expert_table = pq.read_table(args.expert_parquet)
    expert_states = _matrix(expert_table, "observation.state")
    expert_actions = _matrix(expert_table, "action")
    with np.load(args.rollout) as rollout:
        learned_states = np.asarray(rollout["states"], dtype=np.float32)
        learned_actions = np.asarray(rollout["actions"], dtype=np.float32)

    row_count = len(expert_states)
    if not (
        len(expert_actions)
        == len(learned_states)
        == len(learned_actions)
        == row_count
    ):
        raise ValueError(
            "expert and learned trajectories must contain the same number of rows: "
            f"{len(expert_states)}, {len(expert_actions)}, "
            f"{len(learned_states)}, {len(learned_actions)}"
        )

    phases: dict[str, dict[str, object]] = {}
    start = 0
    for name, physics_steps in phase_steps.items():
        if int(physics_steps) % stride:
            raise ValueError(f"phase {name} is not divisible by sample stride")
        end = start + int(physics_steps) // stride
        phases[str(name)] = {
            "start_row": start,
            "end_row_exclusive": end,
            "rows": end - start,
            "state_error": _errors(learned_states[start:end], expert_states[start:end]),
            "action_error": _errors(learned_actions[start:end], expert_actions[start:end]),
        }
        start = end

    if start < row_count:
        phases["settle"] = {
            "start_row": start,
            "end_row_exclusive": row_count,
            "rows": row_count - start,
            "state_error": _errors(learned_states[start:], expert_states[start:]),
            "action_error": _errors(learned_actions[start:], expert_actions[start:]),
        }

    payload = {
        "schema_version": "sim2claw.groot_n17_phase_divergence.v1",
        "proof_class": "learned_policy_simulation_diagnostic",
        "promotion_authority": False,
        "expert_parquet": str(args.expert_parquet.resolve()),
        "rollout": str(args.rollout.resolve()),
        "rows": row_count,
        "whole_episode": {
            "state_error": _errors(learned_states, expert_states),
            "action_error": _errors(learned_actions, expert_actions),
        },
        "phases": phases,
    }
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end="")


if __name__ == "__main__":
    main()
