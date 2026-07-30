"""Evaluate the prior board yaw after canonical-rank hardcutover migration."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from .learning_factory_artifacts import FactoryArtifactError, atomic_write_json, canonical_digest, load_json_object
from .observable_registration_belief_recalculation import REPO_ROOT, _bound_json, _bound_path
from .post_hackathon_home_workspace_geometry_camera import _contact_phase_candidate, load_geometry_camera_contract

SCHEMA = "sim2claw.observable_registration_orientation_migrated_yaw_contract.v1"
RECEIPT_SCHEMA = "sim2claw.observable_registration_orientation_migrated_yaw_receipt.v1"
CONTRACT_PATH = REPO_ROOT / "configs/evaluations/observable_registration_orientation_migrated_yaw_v1.json"
OUTPUT_DIRECTORY = REPO_ROOT / "outputs/observable_registration_orientation_migrated_yaw_v1"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def load_orientation_migrated_yaw_contract(path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT) -> dict[str, Any]:
    contract = load_json_object(path, label="orientation-migrated yaw")
    _require(contract.get("schema_version") == SCHEMA, "unsupported contract")
    for name, binding in contract["sources"].items():
        _bound_path(binding, root=root, label=name)
    yaw = contract["yaw_migration"]
    _require(yaw["fit_allowed"] is False, "yaw fit widened")
    _require(abs(yaw["historical_pre_cutover_yaw_degrees"] - yaw["canonical_rank_flip_degrees"] - yaw["migrated_yaw_degrees"]) < 1e-12, "yaw migration drifted")
    _require(not any(contract["authority"].values()), "authority widened")
    return contract


def evaluate_orientation_migrated_yaw(contract: dict[str, Any], *, root: Path = REPO_ROOT) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    sources = contract["sources"]
    or16 = _bound_json(sources["or16_receipt"], root=root, label="OR16")
    historical = _bound_json(sources["historical_mapping_receipt"], root=root, label="historical mapping")
    yaw = contract["yaw_migration"]
    _require(historical["mapping"]["candidate"]["board_yaw_relative_to_table_degrees"] == yaw["historical_pre_cutover_yaw_degrees"], "historical yaw drifted")
    scene_path = _bound_path(sources["or13_scene"], root=root, label="OR13 scene")
    scene = copy.deepcopy(load_json_object(scene_path, label="OR13 scene"))
    _require(scene["simulation_estimates"]["board"]["yaw_relative_to_table_degrees"] == yaw["current_unapproved_yaw_degrees"], "current yaw drifted")
    scene["simulation_estimates"]["board"]["yaw_relative_to_table_degrees"] = yaw["migrated_yaw_degrees"]
    derived_path = OUTPUT_DIRECTORY / "derived_scene_config.json"
    atomic_write_json(derived_path, scene)
    or13 = _bound_json(sources["or13_receipt"], root=root, label="OR13")
    or13_contract, _ = load_geometry_camera_contract(_bound_path(sources["or13_contract"], root=root, label="OR13 contract"), root=root)
    offsets = historical["mapping"]["candidate"]["joint_zero_offsets_rad"]
    phase, trace = _contact_phase_candidate(
        contract=or13_contract,
        scene_path=derived_path,
        pawn_height_m=float(or13["board_object_geometry"]["pawn_height_m"]),
        board_thickness_m=float(scene["simulation_estimates"]["board"]["thickness_m"]),
        root=root,
        joint_zero_overrides={i: float(v) for i, v in enumerate(offsets)},
    )
    latest = contract["contact_phase_gate"]["precontact_latest_sample"]
    clear = not any(row["phase_contact_geometry_pass"] for row in trace["rows"] if row["source_sample_index"] <= latest)
    passed = bool(clear and phase["contact_at_expected_phase"])
    before = or16["contact_phase"]["sample_232"]
    after = phase["sample_232"]
    receipt = {
        "schema_version": RECEIPT_SCHEMA, "experiment_id": contract["experiment_id"], "proof_class": contract["proof_class"],
        "status": "PASS_STATIC_NAMED_CONTACT_QUARANTINED_NO_DYNAMICS" if passed else "TERMINAL_NEGATIVE_NO_PHASE_CORRECT_NAMED_CONTACT",
        "yaw_migration": yaw,
        "contact_phase": {**phase, "precontact_clear_through_sample_224": clear, "static_gate_passed": passed},
        "sample_232_change_from_or16": {
            "planar_midpoint_error_before_m": before["midpoint_to_pawn_planar_distance_m"], "planar_midpoint_error_after_m": after["midpoint_to_pawn_planar_distance_m"],
            "vertical_residual_before_m": before["midpoint_to_pawn_vector_m"][2], "vertical_residual_after_m": after["midpoint_to_pawn_vector_m"][2],
            "fixed_jaw_gap_before_m": before["fixed_signed_distance_m"], "fixed_jaw_gap_after_m": after["fixed_signed_distance_m"],
            "moving_jaw_gap_before_m": before["moving_signed_distance_m"], "moving_jaw_gap_after_m": after["moving_signed_distance_m"]
        },
        "actions_changed": False,
        "yaw_fit": False, "physics_integration_steps": 0, "dynamic_replays": 0, "global_mapping_approved": False, "authority": contract["authority"]
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    return receipt, trace, scene


def build_orientation_migrated_yaw_receipt(contract_path: Path = CONTRACT_PATH, output_directory: Path = OUTPUT_DIRECTORY, *, root: Path = REPO_ROOT) -> dict[str, Any]:
    contract = load_orientation_migrated_yaw_contract(contract_path, root=root)
    receipt, trace, _ = evaluate_orientation_migrated_yaw(contract, root=root)
    atomic_write_json(output_directory / "trace.json", trace)
    atomic_write_json(output_directory / "receipt.json", receipt)
    return receipt


def main() -> int:
    build_orientation_migrated_yaw_receipt()
    return 0
