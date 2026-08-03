"""Identify one stable physical-only persistent enclosure boundary line family."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .learning_factory_artifacts import atomic_write_json, canonical_digest
from .observable_registration_board_anchored_workcell_se2_static_development_fit import _region_masks
from .observable_registration_host_native_analytic_3d_renderer_capability import REPO_ROOT, sha256_file
from .observable_registration_post_final_legacy_photo_background_ablation import _write_png


cv2.ocl.setUseOpenCL(False)
SCHEMA = "sim2claw.observable_registration_post_final_persistent_static_enclosure_boundary_line_identifiability_contract.v1"
DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_post_final_persistent_static_enclosure_boundary_line_identifiability_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_post_final_persistent_static_enclosure_boundary_line_identifiability_v1"


def load_post_final_persistent_static_enclosure_boundary_line_identifiability_contract(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    contract = json.loads(path.read_text())
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("unsupported OR114 contract")
    for source in contract["sources"].values():
        if sha256_file(REPO_ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['path']}")
    split = contract["split"]
    if split["development_positions"] != list(range(1, 8)) or split["validation_positions"] != list(range(8, 12)) or split["validation_never_changes_orientation_or_rho"] is not True:
        raise ValueError("OR114 split drifted")
    extractor = contract["line_extractor"]
    if extractor["orientation_bin_width_degrees"] != 10 or extractor["candidate_match_maximum_orientation_delta_degrees"] != 5 or extractor["candidate_match_maximum_midpoint_distance_px"] != 20:
        raise ValueError("OR114 line extractor drifted")
    resources = contract["resource_boundary"]
    if (
        resources["or97_occupancy_map_reads_allowed"] != 11
        or resources["source_video_decodes_allowed"] != 0
        or resources["candidate_video_decodes_allowed"] != 0
        or resources["renders_allowed"] != 0
        or resources["fits_or_candidate_searches_allowed"] != 0
        or resources["validation_refits_allowed"] != 0
        or resources["geometry_values_produced_allowed"] != 0
        or resources["paid_compute_allowed"] is not False
        or any(contract["authority"].values())
    ):
        raise ValueError("OR114 resource or authority boundary drifted")
    if contract["claim_limits"]["metric_3d_enclosure_geometry_calibrated"] is not False or contract["claim_limits"]["same_video_semantic_match"] is not False:
        raise ValueError("OR114 claim boundary drifted")
    return contract


def _angle_delta(left: float, right: float) -> float:
    delta = abs(float(left) - float(right)) % 180.0
    return min(delta, 180.0 - delta)


def _segment(x1: int, y1: int, x2: int, y2: int, bin_width: float) -> dict[str, Any]:
    dx, dy = float(x2 - x1), float(y2 - y1)
    length = float(np.hypot(dx, dy))
    angle = float(np.degrees(np.arctan2(dy, dx)) % 180.0)
    midpoint = np.asarray([(x1 + x2) * 0.5, (y1 + y2) * 0.5], dtype=np.float64)
    normal = np.asarray([-np.sin(np.deg2rad(angle)), np.cos(np.deg2rad(angle))], dtype=np.float64)
    return {
        "p0": [int(x1), int(y1)],
        "p1": [int(x2), int(y2)],
        "length_px": length,
        "angle_degrees": angle,
        "orientation_bin_degrees": float(np.floor(angle / bin_width) * bin_width),
        "midpoint_px": midpoint.tolist(),
        "rho_px": float(normal @ midpoint),
    }


def _extract_segments(panel: np.ndarray, mask: np.ndarray, spec: dict[str, Any]) -> list[dict[str, Any]]:
    image = np.where(mask, panel, 0).astype(np.uint8)
    lines = cv2.HoughLinesP(
        image,
        rho=float(spec["rho_resolution_px"]),
        theta=np.deg2rad(float(spec["theta_resolution_degrees"])),
        threshold=int(spec["vote_threshold"]),
        minLineLength=float(spec["minimum_line_length_px"]),
        maxLineGap=float(spec["maximum_line_gap_px"]),
    )
    if lines is None:
        return []
    return [
        _segment(int(values[0]), int(values[1]), int(values[2]), int(values[3]), float(spec["orientation_bin_width_degrees"]))
        for values in lines[:, 0, :]
    ]


def _unmatched_physical(physical: list[dict[str, Any]], candidate: list[dict[str, Any]], spec: dict[str, Any]) -> list[dict[str, Any]]:
    unmatched: list[dict[str, Any]] = []
    for segment in physical:
        midpoint = np.asarray(segment["midpoint_px"], dtype=np.float64)
        matched = any(
            _angle_delta(segment["angle_degrees"], other["angle_degrees"]) <= float(spec["candidate_match_maximum_orientation_delta_degrees"])
            and float(np.linalg.norm(midpoint - np.asarray(other["midpoint_px"], dtype=np.float64))) <= float(spec["candidate_match_maximum_midpoint_distance_px"])
            for other in candidate
        )
        if not matched:
            unmatched.append(segment)
    return unmatched


def evaluate_once(contract_path: Path = DEFAULT_CONTRACT, output_directory: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR114 one-run receipt already exists")
    contract = load_post_final_persistent_static_enclosure_boundary_line_identifiability_contract(contract_path)
    closeout = json.loads((REPO_ROOT / contract["sources"]["or113_closeout"]["path"]).read_text())
    if closeout["reviewer_decision"] != "FREEZE_PERSISTENT_STATIC_ENCLOSURE_BOUNDARY_LINE_IDENTIFIABILITY":
        raise ValueError("OR113 did not authorize enclosure boundary lines")
    or97 = json.loads((REPO_ROOT / contract["sources"]["or97_receipt"]["path"]).read_text())
    if or97["artifact_sha256"] != contract["sources"]["or97_receipt"]["artifact_sha256"]:
        raise ValueError("OR97 artifact identity drifted")
    panels = contract["occupancy_panels"]
    width, height = int(panels["panel_width_px"]), int(panels["panel_height_px"])
    _, outside = _region_masks(
        np.asarray(contract["region"]["board_points_px"], dtype=np.float64),
        width=width,
        height=height,
        dilation_kernel_px=int(contract["region"]["board_dilation_kernel_px"]),
    )
    x0, y0, x1, y1 = [int(value) for value in contract["region"]["background_roi_xyxy"]]
    roi = np.zeros((height, width), dtype=bool)
    roi[y0:y1, x0:x1] = True
    analysis_mask = roi & outside.astype(bool)
    spec = contract["line_extractor"]
    raw_rows: list[dict[str, Any]] = []
    map_images: dict[int, np.ndarray] = {}
    for source_row in sorted(or97["rows"], key=lambda row: int(row["split_position"])):
        position = int(source_row["split_position"])
        binding = source_row["occupancy_map"]
        path = REPO_ROOT / binding["path"]
        if sha256_file(path) != binding["sha256"]:
            raise ValueError("OR114 occupancy map hash mismatch")
        image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if image is None or image.shape != (height, 4 * width):
            raise ValueError("OR114 occupancy map dimensions drifted")
        map_images[position] = image
        physical_panel = image[:, int(panels["physical_persistent_panel_index"]) * width : (int(panels["physical_persistent_panel_index"]) + 1) * width]
        candidate_panel = image[:, int(panels["candidate_persistent_panel_index"]) * width : (int(panels["candidate_persistent_panel_index"]) + 1) * width]
        physical_segments = _extract_segments(physical_panel, analysis_mask, spec)
        candidate_segments = _extract_segments(candidate_panel, analysis_mask, spec)
        unmatched = _unmatched_physical(physical_segments, candidate_segments, spec)
        raw_rows.append({
            "split_position": position,
            "recording_id": source_row["recording_id"],
            "physical_segment_count": len(physical_segments),
            "candidate_segment_count": len(candidate_segments),
            "unmatched_physical_segment_count": len(unmatched),
            "physical_segments": physical_segments,
            "candidate_segments": candidate_segments,
            "unmatched_physical_segments": unmatched,
        })
    development_positions = set(int(value) for value in contract["split"]["development_positions"])
    development_unmatched = [segment for row in raw_rows if row["split_position"] in development_positions for segment in row["unmatched_physical_segments"]]
    bins = [float(value) for value in np.arange(0.0, 180.0, float(spec["orientation_bin_width_degrees"]))]
    bin_lengths = {bin_value: float(sum(segment["length_px"] for segment in development_unmatched if segment["orientation_bin_degrees"] == bin_value)) for bin_value in bins}
    selected_bin = max(bins, key=lambda value: (bin_lengths[value], -value))
    selected_development_all = [segment for segment in development_unmatched if segment["orientation_bin_degrees"] == selected_bin]
    if not selected_development_all:
        raise ValueError("OR114 no development boundary family selected")
    shared_angle = float(np.median([segment["angle_degrees"] for segment in selected_development_all]))
    shared_rho = float(np.median([segment["rho_px"] for segment in selected_development_all]))
    rho_tolerance = float(spec["selected_line_maximum_rho_delta_px"])

    def summarize(position_set: set[int]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for raw in raw_rows:
            if raw["split_position"] not in position_set:
                continue
            selected = [segment for segment in raw["unmatched_physical_segments"] if segment["orientation_bin_degrees"] == selected_bin and abs(float(segment["rho_px"]) - shared_rho) <= rho_tolerance]
            selected_length = float(sum(segment["length_px"] for segment in selected))
            all_unmatched_length = float(sum(segment["length_px"] for segment in raw["unmatched_physical_segments"]))
            rows.append({
                "split_position": raw["split_position"],
                "recording_id": raw["recording_id"],
                "selected_unmatched_segment_count": len(selected),
                "selected_unmatched_length_px": selected_length,
                "all_unmatched_length_px": all_unmatched_length,
                "selected_segments": selected,
            })
        summary = {
            "position_count": len(rows),
            "positions_with_selected_line_length_at_least_20px": sum(row["selected_unmatched_length_px"] >= 20.0 for row in rows),
            "mean_selected_unmatched_length_px": float(np.mean([row["selected_unmatched_length_px"] for row in rows])),
            "total_selected_unmatched_length_px": float(sum(row["selected_unmatched_length_px"] for row in rows)),
            "total_all_unmatched_length_px": float(sum(row["all_unmatched_length_px"] for row in rows)),
            "selected_share_of_all_unmatched_length": float(sum(row["selected_unmatched_length_px"] for row in rows) / max(sum(row["all_unmatched_length_px"] for row in rows), 1e-12)),
        }
        return rows, summary

    development_rows, development_summary = summarize(development_positions)
    validation_positions = set(int(value) for value in contract["split"]["validation_positions"])
    validation_rows, validation_summary = summarize(validation_positions)
    acceptance = contract["acceptance"]
    development_gates = {
        "minimum_positions_with_selected_line_length_at_least_20px": development_summary["positions_with_selected_line_length_at_least_20px"] >= int(acceptance["development_minimum_positions_with_selected_line_length_at_least_20px"]),
        "minimum_mean_selected_unmatched_length_px": development_summary["mean_selected_unmatched_length_px"] >= float(acceptance["development_minimum_mean_selected_unmatched_length_px"]),
        "minimum_selected_share_of_all_unmatched_length": development_summary["selected_share_of_all_unmatched_length"] >= float(acceptance["development_minimum_selected_share_of_all_unmatched_length"]),
    }
    validation_gates = {
        "minimum_positions_with_selected_line_length_at_least_20px": validation_summary["positions_with_selected_line_length_at_least_20px"] >= int(acceptance["validation_minimum_positions_with_selected_line_length_at_least_20px"]),
        "minimum_mean_selected_unmatched_length_px": validation_summary["mean_selected_unmatched_length_px"] >= float(acceptance["validation_minimum_mean_selected_unmatched_length_px"]),
        "minimum_total_physical_minus_candidate_matched_length_px": validation_summary["total_selected_unmatched_length_px"] >= float(acceptance["validation_minimum_total_physical_minus_candidate_matched_length_px"]),
    }
    integrity = {
        "exact_eleven_occupancy_maps_read": len(raw_rows) == int(panels["expected_map_count"]),
        "one_development_selected_orientation_bin": selected_bin in bins,
        "one_shared_angle_and_rho_frozen_before_validation": True,
        "zero_video_decode_render_fit_search_replay_geometry_value_hardware_or_paid_compute": True,
        "image_space_boundary_identifiability_not_3d_geometry_same_video_physics_transfer_or_promotion": True,
    }
    passed = all(development_gates.values()) and all(validation_gates.values()) and all(integrity.values())
    output_directory.mkdir(parents=True, exist_ok=True)
    visualization_rows: list[np.ndarray] = []
    selected_by_position = {row["split_position"]: row["selected_segments"] for row in development_rows + validation_rows}
    for raw in raw_rows:
        image = map_images[raw["split_position"]]
        physical = cv2.cvtColor(image[:, :width], cv2.COLOR_GRAY2BGR)
        overlay = physical.copy()
        for segment in raw["unmatched_physical_segments"]:
            cv2.line(overlay, tuple(segment["p0"]), tuple(segment["p1"]), (96, 96, 96), 1, cv2.LINE_AA)
        for segment in selected_by_position[raw["split_position"]]:
            cv2.line(overlay, tuple(segment["p0"]), tuple(segment["p1"]), (0, 0, 255), 2, cv2.LINE_AA)
        visualization_rows.append(np.concatenate([physical, overlay], axis=1))
    montage = {**_write_png(output_directory / "persistent_physical_boundary_line_family.png", np.concatenate(visualization_rows, axis=0)), "layout": "physical_persistent_left_unmatched_gray_selected_red_right"}
    receipt: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_post_final_persistent_static_enclosure_boundary_line_identifiability_receipt.v1",
        "experiment_id": contract["experiment_id"],
        "status": "PASS_PERSISTENT_STATIC_ENCLOSURE_BOUNDARY_LINE_IDENTIFIABLE" if passed else "TERMINAL_PERSISTENT_STATIC_ENCLOSURE_BOUNDARY_LINE_UNIDENTIFIABLE",
        "proof_class": contract["proof_class"],
        "contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)},
        "selected_line_family": {"orientation_bin_degrees": selected_bin, "shared_angle_degrees": shared_angle, "shared_rho_px": shared_rho, "rho_tolerance_px": rho_tolerance},
        "development_bin_total_unmatched_lengths_px": {str(int(key)): value for key, value in bin_lengths.items()},
        "development_rows": development_rows,
        "development_summary": development_summary,
        "validation_rows": validation_rows,
        "validation_summary": validation_summary,
        "montage": montage,
        "gates": {"development": development_gates, "validation": validation_gates, "integrity": integrity},
        "execution": {"or97_occupancy_map_reads": len(raw_rows), "source_video_decodes": 0, "candidate_video_decodes": 0, "renders": 0, "fits_or_candidate_searches": 0, "orientation_bins": len(bins), "shared_line_values": 2, "validation_refits": 0, "simulator_replays": 0, "geometry_values_produced": 0, "hardware_actions": 0, "paid_compute": False},
        "claim_limits": contract["claim_limits"],
        "reviewer_decision": "FREEZE_BOARD_RELATIVE_ENCLOSURE_PLANE_FAMILY_FROM_BOUNDARY_LINE" if passed else "RECONCILE_NONLINEAR_PERSISTENT_STATIC_RESIDUAL",
        "next_transition": "freeze_or115_board_relative_enclosure_plane_family_from_boundary_line" if passed else "freeze_or115_nonlinear_persistent_static_residual_reconciliation",
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(evaluate_once(), sort_keys=True))
