#!/usr/bin/env python3
"""Run the frozen calibrated-range canonical seeded static compiler."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.canonical_seeded_action_static_v2 import enumerate_and_freeze
from sim2claw.paths import REPO_ROOT


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--contract",
        type=Path,
        default=REPO_ROOT
        / "configs/evaluations/canonical_seeded_action_static_v2.json",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    output = args.output or (REPO_ROOT / contract["output_directory"])
    receipt = enumerate_and_freeze(
        args.contract.resolve(), output.resolve()
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
