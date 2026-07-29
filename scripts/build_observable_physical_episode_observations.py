#!/usr/bin/env python3
"""Compile the frozen physical jaw/pawn/contact observation artifact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.observable_physical_episode import (
    OBSERVATION_CONTRACT_PATH,
    OBSERVATION_OUTPUT_PATH,
    build_observation_receipt,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=OBSERVATION_CONTRACT_PATH)
    parser.add_argument("--output", type=Path, default=OBSERVATION_OUTPUT_PATH)
    args = parser.parse_args()
    receipt = build_observation_receipt(args.contract, args.output)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["accepted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
