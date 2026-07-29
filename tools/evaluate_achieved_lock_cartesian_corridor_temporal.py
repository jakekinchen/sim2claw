#!/usr/bin/env python3
"""Run the frozen 20-episode RP03C Cartesian-corridor dynamic gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.achieved_lock_cartesian_corridor_temporal import replay
from sim2claw.paths import REPO_ROOT


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--contract",
        type=Path,
        default=REPO_ROOT
        / "configs/evaluations/"
        "achieved_lock_cartesian_corridor_temporal_v1.json",
    )
    parser.add_argument("--output-directory", type=Path)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    output = args.output_directory or (
        REPO_ROOT / contract["output_directory"]
    )
    receipt = replay(args.contract.resolve(), output.resolve())
    print(
        json.dumps(
            {
                "status": receipt["status"],
                "episode_count": receipt["episode_count"],
                "direction_counts": receipt["direction_counts"],
                "passing_case_ids": receipt["passing_case_ids"],
                "passed": receipt["passed"],
                "physical_motion": receipt["physical_motion"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
