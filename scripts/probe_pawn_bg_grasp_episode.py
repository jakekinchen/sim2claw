#!/usr/bin/env python3
"""Run one action-frozen B--G grasp mechanism probe."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sim2claw.learning_factory_artifacts import atomic_write_json
from sim2claw.paths import REPO_ROOT
from sim2claw.pawn_bg_grasp_coordinate_descent import run_grasp_episode_probe


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("recording_id")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--parameters-json",
        type=Path,
        help="JSON object containing the simulator-only parameter composite",
    )
    source.add_argument(
        "--v1-profile",
        choices=("current_no_tip_baseline", "initial_high_prior", "frozen_composite"),
        help="reuse a parameter profile from the completed v1 campaign receipt",
    )
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="override/add a numeric or true/false simulator parameter",
    )
    parser.add_argument(
        "--piece-reset",
        action="append",
        default=[],
        metavar="FILE=X_M,Y_M",
        help=(
            "set a bounded per-episode pawn initial-state offset without "
            "changing the source action trace"
        ),
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--retention-trace",
        action="store_true",
        help=(
            "record source-frame contact geometry, simulated contact forces, "
            "gripper state, and contact-loss ordering"
        ),
    )
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()
    if args.parameters_json is not None:
        parameters = json.loads(args.parameters_json.read_text(encoding="utf-8"))
    else:
        v1_receipt = json.loads(
            (
                REPO_ROOT
                / "outputs"
                / "pawn_bg_grasp_coordinate_descent_v1"
                / "grasp_coordinate_descent_receipt.json"
            ).read_text(encoding="utf-8")
        )
        parameters = v1_receipt["full_evaluation"][args.v1_profile]["parameters"]
    if not isinstance(parameters, dict):
        raise ValueError("parameters JSON must be an object")
    parameters = dict(parameters)
    for assignment in args.set:
        if "=" not in assignment:
            raise ValueError(f"parameter override must be NAME=VALUE: {assignment}")
        name, raw_value = assignment.split("=", 1)
        normalized = raw_value.strip().lower()
        if normalized in {"true", "false"}:
            value: float | bool = normalized == "true"
        else:
            value = float(raw_value)
        parameters[name] = value
    for assignment in args.piece_reset:
        if "=" not in assignment:
            raise ValueError(
                f"piece reset must be FILE=X_M,Y_M: {assignment}"
            )
        file_name, raw_offset = assignment.split("=", 1)
        components = raw_offset.split(",")
        if len(components) != 2:
            raise ValueError(
                f"piece reset must have two coordinates: {assignment}"
            )
        reset_map = parameters.setdefault("episode_piece_reset_offsets_m", {})
        if not isinstance(reset_map, dict):
            raise ValueError("episode_piece_reset_offsets_m must be an object")
        episode_map = reset_map.setdefault(args.recording_id, {})
        if not isinstance(episode_map, dict):
            raise ValueError("episode piece reset entry must be an object")
        episode_map[file_name] = [float(components[0]), float(components[1])]
    receipt = run_grasp_episode_probe(
        source_repository_root=REPO_ROOT,
        recording_id=args.recording_id,
        parameters=parameters,
        retention_trace_enabled=args.retention_trace,
    )
    output = args.output or (
        REPO_ROOT
        / "outputs"
        / "pawn_bg_grasp_episode_probes"
        / f"{args.recording_id}__{receipt['parameter_digest'][:12]}.json"
    )
    atomic_write_json(output, receipt)
    episode = receipt["episode"]
    if args.compact:
        contacts = episode["wrong_piece_robot_contacts"]
        print(
            json.dumps(
                {
                    "output": str(output.resolve()),
                    "recording_id": args.recording_id,
                    "parameter_digest": receipt["parameter_digest"],
                    "action_byte_identical": episode["action_byte_identical"],
                    "task_consequence_success": episode[
                        "task_consequence_success"
                    ],
                    "piece_lifted": episode["piece_lifted"],
                    "lift_and_transport": episode["lift_and_transport"],
                    "whole_base_inside_destination": episode[
                        "whole_base_inside_destination"
                    ],
                    "final_target_distance_m": episode[
                        "final_target_distance_m"
                    ],
                    "maximum_piece_rise_m": episode["maximum_piece_rise_m"],
                    "maximum_other_piece_displacement_m": episode[
                        "maximum_other_piece_displacement_m"
                    ],
                    "wrong_contact_identities": sorted(
                        {
                            f"{row['robot_geom_name']}->{row['piece_name']}"
                            for row in contacts
                        }
                    ),
                    "original_gate_results": episode["original_gate_results"],
                    "trace_metrics": {
                        "overall_joint_rms_degrees": episode["trace_metrics"][
                            "overall_joint_rms_degrees"
                        ],
                        "ee_rms_m": episode["trace_metrics"]["ee_rms_m"],
                    },
                },
                sort_keys=True,
            )
        )
        return 0
    print(
        json.dumps(
            {
                "output": str(output.resolve()),
                "recording_id": args.recording_id,
                "action_byte_identical": episode["action_byte_identical"],
                "task_consequence_success": episode["task_consequence_success"],
                "original_gate_results": episode["original_gate_results"],
                "first_collateral_threshold_crossing": episode[
                    "first_collateral_threshold_crossing"
                ],
                "wrong_piece_robot_contacts": episode[
                    "wrong_piece_robot_contacts"
                ],
                "maximum_displacement_by_other_piece_m": episode[
                    "maximum_displacement_by_other_piece_m"
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
