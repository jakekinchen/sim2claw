from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from sim2claw.physical_fk_frame import (
    CONTRACT_PATH,
    PhysicalFKFrameError,
    load_physical_fk_contract,
    physical_fk_base_from_wrist,
)

MANIFEST = Path(
    "runs/physical_excitation/20260725-follower-only-v1/"
    "simulation-canary-v1/candidate_manifest.json"
)
pytestmark = pytest.mark.skipif(
    not MANIFEST.is_file(), reason="ignored bound candidate manifest is absent"
)


def test_contract_binds_candidate_model_adapter_and_frames() -> None:
    contract, _model = load_physical_fk_contract()

    assert contract["compiled_kinematic_model_sha256"] == (
        "0814b790d7eae6d3175d4abfcdc32aa72c986475509dca703c491a1efffc05a9"
    )
    assert contract["frames"]["base"]["mujoco_body"] == "left_base"
    assert contract["frames"]["wrist"]["mujoco_body"] == "left_gripper"
    assert contract["frames"]["d405_depth_optical"]["axes"] == {
        "x": "right",
        "y": "down",
        "z": "forward",
    }
    assert contract["unknown_to_fit"] == "wrist_from_d405_depth_optical"


def test_fk_is_deterministic_at_two_frozen_poses() -> None:
    zero = physical_fk_base_from_wrist([0, 0, 0, 0, 0, 0])
    observed = physical_fk_base_from_wrist([10, -56.5, 89.8, 0.2, -75.1, 3.1])

    np.testing.assert_allclose(
        zero[:3, 3], [0.2932345, -0.0001778, 0.23437], atol=1e-9
    )
    np.testing.assert_allclose(
        observed,
        [
            [-0.055744000, 0.567886330, -0.821217223, 0.155542220],
            [-0.982997550, 0.112906930, 0.144802753, -0.020759120],
            [0.174952620, 0.815326400, 0.551936985, 0.098640020],
            [0.0, 0.0, 0.0, 1.0],
        ],
        atol=1e-8,
    )
    np.testing.assert_allclose(
        observed[:3, :3].T @ observed[:3, :3], np.eye(3), atol=1e-12
    )
    assert np.linalg.det(observed[:3, :3]) == pytest.approx(1.0)


def test_compiled_model_hash_drift_fails_closed(tmp_path: Path) -> None:
    value = json.loads(CONTRACT_PATH.read_text())
    value["compiled_kinematic_model_sha256"] = "0" * 64
    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps(value))

    with pytest.raises(PhysicalFKFrameError, match="model hash drifted"):
        load_physical_fk_contract(changed)
