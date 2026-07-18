#!/usr/bin/env python3
"""Select a frozen temporal-overlap arm from training consequence evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--parent-summary", type=Path, required=True)
    parser.add_argument("--rollout-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    experiment = json.loads(args.experiment.read_text(encoding="utf-8"))
    experiment_sha256 = sha256_file(args.experiment)
    parent_summary = json.loads(args.parent_summary.read_text(encoding="utf-8"))
    parent_summary_sha256 = sha256_file(args.parent_summary)
    if parent_summary_sha256 != experiment["parent_waypoint_summary_sha256"]:
        raise ValueError("parent waypoint summary hash mismatch")
    if parent_summary.get("held_out_may_open") is not False:
        raise ValueError("parent waypoint summary unexpectedly opened held-out")
    if parent_summary.get("experiment_sha256") != experiment[
        "parent_waypoint_experiment_sha256"
    ]:
        raise ValueError("parent waypoint summary references a different experiment")

    development = experiment["development"]
    arms = {str(arm["id"]): arm for arm in development["candidate_arms"]}
    if not arms or len(arms) != len(development["candidate_arms"]):
        raise ValueError("temporal candidate arms must be unique and non-empty")
    if len(arms) > int(development["maximum_candidate_arms"]):
        raise ValueError("temporal candidate set violates the frozen size bound")
    episodes = [int(value) for value in development["episode_indices"]]
    seeds = [int(value) for value in development["inference_seeds"]]
    expected_cells = {
        (arm_id, episode, seed)
        for arm_id in arms
        for episode in episodes
        for seed in seeds
    }
    observed_cells: set[tuple[str, int, int]] = set()
    arm_rows: dict[str, list[dict[str, bool]]] = defaultdict(list)
    input_hashes: dict[str, str] = {}
    identities = experiment["frozen_identities"]
    fixed = experiment["fixed_model_inference"]
    renderer = experiment["renderer"]
    adapter_method = experiment["action_execution_adapter"]["method"]
    paths = sorted(args.rollout_root.glob("*/training-episode-*-seed-*/receipt.json"))
    if not paths:
        parser.error(f"no temporal receipts found under {args.rollout_root}")

    for path in paths:
        arm_id = path.parent.parent.name
        if arm_id not in arms:
            raise ValueError(f"receipt belongs to an undeclared temporal arm: {path}")
        receipt = json.loads(path.read_text(encoding="utf-8"))
        cell = (
            arm_id,
            int(receipt["episode_index"]),
            int(receipt["inference_seed"]),
        )
        if cell not in expected_cells:
            raise ValueError(f"receipt is outside the frozen temporal matrix: {path}")
        if cell in observed_cells:
            raise ValueError(f"duplicate temporal cell: {cell}")
        observed_cells.add(cell)
        if receipt.get("split") != "training":
            raise ValueError(f"receipt is not training-only: {path}")
        expected_identity = {
            "checkpoint_id": identities["nominal_checkpoint_id"],
            "checkpoint_manifest_sha256": identities[
                "nominal_checkpoint_aggregate_manifest_sha256"
            ],
            "groot_source_commit": identities["nvidia_source_commit"],
            "task_contract_sha256": identities[
                "base_task_contract_canonical_sha256"
            ],
        }
        for key, expected in expected_identity.items():
            if receipt.get(key) != expected:
                raise ValueError(f"receipt {path} has wrong {key}")
        observed_consensus = receipt.get("action_consensus", {})
        for key in (
            "proposal_count",
            "action_aggregation",
            "noise_scale",
            "num_inference_timesteps",
        ):
            if observed_consensus.get(key) != fixed.get(key):
                raise ValueError(f"receipt {path} has wrong fixed {key}")

        arm = arms[arm_id]
        if int(receipt.get("execution_horizon", -1)) != int(
            arm["execution_horizon"]
        ):
            raise ValueError(f"receipt {path} has wrong execution horizon")
        temporal = receipt.get("temporal_action_aggregation", {})
        temporal_expected = {
            "method": arm["temporal_action_aggregation"],
            "exponential_decay": arm["temporal_decay"],
            "maximum_overlapping_predictions": arm[
                "maximum_overlapping_predictions"
            ],
            "model_chunks_only": True,
            "causal": True,
            "assistance_frames": 0,
        }
        for key, expected in temporal_expected.items():
            if temporal.get(key) != expected:
                raise ValueError(f"receipt {path} has wrong temporal {key}")
        adapter = receipt.get("action_execution_adapter", {})
        if adapter.get("method") != adapter_method:
            raise ValueError(f"receipt {path} used the wrong action adapter")
        if adapter.get("model_waypoints_only") is not True:
            raise ValueError(f"receipt {path} has non-model waypoint provenance")
        cadence = receipt.get("render_cadence", {})
        if cadence.get("method") != renderer["development_cadence"]:
            raise ValueError(f"receipt {path} used the wrong render cadence")
        if cadence.get("policy_observation_frames_omitted") is not False:
            raise ValueError(f"receipt {path} omitted a policy observation frame")
        backend = receipt.get("render_backend", {})
        if (
            backend.get("mujoco_gl") != renderer["mujoco_gl"]
            or backend.get("pyopengl_platform") != renderer["pyopengl_platform"]
        ):
            raise ValueError(f"receipt {path} used the wrong renderer")
        if receipt.get("all_actions_model_owned") is not True:
            raise ValueError(f"receipt {path} includes non-model actions")
        if int(receipt.get("assistance_frames", -1)) != 0:
            raise ValueError(f"receipt {path} includes assistance")

        gates = receipt.get("verdict", {}).get("gates", {})
        required_gates = {
            "assistance_frames",
            "model_owned_actions",
            "maximum_other_piece_displacement",
            "final_xy_error",
            "final_upright_cosine",
            "minimum_piece_rise",
        }
        if not required_gates.issubset(gates):
            raise ValueError(f"receipt {path} lacks unchanged consequence gates")
        if not gates["assistance_frames"].get("passed"):
            raise ValueError(f"receipt {path} fails the zero-assistance gate")
        if not gates["model_owned_actions"].get("passed"):
            raise ValueError(f"receipt {path} fails the model-owned-action gate")
        arm_rows[arm_id].append(
            {
                "success": bool(receipt["verdict"]["success"]),
                "board_safety": bool(
                    gates["maximum_other_piece_displacement"]["passed"]
                ),
                "final_xy": bool(gates["final_xy_error"]["passed"]),
                "upright": bool(gates["final_upright_cosine"]["passed"]),
                "lift": bool(gates["minimum_piece_rise"]["passed"]),
            }
        )
        input_hashes[str(path.resolve())] = sha256_file(path)

    missing = sorted(expected_cells - observed_cells)
    if missing:
        raise ValueError(f"temporal matrix is incomplete; missing cells: {missing}")

    summaries: list[dict[str, Any]] = []
    for arm_id, arm in arms.items():
        rows = arm_rows[arm_id]
        counts = {
            "full_task_consequence_pass_count": sum(row["success"] for row in rows),
            "board_safety_pass_count": sum(row["board_safety"] for row in rows),
            "final_xy_pass_count": sum(row["final_xy"] for row in rows),
            "upright_pass_count": sum(row["upright"] for row in rows),
            "lift_pass_count": sum(row["lift"] for row in rows),
        }
        summaries.append(
            {
                **arm,
                "rollout_cells": len(rows),
                **counts,
                "eligible_for_configuration_freeze": (
                    counts["full_task_consequence_pass_count"] >= 2
                ),
            }
        )
    selection_order = [str(value) for value in development["selection_order"]]
    ranked = sorted(
        summaries,
        key=lambda row: tuple(-int(row[key]) for key in selection_order)
        + (str(row["id"]),),
    )
    eligible = [row for row in ranked if row["eligible_for_configuration_freeze"]]
    winning_configuration = None
    winning_configuration_sha256 = None
    if eligible:
        winner = eligible[0]
        winning_configuration = {
            "schema_version": "sim2claw.groot_n17_temporal_overlap_configuration.v1",
            "experiment_sha256": experiment_sha256,
            "checkpoint_manifest_sha256": identities[
                "nominal_checkpoint_aggregate_manifest_sha256"
            ],
            **fixed,
            **{
                key: winner[key]
                for key in (
                    "id",
                    "execution_horizon",
                    "temporal_action_aggregation",
                    "temporal_decay",
                )
            },
            "physics_action_adapter": adapter_method,
            "development_render_cadence": renderer["development_cadence"],
            "sealed_promotion_render_cadence": renderer[
                "sealed_promotion_cadence"
            ],
            "assistance_frames": 0,
        }
        winning_configuration_sha256 = canonical_sha256(winning_configuration)

    output = {
        "schema_version": "sim2claw.groot_n17_temporal_overlap_summary.v1",
        "experiment_sha256": experiment_sha256,
        "parent_waypoint_summary_sha256": parent_summary_sha256,
        "proof_class": "learned_policy_simulation_training_development",
        "promotion_authority": False,
        "ranked_arms": ranked,
        "winning_configuration": winning_configuration,
        "winning_configuration_sha256": winning_configuration_sha256,
        "held_out_may_open": winning_configuration is not None,
        "input_receipt_sha256": input_hashes,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
