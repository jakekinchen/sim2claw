#!/usr/bin/env python3
"""Compare correct and deliberately wrong language in a GR00T diagnostic."""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
from typing import Any


METRIC = re.compile(
    r"MSE for trajectory (?P<episode>\d+): (?P<mse>[0-9.eE+-]+), "
    r"MAE: (?P<mae>[0-9.eE+-]+)"
)


def parse_log(path: Path) -> dict[int, dict[str, float]]:
    rows: dict[int, dict[str, float]] = {}
    for match in METRIC.finditer(path.read_text()):
        episode = int(match.group("episode"))
        if episode in rows:
            raise ValueError(f"duplicate trajectory metric in {path}: {episode}")
        rows[episode] = {
            "mse": float(match.group("mse")),
            "mae": float(match.group("mae")),
        }
    if not rows:
        raise ValueError(f"no trajectory metrics in {path}")
    return rows


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mean(values: list[float]) -> float:
    return sum(values) / len(values)


def increase(correct: float, wrong: float) -> float:
    return (wrong - correct) / correct


def reduction(wrong: float, correct: float) -> float:
    return (wrong - correct) / wrong


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--correct-log", type=Path, required=True)
    parser.add_argument("--wrong-log", type=Path, required=True)
    parser.add_argument("--episodes", type=Path, required=True)
    parser.add_argument("--counterfactual-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    correct = parse_log(args.correct_log)
    wrong = parse_log(args.wrong_log)
    if correct.keys() != wrong.keys():
        raise ValueError("correct and wrong-instruction trajectory sets differ")

    episodes = {
        int(row["episode_index"]): row
        for line in args.episodes.read_text().splitlines()
        if line
        for row in [json.loads(line)]
    }
    if correct.keys() != episodes.keys():
        raise ValueError("evaluated trajectories do not match the episode catalog")
    receipt = json.loads(args.counterfactual_receipt.read_text())
    if not receipt.get("all_instructions_changed"):
        raise ValueError("counterfactual receipt does not change every instruction")
    task_mapping = receipt["task_mapping"]

    grouped: dict[str, list[int]] = defaultdict(list)
    trajectory_rows: list[dict[str, Any]] = []
    for episode in sorted(correct):
        task = str(episodes[episode]["tasks"][0])
        grouped[task].append(episode)
        trajectory_rows.append(
            {
                "episode_index": episode,
                "correct_instruction": task,
                "wrong_instruction": task_mapping[task],
                "correct": correct[episode],
                "wrong": wrong[episode],
                "wrong_instruction_mse_increase_fraction": increase(
                    correct[episode]["mse"], wrong[episode]["mse"]
                ),
                "wrong_instruction_mae_increase_fraction": increase(
                    correct[episode]["mae"], wrong[episode]["mae"]
                ),
                "correct_instruction_has_lower_mse": (
                    correct[episode]["mse"] < wrong[episode]["mse"]
                ),
                "correct_instruction_has_lower_mae": (
                    correct[episode]["mae"] < wrong[episode]["mae"]
                ),
            }
        )

    def aggregate(indices: list[int]) -> dict[str, Any]:
        correct_mse = mean([correct[index]["mse"] for index in indices])
        correct_mae = mean([correct[index]["mae"] for index in indices])
        wrong_mse = mean([wrong[index]["mse"] for index in indices])
        wrong_mae = mean([wrong[index]["mae"] for index in indices])
        return {
            "episode_indices": indices,
            "episode_count": len(indices),
            "correct_mse": correct_mse,
            "wrong_mse": wrong_mse,
            "wrong_instruction_mse_increase_fraction": increase(
                correct_mse, wrong_mse
            ),
            "correct_vs_wrong_mse_reduction_fraction": reduction(
                wrong_mse, correct_mse
            ),
            "correct_mae": correct_mae,
            "wrong_mae": wrong_mae,
            "wrong_instruction_mae_increase_fraction": increase(
                correct_mae, wrong_mae
            ),
            "correct_vs_wrong_mae_reduction_fraction": reduction(
                wrong_mae, correct_mae
            ),
            "correct_instruction_mse_win_count": sum(
                correct[index]["mse"] < wrong[index]["mse"] for index in indices
            ),
            "correct_instruction_mae_win_count": sum(
                correct[index]["mae"] < wrong[index]["mae"] for index in indices
            ),
        }

    payload = {
        "schema_version": "sim2claw.groot_counterfactual_language_comparison.v1",
        "proof_class": "in_sample_counterfactual_language_diagnostic",
        "checkpoint_id": "checkpoint-5000",
        "counterfactual_receipt_sha256": sha256_file(
            args.counterfactual_receipt
        ),
        "trajectory_count": len(correct),
        "overall": aggregate(sorted(correct)),
        "by_correct_instruction": {
            task: aggregate(indices) for task, indices in sorted(grouped.items())
        },
        "trajectories": trajectory_rows,
        "held_out": False,
        "closed_loop": False,
        "promotion_authority": False,
        "physical_policy_result": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
