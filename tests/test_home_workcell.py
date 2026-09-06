from __future__ import annotations

import hashlib

import mujoco
import numpy as np
import pytest

from sim2claw.current_workcell import build_current_workcell_spec
from sim2claw.home_workcell import (
    HOME_VISUAL_CONFIG,
    HOME_WORKCELL_ID,
    build_home_workcell_spec,
    build_home_workcell_xml,
    home_workcell_summary,
    initialize_robot_poses,
)
from sim2claw.paths import REPO_ROOT

HISTORICAL_SCENE_SHA256 = (
    "4b7dd7b251c87580505a40164117cc0999f36960244a5c66c2065165afcf3e46"
)


def _body_xpos(model: mujoco.MjModel, data: mujoco.MjData, name: str) -> np.ndarray:
    body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, name)
    assert body_id >= 0
    return data.xpos[body_id].copy()


def test_home_scene_is_versioned_and_visual_only() -> None:
    summary = home_workcell_summary()
    assert summary["scene_id"] == HOME_WORKCELL_ID
    assert summary["base_workcell_id"] == "canonical_rank1_near_v1"
    assert summary["invariants"]["collision_or_contact_geometry_changed"] is False
    assert summary["authority"]["physics"] is False
    assert HOME_VISUAL_CONFIG.is_file()


def test_home_scene_replaces_hackathon_appearance() -> None:
    model = build_home_workcell_spec(include_robots=False).compile()
    for removed in ("photo_background", "fiducial_sheet", "antler_mug"):
        assert mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, removed) == -1
    for added in (
        "home_workspace_visual_environment",
        "home_small_board_frame_tag",
    ):
        assert mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, added) >= 0
    for geom_name in (
        "home_rear_backsplash",
        "home_rear_wall",
        "home_side_backsplash",
        "home_side_wall",
        "home_large_fiducial_sheet",
    ):
        geom_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, geom_name)
        assert geom_id >= 0
        assert model.geom_contype[geom_id] == 0
        assert model.geom_conaffinity[geom_id] == 0


def test_home_scene_preserves_task_and_robot_kinematics() -> None:
    canonical_model = build_current_workcell_spec().compile()
    home_model = build_home_workcell_spec().compile()
    canonical_data = mujoco.MjData(canonical_model)
    home_data = mujoco.MjData(home_model)
    initialize_robot_poses(canonical_model, canonical_data)
    initialize_robot_poses(home_model, home_data)

    assert home_model.nq == canonical_model.nq
    assert home_model.nv == canonical_model.nv
    assert home_model.nu == canonical_model.nu
    assert home_data.qpos == pytest.approx(canonical_data.qpos, abs=1e-12)
    assert home_data.ctrl == pytest.approx(canonical_data.ctrl, abs=1e-12)
    for body_name in (
        "measured_table",
        "chess_board",
        "brown_pawn_d1",
        "tan_pawn_c8",
        "left_base",
        "left_gripper",
        "right_base",
        "right_gripper",
    ):
        assert _body_xpos(home_model, home_data, body_name) == pytest.approx(
            _body_xpos(canonical_model, canonical_data, body_name),
            abs=1e-12,
        )


def test_home_xml_compiles_without_robot_assets() -> None:
    xml = build_home_workcell_xml()
    assert "home_workspace_visual_environment" in xml
    assert "photo_background" not in xml
    mujoco.MjModel.from_xml_string(xml)


def test_frozen_hackathon_scene_implementation_remains_unchanged() -> None:
    scene_path = REPO_ROOT / "src/sim2claw/scene.py"
    assert hashlib.sha256(scene_path.read_bytes()).hexdigest() == (
        HISTORICAL_SCENE_SHA256
    )
