#!/usr/bin/env python3
"""Write an offline, nonmetric D405 board-grid visibility receipt."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.d405_board_grid_visibility import diagnose_board_grid_visibility


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    receipt = diagnose_board_grid_visibility(args.input, output_path=args.output)
    print(json.dumps(receipt["verdict"], indent=2, sort_keys=True))
    return 0 if receipt["verdict"]["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
