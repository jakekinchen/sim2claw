from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from sim2claw.paths import REPO_ROOT
from sim2claw.twin_fidelity_closure import (
    DOMAIN_ORDER,
    TwinFidelityClosureError,
    compile_twin_fidelity_closure,
    evaluate_verified_twin_fidelity_closure,
    load_twin_fidelity_closure_contract,
)


CONTRACT = REPO_ROOT / "configs/evaluations/twin_fidelity_closure_v1.json"
LIVE_RECEIPT = REPO_ROOT / "outputs/sail/live-operator-c2-adapter-v1/receipt.json"
HIL_RECEIPT = REPO_ROOT / "outputs/current-100mm-hil-evidence-v1/receipt.json"


def _verified_inputs() -> tuple[dict, dict, dict, dict]:
    contract = load_twin_fidelity_closure_contract()
    hil = {
        "summary": {
            "admitted_packet_ids": ["HIL-GRIPPER-05", "HIL-SHOULDER-LIFT-22"],
            "rejected_packet_count": 2,
            "remaining_observables": [
                "calibrated_current_zero_and_scale",
                "command_application_timestamp",
                "force",
            ],
        },
        "offline_decomposition": {
            "report": {
                "packets": [
                    {
                        "action_identity": {
                            "requested_action_sha256": f"requested-{index}",
                            "applied_action_sha256": f"applied-{index}",
                        }
                    }
                    for index in range(4)
                ]
            }
        },
        "simulator": {
            "evaluation": {
                "verdict": "diagnostic_shoulder_range_external_tie_or_loss_no_promotion"
            }
        },
    }
    receipt = {"verdict": "evaluator_reject"}
    consequence = {
        "candidate_count": 4,
        "strict_task_and_ee_pass_count": 0,
        "admitted_evaluator_owned_evidence": False,
    }
    return contract, hil, receipt, consequence


def test_closure_contract_has_explicit_six_domain_denominator() -> None:
    contract = load_twin_fidelity_closure_contract()
    assert tuple(contract["domain_order"]) == DOMAIN_ORDER
    assert contract["completion"] == {
        "required_domain_count": 6,
        "required_pass_count": 6,
        "allow_weighted_percentage": False,
        "allow_unknown_as_zero": False,
        "allow_partial_as_pass": False,
    }
    assert not any(contract["authority"].values())


def test_verified_current_evidence_is_not_perfect_and_keeps_states_distinct() -> None:
    contract, hil, receipt, consequence = _verified_inputs()
    report = evaluate_verified_twin_fidelity_closure(
        contract=contract,
        hil_bundle=hil,
        live_receipt=receipt,
        live_consequence=consequence,
        source_identity={"fixture": "verified"},
    )
    assert report["status"] == "not_perfect"
    assert report["perfect"] is False
    assert report["closure"] == {
        "passed_required_domains": 0,
        "required_domain_count": 6,
        "weighted_percentage": None,
        "unknown_counted_as_zero": False,
    }
    statuses = {row["id"]: row["status"] for row in report["domains"]}
    assert statuses == {
        "geometry_scale": "missing",
        "kinematics": "partial",
        "action_timing": "partial",
        "contact_compliance": "missing",
        "actuator_load_path": "partial",
        "task_ee_consequence": "failed",
    }
    task = report["domains"][-1]
    assert task["failed_gates"] == ["retained_c2_strict_task_and_ee_gate"]
    assert "strict_held_out_physical_task_consequence" in task["missing_evidence"]
    assert report["authority"]["robot_motion"] is False


def test_closure_fails_closed_on_authority_or_evaluator_mutation(tmp_path: Path) -> None:
    widened = json.loads(CONTRACT.read_text(encoding="utf-8"))
    widened["authority"]["robot_motion"] = True
    path = tmp_path / "widened.json"
    path.write_text(json.dumps(widened), encoding="utf-8")
    with pytest.raises(TwinFidelityClosureError, match="authority widened"):
        load_twin_fidelity_closure_contract(path, repo_root=tmp_path)

    contract, hil, receipt, consequence = _verified_inputs()
    changed = copy.deepcopy(receipt)
    changed["verdict"] = "promote"
    with pytest.raises(TwinFidelityClosureError, match="verdict changed"):
        evaluate_verified_twin_fidelity_closure(
            contract=contract,
            hil_bundle=hil,
            live_receipt=changed,
            live_consequence=consequence,
            source_identity={},
        )


@pytest.mark.skipif(
    not LIVE_RECEIPT.is_file() or not HIL_RECEIPT.is_file(),
    reason="receipt-bound local HIL/SAIL evidence unavailable",
)
def test_live_closure_materializes_byte_identically(tmp_path: Path) -> None:
    first = compile_twin_fidelity_closure(tmp_path / "first")
    second = compile_twin_fidelity_closure(tmp_path / "second")
    assert first == second
    assert (tmp_path / "first/report.json").read_bytes() == (
        tmp_path / "second/report.json"
    ).read_bytes()
    assert first["perfect"] is False
    assert first["passed_required_domains"] == 0
    assert first["required_domain_count"] == 6
