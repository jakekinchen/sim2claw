from __future__ import annotations

import numpy as np

from sim2claw.observable_registration_planar_array_residual_motion_ownership_attribution import _translation_measurement
from sim2claw.observable_registration_planar_array_residual_motion_ownership_attribution_identity_reproduction_v2 import (
    DEFAULT_OUTPUT,
    evaluate_once,
    load_identity_reproduction_v2_contract,
)


def test_or124c_contract_binds_or124b_quarantine_and_new_output() -> None:
    contract = load_identity_reproduction_v2_contract()

    assert contract["experiment_id"] == "OR124C_IDENTITY_BOUND_RESIDUAL_MOTION_OWNERSHIP_REPRODUCTION_V2"
    assert contract["sources"]["or125_prerequisite_audit"]["status"] == "NOT_RUN_OR124B_PREREQUISITE_IDENTITY_DRIFT"
    assert contract["claim_limits"]["identity_bound_reproduction_only"] is True
    assert DEFAULT_OUTPUT.name.endswith("identity_reproduction_v2")


def test_or124c_final_measurement_logic_recovers_known_translation() -> None:
    target = np.zeros((32, 32), dtype=bool)
    target[8:20, 10] = True
    target[19, 10:19] = True
    edges = np.zeros_like(target)
    edges[8:20, 14] = True
    edges[19, 14:23] = True

    result = _translation_measurement(target, edges, radius=8)

    assert result["best_translation_xy"] == [4, 0]
    assert result["best_support_fraction"] == 1.0


def test_or124c_one_shot_symbol_is_callable() -> None:
    assert callable(evaluate_once)
