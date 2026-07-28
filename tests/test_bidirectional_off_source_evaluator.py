import numpy as np
import pytest

from sim2claw.bidirectional_off_source_evaluator import (
    OffSourceEvaluatorError,
    evaluate_consequence,
    load_contract,
    raw_action_sha256,
    validate_attempt_ledger,
)


def test_contract_freezes_ten_one_use_cases_and_direction_budget() -> None:
    contract = load_contract()
    cases = contract["case_family"]
    assert len(cases) == 10
    assert len({case["case_id"] for case in cases}) == 10
    assert sum(case["direction"] == "REAL_TO_SIM" for case in cases) == 5
    assert sum(case["direction"] == "SIM_TO_REAL" for case in cases) == 5
    assert all(case["physical_attempt_budget"] == 1 for case in cases)
    assert contract["case_rules"]["maximum_physical_attempts_total"] == 10
    assert contract["case_rules"]["c2_is_excluded"] is True


def test_native_action_hash_requires_float64_c_order() -> None:
    action = np.zeros((4, 6), dtype="<f8", order="C")
    assert len(raw_action_sha256(action)) == 64
    with pytest.raises(OffSourceEvaluatorError):
        raw_action_sha256(np.zeros((4, 6), dtype=np.float32))
    with pytest.raises(OffSourceEvaluatorError):
        raw_action_sha256(np.zeros((4, 7), dtype=np.float64))


def test_complete_off_source_threshold_and_exclusions_are_strict() -> None:
    contract = load_contract()
    passed = evaluate_consequence(
        contract=contract,
        case_id="R01_G2_G1",
        initial_selected_center_xy_mm=[0.0, 0.0],
        final_selected_center_xy_mm=[0.0, -36.025],
        initial_upright_cosine=1.0,
        selected_contact_count=1,
        excluded_contact_count=0,
        maximum_excluded_displacement=4.0,
        excluded_displacement_unit="px",
    )
    assert passed["passed"] is True
    failed = evaluate_consequence(
        contract=contract,
        case_id="R01_G2_G1",
        initial_selected_center_xy_mm=[0.0, 0.0],
        final_selected_center_xy_mm=[0.0, -36.024],
        initial_upright_cosine=1.0,
        selected_contact_count=1,
        excluded_contact_count=0,
        maximum_excluded_displacement=0.0,
        excluded_displacement_unit="mm",
    )
    assert failed["passed"] is False
    assert failed["complete_off_source_passed"] is False


def test_attempt_ledger_keeps_failures_and_rejects_retries() -> None:
    contract = load_contract()
    ledger = validate_attempt_ledger(
        contract,
        [
            {"case_id": "R01_G2_G1", "passed": False},
            {"case_id": "S01_F1_F2", "passed": True},
        ],
    )
    assert ledger["REAL_TO_SIM"] == {"successes": 0, "physical_attempts": 1}
    assert ledger["SIM_TO_REAL"] == {"successes": 1, "physical_attempts": 1}
    assert ledger["total_physical_attempts"] == 2
    with pytest.raises(OffSourceEvaluatorError):
        validate_attempt_ledger(
            contract,
            [
                {"case_id": "R01_G2_G1", "passed": False},
                {"case_id": "R01_G2_G1", "passed": True},
            ],
        )
