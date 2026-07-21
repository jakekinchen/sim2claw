#!/usr/bin/env python3
"""Compare two seeded NVIDIA GR00T open-loop diagnostic logs."""

from __future__ import annotations

import argparse
from collections import defaultdict
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


def mean(values: list[float]) -> float:
    return sum(values) / len(values)


def reduction(before: float, after: float) -> float:
    return (before - after) / before


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-log", type=Path, required=True)
    parser.add_argument("--candidate-log", type=Path, required=True)
    parser.add_argument("--episodes", type=Path, required=True)
    parser.add_argument("--baseline-id", required=True)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    baseline = parse_log(args.baseline_log)
    candidate = parse_log(args.candidate_log)
    if baseline.keys() != candidate.keys():
        raise ValueError("baseline and candidate trajectory sets differ")

    episodes = {
        int(row["episode_index"]): row
        for line in args.episodes.read_text().splitlines()
        if line
        for row in [json.loads(line)]
    }
    if baseline.keys() != episodes.keys():
        raise ValueError("evaluated trajectories do not match the episode catalog")

    grouped: dict[str, list[int]] = defaultdict(list)
    trajectory_rows: list[dict[str, Any]] = []
    for episode in sorted(baseline):
        task = str(episodes[episode]["tasks"][0])
        grouped[task].append(episode)
        trajectory_rows.append(
            {
                "episode_index": episode,
                "task": task,
                "baseline": baseline[episode],
                "candidate": candidate[episode],
                "mse_reduction_fraction": reduction(
                    baseline[episode]["mse"], candidate[episode]["mse"]
                ),
                "mae_reduction_fraction": reduction(
                    baseline[episode]["mae"], candidate[episode]["mae"]
                ),
            }
        )

    def aggregate(indices: list[int]) -> dict[str, Any]:
        baseline_mse = mean([baseline[index]["mse"] for index in indices])
        baseline_mae = mean([baseline[index]["mae"] for index in indices])
        candidate_mse = mean([candidate[index]["mse"] for index in indices])
        candidate_mae = mean([candidate[index]["mae"] for index in indices])
        return {
            "episode_indices": indices,
            "episode_count": len(indices),
            "baseline_mse": baseline_mse,
            "candidate_mse": candidate_mse,
            "mse_reduction_fraction": reduction(baseline_mse, candidate_mse),
            "baseline_mae": baseline_mae,
            "candidate_mae": candidate_mae,
            "mae_reduction_fraction": reduction(baseline_mae, candidate_mae),
        }

    payload = {
        "schema_version": "sim2claw.groot_open_loop_comparison.v1",
        "proof_class": "in_sample_open_loop_diagnostic",
        "baseline_id": args.baseline_id,
        "candidate_id": args.candidate_id,
        "trajectory_count": len(baseline),
        "overall": aggregate(sorted(baseline)),
        "by_task": {task: aggregate(indices) for task, indices in sorted(grouped.items())},
        "trajectories": trajectory_rows,
        "promotion_authority": False,
        "physical_policy_result": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
