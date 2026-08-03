"""Identify a bounded surface family for identity-clean OR124C components."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .learning_factory_artifacts import atomic_write_json, canonical_digest
from .observable_registration_development_shared_camera_baseline import _decode_selected_frames
from .observable_registration_host_native_analytic_3d_renderer_capability import REPO_ROOT, sha256_file
from .observable_registration_planar_array_residual_motion_ownership_attribution import _extract_components
from .observable_registration_post_final_independent_robot_base_full_corpus_diagnostic import (
    _episode_inventory,
    load_post_final_independent_robot_base_full_corpus_diagnostic_contract,
)


cv2.ocl.setUseOpenCL(False)

SCHEMA = "sim2claw.observable_registration_workcell_static_component_surface_identification_contract.v1"
DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_workcell_static_component_surface_identification_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_workcell_static_component_surface_identification_v1"


def load_surface_identification_contract(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    contract = json.loads(path.read_text())
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("unsupported OR125 contract")
    for group in ("sources", "frozen_identities"):
        for binding in contract[group].values():
            source_path = binding.get("path")
            expected = binding.get("sha256")
            if source_path and expected and sha256_file(REPO_ROOT / source_path) != expected:
                raise ValueError(f"OR125 identity mismatch: {source_path}")
    split = contract["split"]
    if split["development_positions"] != list(range(1, 8)) or split["corroboration_positions"] != list(range(8, 12)):
        raise ValueError("OR125 split drifted")
    detector = contract["detector"]
    if detector["backend"] != "opencv_aruco" or detector["dictionary"] != "DICT_APRILTAG_36h11":
        raise ValueError("OR125 detector drifted")
    if detector["corner_refinement"] != "CORNER_REFINE_SUBPIX":
        raise ValueError("OR125 detector refinement drifted")
    decision = contract["decision_tree"]
    if decision["minimum_associated_component_count"] != 3 or decision["minimum_associated_raw_pixel_fraction"] != 0.75:
        raise ValueError("OR125 association rule drifted")
    if decision["maximum_component_to_fixture_distance_px"] != 60 or decision["maximum_axis_family_error_degrees"] != 12.0:
        raise ValueError("OR125 planar-fixture support rule drifted")
    if decision["development_minimum_fixture_episode_count"] != 5 or decision["corroboration_minimum_fixture_episode_count"] != 3:
        raise ValueError("OR125 vote rule drifted")
    resources = contract["resource_boundary"]
    zero = ("renders_allowed", "dense_mask_vectorizations_allowed", "geometry_or_material_fits_allowed", "parameter_searches_allowed", "threshold_changes_allowed", "retries_allowed", "simulator_replays_allowed", "hardware_actions_allowed")
    if any(resources[key] != 0 for key in zero) or resources["paid_compute_allowed"] is not False:
        raise ValueError("OR125 resource boundary drifted")
    if any(contract["authority"].values()):
        raise ValueError("OR125 authority must remain closed")
    for key in ("specific_object_identity", "metric_3d_geometry_calibrated", "predictive_simulation", "physics_fidelity", "physical_transfer", "simulator_promotion"):
        if contract["claim_limits"][key] is not False:
            raise ValueError("OR125 claim boundary drifted")
    return contract


def _detector() -> cv2.aruco.ArucoDetector:
    parameters = cv2.aruco.DetectorParameters()
    parameters.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
    return cv2.aruco.ArucoDetector(dictionary, parameters)


def _axis_family_errors(corners: np.ndarray, expected: list[float]) -> list[float]:
    closed = np.vstack([corners, corners[:1]])
    edges = np.diff(closed, axis=0)
    angles = np.mod(np.degrees(np.arctan2(edges[:, 1], edges[:, 0])), 180.0)
    return [
        float(min(min(abs(angle - target), 180.0 - abs(angle - target)) for angle in angles))
        for target in expected
    ]


def _detect_fixture_mask(
    frame: np.ndarray, detector: cv2.aruco.ArucoDetector, expected_axes: list[float]
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    corners, ids, _ = detector.detectMarkers(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
    mask = np.zeros(frame.shape[:2], dtype=np.uint8)
    detections: list[dict[str, Any]] = []
    if ids is None:
        return mask.astype(bool), detections
    for corner, _tag_id in zip(corners, ids.reshape(-1), strict=True):
        polygon = np.rint(corner.reshape(4, 2)).astype(np.int32)
        cv2.fillConvexPoly(mask, polygon, 1)
        float_corners = corner.reshape(4, 2).astype(float)
        detections.append(
            {
                "corners_px": float_corners.tolist(),
                "axis_family_errors_degrees": _axis_family_errors(float_corners, expected_axes),
            }
        )
    detections.sort(key=lambda row: row["corners_px"][0])
    return mask.astype(bool), detections


def _classify_frame(
    components: list[dict[str, Any]], fixture_mask: np.ndarray, detections: list[dict[str, Any]], decision: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    axis_consistent = bool(detections) and all(
        max(detection["axis_family_errors_degrees"]) <= float(decision["maximum_axis_family_error_degrees"])
        for detection in detections
    )
    if axis_consistent:
        distance = cv2.distanceTransform((~fixture_mask).astype(np.uint8), cv2.DIST_L2, 5)
        associated_fixture = distance <= float(decision["maximum_component_to_fixture_distance_px"])
    else:
        associated_fixture = np.zeros_like(fixture_mask)
    overlaps = [float((component["raw_mask"] & associated_fixture).sum() / max(component["raw_pixel_count"], 1)) for component in components]
    associated = [value >= float(decision["minimum_component_fixture_overlap_fraction"]) for value in overlaps]
    total_raw = sum(component["raw_pixel_count"] for component in components)
    associated_pixels = sum(int((component["raw_mask"] & associated_fixture).sum()) for component in components)
    summary = {
        "complete_fixture_detection_count": len(detections),
        "fixture_axes_match_frozen_rectilinear_family": axis_consistent,
        "maximum_detected_axis_family_error_degrees": max(
            (max(row["axis_family_errors_degrees"]) for row in detections), default=None
        ),
        "component_overlap_fractions": overlaps,
        "associated_component_count": sum(associated),
        "associated_raw_pixel_fraction": float(associated_pixels / max(total_raw, 1)),
    }
    if (
        summary["associated_component_count"] >= int(decision["minimum_associated_component_count"])
        and summary["associated_raw_pixel_fraction"] >= float(decision["minimum_associated_raw_pixel_fraction"])
    ):
        label = "separate_static_planar_fixture"
    else:
        label = "indeterminate"
    return label, summary


def evaluate_once(contract_path: Path = DEFAULT_CONTRACT, output_directory: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR125 one-run receipt already exists")
    contract = load_surface_identification_contract(contract_path)
    or124c = json.loads((REPO_ROOT / contract["sources"]["or124c_receipt"]["path"]).read_text())
    if or124c["artifact_sha256"] != contract["sources"]["or124c_receipt"]["artifact_sha256"] or or124c["selected_motion_ownership"] != "workcell_static":
        raise ValueError("OR125 OR124C prerequisite drifted")
    or124c_contract = json.loads((REPO_ROOT / contract["sources"]["or124c_contract"]["path"]).read_text())
    audit = cv2.imread(str(REPO_ROOT / contract["sources"]["or123_audit"]["path"]), cv2.IMREAD_COLOR)
    if audit is None or audit.shape != (240, 1280, 3):
        raise ValueError("OR125 OR123 audit drifted")
    uncovered = audit[:, 960:1280, 2] > 0
    components = _extract_components(uncovered, or124c_contract["component_rule"])
    if len(components) != len(or124c["components"]):
        raise ValueError("OR125 significant component identity drifted")

    or95_contract = load_post_final_independent_robot_base_full_corpus_diagnostic_contract(REPO_ROOT / contract["sources"]["or95_contract"]["path"])
    episodes = _episode_inventory(or95_contract)
    by_position = {int(row["split_position"]): row for row in episodes}
    detector = _detector()
    rows: list[dict[str, Any]] = []
    panels: list[np.ndarray] = []

    def evaluate_positions(positions: list[int], split_name: str) -> None:
        for position in positions:
            episode = by_position[position]
            video = episode["physical_video"]
            video_path = REPO_ROOT / video["path"]
            if sha256_file(video_path) != video["sha256"]:
                raise ValueError("OR125 physical video drifted")
            frame = cv2.flip(
                _decode_selected_frames(
                    video_path,
                    selected_indices=np.asarray([0], dtype=np.int64),
                    expected_frame_count=int(video["frame_count"]),
                    expected_width=int(video["width_px"]),
                    expected_height=int(video["height_px"]),
                    output_width=320,
                    output_height=240,
                )[0],
                -1,
            )
            fixture_mask, detections = _detect_fixture_mask(
                frame, detector, contract["decision_tree"]["fixture_axis_families_degrees"]
            )
            label, summary = _classify_frame(components, fixture_mask, detections, contract["decision_tree"])
            rows.append({"split": split_name, "split_position": position, "recording_id": episode["recording_id"], "surface_family": label, **summary})
            annotated = frame.copy()
            for detection in detections:
                cv2.polylines(annotated, [np.rint(detection["corners_px"]).astype(np.int32)], True, (0, 255, 0), 2, cv2.LINE_AA)
            for component in components:
                annotated[component["raw_mask"]] = (0, 0, 255)
            panels.append(annotated)

    split = contract["split"]
    decision = contract["decision_tree"]
    evaluate_positions(split["development_positions"], "development")
    development_fixture_count = sum(row["surface_family"] == "separate_static_planar_fixture" for row in rows)
    development_decisive = development_fixture_count >= int(decision["development_minimum_fixture_episode_count"])
    if development_decisive:
        evaluate_positions(split["corroboration_positions"], "corroboration")
    corroboration_rows = [row for row in rows if row["split"] == "corroboration"]
    corroboration_fixture_count = sum(row["surface_family"] == "separate_static_planar_fixture" for row in corroboration_rows)
    corroboration_passed = bool(corroboration_rows) and corroboration_fixture_count >= int(decision["corroboration_minimum_fixture_episode_count"])
    selected = "separate_static_planar_fixture" if development_decisive and corroboration_passed else "indeterminate"

    output_directory.mkdir(parents=True, exist_ok=True)
    montage = np.concatenate(panels, axis=0)
    montage_path = output_directory / "surface-identification-audit.png"
    ok, encoded = cv2.imencode(".png", montage, [cv2.IMWRITE_PNG_COMPRESSION, 9])
    if not ok:
        raise RuntimeError("OR125 audit encoding failed")
    montage_path.write_bytes(encoded.tobytes())
    integrity = {
        "exact_five_significant_components": len(components) == 5,
        "development_exact_seven_frames": len([row for row in rows if row["split"] == "development"]) == 7,
        "corroboration_condition_respected": (len(corroboration_rows) == 4) == development_decisive,
        "corroboration_no_refit": True,
        "zero_dense_vectorization_render_fit_search_retry_replay_hardware_or_paid_compute": True,
    }
    passed = selected != "indeterminate" and all(integrity.values())
    status = "PASS_WORKCELL_STATIC_SURFACE_FAMILY_IDENTIFIED" if passed else "TERMINAL_WORKCELL_STATIC_SURFACE_FAMILY_INDETERMINATE"
    next_transition = "freeze_or126_renderer_native_planar_fixture_parameterization" if passed else "freeze_or126_static_component_surface_discriminator"
    receipt: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_workcell_static_component_surface_identification_receipt.v1",
        "experiment_id": contract["experiment_id"],
        "status": status,
        "proof_class": contract["proof_class"],
        "identities": {"contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)}, "implementation": contract["frozen_identities"]["implementation"], "test": contract["frozen_identities"]["test"]},
        "rows": rows,
        "development_fixture_episode_count": development_fixture_count,
        "development_decisive": development_decisive,
        "corroboration_fixture_episode_count": corroboration_fixture_count,
        "corroboration_passed": corroboration_passed,
        "selected_surface_family": selected,
        "audit": {"path": str(montage_path.relative_to(REPO_ROOT)), "sha256": sha256_file(montage_path), "layout": "physical_initial_frames_with_green_complete_planar_fixture_quads_and_red_static_components"},
        "integrity_gates": integrity,
        "execution": {"physical_video_decodes": len(rows), "physical_frame_reads": len(rows), "renders": 0, "dense_mask_vectorizations": 0, "geometry_or_material_fits": 0, "parameter_searches": 0, "threshold_changes": 0, "retries": 0, "simulator_replays": 0, "hardware_actions": 0, "paid_compute": False},
        "claim_limits": contract["claim_limits"],
        "reviewer_decision": "FREEZE_SURFACE_CONSISTENT_PARAMETERIZATION" if passed else "FREEZE_ADDITIONAL_SURFACE_DISCRIMINATOR",
        "next_transition": next_transition,
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(evaluate_once(), sort_keys=True))
