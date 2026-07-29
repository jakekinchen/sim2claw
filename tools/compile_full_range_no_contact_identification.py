#!/usr/bin/env python3
"""Compile the frozen RP04C full-range no-contact route."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.full_range_no_contact_identification import (
    compile_identification_route,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = compile_identification_route(
        args.contract.resolve(), args.output.resolve()
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
