from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from sim2claw.sail.contracts import SailContractError, validate_contract, verify_contract
from sim2claw.sail.twin_worthiness import (
    capabilities_for_level,
    certificate_is_available,
    gate_verdict,
    load_twin_worthiness_contract,
    resolve_level,
)


FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "sail"
    / "twin_worthiness_certificate_valid_v1.json"
)


def _gates(status: str = "pass") -> dict[str, dict]:
    return {
        f"TW-G{index}": {"status": status, "reason": "fixture", "evidence_ids": []}
        for index in range(5)
    }


def test_gold_03_missing_channels_are_not_evaluable() -> None:
    verdict = gate_verdict(
        required=["camera", "object", "contact"],
        available={"camera": False, "object": False, "contact": False},
        threshold_failures=[],
    )
    assert verdict["status"] == "not_evaluable"
    assert resolve_level({"TW-G0": {"status": "pass"}, "TW-G1": verdict}) == "TW-DIAGNOSTIC"


def test_twin_worthiness_truth_table_is_monotonic_and_fail_closed() -> None:
    gates = _gates()
    assert resolve_level(gates) == "TW-SELECTION"
    assert resolve_level(gates, physical_canary_authorized=True) == "TW-PHYSICAL-CANARY"
    gates["TW-G2"] = {"status": "not_evaluable"}
    assert resolve_level(gates) == "TW-REPLAY"
    gates["TW-G1"] = {"status": "fail"}
    assert resolve_level(gates) == "TW-DIAGNOSTIC"


def test_capabilities_require_the_declared_level() -> None:
    assert not capabilities_for_level("TW-REPLAY")["data_generation"]
    assert capabilities_for_level("TW-DATA")["data_generation"]
    assert not capabilities_for_level("TW-DATA")["policy_selection"]
    assert capabilities_for_level("TW-SELECTION")["policy_selection"]
    assert not capabilities_for_level("TW-SELECTION")["physical_canary"]


def test_gold_17_retained_interaction_gate() -> None:
    verdict = gate_verdict(
        required=["physical_contact_state", "physical_contact_force"],
        available={"physical_contact_state": False, "physical_contact_force": False},
        threshold_failures=[],
    )
    assert verdict["status"] == "not_evaluable"
    assert resolve_level({"TW-G0": {"status": "pass"}, "TW-G1": {"status": "pass"}, "TW-G2": verdict}) == "TW-REPLAY"


def test_gold_18_policy_concordance_missing() -> None:
    verdict = gate_verdict(
        required=["policy_rank_concordance"],
        available={"policy_rank_concordance": False},
        threshold_failures=[],
    )
    assert verdict["status"] == "not_evaluable"
    gates = {"TW-G0": {"status": "pass"}, "TW-G1": {"status": "pass"}, "TW-G2": {"status": "pass"}, "TW-G3": verdict}
    assert resolve_level(gates) == "TW-DATA"


def test_gold_19_modified_certificate_revokes_capability() -> None:
    certificate = json.loads(FIXTURE.read_text())
    assert certificate_is_available(certificate)
    certificate["gates"]["TW-G1"]["status"] = "pass"
    assert not certificate_is_available(certificate)


def test_certificate_cannot_overstate_authority() -> None:
    certificate = json.loads(FIXTURE.read_text())
    certificate["authority"]["data_generation"] = True
    with pytest.raises(SailContractError, match="overstates"):
        validate_contract(certificate)


def test_certificate_level_cannot_exceed_passing_gates() -> None:
    certificate = json.loads(FIXTURE.read_text())
    certificate["level"] = "TW-DATA"
    with pytest.raises(SailContractError, match="level exceeds"):
        validate_contract(certificate)


def test_frozen_thresholds_and_missing_semantics_are_explicit() -> None:
    contract = load_twin_worthiness_contract()
    assert contract["threshold_change_policy"] == "new_contract_version_required"
    assert contract["status_semantics"]["not_evaluable"].endswith(
        "this never counts as pass"
    )
    assert set(contract["gates"]) == {f"TW-G{index}" for index in range(5)}


def test_valid_certificate_fixture_digest_is_stable() -> None:
    certificate = json.loads(FIXTURE.read_text())
    assert verify_contract(copy.deepcopy(certificate))["canonical_digest"] == certificate[
        "canonical_digest"
    ]
