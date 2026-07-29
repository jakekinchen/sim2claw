#!/usr/bin/env python3
"""Fit the frozen RP04A elbow-only tracking challenger."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.coordinated_unloading_tracking_challenger import (
    fit_tracking_challenger,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = fit_tracking_challenger(
        args.contract.resolve(), args.output.resolve()
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
