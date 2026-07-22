#!/usr/bin/env python3
"""Run the frozen SAIL grasp-retention anchor screen."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.sail.grasp_retention_resolution import CONTRACT_PATH, run_anchor_screen


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    receipt = run_anchor_screen(
        contract_path=args.contract, output_root=args.output_root
    )
    print(
        json.dumps(
            {
                "candidate_count": receipt["candidate_count"],
                "anchor_pass_count": receipt["anchor_pass_count"],
                "all_actions_byte_identical": receipt[
                    "all_actions_byte_identical"
                ],
                "ranking": receipt["ranking"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
