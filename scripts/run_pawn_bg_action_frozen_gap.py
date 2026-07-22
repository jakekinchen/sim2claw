#!/usr/bin/env python3
"""Run geometry-only gap fitting with immutable recorded and policy actions."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sim2claw.paths import REPO_ROOT
from sim2claw.pawn_bg_action_frozen_gap import (
    run_action_frozen_confirmation,
    run_action_frozen_gap_fit,
    run_frozen_policy_action_replay,
)


POLICY_ROOT_ENV = "SIM2CLAW_GROOT_EVAL_ROOT"


def _default_policy_root() -> Path | None:
    value = os.environ.get(POLICY_ROOT_ENV)
    return Path(value).expanduser() if value else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO_ROOT / "runs" / "pawn-bg-action-frozen-gap-v1",
    )
    parser.add_argument(
        "--policy-root",
        type=Path,
        default=_default_policy_root(),
        help=f"retained GR00T evaluation root (or set {POLICY_ROOT_ENV})",
    )
    parser.add_argument(
        "--skip-policy-replay",
        action="store_true",
        help="materialize only the recorded-action fit and confirmation",
    )
    args = parser.parse_args()
    if not args.skip_policy_replay and args.policy_root is None:
        parser.error(
            f"--policy-root is required unless {POLICY_ROOT_ENV} is set "
            "(or pass --skip-policy-replay)"
        )
    source_root = args.source_root.resolve()
    output_root = args.output_root.resolve()
    fit = run_action_frozen_gap_fit(
        source_repository_root=source_root,
        output_root=output_root,
    )
    confirmation = run_action_frozen_confirmation(
        source_repository_root=source_root,
        fit_receipt_path=output_root / "train_fit.json",
        output_root=output_root,
    )
    policy = None
    if not args.skip_policy_replay:
        assert args.policy_root is not None
        policy = run_frozen_policy_action_replay(
            fit_receipt_path=output_root / "train_fit.json",
            policy_root=args.policy_root.resolve(),
            output_root=output_root,
        )
    summary = {
        "selected_simulator_candidate": fit["selected_simulator_candidate"],
        "stage_d_train_event_rms_m": fit["stage_d"]["event_metrics"][
            "event_rms_distance_m"
        ],
        "geometry_train_event_rms_m": fit["geometry_only"]["event_metrics"][
            "event_rms_distance_m"
        ],
        "train_relative_reduction": fit["train_acceptance"][
            "event_rms_relative_reduction"
        ],
        "train_actions_byte_identical": fit["train_acceptance"][
            "byte_identical_action_gate"
        ],
        "confirmation_relative_reduction": confirmation[
            "geometry_event_rms_relative_reduction"
        ],
        "confirmation_actions_byte_identical": confirmation[
            "all_actions_byte_identical"
        ],
        "policy_replay": (
            {
                "policy_invoked": policy["policy_invoked"],
                "all_actions_byte_identical": policy["all_actions_byte_identical"],
                "comparisons": policy["comparisons"],
            }
            if policy is not None
            else None
        ),
        "fit_receipt": str((output_root / "train_fit.json").resolve()),
        "confirmation_receipt": str((output_root / "confirmation.json").resolve()),
        "policy_replay_receipt": (
            str((output_root / "policy_action_replay.json").resolve())
            if policy is not None
            else None
        ),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
