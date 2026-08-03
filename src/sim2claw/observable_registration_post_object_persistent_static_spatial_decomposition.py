"""Spatially decompose OR120B's identity-bound physical-only persistent residual."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .learning_factory_artifacts import atomic_write_json, canonical_digest
from .observable_registration_host_native_analytic_3d_renderer_capability import REPO_ROOT, sha256_file


cv2.ocl.setUseOpenCL(False)

SCHEMA = "sim2claw.observable_registration_post_object_persistent_static_spatial_decomposition_contract.v1"
DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_post_object_persistent_static_spatial_decomposition_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_post_object_persistent_static_spatial_decomposition_v1"


def load_spatial_decomposition_contract(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    contract = json.loads(path.read_text())
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("unsupported OR121 contract")
    for group in ("sources", "frozen_identities"):
        for binding in contract[group].values():
            if sha256_file(REPO_ROOT / binding["path"]) != binding["sha256"]:
                raise ValueError(f"OR121 identity mismatch: {binding['path']}")
    or114 = json.loads((REPO_ROOT / contract["sources"]["or114_contract"]["path"]).read_text())
    if contract["line_extractor"] != or114["line_extractor"]:
        raise ValueError("OR121 must reuse the exact OR114 line extractor")
    panels = contract["input_panels"]
    if panels["panel_width_px"] != 320 or panels["panel_height_px"] != 240 or panels["physical_only_persistent_panel_index"] != 2:
        raise ValueError("OR121 panel binding drift")
    consensus = contract["consensus"]
    if consensus["minimum_episode_count"] != 9 or consensus["component_dilation_kernel_px"] != 3:
        raise ValueError("OR121 consensus rule drift")
    resources = contract["resource_boundary"]
    zero_keys = (
        "source_video_decodes_allowed",
        "candidate_video_decodes_allowed",
        "renders_allowed",
        "fits_allowed",
        "candidate_selections_allowed",
        "threshold_changes_allowed",
        "retries_allowed",
        "simulator_replays_allowed",
        "geometry_values_produced_allowed",
        "hardware_actions_allowed",
    )
    if any(resources[key] != 0 for key in zero_keys) or resources["paid_compute_allowed"] is not False:
        raise ValueError("OR121 resource boundary drift")
    if any(contract["authority"].values()):
        raise ValueError("OR121 authority must remain closed")
    return contract


def _extract_panel(image: np.ndarray, panel_index: int, width: int, height: int) -> np.ndarray:
    if image.shape[:2] != (height, width * 8):
        raise ValueError("OR121 eight-panel map shape drift")
    start = panel_index * width
    return image[:, start : start + width]


def _orientation_bin(angle_degrees: float, bin_width_degrees: int) -> int:
    return int((angle_degrees % 180.0) // bin_width_degrees) * bin_width_degrees


def _orientation_separation(first_bin: int, second_bin: int) -> float:
    delta = abs(float(first_bin) - float(second_bin))
    return min(delta, 180.0 - delta)


def _classify_spatial_family(summary: dict[str, Any], acceptance: dict[str, Any]) -> str:
    if (
        int(summary["consensus_pixel_count"]) >= int(acceptance["minimum_consensus_pixel_count"])
        and float(summary["minimum_episode_consensus_coverage"]) >= float(acceptance["minimum_each_episode_consensus_coverage"])
        and float(summary["largest_component_dilated_share"]) >= float(acceptance["minimum_largest_component_dilated_share"])
        and int(summary["primary_orientation_line_count"]) >= int(acceptance["minimum_primary_orientation_line_count"])
        and float(summary["primary_orientation_total_length_px"]) >= float(acceptance["minimum_primary_orientation_total_length_px"])
        and int(summary["secondary_orientation_line_count"]) >= int(acceptance["minimum_secondary_orientation_line_count"])
        and float(summary["secondary_orientation_total_length_px"]) >= float(acceptance["minimum_secondary_orientation_total_length_px"])
        and float(acceptance["minimum_orthogonal_separation_degrees"])
        <= float(summary["orientation_family_separation_degrees"])
        <= float(acceptance["maximum_orthogonal_separation_degrees"])
        and bool(summary["largest_component_touches_image_boundary"])
    ):
        return "clipped_image_space_rectilinear_planar_array"
    if (
        float(summary["largest_component_dilated_share"]) >= float(acceptance["minimum_largest_component_dilated_share"])
        and not bool(summary["largest_component_touches_image_boundary"])
        and float(summary["largest_component_bbox_aspect_ratio"])
        >= float(acceptance["minimum_finite_elongated_bbox_aspect_ratio"])
    ):
        return "finite_elongated_component"
    return "unresolved_multi_component_persistent_scene"


def _analyze_masks(masks: list[np.ndarray], contract: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if len(masks) != int(contract["input_panels"]["expected_map_count"]):
        raise ValueError("OR121 map count drift")
    support = np.sum(np.stack(masks, axis=0), axis=0).astype(np.uint8)
    consensus = support >= int(contract["consensus"]["minimum_episode_count"])
    consensus_pixels = int(consensus.sum())
    coverages = [float((mask & consensus).sum() / max(consensus_pixels, 1)) for mask in masks]
    kernel_size = int(contract["consensus"]["component_dilation_kernel_px"])
    dilated = cv2.dilate(consensus.astype(np.uint8), np.ones((kernel_size, kernel_size), dtype=np.uint8))
    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(dilated, connectivity=8)
    components: list[dict[str, Any]] = []
    for label in range(1, component_count):
        x, y, width, height, area = [int(value) for value in stats[label]]
        components.append(
            {
                "label": label,
                "area_px": area,
                "bbox_xywh": [x, y, width, height],
                "bbox_aspect_ratio": float(max(width, height) / max(min(width, height), 1)),
                "touches_left": x == 0,
                "touches_right": x + width == consensus.shape[1],
                "touches_top": y == 0,
                "touches_bottom": y + height == consensus.shape[0],
            }
        )
    components.sort(key=lambda row: (-int(row["area_px"]), int(row["label"])))
    largest = components[0] if components else {
        "label": 0,
        "area_px": 0,
        "bbox_xywh": [0, 0, 0, 0],
        "bbox_aspect_ratio": 0.0,
        "touches_left": False,
        "touches_right": False,
        "touches_top": False,
        "touches_bottom": False,
    }
    extractor = contract["line_extractor"]
    lines = cv2.HoughLinesP(
        consensus.astype(np.uint8) * 255,
        rho=float(extractor["rho_resolution_px"]),
        theta=np.deg2rad(float(extractor["theta_resolution_degrees"])),
        threshold=int(extractor["vote_threshold"]),
        minLineLength=float(extractor["minimum_line_length_px"]),
        maxLineGap=float(extractor["maximum_line_gap_px"]),
    )
    bins: dict[int, dict[str, Any]] = {
        value: {"orientation_bin_degrees": value, "line_count": 0, "total_length_px": 0.0, "lines": []}
        for value in range(0, 180, int(extractor["orientation_bin_width_degrees"]))
    }
    if lines is not None:
        for raw in lines[:, 0]:
            x1, y1, x2, y2 = [int(value) for value in raw]
            length = float(np.hypot(x2 - x1, y2 - y1))
            angle = float(np.degrees(np.arctan2(y2 - y1, x2 - x1)) % 180.0)
            bin_value = _orientation_bin(angle, int(extractor["orientation_bin_width_degrees"]))
            bins[bin_value]["line_count"] += 1
            bins[bin_value]["total_length_px"] += length
            bins[bin_value]["lines"].append([x1, y1, x2, y2])
    ranked_bins = sorted(bins.values(), key=lambda row: (-float(row["total_length_px"]), int(row["orientation_bin_degrees"])))
    primary = ranked_bins[0]
    secondary = ranked_bins[1]
    largest_touches = any(bool(largest[key]) for key in ("touches_left", "touches_right", "touches_top", "touches_bottom"))
    summary: dict[str, Any] = {
        "consensus_pixel_count": consensus_pixels,
        "consensus_fraction_of_frame": float(consensus.mean()),
        "minimum_episode_consensus_coverage": float(min(coverages)),
        "mean_episode_consensus_coverage": float(np.mean(coverages)),
        "component_count_after_frozen_dilation": len(components),
        "dilated_pixel_count": int(dilated.sum()),
        "largest_component_area_px": int(largest["area_px"]),
        "largest_component_dilated_share": float(int(largest["area_px"]) / max(int(dilated.sum()), 1)),
        "largest_component_bbox_xywh": largest["bbox_xywh"],
        "largest_component_bbox_aspect_ratio": float(largest["bbox_aspect_ratio"]),
        "largest_component_touches_image_boundary": largest_touches,
        "largest_component_boundary_contacts": {
            "left": bool(largest["touches_left"]),
            "right": bool(largest["touches_right"]),
            "top": bool(largest["touches_top"]),
            "bottom": bool(largest["touches_bottom"]),
        },
        "primary_orientation_bin_degrees": int(primary["orientation_bin_degrees"]),
        "primary_orientation_line_count": int(primary["line_count"]),
        "primary_orientation_total_length_px": float(primary["total_length_px"]),
        "secondary_orientation_bin_degrees": int(secondary["orientation_bin_degrees"]),
        "secondary_orientation_line_count": int(secondary["line_count"]),
        "secondary_orientation_total_length_px": float(secondary["total_length_px"]),
        "orientation_family_separation_degrees": _orientation_separation(
            int(primary["orientation_bin_degrees"]), int(secondary["orientation_bin_degrees"])
        ),
    }
    summary["selected_spatial_family"] = _classify_spatial_family(summary, contract["acceptance"])
    internals = {
        "support": support,
        "consensus": consensus,
        "dilated": dilated,
        "labels": labels,
        "largest_label": int(largest["label"]),
        "primary": primary,
        "secondary": secondary,
        "episode_coverages": coverages,
    }
    return summary, internals


def _write_audit_montage(path: Path, internals: dict[str, Any]) -> dict[str, str]:
    consensus = internals["consensus"]
    panel_consensus = np.repeat((consensus.astype(np.uint8) * 255)[:, :, None], 3, axis=2)
    support_scaled = np.rint(internals["support"].astype(np.float64) * (255.0 / 11.0)).astype(np.uint8)
    panel_support = cv2.applyColorMap(support_scaled, cv2.COLORMAP_TURBO)
    panel_components = np.zeros_like(panel_consensus)
    panel_components[internals["dilated"] > 0] = (96, 96, 96)
    if int(internals["largest_label"]) > 0:
        panel_components[internals["labels"] == int(internals["largest_label"])] = (0, 255, 0)
    panel_lines = panel_consensus.copy()
    for line in internals["primary"]["lines"]:
        cv2.line(panel_lines, tuple(line[:2]), tuple(line[2:]), (0, 255, 0), 1, cv2.LINE_AA)
    for line in internals["secondary"]["lines"]:
        cv2.line(panel_lines, tuple(line[:2]), tuple(line[2:]), (255, 255, 0), 1, cv2.LINE_AA)
    montage = np.concatenate([panel_consensus, panel_support, panel_components, panel_lines], axis=1)
    ok, encoded = cv2.imencode(".png", montage, [cv2.IMWRITE_PNG_COMPRESSION, 9])
    if not ok:
        raise RuntimeError("OR121 montage encoding failed")
    path.write_bytes(encoded.tobytes())
    return {
        "path": str(path.relative_to(REPO_ROOT)),
        "sha256": sha256_file(path),
        "layout": "nine_of_eleven_consensus_support_heatmap_dilated_components_primary_secondary_hough_lines",
    }


def evaluate_once(contract_path: Path = DEFAULT_CONTRACT, output_directory: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR121 one-run receipt already exists")
    contract = load_spatial_decomposition_contract(contract_path)
    source = json.loads((REPO_ROOT / contract["sources"]["or120b_receipt"]["path"]).read_text())
    if source["status"] != "PASS_IDENTITY_BOUND_PERSISTENT_STATIC_RESIDUAL_REPRODUCED":
        raise ValueError("OR120B did not authorize OR121")
    panels = contract["input_panels"]
    masks: list[np.ndarray] = []
    map_bindings: list[dict[str, Any]] = []
    for row in source["rows"]:
        binding = row["residual_map"]
        path = REPO_ROOT / binding["path"]
        if sha256_file(path) != binding["sha256"]:
            raise ValueError("OR121 residual map hash drift")
        image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        if image is None:
            raise ValueError("OR121 residual map decode failed")
        panel = _extract_panel(
            image,
            int(panels["physical_only_persistent_panel_index"]),
            int(panels["panel_width_px"]),
            int(panels["panel_height_px"]),
        )
        masks.append(panel > 0)
        map_bindings.append({"recording_id": row["recording_id"], "split_position": row["split_position"], **binding})
    summary, internals = _analyze_masks(masks, contract)
    output_directory.mkdir(parents=True, exist_ok=True)
    montage = _write_audit_montage(output_directory / "persistent-static-spatial-decomposition.png", internals)
    selected = summary["selected_spatial_family"]
    gates = {
        "exact_eleven_hash_bound_eight_panel_maps": len(masks) == 11,
        "nine_of_eleven_consensus_material": int(summary["consensus_pixel_count"]) >= int(contract["acceptance"]["minimum_consensus_pixel_count"]),
        "each_episode_covers_consensus": float(summary["minimum_episode_consensus_coverage"]) >= float(contract["acceptance"]["minimum_each_episode_consensus_coverage"]),
        "single_observational_spatial_family_selected": selected != "unresolved_multi_component_persistent_scene",
        "zero_video_decode_render_fit_selection_threshold_change_retry_replay_geometry_or_hardware": True,
        "retrospective_image_space_diagnostic_not_object_identity_or_promotion": True,
    }
    if selected == "clipped_image_space_rectilinear_planar_array" and all(gates.values()):
        status = "PASS_CLIPPED_RECTILINEAR_PLANAR_ARRAY_IDENTIFIED"
        reviewer_decision = "FREEZE_RENDERER_NATIVE_CLIPPED_RECTILINEAR_PLANAR_ARRAY_RECONSTRUCTION"
        next_transition = "freeze_or122_renderer_native_clipped_rectilinear_planar_array_reconstruction"
    elif selected == "finite_elongated_component" and all(gates.values()):
        status = "PASS_ADDITIONAL_FINITE_ELONGATED_COMPONENT_IDENTIFIED"
        reviewer_decision = "FREEZE_ADDITIONAL_FINITE_ELONGATED_COMPONENT_RECONSTRUCTION"
        next_transition = "freeze_or122_additional_finite_elongated_component_reconstruction"
    else:
        status = "TERMINAL_PERSISTENT_STATIC_SPATIAL_DECOMPOSITION_UNRESOLVED"
        reviewer_decision = "CLOSE_RETAINED_PERSISTENT_STATIC_SUCCESSOR_LANE"
        next_transition = None
    receipt: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_post_object_persistent_static_spatial_decomposition_receipt.v1",
        "experiment_id": contract["experiment_id"],
        "status": status,
        "proof_class": contract["proof_class"],
        "identities": {
            "contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)},
            "implementation": contract["frozen_identities"]["implementation"],
            "test": contract["frozen_identities"]["test"],
        },
        "source_maps": map_bindings,
        "summary": summary,
        "episode_consensus_coverages": internals["episode_coverages"],
        "audit_montage": montage,
        "gates": gates,
        "execution": {
            "identity_bound_residual_map_reads": len(masks),
            "source_video_decodes": 0,
            "candidate_video_decodes": 0,
            "renders": 0,
            "fits": 0,
            "candidate_selections": 0,
            "threshold_changes": 0,
            "retries": 0,
            "simulator_replays": 0,
            "geometry_values_produced": 0,
            "hardware_actions": 0,
            "paid_compute": False,
        },
        "claim_limits": contract["claim_limits"],
        "reviewer_decision": reviewer_decision,
        "next_transition": next_transition,
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(evaluate_once(), sort_keys=True))
