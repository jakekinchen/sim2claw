from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from sim2claw.sail.contracts import (
    SCHEMA_PATHS,
    SailContractError,
    action_descriptor,
    admitted_corrective_row_count,
    assert_action_invariant,
    assert_parameter_within_bounds,
    assert_provider_identity_stable,
    load_schema,
    phase_timing_error,
    sealed_access_allowed,
    validate_contract,
    verify_contract,
    verify_source_binding,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "sail"
VALID_FIXTURES = {
    "CalibrationEvidence.v1": "calibration_evidence_valid_v1.json",
    "ResidualField.v1": "residual_field_valid_v1.json",
    "PhysicalMechanism.v1": "physical_mechanism_valid_v1.json",
    "Intervention.v1": "intervention_valid_v1.json",
    "TwinWorthinessCertificate.v1": "twin_worthiness_certificate_valid_v1.json",
}


def _fixture(name: str) -> dict:
    return json.loads((FIXTURE_ROOT / VALID_FIXTURES[name]).read_text())


def test_all_five_draft_2020_12_schemas_and_positive_fixtures_validate() -> None:
    assert set(SCHEMA_PATHS) == set(VALID_FIXTURES)
    for contract_name in sorted(SCHEMA_PATHS):
        schema = load_schema(contract_name)
        assert schema["$schema"].endswith("draft/2020-12/schema")
        assert verify_contract(_fixture(contract_name))["schema_version"]


@pytest.mark.parametrize(
    ("contract_name", "mutator"),
    [
        ("CalibrationEvidence.v1", lambda value: value.pop("source")),
        (
            "ResidualField.v1",
            lambda value: value["samples"][1].update({"value": 0.0}),
        ),
        (
            "PhysicalMechanism.v1",
            lambda value: value["parameters"][0].update({"minimum": 1.0, "maximum": 0.0}),
        ),
        (
            "Intervention.v1",
            lambda value: value["authority"].update({"agent_can_promote": True}),
        ),
        (
            "TwinWorthinessCertificate.v1",
            lambda value: value["authority"].update({"robot_motion": True}),
        ),
    ],
)
def test_every_schema_rejects_malformed_or_authority_violating_fixture(
    contract_name: str, mutator
) -> None:
    value = _fixture(contract_name)
    mutator(value)
    with pytest.raises(SailContractError):
        validate_contract(value, contract_name=contract_name)


def test_gold_00_source_binding_fails_closed(tmp_path: Path) -> None:
    source_file = tmp_path / "source.bin"
    source_file.write_bytes(b"frozen-source")
    binding = {
        "path": source_file.name,
        "sha256": hashlib.sha256(b"frozen-source").hexdigest(),
    }
    assert verify_source_binding(binding, repo_root=tmp_path) == source_file
    source_file.write_bytes(b"changed-source")
    with pytest.raises(SailContractError, match="digest mismatch"):
        verify_source_binding(binding, repo_root=tmp_path)
    source_file.unlink()
    with pytest.raises(SailContractError, match="missing"):
        verify_source_binding(binding, repo_root=tmp_path)


def test_gold_01_action_bytes_dtype_and_order_are_identity() -> None:
    expected = action_descriptor(
        b"12345678", shape=[1, 1], dtype="float64", ordering="time_joint_c"
    )
    assert_action_invariant(expected, dict(expected))
    for changed in (
        action_descriptor(
            b"12345678", shape=[1, 1], dtype="float32", ordering="time_joint_c"
        ),
        action_descriptor(
            b"12345678", shape=[1, 1], dtype="float64", ordering="joint_time_c"
        ),
        action_descriptor(
            b"87654321", shape=[1, 1], dtype="float64", ordering="time_joint_c"
        ),
    ):
        with pytest.raises(SailContractError, match="action invariance"):
            assert_action_invariant(expected, changed)


def test_gold_02_valid_contract_round_trip() -> None:
    evidence = _fixture("CalibrationEvidence.v1")
    first = verify_contract(evidence)
    second = verify_contract(json.loads(json.dumps(first, sort_keys=True)))
    assert first["canonical_digest"] == second["canonical_digest"]
    assert first["observations"]["joint_position"]["available"] == [True, True]


def test_gold_04_phase_shift_cannot_hide_behind_minimum() -> None:
    expected = [0.0, 1.0, 2.0, 1.0, 0.0]
    shifted = [0.0, 0.0, 1.0, 2.0, 1.0]
    assert min(expected) == min(shifted)
    assert phase_timing_error(expected, shifted) > 0.0


def test_gold_13_sealed_access_is_evaluator_only() -> None:
    assert not sealed_access_allowed(actor_role="codex_agent", evaluator_owned=True)
    assert not sealed_access_allowed(
        actor_role="deterministic_evaluator", evaluator_owned=False
    )
    assert sealed_access_allowed(
        actor_role="deterministic_evaluator", evaluator_owned=True
    )


def test_gold_14_parameter_bounds_fail_closed() -> None:
    mechanism = verify_contract(_fixture("PhysicalMechanism.v1"))
    assert_parameter_within_bounds(mechanism, {"delay_seconds": 0.1})
    with pytest.raises(SailContractError, match="out of bounds"):
        assert_parameter_within_bounds(mechanism, {"delay_seconds": 0.3})


def test_gold_15_failed_correction_admits_zero_rows() -> None:
    assert (
        admitted_corrective_row_count(
            trajectory_succeeded=False, suffix_succeeded=True, suffix_row_count=20
        )
        == 0
    )
    assert (
        admitted_corrective_row_count(
            trajectory_succeeded=True, suffix_succeeded=False, suffix_row_count=20
        )
        == 0
    )
    assert (
        admitted_corrective_row_count(
            trajectory_succeeded=True, suffix_succeeded=True, suffix_row_count=20
        )
        == 20
    )


def test_gold_24_provider_identity_must_be_stable() -> None:
    first = {
        "provider": "provider-a",
        "model": "model-a",
        "model_revision": "rev-1",
        "harness_sha256": "a" * 64,
    }
    assert_provider_identity_stable([first, copy.deepcopy(first)])
    changed = {**first, "model_revision": "rev-2"}
    with pytest.raises(SailContractError, match="identity changed"):
        assert_provider_identity_stable([first, changed])


def test_golden_registry_has_exactly_25_stable_unique_cases() -> None:
    registry = json.loads((FIXTURE_ROOT / "golden_cases_v1.json").read_text())
    case_ids = [row["id"] for row in registry["cases"]]
    assert case_ids == [f"GOLD-{index:02d}" for index in range(25)]
    assert len(set(case_ids)) == 25


def test_six_ci_tiers_are_frozen_and_privileged_tiers_are_manual() -> None:
    config = json.loads(
        (SCHEMA_PATHS["CalibrationEvidence.v1"].parents[1] / "ci_tiers_v1.json").read_text()
    )
    tiers = config["tiers"]
    assert [row["ordinal"] for row in tiers] == list(range(1, 7))
    assert [row["id"] for row in tiers] == [
        "fast_contract",
        "synthetic_golden",
        "integration",
        "retained_evidence",
        "provider_campaign",
        "hardware",
    ]
    assert tiers[4]["mode"] == "manual_budgeted"
    assert tiers[5]["mode"] == "manual_separately_authorized"
    assert tiers[5]["gateway_only"] is True
