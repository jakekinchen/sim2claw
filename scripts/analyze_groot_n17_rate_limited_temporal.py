#!/usr/bin/env python3
"""Gate one frozen rate-limited temporal executor on training consequences."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np


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
    parent = json.loads(args.parent_summary.read_text(encoding="utf-8"))
    parent_sha256 = sha256_file(args.parent_summary)
    if parent_sha256 != experiment["parent_temporal_summary_sha256"]:
        raise ValueError("parent temporal summary hash mismatch")
    if parent.get("held_out_may_open") is not False:
        raise ValueError("parent temporal summary unexpectedly opened held-out")
    if parent.get("experiment_sha256") != experiment[
        "parent_temporal_experiment_sha256"
    ]:
        raise ValueError("parent temporal summary references a different experiment")
    expected_parent = experiment["parent_result"]["best_arm"]
    parent_ranked = parent.get("ranked_arms", [])
    if not parent_ranked:
        raise ValueError("parent temporal summary has no ranked arm")
    for key in (
        "id",
        "execution_horizon",
        "temporal_action_aggregation",
        "temporal_decay",
        "maximum_overlapping_predictions",
    ):
        if parent_ranked[0].get(key) != expected_parent[key]:
            raise ValueError(f"parent temporal winner has wrong {key}")

    development = experiment["development"]
    arm_id = str(development["arm_id"])
    episodes = [int(value) for value in development["episode_indices"]]
    seeds = [int(value) for value in development["inference_seeds"]]
    expected_cells = {(episode, seed) for episode in episodes for seed in seeds}
    observed_cells: set[tuple[int, int]] = set()
    rows: list[dict[str, Any]] = []
    input_hashes: dict[str, str] = {}
    identities = experiment["frozen_identities"]
    fixed = experiment["fixed_model_inference"]
    temporal_expected = experiment["fixed_temporal_executor"]
    rate_expected = experiment["rate_limiter"]
    limits_expected = np.asarray(
        rate_expected["maximum_abs_delta_per_sample"], dtype=np.float32
    )
    renderer = experiment["renderer"]
    paths = sorted(args.rollout_root.glob("*/training-episode-*-seed-*/receipt.json"))
    if not paths:
        parser.error(f"no rate-limited receipts found under {args.rollout_root}")

    for path in paths:
        if path.parent.parent.name != arm_id:
            raise ValueError(f"receipt belongs to an undeclared rate arm: {path}")
        receipt = json.loads(path.read_text(encoding="utf-8"))
        cell = (int(receipt["episode_index"]), int(receipt["inference_seed"]))
        if cell not in expected_cells:
            raise ValueError(f"receipt is outside the frozen rate matrix: {path}")
        if cell in observed_cells:
            raise ValueError(f"duplicate rate-limited cell: {cell}")
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
        consensus = receipt.get("action_consensus", {})
        for key in (
            "proposal_count",
            "action_aggregation",
            "noise_scale",
            "num_inference_timesteps",
        ):
            if consensus.get(key) != fixed[key]:
                raise ValueError(f"receipt {path} has wrong fixed {key}")
        if int(receipt.get("execution_horizon", -1)) != int(
            temporal_expected["execution_horizon"]
        ):
            raise ValueError(f"receipt {path} has wrong execution horizon")
        temporal = receipt.get("temporal_action_aggregation", {})
        for key in (
            "temporal_action_aggregation",
            "temporal_decay",
            "maximum_overlapping_predictions",
        ):
            receipt_key = {
                "temporal_action_aggregation": "method",
                "temporal_decay": "exponential_decay",
                "maximum_overlapping_predictions": "maximum_overlapping_predictions",
            }[key]
            if temporal.get(receipt_key) != temporal_expected[key]:
                raise ValueError(f"receipt {path} has wrong temporal {receipt_key}")
        if temporal.get("model_chunks_only") is not True or temporal.get(
            "causal"
        ) is not True:
            raise ValueError(f"receipt {path} has noncausal temporal provenance")

        limiter = receipt.get("action_rate_limiter", {})
        if limiter.get("enabled") is not True:
            raise ValueError(f"receipt {path} disabled the rate limiter")
        if limiter.get("source") != rate_expected["source"]:
            raise ValueError(f"receipt {path} has wrong rate-limit source")
        observed_limits = np.asarray(
            limiter.get("maximum_abs_delta_per_sample", []), dtype=np.float32
        )
        if not np.array_equal(observed_limits, limits_expected):
            raise ValueError(f"receipt {path} has wrong rate limits")
        if limiter.get("initial_reference") != rate_expected["initial_reference"]:
            raise ValueError(f"receipt {path} has wrong initial rate reference")
        for key, expected in (
            ("model_targets_only", True),
            ("task_geometry_used", False),
            ("reward_used", False),
            ("assistance_frames", 0),
        ):
            if limiter.get(key) != expected:
                raise ValueError(f"receipt {path} has wrong rate provenance {key}")
        if int(limiter.get("rate_limited_sample_count", 0)) <= 0:
            raise ValueError(f"receipt {path} never activated the rate limiter")
        applied_max = np.asarray(
            limiter.get("maximum_applied_abs_delta", []), dtype=np.float32
        )
        if applied_max.shape != limits_expected.shape or np.any(
            applied_max > limits_expected + np.finfo(np.float32).eps
        ):
            raise ValueError(f"receipt {path} exceeded the frozen rate limits")

        adapter = receipt.get("action_execution_adapter", {})
        if adapter.get("method") != experiment["action_execution_adapter"]["method"]:
            raise ValueError(f"receipt {path} used the wrong action adapter")
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
        if not gates["assistance_frames"].get("passed") or not gates[
            "model_owned_actions"
        ].get("passed"):
            raise ValueError(f"receipt {path} fails the action provenance gates")
        rows.append(
            {
                "episode_index": cell[0],
                "inference_seed": cell[1],
                "receipt_sha256": sha256_file(path),
                "success": bool(receipt["verdict"]["success"]),
                "board_safety": bool(
                    gates["maximum_other_piece_displacement"]["passed"]
                ),
                "final_xy": bool(gates["final_xy_error"]["passed"]),
                "upright": bool(gates["final_upright_cosine"]["passed"]),
                "lift": bool(gates["minimum_piece_rise"]["passed"]),
                "maximum_piece_rise_m": float(receipt["maximum_piece_rise_m"]),
                "final_xy_error_m": float(gates["final_xy_error"]["measured"]),
                "final_upright_cosine": float(
                    gates["final_upright_cosine"]["measured"]
                ),
            }
        )
        input_hashes[str(path.resolve())] = sha256_file(path)

    missing = sorted(expected_cells - observed_cells)
    if missing:
        raise ValueError(f"rate-limited matrix is incomplete; missing cells: {missing}")
    counts = {
        "full_task_consequence_pass_count": sum(row["success"] for row in rows),
        "board_safety_pass_count": sum(row["board_safety"] for row in rows),
        "final_xy_pass_count": sum(row["final_xy"] for row in rows),
        "upright_pass_count": sum(row["upright"] for row in rows),
        "lift_pass_count": sum(row["lift"] for row in rows),
    }
    eligible = counts["full_task_consequence_pass_count"] >= 2
    arm_summary = {
        "id": arm_id,
        **fixed,
        **temporal_expected,
        "rate_limit_source": rate_expected["source"],
        "maximum_abs_delta_per_sample": rate_expected[
            "maximum_abs_delta_per_sample"
        ],
        "rollout_cells": len(rows),
        **counts,
        "eligible_for_configuration_freeze": eligible,
    }
    winning_configuration = None
    winning_configuration_sha256 = None
    if eligible:
        winning_configuration = {
            "schema_version": (
                "sim2claw.groot_n17_rate_limited_temporal_configuration.v1"
            ),
            "experiment_sha256": experiment_sha256,
            "checkpoint_manifest_sha256": identities[
                "nominal_checkpoint_aggregate_manifest_sha256"
            ],
            **fixed,
            **temporal_expected,
            "rate_limit_source": rate_expected["source"],
            "maximum_abs_delta_per_sample": rate_expected[
                "maximum_abs_delta_per_sample"
            ],
            "physics_action_adapter": experiment["action_execution_adapter"][
                "method"
            ],
            "development_render_cadence": renderer["development_cadence"],
            "sealed_promotion_render_cadence": renderer[
                "sealed_promotion_cadence"
            ],
            "assistance_frames": 0,
        }
        winning_configuration_sha256 = canonical_sha256(winning_configuration)
    representative = sorted(
        rows,
        key=lambda row: (
            -int(row["success"]),
            -int(row["final_xy"]),
            -int(row["upright"]),
            -int(row["lift"]),
            -int(row["board_safety"]),
            float(row["final_xy_error_m"]),
            -float(row["maximum_piece_rise_m"]),
        ),
    )[0]
    output = {
        "schema_version": "sim2claw.groot_n17_rate_limited_temporal_summary.v1",
        "experiment_sha256": experiment_sha256,
        "parent_temporal_summary_sha256": parent_sha256,
        "proof_class": "learned_policy_simulation_training_development",
        "promotion_authority": False,
        "arm": arm_summary,
        "representative_development_receipt": representative,
        "winning_configuration": winning_configuration,
        "winning_configuration_sha256": winning_configuration_sha256,
        "held_out_may_open": eligible,
        "input_receipt_sha256": input_hashes,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
