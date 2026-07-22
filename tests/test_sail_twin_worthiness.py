from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from sim2claw.learning_factory_artifacts import canonical_digest
from sim2claw.sail.contracts import (
    SailContractError,
    seal_contract,
    validate_contract,
    verify_contract,
)
from sim2claw.sail.twin_worthiness import (
    TwinCapabilityDenied,
    capability_decision,
    capabilities_for_level,
    certificate_is_available,
    gate_verdict,
    issue_capability_certificate,
    load_capability_contract,
    load_twin_worthiness_contract,
    require_capability_decision,
    resolve_level,
    revoke_capability_certificate,
    validate_capability_certificate,
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


def _base_certificate(level: str = "TW-SELECTION") -> dict:
    gates = _gates()
    if level == "TW-REPLAY":
        gates["TW-G2"]["status"] = "not_evaluable"
        gates["TW-G3"]["status"] = "not_evaluable"
        gates["TW-G4"]["status"] = "not_evaluable"
    authority = {
        "data_generation": level in {"TW-DATA", "TW-SELECTION", "TW-PHYSICAL-CANARY"},
        "policy_selection": level in {"TW-SELECTION", "TW-PHYSICAL-CANARY"},
        "physical_canary": level == "TW-PHYSICAL-CANARY",
        "robot_motion": False,
    }
    return seal_contract(
        {
            "schema_version": "sim2claw.twin_worthiness_certificate.v1",
            "certificate_id": f"fixture-{level.lower()}",
            "campaign_id": "fixture-capability-campaign",
            "identities": {
                "evidence": ["a" * 64],
                "graph": "b" * 64,
                "posterior": "c" * 64,
                "simulator": "d" * 64,
                "evaluator": "e" * 64,
                "policy_candidates": (["f" * 64] if level in {"TW-SELECTION", "TW-PHYSICAL-CANARY"} else []),
            },
            "gates": gates,
            "level": level,
            "authority": authority,
            "issued_at": "2026-07-22T00:00:00Z",
        }
    )


def _scope() -> dict:
    return {
        "twin_id": "fixture-twin-v1",
        "workcell_id": "fixture-workcell-v1",
        "task_id": "fixture-task-v1",
        "distribution_id": "fixture-distribution-v1",
        "task_contract_sha256": "1" * 64,
        "distribution_sha256": "2" * 64,
    }


def _capability(level: str = "TW-SELECTION") -> tuple[dict, dict]:
    base = _base_certificate(level)
    certificate = issue_capability_certificate(
        base_certificate=base,
        scope=_scope(),
        not_before="2026-07-22T00:00:00Z",
        expires_at="2027-07-22T00:00:00Z",
        issuance_request={
            "issuer_owner": "deterministic_sail_evaluator",
            "request_id": f"fixture-{level}",
        },
    )
    return base, certificate


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


def test_exact_scope_selection_certificate_opens_only_declared_capabilities() -> None:
    base, certificate = _capability("TW-SELECTION")
    for capability in ("diagnostics", "data_generation", "policy_selection"):
        request = {
            "capability": capability,
            "stage_id": "LF-11",
            "scope": _scope(),
            "expected_identities": base["identities"],
            "external_authority": {},
        }
        decision = capability_decision(
            certificate, request, at_time="2026-07-22T12:00:00Z"
        )
        assert decision["allowed"] is True
        assert require_capability_decision(decision, capability=capability)[
            "decision_digest"
        ] == decision["decision_digest"]
    physical = capability_decision(
        certificate,
        {
            "capability": "physical_canary",
            "scope": _scope(),
            "expected_identities": base["identities"],
            "external_authority": {},
        },
        at_time="2026-07-22T12:00:00Z",
    )
    assert physical["allowed"] is False
    assert set(physical["denial_codes"]) == {
        "base_authority_closed",
        "external_physical_authority_missing",
        "insufficient_twin_worthiness_level",
    }


def test_scope_identity_expiry_revocation_and_tamper_revoke_capability() -> None:
    base, certificate = _capability("TW-SELECTION")
    request = {
        "capability": "data_generation",
        "scope": _scope(),
        "expected_identities": base["identities"],
        "external_authority": {},
    }
    changed_scope = copy.deepcopy(request)
    changed_scope["scope"]["distribution_id"] = "other"
    assert capability_decision(
        certificate, changed_scope, at_time="2026-07-22T12:00:00Z"
    )["denial_codes"] == ["scope_mismatch"]
    changed_identity = copy.deepcopy(request)
    changed_identity["expected_identities"]["simulator"] = "0" * 64
    assert capability_decision(
        certificate, changed_identity, at_time="2026-07-22T12:00:00Z"
    )["denial_codes"] == ["identity_mismatch"]
    assert capability_decision(
        certificate, request, at_time="2028-07-22T12:00:00Z"
    )["denial_codes"] == ["certificate_expired"]
    revoked = revoke_capability_certificate(
        certificate,
        reason="fixture revocation",
        issuer_owner="deterministic_sail_evaluator",
    )
    assert capability_decision(
        revoked, request, at_time="2026-07-22T12:00:00Z"
    )["denial_codes"] == ["certificate_revoked"]
    tampered = copy.deepcopy(certificate)
    tampered["scope"]["twin_id"] = "tampered"
    assert capability_decision(
        tampered, request, at_time="2026-07-22T12:00:00Z"
    )["denial_codes"] == ["invalid_or_tampered_certificate"]


def test_tw_replay_reports_g2_as_minimum_data_resolution() -> None:
    base, certificate = _capability("TW-REPLAY")
    decision = capability_decision(
        certificate,
        {
            "capability": "data_generation",
            "stage_id": "LF-08",
            "scope": _scope(),
            "expected_identities": base["identities"],
            "external_authority": {},
        },
        at_time="2026-07-22T12:00:00Z",
    )
    assert decision["allowed"] is False
    assert decision["failed_gates"] == ["TW-G2"]
    assert set(decision["denial_codes"]) == {
        "base_authority_closed",
        "insufficient_twin_worthiness_level",
    }
    assert "measured contact" in decision["minimum_new_evidence"][0]
    with pytest.raises(TwinCapabilityDenied):
        require_capability_decision(decision, capability="data_generation")


def test_physical_canary_and_motion_require_every_external_authority() -> None:
    base, certificate = _capability("TW-PHYSICAL-CANARY")
    external = {
        "owner_task_authority": True,
        "reviewed_gateway_preflight": True,
        "hash_bound_new_related_workcell_identity": True,
        "frozen_hardware_protocol": True,
        "reviewed_motion_authority": True,
        "motion_authority_digest_present": True,
    }
    common = {
        "scope": _scope(),
        "expected_identities": base["identities"],
        "external_authority": external,
    }
    for capability in ("physical_canary", "robot_motion"):
        decision = capability_decision(
            certificate,
            {"capability": capability, **common},
            at_time="2026-07-22T12:00:00Z",
        )
        assert decision["allowed"] is True
    missing = copy.deepcopy(common)
    missing["external_authority"]["reviewed_motion_authority"] = False
    assert capability_decision(
        certificate,
        {"capability": "robot_motion", **missing},
        at_time="2026-07-22T12:00:00Z",
    )["denial_codes"] == ["external_physical_authority_missing"]


def test_capability_contract_is_operational_extension_not_schema_rewrite() -> None:
    contract = load_capability_contract()
    assert contract["base_contract"]["sha256"] == (
        "0e4828802daa54301779621a8af1ff48e99920a84d594fa12a6c72d5ede7c9e1"
    )
    assert contract["legacy_v1_certificate_without_capability_envelope_can_authorize_downstream"] is False
    assert contract["training_code_can_issue_or_widen_certificate"] is False
    assert contract["learning_factory_stage_requirements"] == {
        "LF-08": "data_generation",
        "LF-09": "data_generation",
        "LF-11": "policy_selection",
        "LF-13": "policy_selection",
    }
    _, certificate = _capability()
    assert validate_capability_certificate(certificate)["canonical_digest"] == certificate[
        "canonical_digest"
    ]
    unsigned = copy.deepcopy(certificate)
    unsigned.pop("canonical_digest")
    assert certificate["canonical_digest"] == canonical_digest(unsigned)
