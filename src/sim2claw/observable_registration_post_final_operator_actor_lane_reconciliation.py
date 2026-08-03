"""Close or continue the operator-actor lane using immutable receipts only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .learning_factory_artifacts import atomic_write_json, canonical_digest
from .observable_registration_host_native_analytic_3d_renderer_capability import REPO_ROOT, sha256_file


SCHEMA = "sim2claw.observable_registration_post_final_operator_actor_lane_reconciliation_contract.v1"
DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_post_final_operator_actor_lane_reconciliation_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_post_final_operator_actor_lane_reconciliation_v1"


def load_post_final_operator_actor_lane_reconciliation_contract(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    contract = json.loads(path.read_text())
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("unsupported OR113 contract")
    for source in contract["sources"].values():
        if sha256_file(REPO_ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['path']}")
    tree = contract["decision_tree"]
    if tree["actor_lane_continues_only_if_any_tested_renderer_or_successor_shape_passes_material_edge_gates"] is not True:
        raise ValueError("OR113 actor continuation boundary drifted")
    if tree["outside_board_target_edge_f1"] != 0.6 or tree["static_gap_must_exceed_dynamic_gap_by_factor"] != 2.0:
        raise ValueError("OR113 residual decision boundary drifted")
    resources = contract["resource_boundary"]
    if resources != {"receipt_reads_allowed": 10, "pixel_reads_allowed": 0, "video_decodes_allowed": 0, "renders_allowed": 0, "fits_or_candidate_searches_allowed": 0, "simulator_replays_allowed": 0, "threshold_changes_allowed": 0, "hardware_actions_allowed": 0, "paid_compute_allowed": False}:
        raise ValueError("OR113 resource boundary drifted")
    if any(contract["authority"].values()) or contract["claim_limits"]["same_video_semantic_match"] is not False:
        raise ValueError("OR113 authority or claim boundary drifted")
    return contract


def _select(
    *,
    actor_passed: bool,
    static_gap: float,
    dynamic_gap: float,
    maximum_static_primitive_gain: float,
    tree: dict[str, Any],
) -> tuple[str, str, str]:
    if actor_passed:
        return "CONTINUE_TESTED_ACTOR_LANE", "FREEZE_TESTED_ACTOR_FULL_TIMELINE", "freeze_or114_tested_actor_full_timeline"
    if (
        static_gap >= float(tree["static_gap_must_exceed_dynamic_gap_by_factor"]) * dynamic_gap
        and maximum_static_primitive_gain < float(tree["existing_static_primitive_material_gain_threshold"])
    ):
        return (
            "CLOSE_ACTOR_LANE_SELECT_PERSISTENT_STATIC_ENCLOSURE_BOUNDARY_LINES",
            "FREEZE_PERSISTENT_STATIC_ENCLOSURE_BOUNDARY_LINE_IDENTIFIABILITY",
            "freeze_or114_persistent_static_enclosure_boundary_line_identifiability",
        )
    return "CLOSE_ACTOR_LANE_SELECT_ROBOT_DYNAMIC_RESIDUAL", "FREEZE_ROBOT_DYNAMIC_RESIDUAL_RECONCILIATION", "freeze_or114_robot_dynamic_residual_reconciliation"


def evaluate_once(contract_path: Path = DEFAULT_CONTRACT, output_directory: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR113 one-run receipt already exists")
    contract = load_post_final_operator_actor_lane_reconciliation_contract(contract_path)
    receipts: dict[str, dict[str, Any]] = {}
    for name, source in contract["sources"].items():
        value = json.loads((REPO_ROOT / source["path"]).read_text())
        expected_artifact = source.get("artifact_sha256")
        if expected_artifact is not None and value.get("artifact_sha256") != expected_artifact:
            raise ValueError(f"OR113 artifact identity drifted: {name}")
        receipts[name] = value
    if receipts["or112_closeout"]["reviewer_decision"] != "REJECT_TWO_PART_SHAPE_AND_RECONCILE_OPERATOR_ACTOR_LANE":
        raise ValueError("OR112 did not authorize reconciliation")
    or110 = receipts["or110_receipt"]
    or111 = receipts["or111_receipt"]
    or112 = receipts["or112_receipt"]
    actor_passed = or110["status"] == "PASS_RENDERER_NATIVE_SINGLE_CAPSULE_OPERATOR_RECONSTRUCTION_VALIDATED" or or112["status"] == "PASS_TWO_PART_HAND_FOREARM_SHAPE_IDENTIFIABLE"
    or97 = receipts["or97_receipt"]
    target = float(contract["decision_tree"]["outside_board_target_edge_f1"])
    persistent_f1 = float(or97["summary"]["mean_persistent_outside_board_edge_occupancy_f1"])
    dynamic_f1 = float(or97["summary"]["mean_dynamic_outside_board_edge_occupancy_f1"])
    static_gap = max(0.0, target - persistent_f1)
    dynamic_gap = max(0.0, target - dynamic_f1)
    or99_gain = float(receipts["or99_receipt"]["summary"]["outside_board_edge_f1_delta"])
    or100_gain = float(receipts["or100_receipt"]["development_summary"]["outside_board_edge_f1_delta"])
    maximum_static_primitive_gain = max(or99_gain, or100_gain)
    selection, reviewer_decision, next_transition = _select(
        actor_passed=actor_passed,
        static_gap=static_gap,
        dynamic_gap=dynamic_gap,
        maximum_static_primitive_gain=maximum_static_primitive_gain,
        tree=contract["decision_tree"],
    )
    actor_lane = {
        "continued": actor_passed,
        "or110_status": or110["status"],
        "or110_present_mean_full_frame_similarity_delta": float(or110["development_summary"]["present_mean_full_frame_linear_similarity_delta"]),
        "or110_present_mean_outside_board_edge_f1_delta": float(or110["development_summary"]["present_mean_outside_board_edge_f1_delta"]),
        "or111_attribution": or111["attribution"],
        "or112_status": or112["status"],
        "or112_validation_mean_iou_gain": float(or112["validation_summary"]["mean_iou_gain_over_single"]),
        "or112_validation_mean_local_edge_f1_gain": float(or112["validation_summary"]["mean_local_physical_edge_f1_gain_over_single"]),
        "closure_reason": None if actor_passed else "no_tested_actor_renderer_or_successor_shape_passed_material_edge_gates",
    }
    residuals = {
        "target_outside_board_edge_f1": target,
        "persistent_static_f1": persistent_f1,
        "robot_dynamic_f1": dynamic_f1,
        "persistent_static_gap": static_gap,
        "robot_dynamic_gap": dynamic_gap,
        "persistent_to_dynamic_gap_ratio": float(static_gap / max(dynamic_gap, 1e-12)),
        "or99_shell_gain": or99_gain,
        "or100_plane_gain": or100_gain,
        "maximum_existing_static_primitive_gain": maximum_static_primitive_gain,
    }
    gates = {
        "exact_ten_receipt_or_closeout_reads": len(receipts) == int(contract["resource_boundary"]["receipt_reads_allowed"]),
        "actor_continuation_requires_material_gate_pass": actor_passed == (or110["status"].startswith("PASS_") or or112["status"].startswith("PASS_")),
        "one_successor_selected": selection in {"CONTINUE_TESTED_ACTOR_LANE", "CLOSE_ACTOR_LANE_SELECT_PERSISTENT_STATIC_ENCLOSURE_BOUNDARY_LINES", "CLOSE_ACTOR_LANE_SELECT_ROBOT_DYNAMIC_RESIDUAL"},
        "zero_pixel_read_decode_render_fit_search_replay_threshold_change_hardware_or_paid_compute": True,
        "lane_selection_not_same_video_predictive_simulation_physics_transfer_or_promotion": True,
    }
    passed = all(gates.values())
    receipt: dict[str, Any] = {
        "schema_version": "sim2claw.observable_registration_post_final_operator_actor_lane_reconciliation_receipt.v1",
        "experiment_id": contract["experiment_id"],
        "status": "PASS_OPERATOR_ACTOR_LANE_RECONCILED" if passed else "TERMINAL_OPERATOR_ACTOR_LANE_RECONCILIATION_INTEGRITY_FAILED",
        "proof_class": contract["proof_class"],
        "contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)},
        "actor_lane": actor_lane,
        "remaining_residuals": residuals,
        "selected_successor": selection if passed else None,
        "gates": gates,
        "execution": {"receipt_or_closeout_reads": len(receipts), "pixel_reads": 0, "video_decodes": 0, "renders": 0, "fits_or_candidate_searches": 0, "simulator_replays": 0, "threshold_changes": 0, "hardware_actions": 0, "paid_compute": False},
        "claim_limits": contract["claim_limits"],
        "reviewer_decision": reviewer_decision if passed else "STOP_POST_FINAL_RESIDUAL_LANES",
        "next_transition": next_transition if passed else "stop_post_final_residual_lanes",
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    output_directory.mkdir(parents=True, exist_ok=True)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(evaluate_once(), sort_keys=True))
