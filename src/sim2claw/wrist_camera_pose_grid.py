"""Action-free MuJoCo wrist-camera frustum pose-grid diagnostic."""

from __future__ import annotations

import itertools
import json
import math
from pathlib import Path
from typing import Any, Mapping

import mujoco
import numpy as np

from .canary_contact_preflight import DEFAULT_POLICY_PATH
from .capture import load_capture_config
from .learning_factory_artifacts import atomic_write_json, sha256_file
from .paths import DEFAULT_CAPTURE_CONFIG, REPO_ROOT, SO101_MODEL_PATH
from .physical_canary import _physical_to_model_position
from .recorded_replay import _compile_model
from .scene import ROBOT_JOINTS, scene_geometry


CONTRACT_PATH = (
    REPO_ROOT / "configs" / "evaluations" / "d405_wrist_frustum_pose_grid_v1.json"
)
CONTRACT_SCHEMA = "sim2claw.d405_wrist_frustum_pose_grid_contract.v1"
RECEIPT_SCHEMA = "sim2claw.d405_wrist_frustum_pose_grid_receipt.v1"


class WristCameraPoseGridError(RuntimeError):
    """The frozen simulator-frustum diagnostic is invalid."""


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise WristCameraPoseGridError(f"cannot read {label} {path}: {error}") from error
    if not isinstance(value, dict):
        raise WristCameraPoseGridError(f"{label} must contain an object")
    return value


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    value = _read_json(path, "pose-grid contract")
    if value.get("schema_version") != CONTRACT_SCHEMA:
        raise WristCameraPoseGridError("unexpected pose-grid contract schema")
    authority = value.get("authority")
    if not isinstance(authority, dict) or not authority or any(authority.values()):
        raise WristCameraPoseGridError("pose-grid authority widened")
    families = value.get("grid_families")
    if not isinstance(families, list) or not 1 <= len(families) <= 2:
        raise WristCameraPoseGridError("pose grid must contain one or two bounded families")
    joint_keys = [f"{name}_degrees" for name in ROBOT_JOINTS[:5]]
    count = 0
    for family in families:
        if not isinstance(family, dict) or not str(family.get("name") or ""):
            raise WristCameraPoseGridError("pose-grid family is malformed")
        for key in joint_keys:
            values = family.get(key)
            if (
                not isinstance(values, list)
                or len(values) != 3
                or any(not math.isfinite(float(item)) for item in values)
            ):
                raise WristCameraPoseGridError(f"{key} must freeze exactly three values")
        count += 3**5
    if count > 486:
        raise WristCameraPoseGridError("pose grid exceeds its bounded 486-candidate limit")
    if int(value.get("boundary_sample_count", 0)) < 5:
        raise WristCameraPoseGridError("boundary visibility sampling was weakened")
    if float(value.get("minimum_boundary_margin_px", 0.0)) <= 0.0:
        raise WristCameraPoseGridError("positive pixel margin is required")
    return value


def _body_subtree(model: mujoco.MjModel, root_name: str) -> set[int]:
    root = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, root_name)
    if root < 0:
        raise WristCameraPoseGridError(f"contact policy body is missing: {root_name}")
    result: set[int] = set()
    for body_id in range(model.nbody):
        cursor = body_id
        while cursor > 0:
            if cursor == root:
                result.add(body_id)
                break
            cursor = int(model.body_parentid[cursor])
    return result


def _contact_geometry_policy(
    model: mujoco.MjModel, policy: Mapping[str, Any]
) -> dict[str, Any]:
    commanded = _body_subtree(model, str(policy["commanded_body_root"]))
    outside: set[int] = set()
    for key in (
        "forbidden_static_body_roots",
        "forbidden_object_body_roots",
        "forbidden_other_arm_body_roots",
    ):
        for name in policy[key]:
            outside.update(_body_subtree(model, str(name)))
    collision_geoms = {
        geom_id
        for geom_id in range(model.ngeom)
        if int(model.geom_contype[geom_id]) != 0
        or int(model.geom_conaffinity[geom_id]) != 0
    }
    commanded_geoms = {
        geom_id
        for geom_id in collision_geoms
        if int(model.geom_bodyid[geom_id]) in commanded
    }
    outside_geoms = {
        geom_id
        for geom_id in collision_geoms
        if int(model.geom_bodyid[geom_id]) in outside
    }
    for name in policy["forbidden_static_geom_names"]:
        geom_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, str(name))
        if geom_id < 0:
            raise WristCameraPoseGridError(f"contact policy geom is missing: {name}")
        outside_geoms.add(geom_id)
    excluded = {
        frozenset(
            mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, str(name))
            for name in pair
        )
        for pair in policy["excluded_internal_body_pairs"]
    }
    distance_pairs = {
        tuple(sorted((first, second)))
        for first in commanded_geoms
        for second in outside_geoms
        if first != second
    }
    ordered_commanded = sorted(commanded_geoms)
    for index, first in enumerate(ordered_commanded):
        body_first = int(model.geom_bodyid[first])
        for second in ordered_commanded[index + 1 :]:
            body_second = int(model.geom_bodyid[second])
            if body_first == body_second:
                continue
            if frozenset((body_first, body_second)) in excluded:
                continue
            distance_pairs.add((first, second))
    return {
        "commanded_bodies": commanded,
        "outside_bodies": outside,
        "excluded_body_pairs": excluded,
        "distance_pairs": sorted(distance_pairs),
    }


def _name(
    model: mujoco.MjModel, object_type: mujoco.mjtObj, object_id: int
) -> str:
    return (
        mujoco.mj_id2name(model, object_type, object_id)
        or f"{object_type.name.lower()}#{object_id}"
    )


def _forbidden_contacts(
    model: mujoco.MjModel, data: mujoco.MjData, policy: Mapping[str, Any]
) -> list[dict[str, Any]]:
    commanded = policy["commanded_bodies"]
    outside = policy["outside_bodies"]
    excluded = policy["excluded_body_pairs"]
    result: list[dict[str, Any]] = []
    for index in range(data.ncon):
        contact = data.contact[index]
        geom_a, geom_b = int(contact.geom1), int(contact.geom2)
        body_a = int(model.geom_bodyid[geom_a])
        body_b = int(model.geom_bodyid[geom_b])
        if body_a not in commanded and body_b not in commanded:
            continue
        if body_a in commanded and body_b in commanded:
            forbidden = (
                body_a != body_b
                and frozenset((body_a, body_b)) not in excluded
            )
        else:
            other = body_b if body_a in commanded else body_a
            forbidden = other in outside
        if forbidden:
            result.append(
                {
                    "geom_pair": sorted(
                        (
                            _name(model, mujoco.mjtObj.mjOBJ_GEOM, geom_a),
                            _name(model, mujoco.mjtObj.mjOBJ_GEOM, geom_b),
                        )
                    ),
                    "body_pair": sorted(
                        (
                            _name(model, mujoco.mjtObj.mjOBJ_BODY, body_a),
                            _name(model, mujoco.mjtObj.mjOBJ_BODY, body_b),
                        )
                    ),
                    "distance_m": float(contact.dist),
                }
            )
    return result


def _board_geometry(sample_count: int) -> tuple[np.ndarray, list[np.ndarray]]:
    geometry = scene_geometry(load_capture_config(DEFAULT_CAPTURE_CONFIG))
    angle = math.radians(geometry.board_yaw_degrees)
    rotation = np.asarray(
        ((math.cos(angle), -math.sin(angle)), (math.sin(angle), math.cos(angle))),
        dtype=np.float64,
    )
    center = np.asarray(geometry.board_center, dtype=np.float64)
    half = geometry.board_side / 2.0
    local = np.asarray(
        ((-half, -half), (half, -half), (half, half), (-half, half)),
        dtype=np.float64,
    )
    xy = local @ rotation.T + center
    z = geometry.table_top + geometry.board_thickness + 0.001
    corners = np.column_stack((xy, np.full(4, z, dtype=np.float64)))
    boundaries = [
        np.linspace(corners[index], corners[(index + 1) % 4], sample_count)
        for index in range(4)
    ]
    board_center = np.asarray((center[0], center[1], z), dtype=np.float64)
    # Shift samples 1 mm inward so rays hit a playing-square surface, not a gap.
    shifted = []
    for samples in boundaries:
        direction = board_center - np.mean(samples, axis=0)
        direction[2] = 0.0
        direction /= np.linalg.norm(direction)
        shifted.append(samples + direction * 0.001)
    return corners, shifted


def _project(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    camera_id: int,
    points: np.ndarray,
    *,
    width: int,
    height: int,
) -> tuple[np.ndarray, np.ndarray]:
    camera_rotation = data.cam_xmat[camera_id].reshape(3, 3)
    camera_points = (points - data.cam_xpos[camera_id]) @ camera_rotation
    depths = -camera_points[:, 2]
    focal = 0.5 * height / math.tan(math.radians(model.cam_fovy[camera_id]) / 2.0)
    pixels = np.column_stack(
        (
            width / 2.0 + focal * camera_points[:, 0] / depths,
            height / 2.0 - focal * camera_points[:, 1] / depths,
        )
    )
    return pixels, depths


def _visibility(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    camera_id: int,
    boundaries: list[np.ndarray],
    *,
    target_tolerance_m: float,
) -> list[dict[str, Any]]:
    result = []
    camera = np.asarray(data.cam_xpos[camera_id], dtype=np.float64)
    camera_body = int(model.cam_bodyid[camera_id])
    for name, samples in zip(
        ("robot_far", "board_right", "robot_near", "board_left"),
        boundaries,
        strict=True,
    ):
        visible = 0
        hits: dict[str, int] = {}
        for target in samples:
            vector = target - camera
            target_distance = float(np.linalg.norm(vector))
            vector /= target_distance
            geom_id = np.asarray((-1,), dtype=np.int32)
            distance = float(
                mujoco.mj_ray(
                    model,
                    data,
                    camera,
                    vector,
                    None,
                    True,
                    camera_body,
                    geom_id,
                )
            )
            hit_name = (
                _name(model, mujoco.mjtObj.mjOBJ_GEOM, int(geom_id[0]))
                if int(geom_id[0]) >= 0
                else "no_hit"
            )
            hits[hit_name] = hits.get(hit_name, 0) + 1
            if distance >= 0.0 and abs(distance - target_distance) <= target_tolerance_m:
                visible += 1
        result.append(
            {
                "boundary": name,
                "sample_count": len(samples),
                "direct_ray_visible_sample_count": visible,
                "direct_ray_visible_fraction": visible / len(samples),
                "first_hit_geom_counts": dict(sorted(hits.items())),
            }
        )
    return result


def _candidate_vectors(contract: Mapping[str, Any]) -> list[tuple[str, np.ndarray]]:
    result = []
    keys = [f"{name}_degrees" for name in ROBOT_JOINTS[:5]]
    gripper = float(contract["gripper_percent"])
    for family in contract["grid_families"]:
        axes = [[float(item) for item in family[key]] for key in keys]
        for body in itertools.product(*axes):
            result.append(
                (str(family["name"]), np.asarray((*body, gripper), dtype=np.float64))
            )
    return result


def _minimum_distance(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    pairs: list[tuple[int, int]],
    *,
    limit_m: float,
) -> tuple[float, tuple[int, int] | None]:
    minimum = limit_m
    minimum_pair: tuple[int, int] | None = None
    for first, second in pairs:
        distance = float(
            mujoco.mj_geomDistance(model, data, first, second, limit_m, None)
        )
        if distance < minimum:
            minimum = distance
            minimum_pair = (first, second)
    return minimum, minimum_pair


def search_wrist_camera_pose_grid(
    *,
    contract_path: Path = CONTRACT_PATH,
    output_path: Path | None = None,
    candidate_manifest_path: Path | None = None,
) -> dict[str, Any]:
    """Rank a frozen, action-free grid using current MuJoCo geometry only."""
    contract_path = contract_path.resolve()
    contract = load_contract(contract_path)
    manifest_path = (
        candidate_manifest_path.resolve()
        if candidate_manifest_path is not None
        else (REPO_ROOT / str(contract["candidate_manifest_path"])).resolve()
    )
    manifest = _read_json(manifest_path, "candidate manifest")
    route_path = (REPO_ROOT / str(contract["route_path"])).resolve()
    route = _read_json(route_path, "wrist-view route")
    route_targets = np.asarray(route.get("stage_targets_degrees"), dtype=np.float64)
    family = contract["grid_families"][0]
    v24_center = np.asarray(
        [
            family[
                {
                    "shoulder_pan": "shoulder_pan_degrees",
                    "shoulder_lift": "shoulder_lift_degrees",
                    "elbow_flex": "elbow_flex_degrees",
                    "wrist_flex": "wrist_flex_degrees",
                    "wrist_roll": "wrist_roll_degrees",
                }[name]
            ][1]
            for name in ROBOT_JOINTS[:5]
        ]
        + [float(contract["gripper_percent"])],
        dtype=np.float64,
    )
    if (
        route_targets.shape != (1, 6)
        or not np.array_equal(route_targets[0], v24_center)
        or family.get("name") != "v24_local"
    ):
        raise WristCameraPoseGridError("v24 grid center no longer matches frozen route")
    candidate_config = manifest.get("candidate_config")
    if not isinstance(candidate_config, dict):
        raise WristCameraPoseGridError("candidate manifest lacks candidate_config")
    if manifest.get("runtime", {}).get("camera_transform_supported") is not False:
        raise WristCameraPoseGridError(
            "candidate manifest camera-transform limitation changed"
        )
    model, current_scene = _compile_model(candidate_config, base_directory=None)
    if not current_scene:
        raise WristCameraPoseGridError("pose-grid search requires current chess scene")
    data = mujoco.MjData(model)
    camera_name = str(contract["camera_name"])
    camera_id = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_CAMERA, camera_name
    )
    if camera_id < 0:
        raise WristCameraPoseGridError(f"wrist camera is missing: {camera_name}")
    joint_names = list(candidate_config["bindings"]["joint_names"])
    joint_ids = [
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        for name in joint_names
    ]
    if len(joint_ids) != 6 or any(joint_id < 0 for joint_id in joint_ids):
        raise WristCameraPoseGridError("candidate joint binding is incomplete")
    policy_path = DEFAULT_POLICY_PATH.resolve()
    geometry_policy = _contact_geometry_policy(
        model, _read_json(policy_path, "contact policy")
    )
    corners, boundaries = _board_geometry(int(contract["boundary_sample_count"]))
    width = int(contract["render_width_px"])
    height = int(contract["render_height_px"])
    required_margin = float(contract["minimum_boundary_margin_px"])
    required_visibility = float(contract["minimum_visible_fraction_per_boundary"])
    target_tolerance = float(contract["ray_target_tolerance_m"])
    distance_limit = float(contract["minimum_clearance_query_limit_m"])
    required_clearance = float(contract["minimum_forbidden_geometry_clearance_m"])
    rows: list[dict[str, Any]] = []
    for family, physical in _candidate_vectors(contract):
        model_position = _physical_to_model_position(
            physical.reshape(1, 6), candidate_config
        )[0]
        for joint_id, value in zip(joint_ids, model_position, strict=True):
            data.qpos[int(model.jnt_qposadr[joint_id])] = float(value)
        data.qvel[:] = 0.0
        mujoco.mj_forward(model, data)
        pixels, depths = _project(
            model, data, camera_id, corners, width=width, height=height
        )
        pixel_margins = np.column_stack(
            (
                pixels[:, 0],
                width - 1 - pixels[:, 0],
                pixels[:, 1],
                height - 1 - pixels[:, 1],
            )
        )
        minimum_margin = (
            float(np.min(pixel_margins))
            if np.all(depths > 0.0)
            else float("-inf")
        )
        contacts = _forbidden_contacts(model, data, geometry_policy)
        visibility = _visibility(
            model,
            data,
            camera_id,
            boundaries,
            target_tolerance_m=target_tolerance,
        )
        minimum_visibility = min(
            item["direct_ray_visible_fraction"] for item in visibility
        )
        visual_gate = (
            minimum_margin >= required_margin
            and minimum_visibility >= required_visibility
        )
        minimum_distance: float | None = None
        minimum_pair: tuple[int, int] | None = None
        if not contacts and visual_gate:
            minimum_distance, minimum_pair = _minimum_distance(
                model,
                data,
                geometry_policy["distance_pairs"],
                limit_m=distance_limit,
            )
        passed = (
            not contacts
            and visual_gate
            and minimum_distance is not None
            and minimum_distance >= required_clearance
        )
        rows.append(
            {
                "grid_family": family,
                "physical_joint_vector_degrees_percent": physical.tolist(),
                "model_joint_vector_radians": model_position.tolist(),
                "forbidden_contact_count": len(contacts),
                "forbidden_contacts": contacts,
                "board_corner_pixels": pixels.tolist(),
                "board_corner_depths_m_in_simulator_camera": depths.tolist(),
                "image_edge_margins_px": {
                    "left": float(np.min(pixel_margins[:, 0])),
                    "right": float(np.min(pixel_margins[:, 1])),
                    "top": float(np.min(pixel_margins[:, 2])),
                    "bottom": float(np.min(pixel_margins[:, 3])),
                    "minimum": minimum_margin,
                },
                "boundary_direct_ray_visibility": visibility,
                "minimum_boundary_direct_ray_visible_fraction": minimum_visibility,
                "minimum_forbidden_geometry_distance_m": minimum_distance,
                "minimum_distance_is_query_limit_censored": (
                    minimum_distance == distance_limit and minimum_pair is None
                    if minimum_distance is not None
                    else None
                ),
                "minimum_distance_geom_pair": (
                    [
                        _name(model, mujoco.mjtObj.mjOBJ_GEOM, minimum_pair[0]),
                        _name(model, mujoco.mjtObj.mjOBJ_GEOM, minimum_pair[1]),
                    ]
                    if minimum_pair is not None
                    else None
                ),
                "passed_simulator_frustum_gate": passed,
                "_model_position": model_position,
            }
        )
    rows.sort(
        key=lambda row: (
            row["passed_simulator_frustum_gate"],
            -row["forbidden_contact_count"],
            row["minimum_boundary_direct_ray_visible_fraction"],
            row["image_edge_margins_px"]["minimum"],
        ),
        reverse=True,
    )
    ranked_count = int(contract["ranked_result_count"])
    ranked = rows[:ranked_count]
    for row in ranked:
        model_position = row.pop("_model_position")
        for joint_id, value in zip(joint_ids, model_position, strict=True):
            data.qpos[int(model.jnt_qposadr[joint_id])] = float(value)
        mujoco.mj_forward(model, data)
        if row["minimum_forbidden_geometry_distance_m"] is None:
            minimum, minimum_pair = _minimum_distance(
                model,
                data,
                geometry_policy["distance_pairs"],
                limit_m=distance_limit,
            )
            row["minimum_forbidden_geometry_distance_m"] = minimum
            row["minimum_distance_is_query_limit_censored"] = minimum_pair is None
            row["minimum_distance_geom_pair"] = (
                [
                    _name(model, mujoco.mjtObj.mjOBJ_GEOM, minimum_pair[0]),
                    _name(model, mujoco.mjtObj.mjOBJ_GEOM, minimum_pair[1]),
                ]
                if minimum_pair is not None
                else None
            )
    passed_count = sum(row["passed_simulator_frustum_gate"] for row in rows)
    family_summary = {
        family["name"]: {
            "candidate_count": sum(
                row["grid_family"] == family["name"] for row in rows
            ),
            "passed_count": sum(
                row["grid_family"] == family["name"]
                and row["passed_simulator_frustum_gate"]
                for row in rows
            ),
        }
        for family in contract["grid_families"]
    }
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "proof_class": contract["proof_class"],
        "action_free": True,
        "simulation_only": True,
        "hardware_accessed": False,
        "metric_calibration_used": False,
        "camera_transform_supported_by_candidate_manifest": False,
        "authority": contract["authority"],
        "contract_lineage": {
            "path": str(contract_path),
            "sha256": sha256_file(contract_path),
        },
        "candidate_manifest_lineage": {
            "path": str(manifest_path),
            "sha256": sha256_file(manifest_path),
            "candidate_digest": manifest.get("candidate_digest"),
        },
        "route_lineage": {
            "path": str(route_path),
            "sha256": sha256_file(route_path),
            "route_id": route.get("route_id"),
            "v24_center_physical_joint_vector_degrees_percent": v24_center.tolist(),
        },
        "scene_lineage": {
            "capture_config_path": str(DEFAULT_CAPTURE_CONFIG.resolve()),
            "capture_config_sha256": sha256_file(DEFAULT_CAPTURE_CONFIG),
            "contact_policy_path": str(policy_path),
            "contact_policy_sha256": sha256_file(policy_path),
            "wrist_camera_model_path": str(SO101_MODEL_PATH.resolve()),
            "wrist_camera_model_sha256": sha256_file(SO101_MODEL_PATH),
            "camera_name": camera_name,
            "camera_body_name": _name(
                model,
                mujoco.mjtObj.mjOBJ_BODY,
                int(model.cam_bodyid[camera_id]),
            ),
            "camera_mount_position_m": model.cam_pos[camera_id].tolist(),
            "camera_mount_quaternion_wxyz": model.cam_quat[camera_id].tolist(),
            "camera_resolution_declared_by_model": model.cam_resolution[
                camera_id
            ].tolist(),
            "camera_focal_m": model.cam_intrinsic[camera_id][:2].tolist(),
            "camera_sensor_size_m": model.cam_sensorsize[camera_id].tolist(),
            "camera_fovy_degrees": float(model.cam_fovy[camera_id]),
            "camera_mount_provenance": (
                "vendored_upstream_simulator_geometry_not_calibrated_d405_extrinsics"
            ),
        },
        "grid_candidate_count": len(rows),
        "grid_family_summary": family_summary,
        "passed_candidate_count": passed_count,
        "ranked_candidates": ranked,
        "verdict": {
            "passed": passed_count > 0,
            "classification": (
                "simulator_frustum_candidate_found"
                if passed_count > 0
                else "no_simulator_frustum_candidate_in_frozen_grid"
            ),
            "grants_physical_reachability_or_camera_calibration": False,
        },
    }
    if output_path is not None:
        atomic_write_json(output_path, receipt)
    return receipt
