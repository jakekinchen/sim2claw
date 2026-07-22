#!/usr/bin/env python3
"""Compile the retired-workcell SAIL retrospective case."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.sail.retrospective_case import compile_case


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/sail/retrospective_case_v1.json"))
    parser.add_argument("--output-root", type=Path, default=Path("outputs/sail/retired-workcell-case-v1"))
    args = parser.parse_args()
    print(json.dumps(compile_case(args.config, output_root=args.output_root), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
