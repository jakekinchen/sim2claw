"""Run OR133A's outcome-informed, diagnostic-only regional attribution audit."""

from __future__ import annotations

import ctypes
import json
import platform
import subprocess
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from scipy.ndimage import distance_transform_edt

from .learning_factory_artifacts import atomic_write_json, canonical_digest
from .observable_registration_board_anchored_workcell_se2_static_development_fit import (
    _prepare_full_mesh_stream,
    _region_masks,
)
from .observable_registration_development_shared_camera_baseline import (
    _decode_selected_frames,
)
from .observable_registration_expanded_development_global_monotone_response_fit import (
    apply_monotone_response,
)
from .observable_registration_host_native_analytic_3d_renderer_capability import (
    REPO_ROOT,
    sha256_file,
)
from .observable_registration_host_native_mesh_zbuffer_renderer_capability import (
    _local_triangles_for_geom,
)
from .observable_registration_native_rasterizer_byte_equivalence import (
    _compile_native,
    _native_rasterize,
)
from .observable_registration_post_final_independent_left_right_robot_base_se2_diagnostic import (
    _independently_registered_trace,
)
from .observable_registration_post_final_independent_robot_base_full_corpus_diagnostic import (
    _episode_inventory,
    load_post_final_independent_robot_base_full_corpus_diagnostic_contract,
)
from .observable_registration_post_final_renderer_native_finite_linear_workcell_object_reconstruction import (
    _primitive_triangle_stream,
    load_post_final_renderer_native_finite_linear_workcell_object_reconstruction_contract,
)
from .observable_registration_post_final_static_dynamic_edge_occupancy_factorization import (
    _read_video_frames,
)
from .observable_registration_renderer_native_planar_fixture_static_comparison import (
    _fixture_stream,
)
from .observable_registration_renderer_native_two_planar_fixture_full_timeline_propagation import (
    _merged_or119_contract,
    load_two_planar_fixture_full_timeline_contract,
)
from .observable_registration_static_development_full_mesh_comparison import (
    _load_unique_asset_cache,
)


cv2.ocl.setUseOpenCL(False)

SCHEMA = "sim2claw.observable_registration_renderer_native_regional_residual_attribution_contract.v1"
DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_renderer_native_regional_residual_attribution_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_renderer_native_regional_residual_attribution_v1"


def load_regional_residual_attribution_contract(
    path: Path = DEFAULT_CONTRACT,
) -> dict[str, Any]:
    contract = json.loads(path.read_text())
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("unsupported OR133A contract")
    for binding in contract["sources"].values():
        source = REPO_ROOT / binding["path"]
        if sha256_file(source) != binding["sha256"]:
            raise ValueError(f"OR133A source identity mismatch: {binding['path']}")
    for binding in contract["frozen_identities"].values():
        source = REPO_ROOT / binding["path"]
        if sha256_file(source) != binding["sha256"]:
            raise ValueError(f"OR133A frozen identity mismatch: {binding['path']}")

    or131 = json.loads((REPO_ROOT / contract["sources"]["or131_receipt"]["path"]).read_text())
    or132 = json.loads((REPO_ROOT / contract["sources"]["or132_receipt"]["path"]).read_text())
    if or131["artifact_sha256"] != contract["sources"]["or131_receipt"]["artifact_sha256"]:
        raise ValueError("OR133A OR131 artifact drifted")
    if or132["artifact_sha256"] != contract["sources"]["or132_receipt"]["artifact_sha256"]:
        raise ValueError("OR133A OR132 artifact drifted")

    development = contract["development_partition"]
    if development["split_positions"] != list(range(1, 8)):
        raise ValueError("OR133A development partition drifted")
    episodes = development["episodes"]
    if len(episodes) != 7 or sum(int(row["frame_count"]) for row in episodes) != 751:
        raise ValueError("OR133A development budget drifted")
    if [int(row["split_position"]) for row in episodes] != list(range(1, 8)):
        raise ValueError("OR133A episode ordering drifted")

    groups = contract["renderer_group_ids"]
    declared_body_ids = [int(body) for group in groups.values() for body in group.get("body_ids", [])]
    if len(declared_body_ids) != len(set(declared_body_ids)):
        raise ValueError("OR133A renderer body groups overlap")
    scene = json.loads((REPO_ROOT / contract["sources"]["scene_manifest"]["path"]).read_text())
    rendered_body_ids = {int(geom["body_id"]) for geom in scene["geoms"]}
    if set(declared_body_ids) != rendered_body_ids:
        raise ValueError("OR133A renderer body groups are not exhaustive")

    resources = contract["resource_boundary"]
    expected_resources = {
        "existing_physical_video_decodes_allowed": 7,
        "physical_frames_read_allowed": 751,
        "existing_or131_candidate_video_decodes_allowed": 7,
        "candidate_frames_read_allowed": 751,
        "existing_or132_occupancy_map_reads_allowed": 7,
        "instrumented_id_buffer_frame_renders_allowed": 751,
        "synthetic_renderer_equivalence_test_renders_allowed": 2,
        "positions_8_through_11_pixel_reads_allowed": 0,
        "sibling_pixel_reads_allowed": 0,
        "fits_allowed": 0,
        "candidate_selections_allowed": 0,
        "threshold_changes_allowed": 0,
        "retries_allowed": 0,
        "simulator_replays_allowed": 0,
        "hardware_actions_allowed": 0,
        "paid_compute_allowed": False,
    }
    if resources != expected_resources:
        raise ValueError("OR133A resource boundary drifted")
    if any(contract["authority"].values()):
        raise ValueError("OR133A authority must remain closed")
    if contract["protocol_provenance"]["retrospective_and_outcome_informed"] is not True:
        raise ValueError("OR133A must remain outcome-informed")
    if any(
        contract["claim_limits"][key] is not False
        for key in (
            "fidelity_improvement",
            "regional_target_progress",
            "regional_target_resolution",
            "physics_fidelity",
            "predictive_simulation",
            "physical_transfer",
            "simulator_promotion",
        )
    ):
        raise ValueError("OR133A claim boundary drifted")
    return contract


def _compile_id_renderer(output_directory: Path) -> tuple[Path, list[str], str]:
    source = REPO_ROOT / "tools/renderer/or133a_id_buffer_attribution.c"
    suffix = ".dylib" if platform.system() == "Darwin" else ".so"
    library = output_directory / f"or133a_id_buffer_attribution{suffix}"
    command = [
        "clang",
        "-O2",
        "-std=c11",
        *(["-dynamiclib"] if platform.system() == "Darwin" else ["-shared", "-fPIC"]),
        str(source),
        "-o",
        str(library),
    ]
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    return library, command, completed.stderr


def _native_rasterize_with_ids(
    library_path: Path,
    pixels: np.ndarray,
    depths: np.ndarray,
    colors: np.ndarray,
    group_ids: np.ndarray,
    renderer: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray, int, int, float]:
    if not (
        pixels.flags.c_contiguous
        and depths.flags.c_contiguous
        and colors.flags.c_contiguous
        and group_ids.flags.c_contiguous
    ):
        raise ValueError("OR133A native inputs must be contiguous")
    if len(pixels) != len(depths) or len(pixels) != len(colors) or len(pixels) != len(group_ids):
        raise ValueError("OR133A native input length mismatch")
    library = ctypes.CDLL(str(library_path))
    function = library.rasterize_triangles_with_ids
    function.argtypes = [
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.POINTER(ctypes.c_double),
        ctypes.POINTER(ctypes.c_uint16),
        ctypes.c_int,
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_double),
        ctypes.POINTER(ctypes.c_double),
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.POINTER(ctypes.c_uint16),
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_uint64),
        ctypes.POINTER(ctypes.c_uint64),
    ]
    function.restype = ctypes.c_int
    width, height = int(renderer["width_px"]), int(renderer["height_px"])
    frame = np.empty((height, width, 3), dtype=np.uint8)
    frame[:] = np.asarray(renderer["background_rgb"], dtype=np.uint8)[::-1]
    zbuffer = np.full((height, width), np.inf, dtype=np.float64)
    idbuffer = np.zeros((height, width), dtype=np.uint16)
    updates = ctypes.c_uint64(0)
    occluded = ctypes.c_uint64(0)
    started = time.perf_counter()
    result = function(
        frame.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)),
        zbuffer.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        idbuffer.ctypes.data_as(ctypes.POINTER(ctypes.c_uint16)),
        width,
        height,
        pixels.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        depths.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
        colors.ctypes.data_as(ctypes.POINTER(ctypes.c_uint8)),
        group_ids.ctypes.data_as(ctypes.POINTER(ctypes.c_uint16)),
        len(pixels),
        ctypes.byref(updates),
        ctypes.byref(occluded),
    )
    elapsed = time.perf_counter() - started
    if result != 0:
        raise RuntimeError(f"OR133A native rasterizer returned {result}")
    return frame, idbuffer, updates.value, occluded.value, elapsed


def _renderer_equivalence_probe(
    original_library: Path,
    id_library: Path,
) -> dict[str, Any]:
    renderer = {"width_px": 16, "height_px": 12, "background_rgb": [13, 29, 47]}
    pixels = np.ascontiguousarray(
        [[[1.25, 1.25], [14.5, 1.5], [2.0, 10.5]], [[4.0, 3.0], [13.0, 4.0], [8.0, 10.0]]],
        dtype=np.float64,
    )
    depths = np.ascontiguousarray([[2.0, 2.2, 2.1], [1.0, 1.1, 1.05]], dtype=np.float64)
    colors = np.ascontiguousarray([[31, 79, 127], [211, 163, 97]], dtype=np.uint8)
    group_ids = np.ascontiguousarray([4, 9], dtype=np.uint16)
    original, original_updates, original_occluded, _ = _native_rasterize(
        original_library, pixels, depths, colors, renderer
    )
    instrumented, ids, id_updates, id_occluded, _ = _native_rasterize_with_ids(
        id_library, pixels, depths, colors, group_ids, renderer
    )
    return {
        "synthetic_render_count": 2,
        "rgb_byte_equal": bool(np.array_equal(original, instrumented)),
        "depth_updates_equal": original_updates == id_updates,
        "occluded_fragments_equal": original_occluded == id_occluded,
        "visible_group_ids": sorted(int(value) for value in np.unique(ids) if value != 0),
    }


def _triangle_group_ids(
    scene: dict[str, Any],
    meshes: dict[int, tuple[dict[str, Any], np.ndarray]],
    renderer: dict[str, Any],
    groups: dict[str, Any],
) -> tuple[np.ndarray, dict[str, int]]:
    names = list(groups)
    numeric = {name: index + 1 for index, name in enumerate(names)}
    body_to_group = {
        int(body_id): numeric[name]
        for name, declaration in groups.items()
        for body_id in declaration.get("body_ids", [])
    }
    chunks: list[np.ndarray] = []
    for geom in scene["geoms"]:
        local, _, _ = _local_triangles_for_geom(geom, meshes=meshes, config=renderer)
        body_id = int(geom["body_id"])
        if body_id not in body_to_group:
            raise ValueError(f"OR133A ungrouped rendered body: {body_id}")
        chunks.append(np.full(len(local), body_to_group[body_id], dtype=np.uint16))
    return np.ascontiguousarray(np.concatenate(chunks)), numeric


def _occupancy_panels(binding: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    path = REPO_ROOT / binding["path"]
    if binding.get("layout") != "physical_persistent_candidate_persistent_physical_dynamic_candidate_dynamic":
        raise ValueError("OR133A occupancy layout drifted")
    if sha256_file(path) != binding["sha256"]:
        raise ValueError("OR133A occupancy map hash drifted")
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None or image.shape != (240, 1280):
        raise ValueError("OR133A occupancy map shape drifted")
    return tuple(panel > 0 for panel in np.split(image, 4, axis=1))  # type: ignore[return-value]


def _rigid_edge_diagnostic(
    physical_persistent: np.ndarray,
    candidate_persistent: np.ndarray,
    physical_frames: list[np.ndarray],
    candidate_frames: list[np.ndarray],
) -> dict[str, Any]:
    candidate_y, candidate_x = np.nonzero(candidate_persistent)
    if len(candidate_x) == 0 or not physical_persistent.any():
        return {"available": False, "reason": "empty persistent edge support"}
    distances, nearest = distance_transform_edt(~physical_persistent, return_indices=True)
    target_y = nearest[0, candidate_y, candidate_x]
    target_x = nearest[1, candidate_y, candidate_x]
    source = np.column_stack([candidate_x, candidate_y]).astype(np.float64)
    target = np.column_stack([target_x, target_y]).astype(np.float64)
    source_center = source.mean(axis=0)
    target_center = target.mean(axis=0)
    covariance = (source - source_center).T @ (target - target_center)
    u, _, vt = np.linalg.svd(covariance)
    rotation = vt.T @ u.T
    if np.linalg.det(rotation) < 0:
        vt[-1] *= -1
        rotation = vt.T @ u.T
    translation = target_center - source_center @ rotation.T
    predicted = source @ rotation.T + translation
    residual = np.linalg.norm(predicted - target, axis=1)
    vectors = target - source
    physical_median = np.median(np.stack(physical_frames), axis=0).astype(np.uint8)
    candidate_median = np.median(np.stack(candidate_frames), axis=0).astype(np.uint8)
    physical_gray = cv2.cvtColor(physical_median, cv2.COLOR_BGR2GRAY)
    candidate_gray = cv2.cvtColor(candidate_median, cv2.COLOR_BGR2GRAY)
    intensity = np.abs(
        physical_gray[target_y, target_x].astype(np.int16)
        - candidate_gray[candidate_y, candidate_x].astype(np.int16)
    )
    angle = float(np.degrees(np.arctan2(rotation[1, 0], rotation[0, 0])))
    sampled = distances[candidate_y, candidate_x]
    return {
        "available": True,
        "candidate_persistent_edge_pixels": int(len(source)),
        "physical_persistent_edge_pixels": int(physical_persistent.sum()),
        "distance_px": {
            "median": float(np.median(sampled)),
            "mean": float(np.mean(sampled)),
            "p90": float(np.percentile(sampled, 90)),
        },
        "nearest_neighbor_vector_field_px": {
            "mean_dx": float(vectors[:, 0].mean()),
            "mean_dy": float(vectors[:, 1].mean()),
            "median_dx": float(np.median(vectors[:, 0])),
            "median_dy": float(np.median(vectors[:, 1])),
        },
        "weighted_image_plane_rigid_decomposition_not_applied": {
            "rotation_degrees": angle,
            "translation_xy_px": [float(value) for value in translation],
            "median_correspondence_residual_px": float(np.median(residual)),
        },
        "nearest_edge_matched_intensity_absolute_residual_no_response_fit": {
            "mean_luma": float(np.mean(intensity)),
            "median_luma": float(np.median(intensity)),
            "p90_luma": float(np.percentile(intensity, 90)),
        },
    }


def _bearing_span_degrees(points_xy: np.ndarray) -> float:
    if len(points_xy) < 2:
        return 0.0
    angles = np.sort(
        np.mod(np.degrees(np.arctan2(points_xy[:, 1] - 120.0, points_xy[:, 0] - 160.0)), 360.0)
    )
    gaps = np.diff(np.concatenate([angles, angles[:1] + 360.0]))
    return float(360.0 - np.max(gaps))


def _landmark_inventory(mask: np.ndarray, limits: dict[str, Any]) -> dict[str, Any]:
    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    points: set[tuple[int, int]] = set()
    for contour in contours:
        hull = cv2.convexHull(contour)
        points.update((int(point[0][0]), int(point[0][1])) for point in hull)
    ordered = np.asarray(sorted(points), dtype=np.float64)
    if len(ordered) >= 3:
        design = np.column_stack(
            [(ordered[:, 0] - 160.0) / 160.0, (ordered[:, 1] - 120.0) / 120.0, np.ones(len(ordered))]
        )
        condition = float(np.linalg.cond(design))
    else:
        condition = float("inf")
    span = _bearing_span_degrees(ordered) if len(ordered) else 0.0
    eligible = (
        len(ordered) >= int(limits["future_fit_eligibility_only_if_landmarks_at_least"])
        and span >= float(limits["future_fit_eligibility_only_if_bearing_span_degrees_at_least"])
        and np.isfinite(condition)
        and condition <= float(limits["future_fit_eligibility_only_if_condition_number_at_most"])
    )
    return {
        "definition": "unique convex-hull vertices of visible connected renderer-group masks",
        "available_landmark_count": int(len(ordered)),
        "bearing_span_degrees": span,
        "least_squares_condition_number": condition if np.isfinite(condition) else None,
        "future_fit_eligible": bool(eligible),
        "transforms_fitted": 0,
    }


def _shadow_image_direction(camera: dict[str, Any], light: list[float]) -> np.ndarray:
    position = np.asarray(camera["position"], dtype=np.float64)
    target = np.asarray(camera["target"], dtype=np.float64)
    forward = target - position
    forward /= np.linalg.norm(forward)
    world_up = np.asarray([0.0, 0.0, 1.0])
    right = np.cross(forward, world_up)
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    roll = np.deg2rad(float(camera.get("roll_degrees", 0.0)))
    rolled_right = np.cos(roll) * right + np.sin(roll) * up
    rolled_up = -np.sin(roll) * right + np.cos(roll) * up
    direction = np.asarray(light, dtype=np.float64)
    image_light = np.asarray([direction @ rolled_right, -(direction @ rolled_up)])
    shadow = -image_light
    norm = np.linalg.norm(shadow)
    if norm <= 1.0e-12:
        raise ValueError("OR133A nominal light has no image-plane component")
    return shadow / norm


def _boundary_component_pixels(mask: np.ndarray) -> int:
    count, labels = cv2.connectedComponents(mask.astype(np.uint8), connectivity=8)
    total = 0
    for label in range(1, count):
        component = labels == label
        if component[0].any() or component[-1].any() or component[:, 0].any() or component[:, -1].any():
            total += int(component.sum())
    return total


def _dynamic_attribution(
    physical_frames: list[np.ndarray],
    candidate_frames: list[np.ndarray],
    idbuffers: list[np.ndarray],
    physical_persistent: np.ndarray,
    physical_dynamic: np.ndarray,
    outside_mask: np.ndarray,
    arm_group_ids: set[int],
    contract: dict[str, Any],
    baseline_luma: float,
) -> dict[str, Any]:
    tolerance = int(contract["edge_tolerance_kernel_px"])
    kernel = np.ones((tolerance, tolerance), dtype=np.uint8)
    shadow_direction = _shadow_image_direction(
        contract["camera"], contract["nominal_light_direction"]
    )
    silhouette_limit = float(
        contract["silhouette_deficit"]["distance_to_rendered_arm_silhouette_px_exclusive_max"]
    )
    shadow_minimum = float(contract["shadow_like"]["distance_to_rendered_arm_silhouette_px_min"])
    staged: list[dict[str, Any]] = []
    silhouette_total = 0
    residual_total = 0
    for physical, candidate, ids in zip(physical_frames, candidate_frames, idbuffers, strict=True):
        physical_gray = cv2.cvtColor(physical, cv2.COLOR_BGR2GRAY)
        candidate_gray = cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY)
        physical_edge = cv2.Canny(
            physical_gray,
            int(contract["canny_low_threshold"]),
            int(contract["canny_high_threshold"]),
        ) > 0
        candidate_edge = cv2.Canny(
            candidate_gray,
            int(contract["canny_low_threshold"]),
            int(contract["canny_high_threshold"]),
        ) > 0
        matched = cv2.dilate(candidate_edge.astype(np.uint8), kernel) > 0
        residual = physical_edge & physical_dynamic & outside_mask & ~matched
        arm_mask = np.isin(ids, list(arm_group_ids))
        arm_edge = cv2.morphologyEx(arm_mask.astype(np.uint8), cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0
        if arm_edge.any():
            arm_distance = distance_transform_edt(~arm_edge)
        else:
            arm_distance = np.full(residual.shape, np.inf)
        silhouette = residual & (arm_distance < silhouette_limit)
        rest = residual & ~silhouette
        potential = np.zeros_like(rest)
        offset: list[float] | None = None
        if arm_mask.any() and rest.any():
            arm_y, arm_x = np.nonzero(arm_mask)
            centroid = np.asarray([arm_x.mean(), arm_y.mean()])
            yy, xx = np.nonzero(rest)
            relative = np.column_stack([xx, yy]) - centroid
            on_shadow_side = relative @ shadow_direction > 0.0
            dark = physical_gray[yy, xx] < baseline_luma
            far = arm_distance[yy, xx] >= shadow_minimum
            chosen = on_shadow_side & dark & far
            potential[yy[chosen], xx[chosen]] = True
            if potential.any():
                py, px = np.nonzero(potential)
                offset = [float(px.mean() - centroid[0]), float(py.mean() - centroid[1])]
        residual_total += int(residual.sum())
        silhouette_total += int(silhouette.sum())
        staged.append({"rest": rest, "potential": potential, "offset": offset})

    offsets = np.asarray([row["offset"] for row in staged if row["offset"] is not None], dtype=np.float64)
    median_offset = np.median(offsets, axis=0) if len(offsets) else np.asarray([np.nan, np.nan])
    stability_max = float(contract["shadow_like"]["arm_centroid_offset_stability_px_max"])
    shadow_total = 0
    operator_total = 0
    for row in staged:
        stable = False
        if row["offset"] is not None:
            stable = float(np.linalg.norm(np.asarray(row["offset"]) - median_offset)) <= stability_max
        shadow = row["potential"] if stable else np.zeros_like(row["potential"])
        shadow_total += int(shadow.sum())
        nonshadow = row["rest"] & ~shadow
        operator_total += _boundary_component_pixels(nonshadow)
    unattributed = residual_total - silhouette_total - shadow_total - operator_total
    if unattributed < 0:
        raise ValueError("OR133A dynamic attribution mass overlap")
    denominator = max(residual_total, 1)
    shares = {
        "silhouette_deficit": silhouette_total / denominator,
        "shadow_like": shadow_total / denominator,
        "operator_or_cable_like": operator_total / denominator,
        "unattributed": unattributed / denominator,
    }
    return {
        "physical_dynamic_unmatched_edge_pixels": residual_total,
        "mass_pixels": {
            "silhouette_deficit": silhouette_total,
            "shadow_like": shadow_total,
            "operator_or_cable_like": operator_total,
            "unattributed": unattributed,
        },
        "mass_shares": shares,
        "mass_shares_sum": float(sum(shares.values())),
        "shadow_image_direction_xy": [float(value) for value in shadow_direction],
        "persistent_baseline_median_luma": baseline_luma,
        "shadow_offset_median_xy_px": None if not len(offsets) else [float(value) for value in median_offset],
        "shadow_offset_observed_frame_count": int(len(offsets)),
    }


def _json_reference_paths(value: Any, needle: str, prefix: str = "$") -> list[str]:
    matches: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            matches.extend(_json_reference_paths(child, needle, f"{prefix}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            matches.extend(_json_reference_paths(child, needle, f"{prefix}[{index}]"))
    elif isinstance(value, str) and needle in value:
        matches.append(prefix)
    return matches


def _exposure_audit(contract: dict[str, Any]) -> dict[str, Any]:
    pairing = json.loads((REPO_ROOT / contract["sources"]["pairing_inventory"]["path"]).read_text())
    selection = json.loads((REPO_ROOT / contract["sources"]["exposure_frame_selection"]["path"]).read_text())
    owner = json.loads((REPO_ROOT / contract["sources"]["owner_visual_review"]["path"]).read_text())
    pair_by_id = {row["recording_id"]: row for row in pairing["pairs"]}
    selection_by_id = {row["recording_id"]: row for row in selection["episodes"]}
    global_artifacts = sorted(
        {
            str(value)
            for source in (selection, owner)
            for key, value in source.items()
            if isinstance(value, str) and (key.endswith("_path") or "review_sheet" in key)
        }
    )
    rows: list[dict[str, Any]] = []
    for recording_id, episode in sorted(selection_by_id.items()):
        pair = pair_by_id.get(recording_id)
        frame_artifacts = [
            {"path": frame["path"], "phase": frame["phase"], "sha256": frame["sha256"]}
            for frame in episode.get("frames", [])
        ]
        rows.append(
            {
                "recording_id": recording_id,
                "or131_corpus_member": pair is not None,
                "or131_split_position": None if pair is None else int(pair["split_position"]),
                "physical_source_metadata": None if pair is None else pair["physical_video"],
                "derived_frame_artifacts": frame_artifacts,
                "frame_selection_json_references": _json_reference_paths(selection, recording_id),
                "owner_review_json_references": _json_reference_paths(owner, recording_id),
                "recorded_exposure": bool(frame_artifacts or _json_reference_paths(owner, recording_id)),
                "pixels_read_by_or133a": 0 if pair is None else None,
            }
        )
    sibling_rows = [row for row in rows if not row["or131_corpus_member"]]
    complete = (
        len(rows) == int(selection["total_episode_count"]) == 18
        and sum(len(row["derived_frame_artifacts"]) for row in rows) == int(selection["extracted_frame_count"]) == 36
        and len(sibling_rows) == 7
        and all(row["recorded_exposure"] for row in rows)
    )
    return {
        "metadata_only": True,
        "recording_count": len(rows),
        "or131_recording_count": len(rows) - len(sibling_rows),
        "other_sibling_recording_count": len(sibling_rows),
        "derived_frame_artifact_count": sum(len(row["derived_frame_artifacts"]) for row in rows),
        "global_review_artifacts": global_artifacts,
        "recordings": rows,
        "complete": complete,
        "resulting_claim": contract["exposure_audit"]["resulting_claim"],
        "untouched_cohort_remaining": False,
    }


def _summary(values: list[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=np.float64)
    return {
        "mean": float(array.mean()),
        "median": float(np.median(array)),
        "p10": float(np.percentile(array, 10)),
        "p90": float(np.percentile(array, 90)),
    }


def evaluate_once(
    contract_path: Path = DEFAULT_CONTRACT,
    output_directory: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR133A one-run receipt already exists; retry prohibited")
    contract = load_regional_residual_attribution_contract(contract_path)
    started = time.perf_counter()
    output_directory.mkdir(parents=True, exist_ok=True)

    or131_contract = load_two_planar_fixture_full_timeline_contract(
        REPO_ROOT / contract["sources"]["or131_contract"]["path"]
    )
    merged = _merged_or119_contract(or131_contract)
    or95_contract = load_post_final_independent_robot_base_full_corpus_diagnostic_contract(
        REPO_ROOT / merged["sources"]["or95_contract"]["path"]
    )
    or116_contract = load_post_final_renderer_native_finite_linear_workcell_object_reconstruction_contract(
        REPO_ROOT / merged["sources"]["or116_contract"]["path"]
    )
    or118 = json.loads((REPO_ROOT / merged["sources"]["or118_receipt"]["path"]).read_text())
    or131_receipt = json.loads((REPO_ROOT / contract["sources"]["or131_receipt"]["path"]).read_text())
    or131_rows = json.loads((REPO_ROOT / contract["sources"]["or131_frame_rows"]["path"]).read_text())["rows"]
    or132_receipt = json.loads((REPO_ROOT / contract["sources"]["or132_receipt"]["path"]).read_text())
    or120_contract = json.loads((REPO_ROOT / contract["sources"]["or120_contract"]["path"]).read_text())
    scene = json.loads((REPO_ROOT / contract["sources"]["scene_manifest"]["path"]).read_text())
    frozen = or95_contract["frozen_candidate"]
    camera = frozen["camera"]
    renderer = merged["renderer"]
    response = frozen["global_monotone_response"]
    static = frozen["static_workcell_transform"]
    static_family = {
        "anchor_body_id": int(static["anchor_body_id"]),
        "transformed_workcell_body_ids": [int(value) for value in static["transformed_body_ids"]],
    }
    static_vector = np.asarray(static["vector"], dtype=np.float64)
    left_ids = [int(value) for value in frozen["left_robot_transform"]["transformed_body_ids"]]
    right_ids = [int(value) for value in frozen["right_robot_transform"]["transformed_body_ids"]]
    robot_vector = np.asarray(
        frozen["left_robot_transform"]["vector"] + frozen["right_robot_transform"]["vector"],
        dtype=np.float64,
    )
    if static_vector.tolist() != contract["frozen_transforms"]["static_workcell"]["vector_yaw_deg_xy_m"]:
        raise ValueError("OR133A static transform binding drifted")
    if frozen["left_robot_transform"]["vector"] != contract["frozen_transforms"]["left_robot"]["vector_yaw_deg_xy_m"]:
        raise ValueError("OR133A left transform binding drifted")
    if frozen["right_robot_transform"]["vector"] != contract["frozen_transforms"]["right_robot"]["vector_yaw_deg_xy_m"]:
        raise ValueError("OR133A right transform binding drifted")
    if renderer["lighting"]["world_direction"] != contract["d0_dynamic_attribution"]["nominal_light_direction"]:
        raise ValueError("OR133A light-direction binding drifted")

    meshes, asset_receipts = _load_unique_asset_cache(
        scene, REPO_ROOT / merged["sources"]["mesh_asset_root"]["path"]
    )
    original_library, original_compile, original_stderr = _compile_native(
        {"sources": {"native_source": contract["sources"]["or79_native_source"]}, "compiler": {"executable": "clang"}},
        output_directory,
    )
    id_library, id_compile, id_stderr = _compile_id_renderer(output_directory)
    equivalence = _renderer_equivalence_probe(original_library, id_library)
    if not all(equivalence[key] for key in ("rgb_byte_equal", "depth_updates_equal", "occluded_fragments_equal")):
        raise ValueError("OR133A instrumented renderer failed synthetic equivalence")

    base_group_ids, group_numbers = _triangle_group_ids(
        scene, meshes, renderer, contract["renderer_group_ids"]
    )
    complete_parameters = json.loads((REPO_ROOT / or131_contract["sources"]["or126_parameters"]["path"]).read_text())
    clipped_parameters = json.loads((REPO_ROOT / or131_contract["sources"]["or129_parameters"]["path"]).read_text())
    complete_pixels, complete_depths, complete_colors = _fixture_stream(
        complete_parameters, camera, or131_contract, response
    )
    clipped_pixels, clipped_depths, clipped_colors = _fixture_stream(
        clipped_parameters, camera, or131_contract, response
    )
    fixture_pixels = np.ascontiguousarray(np.concatenate([complete_pixels, clipped_pixels]))
    fixture_depths = np.ascontiguousarray(np.concatenate([complete_depths, clipped_depths]))
    fixture_colors = np.ascontiguousarray(np.concatenate([complete_colors, clipped_colors]))
    fixture_ids = np.ascontiguousarray(
        np.concatenate(
            [
                np.full(len(complete_pixels), group_numbers["or126_complete_fixture"], np.uint16),
                np.full(len(clipped_pixels), group_numbers["or129_clipped_fixture"], np.uint16),
            ]
        )
    )
    shaft = np.asarray(merged["frozen_object"]["shaft_pre_response_bgr"], dtype=np.uint8)
    terminal = np.asarray(merged["frozen_object"]["terminal_pre_response_bgr"], dtype=np.uint8)
    object_colors = np.ascontiguousarray(
        np.concatenate([np.tile(shaft, (248, 1)), np.tile(terminal, (100, 1))])
    )
    object_ids = np.full(348, group_numbers["or116_finite_linear_object"], dtype=np.uint16)

    episodes = {int(row["split_position"]): row for row in _episode_inventory(or95_contract)}
    expected = {int(row["split_position"]): row for row in contract["development_partition"]["episodes"]}
    video_map = {row["recording_id"]: row for row in or131_receipt["candidate_videos"]}
    occupancy_map = {int(row["split_position"]): row for row in or132_receipt["rows"]}
    rows_by_position = {position: [] for position in expected}
    for row in or131_rows:
        position = int(row["split_position"])
        if position in rows_by_position:
            rows_by_position[position].append(row)
    for rows in rows_by_position.values():
        rows.sort(key=lambda row: int(row["evaluation_index"]))

    _, outside_mask = _region_masks(
        np.asarray(merged["regions"]["board_plus_margin"]["points_px"], dtype=np.float64),
        width=320,
        height=240,
        dilation_kernel_px=int(merged["regions"]["board_plus_margin"]["dilation_kernel_px_at_320x240"]),
    )
    group_aggregate = {
        name: {"visible_pixels": 0, "boundary_edge_pixels": 0, "persistent_overlap_pixels": 0, "union": np.zeros((240, 320), bool)}
        for name in group_numbers
    }
    episode_results: list[dict[str, Any]] = []
    triangle_counts: list[int] = []
    raster_seconds: list[float] = []
    visible_ids_valid = True
    physical_frame_reads = 0
    candidate_frame_reads = 0
    for position in range(1, 8):
        episode = episodes[position]
        declaration = expected[position]
        if episode["recording_id"] != declaration["recording_id"]:
            raise ValueError("OR133A episode identity drifted")
        bound_rows = rows_by_position[position]
        if len(bound_rows) != int(declaration["frame_count"]):
            raise ValueError("OR133A frame-count binding drifted")
        indices = np.asarray([int(row["physical_frame_index"]) for row in bound_rows], dtype=np.int64)
        physical_binding = episode["physical_video"]
        physical_frames = [
            cv2.flip(frame, -1)
            for frame in _decode_selected_frames(
                REPO_ROOT / physical_binding["path"],
                selected_indices=indices,
                expected_frame_count=int(physical_binding["frame_count"]),
                expected_width=int(physical_binding["width_px"]),
                expected_height=int(physical_binding["height_px"]),
                output_width=320,
                output_height=240,
            )
        ]
        candidate_binding = video_map[episode["recording_id"]]
        candidate_path = REPO_ROOT / candidate_binding["path"]
        if sha256_file(candidate_path) != candidate_binding["sha256"]:
            raise ValueError("OR133A OR131 candidate video drifted")
        candidate_frames = _read_video_frames(candidate_path, len(bound_rows))
        physical_frame_reads += len(physical_frames)
        candidate_frame_reads += len(candidate_frames)
        physical_persistent, candidate_persistent, physical_dynamic, _ = _occupancy_panels(
            occupancy_map[position]["occupancy_map"]
        )
        physical_persistent &= outside_mask
        candidate_persistent &= outside_mask
        physical_dynamic &= outside_mask
        trace = json.loads((REPO_ROOT / episode["state_trace"]["path"]).read_text())
        initial_one = {"body_names": trace["body_names"], "frames": [trace["frames"][0]]}
        initial_registered = _independently_registered_trace(
            initial_one,
            anchor_body_id=int(static["anchor_body_id"]),
            left_body_ids=left_ids,
            right_body_ids=right_ids,
            vector=robot_vector,
        )
        object_pixels, object_depths, _, object_metadata = _primitive_triangle_stream(
            or118["frozen_shape"],
            initial_registered,
            scene,
            camera,
            renderer,
            static_family,
            static_vector,
            or116_contract["support_plane"],
            np.asarray([0, 0, 0], dtype=np.uint8),
        )
        if len(object_pixels) != 348:
            raise ValueError("OR133A object triangle count drifted")
        idbuffers: list[np.ndarray] = []
        render_rgb_similarity: list[float] = []
        for bound, candidate in zip(bound_rows, candidate_frames, strict=True):
            trace_index = int(bound["state_trace_frame_index"])
            one = {"body_names": trace["body_names"], "frames": [trace["frames"][trace_index]]}
            registered = _independently_registered_trace(
                one,
                anchor_body_id=int(static["anchor_body_id"]),
                left_body_ids=left_ids,
                right_body_ids=right_ids,
                vector=robot_vector,
            )
            pixels, depths, colors, baseline_count = _prepare_full_mesh_stream(
                scene, registered, meshes, camera, renderer, static_family, static_vector
            )
            if baseline_count != len(base_group_ids):
                raise ValueError("OR133A base triangle/group count drifted")
            pixels = np.ascontiguousarray(np.concatenate([pixels, object_pixels, fixture_pixels]))
            depths = np.ascontiguousarray(np.concatenate([depths, object_depths, fixture_depths]))
            colors = np.ascontiguousarray(np.concatenate([colors, object_colors, fixture_colors]))
            ids_for_triangles = np.ascontiguousarray(
                np.concatenate([base_group_ids, object_ids, fixture_ids]), dtype=np.uint16
            )
            simulator, idbuffer, _, _, elapsed = _native_rasterize_with_ids(
                id_library, pixels, depths, colors, ids_for_triangles, renderer
            )
            rendered = apply_monotone_response(
                simulator,
                bias=float(response["bias"]),
                low_slope=float(response["low_intensity_slope"]),
                high_slope=float(response["high_intensity_slope"]),
                knot=int(response["fixed_input_knot"]),
            )
            render_rgb_similarity.append(float(1.0 - np.abs(rendered.astype(np.float64) - candidate).mean() / 255.0))
            triangle_counts.append(len(pixels))
            raster_seconds.append(elapsed)
            observed_ids = set(int(value) for value in np.unique(idbuffer) if value != 0)
            visible_ids_valid = visible_ids_valid and observed_ids.issubset(set(group_numbers.values()))
            idbuffers.append(idbuffer)
            for name, group_id in group_numbers.items():
                mask = idbuffer == group_id
                edge_mask = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0
                aggregate = group_aggregate[name]
                aggregate["visible_pixels"] += int(mask.sum())
                aggregate["boundary_edge_pixels"] += int(edge_mask.sum())
                aggregate["persistent_overlap_pixels"] += int((edge_mask & physical_persistent).sum())
                aggregate["union"] |= mask

        persistent_values = [
            cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)[physical_persistent]
            for frame in physical_frames
            if physical_persistent.any()
        ]
        baseline_luma = float(np.median(np.concatenate(persistent_values))) if persistent_values else 0.0
        d0_contract = dict(contract["d0_dynamic_attribution"])
        d0_contract["camera"] = camera
        d0_contract["canny_low_threshold"] = or120_contract["edge_occupancy"]["canny_low_threshold"]
        d0_contract["canny_high_threshold"] = or120_contract["edge_occupancy"]["canny_high_threshold"]
        dynamic = _dynamic_attribution(
            physical_frames,
            candidate_frames,
            idbuffers,
            physical_persistent,
            physical_dynamic,
            outside_mask,
            {group_numbers["left_robot"], group_numbers["right_robot"]},
            d0_contract,
            baseline_luma,
        )
        episode_results.append(
            {
                "split_position": position,
                "recording_id": episode["recording_id"],
                "frame_count": len(bound_rows),
                "geometry_vs_photometry": _rigid_edge_diagnostic(
                    physical_persistent, candidate_persistent, physical_frames, candidate_frames
                ),
                "dynamic_attribution": dynamic,
                "fresh_render_vs_lossy_or131_video_linear_similarity": _summary(render_rgb_similarity),
                "object_reprojection_error_px": float(object_metadata["axis_and_terminal_center_reprojection_error_px"]),
            }
        )

    landmarks = contract["s0_diagnostics"]["landmark_inventory"]
    group_results: dict[str, Any] = {}
    for name, aggregate in group_aggregate.items():
        union = aggregate.pop("union")
        group_results[name] = {
            **aggregate,
            "mean_visible_pixels_per_frame": aggregate["visible_pixels"] / 751.0,
            "mean_boundary_edge_pixels_per_frame": aggregate["boundary_edge_pixels"] / 751.0,
            "persistent_overlap_fraction_of_group_boundary_edges": aggregate["persistent_overlap_pixels"]
            / max(aggregate["boundary_edge_pixels"], 1),
            "landmarks": _landmark_inventory(union, landmarks),
        }

    exposure = _exposure_audit(contract)
    episode_path = output_directory / "episode_diagnostics.json"
    exposure_path = output_directory / "exposure_ledger.json"
    atomic_write_json(
        episode_path,
        {
            "schema_version": "sim2claw.observable_registration_renderer_native_regional_residual_attribution_episode_diagnostics.v1",
            "episodes": episode_results,
            "renderer_groups": group_results,
        },
    )
    atomic_write_json(exposure_path, exposure)

    threshold = contract["d0_dynamic_attribution"]["advisory_routing_thresholds"]
    geometry_episodes = sum(
        row["dynamic_attribution"]["mass_shares"]["silhouette_deficit"]
        >= float(threshold["geometry_first_if_silhouette_share_at_least"])
        for row in episode_results
    )
    illumination_episodes = sum(
        row["dynamic_attribution"]["mass_shares"]["shadow_like"]
        >= float(threshold["illumination_candidate_if_shadow_share_at_least"])
        for row in episode_results
    )
    operator_episodes = sum(
        row["dynamic_attribution"]["mass_pixels"]["operator_or_cable_like"]
        >= int(threshold["operator_candidate_if_pixels_per_episode_at_least"])
        for row in episode_results
    )
    minimum = int(threshold["minimum_episode_count"])
    candidates = [
        name
        for name, count in (
            ("renderer_geometry_silhouette", geometry_episodes),
            ("renderer_native_illumination_shadow", illumination_episodes),
            ("operator_or_cable_scene_content", operator_episodes),
        )
        if count >= minimum
    ]
    if len(candidates) == 1:
        successor = candidates[0]
    elif candidates:
        successor = "combined_factorial_of_qualified_diagnostic_families"
    else:
        successor = "broader_combined_factorization_or_diagnostic_repair"

    expected_triangles = int(
        contract["s0_diagnostics"]["per_group_contribution"]["expected_triangle_count_per_frame"]
    )
    mass_valid = all(
        np.isfinite(list(row["dynamic_attribution"]["mass_shares"].values())).all()
        and all(value >= 0.0 for value in row["dynamic_attribution"]["mass_shares"].values())
        and abs(float(row["dynamic_attribution"]["mass_shares_sum"]) - 1.0) <= 1.0e-12
        for row in episode_results
    )
    integrity = {
        "all_source_identities_match": True,
        "synthetic_instrumented_renderer_equivalent_to_or79": all(
            equivalence[key] for key in ("rgb_byte_equal", "depth_updates_equal", "occluded_fragments_equal")
        ),
        "exact_development_episode_count": len(episode_results) == 7,
        "exact_development_frame_count": physical_frame_reads == candidate_frame_reads == len(triangle_counts) == 751,
        "triangle_count_exact_every_frame": all(value == expected_triangles for value in triangle_counts),
        "id_buffer_group_ids_exhaustive_and_disjoint_at_visible_pixel": visible_ids_valid,
        "dynamic_attribution_mass_is_finite_nonnegative_and_conserved": mass_valid,
        "exposure_lineage_complete": exposure["complete"],
        "zero_intervention_fit_selection_threshold_change_or_retry": True,
        "closed_partitions_remain_unopened": True,
        "protocol_outcome_informed_flag_present": True,
    }
    if not integrity["triangle_count_exact_every_frame"] or not integrity["id_buffer_group_ids_exhaustive_and_disjoint_at_visible_pixel"]:
        status = contract["stop_conditions"]["triangle_or_id_buffer_failure"]
    elif not integrity["exposure_lineage_complete"]:
        status = contract["stop_conditions"]["unresolved_exposure_lineage"]
    elif all(integrity.values()):
        status = contract["stop_conditions"]["complete"]
    else:
        status = contract["stop_conditions"]["triangle_or_id_buffer_failure"]

    receipt: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_renderer_native_regional_residual_attribution_receipt.v1",
        "experiment_id": contract["experiment_id"],
        "status": status,
        "proof_class": contract["proof_class"],
        "contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)},
        "protocol_provenance": contract["protocol_provenance"],
        "renderer_equivalence": equivalence,
        "diagnostic_outputs": {
            "episode_diagnostics": {"path": str(episode_path.relative_to(REPO_ROOT)), "sha256": sha256_file(episode_path)},
            "exposure_ledger": {"path": str(exposure_path.relative_to(REPO_ROOT)), "sha256": sha256_file(exposure_path)},
        },
        "episode_summaries": episode_results,
        "renderer_groups": group_results,
        "advisory_routing": {
            "episodes_meeting_geometry_threshold": geometry_episodes,
            "episodes_meeting_illumination_threshold": illumination_episodes,
            "episodes_meeting_operator_threshold": operator_episodes,
            "qualified_families": candidates,
            "single_separately_freezable_successor_family": successor,
            "diagnostic_not_intervention_authority": True,
        },
        "exposure_summary": {
            key: exposure[key]
            for key in (
                "recording_count",
                "or131_recording_count",
                "other_sibling_recording_count",
                "derived_frame_artifact_count",
                "complete",
                "resulting_claim",
                "untouched_cohort_remaining",
            )
        },
        "integrity_gates": integrity,
        "execution": {
            "existing_physical_video_decodes": 7,
            "physical_frames_read": physical_frame_reads,
            "existing_or131_candidate_video_decodes": 7,
            "candidate_frames_read": candidate_frame_reads,
            "existing_or132_occupancy_map_reads": 7,
            "instrumented_id_buffer_frame_renders": len(triangle_counts),
            "synthetic_renderer_equivalence_test_renders": equivalence["synthetic_render_count"],
            "positions_8_through_11_pixel_reads": 0,
            "sibling_pixel_reads": 0,
            "fits": 0,
            "candidate_selections": 0,
            "threshold_changes": 0,
            "retries": 0,
            "simulator_replays": 0,
            "hardware_actions": 0,
            "paid_compute": False,
            "unique_mesh_asset_reads": len(asset_receipts),
            "mean_instrumented_raster_seconds": float(np.mean(raster_seconds)),
            "elapsed_seconds": time.perf_counter() - started,
        },
        "compiled_libraries": {
            "or79": {"path": str(original_library.relative_to(REPO_ROOT)), "sha256": sha256_file(original_library), "compile_command": original_compile, "compiler_stderr": original_stderr},
            "or133a": {"path": str(id_library.relative_to(REPO_ROOT)), "sha256": sha256_file(id_library), "compile_command": id_compile, "compiler_stderr": id_stderr},
        },
        "claim_limits": contract["claim_limits"],
        "reviewer_decision": "FREEZE_SEPARATE_OR133B_FROM_IMMUTABLE_DIAGNOSTIC_RECEIPT" if status == contract["stop_conditions"]["complete"] else "FREEZE_DIAGNOSTIC_REPAIR_CARD",
        "next_transition": contract["stop_conditions"]["success_authorizes_only"] if status == contract["stop_conditions"]["complete"] else contract["stop_conditions"]["failure_authorizes_only"],
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(evaluate_once(), sort_keys=True))
