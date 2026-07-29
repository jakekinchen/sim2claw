#!/usr/bin/env python3
"""Compile the frozen static-geometry reconciliation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.static_geometry_reconciliation import (
    CONTRACT_PATH,
    OUTPUT_PATH,
    build_geometry_receipt,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    arguments = parser.parse_args()
    receipt = build_geometry_receipt(arguments.contract, arguments.output)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
