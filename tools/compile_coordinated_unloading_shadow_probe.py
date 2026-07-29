#!/usr/bin/env python3
"""Compile the prospective coordinated-unloading shadow probe."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.coordinated_unloading_shadow_probe import compile_probe


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = compile_probe(args.contract.resolve(), args.output.resolve())
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

