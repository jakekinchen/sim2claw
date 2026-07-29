from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from sim2claw.canonical_seeded_action_static import (
    CanonicalSeededActionStaticError,
)
from sim2claw.canonical_seeded_action_static_v2 import (
    CanonicalSeededActionStaticV2Error,
    enumerate_and_freeze,
)
from sim2claw.paths import REPO_ROOT


CONTRACT = (
    REPO_ROOT
    / "configs/evaluations/canonical_seeded_action_static_v2.json"
)


def test_v2_contract_binds_calibrated_range_gate() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["gates"]["minimum_model_joint_margin_rad"] == 0.0
    assert contract["range_policy"] == {
        "source": "candidate_manifest.calibrated_body_ranges",
        "physical_to_model_transform": (
            "candidate_manifest.physical_adapter.joint_transform"
        ),
        "apply_to_joint_ranges": True,
        "apply_to_actuator_ctrlranges": True,
        "stock_model_range_is_authority": False,
    }
    assert contract["authority"]["dynamic_simulation"] is False
    assert contract["authority"]["physical_motion"] is False


def test_v2_compiler_has_nonnegative_model_margin(tmp_path: Path) -> None:
    receipt = enumerate_and_freeze(CONTRACT, tmp_path / "v2")
    assert receipt["calibrated_model_ranges_applied"] is True
    assert receipt["model_joint_margin_gate_passed"] is True
    assert receipt["minimum_selected_model_joint_margin_rad"] >= 0.0
    assert receipt["v1_defect_reused_as_success_evidence"] is False
    assert receipt["dynamic_simulation_executed"] is False
    assert receipt["physical_motion"] is False


def test_v2_compiler_refuses_output_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "v2"
    output.mkdir()
    with pytest.raises(
        CanonicalSeededActionStaticError,
        match="immutable output directory already exists",
    ):
        enumerate_and_freeze(CONTRACT, output)


def test_v2_compiler_has_no_hardware_dependencies() -> None:
    source = inspect.getsource(
        __import__(
            "sim2claw.canonical_seeded_action_static_v2",
            fromlist=["unused"],
        )
    )
    for forbidden in (
        "SO101PhysicalGateway",
        "serial",
        "camera.open",
        ".set_torque(",
        "write_goal",
    ):
        assert forbidden not in source
