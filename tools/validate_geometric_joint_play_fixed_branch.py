#!/usr/bin/env python3
"""Evaluate a fixed wrist play branch on two fresh tricam heldouts."""

from __future__ import annotations

import argparse
import hashlib
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
from sim2claw.wrist_view_reposition import _decode_stage
from tools.evaluate_geometric_micro_actuator_response import _stage_payload
from tools.validate_geometric_joint_play import (
    _bound_path,
    _load_json,
    _relative_improvement,
    _repo_path,
    _tricam_gates,
)


CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "geometric_joint_play_fixed_branch_holdout_v2.json"
)
SCHEMA = "sim2claw.geometric_joint_play_fixed_branch_holdout.v2"
RECEIPT_SCHEMA = (
    "sim2claw.geometric_joint_play_fixed_branch_holdout_receipt.v2"
)


class GeometricJointPlayFixedBranchHoldoutError(RuntimeError):
    """The fixed branch, heldouts, evaluator, or authority boundary changed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GeometricJointPlayFixedBranchHoldoutError(message)


def _verify_digest(
    receipt: Mapping[str, Any],
    expected_digest: str,
    *,
    label: str,
) -> None:
    payload = dict(receipt)
    observed = payload.pop("receipt_digest", None)
    _require(
        observed == expected_digest == canonical_digest(payload),
        f"{label} receipt digest changed",
    )


def _comparison(
    selected: Mapping[str, Any],
    parent: Mapping[str, Any],
) -> dict[str, float]:
    return {
        "wrist_rms_relative_improvement": _relative_improvement(
            float(selected["per_joint_rms_degrees"]["wrist_flex"]),
            float(parent["per_joint_rms_degrees"]["wrist_flex"]),
        ),
        "joint_rms_relative_improvement": _relative_improvement(
            float(selected["overall_joint_rms_degrees"]),
            float(parent["overall_joint_rms_degrees"]),
        ),
        "ee_rms_relative_improvement": _relative_improvement(
            float(selected["ee_rms_m"]),
            float(parent["ee_rms_m"]),
        ),
    }


def validate(
    *,
    contract_path: Path = CONTRACT_PATH,
    output_path: Path,
) -> dict[str, Any]:
    contract_path = contract_path.resolve()
    contract = _load_json(contract_path)
    _require(contract.get("schema_version") == SCHEMA, "contract schema changed")
    _require(
        contract.get("status")
        == (
            "prospective_opposite_bias_evaluator_frozen_"
            "positive_opened_negative_unopened"
        ),
        "heldout status changed",
    )
    _require(
        not any((contract.get("authority") or {}).values()),
        "heldout authority widened",
    )
    _require(
        all((contract.get("action_invariance") or {}).values()),
        "action invariance is not fail closed",
    )
    _require(
        contract.get("proof_boundary")
        == {
            "fixed_branch_selected_before_both_traces": True,
            "positive_trace_opened_before_replacement_contract_frozen": True,
            "negative_trace_opened_when_contract_frozen": False,
            "replacement_configuration_selected_for_torque_off_stability_not_metrics": True,
            "selection_may_run_after_negative_trace": False,
            "evaluator_may_refit": False,
            "passing_result_may_admit_pawn_contact": False,
        },
        "heldout proof boundary changed",
    )

    sources = contract["sources"]
    _bound_path(sources["implementation"])
    retrospective_contract_path = _bound_path(
        sources["retrospective_contract"]
    )
    retrospective_contract = _load_json(retrospective_contract_path)
    retrospective_receipt_path = _bound_path(
        sources["retrospective_receipt"]
    )
    retrospective_receipt = _load_json(retrospective_receipt_path)
    _verify_digest(
        retrospective_receipt,
        str(sources["retrospective_receipt"]["receipt_digest"]),
        label="fixed-branch retrospective",
    )

    expected = contract["expected_model"]
    _require(
        retrospective_receipt.get("contract_sha256")
        == sha256_file(retrospective_contract_path)
        and retrospective_receipt.get("selected_candidate_id")
        == expected["selected_candidate_id"]
        and retrospective_receipt.get("selected_fixed_load_sign")
        == expected["selected_fixed_load_sign"]
        and retrospective_receipt.get("parameters_promoted")
        is expected["parameters_promoted"],
        "frozen fixed-branch selection changed",
    )
    frozen_parent = {
        "application_delay_seconds": expected["application_delay_seconds"],
        "load_sign_zero_threshold_nm": expected[
            "load_sign_zero_threshold_nm"
        ],
        "selected_expanded_half_width_degrees": expected[
            "selected_expanded_half_width_degrees"
        ],
    }
    _require(
        retrospective_contract.get("frozen_parent") == frozen_parent,
        "frozen parent play parameters changed",
    )

    hysteresis_fit_path = _bound_path(
        retrospective_contract["sources"]["frozen_parameters"]
    )
    hysteresis_fit = _load_json(hysteresis_fit_path)
    reverse_fit_path = _bound_path(
        hysteresis_fit["sources"]["parent_fit_contract"]
    )
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

    packet_bindings = sources["packets"]
    _require(
        list(packet_bindings)
        == ["positive_wrist_bias", "negative_wrist_bias"],
        "heldout packet set changed",
    )
    packets: dict[str, dict[str, Any]] = {}
    packet_paths: dict[str, Path] = {}
    for packet_id, binding in packet_bindings.items():
        packet_path = _bound_path(binding)
        packet = _load_json(packet_path)
        _require(
            packet.get("plan_sha256") == binding["plan_sha256"],
            f"heldout packet plan changed: {packet_id}",
        )
        packet_paths[packet_id] = packet_path
        packets[packet_id] = packet
    stage_specs = sources["heldout_stages"]
    _require(
        len(stage_specs) == 2
        and [int(stage["stage_index"]) for stage in stage_specs] == [2, 2]
        and [stage["configuration"] for stage in stage_specs]
        == ["positive_wrist_bias", "negative_wrist_bias"],
        "heldout stage set changed",
    )
    triangle_actions = [
        _decode_stage(
            packets[stage["packet_id"]]["stages"][
                int(stage["stage_index"]) - 1
            ]
        )[0]
        for stage in stage_specs
    ]
    triangle_deltas = [
        np.ascontiguousarray(actions - actions[0], dtype="<f8")
        for actions in triangle_actions
    ]
    triangle_delta_hashes = [
        hashlib.sha256(delta.tobytes(order="C")).hexdigest()
        for delta in triangle_deltas
    ]
    expected_delta_hash = str(
        sources["normalized_triangle_delta_sha256"]
    )
    _require(
        sources["normalized_triangle_delta_encoding"]
        == (
            "little_endian_float64_c_order_after_subtracting_"
            "each_stage_row_zero"
        )
        and np.array_equal(triangle_deltas[0], triangle_deltas[1])
        and triangle_delta_hashes
        == [expected_delta_hash, expected_delta_hash]
        and np.all(triangle_deltas[0][:, [0, 1, 2, 4, 5]] == 0.0)
        and float(np.min(triangle_deltas[0][:, 3])) == -6.0
        and float(np.max(triangle_deltas[0][:, 3])) == 6.0
        and np.all(triangle_deltas[0][-1] == 0.0),
        "heldout triangle normalized action invariance changed",
    )

    settle_steps = int(mechanism["candidate_grid"]["initial_settle_steps"])
    replay_kwargs = {
        "settle_steps": settle_steps,
        "delay_seconds": float(expected["application_delay_seconds"]),
        "half_width_degrees": expected[
            "selected_expanded_half_width_degrees"
        ],
        "load_sign_zero_threshold_nm": float(
            expected["load_sign_zero_threshold_nm"]
        ),
    }
    limits = contract["gates"]["maximum_return_error_degrees"]
    joint_indices = {
        "shoulder_pan": 0,
        "shoulder_lift": 1,
        "elbow_flex": 2,
        "wrist_flex": 3,
    }
    heldouts: list[dict[str, Any]] = []
    for stage_spec in stage_specs:
        packet_id = str(stage_spec["packet_id"])
        _require(
            packet_id == stage_spec["configuration"]
            and packet_id in packets,
            "heldout stage packet binding changed",
        )
        packet = packets[packet_id]
        packet_path = packet_paths[packet_id]
        stage_index = int(stage_spec["stage_index"])
        packet_stage = packet["stages"][stage_index - 1]
        _require(
            packet_stage["action_sha256"]
            == stage_spec["expected_action_sha256"]
            and packet_stage["capture_hold_action_sha256"]
            == stage_spec["expected_capture_hold_action_sha256"],
            f"heldout stage {stage_index} action identity changed",
        )

        execution_path = _repo_path(stage_spec["execution_receipt_path"])
        samples_path = _repo_path(stage_spec["samples_path"])
        _require(
            execution_path.is_file() and samples_path.is_file(),
            "preregistered heldout executions have not completed",
        )
        execution = _load_json(execution_path)
        _require(
            execution.get("status") == "completed_wrist_view_reposition_stage"
            and execution.get("stage_index") == stage_index
            and execution.get("packet_sha256") == sha256_file(packet_path)
            and execution.get("action_sha256")
            == packet_stage["action_sha256"]
            and execution.get("capture_hold_action_sha256")
            == packet_stage["capture_hold_action_sha256"]
            and execution.get("completed_samples")
            == int(stage_spec["expected_sample_count"])
            and execution.get("joint_samples_sha256")
            == sha256_file(samples_path)
            and execution.get("physical_follower_torque_enabled") is False,
            f"heldout stage {stage_index} receipt is not exact and torque-off",
        )
        stage_source = {
            "stage_index": stage_index,
            "samples_path": str(samples_path.relative_to(REPO_ROOT)),
            "samples_sha256": sha256_file(samples_path),
            "execution_receipt_path": str(
                execution_path.relative_to(REPO_ROOT)
            ),
            "execution_receipt_sha256": sha256_file(execution_path),
        }
        _, loaded = _stage_payload(stage_source, packet)
        mapped = _mapped_episode(loaded["payload"], workcell)
        parent_states, parent_schedule = replay_joint_play(
            mapped,
            workcell,
            **replay_kwargs,
        )
        selected_states, selected_schedule = replay_joint_play_fixed_branch(
            mapped,
            workcell,
            fixed_load_sign=expected["selected_fixed_load_sign"],
            **replay_kwargs,
        )
        parent_metrics = _strip_arrays(
            _episode_metrics(mapped, parent_states, workcell, mechanism)
        )
        selected_metrics = _strip_arrays(
            _episode_metrics(mapped, selected_states, workcell, mechanism)
        )
        comparison = _comparison(selected_metrics, parent_metrics)
        return_error = {
            name: abs(float(execution["final_residual_degrees"][index]))
            for name, index in joint_indices.items()
        }
        tricam = _tricam_gates(execution)
        stage_gates = {
            "exact_action_invariance": True,
            "all_three_camera_intervals_enclose_action": all(tricam.values()),
            "follower_torque_off_at_close": (
                execution["physical_follower_torque_enabled"] is False
            ),
            "return_error_within_limits": all(
                return_error[name] <= float(limits[name])
                for name in return_error
            ),
            "fixed_branch_wrist_rms_improves_over_parent": (
                comparison["wrist_rms_relative_improvement"] > 0.0
            ),
            "fixed_branch_joint_rms_improves_over_parent": (
                comparison["joint_rms_relative_improvement"] > 0.0
            ),
            "fixed_branch_ee_rms_improves_over_parent": (
                comparison["ee_rms_relative_improvement"] > 0.0
            ),
        }
        heldouts.append(
            {
                "configuration": stage_spec["configuration"],
                "packet_id": packet_id,
                "stage_index": stage_index,
                "source": loaded["source"],
                "mapped_action_receipt": mapped["action_receipt"],
                "variants": {
                    "dynamic_load_sign_parent": {
                        "schedule_sha256": parent_schedule["sha256"],
                        "metrics": parent_metrics,
                    },
                    "fixed_positive_wrist_branch": {
                        "fixed_load_sign": expected[
                            "selected_fixed_load_sign"
                        ],
                        "schedule_sha256": selected_schedule["sha256"],
                        "metrics": selected_metrics,
                    },
                },
                "comparison": comparison,
                "return_error_degrees": return_error,
                "tricam_action_enclosure": tricam,
                "gates": stage_gates,
                "passed": all(stage_gates.values()),
            }
        )

    overall_gates = {
        "both_heldout_configurations_completed": len(heldouts) == 2,
        "all_stage_gates_passed": all(stage["passed"] for stage in heldouts),
        "fixed_branch_wrist_rms_improved_on_both": all(
            stage["comparison"]["wrist_rms_relative_improvement"] > 0.0
            for stage in heldouts
        ),
        "fixed_branch_joint_rms_improved_on_both": all(
            stage["comparison"]["joint_rms_relative_improvement"] > 0.0
            for stage in heldouts
        ),
        "fixed_branch_ee_rms_improved_on_both": all(
            stage["comparison"]["ee_rms_relative_improvement"] > 0.0
            for stage in heldouts
        ),
    }
    passed = all(overall_gates.values())
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "evaluation_id": contract["evaluation_id"],
        "proof_class": contract["proof_class"],
        "contract_path": str(contract_path),
        "contract_sha256": sha256_file(contract_path),
        "implementation_path": str(Path(__file__).resolve()),
        "implementation_sha256": sha256_file(Path(__file__).resolve()),
        "retrospective_receipt_path": str(retrospective_receipt_path),
        "retrospective_receipt_sha256": sha256_file(
            retrospective_receipt_path
        ),
        "normalized_triangle_delta_sha256": expected_delta_hash,
        "normalized_triangle_delta_hashes": triangle_delta_hashes,
        "heldouts": heldouts,
        "overall_gates": overall_gates,
        "heldout_passed": passed,
        "verdict": (
            "fixed_positive_wrist_branch_passed_two_configuration_heldout"
            if passed
            else "fixed_positive_wrist_branch_rejected_on_two_configuration_heldout"
        ),
        "parameter_fitting_performed": False,
        "parameters_promoted": False,
        "action_correction_performed": False,
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
            validate(contract_path=args.contract, output_path=args.output),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
