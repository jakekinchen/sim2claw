#!/usr/bin/env python3
"""Compile training-only endpoint appearance intervals from C922 videos."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.paths import REPO_ROOT
from sim2claw.pawn_bg_endpoint_motion import run_endpoint_motion_pipeline


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO_ROOT / "outputs" / "pawn_bg_endpoint_motion_v1" / "train",
    )
    args = parser.parse_args()
    receipt = run_endpoint_motion_pipeline(output_root=args.output_root)
    print(json.dumps(receipt["summary"], indent=2, sort_keys=True))
    print(args.output_root.resolve() / "endpoint_motion_receipt.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
