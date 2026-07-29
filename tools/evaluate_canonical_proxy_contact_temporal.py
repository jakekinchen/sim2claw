#!/usr/bin/env python3
"""Run the frozen canonical proxy-only contact challenger."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.canonical_proxy_contact_temporal import replay
from sim2claw.paths import REPO_ROOT


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--contract",
        type=Path,
        default=REPO_ROOT
        / "configs/evaluations/canonical_proxy_contact_temporal_v2.json",
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
                "passing_case_ids": receipt["passing_case_ids"],
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
