from __future__ import annotations

from sim2claw.observable_registration_measured_state_compliance import (
    _parameters,
    load_measured_state_compliance_contract,
)


def test_compliance_contract_preserves_raw_driver_and_force() -> None:
    contract = load_measured_state_compliance_contract()
    baseline, candidate = contract["variants"]

    assert baseline["sts3215_force_limit_nm"] == 2.94
    assert candidate["sts3215_force_limit_nm"] == 2.94
    assert contract["trajectory"]["robot_driver"] == "raw_follower_actual_position_degrees"
    assert contract["contact_model"]["zero_refit_on_d1_to_d2"] is True


def test_only_compliance_enablement_differs_between_parameter_sets() -> None:
    contract = load_measured_state_compliance_contract()
    rigid = _parameters(contract, compliance_enabled=False)
    compliant = _parameters(contract, compliance_enabled=True)

    differing = {
        key
        for key in rigid
        if rigid[key] != compliant[key]
    }
    assert differing == {"rubber_tip_normal_compliance_enabled"}
