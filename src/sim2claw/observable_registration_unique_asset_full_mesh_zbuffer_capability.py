"""Full-source-mesh successor to OR76 with exact unique-asset caching."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .learning_factory_artifacts import atomic_write_json, canonical_digest
from .observable_registration_host_native_analytic_3d_renderer_capability import (
    REPO_ROOT,
    quaternion_matrix_wxyz,
    sha256_file,
)
from .observable_registration_host_native_mesh_zbuffer_renderer_capability import (
    _local_triangles_for_geom,
    _project_camera,
    _rasterize_triangle,
    load_binary_stl_triangles,
)


cv2.ocl.setUseOpenCL(False)

DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_unique_asset_full_mesh_zbuffer_capability_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_unique_asset_full_mesh_zbuffer_capability_v1"


def render_once(
    contract_path: Path = DEFAULT_CONTRACT, output_directory: Path = DEFAULT_OUTPUT
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR77 one-run receipt already exists")
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
        raise ValueError("scene and trace body ordering drifted")
    state = trace["frames"][int(trace_source["frame_index"])]
    body_positions = np.asarray(state["p"], dtype=np.float64).reshape((-1, 3))
    body_rotations = [
        quaternion_matrix_wxyz(value)
        for value in np.asarray(state["q"], dtype=np.float64).reshape((-1, 4))
    ]

    mesh_root = REPO_ROOT / contract["sources"]["mesh_asset_root"]["path"]
    asset_cache: dict[str, np.ndarray] = {}
    asset_receipts: list[dict[str, Any]] = []
    for filename in sorted({Path(mesh["asset_url"]).name for mesh in scene["meshes"]}):
        definitions = [mesh for mesh in scene["meshes"] if Path(mesh["asset_url"]).name == filename]
        expected_hashes = {mesh["asset_sha256"] for mesh in definitions}
        if len(expected_hashes) != 1:
            raise ValueError(f"manifest hash disagreement for unique asset: {filename}")
        path = mesh_root / filename
        actual_hash = sha256_file(path)
        if actual_hash != next(iter(expected_hashes)):
            raise ValueError(f"mesh asset hash mismatch: {filename}")
        triangles = load_binary_stl_triangles(path)
        asset_cache[filename] = triangles
        asset_receipts.append(
            {
                "asset": filename,
                "sha256": actual_hash,
                "source_triangle_count": len(triangles),
                "mesh_definition_count": len(definitions),
            }
        )
    meshes = {
        int(mesh["id"]): (mesh, asset_cache[Path(mesh["asset_url"]).name])
        for mesh in scene["meshes"]
    }

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
    mesh_source_triangles = 0
    mesh_raster_triangles = 0
    total_raster_triangles = 0
    mesh_definition_count = 0
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
        total_raster_triangles += len(local)
        if is_mesh:
            mesh_definition_count += 1
            mesh_source_triangles += source_count
            mesh_raster_triangles += len(local)

    output_directory.mkdir(parents=True, exist_ok=True)
    ok, encoded = cv2.imencode(".png", frame, [cv2.IMWRITE_PNG_COMPRESSION, 9])
    if not ok:
        raise RuntimeError("failed to encode OR77 capability image")
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
        "mesh_definition_count": mesh_definition_count,
        "manifest_derived_unique_mesh_asset_count": len(asset_cache),
        "unique_mesh_asset_reads": len(asset_receipts),
        "mesh_source_triangle_count": mesh_source_triangles,
        "mesh_raster_triangle_count": mesh_raster_triangles,
        "total_raster_triangle_count": total_raster_triangles,
        "depth_buffer_update_count": depth_updates,
        "occluded_fragment_count": occluded_fragments,
        "frame_coverage_fraction": coverage,
        "rgb_standard_deviation": float(frame.std()),
        "unique_rgb_triplet_count": unique_rgb,
    }
    expected = contract["gates"]
    gates = {
        "scene_body_count": metrics["scene_body_count"] == expected["expected_scene_body_count"],
        "visible_geom_count": metrics["visible_geom_count"] == expected["expected_visible_geom_count"],
        "mesh_definition_count": mesh_definition_count == expected["expected_mesh_definition_count"],
        "manifest_derived_unique_mesh_asset_count": len(asset_cache) == expected["expected_manifest_derived_unique_mesh_asset_count"],
        "unique_mesh_asset_reads": len(asset_receipts) == expected["expected_unique_mesh_asset_reads"],
        "mesh_source_triangle_count": mesh_source_triangles == expected["expected_mesh_source_triangle_count"],
        "mesh_raster_triangle_count": mesh_raster_triangles == expected["expected_mesh_raster_triangle_count"],
        "every_mesh_asset_hash_match": len(asset_receipts) == len(asset_cache),
        "every_mesh_definition_bound_to_cache": mesh_definition_count == len(scene["meshes"]),
        "depth_test_occlusion": depth_updates > 0 and occluded_fragments > 0,
        "frame_coverage_fraction": coverage >= expected["minimum_frame_coverage_fraction"],
        "rgb_standard_deviation": metrics["rgb_standard_deviation"] >= expected["minimum_rgb_standard_deviation"],
        "unique_rgb_triplet_count": unique_rgb >= expected["minimum_unique_rgb_triplet_count"],
        "deterministic_repeat_hash": encoded.tobytes() == repeat.tobytes(),
    }
    passed = all(gates.values())
    receipt: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_unique_asset_full_mesh_zbuffer_capability_receipt.v1",
        "experiment_id": contract["experiment_id"],
        "status": "PASS_UNIQUE_ASSET_FULL_MESH_ZBUFFER_CAPABILITY" if passed else "TERMINAL_UNIQUE_ASSET_FULL_MESH_ZBUFFER_GATE_FAILED",
        "proof_class": contract["proof_class"],
        "contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)},
        "camera": contract["camera"],
        "renderer": renderer,
        "unique_mesh_assets": asset_receipts,
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
            "unique_mesh_asset_reads": len(asset_receipts),
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
        "reviewer_decision": "ADVANCE_TO_DEVELOPMENT_STATIC_FULL_MESH_COMPARISON" if passed else "DO_NOT_ADVANCE_FULL_MESH_RENDERER",
        "next_transition": "freeze_or78_static_development_full_mesh_comparison" if passed else "revise_or77_without_footage_or_split_expansion",
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(render_once(), sort_keys=True))
