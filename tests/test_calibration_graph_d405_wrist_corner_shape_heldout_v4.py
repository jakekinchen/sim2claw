from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import mujoco
import numpy as np

from tools.fit_current_session_pi_articulated_cad_bundle import Model


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    ROOT / "tools/evaluate_calibration_graph_d405_wrist_corner_shape_heldout_v4.py"
)
SPEC = importlib.util.spec_from_file_location(
    "evaluate_calibration_graph_d405_wrist_corner_shape_heldout_v4",
    MODULE_PATH,
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_v4_evaluator_exposes_callable_entrypoint() -> None:
    assert callable(MODULE.evaluate)


def test_copied_body_rotation_does_not_alias_live_mujoco_buffer() -> None:
    manifest = json.loads(
        (
            ROOT
            / "runs/physical_excitation/20260725-follower-only-v1/"
            "simulation-canary-v1/candidate_manifest.json"
        ).read_text(encoding="utf-8")
    )
    robot = Model(manifest["candidate_config"])
    anchor = np.asarray(
        [5.8021978022, -85.010989011, 99.6483516484, -17.4505494505, -103.340659341, 2.3752969121],
        dtype=np.float64,
    )
    robot.set_pose(anchor, np.zeros(5), np.ones(5))
    copied = MODULE.copied_body_rotation(
        robot.model, robot.data, "left_camera_mount"
    )
    before = copied.copy()
    anchor[3] += 3.0
    robot.set_pose(anchor, np.zeros(5), np.ones(5))
    assert np.array_equal(copied, before)
    assert not np.shares_memory(copied, robot.data.xmat)
