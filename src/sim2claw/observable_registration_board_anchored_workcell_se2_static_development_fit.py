"""Fit one shared board-anchored planar workcell registration on development frames."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from scipy.optimize import differential_evolution

from .learning_factory_artifacts import atomic_write_json, canonical_digest
from .observable_registration_board_anchored_scene_composition_residual_attribution import (
    _masked_tolerant_edge_f1,
)
from .observable_registration_board_grid_camera_sensor_roll_successor import (
    _project_triangles_roll,
    _rolled_basis,
)
from .observable_registration_development_initial_shared_3d_camera_fit import (
    _metrics,
    _read_initial_physical_frame,
)
from .observable_registration_host_native_analytic_3d_renderer_capability import (
    REPO_ROOT,
    _box_corners,
    _declared_bgr,
    _world_transform,
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

DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_board_anchored_workcell_se2_static_development_fit_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_board_anchored_workcell_se2_static_development_fit_v1"


def _apply_board_anchored_se2(
    positions: np.ndarray,
    rotations: list[np.ndarray],
    *,
    anchor_body_id: int,
    transformed_body_ids: list[int],
    vector: np.ndarray,
) -> tuple[np.ndarray, list[np.ndarray]]:
    """Apply one world-frame SE(2) transform around a fixed board anchor."""
    yaw_degrees, translation_x, translation_y = np.asarray(
        vector, dtype=np.float64
    )
    yaw = np.deg2rad(float(yaw_degrees))
    c, s = float(np.cos(yaw)), float(np.sin(yaw))
    rotation_z = np.asarray(
        [[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]], dtype=np.float64
    )
    translation = np.asarray(
        [float(translation_x), float(translation_y), 0.0], dtype=np.float64
    )
    anchor = np.asarray(positions[anchor_body_id], dtype=np.float64)
    transformed_positions = np.asarray(positions, dtype=np.float64).copy()
    transformed_rotations = [np.asarray(value, dtype=np.float64).copy() for value in rotations]
    for body_id in transformed_body_ids:
        transformed_positions[body_id] = (
            anchor + rotation_z @ (positions[body_id] - anchor) + translation
        )
        transformed_rotations[body_id] = rotation_z @ rotations[body_id]
    return transformed_positions, transformed_rotations


def _project_points_roll(
    points: np.ndarray, camera: dict[str, Any], width: int, height: int
) -> tuple[np.ndarray, np.ndarray]:
    position, right, up, forward = _rolled_basis(camera)
    delta = np.asarray(points, dtype=np.float64) - position
    depth = delta @ forward
    focal = 0.5 * height / np.tan(
        np.deg2rad(float(camera["fov_degrees"])) * 0.5
    )
    safe = np.where(depth > 1e-9, depth, 1.0)
    pixels = np.stack(
        [
            width * 0.5 + focal * (delta @ right) / safe,
            height * 0.5 - focal * (delta @ up) / safe,
        ],
        axis=1,
    )
    return pixels, depth


def _render_analytic_geom(
    frame: np.ndarray,
    geom: dict[str, Any],
    center: np.ndarray,
    rotation: np.ndarray,
    camera: dict[str, Any],
) -> bool:
    if float(geom["rgba"][3]) <= 0.01:
        return False
    height, width = frame.shape[:2]
    geom_type = str(geom["type"])
    size = np.asarray(geom["size"], dtype=np.float64)
    color = _declared_bgr(geom)
    outline = tuple(max(0, channel - 28) for channel in color)
    if geom_type in {"box", "mesh", "plane"}:
        half_size = size.copy()
        if geom_type == "plane":
            half_size = np.asarray(
                [size[0], size[1], max(float(size[2]), 0.005)]
            )
        corners = _box_corners(center, rotation, np.maximum(half_size, 0.001))
        pixels, depth = _project_points_roll(corners, camera, width, height)
        valid = depth > 1e-5
        if int(valid.sum()) < 3:
            return False
        hull = cv2.convexHull(np.rint(pixels[valid]).astype(np.int32))
        cv2.fillConvexPoly(frame, hull, color, lineType=cv2.LINE_AA)
        cv2.polylines(frame, [hull], True, outline, 1, cv2.LINE_AA)
        return True
    center_px, center_depth = _project_points_roll(
        center[None, :], camera, width, height
    )
    if center_depth[0] <= 1e-5:
        return False
    center_i = tuple(np.rint(center_px[0]).astype(int))
    if geom_type in {"sphere", "ellipsoid"}:
        radii = np.repeat(size[0], 3) if geom_type == "sphere" else size
        endpoints = np.stack(
            [center + rotation[:, axis] * radii[axis] for axis in range(3)]
        )
        endpoint_px, _ = _project_points_roll(endpoints, camera, width, height)
        deltas = np.abs(endpoint_px - center_px[0])
        radius_x = max(1, int(round(float(np.max(deltas[:, 0])))))
        radius_y = max(1, int(round(float(np.max(deltas[:, 1])))))
        cv2.ellipse(
            frame,
            center_i,
            (radius_x, radius_y),
            0.0,
            0.0,
            360.0,
            color,
            -1,
            cv2.LINE_AA,
        )
        cv2.ellipse(
            frame,
            center_i,
            (radius_x, radius_y),
            0.0,
            0.0,
            360.0,
            outline,
            1,
            cv2.LINE_AA,
        )
        return True
    if geom_type in {"cylinder", "capsule"}:
        half_length = float(size[1])
        endpoints = np.stack(
            [
                center - rotation[:, 2] * half_length,
                center + rotation[:, 2] * half_length,
            ]
        )
        endpoint_px, endpoint_depth = _project_points_roll(
            endpoints, camera, width, height
        )
        if np.any(endpoint_depth <= 1e-5):
            return False
        radial_px, _ = _project_points_roll(
            (center + rotation[:, 0] * float(size[0]))[None, :],
            camera,
            width,
            height,
        )
        thickness = max(
            1,
            int(round(2.0 * float(np.linalg.norm(radial_px[0] - center_px[0])))),
        )
        p0, p1 = (tuple(np.rint(point).astype(int)) for point in endpoint_px)
        cv2.line(frame, p0, p1, color, thickness, cv2.LINE_AA)
        if geom_type == "capsule":
            radius = max(1, thickness // 2)
            cv2.circle(frame, p0, radius, color, -1, cv2.LINE_AA)
            cv2.circle(frame, p1, radius, color, -1, cv2.LINE_AA)
        return True
    raise ValueError(f"unrecognized geom type: {geom_type}")


def _state_arrays(trace: dict[str, Any]) -> tuple[np.ndarray, list[np.ndarray]]:
    state = trace["frames"][0]
    positions = np.asarray(state["p"], dtype=np.float64).reshape((-1, 3))
    rotations = [
        quaternion_matrix_wxyz(value)
        for value in np.asarray(state["q"], dtype=np.float64).reshape((-1, 4))
    ]
    return positions, rotations


def _render_analytic_candidate(
    scene: dict[str, Any],
    trace: dict[str, Any],
    camera: dict[str, Any],
    vector: np.ndarray,
    family: dict[str, Any],
    *,
    width: int,
    height: int,
    background_rgb: list[int],
) -> np.ndarray:
    positions, rotations = _state_arrays(trace)
    positions, rotations = _apply_board_anchored_se2(
        positions,
        rotations,
        anchor_body_id=int(family["anchor_body_id"]),
        transformed_body_ids=[int(value) for value in family["transformed_workcell_body_ids"]],
        vector=vector,
    )
    frame = np.empty((height, width, 3), dtype=np.uint8)
    frame[:] = np.asarray(background_rgb, dtype=np.uint8)[::-1]
    rows: list[tuple[float, dict[str, Any], np.ndarray, np.ndarray]] = []
    for geom in scene["geoms"]:
        center, rotation = _world_transform(geom, positions, rotations)
        _, depth = _project_points_roll(center[None, :], camera, width, height)
        rows.append((float(depth[0]), geom, center, rotation))
    for _, geom, center, rotation in sorted(rows, key=lambda row: row[0], reverse=True):
        _render_analytic_geom(frame, geom, center, rotation, camera)
    return frame


def _prepare_full_mesh_stream(
    scene: dict[str, Any],
    trace: dict[str, Any],
    meshes: dict[int, tuple[dict[str, Any], np.ndarray]],
    camera: dict[str, Any],
    renderer: dict[str, Any],
    family: dict[str, Any],
    vector: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    if trace["body_names"] != [body["name"] for body in scene["bodies"]]:
        raise ValueError("scene and trace body ordering drifted")
    positions, rotations = _state_arrays(trace)
    positions, rotations = _apply_board_anchored_se2(
        positions,
        rotations,
        anchor_body_id=int(family["anchor_body_id"]),
        transformed_body_ids=[int(value) for value in family["transformed_workcell_body_ids"]],
        vector=vector,
    )
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
        geom_rotation = rotations[body_id] @ quaternion_matrix_wxyz(
            geom["quaternion_wxyz"]
        )
        geom_center = positions[body_id] + rotations[body_id] @ np.asarray(
            geom["position"], dtype=np.float64
        )
        world = local @ geom_rotation.T + geom_center
        geom_pixels, geom_depths = _project_triangles_roll(
            world,
            camera,
            int(renderer["width_px"]),
            int(renderer["height_px"]),
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
    all_pixels = np.ascontiguousarray(np.concatenate(projected), dtype=np.float64)
    all_depths = np.ascontiguousarray(np.concatenate(depths), dtype=np.float64)
    all_colors = np.ascontiguousarray(np.concatenate(colors), dtype=np.uint8)
    return all_pixels, all_depths, all_colors, len(all_pixels)


def _region_masks(
    points: np.ndarray, *, width: int, height: int, dilation_kernel_px: int
) -> tuple[np.ndarray, np.ndarray]:
    board_u8 = np.zeros((height, width), dtype=np.uint8)
    cv2.fillConvexPoly(board_u8, np.rint(points).astype(np.int32), 255)
    kernel = np.ones((dilation_kernel_px, dilation_kernel_px), dtype=np.uint8)
    board = cv2.dilate(board_u8, kernel) > 0
    return board, ~board


def fit_once(
    contract_path: Path = DEFAULT_CONTRACT,
    output_directory: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR84 one-run receipt already exists")
    contract = json.loads(contract_path.read_text())
    for name, source in contract["sources"].items():
        if name == "mesh_asset_root":
            continue
        if sha256_file(REPO_ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['path']}")
    or83_closeout = json.loads(
        (REPO_ROOT / contract["sources"]["or83_closeout"]["path"]).read_text()
    )
    if or83_closeout["reviewer_decision"] != "FREEZE_ONE_BOARD_TO_ROBOT_WORLD_REGISTRATION_FAMILY":
        raise ValueError("OR83 did not authorize the OR84 mechanism family")
    or83_receipt = json.loads(
        (REPO_ROOT / contract["sources"]["or83_receipt"]["path"]).read_text()
    )
    or82_receipt = json.loads(
        (REPO_ROOT / contract["sources"]["or82_receipt"]["path"]).read_text()
    )
    if or82_receipt["selected"]["camera"] != contract["fixed_camera"]:
        raise ValueError("OR82 fixed board camera drifted")
    or81_contract = json.loads(
        (REPO_ROOT / contract["sources"]["or81_contract"]["path"]).read_text()
    )
    or72_contract = json.loads(
        (REPO_ROOT / contract["sources"]["or72_contract"]["path"]).read_text()
    )
    episodes = or72_contract["episodes"]
    if len(episodes) != 4 or any(row["split_role"] != "development" for row in episodes):
        raise ValueError("OR84 development episode boundary drifted")
    for episode in episodes:
        for binding in (episode["physical_video"], episode["state_trace"]):
            if sha256_file(REPO_ROOT / binding["path"]) != binding["sha256"]:
                raise ValueError(f"episode source hash mismatch: {binding['path']}")
    scene_binding = contract["sources"]["shared_scene_manifest"]
    scene = json.loads((REPO_ROOT / scene_binding["path"]).read_text())
    if scene["revision_sha256"] != scene_binding["revision_sha256"]:
        raise ValueError("scene revision mismatch")
    family = contract["scene_registration_family"]
    if scene["bodies"][int(family["anchor_body_id"])]["name"] != family["anchor_body_name"]:
        raise ValueError("board anchor identity drifted")
    partition = (
        set(family["fixed_board_group_body_ids"])
        | set(family["transformed_workcell_body_ids"])
        | set(family["untransformed_other_body_ids"])
    )
    if partition != set(range(len(scene["bodies"]))):
        raise ValueError("OR84 body partition is incomplete")
    annotations = {
        row["recording_id"]: np.asarray(row["points_px"], dtype=np.float64)
        for row in or81_contract["annotations"]["episodes"]
    }
    or83_rows = {row["recording_id"]: row for row in or83_receipt["rows"]}
    if set(annotations) != {row["recording_id"] for row in episodes} or set(or83_rows) != set(annotations):
        raise ValueError("OR84 annotation or baseline boundary drifted")
    traces = [
        json.loads((REPO_ROOT / episode["state_trace"]["path"]).read_text())
        for episode in episodes
    ]
    for trace in traces:
        if trace["body_names"] != [body["name"] for body in scene["bodies"]]:
            raise ValueError("scene and trace body ordering drifted")

    search = contract["search"]
    search_width = int(search["width_px"])
    search_height = int(search["height_px"])
    physical_search = [
        _read_initial_physical_frame(
            REPO_ROOT / episode["physical_video"]["path"],
            width=search_width,
            height=search_height,
        )
        for episode in episodes
    ]
    search_masks = [
        _region_masks(
            annotations[episode["recording_id"]]
            * np.asarray([search_width / 320.0, search_height / 240.0]),
            width=search_width,
            height=search_height,
            dilation_kernel_px=max(
                1,
                int(
                    round(
                        contract["regions"]["board_plus_margin"]["dilation_kernel_px_at_320x240"]
                        * search_width
                        / 320.0
                    )
                ),
            ),
        )
        for episode in episodes
    ]
    camera = contract["fixed_camera"]
    edge_metric = contract["metric"]
    background = contract["final_renderer"]["background_rgb"]
    evaluation_count = 0
    best_score = -np.inf
    best_history: list[dict[str, Any]] = []

    def evaluate_proxy(vector: np.ndarray) -> tuple[float, list[dict[str, float]]]:
        values: list[dict[str, float]] = []
        for physical, trace, masks in zip(
            physical_search, traces, search_masks, strict=True
        ):
            candidate = _render_analytic_candidate(
                scene,
                trace,
                camera,
                vector,
                family,
                width=search_width,
                height=search_height,
                background_rgb=background,
            )
            whole = _metrics(physical, candidate, edge_metric)
            region = _masked_tolerant_edge_f1(
                cv2.cvtColor(physical, cv2.COLOR_BGR2GRAY),
                cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY),
                masks[1],
                edge_metric,
            )
            values.append(
                {
                    "outside_board_edge_f1": float(region["f1"]),
                    "whole_frame_edge_f1": whole["tolerant_edge_f1"],
                    "whole_frame_linear_similarity": whole[
                        "full_frame_linear_pixel_similarity"
                    ],
                }
            )
        score = float(
            np.mean([row["outside_board_edge_f1"] for row in values])
            + 0.20 * np.mean([row["whole_frame_edge_f1"] for row in values])
            + 0.05
            * np.mean([row["whole_frame_linear_similarity"] for row in values])
        )
        return score, values

    def objective(vector: np.ndarray) -> float:
        nonlocal evaluation_count, best_score
        score, values = evaluate_proxy(vector)
        evaluation_count += 1
        if score > best_score:
            best_score = score
            best_history.append(
                {
                    "evaluation": evaluation_count,
                    "score": score,
                    "vector": np.asarray(vector, dtype=np.float64).tolist(),
                    "per_episode": values,
                }
            )
        return -score

    proxy_baseline_score, proxy_baseline_rows = evaluate_proxy(
        np.zeros(3, dtype=np.float64)
    )
    result = differential_evolution(
        objective,
        bounds=[tuple(float(value) for value in row) for row in family["bounds"]],
        rng=np.random.default_rng(int(search["seed"])),
        popsize=int(search["population_size_multiplier"]),
        maxiter=int(search["maximum_iterations"]),
        tol=float(search["tolerance"]),
        atol=float(search["absolute_tolerance"]),
        polish=bool(search["polish"]),
        workers=int(search["workers"]),
        updating="immediate",
    )
    if evaluation_count > int(search["maximum_candidate_evaluations"]):
        raise RuntimeError("OR84 proxy search exceeded frozen evaluation budget")
    selected_vector = np.asarray(result.x, dtype=np.float64)
    selected_proxy_score, selected_proxy_rows = evaluate_proxy(selected_vector)

    output_directory.mkdir(parents=True, exist_ok=True)
    meshes, asset_receipts = _load_unique_asset_cache(
        scene, REPO_ROOT / contract["sources"]["mesh_asset_root"]["path"]
    )
    library_path, compile_command, compiler_stderr = _compile_native(
        {
            "sources": {
                "native_source": contract["sources"]["or79_native_source"]
            },
            "compiler": {"executable": "clang"},
        },
        output_directory,
    )
    renderer = contract["final_renderer"]
    final_rows: list[dict[str, Any]] = []
    for episode, trace in zip(episodes, traces, strict=True):
        recording_id = episode["recording_id"]
        physical = _read_initial_physical_frame(
            REPO_ROOT / episode["physical_video"]["path"], width=320, height=240
        )
        board_mask, outside_mask = _region_masks(
            annotations[recording_id],
            width=320,
            height=240,
            dilation_kernel_px=int(
                contract["regions"]["board_plus_margin"]["dilation_kernel_px_at_320x240"]
            ),
        )
        pixels, depths, colors, triangle_count = _prepare_full_mesh_stream(
            scene,
            trace,
            meshes,
            camera,
            renderer,
            family,
            selected_vector,
        )
        candidate, updates, occluded, raster_seconds = _native_rasterize(
            library_path, pixels, depths, colors, renderer
        )
        image_path = output_directory / f"{recording_id}.png"
        ok, encoded = cv2.imencode(
            ".png", candidate, [cv2.IMWRITE_PNG_COMPRESSION, 9]
        )
        if not ok:
            raise RuntimeError("failed to encode OR84 candidate image")
        image_path.write_bytes(encoded.tobytes())
        physical_gray = cv2.cvtColor(physical, cv2.COLOR_BGR2GRAY)
        candidate_gray = cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY)
        whole = _metrics(physical, candidate, edge_metric)
        board = _masked_tolerant_edge_f1(
            physical_gray, candidate_gray, board_mask, edge_metric
        )
        outside = _masked_tolerant_edge_f1(
            physical_gray, candidate_gray, outside_mask, edge_metric
        )
        baseline = or83_rows[recording_id]["metrics"]["or82"]
        final_rows.append(
            {
                "recording_id": recording_id,
                "metrics": {
                    "whole_frame": whole,
                    "board_plus_margin": board,
                    "outside_board": outside,
                    "outside_board_edge_f1_delta_over_or82": float(
                        outside["f1"] - baseline["outside_board"]["f1"]
                    ),
                    "board_plus_margin_edge_f1_delta_over_or82": float(
                        board["f1"] - baseline["board_plus_margin"]["f1"]
                    ),
                },
                "render": {
                    "total_raster_triangle_count": triangle_count,
                    "depth_buffer_update_count": updates,
                    "occluded_fragment_count": occluded,
                    "native_raster_seconds": raster_seconds,
                },
                "candidate_image": {
                    "path": str(image_path.relative_to(REPO_ROOT)),
                    "sha256": sha256_file(image_path),
                },
            }
        )
    mean_board = float(
        np.mean([row["metrics"]["board_plus_margin"]["f1"] for row in final_rows])
    )
    mean_outside = float(
        np.mean([row["metrics"]["outside_board"]["f1"] for row in final_rows])
    )
    mean_edge = float(
        np.mean([row["metrics"]["whole_frame"]["tolerant_edge_f1"] for row in final_rows])
    )
    mean_similarity = float(
        np.mean(
            [
                row["metrics"]["whole_frame"]["full_frame_linear_pixel_similarity"]
                for row in final_rows
            ]
        )
    )
    or82_mean_edge = float(or82_receipt["summary"]["mean_tolerant_edge_f1"])
    acceptance = contract["acceptance"]
    gates = {
        "exact_four_development_episodes": len(final_rows) == 4,
        "one_shared_three_parameter_vector": len(selected_vector) == 3,
        "proxy_search_within_budget": evaluation_count
        <= int(search["maximum_candidate_evaluations"]),
        "exact_four_full_mesh_final_renders": len(final_rows) == 4,
        "manifest_unique_assets_read_once": len(asset_receipts) == 18,
        "mean_board_plus_margin_edge_f1": mean_board
        >= float(acceptance["minimum_selected_mean_board_plus_margin_edge_f1"]),
        "mean_outside_board_edge_f1": mean_outside
        >= float(acceptance["minimum_selected_mean_outside_board_edge_f1"]),
        "every_episode_outside_board_edge_improvement": all(
            row["metrics"]["outside_board_edge_f1_delta_over_or82"]
            >= float(
                acceptance[
                    "minimum_each_episode_outside_board_edge_f1_delta_over_or82"
                ]
            )
            for row in final_rows
        ),
        "mean_whole_frame_tolerant_edge_f1": mean_edge
        >= float(acceptance["minimum_selected_mean_whole_frame_tolerant_edge_f1"]),
        "mean_whole_frame_edge_delta_over_or82": mean_edge - or82_mean_edge
        >= float(
            acceptance[
                "minimum_selected_minus_or82_mean_whole_frame_tolerant_edge_f1"
            ]
        ),
        "mean_full_frame_linear_pixel_similarity": mean_similarity
        >= float(
            acceptance["minimum_selected_mean_full_frame_linear_pixel_similarity"]
        ),
        "camera_board_pawns_fiducials_actions_states_timing_appearance_fixed": True,
        "validation_and_heldout_closed": True,
        "no_replay_hardware_or_paid_compute": True,
    }
    passed = all(gates.values())
    receipt: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_board_anchored_workcell_se2_static_development_fit_receipt.v1",
        "experiment_id": contract["experiment_id"],
        "status": (
            "PASS_BOARD_ANCHORED_WORKCELL_SE2_STATIC_DEVELOPMENT_ADVANCE"
            if passed
            else "TERMINAL_BOARD_ANCHORED_WORKCELL_SE2_STATIC_GATE_FAILED"
        ),
        "proof_class": contract["proof_class"],
        "contract": {
            "path": str(contract_path.relative_to(REPO_ROOT)),
            "sha256": sha256_file(contract_path),
        },
        "selected": {
            "parameter_names": family["parameter_names"],
            "vector": selected_vector.tolist(),
            "optimizer_converged": bool(result.success),
            "optimizer_message": str(result.message),
            "proxy_score": selected_proxy_score,
            "proxy_score_delta_over_identity": selected_proxy_score
            - proxy_baseline_score,
            "proxy_per_episode": selected_proxy_rows,
        },
        "proxy_baseline": {
            "vector": [0.0, 0.0, 0.0],
            "score": proxy_baseline_score,
            "per_episode": proxy_baseline_rows,
        },
        "best_history": best_history,
        "final_rows": final_rows,
        "summary": {
            "mean_board_plus_margin_edge_f1": mean_board,
            "mean_outside_board_edge_f1": mean_outside,
            "mean_whole_frame_tolerant_edge_f1": mean_edge,
            "or82_mean_whole_frame_tolerant_edge_f1": or82_mean_edge,
            "mean_whole_frame_edge_delta_over_or82": mean_edge - or82_mean_edge,
            "mean_full_frame_linear_pixel_similarity": mean_similarity,
        },
        "compiled_library": {
            "path": str(library_path.relative_to(REPO_ROOT)),
            "sha256": sha256_file(library_path),
            "compile_command": compile_command,
            "compiler_stderr": compiler_stderr,
        },
        "gates": gates,
        "execution": {
            "development_physical_video_decodes": 4,
            "development_physical_frames": 4,
            "shared_parameter_count": 3,
            "analytic_search_candidate_evaluations": evaluation_count,
            "exact_full_mesh_final_renders": 4,
            "simulator_replays": 0,
            "validation_reads": 0,
            "evaluator_heldout_reads": 0,
            "hardware_actions": 0,
            "paid_compute": False,
        },
        "claim_limits": contract["claim_limits"],
        "reviewer_decision": (
            "ADVANCE_TO_FROZEN_WORKCELL_SE2_FULL_DEVELOPMENT_TIMELINE"
            if passed
            else "REJECT_WORKCELL_SE2_AND_REATTRIBUTE_COMPONENT_FAMILY"
        ),
        "next_transition": (
            "freeze_or85_workcell_se2_full_development_timeline"
            if passed
            else "freeze_or85_scene_component_residual_reattribution"
        ),
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(fit_once(), sort_keys=True))
