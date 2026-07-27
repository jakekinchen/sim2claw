#!/usr/bin/env python3
"""Fit one current-session Pi camera/articulated CAD diagnostic bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import cv2
import mujoco
import numpy as np
from scipy.ndimage import map_coordinates
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation

from sim2claw.physical_canary import _physical_to_model_position
from sim2claw.recorded_replay import _compile_model


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = (
    ROOT
    / "configs/evaluations/current_session_pi_articulated_cad_bundle_v1.json"
)
DEFAULT_OUTPUT = (
    ROOT
    / "runs/pi-link-tag-calibration/"
    "20260727-current-session-articulated-cad-bundle-v1"
)
DICTIONARY = cv2.aruco.getPredefinedDictionary(
    cv2.aruco.DICT_APRILTAG_36h11
)
VISUAL_GROUP = 2
IMAGE_WIDTH = 1536
IMAGE_HEIGHT = 864
TAG_IDS = (0, 1, 2, 3, 6)
CAMERA_PARAMETER_COUNT = 6
OFFSET_PARAMETER_COUNT = 5
TAG_PARAMETER_COUNT = 6
SAMPLES_PER_HULL_EDGE = 4
MAX_HULL_EDGES_PER_GEOM = 16
EDGE_RESIDUAL_WEIGHT = 0.35


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def transform(vector: np.ndarray) -> np.ndarray:
    value = np.eye(4, dtype=np.float64)
    value[:3, :3] = Rotation.from_rotvec(vector[:3]).as_matrix()
    value[:3, 3] = vector[3:6]
    return value


def pose_vector(value: np.ndarray) -> np.ndarray:
    return np.concatenate(
        (Rotation.from_matrix(value[:3, :3]).as_rotvec(), value[:3, 3])
    )


def body_transform(
    model: mujoco.MjModel, data: mujoco.MjData, body_name: str
) -> np.ndarray:
    body_id = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_BODY, body_name
    )
    require(body_id >= 0, f"missing body {body_name}")
    value = np.eye(4, dtype=np.float64)
    value[:3, :3] = data.xmat[body_id].reshape(3, 3)
    value[:3, 3] = data.xpos[body_id]
    return value


def project(
    points_world: np.ndarray,
    camera_vector: np.ndarray,
    focal: float,
    principal_point: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    homogeneous = np.column_stack(
        (points_world, np.ones(len(points_world), dtype=np.float64))
    )
    camera_points = (transform(camera_vector) @ homogeneous.T).T[:, :3]
    valid = camera_points[:, 2] > 1e-5
    pixels = np.full((len(points_world), 2), np.nan, dtype=np.float64)
    pixels[valid] = (
        focal * camera_points[valid, :2] / camera_points[valid, 2:3]
        + principal_point
    )
    return pixels, valid


def tag_local_points(edge_m: float) -> np.ndarray:
    half = edge_m / 2.0
    return np.asarray(
        (
            (-half, half, 0.0),
            (half, half, 0.0),
            (half, -half, 0.0),
            (-half, -half, 0.0),
        ),
        dtype=np.float64,
    )


def detect_tags(image: np.ndarray) -> dict[int, np.ndarray]:
    corners, identifiers, _ = cv2.aruco.ArucoDetector(
        DICTIONARY
    ).detectMarkers(image)
    found: dict[int, list[np.ndarray]] = {}
    if identifiers is not None:
        for identifier, corner in zip(
            identifiers.ravel(), corners, strict=True
        ):
            tag_id = int(identifier)
            if tag_id in TAG_IDS:
                found.setdefault(tag_id, []).append(
                    corner[0].astype(np.float64)
                )
    return {
        tag_id: rows[0]
        for tag_id, rows in found.items()
        if len(rows) == 1
    }


def edge_distance(
    image: np.ndarray,
    observed_tags: dict[int, np.ndarray],
    canny: list[int],
) -> tuple[np.ndarray, np.ndarray]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, int(canny[0]), int(canny[1]))
    # Fiducial borders are not CAD borders. Suppress their immediate edge
    # response while retaining the rest of the physical-arm silhouette.
    for corners in observed_tags.values():
        polygon = np.rint(corners).astype(np.int32)
        cv2.fillConvexPoly(edges, polygon, 0)
        cv2.polylines(edges, [polygon], True, 0, 10, cv2.LINE_AA)
    distance = cv2.distanceTransform(
        np.where(edges > 0, 0, 255).astype(np.uint8),
        cv2.DIST_L2,
        cv2.DIST_MASK_PRECISE,
    ).astype(np.float64)
    return edges, distance


class Model:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.model, _ = _compile_model(config, base_directory=None)
        self.data = mujoco.MjData(self.model)
        self.joint_ids = [
            mujoco.mj_name2id(
                self.model, mujoco.mjtObj.mjOBJ_JOINT, name
            )
            for name in config["bindings"]["joint_names"]
        ]
        require(all(value >= 0 for value in self.joint_ids), "missing joints")
        self.visual_geoms = []
        for geom_id in range(self.model.ngeom):
            body_name = mujoco.mj_id2name(
                self.model,
                mujoco.mjtObj.mjOBJ_BODY,
                int(self.model.geom_bodyid[geom_id]),
            )
            if (
                int(self.model.geom_group[geom_id]) == VISUAL_GROUP
                and int(self.model.geom_type[geom_id])
                == int(mujoco.mjtGeom.mjGEOM_MESH)
                and body_name
                and body_name.startswith("left_")
            ):
                mesh_id = int(self.model.geom_dataid[geom_id])
                start = int(self.model.mesh_vertadr[mesh_id])
                count = int(self.model.mesh_vertnum[mesh_id])
                self.visual_geoms.append(
                    {
                        "geom_id": geom_id,
                        "body": body_name,
                        "local": np.asarray(
                            self.model.mesh_vert[start : start + count],
                            dtype=np.float64,
                        ),
                    }
                )
        require(self.visual_geoms, "full follower CAD visual tree is absent")

    def set_pose(
        self,
        joint_degrees: np.ndarray,
        offsets_degrees: np.ndarray,
        scales: np.ndarray | None = None,
    ) -> None:
        physical = joint_degrees.copy()
        if scales is None:
            scales = np.ones(5, dtype=np.float64)
        physical[:5] = physical[:5] * scales + offsets_degrees
        qpos = _physical_to_model_position(
            physical[None, :], self.config
        )[0]
        for index, joint_id in enumerate(self.joint_ids):
            self.data.qpos[int(self.model.jnt_qposadr[joint_id])] = qpos[
                index
            ]
        self.data.qvel[:] = 0.0
        mujoco.mj_forward(self.model, self.data)

    def geom_world_vertices(self, geom: dict[str, Any]) -> np.ndarray:
        geom_id = int(geom["geom_id"])
        return (
            geom["local"] @ self.data.geom_xmat[geom_id].reshape(3, 3).T
            + self.data.geom_xpos[geom_id]
        )


def load_contract(contract_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if (
        contract.get("schema_version")
        == "sim2claw.current_session_pi_articulated_cad_bundle_refit_contract.v1"
    ):
        parent_binding = contract["parent_contract"]
        parent_path = ROOT / parent_binding["path"]
        require(parent_path.is_file(), "refit parent contract is missing")
        require(
            sha256(parent_path) == parent_binding["sha256"],
            "refit parent contract hash changed",
        )
        parent = json.loads(parent_path.read_text(encoding="utf-8"))

        def merged(
            base: dict[str, Any], changes: dict[str, Any]
        ) -> dict[str, Any]:
            result = dict(base)
            for key, value in changes.items():
                if isinstance(value, dict) and isinstance(result.get(key), dict):
                    result[key] = merged(result[key], value)
                else:
                    result[key] = value
            return result

        contract = merged(parent, contract["changes"])
        contract["refit_provenance"] = {
            "parent_contract": parent_binding,
            "amendment_path": str(contract_path.relative_to(ROOT)),
        }
    require(
        contract.get("schema_version")
        == "sim2claw.current_session_pi_articulated_cad_bundle_contract.v1",
        "wrong articulated-CAD contract schema",
    )
    for source_name, source in contract["sources"].items():
        if source_name == "poses":
            continue
        require(
            isinstance(source, dict)
            and isinstance(source.get("path"), str)
            and isinstance(source.get("sha256"), str),
            f"{source_name} binding is incomplete",
        )
        path = ROOT / source["path"]
        require(path.is_file(), f"missing {source_name}: {path}")
        require(
            sha256(path) == source["sha256"],
            f"{source_name} hash changed",
        )
    rows = []
    for name, source in contract["sources"]["poses"].items():
        image_path = ROOT / source["image_path"]
        receipt_path = ROOT / source["receipt_path"]
        require(image_path.is_file(), f"missing {name} image")
        require(receipt_path.is_file(), f"missing {name} receipt")
        require(
            sha256(image_path) == source["image_sha256"],
            f"{name} image hash changed",
        )
        require(
            sha256(receipt_path) == source["receipt_sha256"],
            f"{name} receipt hash changed",
        )
        image = cv2.imread(str(image_path))
        require(
            image is not None
            and image.shape[:2] == (IMAGE_HEIGHT, IMAGE_WIDTH),
            f"{name} image dimensions changed",
        )
        tags = detect_tags(image)
        require(tags, f"{name} has no unique follower tags")
        rows.append(
            {
                "name": name,
                "image_path": image_path,
                "image": image,
                "joint_degrees": np.asarray(
                    source["joint_degrees"], dtype=np.float64
                ),
                "tags": tags,
            }
        )
    return contract, rows


def pnp_camera_tag(
    corners: np.ndarray,
    local_points: np.ndarray,
    camera_matrix: np.ndarray,
) -> np.ndarray:
    ok, rotation, translation = cv2.solvePnP(
        np.ascontiguousarray(local_points),
        np.ascontiguousarray(corners),
        camera_matrix,
        np.zeros(5),
        flags=cv2.SOLVEPNP_IPPE_SQUARE,
    )
    require(bool(ok), "tag PnP seed failed")
    return transform(
        np.concatenate((rotation.reshape(3), translation.reshape(3)))
    )


def mean_poses(poses: list[np.ndarray]) -> np.ndarray:
    rotations = Rotation.from_matrix(
        np.asarray([pose[:3, :3] for pose in poses])
    ).mean()
    translations = np.median(
        np.asarray([pose[:3, 3] for pose in poses]), axis=0
    )
    value = np.eye(4, dtype=np.float64)
    value[:3, :3] = rotations.as_matrix()
    value[:3, 3] = translations
    return value


def tag_world(
    robot: Model,
    body: str,
    mount_vector: np.ndarray,
    local_points: np.ndarray,
) -> np.ndarray:
    body_world = body_transform(robot.model, robot.data, body)
    local_h = np.column_stack(
        (local_points, np.ones(len(local_points), dtype=np.float64))
    )
    return (body_world @ transform(mount_vector) @ local_h.T).T[:, :3]


def stage1_fit(
    robot: Model,
    fit_rows: list[dict[str, Any]],
    body_map: dict[int, str],
    local_points: np.ndarray,
    camera_matrix: np.ndarray,
    camera_seed: np.ndarray,
    focal: float,
    principal: np.ndarray,
    contract: dict[str, Any],
) -> dict[str, Any]:
    mount_seed = {}
    for tag_id in TAG_IDS:
        estimates = []
        for row in fit_rows:
            if tag_id not in row["tags"]:
                continue
            robot.set_pose(row["joint_degrees"], np.zeros(5))
            camera_tag = pnp_camera_tag(
                row["tags"][tag_id], local_points, camera_matrix
            )
            body_world = body_transform(
                robot.model, robot.data, body_map[tag_id]
            )
            estimates.append(
                np.linalg.inv(transform(camera_seed) @ body_world)
                @ camera_tag
            )
        require(estimates, f"tag {tag_id} absent from fit poses")
        mount_seed[tag_id] = pose_vector(mean_poses(estimates))
    initial = np.concatenate(
        [camera_seed] + [mount_seed[tag_id] for tag_id in TAG_IDS]
    )
    rotation_bound = float(
        contract["fit_method"]["camera_rotation_delta_bound_radians"]
    )
    translation_bound = float(
        contract["fit_method"]["camera_translation_delta_bound_m"]
    )
    span = np.asarray(
        [rotation_bound] * 3
        + [translation_bound] * 3
        + ([1.2] * 3 + [0.18] * 3) * len(TAG_IDS),
        dtype=np.float64,
    )

    def measurement(parameters: np.ndarray) -> np.ndarray:
        residuals = []
        for row in fit_rows:
            robot.set_pose(row["joint_degrees"], np.zeros(5))
            for tag_id, observed in sorted(row["tags"].items()):
                index = CAMERA_PARAMETER_COUNT + TAG_IDS.index(tag_id) * 6
                world = tag_world(
                    robot,
                    body_map[tag_id],
                    parameters[index : index + 6],
                    local_points,
                )
                pixels, valid = project(
                    world, parameters[:6], focal, principal
                )
                if not np.all(valid):
                    return np.full(
                        sum(len(row["tags"]) * 8 for row in fit_rows),
                        1000.0,
                    )
                residuals.append((pixels - observed).ravel())
        return np.concatenate(residuals)

    def residual(parameters: np.ndarray) -> np.ndarray:
        camera_prior = np.concatenate(
            (
                (parameters[:3] - camera_seed[:3]) / 0.15,
                (parameters[3:6] - camera_seed[3:6]) / 0.10,
            )
        )
        mount_prior = []
        for tag_id in TAG_IDS:
            index = CAMERA_PARAMETER_COUNT + TAG_IDS.index(tag_id) * 6
            mount_prior.extend(
                (
                    (parameters[index : index + 3] - mount_seed[tag_id][:3])
                    / 0.50
                ).tolist()
            )
            mount_prior.extend(
                (
                    (
                        parameters[index + 3 : index + 6]
                        - mount_seed[tag_id][3:6]
                    )
                    / 0.08
                ).tolist()
            )
        return np.concatenate(
            (measurement(parameters), camera_prior, np.asarray(mount_prior))
        )

    result = least_squares(
        residual,
        initial,
        bounds=(initial - span, initial + span),
        loss="soft_l1",
        f_scale=2.0,
        max_nfev=5000,
    )
    errors = measurement(result.x).reshape(-1, 2)
    norms = np.linalg.norm(errors, axis=1)
    return {
        "parameters": result.x,
        "camera_seed": camera_seed,
        "mount_seed": mount_seed,
        "metrics": {
            "corner_rmse_px": float(np.sqrt(np.mean(norms**2))),
            "corner_max_px": float(np.max(norms)),
            "cost": float(result.cost),
            "optimality": float(result.optimality),
            "function_evaluations": int(result.nfev),
        },
    }


def freeze_hull_edges(
    robot: Model,
    row: dict[str, Any],
    camera_vector: np.ndarray,
    focal: float,
    principal: np.ndarray,
) -> list[dict[str, Any]]:
    robot.set_pose(row["joint_degrees"], np.zeros(5))
    result = []
    for geom in robot.visual_geoms:
        world = robot.geom_world_vertices(geom)
        pixels, valid = project(world, camera_vector, focal, principal)
        usable = (
            valid
            & np.isfinite(pixels).all(axis=1)
            & (pixels[:, 0] > -150)
            & (pixels[:, 0] < IMAGE_WIDTH + 150)
            & (pixels[:, 1] > -150)
            & (pixels[:, 1] < IMAGE_HEIGHT + 150)
        )
        indices = np.flatnonzero(usable)
        if len(indices) < 3:
            continue
        hull = cv2.convexHull(
            pixels[indices].astype(np.float32), returnPoints=False
        ).reshape(-1)
        if len(hull) < 3:
            continue
        hull_indices = indices[hull]
        pairs = np.column_stack(
            (hull_indices, np.roll(hull_indices, -1))
        ).astype(np.int64)
        if len(pairs) > MAX_HULL_EDGES_PER_GEOM:
            selected = np.linspace(
                0,
                len(pairs),
                MAX_HULL_EDGES_PER_GEOM,
                endpoint=False,
                dtype=np.int64,
            )
            pairs = pairs[selected]
        result.append(
            {
                "geom_id": geom["geom_id"],
                "body": geom["body"],
                "local": geom["local"],
                "pairs": pairs,
            }
        )
    require(result, f"{row['name']} produced no CAD hull edges")
    return result


def cad_samples(
    robot: Model, frozen_geoms: list[dict[str, Any]]
) -> tuple[np.ndarray, list[str]]:
    points = []
    bodies = []
    alphas = np.linspace(
        0.0, 1.0, SAMPLES_PER_HULL_EDGE, endpoint=False
    )
    for frozen in frozen_geoms:
        geom_id = int(frozen["geom_id"])
        world = (
            frozen["local"]
            @ robot.data.geom_xmat[geom_id].reshape(3, 3).T
            + robot.data.geom_xpos[geom_id]
        )
        for first_index, second_index in frozen["pairs"]:
            first = world[int(first_index)]
            second = world[int(second_index)]
            for alpha in alphas:
                points.append((1.0 - alpha) * first + alpha * second)
                bodies.append(frozen["body"])
    return np.asarray(points, dtype=np.float64), bodies


def sample_distance(
    distance: np.ndarray,
    pixels: np.ndarray,
    valid: np.ndarray,
    clip_px: float,
) -> np.ndarray:
    inside = (
        valid
        & np.isfinite(pixels).all(axis=1)
        & (pixels[:, 0] >= 0)
        & (pixels[:, 0] <= IMAGE_WIDTH - 1)
        & (pixels[:, 1] >= 0)
        & (pixels[:, 1] <= IMAGE_HEIGHT - 1)
    )
    values = np.full(len(pixels), clip_px, dtype=np.float64)
    if np.any(inside):
        values[inside] = map_coordinates(
            distance,
            (pixels[inside, 1], pixels[inside, 0]),
            order=1,
            mode="constant",
            cval=clip_px,
        )
    return np.clip(values, 0.0, clip_px)


def tag_residual(
    robot: Model,
    rows: list[dict[str, Any]],
    body_map: dict[int, str],
    mounts: dict[int, np.ndarray],
    camera: np.ndarray,
    offsets: np.ndarray,
    scales: np.ndarray,
    local_points: np.ndarray,
    focal: float,
    principal: np.ndarray,
) -> np.ndarray:
    residuals = []
    for row in rows:
        robot.set_pose(row["joint_degrees"], offsets, scales)
        for tag_id, observed in sorted(row["tags"].items()):
            world = tag_world(
                robot, body_map[tag_id], mounts[tag_id], local_points
            )
            pixels, valid = project(world, camera, focal, principal)
            require(np.all(valid), f"tag {tag_id} projects behind camera")
            residuals.append((pixels - observed).ravel())
    return np.concatenate(residuals)


def stage2_fit(
    robot: Model,
    fit_rows: list[dict[str, Any]],
    body_map: dict[int, str],
    mounts: dict[int, np.ndarray],
    stage1_camera: np.ndarray,
    local_points: np.ndarray,
    focal: float,
    principal: np.ndarray,
    contract: dict[str, Any],
) -> dict[str, Any]:
    clip_px = float(contract["fit_method"]["edge_distance_clip_px"])
    canny = contract["fit_method"]["canny_thresholds"]
    prepared = []
    for row in fit_rows:
        edges, distance = edge_distance(row["image"], row["tags"], canny)
        frozen = freeze_hull_edges(
            robot, row, stage1_camera, focal, principal
        )
        robot.set_pose(row["joint_degrees"], np.zeros(5))
        samples, bodies = cad_samples(robot, frozen)
        prepared.append(
            {
                "row": row,
                "edges": edges,
                "distance": distance,
                "frozen": frozen,
                "sample_count": len(samples),
                "bodies": bodies,
            }
        )
    initial = np.concatenate(
        (stage1_camera, np.zeros(5), np.ones(5))
    )
    rotation_bound = float(
        contract["fit_method"]["camera_rotation_delta_bound_radians"]
    )
    translation_bound = float(
        contract["fit_method"]["camera_translation_delta_bound_m"]
    )
    offset_bound = float(
        contract["fit_method"]["joint_zero_bound_degrees"]
    )
    scale_minimum = float(
        contract["fit_method"].get("joint_scale_minimum", 1.0 - 1e-12)
    )
    scale_maximum = float(
        contract["fit_method"].get("joint_scale_maximum", 1.0 + 1e-12)
    )
    span = np.asarray(
        [rotation_bound] * 3
        + [translation_bound] * 3
        + [offset_bound] * 5,
        dtype=np.float64,
    )
    lower = np.concatenate(
        (initial[:11] - span, np.full(5, scale_minimum))
    )
    upper = np.concatenate(
        (initial[:11] + span, np.full(5, scale_maximum))
    )

    def measurement(parameters: np.ndarray) -> np.ndarray:
        camera = parameters[:6]
        offsets = parameters[6:11]
        scales = parameters[11:16]
        residuals = [
            tag_residual(
                robot,
                fit_rows,
                body_map,
                mounts,
                camera,
                offsets,
                scales,
                local_points,
                focal,
                principal,
            )
        ]
        for item in prepared:
            row = item["row"]
            robot.set_pose(row["joint_degrees"], offsets, scales)
            points, _ = cad_samples(robot, item["frozen"])
            pixels, valid = project(points, camera, focal, principal)
            residuals.append(
                EDGE_RESIDUAL_WEIGHT
                * sample_distance(
                    item["distance"], pixels, valid, clip_px
                )
            )
        return np.concatenate(residuals)

    def residual(parameters: np.ndarray) -> np.ndarray:
        priors = np.concatenate(
            (
                (parameters[:3] - stage1_camera[:3]) / 0.12,
                (parameters[3:6] - stage1_camera[3:6]) / 0.08,
                parameters[6:11] / 3.0,
                (parameters[11:16] - 1.0) / 0.20,
            )
        )
        return np.concatenate((measurement(parameters), priors))

    result = least_squares(
        residual,
        initial,
        bounds=(lower, upper),
        loss="soft_l1",
        f_scale=2.0,
        max_nfev=1200,
        diff_step=2e-4,
    )
    return {
        "parameters": result.x,
        "measurement": measurement,
        "prepared": prepared,
        "metrics": {
            "cost": float(result.cost),
            "optimality": float(result.optimality),
            "function_evaluations": int(result.nfev),
            "optimizer_success": bool(result.success),
            "optimizer_message": str(result.message),
        },
    }


def stage3_fit(
    robot: Model,
    fit_rows: list[dict[str, Any]],
    body_map: dict[int, str],
    mount_seed: dict[int, np.ndarray],
    camera: np.ndarray,
    offsets: np.ndarray,
    scales: np.ndarray,
    local_points: np.ndarray,
    focal: float,
    principal: np.ndarray,
) -> dict[str, Any]:
    initial = np.concatenate([mount_seed[tag_id] for tag_id in TAG_IDS])
    span = np.asarray(([0.3] * 3 + [0.05] * 3) * len(TAG_IDS))

    def mounts_from(parameters: np.ndarray) -> dict[int, np.ndarray]:
        return {
            tag_id: parameters[index * 6 : index * 6 + 6]
            for index, tag_id in enumerate(TAG_IDS)
        }

    def measurement(parameters: np.ndarray) -> np.ndarray:
        return tag_residual(
            robot,
            fit_rows,
            body_map,
            mounts_from(parameters),
            camera,
            offsets,
            scales,
            local_points,
            focal,
            principal,
        )

    def residual(parameters: np.ndarray) -> np.ndarray:
        prior = (parameters - initial) / np.tile(
            np.asarray([0.15] * 3 + [0.025] * 3), len(TAG_IDS)
        )
        return np.concatenate((measurement(parameters), prior))

    result = least_squares(
        residual,
        initial,
        bounds=(initial - span, initial + span),
        loss="soft_l1",
        f_scale=2.0,
        max_nfev=4000,
    )
    errors = measurement(result.x).reshape(-1, 2)
    norms = np.linalg.norm(errors, axis=1)
    return {
        "mounts": mounts_from(result.x),
        "metrics": {
            "corner_rmse_px": float(np.sqrt(np.mean(norms**2))),
            "corner_max_px": float(np.max(norms)),
            "cost": float(result.cost),
            "optimality": float(result.optimality),
            "function_evaluations": int(result.nfev),
        },
    }


def numerical_jacobian(
    function: Any, parameters: np.ndarray
) -> dict[str, Any]:
    base = function(parameters)
    columns = []
    steps = np.asarray(
        [1e-5] * 6 + [1e-2] * 5 + [1e-4] * (len(parameters) - 11)
    )
    for index, step in enumerate(steps):
        plus = parameters.copy()
        minus = parameters.copy()
        plus[index] += step
        minus[index] -= step
        columns.append((function(plus) - function(minus)) / (2.0 * step))
    jacobian = np.column_stack(columns)
    require(jacobian.shape[0] == len(base), "Jacobian residual shape changed")
    scales = np.linalg.norm(jacobian, axis=0)
    normalized = jacobian / np.maximum(scales, 1e-12)
    singular = np.linalg.svd(normalized, compute_uv=False)
    tolerance = (
        np.finfo(np.float64).eps
        * max(normalized.shape)
        * singular[0]
    )
    rank = int(np.count_nonzero(singular > tolerance))
    return {
        "measurement_parameter_count": int(jacobian.shape[1]),
        "measurement_residual_count": int(jacobian.shape[0]),
        "column_norms": scales.tolist(),
        "normalized_singular_values": singular.tolist(),
        "normalized_rank": rank,
        "normalized_condition_number": (
            float(singular[0] / singular[-1])
            if singular[-1] > tolerance
            else math.inf
        ),
    }


def metrics_for_pose(
    robot: Model,
    row: dict[str, Any],
    body_map: dict[int, str],
    mounts: dict[int, np.ndarray],
    camera: np.ndarray,
    offsets: np.ndarray,
    scales: np.ndarray,
    local_points: np.ndarray,
    focal: float,
    principal: np.ndarray,
    contract: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    tag_error = tag_residual(
        robot,
        [row],
        body_map,
        mounts,
        camera,
        offsets,
        scales,
        local_points,
        focal,
        principal,
    ).reshape(-1, 2)
    tag_norms = np.linalg.norm(tag_error, axis=1)
    edges, distance = edge_distance(
        row["image"], row["tags"], contract["fit_method"]["canny_thresholds"]
    )
    frozen = freeze_hull_edges(robot, row, camera, focal, principal)
    robot.set_pose(row["joint_degrees"], offsets, scales)
    points, bodies = cad_samples(robot, frozen)
    pixels, valid = project(points, camera, focal, principal)
    values = sample_distance(
        distance,
        pixels,
        valid,
        float(contract["fit_method"]["edge_distance_clip_px"]),
    )
    metrics = {
        "observed_tag_ids": sorted(row["tags"]),
        "tag_corner_count": int(len(tag_norms)),
        "tag_corner_rmse_px": float(np.sqrt(np.mean(tag_norms**2))),
        "tag_corner_max_px": float(np.max(tag_norms)),
        "CAD_edge_sample_count": int(len(values)),
        "CAD_edge_valid_projection_count": int(np.count_nonzero(valid)),
        "CAD_edge_median_px": float(np.median(values)),
        "CAD_edge_p80_px": float(np.percentile(values, 80)),
        "CAD_edge_clipped_rmse_px": float(np.sqrt(np.mean(values**2))),
    }
    render_data = {
        "edges": edges,
        "pixels": pixels,
        "valid": valid,
        "bodies": bodies,
    }
    return metrics, render_data


def draw_overlay(
    row: dict[str, Any],
    robot: Model,
    body_map: dict[int, str],
    mounts: dict[int, np.ndarray],
    camera: np.ndarray,
    offsets: np.ndarray,
    scales: np.ndarray,
    local_points: np.ndarray,
    focal: float,
    principal: np.ndarray,
    render_data: dict[str, Any],
    output: Path,
    metrics: dict[str, Any],
) -> None:
    image = row["image"].copy()
    body_colors = {
        name: tuple(int(value) for value in color)
        for name, color in zip(
            sorted(set(render_data["bodies"])),
            (
                (40, 210, 255),
                (80, 220, 80),
                (220, 100, 255),
                (255, 150, 40),
                (50, 80, 255),
                (200, 220, 50),
                (255, 80, 140),
                (120, 255, 180),
            ),
            strict=False,
        )
    }
    for pixel, valid, body in zip(
        render_data["pixels"],
        render_data["valid"],
        render_data["bodies"],
        strict=True,
    ):
        if (
            valid
            and 0 <= pixel[0] < IMAGE_WIDTH
            and 0 <= pixel[1] < IMAGE_HEIGHT
        ):
            cv2.circle(
                image,
                tuple(np.rint(pixel).astype(int)),
                2,
                body_colors[body],
                -1,
                cv2.LINE_AA,
            )
    robot.set_pose(row["joint_degrees"], offsets, scales)
    for tag_id, observed in sorted(row["tags"].items()):
        world = tag_world(
            robot, body_map[tag_id], mounts[tag_id], local_points
        )
        projected, _ = project(world, camera, focal, principal)
        cv2.polylines(
            image,
            [np.rint(observed).astype(np.int32)],
            True,
            (0, 255, 0),
            2,
            cv2.LINE_AA,
        )
        cv2.polylines(
            image,
            [np.rint(projected).astype(np.int32)],
            True,
            (0, 0, 255),
            2,
            cv2.LINE_AA,
        )
        for actual, estimate in zip(observed, projected, strict=True):
            cv2.line(
                image,
                tuple(np.rint(actual).astype(int)),
                tuple(np.rint(estimate).astype(int)),
                (255, 0, 255),
                1,
                cv2.LINE_AA,
            )
    label = (
        f"{row['name']} tag RMS {metrics['tag_corner_rmse_px']:.2f}px  "
        f"CAD med/p80 {metrics['CAD_edge_median_px']:.2f}/"
        f"{metrics['CAD_edge_p80_px']:.2f}px"
    )
    cv2.rectangle(image, (15, 15), (1050, 58), (20, 20, 20), -1)
    cv2.putText(
        image,
        label,
        (28, 46),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.72,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )
    require(cv2.imwrite(str(output), image), f"failed to write {output}")


def run(contract_path: Path, output: Path) -> dict[str, Any]:
    require(not output.exists(), f"refusing to overwrite {output}")
    contract, rows = load_contract(contract_path)
    fit_names = set(contract["split"]["fit_poses"])
    heldout_name = str(contract["split"]["heldout_pose"])
    fit_rows = [row for row in rows if row["name"] in fit_names]
    heldout = next(row for row in rows if row["name"] == heldout_name)
    require(
        {row["name"] for row in fit_rows} == fit_names,
        "fit pose split is incomplete",
    )
    intrinsics = json.loads(
        (ROOT / contract["sources"]["intrinsics"]["path"]).read_text(
            encoding="utf-8"
        )
    )
    focal = float(contract["frozen_model"]["focal_px"])
    principal = np.asarray(
        contract["frozen_model"]["principal_point_px"], dtype=np.float64
    )
    camera_matrix = np.asarray(
        ((focal, 0.0, principal[0]), (0.0, focal, principal[1]), (0, 0, 1)),
        dtype=np.float64,
    )
    require(
        abs(
            float(intrinsics["output_resolution"]["camera_matrix"][0][0])
            - focal
        )
        < 1e-9,
        "contract focal no longer matches bound intrinsics",
    )
    manifest = json.loads(
        (ROOT / contract["sources"]["candidate_manifest"]["path"]).read_text(
            encoding="utf-8"
        )
    )
    seed = json.loads(
        (ROOT / contract["sources"]["camera_seed"]["path"]).read_text(
            encoding="utf-8"
        )
    )
    camera_seed = np.concatenate(
        (
            np.asarray(
                seed["parameters"]["camera_world_rotation_vector_radians"]
            ),
            np.asarray(seed["parameters"]["camera_world_translation_m"]),
        )
    ).astype(np.float64)
    body_map = {
        int(tag_id): body
        for tag_id, body in contract["frozen_model"]["tag_body_map"].items()
    }
    require(set(body_map) == set(TAG_IDS), "tag/body map is incomplete")
    local_points = tag_local_points(
        float(contract["frozen_model"]["tag_black_edge_m"])
    )
    robot = Model(manifest["candidate_config"])
    stage1 = stage1_fit(
        robot,
        fit_rows,
        body_map,
        local_points,
        camera_matrix,
        camera_seed,
        focal,
        principal,
        contract,
    )
    stage1_parameters = stage1["parameters"]
    stage1_camera = stage1_parameters[:6]
    stage1_mounts = {
        tag_id: stage1_parameters[
            CAMERA_PARAMETER_COUNT
            + index * TAG_PARAMETER_COUNT : CAMERA_PARAMETER_COUNT
            + (index + 1) * TAG_PARAMETER_COUNT
        ]
        for index, tag_id in enumerate(TAG_IDS)
    }
    stage2 = stage2_fit(
        robot,
        fit_rows,
        body_map,
        stage1_mounts,
        stage1_camera,
        local_points,
        focal,
        principal,
        contract,
    )
    stage2_parameters = stage2["parameters"]
    camera = stage2_parameters[:6]
    offsets = stage2_parameters[6:11]
    scales = stage2_parameters[11:16]
    stage3 = stage3_fit(
        robot,
        fit_rows,
        body_map,
        stage1_mounts,
        camera,
        offsets,
        scales,
        local_points,
        focal,
        principal,
    )
    mounts = stage3["mounts"]
    identifiability = numerical_jacobian(
        stage2["measurement"], stage2_parameters
    )
    output.mkdir(parents=True)
    pose_metrics = {}
    overlays = {}
    for row in [*fit_rows, heldout]:
        metrics, render_data = metrics_for_pose(
            robot,
            row,
            body_map,
            mounts,
            camera,
            offsets,
            scales,
            local_points,
            focal,
            principal,
            contract,
        )
        overlay = output / f"{row['name']}-overlay.jpg"
        draw_overlay(
            row,
            robot,
            body_map,
            mounts,
            camera,
            offsets,
            scales,
            local_points,
            focal,
            principal,
            render_data,
            overlay,
            metrics,
        )
        pose_metrics[row["name"]] = metrics
        overlays[row["name"]] = {
            "path": str(overlay.relative_to(ROOT)),
            "sha256": sha256(overlay),
        }
    fit_tag_norms = []
    for name in contract["split"]["fit_poses"]:
        count = pose_metrics[name]["tag_corner_count"]
        fit_tag_norms.extend(
            [pose_metrics[name]["tag_corner_rmse_px"]] * count
        )
    heldout_metrics = pose_metrics[heldout_name]
    gates = contract["gates"]
    margin = float(gates["joint_offset_no_bound_saturation_margin_degrees"])
    bound = float(contract["fit_method"]["joint_zero_bound_degrees"])
    scale_margin = float(
        gates.get("joint_scale_no_bound_saturation_margin", 0.0)
    )
    scale_minimum = float(
        contract["fit_method"].get("joint_scale_minimum", 1.0 - 1e-12)
    )
    scale_maximum = float(
        contract["fit_method"].get("joint_scale_maximum", 1.0 + 1e-12)
    )
    gate_results = {
        "fit_tag_corner_rmse": bool(
            stage3["metrics"]["corner_rmse_px"]
            <= float(gates["fit_tag_corner_rmse_max_px"])
        ),
        "heldout_tag_corner_rmse": bool(
            heldout_metrics["tag_corner_rmse_px"]
            <= float(gates["heldout_tag_corner_rmse_max_px"])
        ),
        "heldout_tag_corner_max": bool(
            heldout_metrics["tag_corner_max_px"]
            <= float(gates["heldout_tag_corner_max_px"])
        ),
        "heldout_CAD_edge_median": bool(
            heldout_metrics["CAD_edge_median_px"]
            <= float(gates["heldout_CAD_edge_median_max_px"])
        ),
        "heldout_CAD_edge_p80": bool(
            heldout_metrics["CAD_edge_p80_px"]
            <= float(gates["heldout_CAD_edge_p80_max_px"])
        ),
        "joint_offset_no_bound_saturation": bool(
            np.all(np.abs(offsets) <= bound - margin)
        ),
        "joint_scale_no_bound_saturation": bool(
            np.all(scales >= scale_minimum + scale_margin)
            and np.all(scales <= scale_maximum - scale_margin)
        ),
        "stage_2_jacobian_full_rank": bool(
            identifiability["normalized_rank"]
            == identifiability["measurement_parameter_count"]
        ),
    }
    receipt = {
        "schema_version": "sim2claw.current_session_pi_articulated_cad_bundle.v1",
        "status": (
            "diagnostic_gates_passed"
            if all(gate_results.values())
            else "diagnostic_gates_failed"
        ),
        "proof_class": contract["proof_class"],
        "contract": {
            "path": str(contract_path.relative_to(ROOT)),
            "sha256": sha256(contract_path),
            "heldout_limitation": contract["split"]["heldout_limitation"],
        },
        "sources": contract["sources"],
        "model": {
            "visual_mesh_geom_count": len(robot.visual_geoms),
            "visual_bodies": sorted(
                {str(geom["body"]) for geom in robot.visual_geoms}
            ),
            "focal_px": focal,
            "principal_point_px": principal.tolist(),
            "tag_body_map": {
                str(tag_id): body for tag_id, body in body_map.items()
            },
        },
        "parameters": {
            "camera_world_rotation_vector_radians": camera[:3].tolist(),
            "camera_world_translation_m": camera[3:6].tolist(),
            "joint_zero_offsets_degrees": offsets.tolist(),
            "joint_degree_scales": scales.tolist(),
            "tag_mounts": {
                str(tag_id): {
                    "body_tag_rotation_vector_radians": mounts[tag_id][
                        :3
                    ].tolist(),
                    "body_tag_translation_m": mounts[tag_id][3:6].tolist(),
                }
                for tag_id in TAG_IDS
            },
        },
        "stage_1_shared_camera_and_mount_fit": stage1["metrics"],
        "stage_2_full_CAD_and_tag_fit": stage2["metrics"],
        "stage_3_mount_refit": stage3["metrics"],
        "stage_2_measurement_identifiability": identifiability,
        "pose_metrics": pose_metrics,
        "overlays": overlays,
        "gates": gates,
        "gate_results": gate_results,
        "all_diagnostic_gates_passed": all(gate_results.values()),
        "limitations": {
            "heldout_was_retrospectively_inspected": True,
            "occlusion_reasoning": False,
            "generic_image_edges_can_include_background": True,
            "camera_exposure_synchronized_to_joint_encoder": False,
            "simulator_parameter_promotion": False,
            "physical_robot_control": False,
            "pawn_contact": False,
            "task_or_policy_evidence": False,
        },
        "authority": contract["authority"],
    }
    receipt_path = output / "receipt.json"
    receipt_path.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    arguments = parser.parse_args()
    run(arguments.contract.resolve(), arguments.output.resolve())


if __name__ == "__main__":
    main()
