#!/usr/bin/env python3
"""Run the frozen elbow-locked wrist-path static successor."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.canonical_elbow_locked_wrist_path_static import (
    enumerate_and_freeze,
)
from sim2claw.paths import REPO_ROOT


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path)
    arguments = parser.parse_args()
    contract = json.loads(
        arguments.contract.read_text(encoding="utf-8")
    )
    output = arguments.output_directory or (
        REPO_ROOT / contract["output_directory"]
    )
    receipt = enumerate_and_freeze(
        arguments.contract.resolve(), output.resolve()
    )
    print(
        json.dumps(
            {
                "status": receipt["status"],
                "family_count": receipt["family_count"],
                "grid_result_count": receipt["grid_result_count"],
                "statically_eligible_family_count": receipt[
                    "statically_eligible_family_count"
                ],
                "direction_counts": receipt["direction_counts"],
                "elbow_lock": receipt["elbow_lock"],
                "passed": receipt["passed"],
                "physical_motion": receipt["physical_motion"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
