from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from sim2claw.learning_factory_artifacts import canonical_digest
from sim2claw.sail.structural_surprise import (
    StructuralSurpriseError,
    build_mechanism_request,
    calibrate_clean_seeded_cases,
    evaluate_surprise,
    load_surprise_config,
    verify_mechanism_request,
    verify_surprise_artifact,
    verify_surprise_receipt,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "configs" / "sail" / "structural_surprise_retired_bg_v1.json"
OUTPUT_ROOT = REPO_ROOT / "outputs" / "sail" / "retired-bg-v1" / "structural-surprise"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _signal(value: float | None, *, available: bool = True) -> dict:
    return {
        "value": value,
        "available": available,
        "provenance": "synthetic:gold-05",
        "reason": "test_fixture",
    }


def _gold_05_signals() -> dict[str, dict]:
    return {
        "boundary_pressure": _signal(1.0),
        "cross_family_regression": _signal(0.9),
        "parameter_reversal_or_drift": _signal(None, available=False),
        "phase_or_context_inconsistency": _signal(None, available=False),
        "persistent_structured_residual": _signal(0.8),
        "posterior_correlation": _signal(None, available=False),
        "sim_success_trace_regression": _signal(0.8),
        "ensemble_without_single_winner": _signal(0.7),
    }


def test_gold_05_compensation_debt_triggers() -> None:
    config = load_surprise_config(CONFIG_PATH)
    result = evaluate_surprise(
        _gold_05_signals(),
        config,
        missing_observables=["delay_state"],
    )
    assert result["evaluable"] is True
    assert result["triggered"] is True
    assert result["score"] >= config["trigger"]["score_threshold"]
    assert "boundary_pressure" in result["triggered_component_ids"]
    assert "cross_family_regression" in result["triggered_component_ids"]
    assert result["uncertainty"]["primary"] == "missing_observable"


def test_missing_components_are_not_silent_zeros() -> None:
    config = load_surprise_config(CONFIG_PATH)
    signals = {
        component["id"]: _signal(None, available=False)
        for component in config["components"]
    }
    signals["boundary_pressure"] = _signal(1.0)
    result = evaluate_surprise(signals, config)
    assert result["available_weight"] == pytest.approx(0.18)
    assert result["score"] is None
    assert result["evaluable"] is False
    assert result["triggered"] is False


def test_available_component_must_be_normalized() -> None:
    config = load_surprise_config(CONFIG_PATH)
    signals = _gold_05_signals()
    signals["boundary_pressure"] = _signal(1.01)
    with pytest.raises(StructuralSurpriseError, match="not normalized"):
        evaluate_surprise(signals, config)


def test_seeded_parameter_only_cases_stay_below_false_trigger_ceiling() -> None:
    config = load_surprise_config(CONFIG_PATH)
    first = calibrate_clean_seeded_cases(config)
    second = calibrate_clean_seeded_cases(config)
    assert first == second
    assert first["passed"] is True
    assert first["false_trigger_rate"] <= first["maximum_false_trigger_rate"]
    assert first["trigger_count"] == 0


@pytest.mark.skipif(
    not (OUTPUT_ROOT / "structural_surprise.json").is_file(),
    reason="owner-local retained structural-surprise artifact is unavailable",
)
def test_retained_boundary_and_mixed_outcomes_trigger_without_causal_claim() -> None:
    diagnostic = verify_surprise_artifact(_load(OUTPUT_ROOT / "structural_surprise.json"))
    assert diagnostic["triggered"] is True
    assert diagnostic["score"] == pytest.approx(0.942857142857143)
    assert diagnostic["physical_cause_asserted"] is False
    assert diagnostic["probable_absorption_not_cause"] is True
    assert diagnostic["evidence"]["suspected_absorber"] == "elbow_load_bias_coefficient"
    assert diagnostic["evidence"]["lift_count_delta"] == -1
    assert diagnostic["golden_case"] == {
        "id": "GOLD-05",
        "expected": "structural_surprise",
        "passed": True,
    }


def test_retained_missing_observables_and_uncertainty_classes_are_explicit() -> None:
    if not (OUTPUT_ROOT / "structural_surprise.json").is_file():
        pytest.skip("owner-local retained structural-surprise artifact is unavailable")
    diagnostic = _load(OUTPUT_ROOT / "structural_surprise.json")
    assert diagnostic["uncertainty"]["classes"] == [
        "parameter_uncertainty",
        "structural_uncertainty",
        "missing_observable",
    ]
    assert diagnostic["uncertainty"]["missing_observables"] == [
        "end_effector_to_source",
        "end_effector_to_target",
        "pawn_to_target",
        "physical_consequence",
        "physical_contact",
        "physical_contact_force",
    ]
    unavailable = [row for row in diagnostic["components"] if not row["available"]]
    assert {row["id"] for row in unavailable} == {
        "parameter_reversal_or_drift",
        "phase_or_context_inconsistency",
        "posterior_correlation",
    }
    assert all(row["value"] is None and row["weighted_contribution"] is None for row in unavailable)


def test_no_agent_request_cannot_select_mechanism_or_assert_cause() -> None:
    if not (OUTPUT_ROOT / "structural_surprise.json").is_file():
        pytest.skip("owner-local retained structural-surprise artifact is unavailable")
    config = load_surprise_config(CONFIG_PATH)
    diagnostic = verify_surprise_artifact(_load(OUTPUT_ROOT / "structural_surprise.json"))
    request = verify_mechanism_request(build_mechanism_request(diagnostic, config))
    assert request["status"] == "requested"
    assert request["agent_allowed"] is False
    assert request["mechanism_selected"] is False
    assert request["physical_cause_asserted"] is False

    changed = copy.deepcopy(request)
    changed["physical_cause_asserted"] = True
    changed.pop("request_digest")
    changed["request_digest"] = canonical_digest(changed)
    with pytest.raises(StructuralSurpriseError, match="widened authority"):
        verify_mechanism_request(changed)


def test_diagnostic_rejects_resealed_causal_claim() -> None:
    if not (OUTPUT_ROOT / "structural_surprise.json").is_file():
        pytest.skip("owner-local retained structural-surprise artifact is unavailable")
    changed = _load(OUTPUT_ROOT / "structural_surprise.json")
    changed["physical_cause_asserted"] = True
    changed.pop("diagnostic_digest")
    changed["diagnostic_digest"] = canonical_digest(changed)
    with pytest.raises(StructuralSurpriseError, match="asserted a cause"):
        verify_surprise_artifact(changed)


def test_receipt_binds_diagnostic_request_and_clean_calibration() -> None:
    path = OUTPUT_ROOT / "receipt.json"
    if not path.is_file():
        pytest.skip("owner-local retained structural-surprise receipt is unavailable")
    receipt = _load(path)
    verify_surprise_receipt(receipt, output_root=OUTPUT_ROOT)
    changed = copy.deepcopy(receipt)
    changed["result"]["gold_05_passed"] = False
    with pytest.raises(StructuralSurpriseError, match="digest mismatch"):
        verify_surprise_receipt(changed, output_root=OUTPUT_ROOT)
