#!/usr/bin/env python3
"""Run the bounded action-frozen B--G grasp coordinate campaign."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.paths import REPO_ROOT
from sim2claw.pawn_bg_grasp_coordinate_descent import run_grasp_coordinate_descent


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO_ROOT / "outputs" / "pawn_bg_grasp_coordinate_descent_v1",
    )
    args = parser.parse_args()
    receipt = run_grasp_coordinate_descent(
        source_repository_root=REPO_ROOT,
        output_root=args.output_root,
    )
    print(
        json.dumps(
            {
                "frozen_composite_parameters": receipt[
                    "frozen_composite_parameters"
                ],
                "full_evaluation": {
                    name: value["summary"]
                    for name, value in receipt["full_evaluation"].items()
                },
                "paired_episode_bootstrap": receipt["paired_episode_bootstrap"],
                "advancement_gates": receipt["advancement_gates"],
                "verified_significant_consequence_advancement": receipt[
                    "verified_significant_consequence_advancement"
                ],
                "goal_loop_stop_decision": receipt["goal_loop_stop_decision"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    print(args.output_root.resolve() / "grasp_coordinate_descent_receipt.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
