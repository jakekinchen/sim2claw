#!/usr/bin/env python3
"""Compile the retained pawn trace/policy concordance diagnostic."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sim2claw.paths import REPO_ROOT
from sim2claw.policy_trace_concordance import compile_policy_trace_concordance


POLICY_ROOT_ENV = "SIM2CLAW_GROOT_EVAL_ROOT"


def _default_policy_root() -> Path | None:
    value = os.environ.get(POLICY_ROOT_ENV)
    return Path(value).expanduser() if value else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fit-root",
        type=Path,
        default=REPO_ROOT / "runs" / "pawn-metric-policy-concordance-v1",
    )
    parser.add_argument(
        "--policy-root",
        type=Path,
        default=_default_policy_root(),
        help=f"retained GR00T evaluation root (or set {POLICY_ROOT_ENV})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT
        / "runs"
        / "pawn-metric-policy-concordance-v1"
        / "concordance_report.json",
    )
    args = parser.parse_args()
    if args.policy_root is None:
        parser.error(f"--policy-root is required unless {POLICY_ROOT_ENV} is set")
    report = compile_policy_trace_concordance(
        train_fit_path=args.fit_root / "workcell_fit_train.json",
        held_out_fit_path=args.fit_root / "workcell_fit_held_out.json",
        baseline_policy_report_path=args.policy_root
        / "pawn-centering-checkpoint5000-full-v1"
        / "report.json",
        aligned_policy_report_path=args.policy_root
        / "pawn-centering-checkpoint5000-stage-d-aligned-smoke-v1"
        / "report.json",
        output_path=args.output,
    )
    print(
        json.dumps(
            {
                "output": str(args.output.resolve()),
                "verdict": report["concordance"]["verdict"],
                "train_event_rms_reduction": report["trace_fit"]["train"]["relative_reduction"],
                "held_out_event_rms_reduction": report["trace_fit"]["held_out"]["relative_reduction"],
                "train_contact_delta": report["source_replay_consequences"]["train"]["delta"]["selected_piece_contact_delta"],
                "held_out_contact_delta": report["source_replay_consequences"]["held_out"]["delta"]["selected_piece_contact_delta"],
                "paired_policy_collateral_reduction_fraction": report["paired_simulator_policy_probe"]["delta"]["maximum_other_piece_displacement_reduction_fraction"],
                "task_success_improved": report["concordance"]["lift_or_task_success_improved"],
                "report_sha256": report["report_sha256"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
