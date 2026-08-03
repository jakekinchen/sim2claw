"""Attribute the OR114 line as a finite workcell object or a scene boundary."""

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
SCHEMA = "sim2claw.observable_registration_post_final_persistent_linear_workcell_object_attribution_contract.v1"
DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_post_final_persistent_linear_workcell_object_attribution_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_post_final_persistent_linear_workcell_object_attribution_v1"


def load_post_final_persistent_linear_workcell_object_attribution_contract(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    contract = json.loads(path.read_text())
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("unsupported OR115 contract")
    for source in contract["sources"].values():
        if sha256_file(REPO_ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['path']}")
    split = contract["split"]
    if split["development_positions"] != list(range(1, 8)) or split["validation_positions"] != list(range(8, 12)) or split["validation_never_changes_component_or_classification_rules"] is not True:
        raise ValueError("OR115 split drifted")
    extractor = contract["topology_extractor"]
    if (
        extractor["component_selector"] != "maximum_seed_intersection_then_lowest_label"
        or extractor["selected_segment_seed_thickness_px"] != 5
        or extractor["minimum_axial_span_px"] != 60
        or extractor["minimum_axial_to_transverse_span_ratio"] != 3.0
    ):
        raise ValueError("OR115 topology rule drifted")
    resources = contract["resource_boundary"]
    if (
        resources["or97_occupancy_map_reads_allowed"] != 11
        or resources["or114_receipt_reads_allowed"] != 1
        or resources["source_video_decodes_allowed"] != 0
        or resources["candidate_video_decodes_allowed"] != 0
        or resources["renders_allowed"] != 0
        or resources["fits_or_candidate_searches_allowed"] != 0
        or resources["validation_refits_allowed"] != 0
        or resources["simulator_replays_allowed"] != 0
        or resources["metric_3d_geometry_values_produced_allowed"] != 0
        or resources["paid_compute_allowed"] is not False
        or any(contract["authority"].values())
    ):
        raise ValueError("OR115 resource or authority boundary drifted")
    if contract["claim_limits"]["specific_object_identity_known"] is not False or contract["claim_limits"]["same_video_semantic_match"] is not False:
        raise ValueError("OR115 claim boundary drifted")
    return contract


def _component_metrics(
    panel: np.ndarray,
    analysis_mask: np.ndarray,
    segments: list[dict[str, Any]],
    shared_angle_degrees: float,
    roi_xyxy: list[int],
    spec: dict[str, Any],
) -> tuple[dict[str, Any], np.ndarray, np.ndarray]:
    binary = ((panel > int(spec["binary_threshold"])) & analysis_mask).astype(np.uint8)
    close_kernel = np.ones((int(spec["closing_kernel_px"]), int(spec["closing_kernel_px"])), dtype=np.uint8)
    dilate_kernel = np.ones((int(spec["dilation_kernel_px"]), int(spec["dilation_kernel_px"])), dtype=np.uint8)
    connected = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, close_kernel, iterations=int(spec["closing_iterations"]))
    connected = cv2.dilate(connected, dilate_kernel, iterations=int(spec["dilation_iterations"]))
    connected = (connected.astype(bool) & analysis_mask).astype(np.uint8)
    seed = np.zeros_like(binary)
    for segment in segments:
        cv2.line(seed, tuple(segment["p0"]), tuple(segment["p1"]), 1, int(spec["selected_segment_seed_thickness_px"]), cv2.LINE_8)
    seed = (seed.astype(bool) & analysis_mask).astype(np.uint8)
    label_count, labels, _, _ = cv2.connectedComponentsWithStats(connected, connectivity=8)
    intersections = [(int(np.count_nonzero((labels == label) & (seed > 0))), label) for label in range(1, label_count)]
    maximum_intersection = max((value for value, _ in intersections), default=0)
    selected_labels = [label for value, label in intersections if value == maximum_intersection and value > 0]
    if not selected_labels:
        empty = np.zeros_like(binary, dtype=bool)
        return {
            "supported": bool(segments),
            "selected_component_found": False,
            "classification": "unresolved",
            "seed_overlap_fraction": 0.0,
            "component_area_px": 0,
            "axial_span_px": 0.0,
            "transverse_span_px": 0.0,
            "axial_to_transverse_span_ratio": 0.0,
            "minimum_roi_boundary_margin_px": 0.0,
            "hole_count": 0,
        }, empty, seed.astype(bool)
    selected_label = min(selected_labels)
    component = labels == selected_label
    ys, xs = np.nonzero(component)
    radians = np.deg2rad(float(shared_angle_degrees))
    direction = np.asarray([np.cos(radians), np.sin(radians)], dtype=np.float64)
    normal = np.asarray([-direction[1], direction[0]], dtype=np.float64)
    points = np.stack([xs, ys], axis=1).astype(np.float64)
    axial = points @ direction
    transverse = points @ normal
    axial_span = float(np.ptp(axial)) if axial.size else 0.0
    transverse_span = float(np.ptp(transverse)) if transverse.size else 0.0
    elongation = float(axial_span / max(transverse_span, 1.0))
    x0, y0, x1, y1 = [int(value) for value in roi_xyxy]
    roi_margin = float(min(np.min(xs - x0), np.min((x1 - 1) - xs), np.min(ys - y0), np.min((y1 - 1) - ys)))
    seed_pixels = int(np.count_nonzero(seed))
    overlap_fraction = float(np.count_nonzero(component & (seed > 0)) / max(seed_pixels, 1))
    crop = component[int(np.min(ys)) : int(np.max(ys)) + 1, int(np.min(xs)) : int(np.max(xs)) + 1].astype(np.uint8)
    contours, hierarchy = cv2.findContours(crop, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    hole_count = 0
    if hierarchy is not None:
        for index, contour in enumerate(contours):
            if int(hierarchy[0][index][3]) >= 0 and cv2.contourArea(contour) >= float(spec["minimum_hole_area_px"]):
                hole_count += 1
    overlap_pass = overlap_fraction >= float(spec["minimum_selected_seed_overlap_fraction"])
    area_pass = int(np.count_nonzero(component)) >= int(spec["minimum_component_area_px"])
    span_pass = axial_span >= float(spec["minimum_axial_span_px"])
    elongation_pass = elongation >= float(spec["minimum_axial_to_transverse_span_ratio"])
    finite_margin_pass = roi_margin >= float(spec["finite_minimum_roi_boundary_margin_px"])
    boundary_touch = roi_margin <= float(spec["roi_boundary_touch_margin_px"])
    if overlap_pass and area_pass and span_pass and elongation_pass and finite_margin_pass:
        classification = "finite_linear_workcell_object"
    elif overlap_pass and span_pass and boundary_touch:
        classification = "scene_boundary"
    else:
        classification = "unresolved"
    return {
        "supported": bool(segments),
        "selected_component_found": True,
        "classification": classification,
        "seed_overlap_fraction": overlap_fraction,
        "component_area_px": int(np.count_nonzero(component)),
        "axial_span_px": axial_span,
        "transverse_span_px": transverse_span,
        "axial_to_transverse_span_ratio": elongation,
        "minimum_roi_boundary_margin_px": roi_margin,
        "touches_roi_boundary": boundary_touch,
        "hole_count": hole_count,
    }, component, seed.astype(bool)


def evaluate_once(contract_path: Path = DEFAULT_CONTRACT, output_directory: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR115 one-run receipt already exists")
    contract = load_post_final_persistent_linear_workcell_object_attribution_contract(contract_path)
    closeout = json.loads((REPO_ROOT / contract["sources"]["or114_closeout"]["path"]).read_text())
    if closeout["reviewer_decision"] != "REJECT_ENCLOSURE_PLANE_SEMANTIC_AND_FREEZE_PERSISTENT_LINEAR_WORKCELL_OBJECT_ATTRIBUTION":
        raise ValueError("OR114 did not authorize finite-object attribution")
    or114 = json.loads((REPO_ROOT / contract["sources"]["or114_receipt"]["path"]).read_text())
    or97 = json.loads((REPO_ROOT / contract["sources"]["or97_receipt"]["path"]).read_text())
    if or114["artifact_sha256"] != contract["sources"]["or114_receipt"]["artifact_sha256"] or or97["artifact_sha256"] != contract["sources"]["or97_receipt"]["artifact_sha256"]:
        raise ValueError("OR114 or OR97 artifact identity drifted")
    selected_family = or114["selected_line_family"]
    selected_rows = {int(row["split_position"]): row for row in or114["development_rows"] + or114["validation_rows"]}
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
    raw_rows: list[dict[str, Any]] = []
    visualization_rows: list[np.ndarray] = []
    for source_row in sorted(or97["rows"], key=lambda row: int(row["split_position"])):
        position = int(source_row["split_position"])
        binding = source_row["occupancy_map"]
        path = REPO_ROOT / binding["path"]
        if sha256_file(path) != binding["sha256"]:
            raise ValueError("OR115 occupancy map hash mismatch")
        image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if image is None or image.shape != (height, 4 * width):
            raise ValueError("OR115 occupancy map dimensions drifted")
        panel_index = int(panels["physical_persistent_panel_index"])
        physical = image[:, panel_index * width : (panel_index + 1) * width]
        segments = list(selected_rows[position]["selected_segments"])
        metrics, component, seed = _component_metrics(
            physical,
            analysis_mask,
            segments,
            float(selected_family["shared_angle_degrees"]),
            contract["region"]["background_roi_xyxy"],
            contract["topology_extractor"],
        )
        row = {"split_position": position, "recording_id": source_row["recording_id"], "selected_segment_count": len(segments), **metrics}
        raw_rows.append(row)
        overlay = cv2.cvtColor(physical, cv2.COLOR_GRAY2BGR)
        overlay[component] = (0, 255, 0)
        overlay[seed] = (0, 0, 255)
        visualization_rows.append(np.concatenate([cv2.cvtColor(physical, cv2.COLOR_GRAY2BGR), overlay], axis=1))

    development_positions = set(int(value) for value in contract["split"]["development_positions"])
    validation_positions = set(int(value) for value in contract["split"]["validation_positions"])

    def summarize(position_set: set[int]) -> dict[str, Any]:
        rows = [row for row in raw_rows if row["split_position"] in position_set]
        supported = [row for row in rows if row["supported"]]
        finite = [row for row in supported if row["classification"] == "finite_linear_workcell_object"]
        boundary = [row for row in supported if row["classification"] == "scene_boundary"]
        return {
            "position_count": len(rows),
            "supported_row_count": len(supported),
            "finite_object_row_count": len(finite),
            "finite_object_fraction_of_supported_rows": float(len(finite) / max(len(supported), 1)),
            "scene_boundary_row_count": len(boundary),
            "scene_boundary_fraction_of_supported_rows": float(len(boundary) / max(len(supported), 1)),
            "unresolved_supported_row_count": len(supported) - len(finite) - len(boundary),
        }

    development = summarize(development_positions)
    validation = summarize(validation_positions)
    acceptance = contract["acceptance"]
    finite_gates = {
        "development_minimum_finite_object_rows": development["finite_object_row_count"] >= int(acceptance["development_minimum_finite_object_rows"]),
        "development_minimum_finite_object_fraction": development["finite_object_fraction_of_supported_rows"] >= float(acceptance["development_minimum_finite_object_fraction_of_supported_rows"]),
        "validation_minimum_finite_object_rows": validation["finite_object_row_count"] >= int(acceptance["validation_minimum_finite_object_rows"]),
        "validation_minimum_finite_object_fraction": validation["finite_object_fraction_of_supported_rows"] >= float(acceptance["validation_minimum_finite_object_fraction_of_supported_rows"]),
    }
    boundary_gates = {
        "development_minimum_scene_boundary_rows": development["scene_boundary_row_count"] >= int(acceptance["development_minimum_scene_boundary_rows"]),
        "validation_minimum_scene_boundary_rows": validation["scene_boundary_row_count"] >= int(acceptance["validation_minimum_scene_boundary_rows"]),
    }
    finite_pass = all(finite_gates.values())
    boundary_pass = all(boundary_gates.values())
    if finite_pass and not boundary_pass:
        status = "PASS_PERSISTENT_FINITE_LINEAR_WORKCELL_OBJECT_ATTRIBUTED"
        reviewer_decision = "FREEZE_RENDERER_NATIVE_FINITE_LINEAR_WORKCELL_OBJECT_PRIMITIVE_FAMILY"
        next_transition = "freeze_or116_renderer_native_finite_linear_workcell_object_primitive_family"
    elif boundary_pass and not finite_pass:
        status = "PASS_PERSISTENT_SCENE_BOUNDARY_ATTRIBUTED"
        reviewer_decision = "FREEZE_RENDERER_NATIVE_SCENE_BOUNDARY_PRIMITIVE_FAMILY"
        next_transition = "freeze_or116_renderer_native_scene_boundary_primitive_family"
    else:
        status = "TERMINAL_PERSISTENT_LINEAR_WORKCELL_OBJECT_ATTRIBUTION_UNRESOLVED"
        reviewer_decision = "RECONCILE_PERSISTENT_STATIC_NONLINEAR_TOPOLOGY"
        next_transition = "freeze_or116_persistent_static_nonlinear_topology_reconciliation"
    integrity = {
        "exact_eleven_occupancy_maps_read": len(raw_rows) == int(panels["expected_map_count"]),
        "or114_selected_segments_and_shared_angle_reused_unchanged": True,
        "development_and_validation_rules_identical": True,
        "semantic_label_is_geometry_family_not_specific_object_identity": True,
        "zero_video_decode_render_fit_search_replay_metric_geometry_hardware_or_paid_compute": True,
    }
    output_directory.mkdir(parents=True, exist_ok=True)
    montage = {**_write_png(output_directory / "persistent_linear_object_topology.png", np.concatenate(visualization_rows, axis=0)), "layout": "physical_persistent_left_selected_component_green_segment_seed_red_right"}
    receipt: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_post_final_persistent_linear_workcell_object_attribution_receipt.v1",
        "experiment_id": contract["experiment_id"],
        "status": status,
        "proof_class": contract["proof_class"],
        "contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)},
        "frozen_line_family": selected_family,
        "rows": raw_rows,
        "development_summary": development,
        "validation_summary": validation,
        "gates": {"finite_object": finite_gates, "scene_boundary": boundary_gates, "integrity": integrity},
        "montage": montage,
        "execution": {"or97_occupancy_map_reads": len(raw_rows), "or114_receipt_reads": 1, "source_video_decodes": 0, "candidate_video_decodes": 0, "renders": 0, "fits_or_candidate_searches": 0, "validation_refits": 0, "simulator_replays": 0, "metric_3d_geometry_values_produced": 0, "hardware_actions": 0, "paid_compute": False},
        "claim_limits": contract["claim_limits"],
        "reviewer_decision": reviewer_decision,
        "next_transition": next_transition,
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(evaluate_once(), sort_keys=True))
