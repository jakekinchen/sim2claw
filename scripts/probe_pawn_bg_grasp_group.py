#!/usr/bin/env python3
"""Run an action-frozen retained-group grasp mechanism probe."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.learning_factory_artifacts import atomic_write_json
from sim2claw.paths import REPO_ROOT
from sim2claw.pawn_bg_grasp_coordinate_descent import run_grasp_group_probe


def _value(raw: str) -> float | bool:
    normalized = raw.strip().lower()
    if normalized in {"true", "false"}:
        return normalized == "true"
    return float(raw)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--role",
        choices=("sentinels", "campaign-held", "all"),
        default="sentinels",
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--v1-profile",
        choices=("current_no_tip_baseline", "initial_high_prior", "frozen_composite"),
    )
    source.add_argument(
        "--parameters-json",
        type=Path,
        help="JSON object containing the simulator-only parameter composite",
    )
    parser.add_argument("--set", action="append", default=[], metavar="NAME=VALUE")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    v1_path = (
        REPO_ROOT
        / "outputs"
        / "pawn_bg_grasp_coordinate_descent_v1"
        / "grasp_coordinate_descent_receipt.json"
    )
    v1 = json.loads(v1_path.read_text(encoding="utf-8"))
    if args.parameters_json is not None:
        parameters = json.loads(args.parameters_json.read_text(encoding="utf-8"))
        if not isinstance(parameters, dict):
            raise ValueError("parameters JSON must be an object")
        parameters = dict(parameters)
    else:
        profile = args.v1_profile or "current_no_tip_baseline"
        parameters = dict(v1["full_evaluation"][profile]["parameters"])
    for assignment in args.set:
        if "=" not in assignment:
            raise ValueError(f"parameter override must be NAME=VALUE: {assignment}")
        name, raw = assignment.split("=", 1)
        parameters[name] = _value(raw)

    roles = v1["episode_roles"]
    if args.role == "sentinels":
        recording_ids = roles["adaptive_sentinel_recording_ids"]
    elif args.role == "campaign-held":
        recording_ids = roles["campaign_held_evaluation_recording_ids"]
    else:
        recording_ids = sorted(
            roles["adaptive_sentinel_recording_ids"]
            + roles["campaign_held_evaluation_recording_ids"]
        )
    receipt = run_grasp_group_probe(
        source_repository_root=REPO_ROOT,
        recording_ids=recording_ids,
        parameters=parameters,
    )
    output = args.output or (
        REPO_ROOT
        / "outputs"
        / "pawn_bg_grasp_group_probes"
        / f"{args.role}__{receipt['parameter_digest'][:12]}.json"
    )
    atomic_write_json(output, receipt)
    print(
        json.dumps(
            {
                "output": str(output.resolve()),
                "role": args.role,
                "parameter_digest": receipt["parameter_digest"],
                "summary": receipt["summary"],
                "episodes": [
                    {
                        "recording_id": row["recording_id"],
                        "folder_label": row["folder_label"],
                        "piece_lifted": row["piece_lifted"],
                        "lift_and_transport": row["lift_and_transport"],
                        "strict_success": row["task_consequence_success"],
                        "maximum_piece_rise_m": row["maximum_piece_rise_m"],
                        "final_target_distance_m": row["final_target_distance_m"],
                        "maximum_other_piece_displacement_m": row[
                            "maximum_other_piece_displacement_m"
                        ],
                    }
                    for row in receipt["episodes"]
                ],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
