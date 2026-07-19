#!/usr/bin/env python3
"""Rank frozen training-only GR00T consensus probes without promotion authority."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--probe-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    experiment = json.loads(args.experiment.read_text(encoding="utf-8"))
    arm_contracts = {
        str(arm["id"]): arm
        for arm in experiment["row_zero_development_probe"]["candidate_arms"]
    }
    paths = sorted(args.probe_root.glob("*/training-episode-*-seed-*.json"))
    if not paths:
        parser.error(f"no probe JSON files found under {args.probe_root}")

    rows: dict[str, list[dict[str, float]]] = defaultdict(list)
    input_hashes: dict[str, str] = {}
    seen_cells: set[tuple[str, int, int]] = set()
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        arm_id = path.parent.name
        if arm_id not in arm_contracts:
            raise ValueError(f"probe has undeclared arm directory: {path}")
        if payload.get("split") != "training":
            raise ValueError(f"probe is not training-only: {path}")
        if not payload.get("repeatable"):
            raise ValueError(f"probe is not bitwise repeatable: {path}")
        observed = payload.get("action_consensus", {})
        expected = arm_contracts[arm_id]
        for key in (
            "proposal_count",
            "action_aggregation",
            "noise_scale",
            "num_inference_timesteps",
        ):
            if observed.get(key) != expected.get(key):
                raise ValueError(f"probe {path} has wrong {key}")
        cell = (
            arm_id,
            int(payload["episode_index"]),
            int(payload["inference_seed"]),
        )
        if cell in seen_cells:
            raise ValueError(f"duplicate probe cell: {cell}")
        seen_cells.add(cell)
        probe_metrics = []
        pairwise = []
        for probe in payload["probes"]:
            diagnostic = probe.get("training_expert_diagnostic")
            if diagnostic is None or diagnostic.get("promotion_authority") is not False:
                raise ValueError(f"probe lacks non-promoting expert diagnostic: {path}")
            probe_metrics.append(diagnostic)
            pairwise.append(
                float(probe["action_info"]["consensus"]["maximum_pairwise_l2"])
            )
        rows[arm_id].append(
            {
                "chunk_mae": float(
                    statistics.median(row["chunk_mae"] for row in probe_metrics)
                ),
                "first_action_mae": float(
                    statistics.median(
                        row["first_action_mae"] for row in probe_metrics
                    )
                ),
                "maximum_pairwise_l2": max(pairwise),
            }
        )
        input_hashes[str(path.resolve())] = sha256_file(path)

    expected_cells_per_arm = (
        len(experiment["row_zero_development_probe"]["episode_indices"])
        * len(experiment["row_zero_development_probe"]["inference_seeds"])
    )
    arm_summaries: list[dict[str, Any]] = []
    for arm_id, arm in arm_contracts.items():
        arm_rows = rows.get(arm_id, [])
        if len(arm_rows) != expected_cells_per_arm:
            raise ValueError(
                f"arm {arm_id} has {len(arm_rows)} cells; "
                f"expected {expected_cells_per_arm}"
            )
        arm_summaries.append(
            {
                "id": arm_id,
                **{
                    key: arm[key]
                    for key in (
                        "proposal_count",
                        "action_aggregation",
                        "noise_scale",
                        "num_inference_timesteps",
                    )
                },
                "probe_cells": len(arm_rows),
                "median_training_expert_chunk_mae": float(
                    statistics.median(row["chunk_mae"] for row in arm_rows)
                ),
                "median_training_expert_first_action_mae": float(
                    statistics.median(row["first_action_mae"] for row in arm_rows)
                ),
                "maximum_pairwise_proposal_l2": max(
                    row["maximum_pairwise_l2"] for row in arm_rows
                ),
            }
        )

    def ranking_key(row: dict[str, Any]) -> tuple[float, float, float, int]:
        return (
            float(row["median_training_expert_chunk_mae"]),
            float(row["median_training_expert_first_action_mae"]),
            float(row["maximum_pairwise_proposal_l2"]),
            int(row["proposal_count"]),
        )

    ranked = sorted(arm_summaries, key=ranking_key)
    maximum_nonbaseline = int(
        experiment["row_zero_development_probe"]["shortlist_rule"][
            "maximum_nonbaseline_arms"
        ]
    )
    shortlist = [
        row["id"]
        for row in ranked
        if not str(row["id"]).startswith("baseline-")
    ][:maximum_nonbaseline]
    result = {
        "schema_version": "sim2claw.groot_n17_consensus_probe_summary.v1",
        "proof_class": "learned_policy_simulation_diagnostic",
        "promotion_authority": False,
        "experiment_sha256": sha256_file(args.experiment),
        "expected_cells_per_arm": expected_cells_per_arm,
        "ranked_arms": ranked,
        "nonbaseline_shortlist": shortlist,
        "input_sha256": input_hashes,
    }
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
