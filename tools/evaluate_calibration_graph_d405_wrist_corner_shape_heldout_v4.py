#!/usr/bin/env python3
"""Evaluate wrist-corner shape with copy-safe MuJoCo body rotations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np

from sim2claw.paths import REPO_ROOT
import tools.evaluate_calibration_graph_d405_corner_shape_heldout_v2 as shape_v2
from tools.evaluate_calibration_graph_d405_rotation_heldout_v1 import (
    bound,
    require,
    sha256,
)


EVIDENCE_STATUS = {
    "corrected_evaluator_diagnostic_on_opened_v3_capture": (
        "frozen_copy_fix_diagnostic_after_v3_capture_open"
    ),
    "fresh_prospective_capture": (
        "frozen_after_execution_before_any_new_frame_open"
    ),
}


def copied_body_rotation(*args: Any, **kwargs: Any) -> np.ndarray:
    """Break the live MuJoCo xmat view before trajectory accumulation."""

    return shape_v2.body_rotation(*args, **kwargs).copy()


def stage_shape_copy_safe(**kwargs: Any) -> dict[str, Any]:
    original = shape_v2.body_rotation
    shape_v2.body_rotation = copied_body_rotation
    try:
        return shape_v2.stage_shape(**kwargs)
    finally:
        shape_v2.body_rotation = original


def evaluate(contract_path: Path) -> dict[str, Any]:
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    evidence_class = contract.get("evidence_class")
    require(
        contract.get("schema_version")
        == "sim2claw.calibration_graph_d405_wrist_corner_shape_heldout.v4"
        and evidence_class in EVIDENCE_STATUS
        and contract.get("status") == EVIDENCE_STATUS[evidence_class]
        and contract["authority"]
        == {
            "read_bound_physical_capture": True,
            "evaluate_wrist_trajectory_shape": True,
            "fit_parameters": False,
            "mapping_approval": False,
            "camera": False,
            "gateway": False,
            "serial": False,
            "physical_motion": False,
            "physical_task_attempt": False,
            "simulator_promotion": False,
            "transfer_claim": False,
        },
        "D405 wrist corner-shape v4 contract widened",
    )
    packet_path = bound(contract["sources"]["packet"])
    review_path = bound(contract["sources"]["review"])
    manifest_path = bound(contract["sources"]["candidate_manifest"])
    bound(contract["sources"]["v3_closeout"])
    bound(contract["implementation"])
    bound(contract["implementation_dependency"])
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    review = json.loads(review_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(
        review["packet_sha256"] == sha256(packet_path)
        and review["status"] == "admitted_for_one_execution_per_stage"
        and len(packet["stages"]) == 1,
        "D405 wrist corner-shape v4 packet/review binding changed",
    )
    specification = contract["stage"]
    receipt_path = bound(specification["execution_receipt"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    packet_stage = dict(packet["stages"][0])
    packet_stage["active_joint_index"] = 3
    require(
        receipt["packet_sha256"] == sha256(packet_path)
        and receipt["review_sha256"] == sha256(review_path)
        and receipt["stage_index"] == 1
        and receipt["action_sha256"]
        == packet_stage["action_sha256"]
        == specification["expected_action_sha256"]
        and receipt["status"] == "completed_wrist_view_reposition_stage"
        and receipt["physical_follower_torque_enabled"] is False
        and receipt["error"] is None,
        "wrist stage is not an exact torque-off completion",
    )
    result = stage_shape_copy_safe(
        stage_path=receipt_path.parent,
        receipt=receipt,
        packet_stage=packet_stage,
        candidate_config=manifest["candidate_config"],
        method=contract["method"],
    )
    metrics = result["metrics"]
    gates = contract["gates"]
    checks = {
        "measured_joint_signal": (
            result["measured_active_joint_excursion_degrees"]
            >= float(gates["minimum_measured_joint_excursion_degrees"])
        ),
        "observed_image_signal": (
            metrics["observed_corner_displacement_peak_px"]
            >= float(gates["minimum_observed_corner_displacement_peak_px"])
        ),
        "simulated_rotation_signal": (
            metrics["simulated_rotation_peak_degrees"]
            >= float(gates["minimum_simulated_rotation_peak_degrees"])
        ),
        "normalized_shape_rmse": (
            metrics["normalized_shape_rmse"]
            <= float(gates["normalized_shape_rmse_max"])
        ),
        "normalized_shape_max": (
            metrics["normalized_shape_max_error"]
            <= float(gates["normalized_shape_max_error_max"])
        ),
        "normalized_shape_correlation": (
            metrics["normalized_shape_correlation"]
            >= float(gates["minimum_normalized_shape_correlation"])
        ),
        "return_residual": (
            abs(float(result["final_residual_degrees"][3]))
            <= float(gates["maximum_active_joint_return_residual_degrees"])
        ),
    }
    passed = all(checks.values())
    output = (REPO_ROOT / contract["output_path"]).resolve()
    require(not output.exists(), "immutable D405 wrist corner v4 output exists")
    receipt_output = {
        "schema_version": "sim2claw.calibration_graph_d405_wrist_corner_shape_heldout_receipt.v4",
        "status": (
            "wrist_corner_shape_v4_passed_no_automatic_promotion"
            if passed
            else "wrist_corner_shape_v4_rejected_no_automatic_promotion"
        ),
        "proof_class": (
            "corrected_evaluator_diagnostic_on_opened_v3_capture"
            if evidence_class
            == "corrected_evaluator_diagnostic_on_opened_v3_capture"
            else "prospective_exact_action_physical_d405_fixed_tag_wrist_corner_shape_mapping_heldout"
        ),
        "evidence_class": evidence_class,
        "contract_path": str(contract_path.relative_to(REPO_ROOT)),
        "contract_sha256": sha256(contract_path),
        "stage_result": {
            "joint_name": "wrist_flex",
            "joint_index": 3,
            **result,
            "checks": checks,
            "passed": passed,
        },
        "heldout_passed": (
            passed if evidence_class == "fresh_prospective_capture" else False
        ),
        "diagnostic_passed": passed,
        "physical_model_mapping_approved": False,
        "physical_follower_torque_enabled_at_close": False,
        "physical_task_attempts": 0,
        "claim_boundary": contract["claim_boundary"],
        "authority": contract["authority"],
    }
    output.parent.mkdir(parents=True)
    output.write_text(
        json.dumps(receipt_output, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt_output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, required=True)
    arguments = parser.parse_args()
    result = evaluate(arguments.contract.resolve())
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
