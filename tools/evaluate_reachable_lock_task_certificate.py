#!/usr/bin/env python3
"""Run the frozen RP04D reachable-lock static task screen."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.reachable_lock_task_certificate import enumerate_and_freeze


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = enumerate_and_freeze(
        args.contract.resolve(), args.output.resolve()
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
