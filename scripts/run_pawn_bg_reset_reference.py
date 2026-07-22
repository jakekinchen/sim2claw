#!/usr/bin/env python3
"""Run the action-frozen B--G reset/reference audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.paths import REPO_ROOT
from sim2claw.pawn_bg_reset_reference import run_reset_reference_audit


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO_ROOT / "outputs" / "pawn_bg_reset_reference_v1",
    )
    args = parser.parse_args()
    receipt = run_reset_reference_audit(
        source_repository_root=REPO_ROOT, output_root=args.output_root
    )
    print(json.dumps({
        "initial_command_minus_measured": receipt["initial_command_minus_measured"],
        "variants": receipt["all_train_variants"],
        "cross_validation": receipt["grouped_cross_validation"],
        "decision": receipt["decision"],
    }, indent=2, sort_keys=True))
    print(args.output_root.resolve() / "reset_reference_receipt.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
