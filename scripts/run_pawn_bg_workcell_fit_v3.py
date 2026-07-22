#!/usr/bin/env python3
"""Run Stage-F board-pitch fitting and already-open confirmation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.paths import REPO_ROOT
from sim2claw.pawn_bg_workcell_fit_v3 import (
    run_workcell_fit_v3,
    run_workcell_v3_confirmation,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO_ROOT / "runs" / "pawn-bg-workcell-fit-v3",
    )
    args = parser.parse_args()
    fit_path = args.output_root / "train_fit.json"
    confirmation_path = args.output_root / "confirmation.json"
    fit = run_workcell_fit_v3(
        source_repository_root=args.source_root.resolve(), output_path=fit_path
    )
    confirmation = run_workcell_v3_confirmation(
        source_repository_root=args.source_root.resolve(),
        receipt_path=fit_path,
        output_path=confirmation_path,
    )
    print(
        json.dumps(
            {
                "selected_candidate": fit["selected_candidate"],
                "kinematic_error_candidate": fit["kinematic_error_candidate"],
                "physics_replay_candidate": fit["physics_replay_candidate"],
                "playing_side_m": fit["stage_f_board_pitch"]["parameters"]["board_side_m"],
                "square_side_m": fit["stage_f_board_pitch"]["parameters"]["square_side_m"],
                "stage_d_train_event_rms_m": fit["stage_d_lift"]["kinematic"]["event_rms_distance_m"],
                "stage_f_train_event_rms_m": fit["stage_f_board_pitch"]["kinematic"]["event_rms_distance_m"],
                "stage_f_train_relative_reduction": fit["train_acceptance"]["gates"]["event_rms_relative_reduction"],
                "stage_d_confirmation_event_rms_m": confirmation["comparisons"]["stage_d_lift"]["kinematic"]["event_rms_distance_m"],
                "stage_f_confirmation_event_rms_m": confirmation["comparisons"]["stage_f_board_pitch"]["kinematic"]["event_rms_distance_m"],
                "stage_f_confirmation_relative_reduction": confirmation["stage_f_event_rms_reduction_from_stage_d"],
                "fit_receipt": str(fit_path.resolve()),
                "confirmation_receipt": str(confirmation_path.resolve()),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
