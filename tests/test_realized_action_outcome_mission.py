from __future__ import annotations

import numpy as np

from sim2claw.realized_action_outcome_mission import (
    load_contract,
    physical_to_model,
)


def test_contract_is_write_once_and_physical_authority_false() -> None:
    contract = load_contract()
    assert contract["replay"]["one_run_only"] is True
    assert contract["replay"]["contact_model_validated"] is False
    assert contract["authority"]["simulator_replay"] is True
    assert not any(
        value
        for key, value in contract["authority"].items()
        if key != "simulator_replay"
    )


def test_joint_transform_maps_without_clipping() -> None:
    manifest = {
        "candidate_config": {
            "bindings": {"joint_names": ["a", "b"]},
            "physical_adapter": {
                "joint_transform": {
                    "joints": [
                        {
                            "simulator_joint": "a",
                            "scale": 0.1,
                            "sign": 1.0,
                            "zero_offset": 0.2,
                        },
                        {
                            "simulator_joint": "b",
                            "scale": 0.2,
                            "sign": -1.0,
                            "zero_offset": -0.3,
                        },
                    ]
                }
            },
        }
    }
    mapped = physical_to_model(np.asarray([[1.0, 2.0]]), manifest)
    np.testing.assert_allclose(mapped, [[0.3, -0.7]])


def test_contract_binds_exact_gateway_sent_tensor() -> None:
    contract = load_contract()
    sent = contract["source"]["gateway_sent"]
    assert sent["shape"] == [531, 6]
    assert sent["dtype"] == "<f4"
    assert sent["sha256"] == (
        "3b034bd965d4bf1a71591cc77f033e97f1fe8eb30aa75cb314cc529b4e40e3ef"
    )
