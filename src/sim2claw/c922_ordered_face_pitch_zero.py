"""Hash-bound, no-fit rank preflight for future C922 ordered-face annotations."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import mujoco
import numpy as np

from .learning_factory_artifacts import sha256_file
from .paths import REPO_ROOT
from .physical_fk_frame import load_physical_fk_contract

DEFAULT_CONTRACT_PATH = (
    REPO_ROOT / "configs/evaluations/c922_ordered_face_pitch_zero_v1.json"
)
CONTRACT_SCHEMA = "sim2claw.c922_ordered_link_face_rank_preflight_contract.v1"
ANNOTATION_SCHEMA = "sim2claw.c922_ordered_link_face_annotations.v1"
POSE_RECEIPT_SCHEMA = "sim2claw.c922_ordered_link_face_pose_receipt.v1"
RESULT_SCHEMA = "sim2claw.c922_ordered_link_face_rank_preflight.v1"


class OrderedFaceRankPreflightError(RuntimeError):
    """A frozen contract or future annotation lineage is incomplete or drifted."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise OrderedFaceRankPreflightError(message)


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise OrderedFaceRankPreflightError(f"cannot read JSON {path}: {error}") from error
    _require(isinstance(value, dict), f"JSON root must be an object: {path}")
    return value


def _resolve(parent: Path, value: object) -> Path:
    _require(isinstance(value, str) and value, "lineage path is missing")
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (parent / path).resolve()


def _validate_contract(contract: Mapping[str, Any]) -> None:
    _require(contract.get("schema_version") == CONTRACT_SCHEMA, "unexpected contract schema")
    _require(
        contract.get("status") == "preregistered_readiness_only_no_capture_fit_or_authority",
        "contract status widened",
    )
    authority = contract.get("authority")
    _require(
        isinstance(authority, dict) and authority and not any(authority.values()),
        "all authority must remain false",
    )
    camera = contract.get("camera")
    _require(
        isinstance(camera, dict)
        and camera.get("fixed_for_all_poses") is True
        and camera.get("fit_intrinsics") is False,
        "C922 must be fixed and its intrinsics must not be fit",
    )
    poses = contract.get("candidate_poses")
    _require(isinstance(poses, list) and len(poses) == 4, "exactly four poses are required")
    _require(
        [row.get("split") for row in poses] == ["rank", "rank", "rank", "held_out"],
        "three rank poses and one held-out pose are required",
    )
    _require(
        all(np.asarray(row.get("settled_actual")).shape == (6,) for row in poses),
        "each frozen pose must have six joints",
    )
    faces = contract.get("faces")
    _require(isinstance(faces, list) and len(faces) == 3, "exactly three faces are required")
    _require(
        len({row.get("mujoco_body") for row in faces}) == 3,
        "faces must belong to three distinct bodies",
    )
    for face in faces:
        points = np.asarray(face.get("ordered_points_body_xyz_m"), dtype=np.float64)
        _require(points.shape == (4, 3), "each face must freeze four ordered CAD corners")
        source = face.get("source_visual_mesh")
        _require(
            isinstance(source, dict)
            and len(str(source.get("sha256", ""))) == 64
            and len(source.get("triangle_indices_zero_based", [])) == 2,
            "each face must bind two triangles from an observable visual mesh",
        )
        mesh_path = (REPO_ROOT / str(source.get("path", ""))).resolve()
        _require(
            mesh_path.is_file() and sha256_file(mesh_path) == source["sha256"],
            "visual mesh lineage drifted",
        )
    rank = contract.get("rank_preflight")
    _require(
        isinstance(rank, dict)
        and len(rank.get("parameter_order", [])) == 9
        and rank.get("required_jacobian_rank") == 9
        and rank.get("minimum_sigma_min_over_sigma_max") == 0.0001
        and rank.get("held_out_used_for_rank") is False,
        "rank preflight gates drifted",
    )


def _rotation_from_rotvec(value: Sequence[float]) -> np.ndarray:
    vector = np.asarray(value, dtype=np.float64)
    _require(vector.shape == (3,) and np.all(np.isfinite(vector)), "invalid camera rotvec")
    theta = float(np.linalg.norm(vector))
    if theta < 1e-14:
        return np.eye(3)
    axis = vector / theta
    skew = np.array(
        [
            [0.0, -axis[2], axis[1]],
            [axis[2], 0.0, -axis[0]],
            [-axis[1], axis[0], 0.0],
        ]
    )
    return np.eye(3) + math.sin(theta) * skew + (1.0 - math.cos(theta)) * (skew @ skew)


def _load_intrinsics(path: Path, expected_schema: str) -> tuple[np.ndarray, np.ndarray, tuple[int, int]]:
    value = _json(path)
    _require(value.get("schema_version") == expected_schema, "unexpected intrinsics schema")
    matrix = np.asarray(value.get("camera_matrix"), dtype=np.float64)
    distortion = np.asarray(value.get("distortion_coefficients"), dtype=np.float64)
    image_size = value.get("image_size")
    _require(matrix.shape == (3, 3) and np.all(np.isfinite(matrix)), "invalid camera matrix")
    _require(distortion.shape in {(4,), (5,)} and np.all(np.isfinite(distortion)), "invalid distortion")
    _require(
        isinstance(image_size, list)
        and len(image_size) == 2
        and all(isinstance(item, int) and item > 0 for item in image_size),
        "invalid image size",
    )
    return matrix, distortion, (image_size[0], image_size[1])


def _validate_lineage(
    contract: Mapping[str, Any],
    annotations: Mapping[str, Any],
    annotation_path: Path,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[dict[str, Any]], dict[str, Any]]:
    _require(annotations.get("schema_version") == ANNOTATION_SCHEMA, "unexpected annotation schema")
    intrinsics_ref = annotations.get("intrinsics")
    _require(isinstance(intrinsics_ref, dict), "intrinsics lineage is required")
    intrinsics_path = _resolve(annotation_path.parent, intrinsics_ref.get("path"))
    _require(intrinsics_path.is_file(), "intrinsics artifact is unavailable")
    intrinsics_sha = str(intrinsics_ref.get("sha256", ""))
    _require(len(intrinsics_sha) == 64, "intrinsics sha256 is required")
    _require(sha256_file(intrinsics_path) == intrinsics_sha, "intrinsics hash drifted")
    matrix, distortion, image_size = _load_intrinsics(
        intrinsics_path, str(contract["camera"]["intrinsics_schema"])
    )

    nominal = annotations.get("nominal_camera_from_base")
    _require(isinstance(nominal, dict), "nominal camera transform is required for rank")
    rotvec = np.asarray(nominal.get("rotation_vector_rad"), dtype=np.float64)
    translation = np.asarray(nominal.get("translation_m"), dtype=np.float64)
    _require(rotvec.shape == (3,) and translation.shape == (3,), "invalid nominal camera transform")
    parameters = np.concatenate([rotvec, translation, np.zeros(3)])

    expected_poses = {row["pose_id"]: row for row in contract["candidate_poses"]}
    expected_faces = [row["face_id"] for row in contract["faces"]]
    rows = annotations.get("poses")
    _require(isinstance(rows, list) and len(rows) == 4, "all four poses are required")
    _require([row.get("pose_id") for row in rows] == list(expected_poses), "pose order drifted")
    sessions: set[str] = set()
    mounts: set[str] = set()
    validated: list[dict[str, Any]] = []
    limits = np.asarray(contract["pose_receipt"]["maximum_candidate_pose_error"])
    for row in rows:
        pose_id = str(row["pose_id"])
        expected = expected_poses[pose_id]
        _require(row.get("split") == expected["split"], f"split drifted: {pose_id}")
        image_ref = row.get("image")
        receipt_ref = row.get("pose_receipt")
        _require(isinstance(image_ref, dict), f"image lineage is required: {pose_id}")
        _require(isinstance(receipt_ref, dict), f"pose receipt lineage is required: {pose_id}")
        image_path = _resolve(annotation_path.parent, image_ref.get("path"))
        receipt_path = _resolve(annotation_path.parent, receipt_ref.get("path"))
        _require(image_path.is_file() and receipt_path.is_file(), f"lineage artifact unavailable: {pose_id}")
        image_sha = str(image_ref.get("sha256", ""))
        _require(sha256_file(image_path) == image_sha, f"image hash drifted: {pose_id}")
        _require(
            sha256_file(receipt_path) == receipt_ref.get("sha256"),
            f"pose receipt hash drifted: {pose_id}",
        )
        receipt = _json(receipt_path)
        _require(receipt.get("schema_version") == POSE_RECEIPT_SCHEMA, "unexpected pose receipt schema")
        _require(receipt.get("candidate_pose_id") == pose_id, f"receipt identity drifted: {pose_id}")
        camera = receipt.get("camera")
        gateway = receipt.get("gateway")
        _require(
            isinstance(camera, dict)
            and camera.get("role") == "c922"
            and camera.get("camera_fixed") is True,
            f"camera was not fixed: {pose_id}",
        )
        _require(camera.get("intrinsics_sha256") == intrinsics_sha, f"intrinsics lineage drifted: {pose_id}")
        _require(camera.get("image_sha256") == image_sha, f"image receipt lineage drifted: {pose_id}")
        sessions.add(str(camera.get("session_id", "")))
        mounts.add(str(camera.get("fixed_mount_token", "")))
        _require(
            isinstance(gateway, dict)
            and gateway.get("admitted") is True
            and gateway.get("safety_clamped") is False
            and gateway.get("stalled") is False,
            f"gateway receipt is not admissible: {pose_id}",
        )
        _require(receipt.get("empty_gripper") is True, f"gripper was not empty: {pose_id}")
        actual = np.asarray(receipt.get("settled_actual"), dtype=np.float64)
        frozen = np.asarray(expected["settled_actual"], dtype=np.float64)
        _require(
            actual.shape == (6,)
            and np.all(np.isfinite(actual))
            and np.all(np.abs(actual - frozen) <= limits),
            f"settled pose left frozen envelope: {pose_id}",
        )
        faces = row.get("faces")
        _require(
            isinstance(faces, dict) and set(faces) == set(expected_faces),
            f"face identity drifted: {pose_id}",
        )
        for face_id in expected_faces:
            pixels = np.asarray(faces[face_id], dtype=np.float64)
            _require(pixels.shape == (4, 2) and np.all(np.isfinite(pixels)), f"invalid corners: {pose_id}/{face_id}")
            _require(
                np.all((pixels[:, 0] >= 0) & (pixels[:, 0] < image_size[0]))
                and np.all((pixels[:, 1] >= 0) & (pixels[:, 1] < image_size[1])),
                f"corners leave image bounds: {pose_id}/{face_id}",
            )
        validated.append({"pose_id": pose_id, "split": expected["split"], "actual": actual})
    _require(len(sessions) == 1 and "" not in sessions, "C922 session changed across poses")
    _require(len(mounts) == 1 and "" not in mounts, "C922 fixed-mount token changed across poses")
    return matrix, distortion, parameters, validated, {
        "intrinsics_path": str(intrinsics_path),
        "intrinsics_sha256": intrinsics_sha,
        "camera_session_id": next(iter(sessions)),
        "fixed_mount_token": next(iter(mounts)),
    }


def _base_points(
    model: mujoco.MjModel,
    fk_contract: Mapping[str, Any],
    contract: Mapping[str, Any],
    pose: np.ndarray,
    offsets_rad: np.ndarray,
) -> np.ndarray:
    transform = fk_contract["physical_to_model_transform"]
    qpos = (
        pose * np.asarray(transform["scale"]) * np.asarray(transform["sign"])
        + np.asarray(transform["zero_offset"])
    )
    qpos[1:4] += offsets_rad
    data = mujoco.MjData(model)
    for name, value in zip(fk_contract["model_joint_order"], qpos, strict=True):
        joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        data.qpos[int(model.jnt_qposadr[joint_id])] = float(value)
    mujoco.mj_forward(model, data)
    base_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "left_base")
    base_rotation = data.xmat[base_id].reshape(3, 3)
    points = []
    for face in contract["faces"]:
        body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, face["mujoco_body"])
        _require(body_id >= 0, f"compiled model lacks body {face['mujoco_body']}")
        local = np.asarray(face["ordered_points_body_xyz_m"])
        world = (data.xmat[body_id].reshape(3, 3) @ local.T).T + data.xpos[body_id]
        points.append((base_rotation.T @ (world - data.xpos[base_id]).T).T)
    return np.concatenate(points)


def _project(
    parameters: np.ndarray,
    rows: Sequence[Mapping[str, Any]],
    model: mujoco.MjModel,
    fk_contract: Mapping[str, Any],
    contract: Mapping[str, Any],
    matrix: np.ndarray,
    distortion: np.ndarray,
) -> np.ndarray:
    rotation = _rotation_from_rotvec(parameters[:3])
    projected = []
    for row in rows:
        base = _base_points(model, fk_contract, contract, np.asarray(row["actual"]), parameters[6:9])
        camera = (rotation @ base.T).T + parameters[3:6]
        _require(np.all(camera[:, 2] > 1e-5), "nominal projection crossed behind camera")
        x, y = camera[:, 0] / camera[:, 2], camera[:, 1] / camera[:, 2]
        k1, k2, p1, p2 = distortion[:4]
        k3 = distortion[4] if distortion.size == 5 else 0.0
        r2 = x * x + y * y
        radial = 1.0 + k1 * r2 + k2 * r2**2 + k3 * r2**3
        xd = x * radial + 2.0 * p1 * x * y + p2 * (r2 + 2.0 * x * x)
        yd = y * radial + p1 * (r2 + 2.0 * y * y) + 2.0 * p2 * x * y
        projected.append(np.column_stack([matrix[0, 0] * xd + matrix[0, 2], matrix[1, 1] * yd + matrix[1, 2]]))
    return np.concatenate(projected).reshape(-1)


def evaluate_c922_ordered_face_rank_preflight(
    *,
    annotation_path: Path,
    contract_path: Path = DEFAULT_CONTRACT_PATH,
) -> dict[str, Any]:
    """Validate future evidence lineage and compute rank only; never fit parameters."""

    contract_path = contract_path.resolve()
    annotation_path = annotation_path.resolve()
    contract = _json(contract_path)
    _validate_contract(contract)
    fk_ref = contract["physical_fk_frame_contract"]
    fk_path = (REPO_ROOT / fk_ref["path"]).resolve()
    _require(sha256_file(fk_path) == fk_ref["sha256"], "physical FK contract hash drifted")
    fk_contract, model = load_physical_fk_contract(fk_path)
    matrix, distortion, parameters, rows, lineage = _validate_lineage(
        contract, _json(annotation_path), annotation_path
    )
    rank_rows = [row for row in rows if row["split"] == "rank"]
    settings = contract["rank_preflight"]
    step = float(settings["finite_difference_step"])
    baseline = _project(parameters, rank_rows, model, fk_contract, contract, matrix, distortion)
    jacobian = np.empty((baseline.size, 9))
    for index in range(9):
        plus, minus = parameters.copy(), parameters.copy()
        plus[index] += step
        minus[index] -= step
        jacobian[:, index] = (
            _project(plus, rank_rows, model, fk_contract, contract, matrix, distortion)
            - _project(minus, rank_rows, model, fk_contract, contract, matrix, distortion)
        ) / (2.0 * step)
    singular = np.linalg.svd(jacobian, compute_uv=False)
    ratio = float(singular[-1] / singular[0])
    rank = int(np.sum(singular > singular[0] * float(settings["numerical_rank_relative_tolerance"])))
    checks = {
        "lineage_complete": True,
        "camera_fixed": True,
        "annotation_complete": True,
        "jacobian_rank_9": rank == int(settings["required_jacobian_rank"]),
        "sigma_min_over_sigma_max": ratio >= float(settings["minimum_sigma_min_over_sigma_max"]),
    }
    return {
        "schema_version": RESULT_SCHEMA,
        "proof_class": "offline_annotation_lineage_and_rank_preflight_only",
        "contract": {"path": str(contract_path), "sha256": sha256_file(contract_path)},
        "annotations": {"path": str(annotation_path), "sha256": sha256_file(annotation_path)},
        "camera_lineage": lineage,
        "rank_pose_ids": [row["pose_id"] for row in rank_rows],
        "held_out_pose_ids": [row["pose_id"] for row in rows if row["split"] == "held_out"],
        "held_out_used_for_rank": False,
        "jacobian": {
            "shape": list(jacobian.shape),
            "rank": rank,
            "sigma_min_over_sigma_max": ratio,
            "singular_values": singular.tolist(),
        },
        "checks": checks,
        "ready_for_separately_reviewed_future_fit": all(checks.values()),
        "fit_performed": False,
        "authority": dict(contract["authority"]),
    }
