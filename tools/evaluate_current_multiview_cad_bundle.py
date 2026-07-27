#!/usr/bin/env python3
"""Evaluate current H/I/D C922 and Pi observations against the exact SO-101 CAD.

This is a bounded, retrospective diagnostic.  H and I are the fit views and D
is opened only for the final score.  The tool never writes simulator
parameters, moves hardware, or promotes a candidate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import cv2
import mujoco
import numpy as np
from scipy.ndimage import distance_transform_edt
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

from sim2claw.physical_canary import _physical_to_model_position
from sim2claw.recorded_replay import _compile_model
from tools.fit_pi_dual_link_tag_bundle import transform


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT / "configs/evaluations/current_multiview_cad_bundle_v1.json"
)
FROZEN_CANDIDATE = (
    ROOT
    / "runs/pi-link-tag-calibration/"
    "20260726-current-three-link-fresh-validation-v1/candidate.json"
)
SCENE_REGISTRATION = (
    ROOT / "configs/evaluations/img5349_3dgs_board_registration_v1.json"
)
SCENE_MANIFEST = (
    ROOT
    / "runs/physical_excitation/20260725-follower-only-v1/"
    "simulation-canary-v1/candidate_manifest.json"
)
POSE_DIRECTORIES = {
    "H": ROOT
    / "runs/pi-link-tag-calibration/"
    "20260726-new-scene-tags-pose-h-v1/stage-1",
    "I": ROOT
    / "runs/pi-link-tag-calibration/"
    "20260726-new-scene-tags-pose-i-v1/stage-1",
    "D": ROOT
    / "runs/pi-link-tag-calibration/"
    "20260726-new-scene-tags-pose-d-v1/stage-1",
}
FIT_POSES = ("H", "I")
HELDOUT_POSE = "D"
PI_DICTIONARY = cv2.aruco.getPredefinedDictionary(
    cv2.aruco.DICT_APRILTAG_36h11
)
C922_IMAGE_SIZE = (1920, 1080)
PI_IMAGE_SIZE = (1536, 864)
TAG_IDS = (0, 1, 2)
TAG_BODY = {0: "left_shoulder", 1: "left_upper_arm", 2: "left_wrist"}
TAG_EDGE_M = 0.02
GRID_ROI_XYXY = (280, 180, 1400, 740)
ROW_ANGLE_DEGREES = (-10.0, 6.0)
COLUMN_ANGLE_DEGREES = (40.0, 88.0)
ROW_REFERENCE_X = 700.0
COLUMN_REFERENCE_Y = 450.0
ROW_INTERCEPT_RANGE = (200.0, 730.0)
COLUMN_INTERCEPT_RANGE = (300.0, 1250.0)
GRID_CLUSTER_TOLERANCE_PX = 7.0
GRID_LINE_COUNT = 9
C922_FOCAL_BOUNDS_PX = (600.0, 4000.0)
VISUAL_GEOM_GROUP = 2
LEFT_VISUAL_PREFIX = "left_"
CAD_EDGE_CLIP_PX = 60.0


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def load_and_validate_contract() -> dict[str, Any]:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if (
        contract.get("schema_version")
        != "sim2claw.current_multiview_cad_bundle_contract.v1"
        or contract.get("status")
        != "source_bindings_frozen_for_bounded_rerun"
        or contract.get("split", {}).get("fit_poses") != list(FIT_POSES)
        or contract.get("split", {}).get("heldout_pose") != HELDOUT_POSE
    ):
        raise RuntimeError("multiview CAD contract changed")
    sources = contract.get("sources") or {}
    fixed = {
        "frozen_three_tag_candidate": FROZEN_CANDIDATE,
        "frozen_three_tag_heldout_evaluation": (
            FROZEN_CANDIDATE.parent / "heldout-evaluation.json"
        ),
        "scene_board_registration": SCENE_REGISTRATION,
        "compiled_scene_manifest": SCENE_MANIFEST,
    }
    for name, path in fixed.items():
        source = sources.get(name) or {}
        if (
            source.get("path") != str(path.relative_to(ROOT))
            or source.get("sha256") != sha256(path)
        ):
            raise RuntimeError(f"frozen source binding changed: {name}")
    for pose_name, directory in POSE_DIRECTORIES.items():
        expected = (sources.get("poses") or {}).get(pose_name) or {}
        actual = {
            "execution_receipt_sha256": sha256(
                directory / "execution_receipt.json"
            ),
            "pi_imx708_sha256": sha256(
                directory / "pi_imx708_torque_on_hold.jpg"
            ),
            "c922_1920x1080_sha256": sha256(
                directory / "c922_1920x1080_torque_off.png"
            ),
        }
        if expected != actual:
            raise RuntimeError(
                f"frozen pose binding changed: {pose_name}"
            )
    return contract


def _segment_angle_degrees(segment: np.ndarray) -> float:
    x1, y1, x2, y2 = (float(value) for value in segment)
    angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
    while angle >= 90.0:
        angle -= 180.0
    while angle < -90.0:
        angle += 180.0
    return angle


def _fit_tls_line(points: np.ndarray) -> np.ndarray:
    if points.shape[0] < 4 or points.shape[1] != 2:
        raise RuntimeError("too few endpoints for a grid line")
    center = np.mean(points, axis=0)
    _u, _s, vh = np.linalg.svd(points - center, full_matrices=False)
    direction = vh[0]
    normal = np.asarray((-direction[1], direction[0]), dtype=np.float64)
    normal /= np.linalg.norm(normal)
    line = np.asarray((normal[0], normal[1], -normal @ center))
    if line[1] < 0.0 or (
        abs(float(line[1])) < 1e-12 and line[0] < 0.0
    ):
        line *= -1.0
    return line


def _line_intersection(first: np.ndarray, second: np.ndarray) -> np.ndarray:
    value = np.cross(first, second)
    if abs(float(value[2])) <= 1e-9:
        raise RuntimeError("parallel grid lines")
    return value[:2] / value[2]


@dataclass(frozen=True)
class SegmentRow:
    family: str
    intercept: float
    length: float
    pose: str
    segment: np.ndarray


def _hough_rows(pose: str, image: np.ndarray) -> list[SegmentRow]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    x0, y0, x1, y1 = GRID_ROI_XYXY
    masked = np.zeros_like(edges)
    masked[y0:y1, x0:x1] = edges[y0:y1, x0:x1]
    raw = cv2.HoughLinesP(
        masked,
        rho=1.0,
        theta=math.radians(0.1),
        threshold=45,
        minLineLength=45.0,
        maxLineGap=15.0,
    )
    if raw is None:
        raise RuntimeError(f"C922 pose {pose} has no Hough segments")
    rows: list[SegmentRow] = []
    for segment in np.asarray(raw, dtype=np.float64).reshape(-1, 4):
        x_start, y_start, x_end, y_end = segment
        length = float(
            math.hypot(x_end - x_start, y_end - y_start)
        )
        angle = _segment_angle_degrees(segment)
        if (
            ROW_ANGLE_DEGREES[0] <= angle <= ROW_ANGLE_DEGREES[1]
            and abs(x_end - x_start) > 1e-9
        ):
            intercept = y_start + (y_end - y_start) * (
                ROW_REFERENCE_X - x_start
            ) / (x_end - x_start)
            if ROW_INTERCEPT_RANGE[0] < intercept < ROW_INTERCEPT_RANGE[1]:
                rows.append(
                    SegmentRow("row", float(intercept), length, pose, segment)
                )
        if (
            COLUMN_ANGLE_DEGREES[0]
            <= angle
            <= COLUMN_ANGLE_DEGREES[1]
            and abs(y_end - y_start) > 1e-9
        ):
            intercept = x_start + (x_end - x_start) * (
                COLUMN_REFERENCE_Y - y_start
            ) / (y_end - y_start)
            if (
                COLUMN_INTERCEPT_RANGE[0]
                < intercept
                < COLUMN_INTERCEPT_RANGE[1]
            ):
                rows.append(
                    SegmentRow(
                        "column", float(intercept), length, pose, segment
                    )
                )
    return rows


def cluster_segments(
    rows: Iterable[SegmentRow],
    *,
    tolerance_px: float = GRID_CLUSTER_TOLERANCE_PX,
) -> list[list[SegmentRow]]:
    ordered = sorted(rows, key=lambda row: row.intercept)
    clusters: list[list[SegmentRow]] = []
    for row in ordered:
        if not clusters:
            clusters.append([row])
            continue
        center = float(
            np.average(
                [item.intercept for item in clusters[-1]],
                weights=[item.length for item in clusters[-1]],
            )
        )
        if row.intercept - center > tolerance_px:
            clusters.append([row])
        else:
            clusters[-1].append(row)
    return clusters


def _select_grid_clusters(
    rows: list[SegmentRow], family: str
) -> list[list[SegmentRow]]:
    clusters = cluster_segments(row for row in rows if row.family == family)
    ranked = sorted(
        clusters,
        key=lambda cluster: sum(row.length for row in cluster),
        reverse=True,
    )
    selected = sorted(
        ranked[:GRID_LINE_COUNT],
        key=lambda cluster: float(
            np.average(
                [row.intercept for row in cluster],
                weights=[row.length for row in cluster],
            )
        ),
    )
    if len(selected) != GRID_LINE_COUNT:
        raise RuntimeError(f"did not recover {GRID_LINE_COUNT} {family} lines")
    centers = np.asarray(
        [
            np.average(
                [row.intercept for row in cluster],
                weights=[row.length for row in cluster],
            )
            for cluster in selected
        ],
        dtype=np.float64,
    )
    gaps = np.diff(centers)
    limits = (25.0, 95.0) if family == "row" else (60.0, 145.0)
    if np.any(gaps < limits[0]) or np.any(gaps > limits[1]):
        raise RuntimeError(
            f"{family} grid spacing rejected: {gaps.tolist()}"
        )
    return selected


def detect_c922_grid(
    images: dict[str, np.ndarray],
) -> tuple[np.ndarray, dict[str, Any]]:
    rows = [
        row
        for pose in FIT_POSES
        for row in _hough_rows(pose, images[pose])
    ]
    row_clusters = _select_grid_clusters(rows, "row")
    column_clusters = _select_grid_clusters(rows, "column")
    row_lines = [
        _fit_tls_line(
            np.asarray(
                [row.segment for row in cluster], dtype=np.float64
            ).reshape(-1, 2)
        )
        for cluster in row_clusters
    ]
    column_lines = [
        _fit_tls_line(
            np.asarray(
                [row.segment for row in cluster], dtype=np.float64
            ).reshape(-1, 2)
        )
        for cluster in column_clusters
    ]
    grid = np.asarray(
        [
            [
                _line_intersection(row_line, column_line)
                for column_line in column_lines
            ]
            for row_line in row_lines
        ],
        dtype=np.float64,
    )

    def cluster_receipt(cluster: list[SegmentRow]) -> dict[str, Any]:
        return {
            "intercept_px": float(
                np.average(
                    [row.intercept for row in cluster],
                    weights=[row.length for row in cluster],
                )
            ),
            "segment_count": len(cluster),
            "total_segment_length_px": float(
                sum(row.length for row in cluster)
            ),
            "poses": sorted({row.pose for row in cluster}),
        }

    return grid, {
        "method": "H_I_Canny_Hough_TLS_9x9_playing_grid",
        "roi_xyxy": list(GRID_ROI_XYXY),
        "row_clusters": [cluster_receipt(row) for row in row_clusters],
        "column_clusters": [
            cluster_receipt(row) for row in column_clusters
        ],
        "grid_points_px": grid.tolist(),
    }


def _image_edge_distance(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (3, 3), 0), 60, 160)
    return distance_transform_edt(edges == 0).astype(np.float64)


def sample_distance(
    distance: np.ndarray, pixels: np.ndarray, clip_px: float
) -> np.ndarray:
    rounded = np.rint(pixels).astype(np.int64)
    height, width = distance.shape
    valid = (
        (rounded[:, 0] >= 0)
        & (rounded[:, 0] < width)
        & (rounded[:, 1] >= 0)
        & (rounded[:, 1] < height)
    )
    values = np.full(len(pixels), clip_px, dtype=np.float64)
    values[valid] = distance[rounded[valid, 1], rounded[valid, 0]]
    return np.minimum(values, clip_px)


def d4_corner_orders() -> list[tuple[str, ...]]:
    perimeter = ("a1", "h1", "h8", "a8")
    result: list[tuple[str, ...]] = []
    for reverse in (False, True):
        base = perimeter if not reverse else tuple(reversed(perimeter))
        for offset in range(4):
            result.append(base[offset:] + base[:offset])
    return result


def world_grid(
    corners: dict[str, list[float]], order: tuple[str, ...]
) -> np.ndarray:
    top_left, top_right, bottom_right, bottom_left = (
        np.asarray(corners[name], dtype=np.float64) for name in order
    )
    rows = []
    for row in range(GRID_LINE_COUNT):
        v = row / (GRID_LINE_COUNT - 1)
        left = (1.0 - v) * top_left + v * bottom_left
        right = (1.0 - v) * top_right + v * bottom_right
        rows.append(
            [
                (1.0 - column / (GRID_LINE_COUNT - 1)) * left
                + (column / (GRID_LINE_COUNT - 1)) * right
                for column in range(GRID_LINE_COUNT)
            ]
        )
    return np.asarray(rows, dtype=np.float64)


def _camera_matrix(focal: float) -> np.ndarray:
    return np.asarray(
        (
            (focal, 0.0, C922_IMAGE_SIZE[0] / 2.0),
            (0.0, focal, C922_IMAGE_SIZE[1] / 2.0),
            (0.0, 0.0, 1.0),
        ),
        dtype=np.float64,
    )


def project_points(
    points_world: np.ndarray, camera_world: np.ndarray, focal: float
) -> np.ndarray:
    homogeneous = np.column_stack(
        (points_world, np.ones(len(points_world), dtype=np.float64))
    )
    camera = (camera_world @ homogeneous.T).T[:, :3]
    normalized = camera[:, :2] / camera[:, 2:3]
    return np.column_stack(
        (
            focal * normalized[:, 0] + C922_IMAGE_SIZE[0] / 2.0,
            focal * normalized[:, 1] + C922_IMAGE_SIZE[1] / 2.0,
        )
    )


def fit_board_camera(
    points_world: np.ndarray, points_pixels: np.ndarray
) -> tuple[np.ndarray, float, dict[str, Any]]:
    world = points_world.reshape(-1, 3).astype(np.float64)
    pixels = points_pixels.reshape(-1, 2).astype(np.float64)
    fixed_focal = 1500.0
    fixed_success, fixed_rotation, fixed_translation = cv2.solvePnP(
        world,
        pixels,
        _camera_matrix(fixed_focal),
        np.zeros(5),
        flags=cv2.SOLVEPNP_ITERATIVE,
    )
    if not fixed_success:
        raise RuntimeError("fixed-focal C922 board seed failed")
    fixed_projected, _ = cv2.projectPoints(
        world,
        fixed_rotation,
        fixed_translation,
        _camera_matrix(fixed_focal),
        np.zeros(5),
    )
    fixed_errors = np.linalg.norm(
        fixed_projected.reshape(-1, 2) - pixels, axis=1
    )
    best: tuple[np.ndarray, float, float, np.ndarray] | None = None
    for focal in np.geomspace(
        C922_FOCAL_BOUNDS_PX[0], C922_FOCAL_BOUNDS_PX[1], 20
    ):
        success, rotation, translation = cv2.solvePnP(
            world,
            pixels,
            _camera_matrix(float(focal)),
            np.zeros(5),
            flags=cv2.SOLVEPNP_ITERATIVE,
        )
        if not success:
            continue
        vector = np.concatenate(
            (
                [math.log(float(focal))],
                rotation.reshape(3),
                translation.reshape(3),
            )
        )

        def residual(parameters: np.ndarray) -> np.ndarray:
            estimate, _ = cv2.projectPoints(
                world,
                parameters[1:4],
                parameters[4:7],
                _camera_matrix(math.exp(float(parameters[0]))),
                np.zeros(5),
            )
            return (estimate.reshape(-1, 2) - pixels).ravel()

        result = least_squares(
            residual,
            vector,
            bounds=(
                np.asarray(
                    [
                        math.log(C922_FOCAL_BOUNDS_PX[0]),
                        -math.pi,
                        -math.pi,
                        -math.pi,
                        -4.0,
                        -4.0,
                        -4.0,
                    ]
                ),
                np.asarray(
                    [
                        math.log(C922_FOCAL_BOUNDS_PX[1]),
                        math.pi,
                        math.pi,
                        math.pi,
                        4.0,
                        4.0,
                        4.0,
                    ]
                ),
            ),
            loss="soft_l1",
            f_scale=1.0,
            max_nfev=600,
        )
        rms = float(np.sqrt(np.mean(residual(result.x) ** 2)))
        if best is None or rms < best[2]:
            camera = transform(result.x[1:4], result.x[4:7])
            best = (
                camera,
                math.exp(float(result.x[0])),
                rms,
                result.jac,
            )
    if best is None:
        raise RuntimeError("C922 board-conditioned camera solve failed")
    camera, focal, coordinate_rms, jacobian = best
    errors = np.linalg.norm(
        project_points(world, camera, focal) - pixels, axis=1
    )
    return camera, focal, {
        "coordinate_rms_px": coordinate_rms,
        "point_rmse_px": float(np.sqrt(np.mean(errors**2))),
        "point_max_px": float(np.max(errors)),
        "fixed_focal_1500_before": {
            "point_rmse_px": float(
                np.sqrt(np.mean(fixed_errors**2))
            ),
            "point_max_px": float(np.max(fixed_errors)),
        },
        "optimized_seven_parameter_identifiability": _family_rank(
            jacobian, 7
        ),
    }


def _visual_geom_ids(model: mujoco.MjModel) -> list[int]:
    result: list[int] = []
    for geom_id in range(model.ngeom):
        if int(model.geom_group[geom_id]) != VISUAL_GEOM_GROUP:
            continue
        body_id = int(model.geom_bodyid[geom_id])
        name = mujoco.mj_id2name(
            model, mujoco.mjtObj.mjOBJ_BODY, body_id
        )
        if (
            name
            and name.startswith(LEFT_VISUAL_PREFIX)
            and int(model.geom_type[geom_id])
            == int(mujoco.mjtGeom.mjGEOM_MESH)
        ):
            result.append(geom_id)
    return result


def _geom_local_vertices(
    model: mujoco.MjModel, geom_id: int
) -> np.ndarray:
    mesh_id = int(model.geom_dataid[geom_id])
    start = int(model.mesh_vertadr[mesh_id])
    count = int(model.mesh_vertnum[mesh_id])
    return np.asarray(
        model.mesh_vert[start : start + count], dtype=np.float64
    )


def _set_pose(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    config: dict[str, Any],
    joint_degrees: np.ndarray,
    offsets_degrees: np.ndarray,
) -> None:
    physical = joint_degrees.copy()
    physical[:5] += offsets_degrees
    model_position = _physical_to_model_position(
        physical[None, :], config
    )[0]
    for index, name in enumerate(config["bindings"]["joint_names"]):
        joint_id = mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_JOINT, name
        )
        data.qpos[int(model.jnt_qposadr[joint_id])] = model_position[index]
    data.qvel[:] = 0.0
    mujoco.mj_forward(model, data)


def _geom_world_vertices(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    geom_id: int,
) -> np.ndarray:
    local = _geom_local_vertices(model, geom_id)
    rotation = data.geom_xmat[geom_id].reshape(3, 3)
    return local @ rotation.T + data.geom_xpos[geom_id]


def cad_hull_samples(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    camera_world: np.ndarray,
    focal: float,
    *,
    samples_per_edge: int = 5,
) -> np.ndarray:
    samples: list[np.ndarray] = []
    for geom_id in _visual_geom_ids(model):
        world = _geom_world_vertices(model, data, geom_id)
        pixels = project_points(world, camera_world, focal)
        camera_depth = (
            camera_world
            @ np.column_stack((world, np.ones(len(world)))).T
        )[2]
        valid = (
            (camera_depth > 1e-5)
            & np.all(np.isfinite(pixels), axis=1)
            & (pixels[:, 0] > -100)
            & (pixels[:, 0] < C922_IMAGE_SIZE[0] + 100)
            & (pixels[:, 1] > -100)
            & (pixels[:, 1] < C922_IMAGE_SIZE[1] + 100)
        )
        if int(np.count_nonzero(valid)) < 3:
            continue
        valid_world = world[valid]
        valid_pixels = pixels[valid].astype(np.float32)
        hull_indices = cv2.convexHull(
            valid_pixels, returnPoints=False
        ).reshape(-1)
        if len(hull_indices) < 3:
            continue
        hull_world = valid_world[hull_indices]
        for first, second in zip(
            hull_world, np.roll(hull_world, -1, axis=0), strict=True
        ):
            for alpha in np.linspace(
                0.0, 1.0, samples_per_edge, endpoint=False
            ):
                samples.append((1.0 - alpha) * first + alpha * second)
    if not samples:
        raise RuntimeError("no projected C922 CAD hull samples")
    return np.asarray(samples, dtype=np.float64)


def edge_metrics(distance: np.ndarray, pixels: np.ndarray) -> dict[str, float]:
    values = sample_distance(distance, pixels, CAD_EDGE_CLIP_PX)
    return {
        "sample_count": int(len(values)),
        "median_px": float(np.median(values)),
        "p80_px": float(np.percentile(values, 80)),
        "trimmed_rmse_px": float(
            np.sqrt(
                np.mean(
                    np.sort(values)[
                        : max(1, int(math.ceil(0.8 * len(values))))
                    ]
                    ** 2
                )
            )
        ),
        "clipped_rmse_px": float(np.sqrt(np.mean(values**2))),
    }


def _tag_local_points() -> np.ndarray:
    half = TAG_EDGE_M / 2.0
    return np.asarray(
        (
            (-half, half, 0.0, 1.0),
            (half, half, 0.0, 1.0),
            (half, -half, 0.0, 1.0),
            (-half, -half, 0.0, 1.0),
        ),
        dtype=np.float64,
    ).T


def detect_pi_tags(image: np.ndarray) -> dict[int, np.ndarray]:
    detector = cv2.aruco.ArucoDetector(PI_DICTIONARY)
    corners, identifiers, _ = detector.detectMarkers(image)
    if identifiers is None:
        return {}
    found: dict[int, list[np.ndarray]] = {}
    for identifier, corner in zip(
        identifiers.ravel(), corners, strict=True
    ):
        tag_id = int(identifier)
        if (
            tag_id in TAG_IDS
            and float(np.mean(corner[0, :, 1])) < 450.0
        ):
            found.setdefault(tag_id, []).append(
                corner[0].astype(np.float64)
            )
    return {
        tag_id: rows[0]
        for tag_id, rows in found.items()
        if len(rows) == 1
    }


def body_pose(
    model: mujoco.MjModel, data: mujoco.MjData, body_name: str
) -> np.ndarray:
    body_id = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_BODY, body_name
    )
    value = np.eye(4)
    value[:3, :3] = data.xmat[body_id].reshape(3, 3)
    value[:3, 3] = data.xpos[body_id]
    return value


def pi_tag_projection(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    candidate: dict[str, Any],
    tag_id: int,
    *,
    base_delta: np.ndarray | None = None,
    mount_delta: np.ndarray | None = None,
    camera_delta: np.ndarray | None = None,
) -> np.ndarray:
    parameters = candidate["parameters"]
    mount = parameters["tag_mounts"][str(tag_id)]
    body_tag = transform(
        mount["body_tag_rotation_vector_radians"],
        mount["body_tag_translation_m"],
    )
    if mount_delta is not None:
        body_tag = body_tag @ mount_delta
    world_tag = body_pose(model, data, TAG_BODY[tag_id]) @ body_tag
    if base_delta is not None:
        world_tag = base_delta @ world_tag
    camera = transform(
        parameters["camera_world_rotation_vector_radians"],
        parameters["camera_world_translation_m"],
    )
    if camera_delta is not None:
        camera = camera_delta @ camera
    points = (camera @ world_tag @ _tag_local_points())[:3]
    focal = float(candidate["intrinsics"]["focal_pixels"])
    normalized = points[:2] / points[2:3]
    return np.column_stack(
        (
            focal * normalized[0] + PI_IMAGE_SIZE[0] / 2.0,
            focal * normalized[1] + PI_IMAGE_SIZE[1] / 2.0,
        )
    )


def pi_metrics(
    projections: dict[int, np.ndarray],
    observed: dict[int, np.ndarray],
) -> dict[str, Any]:
    common = sorted(set(projections) & set(observed))
    if not common:
        return {
            "tag_ids": [],
            "corner_count": 0,
            "corner_rmse_px": None,
            "corner_max_px": None,
            "by_tag": {},
        }
    errors = {
        tag_id: np.linalg.norm(
            projections[tag_id] - observed[tag_id], axis=1
        )
        for tag_id in common
    }
    combined = np.concatenate(list(errors.values()))
    return {
        "tag_ids": common,
        "corner_count": int(len(combined)),
        "corner_rmse_px": float(np.sqrt(np.mean(combined**2))),
        "corner_max_px": float(np.max(combined)),
        "by_tag": {
            str(tag_id): {
                "corner_rmse_px": float(
                    np.sqrt(np.mean(values**2))
                ),
                "corner_max_px": float(np.max(values)),
            }
            for tag_id, values in errors.items()
        },
    }


def _pose_projection_metrics(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    config: dict[str, Any],
    pose: dict[str, Any],
    candidate: dict[str, Any],
    c922_camera: np.ndarray,
    c922_focal: float,
    *,
    offset_delta_degrees: np.ndarray | None = None,
    base_delta: np.ndarray | None = None,
    mount_deltas: dict[int, np.ndarray] | None = None,
    pi_camera_delta: np.ndarray | None = None,
) -> dict[str, Any]:
    frozen_offsets = np.asarray(
        candidate["parameters"]["joint_zero_offsets_degrees"],
        dtype=np.float64,
    )
    if offset_delta_degrees is not None:
        frozen_offsets = frozen_offsets + offset_delta_degrees
    _set_pose(
        model,
        data,
        config,
        pose["joint_degrees"],
        frozen_offsets,
    )
    tag_projection = {
        tag_id: pi_tag_projection(
            model,
            data,
            candidate,
            tag_id,
            base_delta=base_delta,
            mount_delta=None
            if mount_deltas is None
            else mount_deltas.get(tag_id),
            camera_delta=pi_camera_delta,
        )
        for tag_id in pose["pi_tags"]
    }
    samples = cad_hull_samples(model, data, c922_camera, c922_focal)
    if base_delta is not None:
        homogeneous = np.column_stack(
            (samples, np.ones(len(samples), dtype=np.float64))
        )
        samples = (base_delta @ homogeneous.T).T[:, :3]
    c922_pixels = project_points(samples, c922_camera, c922_focal)
    return {
        "pi": pi_metrics(tag_projection, pose["pi_tags"]),
        "c922_cad_edge": edge_metrics(
            pose["c922_distance"], c922_pixels
        ),
    }


def _family_rank(
    jacobian: np.ndarray, parameter_count: int
) -> dict[str, Any]:
    singular = np.linalg.svd(jacobian, compute_uv=False)
    threshold = (
        max(jacobian.shape)
        * np.finfo(np.float64).eps
        * float(singular[0])
        if len(singular)
        else 0.0
    )
    rank = int(np.count_nonzero(singular > threshold))
    condition = (
        float(singular[0] / singular[-1])
        if len(singular) and singular[-1] > threshold
        else None
    )
    return {
        "parameter_count": parameter_count,
        "numerical_rank": rank,
        "full_rank": rank == parameter_count,
        "condition_number": condition,
        "singular_values": singular.tolist(),
    }


def _pi_residuals(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    config: dict[str, Any],
    poses: dict[str, dict[str, Any]],
    candidate: dict[str, Any],
    *,
    offset_delta_degrees: np.ndarray | None = None,
    base_delta: np.ndarray | None = None,
    mount_deltas: dict[int, np.ndarray] | None = None,
    pi_camera_delta: np.ndarray | None = None,
) -> np.ndarray:
    frozen_offsets = np.asarray(
        candidate["parameters"]["joint_zero_offsets_degrees"],
        dtype=np.float64,
    )
    if offset_delta_degrees is not None:
        frozen_offsets = frozen_offsets + offset_delta_degrees
    residuals: list[np.ndarray] = []
    for pose_name in FIT_POSES:
        pose = poses[pose_name]
        _set_pose(
            model,
            data,
            config,
            pose["joint_degrees"],
            frozen_offsets,
        )
        for tag_id in sorted(pose["pi_tags"]):
            projected = pi_tag_projection(
                model,
                data,
                candidate,
                tag_id,
                base_delta=base_delta,
                mount_delta=None
                if mount_deltas is None
                else mount_deltas.get(tag_id),
                camera_delta=pi_camera_delta,
            )
            residuals.append(
                (projected - pose["pi_tags"][tag_id]).ravel()
            )
    return np.concatenate(residuals)


def fit_parameter_families(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    config: dict[str, Any],
    poses: dict[str, dict[str, Any]],
    candidate: dict[str, Any],
    c922_camera: np.ndarray,
    c922_focal: float,
) -> dict[str, Any]:
    baseline = {
        pose: _pose_projection_metrics(
            model,
            data,
            config,
            poses[pose],
            candidate,
            c922_camera,
            c922_focal,
        )
        for pose in (*FIT_POSES, HELDOUT_POSE)
    }

    def family_receipt(
        name: str,
        result: Any,
        parameter_vector: np.ndarray,
        fit_metrics: dict[str, Any],
        heldout_metrics: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "family": name,
            "fit": {
                "success": bool(result.success),
                "cost": float(result.cost),
                "optimality": float(result.optimality),
                "parameter_vector": parameter_vector.tolist(),
                "identifiability": _family_rank(
                    result.jac, len(parameter_vector)
                ),
                "pose_metrics": fit_metrics,
            },
            "heldout_pose_D": heldout_metrics,
        }

    def joint_residual(delta: np.ndarray) -> np.ndarray:
        pixels = _pi_residuals(
            model,
            data,
            config,
            poses,
            candidate,
            offset_delta_degrees=delta,
        )
        return np.concatenate((pixels, delta / 1.0))

    joint_result = least_squares(
        joint_residual,
        np.zeros(5),
        bounds=(-5.0, 5.0),
        loss="soft_l1",
        f_scale=2.0,
        max_nfev=400,
    )
    joint_fit_metrics = {
        pose: _pose_projection_metrics(
            model,
            data,
            config,
            poses[pose],
            candidate,
            c922_camera,
            c922_focal,
            offset_delta_degrees=joint_result.x,
        )
        for pose in FIT_POSES
    }
    joint_heldout = _pose_projection_metrics(
        model,
        data,
        config,
        poses[HELDOUT_POSE],
        candidate,
        c922_camera,
        c922_focal,
        offset_delta_degrees=joint_result.x,
    )

    def base_residual(delta: np.ndarray) -> np.ndarray:
        base_delta = transform(delta[:3], delta[3:6])
        pixels = _pi_residuals(
            model,
            data,
            config,
            poses,
            candidate,
            base_delta=base_delta,
        )
        prior = np.concatenate(
            (
                np.rad2deg(delta[:3]) / 1.0,
                delta[3:6] / 0.005,
            )
        )
        return np.concatenate((pixels, prior))

    base_result = least_squares(
        base_residual,
        np.zeros(6),
        bounds=(
            np.concatenate(
                (np.deg2rad([-5.0] * 3), [-0.03] * 3)
            ),
            np.concatenate(
                (np.deg2rad([5.0] * 3), [0.03] * 3)
            ),
        ),
        loss="soft_l1",
        f_scale=2.0,
        max_nfev=400,
    )
    fitted_base = transform(base_result.x[:3], base_result.x[3:6])
    base_fit_metrics = {
        pose: _pose_projection_metrics(
            model,
            data,
            config,
            poses[pose],
            candidate,
            c922_camera,
            c922_focal,
            base_delta=fitted_base,
        )
        for pose in FIT_POSES
    }
    base_heldout = _pose_projection_metrics(
        model,
        data,
        config,
        poses[HELDOUT_POSE],
        candidate,
        c922_camera,
        c922_focal,
        base_delta=fitted_base,
    )

    fitted_tag_ids = sorted(
        {
            tag_id
            for pose in FIT_POSES
            for tag_id in poses[pose]["pi_tags"]
        }
    )
    tag_index = {
        tag_id: index * 6 for index, tag_id in enumerate(fitted_tag_ids)
    }

    def mount_deltas(vector: np.ndarray) -> dict[int, np.ndarray]:
        return {
            tag_id: transform(
                vector[start : start + 3],
                vector[start + 3 : start + 6],
            )
            for tag_id, start in tag_index.items()
        }

    def mount_residual(delta: np.ndarray) -> np.ndarray:
        pixels = _pi_residuals(
            model,
            data,
            config,
            poses,
            candidate,
            mount_deltas=mount_deltas(delta),
        )
        priors: list[np.ndarray] = []
        for tag_id in fitted_tag_ids:
            start = tag_index[tag_id]
            priors.append(
                np.concatenate(
                    (
                        np.rad2deg(delta[start : start + 3]) / 5.0,
                        delta[start + 3 : start + 6] / 0.005,
                    )
                )
            )
        return np.concatenate((pixels, *priors))

    mount_parameter_count = 6 * len(fitted_tag_ids)
    mount_lower = np.tile(
        np.concatenate((np.deg2rad([-15.0] * 3), [-0.02] * 3)),
        len(fitted_tag_ids),
    )
    mount_upper = -mount_lower
    mount_result = least_squares(
        mount_residual,
        np.zeros(mount_parameter_count),
        bounds=(mount_lower, mount_upper),
        loss="soft_l1",
        f_scale=2.0,
        max_nfev=600,
    )
    fitted_mounts = mount_deltas(mount_result.x)
    mount_fit_metrics = {
        pose: _pose_projection_metrics(
            model,
            data,
            config,
            poses[pose],
            candidate,
            c922_camera,
            c922_focal,
            mount_deltas=fitted_mounts,
        )
        for pose in FIT_POSES
    }
    mount_heldout = _pose_projection_metrics(
        model,
        data,
        config,
        poses[HELDOUT_POSE],
        candidate,
        c922_camera,
        c922_focal,
        mount_deltas=fitted_mounts,
    )

    def pi_camera_residual(delta: np.ndarray) -> np.ndarray:
        camera_delta = transform(delta[:3], delta[3:6])
        pixels = _pi_residuals(
            model,
            data,
            config,
            poses,
            candidate,
            pi_camera_delta=camera_delta,
        )
        prior = np.concatenate(
            (
                np.rad2deg(delta[:3]) / 2.0,
                delta[3:6] / 0.02,
            )
        )
        return np.concatenate((pixels, prior))

    pi_camera_result = least_squares(
        pi_camera_residual,
        np.zeros(6),
        bounds=(
            np.concatenate(
                (np.deg2rad([-15.0] * 3), [-0.20] * 3)
            ),
            np.concatenate(
                (np.deg2rad([15.0] * 3), [0.20] * 3)
            ),
        ),
        loss="soft_l1",
        f_scale=2.0,
        max_nfev=500,
    )
    fitted_pi_camera = transform(
        pi_camera_result.x[:3], pi_camera_result.x[3:6]
    )
    pi_camera_fit_metrics = {
        pose: _pose_projection_metrics(
            model,
            data,
            config,
            poses[pose],
            candidate,
            c922_camera,
            c922_focal,
            pi_camera_delta=fitted_pi_camera,
        )
        for pose in FIT_POSES
    }
    pi_camera_heldout = _pose_projection_metrics(
        model,
        data,
        config,
        poses[HELDOUT_POSE],
        candidate,
        c922_camera,
        c922_focal,
        pi_camera_delta=fitted_pi_camera,
    )

    return {
        "baseline": baseline,
        "families": {
            "joint_zero": family_receipt(
                "joint_zero_degrees",
                joint_result,
                joint_result.x,
                joint_fit_metrics,
                joint_heldout,
            ),
            "base_pose": family_receipt(
                "follower_base_pose_world_delta",
                base_result,
                base_result.x,
                base_fit_metrics,
                base_heldout,
            ),
            "tag_mount": {
                **family_receipt(
                    "tag_mount_right_delta",
                    mount_result,
                    mount_result.x,
                    mount_fit_metrics,
                    mount_heldout,
                ),
                "tag_parameter_order": fitted_tag_ids,
                "fit_view_count_by_tag": {
                    str(tag_id): sum(
                        tag_id in poses[pose]["pi_tags"]
                        for pose in FIT_POSES
                    )
                    for tag_id in fitted_tag_ids
                },
            },
            "pi_camera_nuisance_control": {
                **family_receipt(
                    "pi_camera_world_left_delta_nuisance_control",
                    pi_camera_result,
                    pi_camera_result.x,
                    pi_camera_fit_metrics,
                    pi_camera_heldout,
                ),
                "eligible_for_promotion": False,
                "reason": (
                    "The requested families freeze the accepted Pi camera; "
                    "this control only tests whether the new observations "
                    "instead look like a global camera-state change."
                ),
            },
        },
    }


def _load_pose(name: str, directory: Path) -> dict[str, Any]:
    receipt_path = directory / "execution_receipt.json"
    pi_path = directory / "pi_imx708_torque_on_hold.jpg"
    c922_path = directory / "c922_1920x1080_torque_off.png"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if (
        receipt.get("status") != "completed_wrist_view_reposition_stage"
        or receipt.get("physical_follower_torque_enabled") is not False
        or (receipt.get("pi_hold_still") or {}).get("sha256")
        != sha256(pi_path)
    ):
        raise RuntimeError(f"pose {name} receipt is not admitted torque-off")
    pi = cv2.imread(str(pi_path))
    c922 = cv2.imread(str(c922_path))
    if pi is None or pi.shape[:2] != (
        PI_IMAGE_SIZE[1],
        PI_IMAGE_SIZE[0],
    ):
        raise RuntimeError(f"pose {name} Pi image changed")
    if c922 is None or c922.shape[:2] != (
        C922_IMAGE_SIZE[1],
        C922_IMAGE_SIZE[0],
    ):
        raise RuntimeError(f"pose {name} C922 image changed")
    return {
        "name": name,
        "directory": str(directory),
        "receipt_path": str(receipt_path),
        "receipt_sha256": sha256(receipt_path),
        "pi_path": str(pi_path),
        "pi_sha256": sha256(pi_path),
        "c922_path": str(c922_path),
        "c922_sha256": sha256(c922_path),
        "joint_degrees": np.asarray(
            receipt["final_actual_degrees"], dtype=np.float64
        ),
        "pi_image": pi,
        "pi_tags": detect_pi_tags(pi),
        "c922_image": c922,
        "c922_distance": _image_edge_distance(c922),
    }


def _public_pose(pose: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in pose.items()
        if key
        not in {
            "pi_image",
            "c922_image",
            "c922_distance",
            "joint_degrees",
            "pi_tags",
        }
    } | {
        "joint_degrees": pose["joint_degrees"].tolist(),
        "pi_tags": {
            str(tag_id): corners.tolist()
            for tag_id, corners in sorted(pose["pi_tags"].items())
        },
    }


def _camera_public(camera: np.ndarray, focal: float) -> dict[str, Any]:
    return {
        "focal_px": focal,
        "principal_point_px": [
            C922_IMAGE_SIZE[0] / 2.0,
            C922_IMAGE_SIZE[1] / 2.0,
        ],
        "square_pixels_assumed": True,
        "distortion_assumed_zero": True,
        "world_to_camera_rotation_vector_radians": Rotation.from_matrix(
            camera[:3, :3]
        ).as_rotvec().tolist(),
        "world_to_camera_translation_m": camera[:3, 3].tolist(),
        "world_to_camera_matrix": camera.tolist(),
    }


def evaluate() -> dict[str, Any]:
    contract = load_and_validate_contract()
    candidate = json.loads(FROZEN_CANDIDATE.read_text(encoding="utf-8"))
    heldout_evaluation = json.loads(
        (
            FROZEN_CANDIDATE.parent / "heldout-evaluation.json"
        ).read_text(encoding="utf-8")
    )
    if (
        candidate.get("schema_version")
        != "sim2claw.pi_current_three_link_candidate.v1"
        or heldout_evaluation.get("status")
        != "heldout_gates_passed_no_automatic_promotion"
    ):
        raise RuntimeError("frozen three-tag source is not the accepted model")
    scene = json.loads(SCENE_REGISTRATION.read_text(encoding="utf-8"))
    corners = scene["target_binding"]["corners_mujoco_m"]
    poses = {
        name: _load_pose(name, directory)
        for name, directory in POSE_DIRECTORIES.items()
    }
    grid_pixels, grid_receipt = detect_c922_grid(
        {name: pose["c922_image"] for name, pose in poses.items()}
    )
    manifest = json.loads(SCENE_MANIFEST.read_text(encoding="utf-8"))
    config = manifest["candidate_config"]
    model, _ = _compile_model(config, base_directory=None)
    data = mujoco.MjData(model)
    frozen_offsets = np.asarray(
        candidate["parameters"]["joint_zero_offsets_degrees"],
        dtype=np.float64,
    )
    camera_candidates: list[dict[str, Any]] = []
    for order in d4_corner_orders():
        grid_world = world_grid(corners, order)
        camera, focal, board_metrics = fit_board_camera(
            grid_world, grid_pixels
        )
        pose_metrics = {}
        try:
            for pose_name in FIT_POSES:
                pose = poses[pose_name]
                _set_pose(
                    model,
                    data,
                    config,
                    pose["joint_degrees"],
                    frozen_offsets,
                )
                samples = cad_hull_samples(model, data, camera, focal)
                pose_metrics[pose_name] = edge_metrics(
                    pose["c922_distance"],
                    project_points(samples, camera, focal),
                )
        except RuntimeError:
            pose_metrics = {
                pose_name: {
                    "sample_count": 0,
                    "median_px": CAD_EDGE_CLIP_PX,
                    "p80_px": CAD_EDGE_CLIP_PX,
                    "trimmed_rmse_px": CAD_EDGE_CLIP_PX,
                    "clipped_rmse_px": CAD_EDGE_CLIP_PX,
                }
                for pose_name in FIT_POSES
            }
        score = float(
            np.mean(
                [
                    pose_metrics[pose][
                        "trimmed_rmse_px"
                    ]
                    for pose in FIT_POSES
                ]
            )
        )
        camera_candidates.append(
            {
                "image_corner_to_world_corner_order": list(order),
                "camera": camera,
                "focal": focal,
                "board_metrics": board_metrics,
                "fit_pose_cad_edge_metrics": pose_metrics,
                "fit_score_trimmed_rmse_px": score,
            }
        )
    camera_candidates.sort(
        key=lambda row: row["fit_score_trimmed_rmse_px"]
    )
    selected = camera_candidates[0]
    selected_camera = selected["camera"]
    selected_focal = float(selected["focal"])
    grid_world = world_grid(
        corners,
        tuple(selected["image_corner_to_world_corner_order"]),
    )
    heldout_board_pixels = project_points(
        grid_world.reshape(-1, 3), selected_camera, selected_focal
    )
    heldout_board_distances = sample_distance(
        poses[HELDOUT_POSE]["c922_distance"],
        heldout_board_pixels,
        CAD_EDGE_CLIP_PX,
    )
    parameter_probe = fit_parameter_families(
        model,
        data,
        config,
        poses,
        candidate,
        selected_camera,
        selected_focal,
    )

    def public_candidate(row: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value
            for key, value in row.items()
            if key not in {"camera", "focal"}
        } | {"camera": _camera_public(row["camera"], row["focal"])}

    best_score = float(
        camera_candidates[0]["fit_score_trimmed_rmse_px"]
    )
    second_score = float(
        camera_candidates[1]["fit_score_trimmed_rmse_px"]
    )
    return {
        "schema_version": "sim2claw.current_multiview_cad_bundle.v1",
        "status": "retrospective_diagnostic_nonpromoting",
        "proof_class": "physical_static_multiview_cad_and_fiducial_diagnostic",
        "fit_poses": list(FIT_POSES),
        "heldout_pose": HELDOUT_POSE,
        "source_bindings": {
            "contract": {
                "path": str(CONTRACT),
                "sha256": sha256(CONTRACT),
                "contract_id": contract["contract_id"],
            },
            "frozen_three_tag_candidate": {
                "path": str(FROZEN_CANDIDATE),
                "sha256": sha256(FROZEN_CANDIDATE),
            },
            "frozen_three_tag_heldout_evaluation": {
                "path": str(FROZEN_CANDIDATE.parent / "heldout-evaluation.json"),
                "sha256": sha256(
                    FROZEN_CANDIDATE.parent / "heldout-evaluation.json"
                ),
            },
            "scene_board_registration": {
                "path": str(SCENE_REGISTRATION),
                "sha256": sha256(SCENE_REGISTRATION),
            },
            "compiled_scene_manifest": {
                "path": str(SCENE_MANIFEST),
                "sha256": sha256(SCENE_MANIFEST),
            },
            "poses": {
                name: _public_pose(pose)
                for name, pose in poses.items()
            },
        },
        "c922_board_grid": grid_receipt,
        "c922_camera_family": {
            "method": "H_I_grid_fit_D4_enumeration_exact_CAD_edge_ranking",
            "selected": public_candidate(selected),
            "fit_score_margin_px": second_score - best_score,
            "candidates": [
                public_candidate(row) for row in camera_candidates
            ],
            "heldout_pose_D_board_edge": {
                "point_count": int(len(heldout_board_distances)),
                "median_px": float(np.median(heldout_board_distances)),
                "p90_px": float(
                    np.percentile(heldout_board_distances, 90)
                ),
                "max_px": float(np.max(heldout_board_distances)),
            },
        },
        "parameter_family_probe": parameter_probe,
        "authority": {
            "c922_metric_intrinsics": False,
            "c922_metric_extrinsics": False,
            "pi_intrinsics_reused_as_diagnostic": True,
            "tag_mount_promotion": False,
            "base_pose_promotion": False,
            "joint_zero_promotion": False,
            "simulator_parameter_promotion": False,
            "policy_or_task_evidence": False,
            "physical_robot_control": False,
        },
        "limitations": [
            "C922 focal and pose are conditioned on one plane, centered square pixels, and zero distortion.",
            "C922 CAD residuals use Canny nearest-edge distance and include cable, camera-module, texture, and occlusion mismatch.",
            "Pose D was already consumed by an earlier rejected four-tag fit and is only a designated retrospective holdout here.",
            "Tag 2 appears in one fit pose, so its independent six-DOF mount is not prospectively identifiable.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    result = evaluate()
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
