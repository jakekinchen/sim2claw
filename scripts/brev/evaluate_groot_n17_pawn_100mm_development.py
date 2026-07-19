#!/usr/bin/env python3
"""Apply the frozen independent pawn evaluator to one learned rollout."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.pawn_policy_evaluator import evaluate_policy_rollout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rollout", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("evaluation receipt must not already exist")
    result = evaluate_policy_rollout(args.rollout, output_path=args.output)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
