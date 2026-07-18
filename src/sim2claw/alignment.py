from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

import mujoco
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .capture import load_capture_config, sha256_file
from .paths import DEFAULT_CAPTURE_CONFIG, DEFAULT_OUTPUT_ROOT
from .scene import (
    _table_to_world,
    build_scene_spec,
    scene_geometry,
)


PHOTO_COLOR = (255, 153, 0, 255)
MODEL_COLOR = (0, 232, 171, 255)
TABLE_COLOR = (0, 190, 255, 255)
MOUNT_COLOR = (255, 64, 110, 255)
LEDGE_COLOR = (198, 92, 255, 255)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        Path("/System/Library/Fonts/SFNS.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    )
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def _as_points(mapping: dict[str, list[float]]) -> np.ndarray:
    order = ("rear_left", "rear_right", "front_left", "front_right")
    return np.asarray([mapping[name] for name in order], dtype=float)


def _table_corners(length: float, width: float) -> np.ndarray:
    half_length = length / 2.0
    half_width = width / 2.0
    return np.asarray(
        [
            (half_length, -half_width),
            (-half_length, -half_width),
            (half_length, half_width),
            (-half_length, half_width),
        ],
        dtype=float,
    )


def _rectangle_corners(
    center: Iterable[float], width: float, depth: float, yaw_degrees: float
) -> np.ndarray:
    half_width = width / 2.0
    half_depth = depth / 2.0
    corners = np.asarray(
        [
            (half_width, -half_depth),
            (-half_width, -half_depth),
            (half_width, half_depth),
            (-half_width, half_depth),
        ],
        dtype=float,
    )
    angle = math.radians(yaw_degrees)
    rotation = np.asarray(
        [[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]]
    )
    return corners @ rotation.T + np.asarray(tuple(center), dtype=float)


def solve_planar_homography(world_xy: np.ndarray, pixels: np.ndarray) -> np.ndarray:
    if world_xy.shape != (4, 2) or pixels.shape != (4, 2):
        raise ValueError("planar homography requires four 2D point pairs")
    rows: list[list[float]] = []
    values: list[float] = []
    for (x, y), (u, v) in zip(world_xy, pixels, strict=True):
        rows.extend(
            [
                [x, y, 1.0, 0.0, 0.0, 0.0, -u * x, -u * y],
                [0.0, 0.0, 0.0, x, y, 1.0, -v * x, -v * y],
            ]
        )
        values.extend([u, v])
    coefficients = np.linalg.solve(np.asarray(rows), np.asarray(values))
    return np.append(coefficients, 1.0).reshape(3, 3)


def project_planar(homography: np.ndarray, points: np.ndarray) -> np.ndarray:
    homogeneous = np.column_stack([points, np.ones(len(points))])
    projected = homogeneous @ homography.T
    return projected[:, :2] / projected[:, 2:3]


def unproject_planar(homography: np.ndarray, pixels: np.ndarray) -> np.ndarray:
    return project_planar(np.linalg.inv(homography), pixels)


def _polygon_order(points: np.ndarray) -> list[tuple[float, float]]:
    # Input order is rear-left, rear-right, front-left, front-right.
    return [tuple(points[index]) for index in (0, 1, 3, 2)]


def _draw_cross(
    draw: ImageDraw.ImageDraw,
    point: np.ndarray,
    color: tuple[int, int, int, int],
    radius: int,
    width: int,
) -> None:
    x, y = (float(value) for value in point)
    draw.line((x - radius, y - radius, x + radius, y + radius), fill=color, width=width)
    draw.line((x - radius, y + radius, x + radius, y - radius), fill=color, width=width)


def _draw_circle(
    draw: ImageDraw.ImageDraw,
    point: np.ndarray,
    color: tuple[int, int, int, int],
    radius: int,
    width: int,
) -> None:
    x, y = (float(value) for value in point)
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), outline=color, width=width)


def _nearest_board_distance(
    point: np.ndarray,
    center: np.ndarray,
    total_side: float,
    yaw_degrees: float,
) -> float:
    angle = math.radians(-yaw_degrees)
    rotation = np.asarray(
        [[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]]
    )
    local = rotation @ (point - center)
    excess = np.maximum(np.abs(local) - (total_side / 2.0), 0.0)
    return float(np.linalg.norm(excess))


def _annotate_photo(
    photo_path: Path,
    output_path: Path,
    config: dict[str, Any],
    homography: np.ndarray,
) -> dict[str, Any]:
    reference = config["simulation_estimates"]["alignment_reference"]
    board = config["simulation_estimates"]["board"]
    geometry = scene_geometry(config)
    image = Image.open(photo_path).convert("RGBA")
    expected_size = tuple(int(value) for value in reference["image_size_px"])
    if image.size != expected_size:
        raise ValueError(f"alignment photo size mismatch: expected {expected_size}, got {image.size}")

    table_world = _table_corners(geometry.table_length, geometry.table_width)
    table_pixels = project_planar(homography, table_world)
    board_world = _rectangle_corners(
        board["center_in_table_frame_xy_m"],
        geometry.board_total_side,
        geometry.board_total_side,
        float(board["yaw_relative_to_table_degrees"]),
    )
    board_pixels = project_planar(homography, board_world)
    observed_board = _as_points(reference["board_corners_px"])

    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    line_width = 11
    draw.line(
        _polygon_order(table_pixels) + [_polygon_order(table_pixels)[0]],
        fill=TABLE_COLOR,
        width=line_width,
        joint="curve",
    )
    draw.polygon(_polygon_order(board_pixels), fill=(0, 232, 171, 45))
    draw.line(
        _polygon_order(board_pixels) + [_polygon_order(board_pixels)[0]],
        fill=MODEL_COLOR,
        width=line_width,
        joint="curve",
    )
    draw.line(
        _polygon_order(observed_board) + [_polygon_order(observed_board)[0]],
        fill=PHOTO_COLOR,
        width=7,
        joint="curve",
    )

    predicted_mounts: dict[str, list[float]] = {}
    mount_residuals: dict[str, float] = {}
    observed_mounts = reference["clamp_contacts_px"]
    for robot in config["simulation_estimates"]["robots"]:
        name = robot["name"]
        contact = np.asarray(robot["clamp_contact_in_table_frame_xy_m"], dtype=float)
        predicted = project_planar(homography, contact.reshape(1, 2))[0]
        observed = np.asarray(observed_mounts[name], dtype=float)
        predicted_mounts[name] = predicted.tolist()
        mount_residuals[name] = float(np.linalg.norm(predicted - observed))
        _draw_circle(draw, predicted, MODEL_COLOR, 28, 10)
        _draw_cross(draw, observed, PHOTO_COLOR, 24, 8)
        draw.text(
            (predicted[0] + 35, predicted[1] - 25),
            f"{name} clamp",
            font=_font(38),
            fill=MOUNT_COLOR,
            stroke_width=2,
            stroke_fill=(0, 0, 0, 210),
        )

    background = config["simulation_estimates"]["background"]
    fiducial_world = np.asarray(
        background["fiducial_center_in_table_frame_xy_m"], dtype=float
    )
    fiducial_pixel = project_planar(homography, fiducial_world.reshape(1, 2))[0]
    observed_fiducial = np.asarray(reference["fiducial_center_px"], dtype=float)
    _draw_circle(draw, fiducial_pixel, MODEL_COLOR, 24, 9)
    _draw_cross(draw, observed_fiducial, PHOTO_COLOR, 20, 7)

    ledge = background["ledge"]
    ledge_front_y = (
        -(geometry.table_width / 2.0)
        + float(ledge["front_overhang_past_rear_table_edge_m"])
    )
    ledge_world = np.asarray(
        [[geometry.table_length / 2.0, ledge_front_y], [-geometry.table_length / 2.0, ledge_front_y]]
    )
    ledge_pixels = project_planar(homography, ledge_world)
    draw.line([tuple(point) for point in ledge_pixels], fill=LEDGE_COLOR, width=9)
    observed_ledge = np.asarray(reference["ledge_front_edge_px"], dtype=float)
    draw.line([tuple(point) for point in observed_ledge], fill=PHOTO_COLOR, width=6)

    dimension_font = _font(34)
    board_label_x = float(np.max(board_pixels[:, 0]) + 45)
    board_label_y = float(np.min(board_pixels[:, 1]) + 170)
    rear_clearance = (
        float(board["center_in_table_frame_xy_m"][1])
        - (geometry.board_total_side / 2.0)
        + (geometry.table_width / 2.0)
    )
    draw.text(
        (board_label_x, board_label_y),
        f"board {geometry.board_total_side * 1000:.0f} mm overall\n"
        f"rear gap {rear_clearance * 1000:.0f} mm",
        font=dimension_font,
        fill=MODEL_COLOR,
        stroke_width=2,
        stroke_fill=(0, 0, 0, 220),
    )
    draw.text(
        (130, 2940),
        f"RoomPlan table {geometry.table_length * 1000:.0f} x "
        f"{geometry.table_width * 1000:.0f} mm",
        font=dimension_font,
        fill=TABLE_COLOR,
        stroke_width=2,
        stroke_fill=(0, 0, 0, 220),
    )
    ledge_midpoint = observed_ledge.mean(axis=0)
    draw.text(
        (ledge_midpoint[0] - 390, ledge_midpoint[1] - 105),
        f"sill bottom +{float(ledge['bottom_above_table_m']) * 1000:.0f} mm "
        "(photo estimate)",
        font=dimension_font,
        fill=LEDGE_COLOR,
        stroke_width=2,
        stroke_fill=(0, 0, 0, 220),
    )
    left_mount_pixel = np.asarray(predicted_mounts["left"])
    right_mount_pixel = np.asarray(predicted_mounts["right"])
    draw.line(
        [tuple(left_mount_pixel), tuple(right_mount_pixel)],
        fill=MOUNT_COLOR,
        width=5,
    )
    mount_midpoint = (left_mount_pixel + right_mount_pixel) / 2.0
    draw.text(
        (mount_midpoint[0] - 175, mount_midpoint[1] + 35),
        "clamps 486 mm apart",
        font=dimension_font,
        fill=MOUNT_COLOR,
        stroke_width=2,
        stroke_fill=(0, 0, 0, 220),
    )

    legend_box = (50, 50, 1490, 410)
    draw.rounded_rectangle(legend_box, radius=24, fill=(8, 12, 18, 205))
    title_font = _font(52)
    body_font = _font(38)
    draw.text((85, 75), "sim2claw alignment overlay", font=title_font, fill=(255, 255, 255, 255))
    draw.text((85, 150), "cyan: measured RoomPlan table", font=body_font, fill=TABLE_COLOR)
    draw.text((85, 205), "green: corrected simulation", font=body_font, fill=MODEL_COLOR)
    draw.text((85, 260), "orange: observed photo landmarks", font=body_font, fill=PHOTO_COLOR)
    draw.text((85, 315), "purple: estimated ledge footprint", font=body_font, fill=LEDGE_COLOR)

    result = Image.alpha_composite(image, layer).convert("RGB")
    result.thumbnail((1440, 1920), Image.Resampling.LANCZOS)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.save(output_path, format="PNG", optimize=True)

    board_pixel_rms = float(
        np.sqrt(np.mean(np.sum((board_pixels - observed_board) ** 2, axis=1)))
    )
    observed_board_world = unproject_planar(homography, observed_board)
    board_world_rms = float(
        np.sqrt(np.mean(np.sum((board_world - observed_board_world) ** 2, axis=1)))
    )
    return {
        "output": str(output_path),
        "output_sha256": sha256_file(output_path),
        "homography_table_frame_to_source_pixels": homography.tolist(),
        "residuals": {
            "board_corner_rms_source_px": board_pixel_rms,
            "board_corner_rms_table_plane_m": board_world_rms,
            "left_clamp_source_px": mount_residuals["left"],
            "right_clamp_source_px": mount_residuals["right"],
            "fiducial_center_source_px": float(
                np.linalg.norm(fiducial_pixel - observed_fiducial)
            ),
        },
        "predicted_source_pixels": {
            "board_corners": board_pixels.tolist(),
            "clamp_contacts": predicted_mounts,
            "fiducial_center": fiducial_pixel.tolist(),
        },
    }


def _camera_project(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    camera_id: int,
    points: np.ndarray,
    width: int,
    height: int,
) -> np.ndarray:
    rotation = data.cam_xmat[camera_id].reshape(3, 3)
    camera_position = data.cam_xpos[camera_id]
    focal = (height / 2.0) / math.tan(math.radians(model.cam_fovy[camera_id]) / 2.0)
    projected: list[tuple[float, float]] = []
    for point in points:
        camera_point = rotation.T @ (point - camera_position)
        projected.append(
            (
                (width / 2.0) + (focal * camera_point[0] / -camera_point[2]),
                (height / 2.0) - (focal * camera_point[1] / -camera_point[2]),
            )
        )
    return np.asarray(projected)


def _annotate_scan(output_path: Path, config: dict[str, Any]) -> dict[str, Any]:
    width = 1200
    height = 1200
    spec = build_scene_spec(scan_overlay=True, include_robots=False)
    for material in spec.materials:
        if material.name == "scan_material":
            material.rgba = [1.0, 1.0, 1.0, 1.0]
    for geom in spec.geoms:
        if geom.name != "polycam_reference":
            geom.rgba = [geom.rgba[0], geom.rgba[1], geom.rgba[2], 0.0]
    model = spec.compile()
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    renderer = mujoco.Renderer(model, height=height, width=width)
    try:
        renderer.update_scene(data, camera="overhead")
        pixels = renderer.render()
    finally:
        renderer.close()

    image = Image.fromarray(pixels, mode="RGB").convert("RGBA")
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    geometry = scene_geometry(config)
    camera_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, "overhead")

    def project_table(points_xy: np.ndarray) -> np.ndarray:
        world = np.asarray(
            [
                _table_to_world(geometry, float(point[0]), float(point[1]), geometry.table_top + 0.02)
                for point in points_xy
            ]
        )
        return _camera_project(model, data, camera_id, world, width, height)

    table_pixels = project_table(_table_corners(geometry.table_length, geometry.table_width))
    draw.line(
        _polygon_order(table_pixels) + [_polygon_order(table_pixels)[0]],
        fill=TABLE_COLOR,
        width=8,
    )

    board = config["simulation_estimates"]["board"]
    current_board = _rectangle_corners(
        board["center_in_table_frame_xy_m"],
        geometry.board_total_side,
        geometry.board_total_side,
        float(board["yaw_relative_to_table_degrees"]),
    )
    current_pixels = project_table(current_board)
    draw.line(
        _polygon_order(current_pixels) + [_polygon_order(current_pixels)[0]],
        fill=MODEL_COLOR,
        width=10,
    )

    scan = config["simulation_estimates"]["polycam_scan_estimates"]
    scan_side = sum(float(value) for value in scan["board_total_side_m_range"]) / 2.0
    scan_board = _rectangle_corners(
        scan["board_center_in_table_frame_xy_m"],
        scan_side,
        scan_side,
        float(scan["board_yaw_relative_to_table_degrees"]),
    )
    scan_pixels = project_table(scan_board)
    draw.line(
        _polygon_order(scan_pixels) + [_polygon_order(scan_pixels)[0]],
        fill=PHOTO_COLOR,
        width=8,
    )

    for robot in config["simulation_estimates"]["robots"]:
        contact = np.asarray(robot["clamp_contact_in_table_frame_xy_m"], dtype=float)
        pixel = project_table(contact.reshape(1, 2))[0]
        _draw_circle(draw, pixel, MOUNT_COLOR, 18, 7)

    draw.rounded_rectangle((30, 30, 855, 228), radius=18, fill=(8, 12, 18, 210))
    draw.text((55, 50), "Polycam textured-mesh comparison", font=_font(39), fill=(255, 255, 255, 255))
    draw.text((55, 105), "green: current photo-registered board", font=_font(29), fill=MODEL_COLOR)
    draw.text((55, 145), "orange: board pose in Polycam capture", font=_font(29), fill=PHOTO_COLOR)
    draw.text((55, 185), "pink circles: current clamp contacts", font=_font(29), fill=MOUNT_COLOR)

    output = Image.alpha_composite(image, layer).convert("RGB")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output.save(output_path, format="PNG", optimize=True)
    current_center = np.asarray(board["center_in_table_frame_xy_m"], dtype=float)
    scan_center = np.asarray(scan["board_center_in_table_frame_xy_m"], dtype=float)
    return {
        "output": str(output_path),
        "output_sha256": sha256_file(output_path),
        "capture_to_current_board_center_delta_m": float(
            np.linalg.norm(current_center - scan_center)
        ),
        "capture_to_current_board_yaw_delta_degrees": float(
            board["yaw_relative_to_table_degrees"]
        )
        - float(scan["board_yaw_relative_to_table_degrees"]),
    }


def compare_alignment(
    photo_path: Path,
    *,
    output_directory: Path = DEFAULT_OUTPUT_ROOT / "alignment",
    config_path: Path = DEFAULT_CAPTURE_CONFIG,
) -> dict[str, Any]:
    config = load_capture_config(config_path)
    reference = config["simulation_estimates"]["alignment_reference"]
    actual_hash = sha256_file(photo_path)
    if actual_hash != reference["sha256"]:
        raise ValueError(
            f"alignment photo SHA-256 mismatch: expected {reference['sha256']}, got {actual_hash}"
        )
    geometry = scene_geometry(config)
    table_world = _table_corners(geometry.table_length, geometry.table_width)
    table_pixels = _as_points(reference["table_corners_px"])
    homography = solve_planar_homography(table_world, table_pixels)

    photo_output = output_directory / "photo-layout-overlay.png"
    scan_output = output_directory / "polycam-scan-overlay.png"
    photo_report = _annotate_photo(photo_path, photo_output, config, homography)
    scan_report = _annotate_scan(scan_output, config)

    board = config["simulation_estimates"]["board"]
    board_center = np.asarray(board["center_in_table_frame_xy_m"], dtype=float)
    total_side = geometry.board_total_side
    rear_clearance = (
        board_center[1] - (total_side / 2.0) + (geometry.table_width / 2.0)
    )
    robots: dict[str, Any] = {}
    for robot in config["simulation_estimates"]["robots"]:
        mount = np.asarray(robot["mount_in_table_frame_xyz_m"][:2], dtype=float)
        robots[robot["name"]] = {
            "mount_in_table_frame_xy_m": mount.tolist(),
            "nearest_mount_to_board_edge_m": _nearest_board_distance(
                mount,
                board_center,
                total_side,
                float(board["yaw_relative_to_table_degrees"]),
            ),
        }
    left = np.asarray(
        config["simulation_estimates"]["robots"][0]["mount_in_table_frame_xyz_m"][:2]
    )
    right = np.asarray(
        config["simulation_estimates"]["robots"][1]["mount_in_table_frame_xyz_m"][:2]
    )
    ledge = config["simulation_estimates"]["background"]["ledge"]
    report = {
        "schema_version": 1,
        "proof_class": "photo_registered_planar_alignment_with_polycam_cross_check",
        "source": {
            "capture_id": config["capture_id"],
            "photo": str(photo_path),
            "photo_sha256": actual_hash,
        },
        "dimensions": {
            "table_length_m": geometry.table_length,
            "table_width_m": geometry.table_width,
            "table_height_m": geometry.table_height,
            "board_playing_side_m": geometry.board_side,
            "board_total_side_m": total_side,
            "board_to_table_length_ratio": total_side / geometry.table_length,
            "board_to_table_width_ratio": total_side / geometry.table_width,
            "board_rear_clearance_m": rear_clearance,
            "robot_mount_separation_m": float(np.linalg.norm(left - right)),
            "ledge_bottom_above_table_m": float(ledge["bottom_above_table_m"]),
            "ledge_front_overhang_m": float(
                ledge["front_overhang_past_rear_table_edge_m"]
            ),
        },
        "robots": robots,
        "photo_registration": photo_report,
        "polycam_comparison": scan_report,
        "limitations": [
            "RoomPlan table dimensions are metric; board mesh bounds and all photo landmarks remain estimates.",
            "The planar registration validates table-top XY relationships but does not calibrate lens distortion or elevated 3D points.",
            "The board moved between the Polycam capture and the later overhead photo, so both poses are shown instead of silently merging them.",
            "Robot mount registration is not physical hand-eye or joint-zero calibration and opens no hardware authority.",
        ],
        "physical_authority": False,
    }
    output_directory.mkdir(parents=True, exist_ok=True)
    report_path = output_directory / "alignment-report.json"
    report["artifacts"] = {
        "photo_overlay": str(photo_output),
        "scan_overlay": str(scan_output),
        "report": str(report_path),
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report["report_sha256"] = hashlib.sha256(report_path.read_bytes()).hexdigest()
    return report
