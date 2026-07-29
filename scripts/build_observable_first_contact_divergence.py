#!/usr/bin/env python3
"""Build the frozen physical/simulator first-divergence receipt."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.observable_first_divergence import (
    CONTRACT_PATH,
    OUTPUT_PATH,
    build_divergence_receipt,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()
    receipt = build_divergence_receipt(args.contract, args.output)
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if receipt["accepted"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
