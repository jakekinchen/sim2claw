#!/usr/bin/env python3
"""Run the frozen static-only action selector."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.canonical_wrist_path_static_selector import select_and_freeze
from sim2claw.paths import REPO_ROOT


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--contract",
        type=Path,
        default=REPO_ROOT
        / "configs/evaluations/canonical_wrist_path_static_selector_v1.json",
    )
    parser.add_argument("--output-directory", type=Path)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    output = args.output_directory or (
        REPO_ROOT / contract["output_directory"]
    )
    receipt = select_and_freeze(
        args.contract.resolve(), output.resolve()
    )
    print(
        json.dumps(
            {
                "status": receipt["status"],
                "selected": [
                    {
                        "case_id": row["case_id"],
                        "candidate": row["selected_candidate"],
                    }
                    for row in receipt["selected"]
                ],
                "direction_counts": receipt["direction_counts"],
                "passed": receipt["passed"],
                "physical_motion": receipt["physical_motion"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
