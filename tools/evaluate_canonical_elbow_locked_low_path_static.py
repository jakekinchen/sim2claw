#!/usr/bin/env python3
"""Run the frozen elbow-locked low-direct-path static successor."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.canonical_elbow_locked_low_path_static import (
    enumerate_and_freeze,
)
from sim2claw.paths import REPO_ROOT


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    arguments = parser.parse_args()
    contract = json.loads(
        arguments.contract.read_text(encoding="utf-8")
    )
    receipt = enumerate_and_freeze(
        arguments.contract.resolve(),
        (REPO_ROOT / contract["output_directory"]).resolve(),
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
