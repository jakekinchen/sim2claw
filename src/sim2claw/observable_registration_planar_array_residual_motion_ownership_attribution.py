"""Classify uncovered OR123 residual components by retained-footage motion ownership."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .learning_factory_artifacts import atomic_write_json, canonical_digest
from .observable_registration_development_shared_camera_baseline import _decode_selected_frames
from .observable_registration_host_native_analytic_3d_renderer_capability import REPO_ROOT, sha256_file
from .observable_registration_post_final_independent_robot_base_full_corpus_diagnostic import (
    _episode_inventory,
    load_post_final_independent_robot_base_full_corpus_diagnostic_contract,
)


cv2.ocl.setUseOpenCL(False)

SCHEMA = "sim2claw.observable_registration_planar_array_residual_motion_ownership_attribution_contract.v1"
DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_planar_array_residual_motion_ownership_attribution_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_planar_array_residual_motion_ownership_attribution_v1"


def load_motion_ownership_contract(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    contract = json.loads(path.read_text())
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("unsupported OR124 contract")
    for group in ("sources", "frozen_identities"):
        for binding in contract[group].values():
            source_path = binding.get("path")
            expected = binding.get("sha256")
            if source_path and expected and sha256_file(REPO_ROOT / source_path) != expected:
                raise ValueError(f"OR124 identity mismatch: {source_path}")
    split = contract["split"]
    if split["development_positions"] != list(range(1, 8)) or split["corroboration_positions"] != list(range(8, 12)):
        raise ValueError("OR124 split drifted")
    if split["corroboration_requires_decisive_development"] is not True or split["corroboration_refit_allowed"] is not False:
        raise ValueError("OR124 corroboration boundary drifted")
    temporal = contract["temporal_measurement"]
    if temporal["canny_low_threshold"] != 50 or temporal["canny_high_threshold"] != 150:
        raise ValueError("OR124 inherited edge threshold drifted")
    if temporal["translation_radius_px"] != 12 or temporal["edge_tolerance_dilation_kernel_px"] != 3:
        raise ValueError("OR124 translation rule drifted")
    decision = contract["decision_tree"]
    if decision["development_minimum_consistent_episode_count"] != 5 or decision["corroboration_minimum_consistent_episode_count"] != 3:
        raise ValueError("OR124 voting rule drifted")
    resources = contract["resource_boundary"]
    zero = (
        "candidate_video_decodes_allowed",
        "renders_allowed",
        "geometry_or_material_fits_allowed",
        "candidate_selections_allowed",
        "threshold_changes_allowed",
        "retries_allowed",
        "simulator_replays_allowed",
        "hardware_actions_allowed",
    )
    if any(resources[key] != 0 for key in zero) or resources["paid_compute_allowed"] is not False:
        raise ValueError("OR124 resource boundary drifted")
    if any(contract["authority"].values()):
        raise ValueError("OR124 authority must remain closed")
    for key in ("specific_object_identity", "metric_3d_geometry_calibrated", "predictive_simulation", "physics_fidelity", "physical_transfer", "simulator_promotion"):
        if contract["claim_limits"][key] is not False:
            raise ValueError("OR124 claim boundary drifted")
    return contract


def _extract_components(uncovered: np.ndarray, component_rule: dict[str, Any]) -> list[dict[str, Any]]:
    kernel_size = int(component_rule["connectivity_dilation_kernel_px"])
    dilated = cv2.dilate(uncovered.astype(np.uint8), np.ones((kernel_size, kernel_size), dtype=np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(dilated, connectivity=8)
    components: list[dict[str, Any]] = []
    for label in range(1, count):
        raw = uncovered & (labels == label)
        raw_count = int(raw.sum())
        area = int(stats[label, cv2.CC_STAT_AREA])
        if raw_count < int(component_rule["minimum_raw_pixel_count"]) or area < int(component_rule["minimum_dilated_area_px"]):
            continue
        x, y, width, height = [int(value) for value in stats[label, :4]]
        components.append(
            {
                "raw_mask": raw,
                "raw_pixel_count": raw_count,
                "dilated_area_px": area,
                "bbox_xywh": [x, y, width, height],
            }
        )
    components.sort(key=lambda item: (-item["raw_pixel_count"], item["bbox_xywh"]))
    return components[: int(component_rule["maximum_component_count"])]


def _translation_measurement(target: np.ndarray, dilated_edges: np.ndarray, radius: int) -> dict[str, float | list[int]]:
    ys, xs = np.nonzero(target)
    if len(xs) == 0:
        raise ValueError("OR124 empty component target")
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    template = target[y0:y1, x0:x1].astype(np.float32)
    padded = np.pad(dilated_edges.astype(np.float32), radius, mode="constant")
    search = padded[y0 : y1 + 2 * radius, x0 : x1 + 2 * radius]
    scores = cv2.matchTemplate(search, template, cv2.TM_CCORR)
    _, maximum, _, location = cv2.minMaxLoc(scores)
    fixed = float(scores[radius, radius])
    denominator = max(float(target.sum()), 1.0)
    dx, dy = int(location[0] - radius), int(location[1] - radius)
    best_score = float(maximum / denominator)
    fixed_score = float(fixed / denominator)
    return {
        "best_translation_xy": [dx, dy],
        "best_translation_distance_px": float(np.hypot(dx, dy)),
        "best_support_fraction": best_score,
        "fixed_support_fraction": fixed_score,
        "translation_gain": best_score - fixed_score,
    }


def _classify_episode(measurements: list[dict[str, Any]], decision: dict[str, Any]) -> tuple[str, dict[str, float]]:
    moving = [
        row
        for row in measurements
        if row["best_translation_distance_px"] >= float(decision["moving_minimum_translation_px"])
        and row["translation_gain"] >= float(decision["moving_minimum_translation_gain"])
    ]
    summary = {
        "frame_count": len(measurements),
        "median_fixed_support_fraction": float(np.median([row["fixed_support_fraction"] for row in measurements])),
        "median_best_support_fraction": float(np.median([row["best_support_fraction"] for row in measurements])),
        "median_best_translation_distance_px": float(np.median([row["best_translation_distance_px"] for row in measurements])),
        "moving_frame_fraction": float(len(moving) / max(len(measurements), 1)),
    }
    if (
        summary["median_fixed_support_fraction"] >= float(decision["static_minimum_median_fixed_support_fraction"])
        and summary["moving_frame_fraction"] <= float(decision["static_maximum_moving_frame_fraction"])
    ):
        label = "workcell_static"
    elif (
        summary["moving_frame_fraction"] >= float(decision["attached_minimum_moving_frame_fraction"])
        and summary["median_best_support_fraction"] >= float(decision["attached_minimum_median_best_support_fraction"])
    ):
        label = "robot_or_actor_attached"
    else:
        label = "indeterminate"
    return label, summary


def _component_vote(rows: list[dict[str, Any]], positions: list[int], minimum: int) -> tuple[str, dict[str, int]]:
    labels = [row["episode_label"] for row in rows if row["split_position"] in positions]
    counts = {name: labels.count(name) for name in ("workcell_static", "robot_or_actor_attached", "indeterminate")}
    if counts["workcell_static"] >= minimum:
        label = "workcell_static"
    elif counts["robot_or_actor_attached"] >= minimum:
        label = "robot_or_actor_attached"
    else:
        label = "indeterminate"
    return label, counts


def evaluate_once(contract_path: Path = DEFAULT_CONTRACT, output_directory: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR124 one-run receipt already exists")
    contract = load_motion_ownership_contract(contract_path)
    or123 = json.loads((REPO_ROOT / contract["sources"]["or123_receipt"]["path"]).read_text())
    if or123["artifact_sha256"] != contract["sources"]["or123_receipt"]["artifact_sha256"]:
        raise ValueError("OR124 OR123 artifact drifted")
    audit = cv2.imread(str(REPO_ROOT / contract["sources"]["or123_audit"]["path"]), cv2.IMREAD_COLOR)
    if audit is None or audit.shape != (240, 1280, 3):
        raise ValueError("OR124 OR123 audit shape drifted")
    uncovered = audit[:, 960:1280, 2] > 0
    if int(uncovered.sum()) != int(contract["integrity"]["expected_uncovered_pixel_count"]):
        raise ValueError("OR124 uncovered support identity drifted")
    components = _extract_components(uncovered, contract["component_rule"])
    if not components:
        raise ValueError("OR124 no significant uncovered components")

    or95_contract = load_post_final_independent_robot_base_full_corpus_diagnostic_contract(
        REPO_ROOT / contract["sources"]["or95_contract"]["path"]
    )
    episodes = _episode_inventory(or95_contract)
    episode_by_position = {int(row["split_position"]): row for row in episodes}
    frame_rows = json.loads((REPO_ROOT / contract["sources"]["or119_frame_rows"]["path"]).read_text())["rows"]
    rows_by_position: dict[int, list[dict[str, Any]]] = {position: [] for position in episode_by_position}
    for row in frame_rows:
        rows_by_position[int(row["split_position"])].append(row)
    for values in rows_by_position.values():
        values.sort(key=lambda row: int(row["evaluation_index"]))

    temporal = contract["temporal_measurement"]
    decision = contract["decision_tree"]
    measured_phases = set(temporal["measured_motion_phases"])
    kernel = np.ones((int(temporal["edge_tolerance_dilation_kernel_px"]),) * 2, dtype=np.uint8)
    component_rows: list[dict[str, Any]] = []
    decoded_positions: list[int] = []
    decoded_frame_count = 0

    def evaluate_positions(positions: list[int], split_name: str) -> None:
        nonlocal decoded_frame_count
        for position in positions:
            episode = episode_by_position[position]
            bound_rows = rows_by_position[position]
            selected = [row for row in bound_rows if row["phase"] in measured_phases]
            indices = np.asarray([int(row["physical_frame_index"]) for row in selected], dtype=np.int64)
            video = episode["physical_video"]
            video_path = REPO_ROOT / video["path"]
            if sha256_file(video_path) != video["sha256"]:
                raise ValueError("OR124 physical video identity drifted")
            frames = [
                cv2.flip(frame, -1)
                for frame in _decode_selected_frames(
                    video_path,
                    selected_indices=indices,
                    expected_frame_count=int(video["frame_count"]),
                    expected_width=int(video["width_px"]),
                    expected_height=int(video["height_px"]),
                    output_width=320,
                    output_height=240,
                )
            ]
            decoded_positions.append(position)
            decoded_frame_count += len(frames)
            edges = [
                cv2.dilate(
                    (cv2.Canny(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), int(temporal["canny_low_threshold"]), int(temporal["canny_high_threshold"])) > 0).astype(np.uint8),
                    kernel,
                )
                > 0
                for frame in frames
            ]
            for component_index, component in enumerate(components):
                measurements = [
                    _translation_measurement(component["raw_mask"], edge, int(temporal["translation_radius_px"]))
                    for edge in edges
                ]
                label, summary = _classify_episode(measurements, decision)
                component_rows.append(
                    {
                        "split": split_name,
                        "split_position": position,
                        "recording_id": episode["recording_id"],
                        "component_index": component_index,
                        "episode_label": label,
                        "summary": summary,
                    }
                )

    development_positions = contract["split"]["development_positions"]
    evaluate_positions(development_positions, "development")
    development_component_labels: list[str] = []
    development_votes: list[dict[str, int]] = []
    for index in range(len(components)):
        label, votes = _component_vote(
            [row for row in component_rows if row["component_index"] == index],
            development_positions,
            int(decision["development_minimum_consistent_episode_count"]),
        )
        development_component_labels.append(label)
        development_votes.append(votes)
    development_decisive = bool(development_component_labels) and len(set(development_component_labels)) == 1 and development_component_labels[0] != "indeterminate"

    corroboration_positions = contract["split"]["corroboration_positions"]
    corroboration_component_labels: list[str] = []
    corroboration_votes: list[dict[str, int]] = []
    if development_decisive:
        evaluate_positions(corroboration_positions, "corroboration")
        for index in range(len(components)):
            label, votes = _component_vote(
                [row for row in component_rows if row["component_index"] == index],
                corroboration_positions,
                int(decision["corroboration_minimum_consistent_episode_count"]),
            )
            corroboration_component_labels.append(label)
            corroboration_votes.append(votes)
    corroboration_matches = development_decisive and corroboration_component_labels == development_component_labels
    selected_ownership = development_component_labels[0] if corroboration_matches else "indeterminate"

    output_directory.mkdir(parents=True, exist_ok=True)
    component_audit = np.zeros((240, 320, 3), dtype=np.uint8)
    palette = [(255, 255, 0), (0, 255, 255), (255, 0, 255), (0, 128, 255), (128, 255, 0)]
    component_bindings: list[dict[str, Any]] = []
    for index, component in enumerate(components):
        component_audit[component["raw_mask"]] = palette[index % len(palette)]
        component_bindings.append(
            {
                "component_index": index,
                "raw_pixel_count": component["raw_pixel_count"],
                "dilated_area_px": component["dilated_area_px"],
                "bbox_xywh": component["bbox_xywh"],
                "development_label": development_component_labels[index],
                "development_votes": development_votes[index],
                "corroboration_label": corroboration_component_labels[index] if corroboration_component_labels else None,
                "corroboration_votes": corroboration_votes[index] if corroboration_votes else None,
            }
        )
    audit_path = output_directory / "motion-ownership-components.png"
    ok, encoded = cv2.imencode(".png", component_audit, [cv2.IMWRITE_PNG_COMPRESSION, 9])
    if not ok:
        raise RuntimeError("OR124 audit encoding failed")
    audit_path.write_bytes(encoded.tobytes())

    integrity = {
        "expected_uncovered_pixel_count": int(uncovered.sum()) == int(contract["integrity"]["expected_uncovered_pixel_count"]),
        "significant_component_count_within_bound": 1 <= len(components) <= int(contract["component_rule"]["maximum_component_count"]),
        "development_exact_seven_episodes": set(development_positions).issubset(decoded_positions),
        "corroboration_condition_respected": (set(corroboration_positions).issubset(decoded_positions)) == development_decisive,
        "corroboration_no_refit": True,
        "zero_candidate_decode_render_fit_selection_threshold_change_retry_replay_hardware_or_paid_compute": True,
    }
    passed = selected_ownership != "indeterminate" and all(integrity.values())
    status = "PASS_RESIDUAL_MOTION_OWNERSHIP_ATTRIBUTED" if passed else "TERMINAL_RESIDUAL_MOTION_OWNERSHIP_INDETERMINATE"
    next_transition = {
        "workcell_static": "freeze_or125_renderer_native_workcell_static_component_identification",
        "robot_or_actor_attached": "freeze_or125_renderer_native_attached_component_kinematic_attribution",
        "indeterminate": "freeze_or125_component_specific_motion_ownership_refinement",
    }[selected_ownership]
    receipt: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_planar_array_residual_motion_ownership_attribution_receipt.v1",
        "experiment_id": contract["experiment_id"],
        "status": status,
        "proof_class": contract["proof_class"],
        "identities": {
            "contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)},
            "implementation": contract["frozen_identities"]["implementation"],
            "test": contract["frozen_identities"]["test"],
        },
        "components": component_bindings,
        "episode_component_rows": component_rows,
        "development_decisive": development_decisive,
        "corroboration_matches_development": corroboration_matches,
        "selected_motion_ownership": selected_ownership,
        "audit": {"path": str(audit_path.relative_to(REPO_ROOT)), "sha256": sha256_file(audit_path), "layout": "significant_uncovered_components_distinct_colors"},
        "integrity_gates": integrity,
        "execution": {
            "physical_video_decodes": len(decoded_positions),
            "physical_frames_read": decoded_frame_count,
            "candidate_video_decodes": 0,
            "renders": 0,
            "geometry_or_material_fits": 0,
            "candidate_selections": 0,
            "threshold_changes": 0,
            "retries": 0,
            "simulator_replays": 0,
            "hardware_actions": 0,
            "paid_compute": False,
        },
        "claim_limits": contract["claim_limits"],
        "reviewer_decision": "FREEZE_OWNERSHIP_CONSISTENT_SUCCESSOR" if passed else "FREEZE_COMPONENT_SPECIFIC_REFINEMENT",
        "next_transition": next_transition,
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(evaluate_once(), sort_keys=True))
