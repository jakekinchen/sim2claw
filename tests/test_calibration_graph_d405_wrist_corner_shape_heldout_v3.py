from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import mujoco
import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from tools.evaluate_calibration_graph_d405_rotation_heldout_v1 import (
    body_rotation,
)
from tools.fit_current_session_pi_articulated_cad_bundle import Model


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    ROOT / "tools/evaluate_calibration_graph_d405_wrist_corner_shape_heldout_v3.py"
)
SPEC = importlib.util.spec_from_file_location(
    "evaluate_calibration_graph_d405_wrist_corner_shape_heldout_v3",
    MODULE_PATH,
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_wrist_evaluator_exposes_callable_entrypoint() -> None:
    assert callable(MODULE.evaluate)


def test_current_camera_mount_inherits_wrist_flex_one_for_one() -> None:
    manifest = json.loads(
        (
            ROOT
            / "runs/physical_excitation/20260725-follower-only-v1/"
            "simulation-canary-v1/candidate_manifest.json"
        ).read_text(encoding="utf-8")
    )
    robot = Model(manifest["candidate_config"])
    model = robot.model
    camera_id = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_BODY, "left_camera_mount"
    )
    gripper_id = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_BODY, "left_gripper"
    )
    wrist_id = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_BODY, "left_wrist"
    )
    assert int(model.body_parentid[camera_id]) == gripper_id
    assert int(model.body_parentid[gripper_id]) == wrist_id

    anchor = np.asarray(
        [5.8021978022, -85.010989011, 99.6483516484, -17.4505494505, -103.340659341, 2.3752969121],
        dtype=np.float64,
    )
    robot.set_pose(anchor, np.zeros(5), np.ones(5))
    reference = body_rotation(model, robot.data, "left_camera_mount").copy()
    perturbed = anchor.copy()
    perturbed[3] += 3.0
    robot.set_pose(perturbed, np.zeros(5), np.ones(5))
    delta = np.degrees(
        Rotation.from_matrix(
            reference.T
            @ body_rotation(model, robot.data, "left_camera_mount").copy()
        ).magnitude()
    )
    assert delta == pytest.approx(3.0, abs=1e-9)
