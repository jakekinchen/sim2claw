#!/usr/bin/env python3
"""Run the action-frozen B--G lift/elbow servo-deadband ablation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.paths import REPO_ROOT
from sim2claw.pawn_bg_servo_deadband import run_servo_deadband_ablation


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO_ROOT / "outputs" / "pawn_bg_servo_deadband_v1",
    )
    args = parser.parse_args()
    receipt = run_servo_deadband_ablation(
        source_repository_root=REPO_ROOT, output_root=args.output_root
    )
    print(
        json.dumps(
            {
                "selected_deadband_degrees": receipt["selected_deadband_degrees"],
                "baseline": receipt["zero_deadband_train_metrics"],
                "selected": receipt["selected_train_metrics"],
                "cross_validation": receipt["grouped_cross_validation"],
                "acceptance": receipt["train_acceptance"],
                "consequences": {
                    name: value["summary"]
                    for name, value in receipt["action_frozen_consequence_replay"].items()
                },
            },
            indent=2,
            sort_keys=True,
        )
    )
    print(args.output_root.resolve() / "servo_deadband_receipt.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
