"""Attribute the complete OR95 temporal residual from immutable receipts only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .learning_factory_artifacts import atomic_write_json, canonical_digest
from .observable_registration_host_native_analytic_3d_renderer_capability import REPO_ROOT, sha256_file


SCHEMA = "sim2claw.observable_registration_post_final_temporal_robot_residual_attribution_contract.v1"
DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_post_final_temporal_robot_residual_attribution_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_post_final_temporal_robot_residual_attribution_v1"


def load_post_final_temporal_robot_residual_attribution_contract(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    contract = json.loads(path.read_text())
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("unsupported OR96 contract")
    for source in contract["sources"].values():
        if sha256_file(REPO_ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['path']}")
    resources = contract["resource_boundary"]
    zero_keys = ("physical_frame_reads_allowed", "physical_video_decodes_allowed", "renders_allowed", "fits_allowed", "candidate_selections_allowed", "simulator_replays_allowed", "hardware_actions_allowed")
    if any(resources[key] != 0 for key in zero_keys) or resources["paid_compute_allowed"] is not False or any(contract["authority"].values()):
        raise ValueError("OR96 resource or authority boundary drifted")
    if contract["claim_limits"]["same_video_semantic_match"] is not False or contract["claim_limits"]["untouched_cohort_remaining"] is not False:
        raise ValueError("OR96 claim boundary drifted")
    return contract


def evaluate_once(contract_path: Path = DEFAULT_CONTRACT, output_directory: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR96 one-run receipt already exists")
    contract = load_post_final_temporal_robot_residual_attribution_contract(contract_path)
    or94 = json.loads((REPO_ROOT / contract["sources"]["or94_receipt"]["path"]).read_text())
    or95_closeout = json.loads((REPO_ROOT / contract["sources"]["or95_closeout"]["path"]).read_text())
    or95 = json.loads((REPO_ROOT / contract["sources"]["or95_receipt"]["path"]).read_text())
    frame_rows = json.loads((REPO_ROOT / contract["sources"]["or95_frame_rows"]["path"]).read_text())
    if frame_rows["frame_count"] != 1210 or len(frame_rows["rows"]) != 1210:
        raise ValueError("OR96 frame-row manifest count drifted")
    if or95_closeout["status"] != "TERMINAL_RETROSPECTIVE_FULL_CORPUS_SAME_VIDEO_TEMPORAL_REGION_GATES_FAILED":
        raise ValueError("OR95 residual prerequisite drifted")
    acceptance = json.loads((REPO_ROOT / or95["contract"]["path"]).read_text())["same_video_acceptance"]
    pooled = or95["pooled"]
    outside_mean = float(pooled["outside_board_edge_f1"]["mean"])
    board_mean = float(pooled["board_plus_margin_edge_f1"]["mean"])
    outside_target = float(acceptance["minimum_pooled_mean_outside_board_edge_f1"])
    board_target = float(acceptance["minimum_pooled_mean_board_plus_margin_edge_f1"])
    outside_gap = max(0.0, outside_target - outside_mean)
    board_gap = max(0.0, board_target - board_mean)
    episode_means = [float(row["outside_board_edge_f1"]["mean"]) for row in or95["episode_summaries"]]
    episode_range = max(episode_means) - min(episode_means)
    base_gain = float(or94["summary"]["selected_minus_baseline_mean_outside_board_edge_f1"])
    baseline_outside = float(or94["summary"]["baseline_mean_outside_board_edge_f1"])
    baseline_gap = outside_target - baseline_outside
    recovered_fraction = base_gain / baseline_gap
    rule = contract["decision_rule"]["select_robot_articulation_and_scene_content_factorization_if"]
    facts = {
        "motion_union_gate_passes": bool(or95["metric_gates"]["pooled_mean_motion_union_linear_pixel_similarity"]),
        "every_phase_full_frame_gate_passes": bool(or95["metric_gates"]["each_phase_mean_full_frame_linear_pixel_similarity"]),
        "outside_board_mean_gap_to_target": outside_gap,
        "board_mean_gap_to_target": board_gap,
        "outside_to_board_mean_gap_ratio": outside_gap / board_gap if board_gap > 0.0 else float("inf"),
        "episode_outside_board_mean_range": episode_range,
        "rigid_base_outside_board_gain": base_gain,
        "rigid_base_fraction_of_baseline_to_target_gap_recovered": recovered_fraction,
    }
    gates = {
        "motion_union_gate_passes": facts["motion_union_gate_passes"] is rule["motion_union_gate_passes"],
        "every_phase_full_frame_gate_passes": facts["every_phase_full_frame_gate_passes"] is rule["every_phase_full_frame_gate_passes"],
        "outside_board_mean_gap_is_large": outside_gap >= float(rule["minimum_outside_board_mean_gap_to_target"]),
        "outside_gap_dominates_board_gap": facts["outside_to_board_mean_gap_ratio"] >= float(rule["minimum_outside_to_board_mean_gap_ratio"]),
        "episode_outside_board_means_are_tightly_clustered": episode_range <= float(rule["maximum_episode_outside_board_mean_range"]),
        "rigid_base_gain_is_positive": base_gain >= float(rule["minimum_positive_rigid_base_outside_board_gain"]),
        "rigid_base_recovers_less_than_one_quarter_of_gap": recovered_fraction <= float(rule["maximum_rigid_base_fraction_of_baseline_to_target_gap_recovered"]),
        "zero_pixel_decode_render_fit_selection_or_replay": True,
        "post_final_diagnostic_not_promotion": True,
    }
    selected = all(gates.values())
    mechanism = "robot_articulation_and_renderer_native_scene_content_factorization" if selected else ("temporal_control_or_state_alignment" if not facts["motion_union_gate_passes"] or not facts["every_phase_full_frame_gate_passes"] else "unresolved_robot_scene_residual")
    receipt: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_post_final_temporal_robot_residual_attribution_receipt.v1",
        "experiment_id": contract["experiment_id"],
        "status": "PASS_ROBOT_ARTICULATION_AND_SCENE_CONTENT_FACTORIZATION_SELECTED" if selected else "TERMINAL_TEMPORAL_ROBOT_RESIDUAL_UNRESOLVED",
        "proof_class": contract["proof_class"],
        "contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)},
        "facts": facts,
        "episode_outside_board_means": episode_means,
        "gates": gates,
        "selected_mechanism": mechanism,
        "execution": {"receipt_reads": 3, "frame_rows_manifest_reads": 1, "physical_frame_reads": 0, "physical_video_decodes": 0, "renders": 0, "fits": 0, "candidate_selections": 0, "simulator_replays": 0, "hardware_actions": 0, "paid_compute": False},
        "claim_limits": contract["claim_limits"],
        "reviewer_decision": "FREEZE_RENDERER_NATIVE_ROBOT_ARTICULATION_VS_SCENE_CONTENT_DIAGNOSTIC" if selected else "STOP_NO_MECHANISM_SELECTED",
        "next_transition": "freeze_or97_renderer_native_robot_articulation_vs_scene_content_diagnostic" if selected else None,
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(evaluate_once(), sort_keys=True))
