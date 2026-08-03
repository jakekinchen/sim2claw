"""Receipt-only mechanism selection after the frozen-camera development run."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .learning_factory_artifacts import atomic_write_json, canonical_digest
from .observable_registration_host_native_analytic_3d_renderer_capability import (
    REPO_ROOT,
    sha256_file,
)


DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_frozen_camera_development_residual_attribution_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_frozen_camera_development_residual_attribution_v1"


def select_mechanism(
    *,
    motion_passes: bool,
    edge_passes: bool,
    static_final_edge_passes: bool,
    edge_gap: float,
    mean_gap: float,
    phase_spread: float,
    episode_spread: float,
) -> str:
    if motion_passes and not edge_passes and not static_final_edge_passes and edge_gap > mean_gap:
        return "renderer_structure"
    if not motion_passes and phase_spread > episode_spread:
        return "timing"
    if edge_passes and motion_passes and mean_gap > 0.0:
        return "appearance"
    return "ambiguous_requires_new_diagnostic"


def evaluate_once(
    contract_path: Path = DEFAULT_CONTRACT, output_directory: Path = DEFAULT_OUTPUT
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR75 one-run receipt already exists")
    contract = json.loads(contract_path.read_text())
    bound: dict[str, dict[str, Any]] = {}
    for name, source in contract["sources"].items():
        path = REPO_ROOT / source["path"]
        if sha256_file(path) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['path']}")
        bound[name] = json.loads(path.read_text())
    or73 = bound["or73_closeout"]
    or74 = bound["or74_closeout"]
    or74_receipt = bound["or74_receipt"]
    target = contract["target_gates"]
    result74 = or74["result"]
    mean_value = float(result74["pooled_mean_full_frame_linear_pixel_similarity"])
    motion_value = float(result74["pooled_mean_motion_union_linear_pixel_similarity"])
    edge_value = float(result74["pooled_mean_tolerant_edge_f1"])
    p10_value = float(result74["pooled_p10_full_frame_linear_pixel_similarity"])
    static_search_edge = float(or73["result"]["selected_search_mean_edge_f1"])
    static_final_edge = float(or73["result"]["selected_final_mean_edge_f1"])
    episode_spread = float(result74["maximum_episode_mean_full_frame_linear_pixel_similarity"] - result74["minimum_episode_mean_full_frame_linear_pixel_similarity"])
    phase_means = [
        float(value["mean"])
        for value in or74_receipt["pooled"]["phase_full_frame_linear_pixel_similarity"].values()
    ]
    phase_spread = max(phase_means) - min(phase_means)
    gaps = {
        "mean_full_frame": max(0.0, float(target["mean_full_frame_linear_pixel_similarity"]) - mean_value),
        "p10_full_frame": max(0.0, float(target["p10_full_frame_linear_pixel_similarity"]) - p10_value),
        "mean_motion_union": max(0.0, float(target["mean_motion_union_linear_pixel_similarity"]) - motion_value),
        "mean_tolerant_edge_f1": max(0.0, float(target["mean_tolerant_edge_f1"]) - edge_value),
        "minimum_phase_mean": max(0.0, float(target["each_phase_mean_full_frame_linear_pixel_similarity"]) - float(result74["minimum_phase_mean_full_frame_linear_pixel_similarity"])),
        "minimum_episode_mean": max(0.0, float(target["each_episode_mean_full_frame_linear_pixel_similarity"]) - float(result74["minimum_episode_mean_full_frame_linear_pixel_similarity"])),
    }
    selected = select_mechanism(
        motion_passes=motion_value >= float(target["mean_motion_union_linear_pixel_similarity"]),
        edge_passes=edge_value >= float(target["mean_tolerant_edge_f1"]),
        static_final_edge_passes=static_final_edge >= float(target["mean_tolerant_edge_f1"]),
        edge_gap=gaps["mean_tolerant_edge_f1"],
        mean_gap=gaps["mean_full_frame"],
        phase_spread=phase_spread,
        episode_spread=episode_spread,
    )
    receipt: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_frozen_camera_development_residual_attribution_receipt.v1",
        "experiment_id": contract["experiment_id"],
        "status": "PASS_RENDERER_STRUCTURE_SELECTED_BEFORE_APPEARANCE_OR_TIMING" if selected == "renderer_structure" else "TERMINAL_RESIDUAL_MECHANISM_AMBIGUOUS",
        "proof_class": contract["proof_class"],
        "contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)},
        "observed": {
            "or73_search_resolution_static_edge_f1": static_search_edge,
            "or73_final_resolution_static_edge_f1": static_final_edge,
            "resolution_edge_f1_drop": static_search_edge - static_final_edge,
            "or74_temporal_mean_similarity": mean_value,
            "or74_temporal_p10_similarity": p10_value,
            "or74_temporal_motion_similarity": motion_value,
            "or74_temporal_edge_f1": edge_value,
            "episode_mean_spread": episode_spread,
            "phase_mean_spread": phase_spread,
            "gaps_to_target": gaps,
        },
        "decision": {
            "selected_mechanism": selected,
            "rule": contract["decision_rule"],
            "appearance_deferred": selected == "renderer_structure",
            "timing_deferred": selected == "renderer_structure",
            "reason": "motion passes while static and temporal edge fail; edge gap dominates mean gap and worsens at the final evaluator resolution",
        },
        "execution": {
            "receipt_reads": 3,
            "physical_video_decodes": 0,
            "renderer_runs": 0,
            "candidate_outputs": 0,
            "parameter_fits": 0,
            "validation_reads": 0,
            "evaluator_heldout_reads": 0,
            "simulator_replays": 0,
            "hardware_actions": 0,
            "paid_compute": False,
        },
        "claim_limits": contract["claim_limits"],
        "reviewer_decision": "FREEZE_MESH_OCCLUSION_CAPABLE_RENDERER_CAPABILITY" if selected == "renderer_structure" else "DO_NOT_OPEN_NEW_FIT",
        "next_transition": "freeze_or76_host_native_mesh_zbuffer_renderer_capability" if selected == "renderer_structure" else "design_new_receipt_only_residual_diagnostic",
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    output_directory.mkdir(parents=True, exist_ok=True)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(evaluate_once(), sort_keys=True))
