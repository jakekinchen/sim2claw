from __future__ import annotations

import math
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

import mujoco

from .capture import capture_directory, load_capture_config
from .mass_profile import (
    apply_so101_mass_profile,
    load_so101_mass_profile,
    mass_profile_summary,
)
from .paths import (
    DEFAULT_CAPTURE_CONFIG,
    DEFAULT_EXTERNAL_ROOT,
    DEFAULT_SO101_MASS_PROFILE,
    SO101_MODEL_PATH,
)


ROBOT_JOINTS = (
    "shoulder_pan",
    "shoulder_lift",
    "elbow_flex",
    "wrist_flex",
    "wrist_roll",
    "gripper",
)

STUDIO_CAMERAS = (
    "studio_overview",
    "studio_left",
    "studio_right",
)

CURRENT_TASK_PIECE_LAYOUT = "sparse_two_sided_pawns"
CURRENT_TASK_LAYOUT_ID = "two_sided_sparse_pawns_rows_1_2_7_8_v1"

TELEOP_PAWN_SOURCE_SQUARES = (
    "a2",
    "b1",
    "c2",
    "d1",
    "e2",
    "f1",
    "g2",
    "h1",
)

TELEOP_TAN_PAWN_SQUARES = (
    "a8",
    "b7",
    "c8",
    "d7",
    "e8",
    "f7",
    "g8",
    "h7",
)


@dataclass(frozen=True)
class SceneGeometry:
    table_center: tuple[float, float, float]
    table_length: float
    table_width: float
    table_height: float
    table_yaw_degrees: float
    board_center: tuple[float, float]
    board_side: float
    board_frame_width: float
    board_thickness: float
    board_yaw_degrees: float
    floor_shift: float

    @property
    def table_top(self) -> float:
        return self.table_center[2] + (self.table_height / 2.0)

    @property
    def square_size(self) -> float:
        return self.board_side / 8.0

    @property
    def board_total_side(self) -> float:
        return self.board_side + (2.0 * self.board_frame_width)


def _rotate_xy(x: float, y: float, degrees: float) -> tuple[float, float]:
    angle = math.radians(degrees)
    return (
        (math.cos(angle) * x) - (math.sin(angle) * y),
        (math.sin(angle) * x) + (math.cos(angle) * y),
    )


def _table_to_world(
    geometry: SceneGeometry, x: float, y: float, z: float
) -> tuple[float, float, float]:
    offset_x, offset_y = _rotate_xy(x, y, geometry.table_yaw_degrees)
    return (
        geometry.table_center[0] + offset_x,
        geometry.table_center[1] + offset_y,
        z,
    )


def scene_geometry(config: dict[str, Any]) -> SceneGeometry:
    measurements = config["roomplan_measurements"]
    table = measurements["table"]
    floor_shift = -float(measurements["floor_height_m"])
    raw_x, raw_y, raw_z = (float(value) for value in table["center_xyz_m"])
    table_center = (raw_x, -raw_z, raw_y + floor_shift)
    table_yaw = float(table["yaw_degrees_after_z_up_conversion"])
    board = config["simulation_estimates"]["board"]
    board_local_x, board_local_y = (
        float(value) for value in board["center_in_table_frame_xy_m"]
    )
    board_offset_x, board_offset_y = _rotate_xy(
        board_local_x, board_local_y, table_yaw
    )
    return SceneGeometry(
        table_center=table_center,
        table_length=float(table["length_m"]),
        table_width=float(table["width_m"]),
        table_height=float(table["height_m"]),
        table_yaw_degrees=table_yaw,
        board_center=(
            table_center[0] + board_offset_x,
            table_center[1] + board_offset_y,
        ),
        board_side=float(board["side_m"]),
        board_frame_width=float(board["frame_width_m"]),
        board_thickness=float(board["thickness_m"]),
        board_yaw_degrees=table_yaw
        + float(board["yaw_relative_to_table_degrees"]),
        floor_shift=floor_shift,
    )


def board_square_center(
    square: str,
    *,
    config_path: Path = DEFAULT_CAPTURE_CONFIG,
) -> tuple[float, float, float]:
    """Return the simulation-only world-frame center of one board square."""

    if len(square) != 2 or square[0] not in "abcdefgh" or square[1] not in "12345678":
        raise ValueError(f"invalid chess square: {square}")
    geometry = scene_geometry(load_capture_config(config_path))
    file_index = ord(square[0]) - ord("a")
    rank_index = int(square[1]) - 1
    local_x = (file_index - 3.5) * geometry.square_size
    local_y = (rank_index - 3.5) * geometry.square_size
    dx, dy = _rotate_xy(local_x, local_y, geometry.board_yaw_degrees)
    return (
        geometry.board_center[0] + dx,
        geometry.board_center[1] + dy,
        geometry.table_top + geometry.board_thickness + 0.001,
    )


def _format_vector(values: tuple[float, ...] | list[float]) -> str:
    return " ".join(f"{value:.9g}" for value in values)


def _piece_geoms(kind: str, rgba: str) -> list[str]:
    base = [
        f'<geom type="cylinder" size="0.014 0.004" pos="0 0 0.004" rgba="{rgba}"/>',
        f'<geom type="cylinder" size="0.0105 0.003" pos="0 0 0.011" rgba="{rgba}"/>',
    ]
    if kind == "pawn":
        return base + [
            f'<geom type="capsule" size="0.006 0.010" pos="0 0 0.022" rgba="{rgba}"/>',
            f'<geom type="sphere" size="0.008" pos="0 0 0.039" rgba="{rgba}"/>',
        ]
    if kind == "rook":
        return base + [
            f'<geom type="cylinder" size="0.007 0.013" pos="0 0 0.025" rgba="{rgba}"/>',
            f'<geom type="cylinder" size="0.010 0.005" pos="0 0 0.043" rgba="{rgba}"/>',
        ]
    if kind == "knight":
        return base + [
            f'<geom type="capsule" size="0.007 0.014" pos="0 0 0.027" euler="0 18 0" rgba="{rgba}"/>',
            f'<geom type="ellipsoid" size="0.009 0.006 0.011" pos="0.005 0 0.047" euler="0 24 0" rgba="{rgba}"/>',
        ]
    if kind == "bishop":
        return base + [
            f'<geom type="capsule" size="0.0065 0.015" pos="0 0 0.028" rgba="{rgba}"/>',
            f'<geom type="ellipsoid" size="0.008 0.008 0.011" pos="0 0 0.051" rgba="{rgba}"/>',
        ]
    if kind == "queen":
        return base + [
            f'<geom type="capsule" size="0.007 0.019" pos="0 0 0.032" rgba="{rgba}"/>',
            f'<geom type="cylinder" size="0.010 0.003" pos="0 0 0.054" rgba="{rgba}"/>',
            f'<geom type="sphere" size="0.006" pos="0 0 0.064" rgba="{rgba}"/>',
        ]
    if kind == "king":
        return base + [
            f'<geom type="capsule" size="0.0075 0.020" pos="0 0 0.033" rgba="{rgba}"/>',
            f'<geom type="sphere" size="0.008" pos="0 0 0.058" rgba="{rgba}"/>',
            f'<geom type="box" size="0.0025 0.007 0.002" pos="0 0 0.070" rgba="{rgba}"/>',
            f'<geom type="box" size="0.007 0.0025 0.002" pos="0 0 0.070" rgba="{rgba}"/>',
        ]
    raise ValueError(f"unknown chess piece kind: {kind}")


def _piece_bodies(
    geometry: SceneGeometry,
    *,
    piece_layout: str = "standard",
) -> list[str]:
    back_rank = ["rook", "knight", "bishop", "queen", "king", "bishop", "knight", "rook"]
    colors = {
        "white": "0.91 0.79 0.58 1",
        "black": "0.18 0.075 0.025 1",
        "brown": "0.34 0.13 0.045 1",
        "tan": "0.84 0.68 0.43 1",
    }
    pieces: list[tuple[str, str, int, int]] = []
    if piece_layout in {CURRENT_TASK_PIECE_LAYOUT, "teleop_pawns"}:
        for square in TELEOP_PAWN_SOURCE_SQUARES:
            pieces.append(
                (
                    "brown",
                    "pawn",
                    ord(square[0]) - ord("a"),
                    int(square[1]) - 1,
                )
            )
        for square in TELEOP_TAN_PAWN_SQUARES:
            pieces.append(
                (
                    "tan",
                    "pawn",
                    ord(square[0]) - ord("a"),
                    int(square[1]) - 1,
                )
            )
    elif piece_layout == "standard":
        for file_index, kind in enumerate(back_rank):
            # The photo has white at the window side and black at the near side.
            pieces.extend(
                [
                    ("white", kind, file_index, 0),
                    ("white", "pawn", file_index, 1),
                    ("black", "pawn", file_index, 6),
                    ("black", kind, file_index, 7),
                ]
            )
    else:
        raise ValueError(f"unknown chess piece layout: {piece_layout}")

    board_top = geometry.table_top + geometry.board_thickness + 0.001
    bodies: list[str] = []
    for color, kind, file_index, rank_index in pieces:
        local_x = (file_index - 3.5) * geometry.square_size
        local_y = (rank_index - 3.5) * geometry.square_size
        dx, dy = _rotate_xy(local_x, local_y, geometry.board_yaw_degrees)
        square = f"{chr(ord('a') + file_index)}{rank_index + 1}"
        name = f"{color}_{kind}_{square}"
        bodies.append(
            f'<body name="{name}" pos="{geometry.board_center[0] + dx:.9g} '
            f'{geometry.board_center[1] + dy:.9g} {board_top:.9g}" '
            f'euler="0 0 {geometry.board_yaw_degrees:.9g}">'
            f'<freejoint name="{name}_free"/>{"".join(_piece_geoms(kind, colors[color]))}</body>'
        )
    return bodies


def _table_body(geometry: SceneGeometry) -> list[str]:
    half_length = geometry.table_length / 2.0
    half_width = geometry.table_width / 2.0
    top_thickness = 0.04
    top_center_z = geometry.table_top - (top_thickness / 2.0)
    lines = [
        f'<body name="measured_table" pos="{_format_vector(geometry.table_center)}" '
        f'euler="0 0 {geometry.table_yaw_degrees:.9g}">',
        f'<geom name="tabletop" type="box" size="{half_length:.9g} {half_width:.9g} '
        f'{top_thickness / 2.0:.9g}" pos="0 0 {top_center_z - geometry.table_center[2]:.9g}" '
        'rgba="0.94 0.94 0.925 1" friction="0.9 0.01 0.001"/>',
    ]
    leg_height = geometry.table_top - top_thickness
    for x_sign in (-1, 1):
        for y_sign in (-1, 1):
            lines.append(
                f'<geom type="box" size="0.027 0.027 {leg_height / 2.0:.9g}" '
                f'pos="{x_sign * (half_length - 0.07):.9g} '
                f'{y_sign * (half_width - 0.07):.9g} '
                f'{(leg_height / 2.0) - geometry.table_center[2]:.9g}" '
                'rgba="0.80 0.81 0.80 1"/>'
            )
    lines.append("</body>")
    return lines


def _board_body(geometry: SceneGeometry) -> list[str]:
    total_half = geometry.board_total_side / 2.0
    lines = [
        f'<body name="chess_board" pos="{geometry.board_center[0]:.9g} '
        f'{geometry.board_center[1]:.9g} {geometry.table_top:.9g}" '
        f'euler="0 0 {geometry.board_yaw_degrees:.9g}">',
        f'<geom name="board_collision" type="box" size="{total_half:.9g} '
        f'{total_half:.9g} {geometry.board_thickness / 2.0:.9g}" '
        f'pos="0 0 {geometry.board_thickness / 2.0:.9g}" '
        'rgba="0.34 0.15 0.045 1" friction="1.1 0.01 0.001"/>',
    ]
    tile_half = geometry.square_size / 2.0
    for file_index in range(8):
        for rank_index in range(8):
            tile_color = (
                "0.83 0.63 0.36 1"
                if (file_index + rank_index) % 2 == 0
                else "0.27 0.105 0.025 1"
            )
            local_x = (file_index - 3.5) * geometry.square_size
            local_y = (rank_index - 3.5) * geometry.square_size
            lines.append(
                f'<geom name="square_{file_index}_{rank_index}" type="box" '
                f'size="{tile_half:.9g} {tile_half:.9g} 0.0005" '
                f'pos="{local_x:.9g} {local_y:.9g} {geometry.board_thickness + 0.0005:.9g}" '
                f'rgba="{tile_color}" contype="0" conaffinity="0"/>'
            )
    lines.append("</body>")
    return lines


def _fiducial_body(config: dict[str, Any], geometry: SceneGeometry) -> list[str]:
    background = config["simulation_estimates"]["background"]
    local_x, local_y = (
        float(value) for value in background["fiducial_center_in_table_frame_xy_m"]
    )
    sheet_x, sheet_y = (
        float(value) for value in background["fiducial_size_xy_m"]
    )
    center = _table_to_world(geometry, local_x, local_y, geometry.table_top + 0.002)
    lines = [
        f'<body name="fiducial_sheet" pos="{_format_vector(center)}" '
        f'euler="0 0 {geometry.table_yaw_degrees:.9g}">',
        f'<geom type="box" size="{sheet_x / 2.0:.9g} {sheet_y / 2.0:.9g} 0.001" '
        'rgba="0.97 0.97 0.95 1" '
        'contype="0" conaffinity="0"/>',
    ]
    patterns = (
        ("0111110", "0100010", "0101010", "0110110", "0101010", "0100010", "0111110"),
        ("0111110", "0100010", "0111010", "0101110", "0110010", "0100010", "0111110"),
    )
    module = 0.010
    for tag_index, pattern in enumerate(patterns):
        tag_x = -0.072 + (tag_index * 0.144)
        lines.append(
            f'<geom type="box" size="0.040 0.040 0.0007" pos="{tag_x:.9g} 0 0.0017" '
            'rgba="0.03 0.03 0.03 1" contype="0" conaffinity="0"/>'
        )
        for row, bits in enumerate(pattern):
            for column, bit in enumerate(bits):
                if bit == "0":
                    x = tag_x + (column - 3) * module
                    y = (3 - row) * module
                    lines.append(
                        f'<geom type="box" size="0.0046 0.0046 0.0008" '
                        f'pos="{x:.9g} {y:.9g} 0.0025" rgba="0.98 0.98 0.98 1" '
                        'contype="0" conaffinity="0"/>'
                    )
    lines.append("</body>")
    return lines


def _photo_background(config: dict[str, Any], geometry: SceneGeometry) -> list[str]:
    half_length = geometry.table_length / 2.0
    half_width = geometry.table_width / 2.0
    background = config["simulation_estimates"]["background"]
    ledge = background["ledge"]
    ledge_depth = float(ledge["depth_m"])
    ledge_thickness = float(ledge["thickness_m"])
    ledge_front_y = -half_width + float(ledge["front_overhang_past_rear_table_edge_m"])
    ledge_center_y = ledge_front_y - (ledge_depth / 2.0)
    ledge_bottom_z = geometry.table_top + float(ledge["bottom_above_table_m"])
    rear_y = -half_width - 0.12
    top = geometry.table_top
    tripod_x, tripod_y = (
        float(value) for value in background["tripod_column_in_table_frame_xy_m"]
    )
    lines = [
        f'<body name="photo_background" pos="{geometry.table_center[0]:.9g} '
        f'{geometry.table_center[1]:.9g} 0" euler="0 0 {geometry.table_yaw_degrees:.9g}">',
        f'<geom name="rear_wall" type="box" size="1.15 0.035 0.95" '
        f'pos="0 {rear_y - 0.06:.9g} 0.95" rgba="0.94 0.945 0.94 1" '
        'contype="0" conaffinity="0"/>',
        f'<geom name="window_dark" type="box" size="0.88 0.012 0.39" '
        f'pos="0 {rear_y - 0.021:.9g} {top + 0.52:.9g}" rgba="0.08 0.09 0.09 1" '
        'contype="0" conaffinity="0"/>',
        f'<geom name="window_sill" type="box" size="0.94 {ledge_depth / 2.0:.9g} '
        f'{ledge_thickness / 2.0:.9g}" pos="0 {ledge_center_y:.9g} '
        f'{ledge_bottom_z + (ledge_thickness / 2.0):.9g}" rgba="0.95 0.95 0.94 1" '
        'contype="0" conaffinity="0"/>',
        f'<geom type="box" size="0.91 0.025 0.025" pos="0 {rear_y:.9g} '
        f'{top + 0.19:.9g}" rgba="0.09 0.10 0.10 1" contype="0" conaffinity="0"/>',
    ]
    for index in range(15):
        blind_z = top + 0.245 + (index * 0.043)
        lines.append(
            f'<geom name="blind_{index:02d}" type="box" size="0.85 0.011 0.014" '
            f'pos="0 {rear_y + 0.005:.9g} {blind_z:.9g}" '
            'rgba="0.76 0.76 0.74 1" contype="0" conaffinity="0"/>'
        )
    # A compact black tripod at the left edge reproduces the strongest side silhouette.
    lines.extend(
        [
            f'<geom name="tripod_column" type="capsule" size="0.014" '
            f'fromto="{tripod_x:.9g} {tripod_y:.9g} {top + 0.02:.9g} '
            f'{tripod_x:.9g} {tripod_y:.9g} {top + 0.58:.9g}" '
            'rgba="0.035 0.04 0.045 1" group="4" contype="0" conaffinity="0"/>',
            f'<geom type="capsule" size="0.010" fromto="{tripod_x:.9g} {tripod_y:.9g} '
            f'{top + 0.31:.9g} {tripod_x - 0.17:.9g} {tripod_y + 0.20:.9g} '
            f'{top + 0.005:.9g}" '
            'rgba="0.03 0.035 0.04 1" group="4" contype="0" conaffinity="0"/>',
            f'<geom type="capsule" size="0.010" fromto="{tripod_x:.9g} {tripod_y:.9g} '
            f'{top + 0.31:.9g} {tripod_x + 0.13:.9g} {tripod_y + 0.17:.9g} '
            f'{top + 0.005:.9g}" '
            'rgba="0.03 0.035 0.04 1" group="4" contype="0" conaffinity="0"/>',
            f'<geom type="box" size="0.075 0.035 0.025" pos="{tripod_x:.9g} '
            f'{tripod_y:.9g} {top + 0.61:.9g}" rgba="0.025 0.03 0.035 1" '
            'group="4" contype="0" conaffinity="0"/>',
        ]
    )
    lines.append("</body>")
    return lines


def _robot_mounts(config: dict[str, Any], geometry: SceneGeometry) -> list[str]:
    lines: list[str] = []
    for robot in config["simulation_estimates"]["robots"]:
        name = robot["name"]
        local_x, local_y, base_z = (float(value) for value in robot["mount_in_table_frame_xyz_m"])
        x, y, _ = _table_to_world(geometry, local_x, local_y, base_z)
        yaw = geometry.table_yaw_degrees + float(robot["yaw_relative_to_table_degrees"])
        lines.extend(
            [
                f'<body name="{name}_edge_clamp" pos="{x:.9g} {y:.9g} {base_z - 0.014:.9g}" '
                f'euler="0 0 {geometry.table_yaw_degrees:.9g}">',
                '<geom type="box" size="0.065 0.052 0.014" rgba="0.94 0.94 0.92 1"/>',
                '<geom type="box" size="0.050 0.020 0.060" pos="0 0.047 -0.052" '
                'rgba="0.12 0.13 0.14 1"/>',
                '<geom type="cylinder" size="0.011 0.009" pos="0.052 0 0.017" '
                'rgba="1 0.28 0.035 1" contype="0" conaffinity="0"/>',
                '</body>',
                f'<frame name="{name}_robot_mount" pos="{x:.9g} {y:.9g} {base_z:.9g}" '
                f'euler="0 0 {yaw:.9g}"/>',
            ]
        )
    return lines


def _studio_cameras(geometry: SceneGeometry) -> list[str]:
    """Add inspection-only cameras without changing the frozen task camera."""

    definitions = (
        (
            "studio_overview",
            (0.00, 0.08, geometry.table_top + 0.14),
            (0.00, 1.35, geometry.table_top + 0.82),
            34.0,
        ),
        (
            "studio_left",
            (-0.01, 0.12, geometry.table_top + 0.18),
            (-0.15, 1.05, geometry.table_top + 0.62),
            30.0,
        ),
        (
            "studio_right",
            (-0.47, 0.28, geometry.table_top + 0.20),
            (-0.75, 1.00, geometry.table_top + 0.62),
            30.0,
        ),
    )
    lines: list[str] = []
    for name, target_local, camera_local, fovy in definitions:
        target = _table_to_world(geometry, *target_local)
        position = _table_to_world(geometry, *camera_local)
        target_name = f"{name}_target"
        lines.extend(
            [
                f'<body name="{target_name}" pos="{_format_vector(target)}"/>',
                f'<camera name="{name}" pos="{_format_vector(position)}" '
                f'mode="targetbody" target="{target_name}" fovy="{fovy:.9g}"/>',
            ]
        )
    return lines


def build_scene_xml(
    *,
    config_path: Path = DEFAULT_CAPTURE_CONFIG,
    external_root: Path = DEFAULT_EXTERNAL_ROOT,
    scan_overlay: bool = False,
    piece_layout: str = "standard",
) -> str:
    config = load_capture_config(config_path)
    geometry = scene_geometry(config)
    capture_root = capture_directory(config, external_root)

    assets = [
        '<texture name="floor_texture" type="2d" builtin="checker" '
        'rgb1="0.10 0.11 0.12" rgb2="0.16 0.17 0.18" width="256" height="256"/>',
        '<material name="floor_material" texture="floor_texture" texrepeat="4 4" reflectance="0.04"/>',
    ]
    scan_geom = ""
    if scan_overlay:
        obj_path = capture_root / "raw.obj"
        texture_path = capture_root / "textures" / "cf0b076cb0c70da17b8b9521e1c314f8.png"
        if not obj_path.is_file() or not texture_path.is_file():
            raise FileNotFoundError(
                "Polycam reference assets are missing; run `sim2claw fetch-polycam` first"
            )
        assets.extend(
            [
                f'<texture name="scan_texture" type="2d" file="{escape(str(texture_path))}"/>',
                '<material name="scan_material" texture="scan_texture" rgba="1 1 1 0.24" '
                'specular="0" shininess="0"/>',
                f'<mesh name="scan_mesh" file="{escape(str(obj_path))}"/>',
            ]
        )
        scan_transform = config["roomplan_measurements"]["scan_to_roomplan_mujoco"]
        scan_geom = (
            '<geom name="polycam_reference" type="mesh" mesh="scan_mesh" '
            'material="scan_material" contype="0" conaffinity="0" group="2" '
            f'pos="{_format_vector(scan_transform["pos_xyz_m"])}" '
            f'quat="{_format_vector(scan_transform["quat_wxyz"])}"/>'
        )

    target = _table_to_world(geometry, 0.0, -0.02, geometry.table_top + 0.12)
    photo_camera = _table_to_world(geometry, 0.55, 1.55, geometry.table_top + 1.23)
    workcell_camera = _table_to_world(geometry, 1.25, 1.10, geometry.table_top + 0.88)
    world = [
        '<geom name="floor" type="plane" size="3 3 0.1" material="floor_material" friction="1 0.01 0.001"/>',
        '<light name="window_key" pos="0 -0.5 2.6" dir="0 0 -1" diffuse="0.92 0.92 0.88"/>',
        '<light name="front_fill" pos="-1.2 1.4 1.9" dir="0 -0.4 -1" diffuse="0.42 0.44 0.48"/>',
        f'<body name="scene_target" pos="{_format_vector(target)}"/>',
        f'<camera name="photo_reference" pos="{_format_vector(photo_camera)}" '
        'mode="targetbody" target="scene_target" fovy="55"/>',
        f'<camera name="workcell" pos="{_format_vector(workcell_camera)}" '
        'mode="targetbody" target="scene_target" fovy="43"/>',
        f'<camera name="overhead" pos="{geometry.table_center[0]:.9g} '
        f'{geometry.table_center[1]:.9g} 2.5" mode="targetbody" target="scene_target" fovy="38"/>',
        *_studio_cameras(geometry),
        scan_geom,
        *_photo_background(config, geometry),
        *_table_body(geometry),
        *_fiducial_body(config, geometry),
        *_board_body(geometry),
        *_piece_bodies(geometry, piece_layout=piece_layout),
        *_robot_mounts(config, geometry),
    ]
    return "\n".join(
        [
            '<mujoco model="sim2claw_photo_aligned_chess_workcell">',
            '<compiler angle="degree" autolimits="true"/>',
            '<option timestep="0.005" integrator="implicitfast" cone="elliptic" '
            'iterations="10" ls_iterations="20" impratio="10"/>',
            f'<statistic center="{geometry.table_center[0]:.9g} {geometry.table_center[1]:.9g} '
            f'{geometry.table_top / 2.0:.9g}" extent="1.8"/>',
            '<visual><global offwidth="1280" offheight="1600"/>'
            '<headlight ambient="0.30 0.30 0.31" diffuse="0.73 0.73 0.70" '
            'specular="0.12 0.12 0.12"/></visual>',
            '<asset>',
            *assets,
            '</asset>',
            '<default><geom density="720" solref="0.01 1" solimp="0.95 0.99 0.001" '
            'friction="0.8 0.01 0.001"/></default>',
            '<worldbody>',
            *world,
            '</worldbody>',
            '</mujoco>',
        ]
    )


def _white_robot_materials(spec: mujoco.MjSpec) -> None:
    for material in spec.materials:
        if not material.name.startswith("sts3215"):
            material.rgba = [0.94, 0.94, 0.91, 1.0]


def build_scene_spec(
    *,
    config_path: Path = DEFAULT_CAPTURE_CONFIG,
    external_root: Path = DEFAULT_EXTERNAL_ROOT,
    mass_profile_path: Path | None = DEFAULT_SO101_MASS_PROFILE,
    scan_overlay: bool = False,
    include_robots: bool = True,
    piece_layout: str = "standard",
) -> mujoco.MjSpec:
    spec = mujoco.MjSpec.from_string(
        build_scene_xml(
            config_path=config_path,
            external_root=external_root,
            scan_overlay=scan_overlay,
            piece_layout=piece_layout,
        )
    )
    if not include_robots:
        return spec
    if not SO101_MODEL_PATH.is_file():
        raise FileNotFoundError(f"vendored SO-101 model missing: {SO101_MODEL_PATH}")
    mass_profile = (
        load_so101_mass_profile(mass_profile_path)
        if mass_profile_path is not None
        else None
    )
    for prefix in ("left_", "right_"):
        robot = mujoco.MjSpec.from_file(str(SO101_MODEL_PATH))
        _white_robot_materials(robot)
        if mass_profile is not None:
            robot_name = prefix.removesuffix("_")
            payload_id = mass_profile["scene_defaults"]["robot_payloads"][robot_name]
            apply_so101_mass_profile(robot, mass_profile, payload_id=payload_id)
        spec.attach(
            robot,
            frame=spec.frame(f"{prefix}robot_mount"),
            prefix=prefix,
        )
    return spec


def initialize_robot_poses(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    *,
    config_path: Path = DEFAULT_CAPTURE_CONFIG,
) -> None:
    config = load_capture_config(config_path)
    for robot in config["simulation_estimates"]["robots"]:
        prefix = f"{robot['name']}_"
        pose = [float(value) for value in robot["joint_pose_radians"]]
        for joint_name, value in zip(ROBOT_JOINTS, pose, strict=True):
            full_name = prefix + joint_name
            joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, full_name)
            actuator_id = mujoco.mj_name2id(
                model, mujoco.mjtObj.mjOBJ_ACTUATOR, full_name
            )
            if joint_id < 0 or actuator_id < 0:
                raise ValueError(f"missing attached SO-101 control: {full_name}")
            data.qpos[model.jnt_qposadr[joint_id]] = value
            data.ctrl[actuator_id] = value
    mujoco.mj_forward(model, data)


def scene_summary(
    config_path: Path = DEFAULT_CAPTURE_CONFIG,
    *,
    mass_profile_path: Path = DEFAULT_SO101_MASS_PROFILE,
    piece_layout: str = "standard",
) -> dict[str, Any]:
    config = load_capture_config(config_path)
    mass_profile = load_so101_mass_profile(mass_profile_path)
    geometry = scene_geometry(config)
    robots = config["simulation_estimates"]["robots"]
    board_local_x = float(
        config["simulation_estimates"]["board"]["center_in_table_frame_xy_m"][0]
    )
    return {
        "capture_id": config["capture_id"],
        "proof_class": "photo_aligned_simulation_scene",
        "table": {
            "length_m": geometry.table_length,
            "width_m": geometry.table_width,
            "height_m": geometry.table_height,
            "measurement_confidence": config["roomplan_measurements"]["table"]["confidence"],
        },
        "board": {
            "playing_side_m": geometry.board_side,
            "total_side_m": geometry.board_total_side,
            "square_m": geometry.square_size,
            "measurement_confidence": config["simulation_estimates"]["board"]["confidence"],
            "near_side_color": "black",
        },
        "robots": {
            "count": 2,
            "model": "MuJoCo Menagerie robotstudio_so101",
            "upstream_commit": "71f066ad0be9cd271f7ed58c030243ef157af9f4",
            "pose_confidence": "mounts_photo_registered_joint_poses_not_calibrated",
            "mass_profile": mass_profile_summary(mass_profile),
            "mounts": [
                {
                    "name": robot["name"],
                    "role": robot["role"],
                    "table_frame_xyz_m": robot["mount_in_table_frame_xyz_m"],
                    "board_centerline_offset_m": abs(
                        float(robot["mount_in_table_frame_xyz_m"][0]) - board_local_x
                    ),
                }
                for robot in robots
            ],
        },
        "studio_cameras": list(STUDIO_CAMERAS),
        "photo_alignment": config["simulation_estimates"]["photo_reference"],
        "scene_elements": config["simulation_estimates"]["background"]["elements"],
        "piece_layout": piece_layout,
        "piece_layout_id": (
            CURRENT_TASK_LAYOUT_ID
            if piece_layout in {CURRENT_TASK_PIECE_LAYOUT, "teleop_pawns"}
            else "standard_full_chess_v1"
        ),
        "piece_count": (
            len(TELEOP_PAWN_SOURCE_SQUARES) + len(TELEOP_TAN_PAWN_SQUARES)
            if piece_layout in {CURRENT_TASK_PIECE_LAYOUT, "teleop_pawns"}
            else 32
        ),
        "physical_authority": False,
    }
