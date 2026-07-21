#!/usr/bin/env python3
"""Run the action-frozen B--G servo load-bias continuation campaign."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.paths import REPO_ROOT
from sim2claw.pawn_bg_servo_load_bias import run_servo_load_bias_ablation


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO_ROOT / "outputs" / "pawn_bg_servo_load_bias_v1",
    )
    args = parser.parse_args()
    receipt = run_servo_load_bias_ablation(
        source_repository_root=REPO_ROOT, output_root=args.output_root
    )
    print(
        json.dumps(
            {
                "selected_candidate": receipt["selected_candidate"],
                "baseline": receipt["baseline"],
                "selected": receipt["selected_train_metrics"],
                "cross_validation": receipt["grouped_cross_validation"],
                "advancement": receipt["advancement_gates"],
                "consequences": {
                    name: value["summary"]
                    for name, value in receipt["action_frozen_consequence_replay"].items()
                },
                "confirmation": receipt["already_opened_confirmation"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    print(args.output_root.resolve() / "servo_load_bias_receipt.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
