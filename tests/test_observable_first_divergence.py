from __future__ import annotations

import pytest

from sim2claw.observable_first_divergence import (
    joint_residual,
    load_divergence_contract,
)


def test_live_divergence_contract_is_read_only_and_fail_closed() -> None:
    contract = load_divergence_contract()
    assert contract["causal_policy"]["mechanism_parameters_may_be_fit_in_or4"] is False
    assert contract["causal_policy"]["simulator_may_run_in_or4"] is False
    assert contract["causal_policy"][
        "contact_material_may_be_primary_without_simulator_contact"
    ] is False
    assert not any(contract["proof_boundaries"].values())
    assert not any(contract["authority"].values())


def test_joint_residual_reports_rms_and_gripper_separately() -> None:
    result = joint_residual(
        [0.0, 0.0, 0.0, 0.0, 0.0, 2.0],
        [1.0, 0.0, 0.0, 0.0, 0.0, 2.5],
    )
    assert result["simulator_minus_physical_degrees"]["shoulder_pan"] == 1.0
    assert result["simulator_minus_physical_degrees"]["gripper"] == 0.5
    assert result["gripper_absolute_error_degrees"] == 0.5
    assert result["all_joint_rms_degrees"] == pytest.approx(
        (1.25 / 6.0) ** 0.5
    )
