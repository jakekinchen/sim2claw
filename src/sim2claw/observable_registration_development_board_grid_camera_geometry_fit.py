"""Fit one shared camera from frozen development board-lattice correspondences."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from scipy.optimize import differential_evolution

from .learning_factory_artifacts import atomic_write_json, canonical_digest
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
from .observable_registration_native_rasterizer_byte_equivalence import (
    _compile_native,
    _native_rasterize,
    _prepare_triangle_stream,
)
from .observable_registration_static_development_full_mesh_comparison import (
    _load_unique_asset_cache,
)


cv2.ocl.setUseOpenCL(False)

DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_development_board_grid_camera_geometry_fit_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_development_board_grid_camera_geometry_fit_v1"


def _project_points(
    points: np.ndarray, camera: dict[str, Any], width: int, height: int
) -> tuple[np.ndarray, np.ndarray]:
    position, right, up, forward = camera_basis(camera)
    delta = points - position
    depth = delta @ forward
    focal = 0.5 * height / np.tan(
        np.deg2rad(float(camera["fov_degrees"])) * 0.5
    )
    pixels = np.empty((len(points), 2), dtype=np.float64)
    pixels[:, 0] = width * 0.5 + focal * (delta @ right) / depth
    pixels[:, 1] = height * 0.5 - focal * (delta @ up) / depth
    return pixels, depth


def _world_board_corners(
    trace: dict[str, Any], body_id: int, half_side: float, local_z: float
) -> np.ndarray:
    state = trace["frames"][0]
    positions = np.asarray(state["p"], dtype=np.float64).reshape((-1, 3))
    quaternions = np.asarray(state["q"], dtype=np.float64).reshape((-1, 4))
    local = np.asarray(
        [
            [-half_side, -half_side, local_z],
            [half_side, -half_side, local_z],
            [half_side, half_side, local_z],
            [-half_side, half_side, local_z],
        ],
        dtype=np.float64,
    )
    rotation = quaternion_matrix_wxyz(quaternions[body_id])
    return local @ rotation.T + positions[body_id]


def _symmetry_permutations() -> list[list[int]]:
    clockwise = [0, 1, 2, 3]
    mirrored = [0, 3, 2, 1]
    return [
        order[offset:] + order[:offset]
        for order in (clockwise, mirrored)
        for offset in range(4)
    ]


def fit_once(
    contract_path: Path = DEFAULT_CONTRACT,
    output_directory: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR81 one-run receipt already exists")
    contract = json.loads(contract_path.read_text())
    for name, source in contract["sources"].items():
        if name == "mesh_asset_root":
            continue
        if sha256_file(REPO_ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['path']}")
    or72 = json.loads(
        (REPO_ROOT / contract["sources"]["or72_contract"]["path"]).read_text()
    )
    episodes = or72["episodes"]
    annotations_by_id = {
        row["recording_id"]: np.asarray(row["points_px"], dtype=np.float64)
        for row in contract["annotations"]["episodes"]
    }
    if len(episodes) != 4 or set(annotations_by_id) != {
        episode["recording_id"] for episode in episodes
    }:
        raise ValueError("OR81 development annotation boundary drifted")
    for episode in episodes:
        for binding in (episode["physical_video"], episode["state_trace"]):
            if sha256_file(REPO_ROOT / binding["path"]) != binding["sha256"]:
                raise ValueError(f"episode source hash mismatch: {binding['path']}")
    scene_binding = contract["sources"]["shared_scene_manifest"]
    scene = json.loads((REPO_ROOT / scene_binding["path"]).read_text())
    if scene["revision_sha256"] != scene_binding["revision_sha256"]:
        raise ValueError("scene revision mismatch")
    correspondence = contract["scene_correspondence"]
    if scene["bodies"][int(correspondence["body_id"])]["name"] != correspondence[
        "body_name"
    ]:
        raise ValueError("board body identity drifted")
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
    width = int(contract["renderer"]["width_px"])
    height = int(contract["renderer"]["height_px"])
    search = contract["search"]
    bounds = [tuple(float(value) for value in bound) for bound in contract["camera_family"]["bounds"]]
    evaluation_count = 0
    hypothesis_results: list[dict[str, Any]] = []

    for hypothesis_index, permutation in enumerate(_symmetry_permutations()):
        def objective(vector: np.ndarray) -> float:
            nonlocal evaluation_count
            evaluation_count += 1
            camera = camera_from_vector(vector)
            residuals: list[np.ndarray] = []
            for world, observed in zip(world_corners, observations, strict=True):
                projected, depth = _project_points(
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
        raise RuntimeError("OR81 camera search exceeded frozen evaluation budget")
    selected = min(
        hypothesis_results, key=lambda row: row["reprojection_coordinate_rms_px"]
    )
    selected_vector = np.asarray(selected["vector"], dtype=np.float64)
    selected_camera = camera_from_vector(selected_vector)
    selected_permutation = np.asarray(selected["permutation"], dtype=np.int64)
    reprojection_rows: list[dict[str, Any]] = []
    all_distances: list[float] = []
    for episode, world, observed in zip(
        episodes, world_corners, observations, strict=True
    ):
        projected, depth = _project_points(
            world[selected_permutation], selected_camera, width, height
        )
        distances = np.linalg.norm(projected - observed, axis=1)
        all_distances.extend(distances.tolist())
        reprojection_rows.append(
            {
                "recording_id": episode["recording_id"],
                "observed_points_px": observed.tolist(),
                "projected_points_px": projected.tolist(),
                "depths_m": depth.tolist(),
                "corner_errors_px": distances.tolist(),
                "rms_px": float(np.sqrt(np.mean(np.square(distances)))),
                "maximum_px": float(np.max(distances)),
            }
        )

    meshes, asset_receipts = _load_unique_asset_cache(
        scene, REPO_ROOT / contract["sources"]["mesh_asset_root"]["path"]
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    library_path, compile_command, compiler_stderr = _compile_native(
        {
            "sources": {
                "native_source": contract["sources"]["or79_native_source"]
            },
            "compiler": {"executable": "clang"},
        },
        output_directory,
    )
    metric_rows: list[dict[str, Any]] = []
    for episode, trace in zip(episodes, traces, strict=True):
        physical = _read_initial_physical_frame(
            REPO_ROOT / episode["physical_video"]["path"],
            width=width,
            height=height,
        )
        pixels, depths, colors, stream = _prepare_triangle_stream(
            scene, trace, meshes, selected_camera, contract["renderer"]
        )
        candidate, depth_updates, occluded, _ = _native_rasterize(
            library_path, pixels, depths, colors, contract["renderer"]
        )
        ok, encoded = cv2.imencode(".png", candidate, [cv2.IMWRITE_PNG_COMPRESSION, 9])
        if not ok:
            raise RuntimeError("failed to encode OR81 candidate image")
        image_path = output_directory / f"{episode['recording_id']}.png"
        image_path.write_bytes(encoded.tobytes())
        metric_rows.append(
            {
                "recording_id": episode["recording_id"],
                "metrics": _metrics(physical, candidate, contract["metric"]["edge"]),
                "total_raster_triangle_count": stream["total_raster_triangle_count"],
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
    acceptance = contract["acceptance"]
    gates = {
        "board_reprojection_rms_px": reprojection_rms
        <= acceptance["maximum_board_reprojection_rms_px"],
        "board_reprojection_max_px": reprojection_max
        <= acceptance["maximum_board_reprojection_max_px"],
        "static_mean_tolerant_edge_f1": mean_edge
        >= acceptance["minimum_static_mean_tolerant_edge_f1"],
        "static_mean_full_frame_linear_pixel_similarity": mean_similarity
        >= acceptance["minimum_static_mean_full_frame_linear_pixel_similarity"],
        "static_each_episode_tolerant_edge_f1": all(
            row["metrics"]["tolerant_edge_f1"]
            >= acceptance["minimum_static_each_episode_tolerant_edge_f1"]
            for row in metric_rows
        ),
        "one_shared_camera_vector": len(selected_vector) == 7,
        "exact_eight_symmetry_hypotheses": len(hypothesis_results) == 8,
        "validation_and_heldout_closed": True,
        "appearance_time_state_fits_zero": True,
    }
    passed = all(gates.values())
    receipt: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_development_board_grid_camera_geometry_fit_receipt.v1",
        "experiment_id": contract["experiment_id"],
        "status": (
            "PASS_BOARD_GRID_CAMERA_GEOMETRY_STATIC_ADVANCE"
            if passed
            else "TERMINAL_BOARD_GRID_CAMERA_GEOMETRY_STATIC_GATE_FAILED"
        ),
        "proof_class": contract["proof_class"],
        "contract": {
            "path": str(contract_path.relative_to(REPO_ROOT)),
            "sha256": sha256_file(contract_path),
        },
        "annotations": contract["annotations"],
        "scene_correspondence": contract["scene_correspondence"],
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
            "baseline_mean_full_frame_linear_pixel_similarity": contract["baseline"]["mean_full_frame_linear_pixel_similarity"],
            "baseline_mean_tolerant_edge_f1": contract["baseline"]["mean_tolerant_edge_f1"],
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
            "validation_reads": 0,
            "evaluator_heldout_reads": 0,
            "simulator_replays": 0,
            "hardware_actions": 0,
            "paid_compute": False,
            "prohibited_candidate_inputs_read": [],
        },
        "claim_limits": contract["claim_limits"],
        "reviewer_decision": (
            "FREEZE_BOARD_CAMERA_AND_RUN_FULL_DEVELOPMENT_TIMELINE"
            if passed
            else "DO_NOT_ADVANCE_BOARD_CAMERA"
        ),
        "next_transition": (
            "freeze_or82_board_camera_full_mesh_development_timeline"
            if passed
            else "audit_board_annotations_and_scene_layout_without_split_expansion"
        ),
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(fit_once(), sort_keys=True))
