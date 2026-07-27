#!/usr/bin/env python3
"""Bounded C922 board/CAD registration diagnostic for current poses J/S/K/L/M.

The evaluator consumes only receipt-bound native MOV frames.  It fits one
conditional pinhole camera and one static base delta on J/S/K/L, freezes both,
then compares the identity and Stage-D joint hypotheses on the same data and
retrospective pose M.  It never controls hardware or promotes P13.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path
from typing import Any, Iterable

import cv2
import mujoco
import numpy as np
from scipy.ndimage import distance_transform_edt
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

from sim2claw.recorded_replay import _compile_model
from tools.evaluate_current_multiview_cad_bundle import (
    _geom_world_vertices,
    _set_pose,
    _visual_geom_ids,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "configs/evaluations/current_c922_board_base_registration_v1.json"
SCENE_REGISTRATION = (
    ROOT / "configs/evaluations/img5349_3dgs_board_registration_v1.json"
)
FIT_POSES = ("J", "S", "K", "L")
VALIDATION_POSES = ("M",)
IMAGE_SIZE = (640, 480)
EDGE_CLIP_PX = 50.0
BASE_BODIES = {"left_base"}
MOVING_BODIES = {
    "left_upper_arm",
    "left_lower_arm",
    "left_wrist",
    "left_gripper",
    "left_camera_mount",
    "left_moving_jaw_so101_v1",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def json_lines(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _source_path(source: dict[str, Any], key: str) -> Path:
    return ROOT / source["directory"] / source[key]


def load_contract() -> dict[str, Any]:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if (
        contract.get("schema_version")
        != "sim2claw.current_c922_board_base_registration.v1"
        or tuple(contract["split"]["fit_poses"]) != FIT_POSES
        or tuple(contract["split"]["retrospective_validation_poses"])
        != VALIDATION_POSES
        or contract["split"]["future_heldout_poses"]
    ):
        raise RuntimeError("C922 extraction/split contract changed")
    for key in ("exact_CAD_scene", "stage_d"):
        item = contract["sources"][key]
        path = ROOT / item["path"]
        if sha256(path) != item["sha256"]:
            raise RuntimeError(f"source hash changed: {key}")
    return contract


def validate_and_extract(
    name: str, source: dict[str, Any]
) -> tuple[np.ndarray, dict[str, Any]]:
    paths = {
        key: _source_path(source, key)
        for key in (
            "execution_receipt",
            "joint_samples",
            "callback_ledger",
            "native_report",
            "native_video",
        )
    }
    for key, path in paths.items():
        expected = source[f"{key}_sha256"]
        if sha256(path) != expected:
            raise RuntimeError(f"{name} {key} hash changed")

    receipt = json.loads(paths["execution_receipt"].read_text(encoding="utf-8"))
    if (
        not str(receipt["status"]).startswith("completed")
        or receipt["completed_capture_hold_samples"] != 80
        or receipt["joint_samples_sha256"]
        != source["joint_samples_sha256"]
    ):
        raise RuntimeError(f"{name} receipt is not a completed 80-sample hold")
    bound = {
        item["kind"]: item
        for item in receipt["capture_artifacts"]
        if item["kind"]
        in {"overhead_source_video", "callback_ledger", "native_report"}
    }
    for kind, path_key in (
        ("overhead_source_video", "native_video"),
        ("callback_ledger", "callback_ledger"),
        ("native_report", "native_report"),
    ):
        if bound[kind]["sha256"] != source[f"{path_key}_sha256"]:
            raise RuntimeError(f"{name} receipt artifact binding changed: {kind}")

    callbacks = [
        row
        for row in json_lines(paths["callback_ledger"])
        if row.get("role") == "c922" and row.get("appended_to_writer") is True
    ]
    if len(callbacks) != source["native_frame_count"]:
        raise RuntimeError(f"{name} appended callback/movie count mismatch")
    joints = json_lines(paths["joint_samples"])
    hold_count = int(receipt["completed_capture_hold_samples"])
    hold = joints[-hold_count:]
    target_ns = int(np.median([row["host_continuous_ns"] for row in hold]))
    frame_index = min(
        range(len(callbacks)),
        key=lambda index: abs(callbacks[index]["host_continuous_ns"] - target_ns),
    )
    event = callbacks[frame_index]
    joint_index = min(
        range(len(joints)),
        key=lambda index: abs(
            joints[index]["host_continuous_ns"] - event["host_continuous_ns"]
        ),
    )
    joint = joints[joint_index]
    if (
        frame_index != source["selected_native_frame_index_zero_based"]
        or event["sequence"] != source["selected_callback_source_sequence"]
        or joint_index != source["selected_joint_sample_index_zero_based"]
        or not np.allclose(
            joint["follower_actual_position_degrees"],
            source["joint_position_degrees"],
            rtol=0.0,
            atol=1e-12,
        )
    ):
        raise RuntimeError(f"{name} deterministic alignment changed")
    delta_ms = (
        joint["host_continuous_ns"] - event["host_continuous_ns"]
    ) / 1e6
    if abs(delta_ms - source["joint_time_delta_ms"]) > 1e-5:
        raise RuntimeError(f"{name} frame/joint time delta changed")

    capture = cv2.VideoCapture(str(paths["native_video"]))
    capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
    ok, frame = capture.read()
    capture.release()
    if not ok or frame.shape[:2] != (IMAGE_SIZE[1], IMAGE_SIZE[0]):
        raise RuntimeError(f"{name} exact native frame decode failed")
    ok, encoded = cv2.imencode(".png", frame)
    if not ok or hashlib.sha256(encoded.tobytes()).hexdigest() != source[
        "decoded_frame_png_sha256"
    ]:
        raise RuntimeError(f"{name} decoded native frame bytes changed")
    return frame, {
        "native_frame_index_zero_based": frame_index,
        "callback_source_sequence": event["sequence"],
        "callback_host_continuous_ns": event["host_continuous_ns"],
        "source_pts_seconds": event["pts_seconds"],
        "joint_sample_index_zero_based": joint_index,
        "joint_time_delta_ms": delta_ms,
        "joint_position_degrees": joint["follower_actual_position_degrees"],
        "decoded_frame_png_sha256": source["decoded_frame_png_sha256"],
        "native_video_sha256": source["native_video_sha256"],
    }


def _clusters(values: Iterable[float], tolerance: float = 5.0) -> list[float]:
    groups: list[list[float]] = []
    for value in sorted(values):
        if not groups or value - float(np.mean(groups[-1])) > tolerance:
            groups.append([value])
        else:
            groups[-1].append(value)
    return [float(np.median(group)) for group in groups if len(group) >= 2]


def board_line_support(
    frames: dict[str, np.ndarray], image_corners: np.ndarray
) -> dict[str, Any]:
    row_values: list[float] = []
    column_values: list[float] = []
    per_pose: dict[str, Any] = {}
    for name, frame in frames.items():
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        edge = cv2.Canny(gray, 55, 150)
        mask = np.zeros_like(edge)
        mask[90:380, 10:470] = edge[90:380, 10:470]
        lines = cv2.HoughLinesP(
            mask, 1, np.pi / 720.0, 35, minLineLength=28, maxLineGap=10
        )
        rows: list[float] = []
        columns: list[float] = []
        if lines is not None:
            for x1, y1, x2, y2 in lines[:, 0]:
                dx, dy = float(x2 - x1), float(y2 - y1)
                angle = abs(math.degrees(math.atan2(dy, dx))) % 180.0
                if angle > 90.0:
                    angle = 180.0 - angle
                if abs(dx) > 1e-6 and angle <= 22.0:
                    rows.append(float(y1 + (250.0 - x1) * dy / dx))
                if abs(dy) > 1e-6 and angle >= 55.0:
                    columns.append(float(x1 + (240.0 - y1) * dx / dy))
        row_values.extend(v for v in rows if 100.0 <= v <= 350.0)
        column_values.extend(v for v in columns if 20.0 <= v <= 430.0)
        per_pose[name] = {
            "candidate_row_segments": len(rows),
            "candidate_column_segments": len(columns),
        }
    row_clusters = _clusters(row_values)
    column_clusters = _clusters(column_values)
    unit_square = np.asarray(((0, 0), (8, 0), (8, 8), (0, 8)), np.float32)
    homography = cv2.getPerspectiveTransform(
        unit_square, image_corners.astype(np.float32)
    )

    def transform(points: np.ndarray) -> np.ndarray:
        homogeneous = np.column_stack((points, np.ones(len(points))))
        result = homogeneous @ homography.T
        return result[:, :2] / result[:, 2:]

    expected_rows = []
    expected_columns = []
    for index in range(9):
        first, second = transform(
            np.asarray(((0, index), (8, index)), dtype=float)
        )
        expected_rows.append(
            float(
                first[1]
                + (250.0 - first[0])
                * (second[1] - first[1])
                / (second[0] - first[0])
            )
        )
        first, second = transform(
            np.asarray(((index, 0), (index, 8)), dtype=float)
        )
        expected_columns.append(
            float(
                first[0]
                + (240.0 - first[1])
                * (second[0] - first[0])
                / (second[1] - first[1])
            )
        )
    tolerance = 4.0
    supported_rows = [
        expected
        for expected in expected_rows
        if row_clusters
        and min(abs(expected - observed) for observed in row_clusters)
        <= tolerance
    ]
    supported_columns = [
        expected
        for expected in expected_columns
        if column_clusters
        and min(abs(expected - observed) for observed in column_clusters)
        <= tolerance
    ]
    return {
        "method": "Canny_Hough_union_then_unique_seed_lattice_line_matching",
        "row_reference_x_px": 250.0,
        "column_reference_y_px": 240.0,
        "matching_tolerance_px": tolerance,
        "raw_row_cluster_intercepts_px": row_clusters,
        "raw_column_cluster_intercepts_px": column_clusters,
        "expected_row_intercepts_px": expected_rows,
        "expected_column_intercepts_px": expected_columns,
        "supported_row_intercepts_px": supported_rows,
        "supported_column_intercepts_px": supported_columns,
        "strong_row_line_count": len(supported_rows),
        "strong_column_line_count": len(supported_columns),
        "per_pose": per_pose,
    }


def board_frame() -> tuple[np.ndarray, np.ndarray]:
    scene = json.loads(SCENE_REGISTRATION.read_text(encoding="utf-8"))
    corners = scene["target_binding"]["corners_mujoco_m"]
    origin = np.asarray(corners["a1"], dtype=np.float64)
    ex = np.asarray(corners["h1"], dtype=np.float64) - origin
    ey = np.asarray(corners["a8"], dtype=np.float64) - origin
    ex /= np.linalg.norm(ex)
    ey /= np.linalg.norm(ey)
    ez = np.cross(ex, ey)
    ez /= np.linalg.norm(ez)
    return origin, np.column_stack((ex, ey, ez))


def to_board(world: np.ndarray, origin: np.ndarray, basis: np.ndarray) -> np.ndarray:
    return (world - origin) @ basis


def square_symmetries() -> list[tuple[int, int, int, int]]:
    xy = np.asarray(((0, 0), (1, 0), (1, 1), (0, 1)), dtype=float)
    result = []
    for permutation in itertools.permutations(range(4)):
        lengths = [
            np.linalg.norm(
                xy[permutation[(index + 1) % 4]] - xy[permutation[index]]
            )
            for index in range(4)
        ]
        if max(lengths) - min(lengths) < 1e-12 and min(lengths) > 0.0:
            result.append(permutation)
    return sorted(result)


def solve_camera(
    side_m: float,
    permutation: tuple[int, int, int, int],
    image_corners: np.ndarray,
) -> dict[str, Any]:
    object_corners = np.asarray(
        ((0, 0, 0), (side_m, 0, 0), (side_m, side_m, 0), (0, side_m, 0)),
        dtype=np.float64,
    )
    objects = object_corners[list(permutation)]
    initial_k = np.asarray(((500, 0, 320), (0, 500, 240), (0, 0, 1)), float)
    ok, rvec, tvec = cv2.solvePnP(
        objects, image_corners, initial_k, None, flags=cv2.SOLVEPNP_ITERATIVE
    )
    if not ok:
        raise RuntimeError("conditional board camera initialization failed")

    def residual(parameters: np.ndarray) -> np.ndarray:
        focal = math.exp(float(parameters[0]))
        k = np.asarray(((focal, 0, 320), (0, focal, 240), (0, 0, 1)))
        projected, _ = cv2.projectPoints(
            objects, parameters[1:4], parameters[4:7], k, None
        )
        return (projected[:, 0] - image_corners).reshape(-1)

    result = least_squares(
        residual,
        np.r_[math.log(500.0), rvec[:, 0], tvec[:, 0]],
        bounds=(
            np.r_[math.log(250.0), [-math.pi] * 3, [-2.0, -2.0, 0.05]],
            np.r_[math.log(4000.0), [math.pi] * 3, [2.0, 2.0, 4.0]],
        ),
        max_nfev=1000,
    )
    singular = np.linalg.svd(result.jac, compute_uv=False)
    condition = float(singular[0] / singular[-1]) if singular[-1] else math.inf
    errors = residual(result.x).reshape(-1, 2)
    return {
        "side_m": side_m,
        "permutation": list(permutation),
        "focal_px": math.exp(float(result.x[0])),
        "rvec": result.x[1:4].tolist(),
        "tvec_m": result.x[4:7].tolist(),
        "corner_rmse_px": float(np.sqrt(np.mean(np.sum(errors**2, axis=1)))),
        "jacobian_condition_number": condition,
        "fit_bound_active": bool(
            abs(math.exp(float(result.x[0])) - 250.0) < 1e-3
            or abs(math.exp(float(result.x[0])) - 4000.0) < 1e-3
            or abs(result.x[6] - 0.05) < 1e-6
            or abs(result.x[6] - 4.0) < 1e-6
        ),
        "_jacobian_rank": int(np.linalg.matrix_rank(result.jac)),
    }


def project(points: np.ndarray, camera: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    rotation = Rotation.from_rotvec(camera["rvec"]).as_matrix()
    camera_points = points @ rotation.T + np.asarray(camera["tvec_m"])
    focal = camera["focal_px"]
    pixels = np.column_stack(
        (
            focal * camera_points[:, 0] / camera_points[:, 2] + 320.0,
            focal * camera_points[:, 1] / camera_points[:, 2] + 240.0,
        )
    )
    return pixels, camera_points[:, 2]


def apply_delta(points: np.ndarray, parameters: np.ndarray) -> np.ndarray:
    rotation = Rotation.from_rotvec(parameters[:3]).as_matrix()
    return points @ rotation.T + parameters[3:]


def body_hull_samples(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    origin: np.ndarray,
    basis: np.ndarray,
    camera: dict[str, Any],
    bodies: set[str] | None,
    samples_per_edge: int = 5,
) -> np.ndarray:
    samples: list[np.ndarray] = []
    for geom_id in _visual_geom_ids(model):
        body_name = mujoco.mj_id2name(
            model,
            mujoco.mjtObj.mjOBJ_BODY,
            int(model.geom_bodyid[geom_id]),
        )
        if bodies is not None and body_name not in bodies:
            continue
        points = to_board(
            _geom_world_vertices(model, data, geom_id), origin, basis
        )
        pixels, depth = project(points, camera)
        valid = (
            (depth > 0.02)
            & np.all(np.isfinite(pixels), axis=1)
            & (pixels[:, 0] > -200)
            & (pixels[:, 0] < 840)
            & (pixels[:, 1] > -200)
            & (pixels[:, 1] < 680)
        )
        if np.count_nonzero(valid) < 3:
            continue
        valid_points = points[valid]
        indices = cv2.convexHull(
            pixels[valid].astype(np.float32), returnPoints=False
        ).reshape(-1)
        hull = valid_points[indices]
        for first, second in zip(hull, np.roll(hull, -1, axis=0), strict=True):
            for alpha in np.linspace(0.0, 1.0, samples_per_edge, endpoint=False):
                samples.append((1.0 - alpha) * first + alpha * second)
    return np.asarray(samples, dtype=np.float64)


def distance_image(frame: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 55, 150)
    return distance_transform_edt(edges == 0)


def bilinear(distance: np.ndarray, pixels: np.ndarray) -> np.ndarray:
    height, width = distance.shape
    x = np.clip(pixels[:, 0], 0, width - 1.001)
    y = np.clip(pixels[:, 1], 0, height - 1.001)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    x1, y1 = x0 + 1, y0 + 1
    ax, ay = x - x0, y - y0
    values = (
        (1 - ax) * (1 - ay) * distance[y0, x0]
        + ax * (1 - ay) * distance[y0, x1]
        + (1 - ax) * ay * distance[y1, x0]
        + ax * ay * distance[y1, x1]
    )
    outside = (
        np.maximum(0.0, -pixels[:, 0])
        + np.maximum(0.0, pixels[:, 0] - (width - 1))
        + np.maximum(0.0, -pixels[:, 1])
        + np.maximum(0.0, pixels[:, 1] - (height - 1))
    )
    return np.minimum(EDGE_CLIP_PX, values + outside)


def edge_values(
    points: np.ndarray,
    parameters: np.ndarray,
    camera: dict[str, Any],
    distance: np.ndarray,
) -> np.ndarray:
    pixels, depth = project(apply_delta(points, parameters), camera)
    values = bilinear(distance, pixels)
    values[depth <= 0.02] = EDGE_CLIP_PX
    return values


def fit_base(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    config: dict[str, Any],
    observations: dict[str, dict[str, Any]],
    frames: dict[str, np.ndarray],
    origin: np.ndarray,
    basis: np.ndarray,
    camera: dict[str, Any],
) -> dict[str, Any]:
    distances = {name: distance_image(frames[name]) for name in FIT_POSES}
    points: dict[str, np.ndarray] = {}
    for name in FIT_POSES:
        _set_pose(
            model,
            data,
            config,
            np.asarray(observations[name]["joint_position_degrees"]),
            np.zeros(5),
        )
        points[name] = body_hull_samples(
            model, data, origin, basis, camera, BASE_BODIES, 8
        )
        if not len(points[name]):
            return {"status": "base_not_projected", "solutions": []}

    scale_rotation = math.radians(2.0)
    scale_translation = 0.01

    def residual(parameters: np.ndarray) -> np.ndarray:
        edge = np.concatenate(
            [
                edge_values(points[name], parameters, camera, distances[name])
                / 8.0
                for name in FIT_POSES
            ]
        )
        prior = np.r_[
            parameters[:3] / scale_rotation,
            parameters[3:] / scale_translation,
        ]
        return np.r_[edge, prior]

    starts = (
        np.zeros(6),
        np.asarray((0, 0, math.radians(2), 0.01, 0, 0)),
        np.asarray((0, 0, -math.radians(2), -0.01, 0, 0)),
        np.asarray((math.radians(2), 0, 0, 0, 0.01, 0)),
        np.asarray((-math.radians(2), 0, 0, 0, -0.01, 0)),
    )
    solutions = []
    for start in starts:
        result = least_squares(
            residual,
            start,
            bounds=(
                np.r_[[-math.radians(10)] * 3, [-0.05] * 3],
                np.r_[[math.radians(10)] * 3, [0.05] * 3],
            ),
            max_nfev=300,
        )
        edge = np.concatenate(
            [
                edge_values(
                    points[name], result.x, camera, distances[name]
                )
                for name in FIT_POSES
            ]
        )
        solutions.append(
            {
                "parameters": result.x.tolist(),
                "edge_median_px": float(np.median(edge)),
                "edge_p90_px": float(np.percentile(edge, 90)),
                "cost": float(result.cost),
            }
        )
    solutions.sort(key=lambda item: item["cost"])
    near = [
        item
        for item in solutions
        if item["cost"] <= solutions[0]["cost"] * 1.05 + 1e-9
    ]
    parameters = np.asarray([item["parameters"] for item in near])
    translation_spread = (
        float(
            np.max(
                np.linalg.norm(
                    parameters[:, None, 3:] - parameters[None, :, 3:], axis=2
                )
            )
            * 1000.0
        )
        if len(parameters) > 1
        else 0.0
    )
    rotation_spread = (
        float(
            np.degrees(
                np.max(
                    np.linalg.norm(
                        parameters[:, None, :3] - parameters[None, :, :3],
                        axis=2,
                    )
                )
            )
        )
        if len(parameters) > 1
        else 0.0
    )
    return {
        "status": "conditional_fit",
        "selected_parameters": solutions[0]["parameters"],
        "selected_edge_median_px": solutions[0]["edge_median_px"],
        "selected_edge_p90_px": solutions[0]["edge_p90_px"],
        "near_optimum_translation_spread_mm": translation_spread,
        "near_optimum_rotation_spread_degrees": rotation_spread,
        "fit_bound_active": bool(
            np.any(np.abs(np.asarray(solutions[0]["parameters"][:3])) > math.radians(9.99))
            or np.any(
                np.abs(np.asarray(solutions[0]["parameters"][3:])) > 0.0499
            )
        ),
        "solutions": solutions,
    }


def hypothesis_metrics(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    config: dict[str, Any],
    observations: dict[str, dict[str, Any]],
    frames: dict[str, np.ndarray],
    origin: np.ndarray,
    basis: np.ndarray,
    camera: dict[str, Any],
    base_parameters: np.ndarray,
    offsets: np.ndarray,
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in (*FIT_POSES, *VALIDATION_POSES):
        _set_pose(
            model,
            data,
            config,
            np.asarray(observations[name]["joint_position_degrees"]),
            offsets,
        )
        points = body_hull_samples(
            model, data, origin, basis, camera, None, 5
        )
        values = edge_values(
            points, base_parameters, camera, distance_image(frames[name])
        )
        result[name] = {
            "sample_count": int(len(values)),
            "median_px": float(np.median(values)),
            "p90_px": float(np.percentile(values, 90)),
            "clipped_rmse_px": float(np.sqrt(np.mean(values**2))),
        }
    return result


def recommend_pose_p(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    config: dict[str, Any],
    origin: np.ndarray,
    basis: np.ndarray,
    camera: dict[str, Any],
    base_parameters: np.ndarray,
    image_corners: np.ndarray,
) -> dict[str, Any]:
    start = np.asarray(
        (0.0, -106.11, 100.18, -100.18, -119.08, 2.494061757719715)
    )
    ranges = np.asarray(
        (
            (-120.26373626373626, 120.26373626373626),
            (-106.63736263736264, 106.63736263736264),
            (-102.10989010989012, 102.10989010989012),
            (-107.47252747252747, 107.47252747252747),
            (-180.0, 180.0),
        )
    )
    grid = itertools.product(
        (70.0, 80.0, 89.0),
        (-30.0, -25.0, -20.0, -16.5),
        (20.0, 40.0, 60.0, 80.0, 100.0),
        (-60.0, -40.0, -20.0, -10.25),
        (-60.0, -30.0),
    )

    def score_pose(pose: list[float], samples_per_edge: int) -> dict[str, Any]:
        _set_pose(
            model, data, config, np.asarray(pose), np.zeros(5)
        )
        robot_contacts = 0
        for contact_index in range(data.ncon):
            contact = data.contact[contact_index]
            bodies = [
                mujoco.mj_id2name(
                    model,
                    mujoco.mjtObj.mjOBJ_BODY,
                    int(model.geom_bodyid[geom_id]),
                )
                for geom_id in (contact.geom1, contact.geom2)
            ]
            if any(body and body.startswith("left_") for body in bodies):
                robot_contacts += 1
        points = body_hull_samples(
            model,
            data,
            origin,
            basis,
            camera,
            MOVING_BODIES,
            samples_per_edge,
        )
        adjusted = apply_delta(points, base_parameters)
        pixels, depth = project(adjusted, camera)
        visible = (
            (depth > 0.02)
            & (pixels[:, 0] >= 0)
            & (pixels[:, 0] < IMAGE_SIZE[0])
            & (pixels[:, 1] >= 0)
            & (pixels[:, 1] < IMAGE_SIZE[1])
        )
        inside = np.asarray(
            [
                cv2.pointPolygonTest(
                    image_corners.astype(np.float32), tuple(pixel), False
                )
                >= 0
                for pixel in pixels
            ]
        )
        visible_fraction = float(np.mean(visible)) if len(visible) else 0.0
        board_overlap_fraction = (
            float(np.mean(inside & visible)) if len(inside) else 1.0
        )
        score = (
            board_overlap_fraction
            + 0.5 * max(0.0, 0.65 - visible_fraction)
            + (10.0 if robot_contacts else 0.0)
        )
        return {
            "joint_position_degrees": pose,
            "excursion_from_repeated_start_degrees": (
                np.asarray(pose) - start
            ).tolist(),
            "maximum_absolute_stage_excursion_degrees": float(
                np.max(np.abs(np.asarray(pose)[:5] - start[:5]))
            ),
            "inside_calibrated_ranges": bool(
                np.all(np.asarray(pose)[:5] >= ranges[:, 0])
                and np.all(np.asarray(pose)[:5] <= ranges[:, 1])
            ),
            "moving_CAD_sample_count": int(len(pixels)),
            "moving_CAD_visible_fraction": visible_fraction,
            "moving_CAD_board_overlap_fraction": board_overlap_fraction,
            "MuJoCo_robot_contact_count": robot_contacts,
            "selection_score_lower_is_better": score,
            "projected_bbox_px": [
                float(np.min(pixels[:, 0])),
                float(np.min(pixels[:, 1])),
                float(np.max(pixels[:, 0])),
                float(np.max(pixels[:, 1])),
            ],
        }

    searched = []
    for values in grid:
        pose = [*values, float(start[5])]
        if np.max(np.abs(np.asarray(pose)[:5] - start[:5])) > 90.0:
            continue
        item = score_pose(pose, 1)
        if (
            item["MuJoCo_robot_contact_count"] == 0
            and item["inside_calibrated_ranges"]
        ):
            searched.append(item)
    searched.sort(key=lambda item: item["selection_score_lower_is_better"])
    selected = score_pose(searched[0]["joint_position_degrees"], 8)
    seed = score_pose(
        [80.0, -20.0, 40.0, -20.0, -30.0, float(start[5])], 8
    )
    unconstrained = score_pose(
        [100.0, 0.0, 40.0, 20.0, 0.0, float(start[5])], 8
    )
    return {
        "status": "simulation_only_no_motion_recommendation",
        "repeated_start_joint_position_degrees": start.tolist(),
        "constraints": {
            "maximum_absolute_per_joint_stage_excursion_degrees": 90.0,
            "calibrated_ranges_degrees": ranges.tolist(),
            "MuJoCo_robot_contact_count_required": 0,
        },
        "selected_single_stage_pose": selected,
        "requested_seed_pose": seed,
        "unconstrained_diagnostic_pose": unconstrained,
        "search_grid_candidate_count_after_constraints_and_contact_gate": len(
            searched
        ),
        "search_grid_best_reduced_scores": searched[:10],
        "execution_authority": False,
    }


def evaluate(output_directory: Path) -> dict[str, Any]:
    contract = load_contract()
    sources = contract["sources"]["observations"]
    frames: dict[str, np.ndarray] = {}
    extraction: dict[str, Any] = {}
    for name in (*FIT_POSES, *VALIDATION_POSES):
        frames[name], extraction[name] = validate_and_extract(
            name, sources[name]
        )

    image_corners = np.asarray(
        contract["board"]["initial_image_playing_corners_px"], dtype=np.float64
    )
    line_support = board_line_support(frames, image_corners)
    manifest = json.loads(
        (
            ROOT / contract["sources"]["exact_CAD_scene"]["path"]
        ).read_text(encoding="utf-8")
    )
    config = manifest["candidate_config"]
    model, _ = _compile_model(config, base_directory=None)
    data = mujoco.MjData(model)
    origin, basis = board_frame()

    nominal_side = contract["board"]["square_side_design_prior_mm"] * 8e-3
    candidates = []
    for permutation in square_symmetries():
        camera = solve_camera(nominal_side, permutation, image_corners)
        base = fit_base(
            model,
            data,
            config,
            extraction,
            frames,
            origin,
            basis,
            camera,
        )
        candidates.append(
            {
                "permutation": list(permutation),
                "camera": camera,
                "base": base,
                "ranking_cost": (
                    base["solutions"][0]["cost"]
                    if base.get("solutions")
                    else math.inf
                ),
            }
        )
    candidates.sort(key=lambda item: item["ranking_cost"])
    selected = candidates[0]
    camera = selected["camera"]
    base_parameters = np.asarray(selected["base"]["selected_parameters"])

    sensitivity = []
    selected_permutation = tuple(selected["permutation"])
    for square_mm in contract["board"]["sensitivity_square_side_mm"]:
        item = solve_camera(
            square_mm * 8e-3, selected_permutation, image_corners
        )
        sensitivity.append(
            {
                "square_side_mm": square_mm,
                "focal_px": item["focal_px"],
                "camera_translation_norm_m": float(
                    np.linalg.norm(item["tvec_m"])
                ),
                "corner_rmse_px": item["corner_rmse_px"],
            }
        )

    hypotheses = {}
    for name, key in (
        ("identity", "identity_joint_zero_offsets_degrees"),
        ("stage_d", "stage_d_joint_zero_offsets_degrees"),
    ):
        hypotheses[name] = hypothesis_metrics(
            model,
            data,
            config,
            extraction,
            frames,
            origin,
            basis,
            camera,
            base_parameters,
            np.asarray(contract["fixed_hypotheses"][key]),
        )

    gates = contract["gates"]
    validation_identity = hypotheses["identity"]["M"]
    validation_stage_d = hypotheses["stage_d"]["M"]
    winner = min(
        ("identity", "stage_d"),
        key=lambda name: hypotheses[name]["M"]["p90_px"],
    )
    loser = "stage_d" if winner == "identity" else "identity"
    winner_margin = (
        hypotheses[loser]["M"]["p90_px"]
        - hypotheses[winner]["M"]["p90_px"]
    )
    gate_results = {
        "direct_row_support": line_support["strong_row_line_count"]
        >= gates["minimum_directly_supported_lattice_lines_per_axis"],
        "direct_column_support": line_support["strong_column_line_count"]
        >= gates["minimum_directly_supported_lattice_lines_per_axis"],
        "frame_joint_alignment": all(
            abs(item["joint_time_delta_ms"])
            <= gates["maximum_joint_to_frame_delta_ms"]
            for item in extraction.values()
        ),
        "board_camera_coordinate_fit": camera["corner_rmse_px"]
        <= gates["maximum_board_coordinate_rmse_px"],
        "camera_condition": camera["jacobian_condition_number"]
        <= gates["maximum_camera_jacobian_condition_number"],
        "camera_fit_interior": not camera["fit_bound_active"],
        "base_translation_multistart": selected["base"][
            "near_optimum_translation_spread_mm"
        ]
        <= gates["maximum_base_multistart_translation_spread_mm"],
        "base_rotation_multistart": selected["base"][
            "near_optimum_rotation_spread_degrees"
        ]
        <= gates["maximum_base_multistart_rotation_spread_degrees"],
        "base_fit_interior": not selected["base"]["fit_bound_active"],
        "retrospective_validation_identity_edge": validation_identity["p90_px"]
        <= gates["retrospective_validation_identity_p90_max_px"],
        "retrospective_validation_hypothesis_margin": winner_margin
        >= gates["retrospective_validation_winner_margin_min_px"],
        "future_heldout": bool(contract["split"]["future_heldout_poses"]),
    }
    failed = [name for name, passed in gate_results.items() if not passed]
    status = (
        "conditional_candidate_all_gates_passed"
        if not failed
        else "identifiability_failed_no_P13_candidate"
    )

    pose_p = recommend_pose_p(
        model,
        data,
        config,
        origin,
        basis,
        camera,
        base_parameters,
        image_corners,
    )
    selected_pose = pose_p["selected_single_stage_pose"][
        "joint_position_degrees"
    ]
    _set_pose(
        model,
        data,
        config,
        np.asarray(selected_pose),
        np.zeros(5),
    )
    preview_points = body_hull_samples(
        model, data, origin, basis, camera, MOVING_BODIES, 3
    )
    preview_pixels, preview_depth = project(
        apply_delta(preview_points, base_parameters), camera
    )
    preview = frames["M"].copy()
    cv2.polylines(
        preview,
        [image_corners.astype(np.int32)],
        True,
        (40, 220, 40),
        2,
    )
    for pixel, depth in zip(preview_pixels, preview_depth, strict=True):
        if (
            depth > 0.02
            and 0 <= pixel[0] < IMAGE_SIZE[0]
            and 0 <= pixel[1] < IMAGE_SIZE[1]
        ):
            cv2.circle(
                preview,
                tuple(np.rint(pixel).astype(int)),
                1,
                (40, 40, 240),
                -1,
            )
    cv2.putText(
        preview,
        "sim-only pose P CAD projection",
        (12, 26),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (30, 30, 240),
        2,
        cv2.LINE_AA,
    )
    result = {
        "schema_version": "sim2claw.current_c922_board_base_registration.result.v1",
        "status": status,
        "proof_class": contract["proof_class"],
        "contract_sha256": sha256(CONTRACT),
        "contract_digest": canonical_digest(contract),
        "split": contract["split"],
        "extraction": extraction,
        "board_observability": line_support,
        "conditional_camera": camera,
        "square_side_sensitivity": sensitivity,
        "d4_candidates": candidates,
        "conditional_base": selected["base"],
        "hypotheses": hypotheses,
        "retrospective_validation": {
            "winner_by_p90_only": winner,
            "winner_margin_px": winner_margin,
            "identity_p90_px": validation_identity["p90_px"],
            "stage_d_p90_px": validation_stage_d["p90_px"],
            "promotion_interpretation": "none_without_all_gates_and_future_heldout",
        },
        "gate_results": gate_results,
        "failed_gates": failed,
        "terminal_missing_data": [
            "direct support for at least seven playing-lattice lines on each axis without extrapolation",
            "independently measured board square side or another metric anchor",
            "nonplanar intrinsic/distortion calibration",
            "one unopened future heldout pose after candidate freeze",
        ],
        "recommended_future_pose_P": pose_p,
        "authority": contract["authority"],
    }
    output_directory.mkdir(parents=True, exist_ok=True)
    for name, frame in frames.items():
        cv2.imwrite(str(output_directory / f"{name}-exact.png"), frame)
    cv2.imwrite(str(output_directory / "pose-P-preview.png"), preview)
    (output_directory / "evaluation.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT
        / "runs/c922-board-base-registration/20260726-current-c922-v1",
    )
    args = parser.parse_args()
    result = evaluate(args.output)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
