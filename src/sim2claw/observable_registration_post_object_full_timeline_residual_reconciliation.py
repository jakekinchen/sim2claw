"""Re-factor the immutable OR119 post-object residual across all retained timelines."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .learning_factory_artifacts import atomic_write_json, canonical_digest
from .observable_registration_board_anchored_workcell_se2_static_development_fit import _region_masks
from .observable_registration_development_shared_camera_baseline import _decode_selected_frames
from .observable_registration_host_native_analytic_3d_renderer_capability import REPO_ROOT, sha256_file
from .observable_registration_post_final_independent_robot_base_full_corpus_diagnostic import _episode_inventory
from .observable_registration_post_final_static_dynamic_edge_occupancy_factorization import (
    _binary_tolerant_f1,
    _read_video_frames,
    _write_map,
)


cv2.ocl.setUseOpenCL(False)

SCHEMA = "sim2claw.observable_registration_post_object_full_timeline_residual_reconciliation_contract.v1"
DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_post_object_full_timeline_residual_reconciliation_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_post_object_full_timeline_residual_reconciliation_v1"


def load_post_object_full_timeline_residual_reconciliation_contract(
    path: Path = DEFAULT_CONTRACT,
) -> dict[str, Any]:
    contract = json.loads(path.read_text())
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("unsupported OR120 contract")
    for source in contract["sources"].values():
        if sha256_file(REPO_ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['path']}")

    or97_contract = json.loads((REPO_ROOT / contract["sources"]["or97_contract"]["path"]).read_text())
    if contract["regions"] != or97_contract["regions"] or contract["edge_occupancy"] != or97_contract["edge_occupancy"]:
        raise ValueError("OR120 must preserve the exact OR97 region and occupancy rule")
    occupancy = contract["edge_occupancy"]
    if (
        occupancy["persistent_minimum_frame_fraction"] != 0.80
        or occupancy["dynamic_minimum_frame_fraction"] != 0.05
        or occupancy["dynamic_maximum_frame_fraction_exclusive"] != 0.80
    ):
        raise ValueError("OR120 occupancy thresholds drifted")
    dominance = contract["dominance_rule"]
    if (
        dominance["minimum_adequate_factor_f1"] != 0.60
        or dominance["minimum_inadequate_episode_count"] != 9
        or dominance["minimum_dominant_episode_count"] != 9
        or dominance["minimum_per_episode_deficit_margin"] != 0.05
        or dominance["minimum_mean_deficit_ratio"] != 2.0
    ):
        raise ValueError("OR120 dominance rule drifted")
    resources = contract["resource_boundary"]
    zero_keys = (
        "renders_allowed",
        "fits_allowed",
        "candidate_selections_allowed",
        "threshold_changes_allowed",
        "simulator_replays_allowed",
        "hardware_actions_allowed",
    )
    if any(resources[key] != 0 for key in zero_keys) or resources["paid_compute_allowed"] is not False:
        raise ValueError("OR120 resource boundary drifted")
    if any(contract["authority"].values()):
        raise ValueError("OR120 authority must remain closed")
    claims = contract["claim_limits"]
    if claims["same_video_semantic_match"] is not False or claims["untouched_cohort_remaining"] is not False:
        raise ValueError("OR120 claim boundary drifted")
    return contract


def _select_residual_family(
    persistent_values: list[float],
    dynamic_values: list[float],
    rule: dict[str, Any],
) -> dict[str, Any]:
    adequate = float(rule["minimum_adequate_factor_f1"])
    persistent_deficits = [max(0.0, adequate - value) for value in persistent_values]
    dynamic_deficits = [max(0.0, adequate - value) for value in dynamic_values]
    persistent_mean_deficit = float(np.mean(persistent_deficits))
    dynamic_mean_deficit = float(np.mean(dynamic_deficits))
    epsilon = 1.0e-12
    persistent_to_dynamic = persistent_mean_deficit / max(dynamic_mean_deficit, epsilon)
    dynamic_to_persistent = dynamic_mean_deficit / max(persistent_mean_deficit, epsilon)
    margin = float(rule["minimum_per_episode_deficit_margin"])
    persistent_dominant = sum(
        persistent - dynamic >= margin
        for persistent, dynamic in zip(persistent_deficits, dynamic_deficits, strict=True)
    )
    dynamic_dominant = sum(
        dynamic - persistent >= margin
        for persistent, dynamic in zip(persistent_deficits, dynamic_deficits, strict=True)
    )
    persistent_below = sum(value < adequate for value in persistent_values)
    dynamic_below = sum(value < adequate for value in dynamic_values)
    minimum_inadequate = int(rule["minimum_inadequate_episode_count"])
    minimum_dominant = int(rule["minimum_dominant_episode_count"])
    minimum_ratio = float(rule["minimum_mean_deficit_ratio"])

    if (
        persistent_below >= minimum_inadequate
        and persistent_dominant >= minimum_dominant
        and persistent_to_dynamic >= minimum_ratio
    ):
        selected = rule["persistent_dominant_selects"]
    elif (
        dynamic_below >= minimum_inadequate
        and dynamic_dominant >= minimum_dominant
        and dynamic_to_persistent >= minimum_ratio
    ):
        selected = rule["dynamic_dominant_selects"]
    else:
        selected = rule["otherwise_selects"]

    return {
        "mean_persistent_outside_board_edge_occupancy_f1": float(np.mean(persistent_values)),
        "mean_dynamic_outside_board_edge_occupancy_f1": float(np.mean(dynamic_values)),
        "mean_persistent_deficit_to_0_60": persistent_mean_deficit,
        "mean_dynamic_deficit_to_0_60": dynamic_mean_deficit,
        "persistent_to_dynamic_mean_deficit_ratio": persistent_to_dynamic,
        "dynamic_to_persistent_mean_deficit_ratio": dynamic_to_persistent,
        "episodes_persistent_below_threshold": persistent_below,
        "episodes_dynamic_below_threshold": dynamic_below,
        "episodes_persistent_deficit_dominant": persistent_dominant,
        "episodes_dynamic_deficit_dominant": dynamic_dominant,
        "selected_residual_family": selected,
    }


def evaluate_once(
    contract_path: Path = DEFAULT_CONTRACT,
    output_directory: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR120 one-run receipt already exists")
    contract = load_post_object_full_timeline_residual_reconciliation_contract(contract_path)
    or97 = json.loads((REPO_ROOT / contract["sources"]["or97_receipt"]["path"]).read_text())
    if or97["status"] != "PASS_STATIC_SCENE_CONTENT_AND_ROBOT_ARTICULATION_SELECTED":
        raise ValueError("OR97 did not establish the frozen factorization baseline")
    or119_closeout = json.loads((REPO_ROOT / contract["sources"]["or119_closeout"]["path"]).read_text())
    if or119_closeout["status"] != "TERMINAL_RETROSPECTIVE_TWO_MATERIAL_FINITE_OBJECT_FULL_TIMELINE_GATES_FAILED":
        raise ValueError("OR119 closeout does not authorize residual reconciliation")
    or119 = json.loads((REPO_ROOT / contract["sources"]["or119_receipt"]["path"]).read_text())
    frame_rows = json.loads((REPO_ROOT / contract["sources"]["or119_frame_rows"]["path"]).read_text())["rows"]
    or95_contract = json.loads((REPO_ROOT / contract["sources"]["or95_contract"]["path"]).read_text())
    episodes = _episode_inventory(or95_contract)
    video_map = {row["recording_id"]: row for row in or119["candidate_videos"]}
    prior_map = {row["recording_id"]: row for row in or97["rows"]}
    rows_by_episode = {episode["recording_id"]: [] for episode in episodes}
    for row in frame_rows:
        rows_by_episode[row["recording_id"]].append(row)
    for rows in rows_by_episode.values():
        rows.sort(key=lambda row: int(row["evaluation_index"]))

    occupancy = contract["edge_occupancy"]
    _, outside_mask = _region_masks(
        np.asarray(contract["regions"]["board_plus_margin"]["points_px"], dtype=np.float64),
        width=int(occupancy["width_px"]),
        height=int(occupancy["height_px"]),
        dilation_kernel_px=int(contract["regions"]["board_plus_margin"]["dilation_kernel_px_at_320x240"]),
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    result_rows: list[dict[str, Any]] = []
    physical_identity_matches = True
    for episode in episodes:
        recording_id = episode["recording_id"]
        bound_rows = rows_by_episode[recording_id]
        if [int(row["evaluation_index"]) for row in bound_rows] != list(range(len(bound_rows))):
            raise ValueError("OR120 evaluation indices drifted")
        indices = [int(row["physical_frame_index"]) for row in bound_rows]
        physical_binding = episode["physical_video"]
        physical_frames = [
            cv2.flip(frame, -1)
            for frame in _decode_selected_frames(
                REPO_ROOT / physical_binding["path"],
                selected_indices=np.asarray(indices, dtype=np.int64),
                expected_frame_count=int(physical_binding["frame_count"]),
                expected_width=int(physical_binding["width_px"]),
                expected_height=int(physical_binding["height_px"]),
                output_width=int(occupancy["width_px"]),
                output_height=int(occupancy["height_px"]),
            )
        ]
        candidate_binding = video_map[recording_id]
        if float(candidate_binding["fps"]) != 5.0 or int(candidate_binding["frame_count"]) != len(bound_rows):
            raise ValueError("OR120 candidate metadata drifted")
        candidate_path = REPO_ROOT / candidate_binding["path"]
        if sha256_file(candidate_path) != candidate_binding["sha256"]:
            raise ValueError("OR120 candidate video hash mismatch")
        candidate_frames = _read_video_frames(candidate_path, len(bound_rows))

        height = int(occupancy["height_px"])
        width = int(occupancy["width_px"])
        physical_edge_sum = np.zeros((height, width), dtype=np.uint32)
        candidate_edge_sum = np.zeros((height, width), dtype=np.uint32)
        for physical, candidate in zip(physical_frames, candidate_frames, strict=True):
            physical_edge_sum += cv2.Canny(
                cv2.cvtColor(physical, cv2.COLOR_BGR2GRAY),
                int(occupancy["canny_low_threshold"]),
                int(occupancy["canny_high_threshold"]),
            ) > 0
            candidate_edge_sum += cv2.Canny(
                cv2.cvtColor(candidate, cv2.COLOR_BGR2GRAY),
                int(occupancy["canny_low_threshold"]),
                int(occupancy["canny_high_threshold"]),
            ) > 0
        count = len(bound_rows)
        physical_fraction = physical_edge_sum.astype(np.float64) / count
        candidate_fraction = candidate_edge_sum.astype(np.float64) / count
        persistent_min = float(occupancy["persistent_minimum_frame_fraction"])
        dynamic_min = float(occupancy["dynamic_minimum_frame_fraction"])
        dynamic_max = float(occupancy["dynamic_maximum_frame_fraction_exclusive"])
        physical_persistent = physical_fraction >= persistent_min
        candidate_persistent = candidate_fraction >= persistent_min
        physical_dynamic = (physical_fraction >= dynamic_min) & (physical_fraction < dynamic_max)
        candidate_dynamic = (candidate_fraction >= dynamic_min) & (candidate_fraction < dynamic_max)
        tolerance = int(occupancy["tolerance_dilation_kernel_px"])
        persistent = _binary_tolerant_f1(physical_persistent, candidate_persistent, outside_mask, tolerance)
        dynamic = _binary_tolerant_f1(physical_dynamic, candidate_dynamic, outside_mask, tolerance)
        prior = prior_map[recording_id]
        physical_identity_matches = physical_identity_matches and (
            int(persistent["physical_pixels"]) == int(prior["persistent_outside_board"]["physical_pixels"])
            and int(dynamic["physical_pixels"]) == int(prior["dynamic_outside_board"]["physical_pixels"])
        )
        map_binding = _write_map(
            output_directory / f"{recording_id}-occupancy.png",
            [physical_persistent, candidate_persistent, physical_dynamic, candidate_dynamic],
        )
        result_rows.append(
            {
                "recording_id": recording_id,
                "split_position": int(episode["split_position"]),
                "frame_count": count,
                "persistent_outside_board": persistent,
                "dynamic_outside_board": dynamic,
                "persistent_f1_delta_vs_or97": float(persistent["f1"]) - float(prior["persistent_outside_board"]["f1"]),
                "dynamic_f1_delta_vs_or97": float(dynamic["f1"]) - float(prior["dynamic_outside_board"]["f1"]),
                "or97_physical_persistent_pixels": int(prior["persistent_outside_board"]["physical_pixels"]),
                "or97_physical_dynamic_pixels": int(prior["dynamic_outside_board"]["physical_pixels"]),
                "occupancy_map": map_binding,
            }
        )

    persistent_values = [float(row["persistent_outside_board"]["f1"]) for row in result_rows]
    dynamic_values = [float(row["dynamic_outside_board"]["f1"]) for row in result_rows]
    summary = _select_residual_family(persistent_values, dynamic_values, contract["dominance_rule"])
    summary["mean_persistent_f1_delta_vs_or97"] = float(np.mean([row["persistent_f1_delta_vs_or97"] for row in result_rows]))
    summary["mean_dynamic_f1_delta_vs_or97"] = float(np.mean([row["dynamic_f1_delta_vs_or97"] for row in result_rows]))
    selected = summary["selected_residual_family"]
    unresolved = contract["dominance_rule"]["otherwise_selects"]
    gates = {
        "exact_eleven_episode_pairs": len(result_rows) == int(contract["gates"]["expected_episode_count"]),
        "expected_total_physical_and_candidate_frames": sum(row["frame_count"] for row in result_rows) == int(contract["gates"]["expected_total_frame_count"]),
        "physical_occupancy_identity_matches_or97": physical_identity_matches,
        "single_residual_family_selected": selected != unresolved,
        "zero_render_fit_selection_threshold_change_replay_hardware_or_paid_compute": True,
        "retrospective_diagnostic_not_promotion": True,
    }
    if selected == contract["dominance_rule"]["persistent_dominant_selects"] and all(gates.values()):
        status = "PASS_PERSISTENT_STATIC_RESIDUAL_DOMINANT"
        reviewer_decision = "FREEZE_RENDERER_NATIVE_PERSISTENT_STATIC_SCENE_SUCCESSOR"
        next_transition = "freeze_or121_renderer_native_persistent_static_scene_successor"
    elif selected == contract["dominance_rule"]["dynamic_dominant_selects"] and all(gates.values()):
        status = "PASS_DYNAMIC_RESIDUAL_DOMINANT"
        reviewer_decision = "FREEZE_DYNAMIC_ROBOT_OPERATOR_ARTICULATION_SUCCESSOR"
        next_transition = "freeze_or121_dynamic_robot_operator_articulation_successor"
    else:
        status = "TERMINAL_POST_OBJECT_RESIDUAL_RECONCILIATION_UNRESOLVED"
        reviewer_decision = "CLOSE_RETAINED_POST_OBJECT_SUCCESSOR_LANE"
        next_transition = None

    receipt: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_post_object_full_timeline_residual_reconciliation_receipt.v1",
        "experiment_id": contract["experiment_id"],
        "status": status,
        "proof_class": contract["proof_class"],
        "contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)},
        "rows": result_rows,
        "summary": summary,
        "gates": gates,
        "execution": {
            "already_open_physical_video_decodes": 11,
            "existing_or119_candidate_video_decodes": 11,
            "physical_frames_read": sum(row["frame_count"] for row in result_rows),
            "candidate_frames_read": sum(row["frame_count"] for row in result_rows),
            "occupancy_map_outputs": len(result_rows),
            "renders": 0,
            "fits": 0,
            "candidate_selections": 0,
            "threshold_changes": 0,
            "simulator_replays": 0,
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
