from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sim2claw.calibration_graph_v1 import evaluate


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = Path("configs/evaluations/calibration_graph_v1.json")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_calibration_graph_is_gauge_fixed_and_fail_closed() -> None:
    contract = json.loads((ROOT / CONTRACT).read_text(encoding="utf-8"))
    assert len(contract["variables"]["active_joint_scales"]) == 4
    assert set(contract["variables"]["fixed"]) == {
        "camera_board",
        "robot_to_board_rigid_transform",
        "physical_degree_to_mujoco_joint_signs",
        "physical_degree_to_mujoco_joint_zero_offsets",
        "jaw_reference",
        "gripper_scale",
    }
    assert contract["factors"]["untouched_composite_heldout_required"]
    assert not contract["authority"]["mapping_approval"]
    for binding in [
        *contract["sources"].values(),
        contract["implementation"],
    ]:
        assert _sha(ROOT / binding["path"]) == binding["sha256"]


def test_calibration_graph_refuses_output_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "existing"
    output.mkdir()
    try:
        evaluate((ROOT / CONTRACT).resolve(), output.resolve())
    except Exception as error:
        assert "already exists" in str(error)
    else:
        raise AssertionError("calibration graph overwrote output")


def test_calibration_graph_source_has_no_hardware_surface() -> None:
    source = (
        ROOT / "src/sim2claw/calibration_graph_v1.py"
    ).read_text(encoding="utf-8")
    for forbidden in ("import serial", "dynamixel_sdk", "mujoco"):
        assert forbidden not in source.lower()
