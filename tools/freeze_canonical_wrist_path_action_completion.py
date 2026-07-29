#!/usr/bin/env python3
"""Freeze the two unopened V4 wrist/path family actions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.canonical_wrist_path_action_completion import freeze_actions
from sim2claw.paths import REPO_ROOT


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--contract",
        type=Path,
        default=REPO_ROOT
        / "configs/evaluations/canonical_wrist_path_action_completion_v1.json",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    output = args.output or (REPO_ROOT / contract["output_directory"])
    receipt = freeze_actions(args.contract.resolve(), output.resolve())
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
