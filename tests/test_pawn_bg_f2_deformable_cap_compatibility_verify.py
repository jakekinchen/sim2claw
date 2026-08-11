from __future__ import annotations

import numpy as np

from sim2claw.pawn_bg_f2_deformable_cap_compatibility_verify import (
    _compatibility_gate,
)
from sim2claw.pawn_bg_f2_deformable_cap_verify import _action_gates


def test_initial_state_is_not_an_applied_action_step() -> None:
    arrays = {
        "source_indices": np.zeros((2, 6), dtype=np.int32),
        "requested_action": np.zeros((2, 6), dtype=np.float64),
        "applied_ctrl": np.vstack(
            [np.full(6, 0.001, dtype=np.float64), np.zeros(6, dtype=np.float64)]
        ),
        "phase": np.asarray([0, 1], dtype=np.int8),
        "time": np.asarray([0.0, 0.00225], dtype=np.float64),
    }
    source = {
        "actions": np.zeros((1, 6), dtype=np.float64),
        "timestamps": np.asarray([0.0], dtype=np.float64),
    }
    contract = {
        "action_invariance": {"per_joint_zoh_delay_seconds": [0.11] * 6}
    }
    gates, metrics = _action_gates(
        arrays,
        source,
        contract,
        applied_control_excluded_phase_codes=frozenset({0}),
    )
    assert gates["applied_ctrl_equals_requested_action"] is True
    assert metrics["maximum_applied_minus_requested_absolute_rad"] == 0.0


def test_compatibility_gate_recomputes_reference_without_producer_booleans() -> None:
    contract = {
        "rigid_compatibility_reference": {
            "compiled_model_sha256": "model",
            "final_target_distance_m": 0.007,
            "maximum_piece_rise_m": 0.042,
            "piece_lifted": True,
            "qualified_bilateral_contact_observed": True,
            "upright": True,
        },
        "rigid_compatibility_tolerances": {
            "final_target_distance_absolute_m": 1e-12,
            "maximum_piece_rise_absolute_m": 1e-12,
        },
    }
    strict = {
        "metrics": {
            "final_center_distance_m": 0.007,
            "maximum_rise_m": 0.042,
            "maximum_qualified_contact_dwell_seconds": 0.1,
            "original_reward_gate_results_recomputed": {
                "piece_lifted": True,
                "upright": True,
            },
        }
    }
    result = _compatibility_gate(
        contract=contract,
        metadata={"compiled_model_sha256": "model"},
        strict_verdict=strict,
    )
    assert result["passed"] is True
    assert all(result["checks"].values())
