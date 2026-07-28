#!/usr/bin/env python3
"""Evaluate the frozen wrist hysteresis band on one fresh tricam heldout."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from sim2claw.actuator_external_validation import _workcell_candidate
from sim2claw.geometric_joint_play import replay_joint_play
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
    / "geometric_joint_play_hysteresis_holdout_v1.json"
)
SCHEMA = "sim2claw.geometric_joint_play_hysteresis_holdout.v1"
RECEIPT_SCHEMA = (
    "sim2claw.geometric_joint_play_hysteresis_holdout_receipt.v1"
)


class GeometricJointPlayHysteresisHoldoutError(RuntimeError):
    """The hysteresis fit, heldout, evaluator, or authority boundary changed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GeometricJointPlayHysteresisHoldoutError(message)


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
        == "prospective_evaluator_frozen_heldout_unopened",
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
            "heldout_opened_when_contract_frozen": False,
            "fit_may_run_after_heldout": False,
            "evaluator_may_refit": False,
            "passing_result_may_admit_pawn_contact": False,
        },
        "heldout proof boundary changed",
    )

    sources = contract["sources"]
    _bound_path(sources["support_implementation"])
    fit_contract_path = _bound_path(sources["fit_contract"])
    fit_contract = _load_json(fit_contract_path)
    fit_receipt_path = _bound_path(sources["fit_receipt"])
    fit_receipt = _load_json(fit_receipt_path)
    _verify_digest(
        fit_receipt,
        str(sources["fit_receipt"]["receipt_digest"]),
        label="hysteresis fit",
    )
    expected_fit = contract["expected_fit"]
    _require(
        fit_receipt.get("contract_sha256") == sha256_file(fit_contract_path)
        and fit_receipt.get("selected_candidate_id")
        == expected_fit["selected_candidate_id"]
        and fit_receipt.get("selected_wrist_load_sign_hysteresis_nm")
        == expected_fit["selected_wrist_load_sign_hysteresis_nm"]
        and fit_receipt.get("parameters_promoted")
        is expected_fit["parameters_promoted"],
        "frozen hysteresis fit selection changed",
    )
    _require(
        fit_contract.get("frozen_parent")
        == {
            "application_delay_seconds": expected_fit[
                "application_delay_seconds"
            ],
            "load_sign_zero_threshold_nm": expected_fit[
                "load_sign_zero_threshold_nm"
            ],
            "selected_expanded_half_width_degrees": expected_fit[
                "selected_expanded_half_width_degrees"
            ],
        },
        "frozen parent play parameters changed",
    )

    reverse_fit_contract_path = _bound_path(
        fit_contract["sources"]["parent_fit_contract"]
    )
    reverse_fit_contract = _load_json(reverse_fit_contract_path)
    original_fit_contract_path = _bound_path(
        reverse_fit_contract["sources"]["parent_fit_contract"]
    )
    original_fit_contract = _load_json(original_fit_contract_path)
    selection_path = _bound_path(
        original_fit_contract["sources"]["selection_receipt"]
    )
    selection = _load_json(selection_path)
    mechanism_path = _bound_path(
        original_fit_contract["sources"]["mechanism_contract"]
    )
    mechanism = load_servo_load_bias_contract(mechanism_path)
    workcell = _workcell_candidate(selection)

    packet_path = _bound_path(sources["packet"])
    packet = _load_json(packet_path)
    _require(
        packet.get("plan_sha256") == sources["packet"]["plan_sha256"],
        "heldout packet plan changed",
    )
    stage_spec = sources["heldout_stage"]
    stage_index = int(stage_spec["stage_index"])
    packet_stage = packet["stages"][stage_index - 1]
    _require(
        packet_stage["action_sha256"]
        == stage_spec["expected_action_sha256"]
        and packet_stage["capture_hold_action_sha256"]
        == stage_spec["expected_capture_hold_action_sha256"],
        "heldout action identity changed",
    )

    execution_path = _repo_path(stage_spec["execution_receipt_path"])
    samples_path = _repo_path(stage_spec["samples_path"])
    _require(
        execution_path.is_file() and samples_path.is_file(),
        "preregistered heldout execution has not completed",
    )
    execution = _load_json(execution_path)
    _require(
        execution.get("status") == "completed_wrist_view_reposition_stage"
        and execution.get("packet_sha256") == sha256_file(packet_path)
        and execution.get("action_sha256") == packet_stage["action_sha256"]
        and execution.get("capture_hold_action_sha256")
        == packet_stage["capture_hold_action_sha256"]
        and execution.get("completed_samples")
        == int(stage_spec["expected_sample_count"])
        and execution.get("joint_samples_sha256") == sha256_file(samples_path)
        and execution.get("physical_follower_torque_enabled") is False,
        "heldout execution receipt is not exact and torque-off",
    )
    stage_source = {
        "stage_index": stage_index,
        "samples_path": str(samples_path.relative_to(REPO_ROOT)),
        "samples_sha256": sha256_file(samples_path),
        "execution_receipt_path": str(execution_path.relative_to(REPO_ROOT)),
        "execution_receipt_sha256": sha256_file(execution_path),
    }
    _, loaded = _stage_payload(stage_source, packet)
    mapped = _mapped_episode(loaded["payload"], workcell)
    settle_steps = int(mechanism["candidate_grid"]["initial_settle_steps"])
    delay_seconds = float(expected_fit["application_delay_seconds"])
    zero_threshold = float(expected_fit["load_sign_zero_threshold_nm"])
    widths = expected_fit["selected_expanded_half_width_degrees"]

    parent_states, parent_schedule = replay_joint_play(
        mapped,
        workcell,
        settle_steps=settle_steps,
        delay_seconds=delay_seconds,
        half_width_degrees=widths,
        load_sign_zero_threshold_nm=zero_threshold,
    )
    selected_states, selected_schedule = replay_joint_play(
        mapped,
        workcell,
        settle_steps=settle_steps,
        delay_seconds=delay_seconds,
        half_width_degrees=widths,
        load_sign_zero_threshold_nm=zero_threshold,
        load_sign_hysteresis_nm={
            "wrist_flex": float(
                expected_fit["selected_wrist_load_sign_hysteresis_nm"]
            )
        },
    )
    parent_metrics = _strip_arrays(
        _episode_metrics(mapped, parent_states, workcell, mechanism)
    )
    selected_metrics = _strip_arrays(
        _episode_metrics(mapped, selected_states, workcell, mechanism)
    )
    comparison = {
        "wrist_rms_relative_improvement": _relative_improvement(
            selected_metrics["per_joint_rms_degrees"]["wrist_flex"],
            parent_metrics["per_joint_rms_degrees"]["wrist_flex"],
        ),
        "joint_rms_relative_improvement": _relative_improvement(
            selected_metrics["overall_joint_rms_degrees"],
            parent_metrics["overall_joint_rms_degrees"],
        ),
        "ee_rms_relative_improvement": _relative_improvement(
            selected_metrics["ee_rms_m"],
            parent_metrics["ee_rms_m"],
        ),
    }
    joint_indices = {
        "shoulder_pan": 0,
        "shoulder_lift": 1,
        "elbow_flex": 2,
        "wrist_flex": 3,
    }
    return_error = {
        name: abs(float(execution["final_residual_degrees"][index]))
        for name, index in joint_indices.items()
    }
    limits = contract["gates"]["maximum_return_error_degrees"]
    tricam = _tricam_gates(execution)
    gates = {
        "exact_action_invariance": True,
        "all_three_camera_intervals_enclose_action": all(tricam.values()),
        "follower_torque_off_at_close": (
            execution["physical_follower_torque_enabled"] is False
        ),
        "return_error_within_limits": all(
            return_error[name] <= float(limits[name])
            for name in return_error
        ),
        "selected_wrist_rms_improves_over_parent": (
            comparison["wrist_rms_relative_improvement"] > 0.0
        ),
        "selected_joint_rms_improves_over_parent": (
            comparison["joint_rms_relative_improvement"] > 0.0
        ),
        "selected_ee_rms_improves_over_parent": (
            comparison["ee_rms_relative_improvement"] > 0.0
        ),
    }
    passed = all(gates.values())
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "evaluation_id": contract["evaluation_id"],
        "proof_class": contract["proof_class"],
        "contract_path": str(contract_path),
        "contract_sha256": sha256_file(contract_path),
        "implementation_path": str(Path(__file__).resolve()),
        "implementation_sha256": sha256_file(Path(__file__).resolve()),
        "fit_receipt_path": str(fit_receipt_path),
        "fit_receipt_sha256": sha256_file(fit_receipt_path),
        "heldout_source": loaded["source"],
        "mapped_action_receipt": mapped["action_receipt"],
        "variants": {
            "parent_reverse_play_without_hysteresis": {
                "parameters": {
                    "half_width_degrees": widths,
                    "wrist_load_sign_hysteresis_nm": None,
                },
                "schedule_sha256": parent_schedule["sha256"],
                "metrics": parent_metrics,
            },
            "selected_reverse_play_with_hysteresis": {
                "parameters": {
                    "half_width_degrees": widths,
                    "wrist_load_sign_hysteresis_nm": expected_fit[
                        "selected_wrist_load_sign_hysteresis_nm"
                    ],
                },
                "schedule_sha256": selected_schedule["sha256"],
                "metrics": selected_metrics,
            },
        },
        "comparison": comparison,
        "return_error_degrees": return_error,
        "tricam_action_enclosure": tricam,
        "gates": gates,
        "heldout_passed": passed,
        "verdict": (
            "wrist_hysteresis_passed_fresh_geometric_heldout"
            if passed
            else "wrist_hysteresis_rejected_on_fresh_geometric_heldout"
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
