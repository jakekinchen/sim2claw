#!/usr/bin/env python3
"""Run the frozen action-frozen B--G fidelity advancement closeout."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.paths import REPO_ROOT
from sim2claw.pawn_bg_fidelity_advancement import run_fidelity_advancement_closeout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO_ROOT / "outputs" / "pawn_bg_fidelity_advancement_v1",
    )
    args = parser.parse_args()
    receipt = run_fidelity_advancement_closeout(
        source_repository_root=REPO_ROOT, output_root=args.output_root
    )
    print(
        json.dumps(
            {
                "pooled_cross_validated_metrics": receipt["pooled_cross_validated_metrics"],
                "episode_bootstrap": receipt["episode_bootstrap"],
                "advancement_gates": receipt["advancement_gates"],
                "verified_significant_action_frozen_rms_advancement": receipt[
                    "verified_significant_action_frozen_rms_advancement"
                ],
                "target_piece_consequence_comparison": receipt[
                    "target_piece_consequence_comparison"
                ],
                "goal_loop_stop_decision": receipt["goal_loop_stop_decision"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    print(args.output_root.resolve() / "advancement_receipt.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
