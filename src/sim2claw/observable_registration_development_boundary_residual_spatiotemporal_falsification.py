"""Falsify semantic ownership of OR133A's border-connected residual."""

from __future__ import annotations

import json
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
from .observable_registration_development_shared_camera_baseline import _decode_selected_frames
from .observable_registration_expanded_development_global_monotone_response_fit import apply_monotone_response
from .observable_registration_host_native_analytic_3d_renderer_capability import REPO_ROOT, sha256_file
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
from .observable_registration_post_final_static_dynamic_edge_occupancy_factorization import _read_video_frames
from .observable_registration_renderer_native_planar_fixture_static_comparison import _fixture_stream
from .observable_registration_renderer_native_regional_residual_attribution import (
    _compile_id_renderer,
    _native_rasterize_with_ids,
    _occupancy_panels,
    _shadow_image_direction,
    _triangle_group_ids,
)
from .observable_registration_renderer_native_two_planar_fixture_full_timeline_propagation import (
    _merged_or119_contract,
    load_two_planar_fixture_full_timeline_contract,
)
from .observable_registration_static_development_full_mesh_comparison import _load_unique_asset_cache


cv2.ocl.setUseOpenCL(False)

SCHEMA = "sim2claw.observable_registration_development_boundary_residual_spatiotemporal_falsification_contract.v1"
DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_development_boundary_residual_spatiotemporal_falsification_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_development_boundary_residual_spatiotemporal_falsification_v1"


def load_boundary_residual_falsification_contract(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    contract = json.loads(path.read_text())
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("unsupported OR133B contract")
    for binding in contract["sources"].values():
        if sha256_file(REPO_ROOT / binding["path"]) != binding["sha256"]:
            raise ValueError(f"OR133B source identity mismatch: {binding['path']}")
    for binding in contract["frozen_identities"].values():
        if sha256_file(REPO_ROOT / binding["path"]) != binding["sha256"]:
            raise ValueError(f"OR133B frozen identity mismatch: {binding['path']}")
    or133a = json.loads((REPO_ROOT / contract["sources"]["or133a_receipt"]["path"]).read_text())
    if (
        or133a["artifact_sha256"] != contract["sources"]["or133a_receipt"]["artifact_sha256"]
        or or133a["status"] != "PASS_RETROSPECTIVE_REGIONAL_ATTRIBUTION_COMPLETE"
    ):
        raise ValueError("OR133B OR133A prerequisite drifted")
    if or133a["advisory_routing"]["episodes_meeting_operator_threshold"] != 7:
        raise ValueError("OR133B OR133A measured-route binding drifted")
    if contract["semantic_correction"] != {
        "or133a_label_rejected": "operator_or_cable_like",
        "measured_class": "boundary_connected_nonshadow_residual",
        "reason": "touching_any_image_border_does_not_identify_entry_side_texture_topology_cable_or_actor",
        "may_authorize_intervention": False,
    }:
        raise ValueError("OR133B semantic correction drifted")
    development = contract["development_partition"]
    if development["split_positions"] != list(range(1, 8)):
        raise ValueError("OR133B development partition drifted")
    if len(development["episodes"]) != 7 or sum(row["frame_count"] for row in development["episodes"]) != 751:
        raise ValueError("OR133B frame budget drifted")
    association = contract["association_test"]
    if (
        association["lags_frames"] != list(range(-3, 4))
        or association["circular_shift_null_count"] != 40
        or association["minimum_circular_shift_frames"] != 25
        or association["minimum_qualifying_episode_count"] != 6
    ):
        raise ValueError("OR133B association protocol drifted")
    resources = contract["resource_boundary"]
    if resources != {
        "existing_physical_video_decodes_allowed": 7,
        "physical_frames_read_allowed": 751,
        "existing_or131_candidate_video_decodes_allowed": 7,
        "candidate_frames_read_allowed": 751,
        "existing_or132_occupancy_map_reads_allowed": 7,
        "physical_sample_files_read_allowed": 7,
        "instrumented_baseline_id_buffer_renders_allowed": 751,
        "candidate_intervention_renders_allowed": 0,
        "positions_8_through_11_pixel_reads_allowed": 0,
        "sibling_pixel_reads_allowed": 0,
        "renderer_or_intervention_dof_allowed": 0,
        "intervention_fits_allowed": 0,
        "candidate_selections_allowed": 0,
        "threshold_changes_allowed": 0,
        "retries_allowed": 0,
        "simulator_replays_allowed": 0,
        "hardware_actions_allowed": 0,
        "paid_compute_allowed": False,
    }:
        raise ValueError("OR133B resource boundary drifted")
    if any(contract["authority"].values()):
        raise ValueError("OR133B authority must remain closed")
    return contract


def _pearson(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 3 or float(np.std(x)) <= 1.0e-12 or float(np.std(y)) <= 1.0e-12:
        return 0.0
    return float(np.corrcoef(x, y)[0, 1])


def _lag_correlation(outcome: np.ndarray, signal: np.ndarray, lag: int) -> float:
    if lag > 0:
        return _pearson(outcome[lag:], signal[:-lag])
    if lag < 0:
        return _pearson(outcome[:lag], signal[-lag:])
    return _pearson(outcome, signal)


def _null_shifts(frame_count: int, count: int, minimum: int) -> list[int]:
    available = frame_count - 2 * minimum
    if available < count:
        raise ValueError("OR133B episode too short for frozen circular-shift null")
    shifts = [minimum + (index * available) // count for index in range(count)]
    if len(set(shifts)) != count or any(min(value, frame_count - value) < minimum for value in shifts):
        raise ValueError("OR133B circular shifts violate minimum displacement")
    return shifts


def _association(outcome: list[int], signal: list[float], contract: dict[str, Any]) -> dict[str, Any]:
    outcome_array = np.asarray(outcome, dtype=np.float64)
    signal_array = np.asarray(signal, dtype=np.float64)
    lags = [int(value) for value in contract["lags_frames"]]
    observed_by_lag = {str(lag): _lag_correlation(outcome_array, signal_array, lag) for lag in lags}
    best_lag = max(lags, key=lambda lag: (abs(observed_by_lag[str(lag)]), -abs(lag), -lag))
    observed = abs(observed_by_lag[str(best_lag)])
    shifts = _null_shifts(
        len(outcome),
        int(contract["circular_shift_null_count"]),
        int(contract["minimum_circular_shift_frames"]),
    )
    null_maxima = [
        max(abs(_lag_correlation(outcome_array, np.roll(signal_array, shift), lag)) for lag in lags)
        for shift in shifts
    ]
    null_threshold = float(np.quantile(null_maxima, float(contract["null_quantile"])))
    qualifies = observed >= float(contract["minimum_absolute_correlation"]) and observed > null_threshold
    return {
        "correlation_by_lag": observed_by_lag,
        "best_lag_frames": best_lag,
        "best_absolute_correlation": observed,
        "null_shifts_frames": shifts,
        "null_maximum_correlations": null_maxima,
        "null_quantile": float(contract["null_quantile"]),
        "null_threshold": null_threshold,
        "qualifies": bool(qualifies),
    }


def _nearest_sample_signals(
    sample_rows: list[dict[str, Any]],
    video_times: list[float],
) -> tuple[list[float], list[float]]:
    sample_times = np.asarray([float(row["overhead_video_time_seconds"]) for row in sample_rows])
    follower: list[float] = []
    leader: list[float] = []
    for value in video_times:
        if value < sample_times[0] or value > sample_times[-1]:
            follower.append(0.0)
            leader.append(0.0)
            continue
        index = int(np.argmin(np.abs(sample_times - value)))
        follower.append(float(np.linalg.norm(sample_rows[index]["follower_actual_velocity_degrees_s"])))
        leader.append(float(np.linalg.norm(sample_rows[index]["leader_relative_delta"])))
    return follower, leader


def _arm_distances(idbuffer: np.ndarray, left_id: int, right_id: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    distances: list[np.ndarray] = []
    combined = np.isin(idbuffer, [left_id, right_id])
    for group_id in (left_id, right_id):
        mask = idbuffer == group_id
        edge = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0
        distances.append(distance_transform_edt(~edge) if edge.any() else np.full(mask.shape, np.inf))
    return distances[0], distances[1], combined


def _stage_residuals(
    physical_frames: list[np.ndarray],
    candidate_frames: list[np.ndarray],
    idbuffers: list[np.ndarray],
    physical_persistent: np.ndarray,
    physical_dynamic: np.ndarray,
    outside_mask: np.ndarray,
    left_id: int,
    right_id: int,
    residual: dict[str, Any],
) -> tuple[list[dict[str, Any]], float, np.ndarray]:
    persistent_values = [
        cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)[physical_persistent]
        for frame in physical_frames
        if physical_persistent.any()
    ]
    baseline_luma = float(np.median(np.concatenate(persistent_values))) if persistent_values else 0.0
    kernel = np.ones(
        (int(residual["candidate_edge_tolerance_kernel_px"]),) * 2, dtype=np.uint8
    )
    shadow_direction = _shadow_image_direction(residual["camera"], residual["nominal_light_direction"])
    staged: list[dict[str, Any]] = []
    for physical, candidate, idbuffer in zip(physical_frames, candidate_frames, idbuffers, strict=True):
        physical_gray = cv2.cvtColor(physical, cv2.COLOR_BGR2GRAY)
        candidate_gray = cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY)
        physical_edge = cv2.Canny(
            physical_gray,
            int(residual["canny_low_threshold"]),
            int(residual["canny_high_threshold"]),
        ) > 0
        candidate_edge = cv2.Canny(
            candidate_gray,
            int(residual["canny_low_threshold"]),
            int(residual["canny_high_threshold"]),
        ) > 0
        matched = cv2.dilate(candidate_edge.astype(np.uint8), kernel) > 0
        unmatched = physical_edge & physical_dynamic & outside_mask & ~matched
        left_distance, right_distance, arm_mask = _arm_distances(idbuffer, left_id, right_id)
        arm_distance = np.minimum(left_distance, right_distance)
        silhouette = unmatched & (
            arm_distance < float(residual["arm_silhouette_distance_px_exclusive_max"])
        )
        rest = unmatched & ~silhouette
        potential_shadow = np.zeros_like(rest)
        offset: list[float] | None = None
        if arm_mask.any() and rest.any():
            arm_y, arm_x = np.nonzero(arm_mask)
            arm_centroid = np.asarray([arm_x.mean(), arm_y.mean()])
            yy, xx = np.nonzero(rest)
            relative = np.column_stack([xx, yy]) - arm_centroid
            selected = (
                (relative @ shadow_direction > 0.0)
                & (physical_gray[yy, xx] < baseline_luma)
                & (arm_distance[yy, xx] >= float(residual["shadow_distance_px_min"]))
            )
            potential_shadow[yy[selected], xx[selected]] = True
            if potential_shadow.any():
                py, px = np.nonzero(potential_shadow)
                offset = [float(px.mean() - arm_centroid[0]), float(py.mean() - arm_centroid[1])]
        staged.append(
            {
                "physical_gray": physical_gray,
                "rest": rest,
                "potential_shadow": potential_shadow,
                "offset": offset,
                "left_distance": left_distance,
                "right_distance": right_distance,
                "arm_mask": arm_mask,
            }
        )
    offsets = np.asarray([row["offset"] for row in staged if row["offset"] is not None], dtype=np.float64)
    median_offset = np.median(offsets, axis=0) if len(offsets) else np.asarray([np.nan, np.nan])
    for row in staged:
        stable = row["offset"] is not None and float(
            np.linalg.norm(np.asarray(row["offset"]) - median_offset)
        ) <= float(residual["shadow_offset_stability_px_max"])
        shadow = row["potential_shadow"] if stable else np.zeros_like(row["potential_shadow"])
        row["boundary_source"] = row["rest"] & ~shadow
    return staged, baseline_luma, shadow_direction


def _component_sides(mask: np.ndarray) -> list[str]:
    sides: list[str] = []
    if mask[0].any():
        sides.append("top")
    if mask[:, -1].any():
        sides.append("right")
    if mask[-1].any():
        sides.append("bottom")
    if mask[:, 0].any():
        sides.append("left")
    return sides


def _boundary_components(
    staged: list[dict[str, Any]],
    baseline_luma: float,
    shadow_direction: np.ndarray,
    tracking: dict[str, Any],
) -> tuple[list[list[dict[str, Any]]], list[int], dict[int, dict[str, int]]]:
    frames: list[list[dict[str, Any]]] = []
    mass_series: list[int] = []
    track_summary: dict[int, dict[str, int]] = {}
    prior: list[dict[str, Any]] = []
    next_track = 1
    kernel = np.ones(
        (int(tracking["adjacent_frame_overlap_dilation_kernel_px"]),) * 2, dtype=np.uint8
    )
    bands = [float(value) for value in tracking["robot_silhouette_distance_bands_px"]]
    for frame_index, row in enumerate(staged):
        count, labels, stats, centroids = cv2.connectedComponentsWithStats(
            row["boundary_source"].astype(np.uint8), connectivity=int(tracking["connectivity"])
        )
        current: list[dict[str, Any]] = []
        masks: list[np.ndarray] = []
        for label in range(1, count):
            mask = labels == label
            sides = _component_sides(mask)
            if not sides:
                continue
            yy, xx = np.nonzero(mask)
            left_values = row["left_distance"][mask]
            right_values = row["right_distance"][mask]
            minimum_distance = np.minimum(left_values, right_values)
            arm_y, arm_x = np.nonzero(row["arm_mask"])
            if len(arm_x):
                arm_centroid = np.asarray([arm_x.mean(), arm_y.mean()])
                relative = np.column_stack([xx, yy]) - arm_centroid
                shadow_side_fraction = float(np.mean(relative @ shadow_direction > 0.0))
            else:
                shadow_side_fraction = 0.0
            current.append(
                {
                    "frame_index": frame_index,
                    "component_index": len(current),
                    "border_sides": sides,
                    "border_side_bitmask_top_right_bottom_left": sum(
                        1 << tracking["border_side_order"].index(side) for side in sides
                    ),
                    "size_pixels": int(stats[label, cv2.CC_STAT_AREA]),
                    "bbox_xywh": [int(value) for value in stats[label, :4]],
                    "centroid_xy": [float(value) for value in centroids[label]],
                    "median_distance_to_left_robot_silhouette_px": float(np.median(left_values)),
                    "median_distance_to_right_robot_silhouette_px": float(np.median(right_values)),
                    "distance_band_pixels": {
                        "lt_5": int((minimum_distance < bands[1]).sum()),
                        "5_to_lt_15": int(((minimum_distance >= bands[1]) & (minimum_distance < bands[2])).sum()),
                        "ge_15": int((minimum_distance >= bands[2]).sum()),
                    },
                    "shadow_side_fraction": shadow_side_fraction,
                    "dark_below_episode_persistent_baseline_fraction": float(
                        np.mean(row["physical_gray"][mask] < baseline_luma)
                    ),
                }
            )
            masks.append(mask)
        candidates: list[tuple[int, int, int]] = []
        for current_index, mask in enumerate(masks):
            for prior_index, previous in enumerate(prior):
                overlap = int(
                    (
                        mask
                        & (cv2.dilate(previous["mask"].astype(np.uint8), kernel) > 0)
                    ).sum()
                )
                if overlap:
                    candidates.append((-overlap, int(previous["track_id"]), current_index, prior_index))
        assigned_current: set[int] = set()
        assigned_prior: set[int] = set()
        for _, track_id, current_index, prior_index in sorted(candidates):
            if current_index in assigned_current or prior_index in assigned_prior:
                continue
            current[current_index]["track_id"] = track_id
            assigned_current.add(current_index)
            assigned_prior.add(prior_index)
        for index, component in enumerate(current):
            if index not in assigned_current:
                component["track_id"] = next_track
                next_track += 1
            track = track_summary.setdefault(int(component["track_id"]), {"frame_count": 0, "mass_pixels": 0})
            track["frame_count"] += 1
            track["mass_pixels"] += int(component["size_pixels"])
        mass_series.append(sum(int(component["size_pixels"]) for component in current))
        frames.append(current)
        prior = [
            {"mask": mask, "track_id": int(component["track_id"])}
            for mask, component in zip(masks, current, strict=True)
        ]
    return frames, mass_series, track_summary


def _write_montage(
    path: Path,
    physical_frames: list[np.ndarray],
    candidate_frames: list[np.ndarray],
    staged: list[dict[str, Any]],
    slots: list[float],
) -> dict[str, Any]:
    indices = [int(np.rint((len(physical_frames) - 1) * float(slot))) for slot in slots]
    rows: list[np.ndarray] = []
    for index in indices:
        residual = np.repeat((staged[index]["boundary_source"].astype(np.uint8) * 255)[:, :, None], 3, axis=2)
        rows.append(np.concatenate([physical_frames[index], candidate_frames[index], residual], axis=1))
    montage = np.concatenate(rows, axis=0)
    ok, encoded = cv2.imencode(".png", montage, [cv2.IMWRITE_PNG_COMPRESSION, 9])
    if not ok:
        raise RuntimeError("OR133B montage encoding failed")
    path.write_bytes(encoded.tobytes())
    return {
        "path": str(path.relative_to(REPO_ROOT)),
        "sha256": sha256_file(path),
        "layout": "rows_are_fixed_normalized_slots_columns_are_physical_or131_boundary_connected_nonshadow",
        "evaluation_indices": indices,
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def evaluate_once(
    contract_path: Path = DEFAULT_CONTRACT,
    output_directory: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR133B one-run receipt already exists; retry prohibited")
    contract = load_boundary_residual_falsification_contract(contract_path)
    started = time.perf_counter()
    output_directory.mkdir(parents=True, exist_ok=True)

    or133a_contract = json.loads((REPO_ROOT / contract["sources"]["or133a_contract"]["path"]).read_text())
    or133a_receipt = json.loads((REPO_ROOT / contract["sources"]["or133a_receipt"]["path"]).read_text())
    or131_contract = load_two_planar_fixture_full_timeline_contract(
        REPO_ROOT / contract["sources"]["or131_contract"]["path"]
    )
    merged = _merged_or119_contract(or131_contract)
    or95_contract = load_post_final_independent_robot_base_full_corpus_diagnostic_contract(
        REPO_ROOT / contract["sources"]["or95_contract"]["path"]
    )
    or116_contract = load_post_final_renderer_native_finite_linear_workcell_object_reconstruction_contract(
        REPO_ROOT / merged["sources"]["or116_contract"]["path"]
    )
    or118 = json.loads((REPO_ROOT / merged["sources"]["or118_receipt"]["path"]).read_text())
    or131_receipt = json.loads((REPO_ROOT / contract["sources"]["or131_receipt"]["path"]).read_text())
    or131_rows = json.loads((REPO_ROOT / contract["sources"]["or131_frame_rows"]["path"]).read_text())["rows"]
    or132_receipt = json.loads((REPO_ROOT / contract["sources"]["or132_receipt"]["path"]).read_text())
    pairing = json.loads((REPO_ROOT / contract["sources"]["pairing_inventory"]["path"]).read_text())
    pairs = {int(row["split_position"]): row for row in pairing["pairs"]}
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
        frozen["left_robot_transform"]["vector"] + frozen["right_robot_transform"]["vector"], dtype=np.float64
    )
    meshes, asset_receipts = _load_unique_asset_cache(
        scene, REPO_ROOT / merged["sources"]["mesh_asset_root"]["path"]
    )
    id_library, compile_command, compiler_stderr = _compile_id_renderer(output_directory)
    base_group_ids, group_numbers = _triangle_group_ids(
        scene, meshes, renderer, or133a_contract["renderer_group_ids"]
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
    shaft = np.asarray(merged["frozen_object"]["shaft_pre_response_bgr"], np.uint8)
    terminal = np.asarray(merged["frozen_object"]["terminal_pre_response_bgr"], np.uint8)
    object_colors = np.ascontiguousarray(
        np.concatenate([np.tile(shaft, (248, 1)), np.tile(terminal, (100, 1))])
    )
    object_group_ids = np.full(348, group_numbers["or116_finite_linear_object"], np.uint16)

    episodes = {int(row["split_position"]): row for row in _episode_inventory(or95_contract)}
    expected = {int(row["split_position"]): row for row in contract["development_partition"]["episodes"]}
    video_map = {row["recording_id"]: row for row in or131_receipt["candidate_videos"]}
    occupancy_map = {int(row["split_position"]): row for row in or132_receipt["rows"]}
    prior_dynamic = {int(row["split_position"]): row["dynamic_attribution"] for row in or133a_receipt["episode_summaries"]}
    rows_by_position = {position: [] for position in expected}
    for row in or131_rows:
        position = int(row["split_position"])
        if position in rows_by_position:
            rows_by_position[position].append(row)
    for rows in rows_by_position.values():
        rows.sort(key=lambda row: int(row["evaluation_index"]))
    _, outside_mask = _region_masks(
        np.asarray(merged["regions"]["board_plus_margin"]["points_px"], np.float64),
        width=320,
        height=240,
        dilation_kernel_px=int(merged["regions"]["board_plus_margin"]["dilation_kernel_px_at_320x240"]),
    )

    episode_results: list[dict[str, Any]] = []
    triangle_counts: list[int] = []
    raster_seconds: list[float] = []
    visible_ids_valid = True
    boundary_reproduction = True
    association_null_counts_exact = True
    for position in range(1, 8):
        declaration = expected[position]
        episode = episodes[position]
        pair = pairs[position]
        if episode["recording_id"] != declaration["recording_id"] or pair["recording_id"] != declaration["recording_id"]:
            raise ValueError("OR133B episode identity drifted")
        rows = rows_by_position[position]
        if len(rows) != int(declaration["frame_count"]):
            raise ValueError("OR133B frame count drifted")
        physical_binding = episode["physical_video"]
        physical_frames = [
            cv2.flip(frame, -1)
            for frame in _decode_selected_frames(
                REPO_ROOT / physical_binding["path"],
                selected_indices=np.asarray([int(row["physical_frame_index"]) for row in rows], np.int64),
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
            raise ValueError("OR133B OR131 video drifted")
        candidate_frames = _read_video_frames(candidate_path, len(rows))
        physical_persistent, _, physical_dynamic, _ = _occupancy_panels(
            occupancy_map[position]["occupancy_map"]
        )
        physical_persistent &= outside_mask
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
        object_pixels, object_depths, _, _ = _primitive_triangle_stream(
            or118["frozen_shape"],
            initial_registered,
            scene,
            camera,
            renderer,
            static_family,
            static_vector,
            or116_contract["support_plane"],
            np.asarray([0, 0, 0], np.uint8),
        )
        idbuffers: list[np.ndarray] = []
        fresh_vs_video: list[float] = []
        for row, candidate in zip(rows, candidate_frames, strict=True):
            one = {
                "body_names": trace["body_names"],
                "frames": [trace["frames"][int(row["state_trace_frame_index"])]],
            }
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
                raise ValueError("OR133B base triangle count drifted")
            pixels = np.ascontiguousarray(np.concatenate([pixels, object_pixels, fixture_pixels]))
            depths = np.ascontiguousarray(np.concatenate([depths, object_depths, fixture_depths]))
            colors = np.ascontiguousarray(np.concatenate([colors, object_colors, fixture_colors]))
            triangle_ids = np.ascontiguousarray(
                np.concatenate([base_group_ids, object_group_ids, fixture_ids]), dtype=np.uint16
            )
            simulator, idbuffer, _, _, elapsed = _native_rasterize_with_ids(
                id_library, pixels, depths, colors, triangle_ids, renderer
            )
            rendered = apply_monotone_response(
                simulator,
                bias=float(response["bias"]),
                low_slope=float(response["low_intensity_slope"]),
                high_slope=float(response["high_intensity_slope"]),
                knot=int(response["fixed_input_knot"]),
            )
            fresh_vs_video.append(float(1.0 - np.abs(rendered.astype(np.float64) - candidate).mean() / 255.0))
            idbuffers.append(idbuffer)
            triangle_counts.append(len(pixels))
            raster_seconds.append(elapsed)
            visible_ids_valid = visible_ids_valid and set(int(value) for value in np.unique(idbuffer) if value).issubset(
                set(group_numbers.values())
            )

        residual_contract = dict(contract["residual_reproduction"])
        residual_contract["camera"] = camera
        staged, baseline_luma, shadow_direction = _stage_residuals(
            physical_frames,
            candidate_frames,
            idbuffers,
            physical_persistent,
            physical_dynamic,
            outside_mask,
            group_numbers["left_robot"],
            group_numbers["right_robot"],
            residual_contract,
        )
        components, mass_series, tracks = _boundary_components(
            staged, baseline_luma, shadow_direction, contract["component_tracking"]
        )
        boundary_total = sum(mass_series)
        expected_boundary = int(declaration["or133a_boundary_pixel_count"])
        boundary_reproduction = boundary_reproduction and boundary_total == expected_boundary
        if boundary_total != int(prior_dynamic[position]["mass_pixels"]["operator_or_cable_like"]):
            raise ValueError("OR133B exact OR133A boundary count reproduction failed")
        sample_binding = pair["physical_samples"]
        sample_path = REPO_ROOT / sample_binding["path"]
        if sha256_file(sample_path) != sample_binding["sha256"]:
            raise ValueError("OR133B physical sample hash drifted")
        samples = _read_jsonl(sample_path)
        video_times = [
            int(row["physical_frame_index"]) * float(physical_binding["duration_seconds"])
            / (int(physical_binding["frame_count"]) - 1)
            for row in rows
        ]
        follower_signal, leader_signal = _nearest_sample_signals(samples, video_times)
        follower = _association(mass_series, follower_signal, contract["association_test"])
        leader = _association(mass_series, leader_signal, contract["association_test"])
        association_null_counts_exact = association_null_counts_exact and (
            len(follower["null_shifts_frames"]) == len(leader["null_shifts_frames"]) == 40
        )
        coherent_minimum = int(contract["component_tracking"]["minimum_coherent_track_frames"])
        coherent_mass = sum(track["mass_pixels"] for track in tracks.values() if track["frame_count"] >= coherent_minimum)
        side_mass = {side: 0 for side in contract["component_tracking"]["border_side_order"]}
        distance_mass = {"lt_5": 0, "5_to_lt_15": 0, "ge_15": 0}
        for frame in components:
            for component in frame:
                for side in component["border_sides"]:
                    side_mass[side] += int(component["size_pixels"])
                for key, value in component["distance_band_pixels"].items():
                    distance_mass[key] += int(value)
        montage = _write_montage(
            output_directory / f"{episode['recording_id']}-fixed-slots.png",
            physical_frames,
            candidate_frames,
            staged,
            contract["component_tracking"]["montage_normalized_slots"],
        )
        component_path = output_directory / f"{episode['recording_id']}-components.json"
        atomic_write_json(
            component_path,
            {
                "schema_version": "sim2claw.observable_registration_boundary_residual_components.v1",
                "recording_id": episode["recording_id"],
                "frames": components,
                "tracks": {str(key): value for key, value in tracks.items()},
            },
        )
        episode_results.append(
            {
                "split_position": position,
                "recording_id": episode["recording_id"],
                "frame_count": len(rows),
                "boundary_connected_nonshadow_residual_pixels": boundary_total,
                "exact_or133a_boundary_count_reproduced": boundary_total == expected_boundary,
                "side_mass_pixels_nonexclusive_at_corners": side_mass,
                "robot_distance_band_mass_pixels": distance_mass,
                "coherent_track_coverage": coherent_mass / max(boundary_total, 1),
                "track_count": len(tracks),
                "coherent_track_count": sum(track["frame_count"] >= coherent_minimum for track in tracks.values()),
                "follower_speed_association": follower,
                "leader_innovation_association": leader,
                "fresh_render_vs_lossy_or131_video_mean_linear_similarity": float(np.mean(fresh_vs_video)),
                "montage": montage,
                "component_ledger": {
                    "path": str(component_path.relative_to(REPO_ROOT)),
                    "sha256": sha256_file(component_path),
                },
            }
        )

    follower_episodes = sum(row["follower_speed_association"]["qualifies"] for row in episode_results)
    leader_episodes = sum(row["leader_innovation_association"]["qualifies"] for row in episode_results)
    minimum = int(contract["association_test"]["minimum_qualifying_episode_count"])
    follower_pass = follower_episodes >= minimum
    leader_pass = leader_episodes >= minimum
    if follower_pass and leader_pass:
        status = contract["stop_conditions"]["both"]
    elif follower_pass:
        status = contract["stop_conditions"]["follower_only"]
    elif leader_pass:
        status = contract["stop_conditions"]["leader_only"]
    else:
        status = contract["stop_conditions"]["neither"]
    expected_triangles = int(contract["residual_reproduction"]["expected_triangle_count_per_frame"])
    integrity = {
        "all_source_identities_match": True,
        "or133a_instrumented_renderer_equivalence_inherited_by_exact_source_hash": bool(
            or133a_receipt["renderer_equivalence"]["rgb_byte_equal"]
        ),
        "exact_development_episode_count": len(episode_results) == 7,
        "exact_development_frame_count": sum(row["frame_count"] for row in episode_results) == 751,
        "triangle_count_exact_every_frame": len(triangle_counts) == 751
        and all(value == expected_triangles for value in triangle_counts),
        "visible_group_ids_valid": visible_ids_valid,
        "exact_or133a_boundary_mass_reproduced": boundary_reproduction,
        "association_null_counts_exact": association_null_counts_exact,
        "zero_intervention_dof_fit_selection_threshold_change_retry": True,
        "closed_partitions_remain_unopened": True,
    }
    if not all(integrity.values()):
        status = contract["stop_conditions"]["instrumentation_failure"]
    details_path = output_directory / "episode_diagnostics.json"
    atomic_write_json(
        details_path,
        {
            "schema_version": "sim2claw.observable_registration_boundary_residual_spatiotemporal_falsification_diagnostics.v1",
            "episodes": episode_results,
        },
    )
    positive = status in {
        contract["stop_conditions"]["follower_only"],
        contract["stop_conditions"]["leader_only"],
    }
    receipt: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_development_boundary_residual_spatiotemporal_falsification_receipt.v1",
        "experiment_id": contract["experiment_id"],
        "status": status,
        "proof_class": contract["proof_class"],
        "contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)},
        "semantic_correction": contract["semantic_correction"],
        "episode_summaries": episode_results,
        "summary": {
            "episodes_qualifying_follower_speed_association": follower_episodes,
            "episodes_qualifying_leader_innovation_association": leader_episodes,
            "required_episode_count": minimum,
            "mean_coherent_track_coverage": float(np.mean([row["coherent_track_coverage"] for row in episode_results])),
            "total_boundary_connected_nonshadow_residual_pixels": sum(
                row["boundary_connected_nonshadow_residual_pixels"] for row in episode_results
            ),
        },
        "diagnostic_output": {"path": str(details_path.relative_to(REPO_ROOT)), "sha256": sha256_file(details_path)},
        "integrity_gates": integrity,
        "execution": {
            "existing_physical_video_decodes": 7,
            "physical_frames_read": 751,
            "existing_or131_candidate_video_decodes": 7,
            "candidate_frames_read": 751,
            "existing_or132_occupancy_map_reads": 7,
            "physical_sample_files_read": 7,
            "instrumented_baseline_id_buffer_renders": len(triangle_counts),
            "candidate_intervention_renders": 0,
            "positions_8_through_11_pixel_reads": 0,
            "sibling_pixel_reads": 0,
            "renderer_or_intervention_dof": 0,
            "intervention_fits": 0,
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
        "compiled_library": {
            "path": str(id_library.relative_to(REPO_ROOT)),
            "sha256": sha256_file(id_library),
            "compile_command": compile_command,
            "compiler_stderr": compiler_stderr,
        },
        "claim_limits": contract["claim_limits"],
        "reviewer_decision": (
            "FREEZE_NARROWER_FACTOR_SPECIFIC_DIAGNOSTIC_NO_RENDERER_CHANGE"
            if positive
            else "CLOSE_RETAINED_EVIDENCE_REGIONAL_IDENTIFIABILITY_LANE"
        ),
        "next_transition": (
            contract["stop_conditions"]["positive_branch_authorizes_only"]
            if positive
            else contract["stop_conditions"]["terminal_branch_authorizes_only"]
        ),
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(evaluate_once(), sort_keys=True))
