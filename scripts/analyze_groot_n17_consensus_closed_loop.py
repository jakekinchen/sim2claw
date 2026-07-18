#!/usr/bin/env python3
"""Select a frozen GR00T consensus arm from training closed-loop evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--probe-summary", type=Path, required=True)
    parser.add_argument("--rollout-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    experiment = json.loads(args.experiment.read_text(encoding="utf-8"))
    experiment_sha256 = sha256_file(args.experiment)
    probe_summary = json.loads(args.probe_summary.read_text(encoding="utf-8"))
    if probe_summary.get("promotion_authority") is not False:
        raise ValueError("probe summary unexpectedly has promotion authority")
    if probe_summary.get("experiment_sha256") != experiment_sha256:
        raise ValueError("probe summary references a different experiment")

    declared_arms = {
        str(arm["id"]): arm
        for arm in experiment["row_zero_development_probe"]["candidate_arms"]
    }
    shortlist = [str(value) for value in probe_summary["nonbaseline_shortlist"]]
    maximum = int(
        experiment["row_zero_development_probe"]["shortlist_rule"][
            "maximum_nonbaseline_arms"
        ]
    )
    if not shortlist or len(shortlist) > maximum:
        raise ValueError("probe shortlist violates the frozen size bound")
    if len(set(shortlist)) != len(shortlist):
        raise ValueError("probe shortlist contains duplicate arms")
    for arm_id in shortlist:
        if arm_id not in declared_arms or arm_id.startswith("baseline-"):
            raise ValueError(f"invalid nonbaseline shortlist arm: {arm_id}")

    development = experiment["closed_loop_development"]
    expected_episodes = [int(value) for value in development["episode_indices"]]
    expected_seeds = [int(value) for value in development["inference_seeds"]]
    expected_cells = {
        (arm_id, episode_index, inference_seed)
        for arm_id in shortlist
        for episode_index in expected_episodes
        for inference_seed in expected_seeds
    }
    identities = experiment["frozen_identities"]
    invariants = experiment["invariants"]
    renderer = experiment["renderer"]
    observed_cells: set[tuple[str, int, int]] = set()
    arm_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    input_hashes: dict[str, str] = {}
    paths = sorted(args.rollout_root.glob("*/training-episode-*-seed-*/receipt.json"))
    if not paths:
        parser.error(f"no closed-loop receipts found under {args.rollout_root}")

    for path in paths:
        arm_id = path.parent.parent.name
        if arm_id not in shortlist:
            raise ValueError(f"receipt belongs to a non-shortlisted arm: {path}")
        receipt = json.loads(path.read_text(encoding="utf-8"))
        cell = (
            arm_id,
            int(receipt["episode_index"]),
            int(receipt["inference_seed"]),
        )
        if cell not in expected_cells:
            raise ValueError(f"receipt is outside the frozen development matrix: {path}")
        if cell in observed_cells:
            raise ValueError(f"duplicate closed-loop cell: {cell}")
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
        arm = declared_arms[arm_id]
        observed_consensus = receipt.get("action_consensus", {})
        for key in (
            "proposal_count",
            "action_aggregation",
            "noise_scale",
            "num_inference_timesteps",
        ):
            if observed_consensus.get(key) != arm.get(key):
                raise ValueError(f"receipt {path} has wrong {key}")
        if int(receipt.get("execution_horizon", -1)) != int(
            invariants["execution_horizon"]
        ):
            raise ValueError(f"receipt {path} has wrong execution horizon")
        if receipt.get("all_actions_model_owned") is not True:
            raise ValueError(f"receipt {path} includes non-model actions")
        if int(receipt.get("assistance_frames", -1)) != 0:
            raise ValueError(f"receipt {path} includes assistance")
        observed_renderer = receipt.get("render_backend", {})
        if (
            observed_renderer.get("mujoco_gl") != renderer["mujoco_gl"]
            or observed_renderer.get("pyopengl_platform")
            != renderer["pyopengl_platform"]
        ):
            raise ValueError(f"receipt {path} used the wrong renderer")

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
        raise ValueError(f"closed-loop matrix is incomplete; missing cells: {missing}")

    summaries: list[dict[str, Any]] = []
    for arm_id in shortlist:
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
                "id": arm_id,
                **{
                    key: declared_arms[arm_id][key]
                    for key in (
                        "proposal_count",
                        "action_aggregation",
                        "noise_scale",
                        "num_inference_timesteps",
                    )
                },
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
            "schema_version": "sim2claw.groot_n17_consensus_configuration.v1",
            "experiment_sha256": experiment_sha256,
            "checkpoint_manifest_sha256": identities[
                "nominal_checkpoint_aggregate_manifest_sha256"
            ],
            "execution_horizon": invariants["execution_horizon"],
            **{
                key: winner[key]
                for key in (
                    "id",
                    "proposal_count",
                    "action_aggregation",
                    "noise_scale",
                    "num_inference_timesteps",
                )
            },
        }
        winning_configuration_sha256 = canonical_sha256(winning_configuration)

    result = {
        "schema_version": "sim2claw.groot_n17_consensus_closed_loop_summary.v1",
        "proof_class": "learned_policy_simulation_development",
        "promotion_authority": False,
        "experiment_sha256": experiment_sha256,
        "probe_summary_sha256": sha256_file(args.probe_summary),
        "ranked_arms": ranked,
        "held_out_may_open": winning_configuration is not None,
        "winning_configuration": winning_configuration,
        "winning_configuration_sha256": winning_configuration_sha256,
        "input_sha256": input_hashes,
    }
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
