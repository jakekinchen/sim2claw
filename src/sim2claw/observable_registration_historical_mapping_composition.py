"""Evaluate a quarantined historical body mapping under OR13 static geometry."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
)
from .observable_registration_belief_recalculation import (
    REPO_ROOT,
    _bound_json,
    _bound_path,
)
from .post_hackathon_home_workspace_geometry_camera import (
    _contact_phase_candidate,
    load_geometry_camera_contract,
)


SCHEMA = "sim2claw.observable_registration_historical_mapping_composition_contract.v1"
RECEIPT_SCHEMA = (
    "sim2claw.observable_registration_historical_mapping_composition_receipt.v1"
)
CONTRACT_PATH = (
    REPO_ROOT
    / "configs/evaluations/observable_registration_historical_mapping_composition_v1.json"
)
OUTPUT_DIRECTORY = (
    REPO_ROOT
    / "outputs/observable_registration_historical_mapping_composition_v1"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def load_historical_mapping_composition_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="historical mapping composition")
    _require(contract.get("schema_version") == SCHEMA, "unsupported contract")
    for source_id, binding in contract["sources"].items():
        _bound_path(binding, root=root, label=source_id)
    mapping = contract["frozen_mapping"]
    _require(mapping["refit_allowed"] is False, "mapping refit widened")
    _require(
        mapping["global_mapping_approved"] is False,
        "mapping promotion widened",
    )
    _require(
        len(mapping["joint_zero_offsets_rad"]) == 5,
        "mapping width changed",
    )
    _require(
        contract["contact_phase_gate"]["physics_integration_allowed"] is False
        and contract["contact_phase_gate"]["dynamics_allowed"] is False,
        "contact gate widened",
    )
    _require(not any(contract["authority"].values()), "authority widened")
    return contract


def evaluate_historical_mapping_composition(
    contract: dict[str, Any], *, root: Path = REPO_ROOT
) -> tuple[dict[str, Any], dict[str, Any]]:
    sources = contract["sources"]
    or15 = _bound_json(
        sources["or15_receipt"], root=root, label="OR15 receipt"
    )
    historical = _bound_json(
        sources["historical_mapping_receipt"],
        root=root,
        label="historical mapping",
    )
    frozen = np.asarray(
        contract["frozen_mapping"]["joint_zero_offsets_rad"],
        dtype=np.float64,
    )
    source_values = np.asarray(
        historical["mapping"]["candidate"]["joint_zero_offsets_rad"],
        dtype=np.float64,
    )
    _require(np.array_equal(frozen, source_values), "mapping values drifted")
    _require(
        historical["mapping"]["global_physical_model_mapping_approved"]
        is False,
        "historical proof class changed",
    )
    or13 = _bound_json(
        sources["or13_receipt"], root=root, label="OR13 receipt"
    )
    scene_path = _bound_path(
        sources["or13_scene"], root=root, label="OR13 scene"
    )
    scene = load_json_object(scene_path, label="OR13 scene")
    or13_contract, _ = load_geometry_camera_contract(
        _bound_path(
            sources["or13_contract"], root=root, label="OR13 contract"
        ),
        root=root,
    )
    phase, trace = _contact_phase_candidate(
        contract=or13_contract,
        scene_path=scene_path,
        pawn_height_m=float(or13["board_object_geometry"]["pawn_height_m"]),
        board_thickness_m=float(
            scene["simulation_estimates"]["board"]["thickness_m"]
        ),
        root=root,
        joint_zero_overrides={
            index: float(value) for index, value in enumerate(frozen)
        },
    )
    latest = int(contract["contact_phase_gate"]["precontact_latest_sample"])
    precontact_clear = not any(
        bool(row["phase_contact_geometry_pass"])
        for row in trace["rows"]
        if int(row["source_sample_index"]) <= latest
    )
    passed = bool(precontact_clear and phase["contact_at_expected_phase"])
    prior_sample = or15["contact_phase"]["sample_232"]
    current_sample = phase["sample_232"]
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "proof_class": contract["proof_class"],
        "status": (
            "PASS_STATIC_NAMED_CONTACT_QUARANTINED_NO_DYNAMICS"
            if passed
            else "TERMINAL_NEGATIVE_NO_PHASE_CORRECT_NAMED_CONTACT"
        ),
        "source_hashes": {
            source_id: binding["sha256"]
            for source_id, binding in sources.items()
        },
        "frozen_mapping": contract["frozen_mapping"],
        "contact_phase": {
            **phase,
            "precontact_clear_through_sample_224": precontact_clear,
            "static_gate_passed": passed,
        },
        "sample_232_change_from_or15": {
            "planar_midpoint_error_before_m": prior_sample[
                "midpoint_to_pawn_planar_distance_m"
            ],
            "planar_midpoint_error_after_m": current_sample[
                "midpoint_to_pawn_planar_distance_m"
            ],
            "vertical_residual_before_m": prior_sample[
                "midpoint_to_pawn_vector_m"
            ][2],
            "vertical_residual_after_m": current_sample[
                "midpoint_to_pawn_vector_m"
            ][2],
            "fixed_jaw_gap_before_m": prior_sample["fixed_signed_distance_m"],
            "fixed_jaw_gap_after_m": current_sample["fixed_signed_distance_m"],
        },
        "actions_changed": False,
        "task_outcome_used_for_new_fit": False,
        "mapping_refit": False,
        "physics_integration_steps": 0,
        "dynamic_replays": 0,
        "global_mapping_approved": False,
        "authority": contract["authority"],
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    return receipt, trace


def build_historical_mapping_composition_receipt(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    contract = load_historical_mapping_composition_contract(
        contract_path, root=root
    )
    receipt, trace = evaluate_historical_mapping_composition(
        contract, root=root
    )
    atomic_write_json(output_directory / "trace.json", trace)
    atomic_write_json(output_directory / "receipt.json", receipt)
    return receipt


def main() -> int:
    build_historical_mapping_composition_receipt()
    return 0

