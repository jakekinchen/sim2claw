from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from sim2claw.elbow_telemetry_probe import (
    ElbowTelemetryProbeError,
    _trajectory,
    load_contract,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "configs/evaluations/elbow_telemetry_probe_v2.json"


def test_contract_is_bounded_and_has_no_task_or_config_authority() -> None:
    contract = load_contract(CONTRACT)
    assert contract["physical_task_attempt"] is False
    assert contract["pawn_contact"] is False
    assert contract["gain_write"] is False
    assert contract["configuration_write"] is False
    assert contract["elbow_offsets_degrees"] == [-3.0, -5.0]
    assert contract["wrist_control_offsets_degrees"] == [3.0, -3.0, 5.0, -5.0]


def test_trajectory_changes_only_declared_joint_and_returns_to_anchor() -> None:
    anchor = np.asarray([1, 2, 3, 4, 5, 6], dtype=np.float64)
    actions, phases = _trajectory(
        anchor,
        joint="elbow_flex",
        offsets=[3.0, -3.0, 5.0, -5.0],
        maximum_slew_degrees_s=10.0,
        hold_seconds=0.35,
    )
    assert actions.dtype == np.dtype("<f8")
    assert np.array_equal(actions[-1], anchor)
    assert np.array_equal(actions[:, [0, 1, 3, 4, 5]], np.repeat(
        anchor[[0, 1, 3, 4, 5]][None, :], actions.shape[0], axis=0
    ))
    assert len(phases) == 8
    assert np.max(np.abs(actions[:, 2] - anchor[2])) == 5.0


def test_contract_rejects_authority_widening(tmp_path: Path) -> None:
    changed = json.loads(CONTRACT.read_text(encoding="utf-8"))
    changed["gain_write"] = True
    path = tmp_path / "changed.json"
    path.write_text(json.dumps(changed), encoding="utf-8")
    with pytest.raises(ElbowTelemetryProbeError, match="authority widened"):
        load_contract(path)
