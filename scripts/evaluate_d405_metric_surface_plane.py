#!/usr/bin/env python3
"""Evaluate a metric D405 surface plane from accepted offline artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.d405_metric_surface_plane import (
    evaluate_d405_metric_surface_plane,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("capture_dir", type=Path)
    parser.add_argument("--capture-receipt", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    receipt = evaluate_d405_metric_surface_plane(
        args.capture_dir,
        capture_receipt_path=args.capture_receipt,
        output_path=args.output,
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["verdict"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
