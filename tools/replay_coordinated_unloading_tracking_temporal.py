#!/usr/bin/env python3
"""Replay the frozen V5 elbow tracking challenger."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.coordinated_unloading_tracking_temporal import (
    replay_tracking_challenger,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = replay_tracking_challenger(
        args.contract.resolve(), args.output.resolve()
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
