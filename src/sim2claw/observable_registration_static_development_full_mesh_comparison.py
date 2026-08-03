"""Compare the frozen OR73 camera with OR77 full meshes on four dev frame-zero pairs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .learning_factory_artifacts import atomic_write_json, canonical_digest
from .observable_registration_development_initial_shared_3d_camera_fit import (
    _metrics,
    _read_initial_physical_frame,
)
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

DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_static_development_full_mesh_comparison_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_static_development_full_mesh_comparison_v1"


def _load_unique_asset_cache(
    scene: dict[str, Any], mesh_root: Path
) -> tuple[dict[int, tuple[dict[str, Any], np.ndarray]], list[dict[str, Any]]]:
    asset_cache: dict[str, np.ndarray] = {}
    asset_receipts: list[dict[str, Any]] = []
    for filename in sorted({Path(mesh["asset_url"]).name for mesh in scene["meshes"]}):
        definitions = [
            mesh
            for mesh in scene["meshes"]
            if Path(mesh["asset_url"]).name == filename
        ]
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
    return meshes, asset_receipts


def _render_full_mesh_frame(
    scene: dict[str, Any],
    trace: dict[str, Any],
    meshes: dict[int, tuple[dict[str, Any], np.ndarray]],
    camera: dict[str, Any],
    renderer: dict[str, Any],
) -> tuple[np.ndarray, dict[str, int | float]]:
    if trace["body_names"] != [body["name"] for body in scene["bodies"]]:
        raise ValueError("scene and trace body ordering drifted")
    state = trace["frames"][0]
    body_positions = np.asarray(state["p"], dtype=np.float64).reshape((-1, 3))
    body_rotations = [
        quaternion_matrix_wxyz(value)
        for value in np.asarray(state["q"], dtype=np.float64).reshape((-1, 4))
    ]

    width = int(renderer["width_px"])
    height = int(renderer["height_px"])
    background_bgr = np.asarray(renderer["background_rgb"], dtype=np.uint8)[::-1]
    frame = np.empty((height, width, 3), dtype=np.uint8)
    frame[:] = background_bgr
    zbuffer = np.full((height, width), np.inf, dtype=np.float64)
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
        geom_rotation = body_rotations[body_id] @ quaternion_matrix_wxyz(
            geom["quaternion_wxyz"]
        )
        geom_center = body_positions[body_id] + body_rotations[body_id] @ np.asarray(
            geom["position"], dtype=np.float64
        )
        world = local @ geom_rotation.T + geom_center
        pixels, depths = _project_camera(world, camera, width, height)
        base_rgb = np.clip(np.asarray(geom["rgba"][:3], dtype=np.float64), 0.0, 1.0)
        for triangle, triangle_pixels, triangle_depths in zip(
            world, pixels, depths, strict=True
        ):
            normal = np.cross(triangle[1] - triangle[0], triangle[2] - triangle[0])
            normal_norm = float(np.linalg.norm(normal))
            lambert = (
                0.0
                if normal_norm <= 1e-12
                else abs(float((normal / normal_norm) @ light))
            )
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

    return frame, {
        "mesh_definition_count": mesh_definition_count,
        "mesh_source_triangle_count": mesh_source_triangles,
        "mesh_raster_triangle_count": mesh_raster_triangles,
        "total_raster_triangle_count": total_raster_triangles,
        "depth_buffer_update_count": depth_updates,
        "occluded_fragment_count": occluded_fragments,
        "frame_coverage_fraction": float(np.isfinite(zbuffer).mean()),
    }


def compare_once(
    contract_path: Path = DEFAULT_CONTRACT, output_directory: Path = DEFAULT_OUTPUT
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR78 one-run receipt already exists")
    contract = json.loads(contract_path.read_text())
    for name, source in contract["sources"].items():
        if name == "mesh_asset_root":
            continue
        if sha256_file(REPO_ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['path']}")

    or73 = json.loads(
        (REPO_ROOT / contract["sources"]["or73_closeout"]["path"]).read_text()
    )
    selected_camera = or73["selected_camera"]
    camera = {
        "name": "or73_shared_development_camera",
        "position": selected_camera["position"],
        "target": selected_camera["target"],
        "fov_degrees": selected_camera["fov_degrees"],
    }
    contract_camera = {
        "name": "or73_shared_development_camera",
        "position": contract["camera"]["position"],
        "target": contract["camera"]["target"],
        "fov_degrees": contract["camera"]["fov_degrees"],
    }
    if camera != contract_camera:
        raise ValueError("OR73 camera binding drifted")
    baseline = contract["baseline"]
    if baseline["mean_full_frame_linear_pixel_similarity"] != or73["result"][
        "selected_final_mean_full_frame_similarity"
    ] or baseline["mean_tolerant_edge_f1"] != or73["result"][
        "selected_final_mean_edge_f1"
    ]:
        raise ValueError("OR73 baseline metric binding drifted")

    or72 = json.loads(
        (REPO_ROOT / contract["sources"]["or72_contract"]["path"]).read_text()
    )
    episodes = or72["episodes"]
    expected_episode_count = int(contract["gates"]["expected_development_episode_count"])
    if len(episodes) != expected_episode_count or any(
        episode["split_role"] != "development" for episode in episodes
    ):
        raise ValueError("development episode boundary drifted")
    for episode in episodes:
        for binding in (episode["physical_video"], episode["state_trace"]):
            if sha256_file(REPO_ROOT / binding["path"]) != binding["sha256"]:
                raise ValueError(f"episode source hash mismatch: {binding['path']}")

    scene_binding = contract["sources"]["shared_scene_manifest"]
    scene = json.loads((REPO_ROOT / scene_binding["path"]).read_text())
    if scene["revision_sha256"] != scene_binding["revision_sha256"]:
        raise ValueError("scene revision mismatch")
    meshes, asset_receipts = _load_unique_asset_cache(
        scene, REPO_ROOT / contract["sources"]["mesh_asset_root"]["path"]
    )

    output_directory.mkdir(parents=True, exist_ok=True)
    renderer = contract["renderer"]
    edge = contract["metric"]["edge"]
    width = int(renderer["width_px"])
    height = int(renderer["height_px"])
    rows: list[dict[str, Any]] = []
    for episode in episodes:
        physical = _read_initial_physical_frame(
            REPO_ROOT / episode["physical_video"]["path"],
            width=width,
            height=height,
        )
        trace = json.loads((REPO_ROOT / episode["state_trace"]["path"]).read_text())
        candidate, render_metrics = _render_full_mesh_frame(
            scene, trace, meshes, camera, renderer
        )
        ok, encoded = cv2.imencode(".png", candidate, [cv2.IMWRITE_PNG_COMPRESSION, 9])
        if not ok:
            raise RuntimeError("failed to encode OR78 candidate image")
        image_path = output_directory / f"{episode['recording_id']}.png"
        image_path.write_bytes(encoded.tobytes())
        rows.append(
            {
                "recording_id": episode["recording_id"],
                "metrics": _metrics(physical, candidate, edge),
                "render_metrics": render_metrics,
                "candidate_image": {
                    "path": str(image_path.relative_to(REPO_ROOT)),
                    "sha256": sha256_file(image_path),
                },
            }
        )

    mean_similarity = float(
        np.mean([row["metrics"]["full_frame_linear_pixel_similarity"] for row in rows])
    )
    mean_edge = float(
        np.mean([row["metrics"]["tolerant_edge_f1"] for row in rows])
    )
    similarity_delta = mean_similarity - float(
        baseline["mean_full_frame_linear_pixel_similarity"]
    )
    edge_delta = mean_edge - float(baseline["mean_tolerant_edge_f1"])
    expected = contract["gates"]
    acceptance = contract["acceptance"]
    render_rows = [row["render_metrics"] for row in rows]
    gates = {
        "exact_four_development_episodes": len(rows) == expected_episode_count,
        "manifest_derived_unique_mesh_asset_count": len(asset_receipts)
        == expected["expected_manifest_derived_unique_mesh_asset_count"],
        "unique_mesh_asset_reads": len(asset_receipts)
        == expected["expected_unique_mesh_asset_reads"],
        "mesh_definition_count_every_frame": all(
            row["mesh_definition_count"]
            == expected["expected_mesh_definition_count_per_frame"]
            for row in render_rows
        ),
        "mesh_source_triangle_count_every_frame": all(
            row["mesh_source_triangle_count"]
            == expected["expected_mesh_source_triangle_count_per_frame"]
            for row in render_rows
        ),
        "mesh_raster_triangle_count_every_frame": all(
            row["mesh_raster_triangle_count"]
            == expected["expected_mesh_raster_triangle_count_per_frame"]
            for row in render_rows
        ),
        "depth_test_exercised_every_frame": all(
            row["depth_buffer_update_count"] > 0
            and row["occluded_fragment_count"] > 0
            for row in render_rows
        ),
        "mean_tolerant_edge_improved": edge_delta
        > float(acceptance["minimum_selected_minus_baseline_mean_tolerant_edge_f1"]),
        "mean_full_frame_similarity_not_regressed": similarity_delta
        >= float(
            acceptance["minimum_selected_minus_baseline_mean_full_frame_similarity"]
        ),
        "camera_byte_equal_to_or73": camera == contract_camera,
        "baseline_metrics_exactly_bound_to_or73": True,
        "validation_and_heldout_closed": True,
        "no_refits_or_replays": True,
    }
    passed = all(gates.values())
    receipt: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_static_development_full_mesh_comparison_receipt.v1",
        "experiment_id": contract["experiment_id"],
        "status": (
            "PASS_FULL_MESH_STATIC_DEVELOPMENT_ADVANCE"
            if passed
            else "TERMINAL_FULL_MESH_STATIC_DEVELOPMENT_COMPARISON_FAILED"
        ),
        "proof_class": contract["proof_class"],
        "contract": {
            "path": str(contract_path.relative_to(REPO_ROOT)),
            "sha256": sha256_file(contract_path),
        },
        "camera": camera,
        "renderer": renderer,
        "unique_mesh_assets": asset_receipts,
        "baseline": baseline,
        "episodes": rows,
        "summary": {
            "selected_mean_full_frame_similarity": mean_similarity,
            "selected_mean_tolerant_edge_f1": mean_edge,
            "selected_minus_baseline_mean_full_frame_similarity": similarity_delta,
            "selected_minus_baseline_mean_tolerant_edge_f1": edge_delta,
        },
        "gates": gates,
        "execution": {
            "development_episode_reads": 4,
            "development_physical_video_decodes": 4,
            "development_physical_frames": 4,
            "development_state_trace_reads": 4,
            "candidate_images": 4,
            "unique_mesh_asset_reads": len(asset_receipts),
            "validation_reads": 0,
            "evaluator_heldout_reads": 0,
            "candidate_videos": 0,
            "simulator_replays": 0,
            "camera_fits": 0,
            "appearance_fits": 0,
            "time_fits": 0,
            "state_or_physics_fits": 0,
            "hardware_actions": 0,
            "paid_compute": False,
            "prohibited_candidate_inputs_read": [],
        },
        "claim_limits": contract["claim_limits"],
        "reviewer_decision": (
            "ADVANCE_TO_FROZEN_CAMERA_FULL_MESH_DEVELOPMENT_TIMELINE"
            if passed
            else "DO_NOT_ADVANCE_FULL_MESH_RENDERER_BEFORE_TRANSFORM_AUDIT"
        ),
        "next_transition": (
            "freeze_or79_full_mesh_full_development_timeline"
            if passed
            else "freeze_or79_mesh_compiler_transform_convention_audit_without_physical_pixel_fit"
        ),
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(compare_once(), sort_keys=True))
