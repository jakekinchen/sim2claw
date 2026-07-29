#!/usr/bin/env python3
"""Run the frozen canonical contact-witness diagnostic."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.canonical_contact_witness import diagnose
from sim2claw.paths import REPO_ROOT


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--contract",
        type=Path,
        default=REPO_ROOT
        / "configs/evaluations/canonical_contact_witness_v1.json",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    output = args.output or (REPO_ROOT / contract["output_path"])
    receipt = diagnose(args.contract.resolve(), output.resolve())
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
