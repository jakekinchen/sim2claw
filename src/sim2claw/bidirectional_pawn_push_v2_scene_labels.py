"""Current-task scene placement and semantic-label contract.

This adapter is prospective and intentionally narrow.  Semantic pawn body IDs
and task square labels use the canonical operator frame, while the immutable
scene grid receives the one required 180-degree placement transform.
Historical scene-registration fits remain outside this module.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import mujoco
import numpy as np

from .board_orientation import canonical_square_center
from .paths import REPO_ROOT


CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "scenes"
    / "bidirectional_pawn_push_v2_current_task_scene_labels_v1.json"
)
CONTRACT_SCHEMA = "sim2claw.bidirectional_pawn_push_v2_current_task_scene_labels.v1"
CANONICAL_FRAME_ID = "standard_robot_near_rank1_v1"
RAW_GRID_TRANSFORM = "rotate_180"
POSITION_TOLERANCE_M = 1e-9


class CurrentTaskSceneLabelError(RuntimeError):
    """The prospective scene and semantic task labels are inconsistent."""


def load_scene_label_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    contract = json.loads(path.read_text(encoding="utf-8"))
    if contract.get("schema_version") != CONTRACT_SCHEMA:
        raise CurrentTaskSceneLabelError("unexpected current-task scene-label contract")
    if contract.get("semantic_frame", {}).get("id") != CANONICAL_FRAME_ID:
        raise CurrentTaskSceneLabelError("current-task semantic frame changed")
    placement = contract.get("raw_grid_placement", {})
    if (
        placement.get("transform") != RAW_GRID_TRANSFORM
        or placement.get("apply_exactly_once") is not True
    ):
        raise CurrentTaskSceneLabelError("current-task raw-grid placement changed")
    target = contract.get("target_resolution", {})
    if (
        target.get("resolver")
        != "sim2claw.board_orientation.canonical_square_center"
        or target.get("apply_exactly_once") is not True
    ):
        raise CurrentTaskSceneLabelError("current-task target resolver changed")
    tolerance = float(contract.get("structural_invariant", {}).get("xy_tolerance_m", -1.0))
    if tolerance != POSITION_TOLERANCE_M:
        raise CurrentTaskSceneLabelError("current-task position tolerance changed")
    return contract


def current_task_square_center(square: str) -> np.ndarray:
    """Resolve one canonical task square through the raw-grid adapter once."""

    return np.asarray(canonical_square_center(square), dtype=np.float64)


def validate_modeled_source_position(
    *,
    selected_piece_id: str,
    source_square: str,
    modeled_source_xyz: np.ndarray,
    tolerance_m: float = POSITION_TOLERANCE_M,
) -> np.ndarray:
    """Fail if a semantic body is not on its canonical source square."""

    if not selected_piece_id.endswith(f"_{source_square}"):
        raise CurrentTaskSceneLabelError(
            "selected semantic body ID and source square disagree: "
            f"{selected_piece_id} / {source_square}"
        )
    modeled = np.asarray(modeled_source_xyz, dtype=np.float64)
    if modeled.shape != (3,) or not np.all(np.isfinite(modeled)):
        raise CurrentTaskSceneLabelError("modeled source position is not finite xyz")
    expected = current_task_square_center(source_square)
    error = float(np.linalg.norm(modeled[:2] - expected[:2]))
    if error > tolerance_m:
        raise CurrentTaskSceneLabelError(
            "current-task scene/label invariant failed for "
            f"{selected_piece_id}: xy error {error:.12g} m"
        )
    return expected


def candidate_geometry(
    *,
    selected_piece_id: str,
    source_square: str,
    destination_square: str,
    modeled_source_xyz: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return source, destination, and unit direction in one canonical frame."""

    source = validate_modeled_source_position(
        selected_piece_id=selected_piece_id,
        source_square=source_square,
        modeled_source_xyz=modeled_source_xyz,
    )
    destination = current_task_square_center(destination_square)
    delta = destination - source
    planar_norm = float(np.linalg.norm(delta[:2]))
    if planar_norm <= 0.0 or abs(float(delta[2])) > POSITION_TOLERANCE_M:
        raise CurrentTaskSceneLabelError("candidate direction is not a planar move")
    direction = delta / planar_norm
    return source, destination, direction


def assert_compiled_reset_layout_alignment(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    pieces_by_square: Mapping[str, str],
) -> None:
    """Check every semantic reset-layout body in the exact compiled scene."""

    if not pieces_by_square:
        raise CurrentTaskSceneLabelError("compiled reset layout has no pawn bodies")
    for square, body_name in sorted(pieces_by_square.items()):
        body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, body_name)
        if body_id < 0:
            raise CurrentTaskSceneLabelError(
                f"compiled reset layout is missing body: {body_name}"
            )
        validate_modeled_source_position(
            selected_piece_id=body_name,
            source_square=square,
            modeled_source_xyz=np.asarray(data.xpos[body_id], dtype=np.float64),
        )
