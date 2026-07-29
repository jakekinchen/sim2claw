"""Canonical current/future chess workcell runtime.

This is the only scene-construction surface for active Studio, recording, and
new transfer work. Standard chess labels are intrinsic: rank 1 is the near
robot/operator edge and files run left-to-right from that view. The public API
has no legacy-frame selector or square-transform option.

Frozen experiments continue to use :mod:`sim2claw.scene` through the explicit
read-only legacy boundary. The immutable scene implementation is bound once
inside this module so its old selector cannot leak into active call sites.
The fixed physical index calculation defines the canonical workcell's axes.
"""

from __future__ import annotations

import math
from pathlib import Path

import mujoco

from .capture import load_capture_config
from .paths import (
    DEFAULT_CAPTURE_CONFIG,
    DEFAULT_EXTERNAL_ROOT,
    DEFAULT_SO101_MASS_PROFILE,
)
from .scene import (
    CURRENT_TASK_LAYOUT_ID,
    CURRENT_TASK_PIECE_LAYOUT,
    ROBOT_JOINTS,
    build_scene_spec,
    build_scene_xml,
    initialize_robot_poses,
    scene_geometry,
    scene_summary,
)


CURRENT_WORKCELL_ID = "canonical_rank1_near_v1"
BOARD_FILES = "abcdefgh"
BOARD_RANKS = "12345678"
_FROZEN_PHYSICAL_LAYOUT = "rotate_180"


def _validate_square(square: str) -> str:
    normalized = str(square).lower()
    if (
        len(normalized) != 2
        or normalized[0] not in BOARD_FILES
        or normalized[1] not in BOARD_RANKS
    ):
        raise ValueError(f"invalid chess square: {square}")
    return normalized


def _canonical_physical_indices(square: str) -> tuple[int, int]:
    """Return intrinsic workcell indices for a standard canonical square."""

    normalized = _validate_square(square)
    # The measured workcell's positive local axes point toward canonical a8.
    # Defining both canonical axes from the near/operator view therefore makes
    # rank 1 and file a the high-index physical edge. This is fixed geometry,
    # not a caller-selectable compatibility transform.
    return (
        7 - BOARD_FILES.index(normalized[0]),
        7 - BOARD_RANKS.index(normalized[1]),
    )


def current_square_center(
    square: str,
    *,
    config_path: Path = DEFAULT_CAPTURE_CONFIG,
    board_center_in_table_frame_xy_m: tuple[float, float] | None = None,
    board_yaw_relative_to_table_degrees: float | None = None,
) -> tuple[float, float, float]:
    """Return a canonical square center in the current world frame."""

    file_index, rank_index = _canonical_physical_indices(square)
    config = load_capture_config(config_path)
    if board_center_in_table_frame_xy_m is not None:
        config["simulation_estimates"]["board"][
            "center_in_table_frame_xy_m"
        ] = list(board_center_in_table_frame_xy_m)
    if board_yaw_relative_to_table_degrees is not None:
        config["simulation_estimates"]["board"][
            "yaw_relative_to_table_degrees"
        ] = float(board_yaw_relative_to_table_degrees)
    geometry = scene_geometry(config)
    local_x = (file_index - 3.5) * geometry.square_size
    local_y = (rank_index - 3.5) * geometry.square_size
    angle = math.radians(geometry.board_yaw_degrees)
    dx = (math.cos(angle) * local_x) - (math.sin(angle) * local_y)
    dy = (math.sin(angle) * local_x) + (math.cos(angle) * local_y)
    return (
        geometry.board_center[0] + dx,
        geometry.board_center[1] + dy,
        geometry.table_top + geometry.board_thickness + 0.001,
    )


def build_current_workcell_xml(
    *,
    config_path: Path = DEFAULT_CAPTURE_CONFIG,
    external_root: Path = DEFAULT_EXTERNAL_ROOT,
    scan_overlay: bool = False,
    board_center_in_table_frame_xy_m: tuple[float, float] | None = None,
    board_yaw_relative_to_table_degrees: float | None = None,
    include_visual_props: bool = True,
) -> str:
    """Build canonical current-task XML with no frame-selection surface."""

    return build_scene_xml(
        config_path=config_path,
        external_root=external_root,
        scan_overlay=scan_overlay,
        piece_layout=CURRENT_TASK_PIECE_LAYOUT,
        piece_square_transform=_FROZEN_PHYSICAL_LAYOUT,
        board_center_in_table_frame_xy_m=board_center_in_table_frame_xy_m,
        board_yaw_relative_to_table_degrees=board_yaw_relative_to_table_degrees,
        include_visual_props=include_visual_props,
    )


def build_current_workcell_spec(
    *,
    config_path: Path = DEFAULT_CAPTURE_CONFIG,
    external_root: Path = DEFAULT_EXTERNAL_ROOT,
    mass_profile_path: Path | None = DEFAULT_SO101_MASS_PROFILE,
    scan_overlay: bool = False,
    include_robots: bool = True,
    board_center_in_table_frame_xy_m: tuple[float, float] | None = None,
    board_yaw_relative_to_table_degrees: float | None = None,
    include_visual_props: bool = True,
) -> mujoco.MjSpec:
    """Build the one canonical current/future workcell specification."""

    return build_scene_spec(
        config_path=config_path,
        external_root=external_root,
        scan_overlay=scan_overlay,
        piece_layout=CURRENT_TASK_PIECE_LAYOUT,
        piece_square_transform=_FROZEN_PHYSICAL_LAYOUT,
        include_robots=include_robots,
        mass_profile_path=mass_profile_path,
        board_center_in_table_frame_xy_m=board_center_in_table_frame_xy_m,
        board_yaw_relative_to_table_degrees=board_yaw_relative_to_table_degrees,
        include_visual_props=include_visual_props,
    )


__all__ = [
    "CURRENT_TASK_LAYOUT_ID",
    "CURRENT_TASK_PIECE_LAYOUT",
    "CURRENT_WORKCELL_ID",
    "ROBOT_JOINTS",
    "build_current_workcell_spec",
    "build_current_workcell_xml",
    "current_square_center",
    "initialize_robot_poses",
    "scene_summary",
]
