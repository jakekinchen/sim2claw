from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from sim2claw.parking_transaction_preview import (
    _witness_distance,
    ladder_request,
)


ROOT = Path(__file__).resolve().parents[1]


def test_rp01_contract_is_motion_free_and_read_conditioned() -> None:
    contract = json.loads(
        (
            ROOT / "configs/hardware/parking_transaction_recovery_v1.json"
        ).read_text(encoding="utf-8")
    )
    assert contract["setup"]["mode"] == "no_op_current_anchor"
    assert contract["setup"]["setup_action_rows"] == 0
    assert contract["setup"]["minimum_dynamic_clearance_m"] == 0.12
    assert contract["parking_control_law"]["target_degrees"] == 91.0
    assert contract["parking_control_law"]["pure_frozen_row_tensor"] is False
    assert contract["parking_control_law"]["maximum_iterations"] == 12
    assert contract["authority"]["static_simulation"] is True
    assert contract["authority"]["camera"] is False
    assert contract["authority"]["gateway"] is False
    assert contract["authority"]["torque"] is False
    assert contract["authority"]["physical_motion"] is False
    assert contract["authority"]["physical_task_attempt"] is False


def test_frozen_ladder_request_never_steps_more_than_five_degrees() -> None:
    assert ladder_request(99.47252747252747) == 94.47252747252747
    assert ladder_request(94.47252747252747) == 91.0
    assert ladder_request(91.4) == 91.0
    assert ladder_request(90.8) == 91.0


def test_witness_distance_recovers_separated_box_pair(monkeypatch) -> None:
    def fake_distance(model, data, first, second, limit, witness):
        witness[:] = np.asarray([0.0, 0.0, 0.2, 0.0, 0.0, 0.0])
        return 0.0

    monkeypatch.setattr(
        "sim2claw.parking_transaction_preview.mujoco.mj_geomDistance",
        fake_distance,
    )
    distance, raw, witness = _witness_distance(
        object(), object(), 1, 2, limit_m=1.0
    )
    assert raw == 0.0
    assert witness == 0.2
    assert distance == 0.2
