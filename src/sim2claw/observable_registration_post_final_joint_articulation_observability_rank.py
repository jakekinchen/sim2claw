"""Rank trace-only joint articulation families by projected observability."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from .learning_factory_artifacts import atomic_write_json, canonical_digest
from .observable_registration_board_anchored_workcell_se2_static_development_fit import _project_points_roll
from .observable_registration_host_native_analytic_3d_renderer_capability import REPO_ROOT, quaternion_matrix_wxyz, sha256_file
from .observable_registration_post_final_independent_left_right_robot_base_se2_diagnostic import _independently_registered_trace
from .observable_registration_post_final_independent_robot_base_full_corpus_diagnostic import _episode_inventory


SCHEMA = "sim2claw.observable_registration_post_final_joint_articulation_observability_rank_contract.v1"
DEFAULT_CONTRACT = REPO_ROOT / "configs/evaluations/observable_registration_post_final_joint_articulation_observability_rank_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "outputs/observable_registration_post_final_joint_articulation_observability_rank_v1"


def load_post_final_joint_articulation_observability_rank_contract(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    contract = json.loads(path.read_text())
    if contract.get("schema_version") != SCHEMA:
        raise ValueError("unsupported OR103 contract")
    for source in contract["sources"].values():
        if sha256_file(REPO_ROOT / source["path"]) != source["sha256"]:
            raise ValueError(f"source hash mismatch: {source['path']}")
    if contract["development_positions"] != list(range(1, 8)):
        raise ValueError("OR103 development split drifted")
    names = [row["name"] for row in contract["joint_families"]]
    if names != ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper"]:
        raise ValueError("OR103 joint family drifted")
    resources = contract["resource_boundary"]
    closed = ("physical_video_decodes_allowed", "candidate_video_decodes_allowed", "renders_allowed", "fits_allowed", "parameter_values_allowed", "simulator_replays_allowed", "action_or_state_mutations_allowed", "hardware_actions_allowed")
    if any(resources[key] != 0 for key in closed) or resources["paid_compute_allowed"] is not False:
        raise ValueError("OR103 resource boundary drifted")
    if any(contract["authority"].values()) or contract["claim_limits"]["same_video_semantic_match"] is not False:
        raise ValueError("OR103 authority or claim boundary drifted")
    return contract


def _rotation_excursion(rotations: list[np.ndarray]) -> float:
    initial = rotations[0]
    angles = []
    for rotation in rotations:
        delta = initial.T @ rotation
        cosine = np.clip((float(np.trace(delta)) - 1.0) * 0.5, -1.0, 1.0)
        angles.append(float(np.arccos(cosine)))
    return float(np.percentile(np.asarray(angles, dtype=np.float64), 95.0))


def evaluate_once(contract_path: Path = DEFAULT_CONTRACT, output_directory: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    if receipt_path.exists():
        raise ValueError("OR103 one-run receipt already exists")
    contract = load_post_final_joint_articulation_observability_rank_contract(contract_path)
    or102 = json.loads((REPO_ROOT / contract["sources"]["or102_closeout"]["path"]).read_text())
    if or102["reviewer_decision"] != "REJECT_GLOBAL_LAG_AND_FREEZE_JOINT_ARTICULATION_CALIBRATION":
        raise ValueError("OR102 did not authorize joint articulation work")
    scene_binding = contract["sources"]["shared_scene_manifest"]
    scene = json.loads((REPO_ROOT / scene_binding["path"]).read_text())
    if scene["revision_sha256"] != scene_binding["revision_sha256"]:
        raise ValueError("scene revision mismatch")
    body_by_id = {int(body["id"]): body for body in scene["bodies"]}
    or95_contract = json.loads((REPO_ROOT / contract["sources"]["or95_contract"]["path"]).read_text())
    frozen = or95_contract["frozen_candidate"]
    episodes = [episode for episode in _episode_inventory(or95_contract) if int(episode["split_position"]) in contract["development_positions"]]
    camera = frozen["camera"]
    static = frozen["static_workcell_transform"]
    left_ids = [int(value) for value in frozen["left_robot_transform"]["transformed_body_ids"]]
    right_ids = [int(value) for value in frozen["right_robot_transform"]["transformed_body_ids"]]
    base_vector = np.asarray(frozen["left_robot_transform"]["vector"] + frozen["right_robot_transform"]["vector"], dtype=np.float64)
    prepared: list[tuple[dict[str, Any], dict[str, Any]]] = []
    total_frames = 0
    for episode in episodes:
        binding = episode["state_trace"]
        if sha256_file(REPO_ROOT / binding["path"]) != binding["sha256"]:
            raise ValueError("OR103 trace hash mismatch")
        trace = json.loads((REPO_ROOT / binding["path"]).read_text())
        transformed_frames = []
        for frame in trace["frames"]:
            one = {"body_names": trace["body_names"], "frames": [frame]}
            transformed_frames.append(_independently_registered_trace(one, anchor_body_id=int(static["anchor_body_id"]), left_body_ids=left_ids, right_body_ids=right_ids, vector=base_vector)["frames"][0])
        transformed = {"body_names": trace["body_names"], "frames": transformed_frames}
        prepared.append((episode, transformed))
        total_frames += len(trace["frames"])
    family_rows: list[dict[str, Any]] = []
    endpoint_ids = {"left": int(contract["endpoint_body_ids"]["left"]), "right": int(contract["endpoint_body_ids"]["right"])}
    for family_index, family in enumerate(contract["joint_families"]):
        rows: list[dict[str, Any]] = []
        for episode, trace in prepared:
            for side in ("left", "right"):
                body_id = int(family[f"{side}_body_id"])
                parent_id = int(family[f"{side}_parent_id"])
                if int(body_by_id[body_id]["parent_id"]) != parent_id:
                    raise ValueError("OR103 scene ancestry drifted")
                endpoint_id = endpoint_ids[side]
                relative_rotations: list[np.ndarray] = []
                projected_leverage: list[float] = []
                for frame in trace["frames"]:
                    positions = np.asarray(frame["p"], dtype=np.float64).reshape((-1, 3))
                    rotations = [quaternion_matrix_wxyz(value) for value in np.asarray(frame["q"], dtype=np.float64).reshape((-1, 4))]
                    relative_rotations.append(rotations[parent_id].T @ rotations[body_id])
                    pixels, depth = _project_points_roll(np.stack([positions[body_id], positions[endpoint_id]]), camera, 320, 240)
                    if np.any(depth <= 1e-6):
                        raise ValueError("OR103 robot body behind camera")
                    projected_leverage.append(float(np.linalg.norm(pixels[1] - pixels[0])))
                excursion = _rotation_excursion(relative_rotations)
                leverage = float(np.median(np.asarray(projected_leverage, dtype=np.float64)))
                rows.append({"recording_id": episode["recording_id"], "split_position": int(episode["split_position"]), "side": side, "relative_rotation_excursion_rad": excursion, "projected_leverage_px": leverage, "observability_score_px_rad": excursion * leverage})
        family_rows.append({"family": family["name"], "declared_order": family_index, "rows": rows, "mean_observability_score_px_rad": float(np.mean([row["observability_score_px_rad"] for row in rows])), "median_rotation_excursion_rad": float(np.median([row["relative_rotation_excursion_rad"] for row in rows])), "median_projected_leverage_px": float(np.median([row["projected_leverage_px"] for row in rows])), "episode_side_rows_with_rotation_excursion_at_least_0p05_rad": sum(row["relative_rotation_excursion_rad"] >= 0.05 for row in rows), "episode_side_rows_with_projected_leverage_at_least_5px": sum(row["projected_leverage_px"] >= 5.0 for row in rows)})
    selected = max(family_rows, key=lambda row: (row["mean_observability_score_px_rad"], -row["declared_order"]))
    acceptance = contract["acceptance"]
    selection_gates = {"minimum_observability_score": selected["mean_observability_score_px_rad"] >= float(acceptance["minimum_selected_observability_score_px_rad"]), "minimum_rows_with_rotation_excursion": selected["episode_side_rows_with_rotation_excursion_at_least_0p05_rad"] >= int(acceptance["minimum_episode_side_rows_with_rotation_excursion_at_least_0p05_rad"]), "minimum_rows_with_projected_leverage": selected["episode_side_rows_with_projected_leverage_at_least_5px"] >= int(acceptance["minimum_episode_side_rows_with_projected_leverage_at_least_5px"])}
    integrity_gates = {"exact_seven_development_traces": len(prepared) == 7, "exact_six_joint_families": len(family_rows) == 6, "scene_ancestry_verified": True, "one_shared_family_selected": True, "zero_pixel_decode_render_fit_parameter_value_replay_action_state_mutation_hardware_or_paid_compute": True, "post_final_observability_not_fidelity_or_promotion": True}
    passed = all(selection_gates.values()) and all(integrity_gates.values())
    receipt: dict[str, Any] = {"schema_version": "sim2claw.observable_registration_post_final_joint_articulation_observability_rank_receipt.v1", "experiment_id": contract["experiment_id"], "status": "PASS_JOINT_ARTICULATION_FAMILY_SELECTED" if passed else "TERMINAL_JOINT_ARTICULATION_OBSERVABILITY_INSUFFICIENT", "proof_class": contract["proof_class"], "contract": {"path": str(contract_path.relative_to(REPO_ROOT)), "sha256": sha256_file(contract_path)}, "family_rows": family_rows, "selected_family": selected["family"], "selected_summary": {key: value for key, value in selected.items() if key != "rows"}, "gates": {"selection": selection_gates, "integrity": integrity_gates}, "execution": {"state_trace_reads": len(prepared), "trace_frames_read": total_frames, "physical_video_decodes": 0, "candidate_video_decodes": 0, "renders": 0, "fits": 0, "parameter_values": 0, "simulator_replays": 0, "action_or_state_mutations": 0, "hardware_actions": 0, "paid_compute": False}, "claim_limits": contract["claim_limits"], "reviewer_decision": "FREEZE_SELECTED_SHARED_JOINT_FAMILY_CALIBRATION" if passed else "STOP_JOINT_ARTICULATION_LANE", "next_transition": f"freeze_or104_shared_{selected['family']}_articulation_calibration" if passed else "stop_joint_articulation_lane"}
    receipt["artifact_sha256"] = canonical_digest(receipt)
    output_directory.mkdir(parents=True, exist_ok=True)
    atomic_write_json(receipt_path, receipt)
    return receipt


if __name__ == "__main__":
    print(json.dumps(evaluate_once(), sort_keys=True))
