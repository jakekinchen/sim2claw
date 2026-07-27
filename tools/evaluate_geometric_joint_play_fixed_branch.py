#!/usr/bin/env python3
"""Select a fixed wrist play branch on three opened contact-free traces."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from sim2claw.actuator_external_validation import _workcell_candidate
from sim2claw.geometric_joint_play import replay_joint_play
from sim2claw.geometric_joint_play_fixed_branch import (
    replay_joint_play_fixed_branch,
)
from sim2claw.learning_factory_artifacts import (
    atomic_write_json,
    canonical_digest,
    sha256_file,
)
from sim2claw.paths import REPO_ROOT
from sim2claw.pawn_bg_servo_load_bias import load_servo_load_bias_contract
from sim2claw.pawn_bg_timing_ablation import (
    _episode_metrics,
    _mapped_episode,
    _strip_arrays,
)
from tools.evaluate_geometric_micro_actuator_response import _stage_payload
from tools.validate_geometric_joint_play import _bound_path, _load_json


CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "geometric_joint_play_fixed_branch_retrospective_v1.json"
)
SCHEMA = "sim2claw.geometric_joint_play_fixed_branch_retrospective.v1"
RECEIPT_SCHEMA = (
    "sim2claw.geometric_joint_play_fixed_branch_retrospective_receipt.v1"
)


class GeometricJointPlayFixedBranchEvaluationError(RuntimeError):
    """The fixed-branch retrospective evidence changed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GeometricJointPlayFixedBranchEvaluationError(message)


def _metric_triplet(metrics: Mapping[str, Any]) -> tuple[float, float, float]:
    return (
        float(metrics["per_joint_rms_degrees"]["wrist_flex"]),
        float(metrics["overall_joint_rms_degrees"]),
        float(metrics["ee_rms_m"]),
    )


def evaluate(
    *,
    contract_path: Path = CONTRACT_PATH,
    output_path: Path,
) -> dict[str, Any]:
    contract_path = contract_path.resolve()
    contract = _load_json(contract_path)
    _require(contract.get("schema_version") == SCHEMA, "contract schema changed")
    _require(
        contract.get("status")
        == "retrospective_selection_on_three_opened_contact_free_traces",
        "evaluation status changed",
    )
    _require(
        not any((contract.get("authority") or {}).values()),
        "evaluation authority widened",
    )
    _require(
        contract.get("proof_boundary")
        == {
            "all_three_traces_opened_before_selection": True,
            "selection_is_retrospective": True,
            "fresh_opposite_load_configuration_falsifier_required": True,
            "passing_retrospective_result_may_not_promote_parameters": True,
            "passing_retrospective_result_may_not_admit_pawn_contact": True,
        },
        "proof boundary changed",
    )

    sources = contract["sources"]
    _bound_path(sources["implementation"])
    frozen_path = _bound_path(sources["frozen_parameters"])
    frozen = _load_json(frozen_path)
    _require(
        frozen.get("frozen_parent") == contract["frozen_parent"],
        "frozen parent parameters changed",
    )
    reverse_fit_path = _bound_path(frozen["sources"]["parent_fit_contract"])
    reverse_fit = _load_json(reverse_fit_path)
    original_fit_path = _bound_path(
        reverse_fit["sources"]["parent_fit_contract"]
    )
    original_fit = _load_json(original_fit_path)
    selection_path = _bound_path(
        original_fit["sources"]["selection_receipt"]
    )
    selection = _load_json(selection_path)
    mechanism_path = _bound_path(
        original_fit["sources"]["mechanism_contract"]
    )
    mechanism = load_servo_load_bias_contract(mechanism_path)
    workcell = _workcell_candidate(selection)

    stages: list[dict[str, Any]] = []
    stage_specs = sources["stages"]
    _require(
        len(stage_specs) == 3
        and [int(stage["trace_index"]) for stage in stage_specs] == [1, 2, 3],
        "evaluation requires the frozen three traces",
    )
    for stage_spec in stage_specs:
        packet_path = _bound_path(stage_spec["packet"])
        packet = _load_json(packet_path)
        _, loaded = _stage_payload(stage_spec, packet)
        stages.append(
            {
                "trace_index": int(stage_spec["trace_index"]),
                "mapped": _mapped_episode(loaded["payload"], workcell),
                "source": loaded["source"],
            }
        )

    parent = contract["frozen_parent"]
    kwargs = {
        "settle_steps": int(
            mechanism["candidate_grid"]["initial_settle_steps"]
        ),
        "delay_seconds": float(parent["application_delay_seconds"]),
        "half_width_degrees": parent[
            "selected_expanded_half_width_degrees"
        ],
        "load_sign_zero_threshold_nm": float(
            parent["load_sign_zero_threshold_nm"]
        ),
    }
    candidates: dict[str, Any] = {}
    for candidate_id, fixed_sign in contract["candidates"].items():
        per_trace: list[dict[str, Any]] = []
        for stage in stages:
            if fixed_sign is None:
                states, schedule = replay_joint_play(
                    stage["mapped"], workcell, **kwargs
                )
            else:
                states, schedule = replay_joint_play_fixed_branch(
                    stage["mapped"],
                    workcell,
                    fixed_load_sign=fixed_sign,
                    **kwargs,
                )
            metrics = _strip_arrays(
                _episode_metrics(
                    stage["mapped"], states, workcell, mechanism
                )
            )
            per_trace.append(
                {
                    "trace_index": stage["trace_index"],
                    "source": stage["source"],
                    "schedule_sha256": schedule["sha256"],
                    "metrics": metrics,
                }
            )
        candidates[candidate_id] = {
            "fixed_load_sign": fixed_sign,
            "per_trace": per_trace,
            "equal_trace_mean_overall_joint_rms_degrees": float(
                np.mean(
                    [
                        trace["metrics"]["overall_joint_rms_degrees"]
                        for trace in per_trace
                    ]
                )
            ),
        }

    parent_rows = candidates["dynamic_load_sign_parent"]["per_trace"]
    eligible: list[str] = []
    dominance: dict[str, list[bool]] = {}
    for candidate_id, candidate in candidates.items():
        if candidate_id == "dynamic_load_sign_parent":
            continue
        passes = [
            all(
                selected < baseline
                for selected, baseline in zip(
                    _metric_triplet(selected_row["metrics"]),
                    _metric_triplet(parent_row["metrics"]),
                    strict=True,
                )
            )
            for selected_row, parent_row in zip(
                candidate["per_trace"], parent_rows, strict=True
            )
        ]
        dominance[candidate_id] = passes
        if all(passes):
            eligible.append(candidate_id)
    selected_id = (
        min(
            eligible,
            key=lambda candidate_id: (
                candidates[candidate_id][
                    "equal_trace_mean_overall_joint_rms_degrees"
                ],
                candidate_id,
            ),
        )
        if eligible
        else "dynamic_load_sign_parent"
    )
    selected = candidates[selected_id]
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "evaluation_id": contract["evaluation_id"],
        "proof_class": contract["proof_class"],
        "contract_path": str(contract_path),
        "contract_sha256": sha256_file(contract_path),
        "implementation_path": str(Path(__file__).resolve()),
        "implementation_sha256": sha256_file(Path(__file__).resolve()),
        "candidate_count": len(candidates),
        "candidates": candidates,
        "per_trace_dominance_over_parent": dominance,
        "eligible_candidate_ids": eligible,
        "selected_candidate_id": selected_id,
        "selected_fixed_load_sign": selected["fixed_load_sign"],
        "selection_rule": contract["selection_rule"],
        "source_actions_modified": False,
        "continuous_parameter_fitting_performed": False,
        "selection_is_retrospective": True,
        "parameters_promoted": False,
        "fresh_opposite_load_configuration_falsifier_required": True,
        "pawn_contact_admitted": False,
        "authority": contract["authority"],
    }
    receipt["receipt_digest"] = canonical_digest(receipt)
    atomic_write_json(output_path.resolve(), receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            evaluate(contract_path=args.contract, output_path=args.output),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
