#!/usr/bin/env python3
"""Evaluate an existing D405 stationary RGBD capture without hardware access."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.d405_stationary_rgbd_capture import (
    evaluate_d405_stationary_rgbd_capture,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("capture_dir", type=Path)
    parser.add_argument("readiness_dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    receipt = evaluate_d405_stationary_rgbd_capture(
        args.capture_dir, args.readiness_dir, output_path=args.output
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["verdict"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
