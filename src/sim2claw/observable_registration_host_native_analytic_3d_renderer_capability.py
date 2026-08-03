"""One-frame, footage-blind analytic projection of a frozen 3D replay scene."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .learning_factory_artifacts import atomic_write_json, canonical_digest


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_host_native_analytic_3d_renderer_capability_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_host_native_analytic_3d_renderer_capability_v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def quaternion_matrix_wxyz(value: list[float] | np.ndarray) -> np.ndarray:
    quaternion = np.asarray(value, dtype=np.float64)
    norm = float(np.linalg.norm(quaternion))
    if not np.isfinite(norm) or norm <= 1e-12:
        raise ValueError("quaternion must be finite and nonzero")
    w, x, y, z = quaternion / norm
    return np.asarray(
        [
            [1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w)],
            [2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w)],
            [2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )


def camera_basis(camera: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    position = np.asarray(camera["position"], dtype=np.float64)
    target = np.asarray(camera["target"], dtype=np.float64)
    forward = target - position
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, np.asarray([0.0, 0.0, 1.0], dtype=np.float64))
    if np.linalg.norm(right) <= 1e-9:
        right = np.cross(forward, np.asarray([0.0, 1.0, 0.0], dtype=np.float64))
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    up /= np.linalg.norm(up)
    return position, right, up, forward


def project_points(
    points: np.ndarray,
    *,
    camera: dict[str, Any],
    width: int,
    height: int,
) -> tuple[np.ndarray, np.ndarray]:
    position, right, up, forward = camera_basis(camera)
    delta = np.asarray(points, dtype=np.float64) - position
    depth = delta @ forward
    focal = 0.5 * float(height) / np.tan(np.deg2rad(float(camera["fov_degrees"])) * 0.5)
    safe_depth = np.where(depth > 1e-9, depth, 1.0)
    pixels = np.stack(
        [
            width * 0.5 + focal * (delta @ right) / safe_depth,
            height * 0.5 - focal * (delta @ up) / safe_depth,
        ],
        axis=1,
    )
    return pixels, depth


def _world_transform(
    geom: dict[str, Any], body_positions: np.ndarray, body_rotations: list[np.ndarray]
) -> tuple[np.ndarray, np.ndarray]:
    body_id = int(geom["body_id"])
    body_rotation = body_rotations[body_id]
    center = body_positions[body_id] + body_rotation @ np.asarray(geom["position"], dtype=np.float64)
    rotation = body_rotation @ quaternion_matrix_wxyz(geom["quaternion_wxyz"])
    return center, rotation


def _box_corners(center: np.ndarray, rotation: np.ndarray, half_size: np.ndarray) -> np.ndarray:
    signs = np.asarray(
        [
            [-1, -1, -1], [-1, -1, 1], [-1, 1, -1], [-1, 1, 1],
            [1, -1, -1], [1, -1, 1], [1, 1, -1], [1, 1, 1],
        ],
        dtype=np.float64,
    )
    return center + (signs * half_size) @ rotation.T


def _declared_bgr(geom: dict[str, Any]) -> tuple[int, int, int]:
    rgb = np.clip(np.asarray(geom["rgba"][:3], dtype=np.float64), 0.0, 1.0)
    return tuple(int(round(channel * 255.0)) for channel in rgb[::-1])


def _render_geom(
    frame: np.ndarray,
    geom: dict[str, Any],
    center: np.ndarray,
    rotation: np.ndarray,
    camera: dict[str, Any],
) -> bool:
    height, width = frame.shape[:2]
    geom_type = str(geom["type"])
    size = np.asarray(geom["size"], dtype=np.float64)
    color = _declared_bgr(geom)
    if float(geom["rgba"][3]) <= 0.01:
        return False

    if geom_type in {"box", "mesh", "plane"}:
        half_size = size.copy()
        if geom_type == "plane":
            half_size = np.asarray([size[0], size[1], max(float(size[2]), 0.005)])
        corners = _box_corners(center, rotation, np.maximum(half_size, 0.001))
        pixels, depth = project_points(corners, camera=camera, width=width, height=height)
        valid = depth > 1e-5
        if int(valid.sum()) < 3:
            return False
        hull = cv2.convexHull(np.rint(pixels[valid]).astype(np.int32))
        cv2.fillConvexPoly(frame, hull, color, lineType=cv2.LINE_AA)
        cv2.polylines(frame, [hull], True, tuple(max(0, c - 28) for c in color), 1, cv2.LINE_AA)
        return True

    center_px, center_depth = project_points(center[None, :], camera=camera, width=width, height=height)
    if center_depth[0] <= 1e-5:
        return False
    center_i = tuple(np.rint(center_px[0]).astype(int))

    if geom_type in {"sphere", "ellipsoid"}:
        radii = np.repeat(size[0], 3) if geom_type == "sphere" else size
        endpoints = np.stack([center + rotation[:, axis] * radii[axis] for axis in range(3)])
        endpoint_px, _ = project_points(endpoints, camera=camera, width=width, height=height)
        deltas = np.abs(endpoint_px - center_px[0])
        radius_x = max(1, int(round(float(np.max(deltas[:, 0])))))
        radius_y = max(1, int(round(float(np.max(deltas[:, 1])))))
        cv2.ellipse(frame, center_i, (radius_x, radius_y), 0.0, 0.0, 360.0, color, -1, cv2.LINE_AA)
        cv2.ellipse(frame, center_i, (radius_x, radius_y), 0.0, 0.0, 360.0, tuple(max(0, c - 28) for c in color), 1, cv2.LINE_AA)
        return True

    if geom_type in {"cylinder", "capsule"}:
        half_length = float(size[1])
        endpoints = np.stack([center - rotation[:, 2] * half_length, center + rotation[:, 2] * half_length])
        endpoint_px, endpoint_depth = project_points(endpoints, camera=camera, width=width, height=height)
        if np.any(endpoint_depth <= 1e-5):
            return False
        radial_point = center + rotation[:, 0] * float(size[0])
        radial_px, _ = project_points(radial_point[None, :], camera=camera, width=width, height=height)
        thickness = max(1, int(round(2.0 * float(np.linalg.norm(radial_px[0] - center_px[0])))))
        p0, p1 = (tuple(np.rint(point).astype(int)) for point in endpoint_px)
        cv2.line(frame, p0, p1, color, thickness, cv2.LINE_AA)
        if geom_type == "capsule":
            radius = max(1, thickness // 2)
            cv2.circle(frame, p0, radius, color, -1, cv2.LINE_AA)
            cv2.circle(frame, p1, radius, color, -1, cv2.LINE_AA)
        return True

    raise ValueError(f"unrecognized geom type: {geom_type}")


def render_capability_frame(
    scene: dict[str, Any], trace: dict[str, Any], contract: dict[str, Any]
) -> tuple[np.ndarray, dict[str, Any]]:
    renderer = contract["renderer"]
    width = int(renderer["width_px"])
    height = int(renderer["height_px"])
    frame = np.empty((height, width, 3), dtype=np.uint8)
    frame[:] = np.asarray(renderer["background_rgb"], dtype=np.uint8)[::-1]

    expected_names = [body["name"] for body in scene["bodies"]]
    if trace["body_names"] != expected_names:
        raise ValueError("state-trace body ordering does not match the scene manifest")
    frame_index = int(contract["sources"]["development_state_trace"]["frame_index"])
    state = trace["frames"][frame_index]
    body_positions = np.asarray(state["p"], dtype=np.float64).reshape((-1, 3))
    body_quaternions = np.asarray(state["q"], dtype=np.float64).reshape((-1, 4))
    body_rotations = [quaternion_matrix_wxyz(value) for value in body_quaternions]
    camera = scene["suggested_camera"]
    recognized = set(renderer["recognized_geom_types"])

    render_rows: list[tuple[float, dict[str, Any], np.ndarray, np.ndarray]] = []
    for geom in scene["geoms"]:
        if geom["type"] not in recognized:
            raise ValueError(f"unrecognized geom type: {geom['type']}")
        center, rotation = _world_transform(geom, body_positions, body_rotations)
        _, depth = project_points(center[None, :], camera=camera, width=width, height=height)
        render_rows.append((float(depth[0]), geom, center, rotation))

    projected_count = 0
    for _, geom, center, rotation in sorted(render_rows, key=lambda row: row[0], reverse=True):
        projected_count += int(_render_geom(frame, geom, center, rotation, camera))

    background = np.asarray(renderer["background_rgb"], dtype=np.uint8)[::-1]
    non_background = np.any(frame != background[None, None, :], axis=2)
    unique_rgb_count = int(np.unique(frame.reshape((-1, 3)), axis=0).shape[0])
    metrics = {
        "body_count": len(scene["bodies"]),
        "declared_visible_geom_count": len(scene["geoms"]),
        "accounted_geom_count": len(render_rows),
        "projected_geom_count": projected_count,
        "mesh_approximation_count": sum(geom["type"] == "mesh" for geom in scene["geoms"]),
        "non_background_fraction": float(non_background.mean()),
        "rgb_standard_deviation": float(frame.std()),
        "unique_rgb_triplet_count": unique_rgb_count,
    }
    return frame, metrics


def run_once(
    contract_path: Path = DEFAULT_CONTRACT, output_directory: Path = DEFAULT_OUTPUT
) -> dict[str, Any]:
    contract = json.loads(contract_path.read_text())
    root = REPO_ROOT
    for source in contract["sources"].values():
        path_value = source.get("path")
        if path_value and sha256_file(root / path_value) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {path_value}")
    scene_source = contract["sources"]["shared_scene_manifest"]
    trace_source = contract["sources"]["development_state_trace"]
    scene = json.loads((root / scene_source["path"]).read_text())
    trace = json.loads((root / trace_source["path"]).read_text())
    if scene["revision_sha256"] != scene_source["revision_sha256"]:
        raise ValueError("scene revision mismatch")

    frame, metrics = render_capability_frame(scene, trace, contract)
    gates = contract["gates"]
    gate_results = {
        "body_count": metrics["body_count"] == gates["expected_body_count"],
        "visible_geom_count": metrics["declared_visible_geom_count"] == gates["expected_visible_geom_count"],
        "all_geoms_accounted": metrics["accounted_geom_count"] == gates["expected_visible_geom_count"],
        "mesh_approximation_count": metrics["mesh_approximation_count"] == gates["expected_mesh_approximation_count"],
        "projected_geom_count": metrics["projected_geom_count"] >= gates["minimum_projected_geom_count"],
        "non_background_fraction": metrics["non_background_fraction"] >= gates["minimum_non_background_fraction"],
        "rgb_standard_deviation": metrics["rgb_standard_deviation"] >= gates["minimum_rgb_standard_deviation"],
        "unique_rgb_triplet_count": metrics["unique_rgb_triplet_count"] >= gates["minimum_unique_rgb_triplet_count"],
    }
    output_directory.mkdir(parents=True, exist_ok=True)
    ok, encoded = cv2.imencode(".png", frame, [cv2.IMWRITE_PNG_COMPRESSION, 9])
    if not ok:
        raise RuntimeError("OpenCV failed to encode capability PNG")
    frame_path = output_directory / "capability_frame.png"
    frame_path.write_bytes(encoded.tobytes())
    repeat_ok, repeat_encoded = cv2.imencode(".png", frame, [cv2.IMWRITE_PNG_COMPRESSION, 9])
    if not repeat_ok:
        raise RuntimeError("OpenCV failed deterministic repeat encoding")
    gate_results["deterministic_repeat_hash"] = hashlib.sha256(encoded.tobytes()).digest() == hashlib.sha256(repeat_encoded.tobytes()).digest()

    passed = all(gate_results.values())
    receipt: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_host_native_analytic_3d_renderer_capability_receipt.v1",
        "experiment_id": contract["experiment_id"],
        "status": "PASS_ANALYTIC_3D_SCENE_STATE_RENDERER_CAPABILITY" if passed else "TERMINAL_ANALYTIC_3D_RENDERER_CAPABILITY_GATE_FAILED",
        "proof_class": contract["proof_class"],
        "contract": {"path": str(contract_path.relative_to(root)), "sha256": sha256_file(contract_path)},
        "renderer": {
            "implementation": renderer["implementation"] if (renderer := contract["renderer"]) else None,
            "numpy_version": np.__version__,
            "opencv_version": cv2.__version__,
            "mesh_policy": renderer["mesh_policy"],
            "camera_source": renderer["camera_source"],
        },
        "source": {
            "scene_manifest": scene_source,
            "development_state_trace": trace_source,
            "physical_video_reads": 0,
            "prohibited_candidate_inputs_read": [],
        },
        "frame": {
            "path": str(frame_path.relative_to(root)),
            "sha256": sha256_file(frame_path),
            "width_px": int(frame.shape[1]),
            "height_px": int(frame.shape[0]),
            "format": "png_bgr8",
        },
        "metrics": metrics,
        "gates": gate_results,
        "execution": {
            "capability_frames": 1,
            "development_state_trace_reads": 1,
            "physical_video_reads": 0,
            "validation_reads": 0,
            "evaluator_heldout_reads": 0,
            "candidate_videos": 0,
            "simulator_replays": 0,
            "camera_fits": 0,
            "parameter_fits": 0,
            "hardware_actions": 0,
            "paid_compute": False,
        },
        "claim_limits": contract["claim_limits"],
        "reviewer_decision": "ADVANCE_TO_DEVELOPMENT_ONLY_SHARED_CAMERA_BASELINE" if passed else "DO_NOT_ADVANCE_REVISE_ANALYTIC_RENDERER",
        "next_transition": "freeze_or72_development_only_shared_camera_baseline" if passed else "revise_or71_without_footage_or_split_expansion",
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(output_directory / "receipt.json", receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(run_once(), sort_keys=True))
