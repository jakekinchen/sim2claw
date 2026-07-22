#!/usr/bin/env python3
"""Run deterministic corrective-repair controls without model or hardware calls."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.corrective_benchmark import run_all_controls
from sim2claw.learning_factory_artifacts import atomic_write_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--seed", type=int, default=20260720)
    args = parser.parse_args()
    result = run_all_controls(args.work_root, seed=args.seed)
    if args.output is not None:
        atomic_write_json(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
