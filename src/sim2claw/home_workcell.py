"""Post-hackathon home-workspace visual environment.

The canonical board, robots, pieces, joints, actuators, and task geometry come
from :mod:`sim2claw.current_workcell` unchanged. This module removes only the
fixed, non-colliding hackathon appearance bodies and replaces them with a
versioned, physical-image-referenced approximation of the current home
countertop corner and fiducial layout.

Nothing here grants metric wall, fiducial, camera, collision, physics, task, or
physical authority.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import mujoco

from .capture import load_capture_config
from .current_workcell import (
    CURRENT_WORKCELL_ID,
    build_current_workcell_spec,
    current_square_center,
    initialize_robot_poses,
)
from .paths import (
    DEFAULT_CAPTURE_CONFIG,
    DEFAULT_EXTERNAL_ROOT,
    DEFAULT_SO101_MASS_PROFILE,
    REPO_ROOT,
)
from .scene import scene_geometry

HOME_WORKCELL_ID = "home_corner_rank1_near_visual_v1"
HOME_VISUAL_CONFIG = REPO_ROOT / "configs" / "scenes" / "home_workspace_visual_v1.json"


def _load_home_visual_config(path: Path = HOME_VISUAL_CONFIG) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload["scene_id"] != HOME_WORKCELL_ID:
        raise ValueError("home visual config scene_id does not match runtime")
    if payload["base_workcell_id"] != CURRENT_WORKCELL_ID:
        raise ValueError("home visual config does not bind the canonical workcell")
    return payload


def _yaw_quaternion(degrees: float) -> list[float]:
    half_angle = math.radians(degrees) / 2.0
    return [math.cos(half_angle), 0.0, 0.0, math.sin(half_angle)]


def _add_box(
    body: mujoco.MjsBody,
    *,
    name: str,
    size: tuple[float, float, float],
    pos: tuple[float, float, float],
    rgba: tuple[float, float, float, float],
    group: int = 0,
) -> mujoco.MjsGeom:
    return body.add_geom(
        name=name,
        type=mujoco.mjtGeom.mjGEOM_BOX,
        size=size,
        pos=pos,
        rgba=rgba,
        contype=0,
        conaffinity=0,
        group=group,
    )


def _add_marker_pattern(
    body: mujoco.MjsBody,
    *,
    prefix: str,
    center_xy: tuple[float, float],
    black_boundary_side: float,
    z: float,
) -> None:
    half = black_boundary_side / 2.0
    _add_box(
        body,
        name=f"{prefix}_black_boundary",
        size=(half, half, 0.0006),
        pos=(center_xy[0], center_xy[1], z),
        rgba=(0.025, 0.025, 0.025, 1.0),
    )
    pattern = (
        "110011",
        "100101",
        "001100",
        "011010",
        "101101",
        "110011",
    )
    module = black_boundary_side / 7.5
    for row, bits in enumerate(pattern):
        for column, bit in enumerate(bits):
            if bit != "1":
                continue
            x = center_xy[0] + ((column - 2.5) * module)
            y = center_xy[1] + ((2.5 - row) * module)
            _add_box(
                body,
                name=f"{prefix}_white_{row}_{column}",
                size=(module * 0.43, module * 0.43, 0.0007),
                pos=(x, y, z + 0.0007),
                rgba=(0.985, 0.985, 0.975, 1.0),
            )


def _replace_hackathon_visuals(
    spec: mujoco.MjSpec,
    *,
    config_path: Path,
    visual_config_path: Path,
    board_center_in_table_frame_xy_m: tuple[float, float] | None,
    board_yaw_relative_to_table_degrees: float | None,
) -> None:
    visual_config = _load_home_visual_config(visual_config_path)
    for body_name in visual_config["removed_hackathon_visual_bodies"]:
        body = spec.body(body_name)
        if body is None:
            raise ValueError(f"canonical workcell lacks visual body {body_name}")
        spec.delete(body)

    capture = load_capture_config(config_path)
    if board_center_in_table_frame_xy_m is not None:
        capture["simulation_estimates"]["board"]["center_in_table_frame_xy_m"] = list(
            board_center_in_table_frame_xy_m
        )
    if board_yaw_relative_to_table_degrees is not None:
        capture["simulation_estimates"]["board"]["yaw_relative_to_table_degrees"] = (
            float(board_yaw_relative_to_table_degrees)
        )
    geometry = scene_geometry(capture)
    board = capture["simulation_estimates"]["board"]
    board_local_x, board_local_y = (
        float(value) for value in board["center_in_table_frame_xy_m"]
    )
    board_half = geometry.board_total_side / 2.0
    table_top = geometry.table_top
    home = visual_config["home_visuals"]

    environment = spec.worldbody.add_body(
        name="home_workspace_visual_environment",
        pos=(geometry.table_center[0], geometry.table_center[1], 0.0),
        quat=_yaw_quaternion(geometry.table_yaw_degrees),
    )
    stone = (0.82, 0.81, 0.78, 1.0)
    wall = (0.955, 0.95, 0.93, 1.0)

    rear = home["rear_surface"]
    rear_thickness = float(rear["thickness_m"])
    rear_y = (
        board_local_y
        - board_half
        - float(rear["board_far_edge_clearance_m"])
        - (rear_thickness / 2.0)
    )
    rear_half_x = float(rear["half_span_x_m"])
    rear_back_height = float(rear["backsplash_height_m"])
    rear_wall_height = float(rear["upper_wall_height_m"])
    _add_box(
        environment,
        name="home_rear_backsplash",
        size=(rear_half_x, rear_thickness / 2.0, rear_back_height / 2.0),
        pos=(0.0, rear_y, table_top + (rear_back_height / 2.0)),
        rgba=stone,
        group=4,
    )
    _add_box(
        environment,
        name="home_rear_wall",
        size=(rear_half_x, rear_thickness / 2.0, rear_wall_height / 2.0),
        pos=(
            0.0,
            rear_y,
            table_top + rear_back_height + (rear_wall_height / 2.0),
        ),
        rgba=wall,
        group=4,
    )

    side = home["side_surface"]
    side_thickness = float(side["thickness_m"])
    side_x = (
        board_local_x
        + board_half
        + float(side["board_side_edge_clearance_m"])
        + (side_thickness / 2.0)
    )
    side_half_y = float(side["half_span_y_m"])
    side_back_height = float(side["backsplash_height_m"])
    side_wall_height = float(side["upper_wall_height_m"])
    _add_box(
        environment,
        name="home_side_backsplash",
        size=(side_thickness / 2.0, side_half_y, side_back_height / 2.0),
        pos=(side_x, board_local_y, table_top + (side_back_height / 2.0)),
        rgba=stone,
        group=4,
    )
    _add_box(
        environment,
        name="home_side_wall",
        size=(side_thickness / 2.0, side_half_y, side_wall_height / 2.0),
        pos=(
            side_x,
            board_local_y,
            table_top + side_back_height + (side_wall_height / 2.0),
        ),
        rgba=wall,
        group=4,
    )

    sheet = home["large_fiducial_sheet"]
    sheet_x, sheet_y = (float(value) for value in sheet["size_xy_m"])
    sheet_center_x = (
        board_local_x - board_half - float(sheet["gap_from_board_m"]) - (sheet_x / 2.0)
    )
    sheet_center_y = board_local_y + 0.01
    _add_box(
        environment,
        name="home_large_fiducial_sheet",
        size=(sheet_x / 2.0, sheet_y / 2.0, 0.001),
        pos=(sheet_center_x, sheet_center_y, table_top + 0.001),
        rgba=(0.975, 0.975, 0.96, 1.0),
    )
    _add_marker_pattern(
        environment,
        prefix="home_large_fiducial",
        center_xy=(sheet_center_x, sheet_center_y - 0.035),
        black_boundary_side=float(sheet["tag_black_boundary_side_m"]),
        z=table_top + 0.0022,
    )

    small = home["small_board_frame_tag"]
    small_inset = float(small["inset_from_near_negative_x_corner_m"])
    small_tag = environment.add_body(
        name="home_small_board_frame_tag",
        pos=(
            board_local_x - board_half + small_inset,
            board_local_y + board_half - small_inset,
            0.0,
        ),
        quat=_yaw_quaternion(float(board["yaw_relative_to_table_degrees"])),
    )
    _add_marker_pattern(
        small_tag,
        prefix="home_small_fiducial",
        center_xy=(0.0, 0.0),
        black_boundary_side=float(small["full_side_m"]),
        z=table_top + geometry.board_thickness + 0.002,
    )


def build_home_workcell_spec(
    *,
    config_path: Path = DEFAULT_CAPTURE_CONFIG,
    external_root: Path = DEFAULT_EXTERNAL_ROOT,
    mass_profile_path: Path | None = DEFAULT_SO101_MASS_PROFILE,
    scan_overlay: bool = False,
    include_robots: bool = True,
    board_center_in_table_frame_xy_m: tuple[float, float] | None = None,
    board_yaw_relative_to_table_degrees: float | None = None,
    visual_config_path: Path = HOME_VISUAL_CONFIG,
) -> mujoco.MjSpec:
    """Build the canonical task workcell with the home visual environment."""

    spec = build_current_workcell_spec(
        config_path=config_path,
        external_root=external_root,
        mass_profile_path=mass_profile_path,
        scan_overlay=scan_overlay,
        include_robots=include_robots,
        board_center_in_table_frame_xy_m=board_center_in_table_frame_xy_m,
        board_yaw_relative_to_table_degrees=board_yaw_relative_to_table_degrees,
        include_visual_props=True,
    )
    _replace_hackathon_visuals(
        spec,
        config_path=config_path,
        visual_config_path=visual_config_path,
        board_center_in_table_frame_xy_m=board_center_in_table_frame_xy_m,
        board_yaw_relative_to_table_degrees=board_yaw_relative_to_table_degrees,
    )
    return spec


def build_home_workcell_xml(
    *,
    config_path: Path = DEFAULT_CAPTURE_CONFIG,
    external_root: Path = DEFAULT_EXTERNAL_ROOT,
    scan_overlay: bool = False,
    board_center_in_table_frame_xy_m: tuple[float, float] | None = None,
    board_yaw_relative_to_table_degrees: float | None = None,
    visual_config_path: Path = HOME_VISUAL_CONFIG,
) -> str:
    """Return robot-free XML for inspection and browser asset generation."""

    spec = build_home_workcell_spec(
        config_path=config_path,
        external_root=external_root,
        mass_profile_path=None,
        scan_overlay=scan_overlay,
        include_robots=False,
        board_center_in_table_frame_xy_m=board_center_in_table_frame_xy_m,
        board_yaw_relative_to_table_degrees=board_yaw_relative_to_table_degrees,
        visual_config_path=visual_config_path,
    )
    return spec.to_xml()


def home_workcell_summary(
    visual_config_path: Path = HOME_VISUAL_CONFIG,
) -> dict[str, Any]:
    """Return the frozen version and evidence boundaries for this appearance."""

    return _load_home_visual_config(visual_config_path)


__all__ = [
    "HOME_VISUAL_CONFIG",
    "HOME_WORKCELL_ID",
    "build_home_workcell_spec",
    "build_home_workcell_xml",
    "current_square_center",
    "home_workcell_summary",
    "initialize_robot_poses",
]
