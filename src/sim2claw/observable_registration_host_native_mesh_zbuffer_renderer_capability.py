"""Footage-blind mesh/primitive triangle rasterizer with a software depth buffer."""

from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .learning_factory_artifacts import atomic_write_json, canonical_digest
from .observable_registration_host_native_analytic_3d_renderer_capability import (
    REPO_ROOT,
    camera_basis,
    quaternion_matrix_wxyz,
    sha256_file,
)


cv2.ocl.setUseOpenCL(False)

DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_host_native_mesh_zbuffer_renderer_capability_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_host_native_mesh_zbuffer_renderer_capability_v1"


def load_binary_stl_triangles(path: Path) -> np.ndarray:
    data = path.read_bytes()
    if len(data) < 84:
        raise ValueError(f"STL too short: {path.name}")
    count = struct.unpack_from("<I", data, 80)[0]
    if len(data) != 84 + 50 * count:
        raise ValueError(f"STL is not canonical binary: {path.name}")
    dtype = np.dtype(
        [
            ("normal", "<f4", (3,)),
            ("vertices", "<f4", (3, 3)),
            ("attribute", "<u2"),
        ]
    )
    records = np.frombuffer(data, dtype=dtype, count=count, offset=84)
    return np.asarray(records["vertices"], dtype=np.float64)


def deterministic_triangle_indices(count: int, maximum: int) -> np.ndarray:
    if count < 1 or maximum < 1:
        raise ValueError("triangle counts must be positive")
    retained = min(count, maximum)
    return np.floor(np.arange(retained, dtype=np.float64) * count / retained).astype(np.int64)


def _box_triangles(half_size: np.ndarray) -> np.ndarray:
    vertices = np.asarray(
        [
            [-1, -1, -1], [-1, -1, 1], [-1, 1, -1], [-1, 1, 1],
            [1, -1, -1], [1, -1, 1], [1, 1, -1], [1, 1, 1],
        ],
        dtype=np.float64,
    ) * half_size
    faces = np.asarray(
        [
            [0, 2, 3], [0, 3, 1], [4, 5, 7], [4, 7, 6],
            [0, 1, 5], [0, 5, 4], [2, 6, 7], [2, 7, 3],
            [0, 4, 6], [0, 6, 2], [1, 3, 7], [1, 7, 5],
        ],
        dtype=np.int64,
    )
    return vertices[faces]


def _uv_sphere_triangles(radii: np.ndarray, latitudes: int, longitudes: int) -> np.ndarray:
    vertices: list[list[float]] = []
    for latitude in range(latitudes + 1):
        phi = np.pi * latitude / latitudes
        for longitude in range(longitudes):
            theta = 2.0 * np.pi * longitude / longitudes
            vertices.append(
                [
                    radii[0] * np.sin(phi) * np.cos(theta),
                    radii[1] * np.sin(phi) * np.sin(theta),
                    radii[2] * np.cos(phi),
                ]
            )
    array = np.asarray(vertices, dtype=np.float64)
    faces: list[list[int]] = []
    for latitude in range(latitudes):
        for longitude in range(longitudes):
            nxt = (longitude + 1) % longitudes
            a = latitude * longitudes + longitude
            b = latitude * longitudes + nxt
            c = (latitude + 1) * longitudes + longitude
            d = (latitude + 1) * longitudes + nxt
            if latitude > 0:
                faces.append([a, c, b])
            if latitude < latitudes - 1:
                faces.append([b, c, d])
    return array[np.asarray(faces, dtype=np.int64)]


def _cylinder_triangles(radius: float, half_length: float, segments: int) -> np.ndarray:
    vertices: list[list[float]] = []
    for z in (-half_length, half_length):
        for segment in range(segments):
            theta = 2.0 * np.pi * segment / segments
            vertices.append([radius * np.cos(theta), radius * np.sin(theta), z])
    vertices.extend([[0.0, 0.0, -half_length], [0.0, 0.0, half_length]])
    array = np.asarray(vertices, dtype=np.float64)
    bottom_center = 2 * segments
    top_center = bottom_center + 1
    faces: list[list[int]] = []
    for segment in range(segments):
        nxt = (segment + 1) % segments
        faces.extend(
            [
                [segment, segments + segment, nxt],
                [nxt, segments + segment, segments + nxt],
                [bottom_center, nxt, segment],
                [top_center, segments + segment, segments + nxt],
            ]
        )
    return array[np.asarray(faces, dtype=np.int64)]


def _local_triangles_for_geom(
    geom: dict[str, Any],
    *,
    meshes: dict[int, tuple[dict[str, Any], np.ndarray]],
    config: dict[str, Any],
) -> tuple[np.ndarray, int, bool]:
    geom_type = str(geom["type"])
    size = np.asarray(geom["size"], dtype=np.float64)
    if geom_type in {"box", "plane"}:
        half_size = np.maximum(size, [0.001, 0.001, 0.005] if geom_type == "plane" else 0.001)
        triangles = _box_triangles(half_size)
        return triangles, len(triangles), False
    if geom_type in {"sphere", "ellipsoid"}:
        radii = np.repeat(size[0], 3) if geom_type == "sphere" else size
        triangles = _uv_sphere_triangles(
            radii,
            int(config["sphere_latitude_segments"]),
            int(config["sphere_longitude_segments"]),
        )
        return triangles, len(triangles), False
    if geom_type == "cylinder":
        triangles = _cylinder_triangles(float(size[0]), float(size[1]), int(config["cylinder_segments"]))
        return triangles, len(triangles), False
    if geom_type == "capsule":
        cylinder = _cylinder_triangles(float(size[0]), float(size[1]), int(config["cylinder_segments"]))
        sphere = _uv_sphere_triangles(
            np.repeat(size[0], 3),
            int(config["sphere_latitude_segments"]),
            int(config["sphere_longitude_segments"]),
        )
        lower = sphere + np.asarray([0.0, 0.0, -float(size[1])])
        upper = sphere + np.asarray([0.0, 0.0, float(size[1])])
        triangles = np.concatenate([cylinder, lower, upper], axis=0)
        return triangles, len(triangles), False
    if geom_type == "mesh":
        mesh, source_triangles = meshes[int(geom["mesh_id"])]
        maximum = int(config["maximum_triangles_per_mesh_instance"])
        indices = deterministic_triangle_indices(len(source_triangles), maximum)
        triangles = source_triangles[indices].copy()
        triangles *= np.asarray(mesh["scale"], dtype=np.float64)
        triangles -= np.asarray(mesh["compiler_position"], dtype=np.float64)
        compiler_inverse = quaternion_matrix_wxyz(mesh["compiler_quaternion_wxyz"]).T
        triangles = triangles @ compiler_inverse.T
        return triangles, len(source_triangles), True
    raise ValueError(f"unsupported geom type: {geom_type}")


def _project_camera(
    triangles: np.ndarray, camera: dict[str, Any], width: int, height: int
) -> tuple[np.ndarray, np.ndarray]:
    position, right, up, forward = camera_basis(camera)
    delta = triangles - position
    depth = delta @ forward
    focal = 0.5 * height / np.tan(np.deg2rad(float(camera["fov_degrees"])) * 0.5)
    pixels = np.empty(triangles.shape[:2] + (2,), dtype=np.float64)
    pixels[..., 0] = width * 0.5 + focal * (delta @ right) / depth
    pixels[..., 1] = height * 0.5 - focal * (delta @ up) / depth
    return pixels, depth


def _rasterize_triangle(
    frame: np.ndarray,
    zbuffer: np.ndarray,
    pixels: np.ndarray,
    depths: np.ndarray,
    color_bgr: np.ndarray,
) -> tuple[int, int]:
    height, width = zbuffer.shape
    if np.any(depths <= 1e-4) or not np.all(np.isfinite(pixels)):
        return 0, 0
    minimum = np.maximum(np.floor(pixels.min(axis=0)).astype(int), [0, 0])
    maximum = np.minimum(np.ceil(pixels.max(axis=0)).astype(int), [width - 1, height - 1])
    if np.any(maximum < minimum):
        return 0, 0
    x0, y0 = minimum
    x1, y1 = maximum
    x, y = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
    a, b, c = pixels
    denominator = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
    if abs(float(denominator)) <= 1e-12:
        return 0, 0
    w0 = ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (y - c[1])) / denominator
    w1 = ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (y - c[1])) / denominator
    w2 = 1.0 - w0 - w1
    inside = (w0 >= -1e-9) & (w1 >= -1e-9) & (w2 >= -1e-9)
    fragments = int(inside.sum())
    if fragments == 0:
        return 0, 0
    inverse_depth = w0 / depths[0] + w1 / depths[1] + w2 / depths[2]
    depth = np.where(inverse_depth > 0.0, 1.0 / inverse_depth, np.inf)
    local_z = zbuffer[y0 : y1 + 1, x0 : x1 + 1]
    update = inside & (depth < local_z)
    updates = int(update.sum())
    occluded = fragments - updates
    if updates:
        local_z[update] = depth[update]
        local_frame = frame[y0 : y1 + 1, x0 : x1 + 1]
        local_frame[update] = color_bgr
    return updates, occluded


def render_once(
    contract_path: Path = DEFAULT_CONTRACT, output_directory: Path = DEFAULT_OUTPUT
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR76 one-run receipt already exists")
    contract = json.loads(contract_path.read_text())
    for name, source in contract["sources"].items():
        if name == "mesh_asset_root":
            continue
        if sha256_file(REPO_ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['path']}")
    scene_source = contract["sources"]["shared_scene_manifest"]
    scene = json.loads((REPO_ROOT / scene_source["path"]).read_text())
    if scene["revision_sha256"] != scene_source["revision_sha256"]:
        raise ValueError("scene revision mismatch")
    trace_source = contract["sources"]["development_state_trace"]
    trace = json.loads((REPO_ROOT / trace_source["path"]).read_text())
    if trace["body_names"] != [body["name"] for body in scene["bodies"]]:
        raise ValueError("scene and state body ordering drifted")
    frame_state = trace["frames"][int(trace_source["frame_index"])]
    body_positions = np.asarray(frame_state["p"], dtype=np.float64).reshape((-1, 3))
    body_rotations = [
        quaternion_matrix_wxyz(value)
        for value in np.asarray(frame_state["q"], dtype=np.float64).reshape((-1, 4))
    ]

    mesh_root = REPO_ROOT / contract["sources"]["mesh_asset_root"]["path"]
    meshes: dict[int, tuple[dict[str, Any], np.ndarray]] = {}
    asset_hash_matches: list[dict[str, Any]] = []
    for mesh in scene["meshes"]:
        path = mesh_root / Path(mesh["asset_url"]).name
        actual_hash = sha256_file(path)
        if actual_hash != mesh["asset_sha256"]:
            raise ValueError(f"mesh asset hash mismatch: {path.name}")
        triangles = load_binary_stl_triangles(path)
        meshes[int(mesh["id"])] = (mesh, triangles)
        asset_hash_matches.append(
            {
                "mesh_id": int(mesh["id"]),
                "asset": path.name,
                "sha256": actual_hash,
                "source_triangle_count": len(triangles),
            }
        )

    renderer = contract["renderer"]
    width = int(renderer["width_px"])
    height = int(renderer["height_px"])
    background_bgr = np.asarray(renderer["background_rgb"], dtype=np.uint8)[::-1]
    frame = np.empty((height, width, 3), dtype=np.uint8)
    frame[:] = background_bgr
    zbuffer = np.full((height, width), np.inf, dtype=np.float64)
    camera = {
        "name": "or73_shared_development_camera",
        "position": contract["camera"]["position"],
        "target": contract["camera"]["target"],
        "fov_degrees": contract["camera"]["fov_degrees"],
    }
    light = np.asarray(renderer["lighting"]["world_direction"], dtype=np.float64)
    light /= np.linalg.norm(light)
    ambient = float(renderer["lighting"]["ambient"])
    diffuse = float(renderer["lighting"]["diffuse"])
    total_triangles = 0
    mesh_source_triangles = 0
    mesh_raster_triangles = 0
    mesh_instance_count = 0
    depth_updates = 0
    occluded_fragments = 0

    for geom in scene["geoms"]:
        local, source_count, is_mesh = _local_triangles_for_geom(
            geom, meshes=meshes, config=renderer
        )
        body_id = int(geom["body_id"])
        geom_rotation = body_rotations[body_id] @ quaternion_matrix_wxyz(geom["quaternion_wxyz"])
        geom_center = body_positions[body_id] + body_rotations[body_id] @ np.asarray(geom["position"], dtype=np.float64)
        world = local @ geom_rotation.T + geom_center
        pixels, depths = _project_camera(world, camera, width, height)
        base_rgb = np.clip(np.asarray(geom["rgba"][:3], dtype=np.float64), 0.0, 1.0)
        for triangle, triangle_pixels, triangle_depths in zip(world, pixels, depths, strict=True):
            normal = np.cross(triangle[1] - triangle[0], triangle[2] - triangle[0])
            normal_norm = float(np.linalg.norm(normal))
            lambert = 0.0 if normal_norm <= 1e-12 else abs(float((normal / normal_norm) @ light))
            intensity = np.clip(ambient + diffuse * lambert, 0.0, 1.0)
            color_bgr = np.rint(base_rgb[::-1] * intensity * 255.0).astype(np.uint8)
            updates, occluded = _rasterize_triangle(
                frame, zbuffer, triangle_pixels, triangle_depths, color_bgr
            )
            depth_updates += updates
            occluded_fragments += occluded
        total_triangles += len(local)
        if is_mesh:
            mesh_instance_count += 1
            mesh_source_triangles += source_count
            mesh_raster_triangles += len(local)

    output_directory.mkdir(parents=True, exist_ok=True)
    ok, encoded = cv2.imencode(".png", frame, [cv2.IMWRITE_PNG_COMPRESSION, 9])
    if not ok:
        raise RuntimeError("failed to encode mesh z-buffer capability image")
    frame_path = output_directory / "capability_frame.png"
    frame_path.write_bytes(encoded.tobytes())
    ok_repeat, repeat = cv2.imencode(".png", frame, [cv2.IMWRITE_PNG_COMPRESSION, 9])
    if not ok_repeat:
        raise RuntimeError("failed repeat encoding")
    coverage = float(np.isfinite(zbuffer).mean())
    unique_rgb = int(np.unique(frame.reshape((-1, 3)), axis=0).shape[0])
    metrics = {
        "scene_body_count": len(scene["bodies"]),
        "visible_geom_count": len(scene["geoms"]),
        "manifest_mesh_count": len(scene["meshes"]),
        "unique_mesh_asset_count": len({row["asset"] for row in asset_hash_matches}),
        "mesh_instance_count": mesh_instance_count,
        "mesh_source_triangle_count": mesh_source_triangles,
        "mesh_raster_triangle_count": mesh_raster_triangles,
        "total_raster_triangle_count": total_triangles,
        "depth_buffer_update_count": depth_updates,
        "occluded_fragment_count": occluded_fragments,
        "frame_coverage_fraction": coverage,
        "rgb_standard_deviation": float(frame.std()),
        "unique_rgb_triplet_count": unique_rgb,
    }
    gates_config = contract["gates"]
    gates = {
        "scene_body_count": metrics["scene_body_count"] == gates_config["expected_scene_body_count"],
        "visible_geom_count": metrics["visible_geom_count"] == gates_config["expected_visible_geom_count"],
        "manifest_mesh_count": metrics["manifest_mesh_count"] == gates_config["expected_manifest_mesh_count"],
        "unique_mesh_asset_count": metrics["unique_mesh_asset_count"] == gates_config["expected_unique_mesh_asset_count"],
        "every_mesh_asset_hash_match": len(asset_hash_matches) == gates_config["expected_manifest_mesh_count"],
        "every_mesh_instance_ingested": mesh_instance_count == gates_config["expected_manifest_mesh_count"],
        "source_mesh_triangles_exceed_raster": mesh_source_triangles > mesh_raster_triangles,
        "depth_test_occlusion": occluded_fragments > 0 and depth_updates > 0,
        "frame_coverage_fraction": coverage >= gates_config["minimum_frame_coverage_fraction"],
        "rgb_standard_deviation": metrics["rgb_standard_deviation"] >= gates_config["minimum_rgb_standard_deviation"],
        "unique_rgb_triplet_count": unique_rgb >= gates_config["minimum_unique_rgb_triplet_count"],
        "deterministic_repeat_hash": encoded.tobytes() == repeat.tobytes(),
    }
    passed = all(gates.values())
    receipt: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_host_native_mesh_zbuffer_renderer_capability_receipt.v1",
        "experiment_id": contract["experiment_id"],
        "status": "PASS_MESH_ASSET_ZBUFFER_RENDERER_CAPABILITY" if passed else "TERMINAL_MESH_ZBUFFER_RENDERER_CAPABILITY_GATE_FAILED",
        "proof_class": contract["proof_class"],
        "contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)},
        "camera": contract["camera"],
        "renderer": renderer,
        "mesh_assets": asset_hash_matches,
        "frame": {
            "path": str(frame_path.relative_to(REPO_ROOT)),
            "sha256": sha256_file(frame_path),
            "width_px": width,
            "height_px": height,
        },
        "metrics": metrics,
        "gates": gates,
        "execution": {
            "capability_frames": 1,
            "development_state_trace_reads": 1,
            "mesh_asset_reads": len(asset_hash_matches),
            "physical_video_reads": 0,
            "validation_reads": 0,
            "evaluator_heldout_reads": 0,
            "candidate_videos": 0,
            "simulator_replays": 0,
            "parameter_fits": 0,
            "hardware_actions": 0,
            "paid_compute": False,
        },
        "claim_limits": contract["claim_limits"],
        "reviewer_decision": "ADVANCE_TO_DEVELOPMENT_STATIC_MESH_RENDERER_COMPARISON" if passed else "DO_NOT_ADVANCE_MESH_RENDERER",
        "next_transition": "freeze_or77_static_development_mesh_renderer_comparison" if passed else "revise_or76_without_footage_or_split_expansion",
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(render_once(), sort_keys=True))
