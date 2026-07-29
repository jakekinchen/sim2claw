from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path

import mujoco
import numpy as np
import pytest

from sim2claw.current_workcell import (
    build_current_workcell_spec,
    build_current_workcell_xml,
    current_square_center,
)
from sim2claw.paths import REPO_ROOT
from sim2claw.scene import board_square_center


HISTORICAL_SCENE_SHA256 = (
    "4b7dd7b251c87580505a40164117cc0999f36960244a5c66c2065165afcf3e46"
)
ACTIVE_SCENE_CALLERS = (
    "src/sim2claw/studio_live.py",
    "src/sim2claw/studio_assets.py",
    "src/sim2claw/teleop_recording.py",
)


def _body_position(model: mujoco.MjModel, name: str) -> np.ndarray:
    body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, name)
    assert body_id >= 0
    return model.body_pos[body_id].copy()


def test_public_current_workcell_api_has_no_frame_selector() -> None:
    forbidden = {
        "piece_square_transform",
        "current_scene_piece_square_transform",
        "frame",
        "transform",
    }
    for function in (
        build_current_workcell_xml,
        build_current_workcell_spec,
        current_square_center,
    ):
        assert forbidden.isdisjoint(inspect.signature(function).parameters)


def test_all_canonical_square_centers_are_unique_and_rank1_near() -> None:
    centers = {
        square: current_square_center(square)
        for rank in "12345678"
        for file_name in "abcdefgh"
        for square in (f"{file_name}{rank}",)
    }
    assert len({tuple(np.round(value, 12)) for value in centers.values()}) == 64
    assert centers["b1"] == pytest.approx(board_square_center("g8"), abs=1e-12)
    assert centers["b8"] == pytest.approx(board_square_center("g1"), abs=1e-12)


def test_current_piece_names_and_positions_are_canonical() -> None:
    model = build_current_workcell_spec(include_robots=False).compile()
    for square in ("b1", "a2", "e2", "b7", "a8", "e8"):
        color = "brown" if int(square[1]) <= 2 else "tan"
        assert _body_position(model, f"{color}_pawn_{square}") == pytest.approx(
            current_square_center(square),
            abs=1e-9,
        )


def test_active_callers_use_only_the_canonical_builder() -> None:
    for relative_path in ACTIVE_SCENE_CALLERS:
        source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        assert "build_current_workcell_spec" in source
        assert "build_scene_spec" not in source
        assert "piece_square_transform" not in source
        assert "board_orientation" not in source


def test_frozen_scene_implementation_hash_is_unchanged() -> None:
    scene_path = REPO_ROOT / "src/sim2claw/scene.py"
    assert hashlib.sha256(scene_path.read_bytes()).hexdigest() == (
        HISTORICAL_SCENE_SHA256
    )


def test_migration_manifest_classifies_every_production_scene_caller() -> None:
    manifest = json.loads(
        (
            REPO_ROOT
            / "configs/migrations/current_workcell_hard_cutover_v1.json"
        ).read_text(encoding="utf-8")
    )
    actual = {
        str(path.relative_to(REPO_ROOT))
        for path in (REPO_ROOT / "src/sim2claw").rglob("*.py")
        if "build_scene_spec(" in path.read_text(encoding="utf-8")
    }
    classified = {
        entry["path"]
        for entry in manifest["production_scene_caller_classification"]
    }
    assert actual == classified
    assert manifest["authority"]["physical_authority"] is False
