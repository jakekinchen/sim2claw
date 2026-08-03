"""One-degree sensor-roll successor to the rejected OR81 camera family."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from scipy.optimize import differential_evolution

from .learning_factory_artifacts import atomic_write_json, canonical_digest
from .observable_registration_development_board_grid_camera_geometry_fit import (
    _symmetry_permutations,
    _world_board_corners,
)
from .observable_registration_development_initial_shared_3d_camera_fit import (
    _metrics,
    _read_initial_physical_frame,
    camera_from_vector,
)
from .observable_registration_host_native_analytic_3d_renderer_capability import (
    REPO_ROOT,
    camera_basis,
    quaternion_matrix_wxyz,
    sha256_file,
)
from .observable_registration_host_native_mesh_zbuffer_renderer_capability import (
    _local_triangles_for_geom,
)
from .observable_registration_native_rasterizer_byte_equivalence import (
    _compile_native,
    _native_rasterize,
)
from .observable_registration_static_development_full_mesh_comparison import (
    _load_unique_asset_cache,
)


cv2.ocl.setUseOpenCL(False)

DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_board_grid_camera_sensor_roll_successor_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_board_grid_camera_sensor_roll_successor_v1"


def camera_from_roll_vector(vector: np.ndarray) -> dict[str, Any]:
    camera = camera_from_vector(np.asarray(vector[:7], dtype=np.float64))
    camera["roll_degrees"] = float(vector[7])
    camera["name"] = "or82_shared_board_camera_with_sensor_roll"
    return camera


def _rolled_basis(
    camera: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    position, right, up, forward = camera_basis(camera)
    angle = np.deg2rad(float(camera["roll_degrees"]))
    rolled_right = np.cos(angle) * right + np.sin(angle) * up
    rolled_up = -np.sin(angle) * right + np.cos(angle) * up
    return position, rolled_right, rolled_up, forward


def _project_points_roll(
    points: np.ndarray, camera: dict[str, Any], width: int, height: int
) -> tuple[np.ndarray, np.ndarray]:
    position, right, up, forward = _rolled_basis(camera)
    delta = points - position
    depth = delta @ forward
    focal = 0.5 * height / np.tan(
        np.deg2rad(float(camera["fov_degrees"])) * 0.5
    )
    pixels = np.empty((len(points), 2), dtype=np.float64)
    pixels[:, 0] = width * 0.5 + focal * (delta @ right) / depth
    pixels[:, 1] = height * 0.5 - focal * (delta @ up) / depth
    return pixels, depth


def _project_triangles_roll(
    triangles: np.ndarray, camera: dict[str, Any], width: int, height: int
) -> tuple[np.ndarray, np.ndarray]:
    position, right, up, forward = _rolled_basis(camera)
    delta = triangles - position
    depth = delta @ forward
    focal = 0.5 * height / np.tan(
        np.deg2rad(float(camera["fov_degrees"])) * 0.5
    )
    pixels = np.empty(triangles.shape[:2] + (2,), dtype=np.float64)
    pixels[..., 0] = width * 0.5 + focal * (delta @ right) / depth
    pixels[..., 1] = height * 0.5 - focal * (delta @ up) / depth
    return pixels, depth


def _prepare_triangle_stream_roll(
    scene: dict[str, Any],
    trace: dict[str, Any],
    meshes: dict[int, tuple[dict[str, Any], np.ndarray]],
    camera: dict[str, Any],
    renderer: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    if trace["body_names"] != [body["name"] for body in scene["bodies"]]:
        raise ValueError("scene and trace body ordering drifted")
    state = trace["frames"][0]
    body_positions = np.asarray(state["p"], dtype=np.float64).reshape((-1, 3))
    body_rotations = [
        quaternion_matrix_wxyz(value)
        for value in np.asarray(state["q"], dtype=np.float64).reshape((-1, 4))
    ]
    light = np.asarray(renderer["lighting"]["world_direction"], dtype=np.float64)
    light /= np.linalg.norm(light)
    ambient = float(renderer["lighting"]["ambient"])
    diffuse = float(renderer["lighting"]["diffuse"])
    projected: list[np.ndarray] = []
    depths: list[np.ndarray] = []
    colors: list[np.ndarray] = []
    for geom in scene["geoms"]:
        local, _, _ = _local_triangles_for_geom(geom, meshes=meshes, config=renderer)
        body_id = int(geom["body_id"])
        geom_rotation = body_rotations[body_id] @ quaternion_matrix_wxyz(
            geom["quaternion_wxyz"]
        )
        geom_center = body_positions[body_id] + body_rotations[body_id] @ np.asarray(
            geom["position"], dtype=np.float64
        )
        world = local @ geom_rotation.T + geom_center
        geom_pixels, geom_depths = _project_triangles_roll(
            world, camera, int(renderer["width_px"]), int(renderer["height_px"])
        )
        normals = np.cross(world[:, 1] - world[:, 0], world[:, 2] - world[:, 0])
        normal_norms = np.linalg.norm(normals, axis=1)
        unit_normals = np.divide(
            normals,
            normal_norms[:, None],
            out=np.zeros_like(normals),
            where=normal_norms[:, None] > 1e-12,
        )
        intensity = np.clip(
            ambient + diffuse * np.abs(unit_normals @ light), 0.0, 1.0
        )
        base_rgb = np.clip(np.asarray(geom["rgba"][:3], dtype=np.float64), 0.0, 1.0)
        geom_colors = np.rint(
            base_rgb[::-1][None, :] * intensity[:, None] * 255.0
        ).astype(np.uint8)
        projected.append(geom_pixels)
        depths.append(geom_depths)
        colors.append(geom_colors)
    all_pixels = np.ascontiguousarray(np.concatenate(projected, axis=0), dtype=np.float64)
    all_depths = np.ascontiguousarray(np.concatenate(depths, axis=0), dtype=np.float64)
    all_colors = np.ascontiguousarray(np.concatenate(colors, axis=0), dtype=np.uint8)
    return all_pixels, all_depths, all_colors, len(all_pixels)


def fit_once(
    contract_path: Path = DEFAULT_CONTRACT,
    output_directory: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR82 one-run receipt already exists")
    contract = json.loads(contract_path.read_text())
    for name, source in contract["sources"].items():
        if name == "mesh_asset_root":
            continue
        if sha256_file(REPO_ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['path']}")
    or81 = json.loads(
        (REPO_ROOT / contract["sources"]["or81_contract"]["path"]).read_text()
    )
    for key in contract["unchanged_or81_sections"]:
        if key not in or81:
            raise ValueError(f"missing frozen OR81 section: {key}")
    or72 = json.loads(
        (REPO_ROOT / contract["sources"]["or72_contract"]["path"]).read_text()
    )
    episodes = or72["episodes"]
    annotations_by_id = {
        row["recording_id"]: np.asarray(row["points_px"], dtype=np.float64)
        for row in or81["annotations"]["episodes"]
    }
    if len(episodes) != 4 or set(annotations_by_id) != {
        episode["recording_id"] for episode in episodes
    }:
        raise ValueError("OR82 development annotation boundary drifted")
    for episode in episodes:
        for binding in (episode["physical_video"], episode["state_trace"]):
            if sha256_file(REPO_ROOT / binding["path"]) != binding["sha256"]:
                raise ValueError(f"episode source hash mismatch: {binding['path']}")
    scene_binding = contract["sources"]["shared_scene_manifest"]
    scene = json.loads((REPO_ROOT / scene_binding["path"]).read_text())
    if scene["revision_sha256"] != scene_binding["revision_sha256"]:
        raise ValueError("scene revision mismatch")
    correspondence = or81["scene_correspondence"]
    traces = [
        json.loads((REPO_ROOT / episode["state_trace"]["path"]).read_text())
        for episode in episodes
    ]
    world_corners = [
        _world_board_corners(
            trace,
            int(correspondence["body_id"]),
            float(correspondence["local_playing_surface_half_side_m"]),
            float(correspondence["local_playing_surface_z_m"]),
        )
        for trace in traces
    ]
    observations = [annotations_by_id[episode["recording_id"]] for episode in episodes]
    width = int(or81["renderer"]["width_px"])
    height = int(or81["renderer"]["height_px"])
    search = contract["search"]
    bounds = [tuple(float(value) for value in bound) for bound in contract["camera_family"]["bounds"]]
    evaluation_count = 0
    hypothesis_results: list[dict[str, Any]] = []
    for hypothesis_index, permutation in enumerate(_symmetry_permutations()):
        def objective(vector: np.ndarray) -> float:
            nonlocal evaluation_count
            evaluation_count += 1
            camera = camera_from_roll_vector(vector)
            residuals: list[np.ndarray] = []
            for world, observed in zip(world_corners, observations, strict=True):
                projected, depth = _project_points_roll(
                    world[np.asarray(permutation, dtype=np.int64)], camera, width, height
                )
                if np.any(depth <= 1e-4) or not np.all(np.isfinite(projected)):
                    return 1e6
                residuals.append(projected - observed)
            combined = np.concatenate(residuals, axis=0)
            return float(np.sqrt(np.mean(np.square(combined))))

        result = differential_evolution(
            objective,
            bounds=bounds,
            rng=np.random.default_rng(int(search["seed"]) + hypothesis_index),
            popsize=int(search["population_size_multiplier"]),
            maxiter=int(search["maximum_iterations"]),
            tol=float(search["tolerance"]),
            atol=float(search["absolute_tolerance"]),
            polish=bool(search["polish"]),
            workers=int(search["workers"]),
            updating="immediate",
        )
        hypothesis_results.append(
            {
                "hypothesis_index": hypothesis_index,
                "permutation": permutation,
                "reprojection_coordinate_rms_px": float(result.fun),
                "vector": np.asarray(result.x, dtype=np.float64).tolist(),
                "optimizer_converged": bool(result.success),
                "optimizer_message": str(result.message),
            }
        )
    if evaluation_count > int(search["maximum_candidate_evaluations_across_all_hypotheses"]):
        raise RuntimeError("OR82 camera search exceeded frozen evaluation budget")
    selected = min(
        hypothesis_results, key=lambda row: row["reprojection_coordinate_rms_px"]
    )
    selected_vector = np.asarray(selected["vector"], dtype=np.float64)
    selected_camera = camera_from_roll_vector(selected_vector)
    selected_permutation = np.asarray(selected["permutation"], dtype=np.int64)
    reprojection_rows: list[dict[str, Any]] = []
    all_distances: list[float] = []
    for episode, world, observed in zip(
        episodes, world_corners, observations, strict=True
    ):
        projected, depth = _project_points_roll(
            world[selected_permutation], selected_camera, width, height
        )
        distances = np.linalg.norm(projected - observed, axis=1)
        all_distances.extend(distances.tolist())
        reprojection_rows.append(
            {
                "recording_id": episode["recording_id"],
                "observed_points_px": observed.tolist(),
                "projected_points_px": projected.tolist(),
                "corner_errors_px": distances.tolist(),
                "rms_px": float(np.sqrt(np.mean(np.square(distances)))),
                "maximum_px": float(np.max(distances)),
                "minimum_depth_m": float(np.min(depth)),
            }
        )
    meshes, asset_receipts = _load_unique_asset_cache(
        scene, REPO_ROOT / contract["sources"]["mesh_asset_root"]["path"]
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    library_path, compile_command, compiler_stderr = _compile_native(
        {
            "sources": {"native_source": contract["sources"]["or79_native_source"]},
            "compiler": {"executable": "clang"},
        },
        output_directory,
    )
    metric_rows: list[dict[str, Any]] = []
    for episode, trace in zip(episodes, traces, strict=True):
        physical = _read_initial_physical_frame(
            REPO_ROOT / episode["physical_video"]["path"], width=width, height=height
        )
        pixels, depths, colors, triangle_count = _prepare_triangle_stream_roll(
            scene, trace, meshes, selected_camera, or81["renderer"]
        )
        candidate, depth_updates, occluded, _ = _native_rasterize(
            library_path, pixels, depths, colors, or81["renderer"]
        )
        ok, encoded = cv2.imencode(".png", candidate, [cv2.IMWRITE_PNG_COMPRESSION, 9])
        if not ok:
            raise RuntimeError("failed to encode OR82 candidate image")
        image_path = output_directory / f"{episode['recording_id']}.png"
        image_path.write_bytes(encoded.tobytes())
        metric_rows.append(
            {
                "recording_id": episode["recording_id"],
                "metrics": _metrics(physical, candidate, or81["metric"]["edge"]),
                "total_raster_triangle_count": triangle_count,
                "depth_buffer_update_count": depth_updates,
                "occluded_fragment_count": occluded,
                "candidate_image": {
                    "path": str(image_path.relative_to(REPO_ROOT)),
                    "sha256": sha256_file(image_path),
                },
            }
        )
    mean_similarity = float(
        np.mean([row["metrics"]["full_frame_linear_pixel_similarity"] for row in metric_rows])
    )
    mean_edge = float(
        np.mean([row["metrics"]["tolerant_edge_f1"] for row in metric_rows])
    )
    reprojection_rms = float(np.sqrt(np.mean(np.square(all_distances))))
    reprojection_max = float(np.max(all_distances))
    acceptance = or81["acceptance"]
    gates = {
        "board_reprojection_rms_px": reprojection_rms <= acceptance["maximum_board_reprojection_rms_px"],
        "board_reprojection_max_px": reprojection_max <= acceptance["maximum_board_reprojection_max_px"],
        "static_mean_tolerant_edge_f1": mean_edge >= acceptance["minimum_static_mean_tolerant_edge_f1"],
        "static_mean_full_frame_linear_pixel_similarity": mean_similarity >= acceptance["minimum_static_mean_full_frame_linear_pixel_similarity"],
        "static_each_episode_tolerant_edge_f1": all(
            row["metrics"]["tolerant_edge_f1"] >= acceptance["minimum_static_each_episode_tolerant_edge_f1"]
            for row in metric_rows
        ),
        "one_shared_eight_parameter_camera_vector": len(selected_vector) == 8,
        "only_sensor_roll_added": contract["camera_family"]["added_parameter_count"] == 1,
        "exact_eight_symmetry_hypotheses": len(hypothesis_results) == 8,
        "validation_and_heldout_closed": True,
        "other_fit_classes_zero": True,
    }
    passed = all(gates.values())
    receipt: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_board_grid_camera_sensor_roll_successor_receipt.v1",
        "experiment_id": contract["experiment_id"],
        "status": (
            "PASS_BOARD_GRID_CAMERA_SENSOR_ROLL_STATIC_ADVANCE"
            if passed
            else "TERMINAL_BOARD_GRID_CAMERA_SENSOR_ROLL_GATE_FAILED"
        ),
        "proof_class": contract["proof_class"],
        "contract": {
            "path": str(contract_path.relative_to(REPO_ROOT)),
            "sha256": sha256_file(contract_path),
        },
        "selected": {
            **selected,
            "camera": selected_camera,
            "reprojection_rms_px": reprojection_rms,
            "reprojection_max_px": reprojection_max,
            "reprojection_by_episode": reprojection_rows,
        },
        "hypotheses": hypothesis_results,
        "static_metrics_by_episode": metric_rows,
        "summary": {
            "candidate_evaluations": evaluation_count,
            "mean_full_frame_linear_pixel_similarity": mean_similarity,
            "mean_tolerant_edge_f1": mean_edge,
            "or81_mean_full_frame_linear_pixel_similarity": 0.7330585196614265,
            "or81_mean_tolerant_edge_f1": 0.3868349737969936,
        },
        "compiled_library": {
            "path": str(library_path.relative_to(REPO_ROOT)),
            "sha256": sha256_file(library_path),
            "command": compile_command,
            "compiler_stderr": compiler_stderr,
        },
        "gates": gates,
        "execution": {
            "development_episode_reads": 4,
            "development_physical_video_decodes": 4,
            "development_physical_frames": 4,
            "development_state_trace_reads": 4,
            "candidate_images": 4,
            "unique_mesh_asset_reads": len(asset_receipts),
            "camera_fits": 1,
            "appearance_fits": 0,
            "time_fits": 0,
            "state_or_physics_fits": 0,
            "principal_point_fits": 0,
            "distortion_fits": 0,
            "validation_reads": 0,
            "evaluator_heldout_reads": 0,
            "simulator_replays": 0,
            "hardware_actions": 0,
            "paid_compute": False,
        },
        "claim_limits": contract["claim_limits"],
        "reviewer_decision": (
            "FREEZE_SENSOR_ROLL_CAMERA_AND_RUN_FULL_DEVELOPMENT_TIMELINE"
            if passed
            else "DO_NOT_ADVANCE_SENSOR_ROLL_CAMERA"
        ),
        "next_transition": (
            "freeze_or83_sensor_roll_camera_full_mesh_development_timeline"
            if passed
            else "audit_residual_camera_model_without_split_expansion"
        ),
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(fit_once(), sort_keys=True))
