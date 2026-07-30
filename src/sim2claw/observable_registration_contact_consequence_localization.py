"""Localize the residual after phase-correct simulator contact."""

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

SCHEMA = (
    "sim2claw.observable_registration_contact_consequence_localization_contract.v1"
)
RECEIPT_SCHEMA = (
    "sim2claw.observable_registration_contact_consequence_localization_receipt.v1"
)
CONTRACT_PATH = (
    REPO_ROOT
    / "configs/evaluations/"
    "observable_registration_contact_consequence_localization_v1.json"
)
OUTPUT_DIRECTORY = (
    REPO_ROOT
    / "outputs/observable_registration_contact_consequence_localization_v1"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def load_contact_consequence_localization_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="contact consequence localization")
    _require(contract.get("schema_version") == SCHEMA, "unsupported contract")
    for name, binding in contract["sources"].items():
        _bound_path(binding, root=root, label=name)
    _require(not any(contract["policy"].values()), "policy widened")
    _require(not any(contract["authority"].values()), "authority widened")
    return contract


def build_contact_consequence_localization_receipt(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    contract = load_contact_consequence_localization_contract(
        contract_path, root=root
    )
    sources = contract["sources"]
    or19 = _bound_json(
        sources["or19_receipt"], root=root, label="OR19 receipt"
    )
    trace = _bound_json(
        sources["or19_trace"], root=root, label="OR19 trace"
    )
    physical = _bound_json(
        sources["physical_episode_receipt"],
        root=root,
        label="physical episode",
    )
    identifiability = _bound_json(
        sources["contact_identifiability_receipt"],
        root=root,
        label="contact identifiability",
    )
    _require(
        or19["actions_changed"] is False
        and or19["source_identity"]["row_count"] == 531,
        "OR19 identity changed",
    )
    rows = trace["rows"]
    _require(
        len(rows) == 531
        and [row["sample_index"] for row in rows] == list(range(531)),
        "OR19 trace order changed",
    )
    positions = np.asarray(
        [row["selected_pawn_position_m"] for row in rows],
        dtype=np.float64,
    )
    planar = np.linalg.norm(positions[:, :2] - positions[0, :2], axis=1)
    vertical = np.abs(positions[:, 2] - positions[0, 2])
    planar_rows = np.flatnonzero(
        planar > float(contract["thresholds"]["planar_motion_m"])
    )
    vertical_rows = np.flatnonzero(
        vertical > float(contract["thresholds"]["vertical_motion_m"])
    )
    first_planar = int(planar_rows[0]) if planar_rows.size else None
    first_vertical = int(vertical_rows[0]) if vertical_rows.size else None
    physical_events = physical["observable_episode"][
        "contact_and_motion_events"
    ]
    physical_outcome = physical["observable_episode"]["outcome"]
    _require(
        physical_events["candidate_contact_interval_samples"][
            "sample_indices"
        ]
        == contract["thresholds"]["physical_contact_samples"]
        and physical_events["candidate_lift_interval_samples"][
            "sample_indices"
        ]
        == contract["thresholds"]["physical_lift_samples"]
        and physical_events["definite_carried_motion_interval_samples"][
            "sample_indices"
        ]
        == contract["thresholds"]["physical_carried_motion_samples"],
        "physical event bounds changed",
    )
    _require(
        identifiability["result"]
        == "TERMINAL_CONTACT_MODEL_NEGATIVE_INSUFFICIENT_NONSEALED_WITNESSES",
        "contact identifiability boundary changed",
    )
    result = {
        "first_named_simulator_contact_sample": or19["dynamics"][
            "first_selected_jaw_contact_sample"
        ],
        "first_simulator_planar_motion_over_1mm_sample": first_planar,
        "first_simulator_vertical_motion_over_1mm_sample": first_vertical,
        "physical_candidate_contact_samples": contract["thresholds"][
            "physical_contact_samples"
        ],
        "physical_candidate_lift_samples": contract["thresholds"][
            "physical_lift_samples"
        ],
        "physical_definite_carried_motion_samples": contract["thresholds"][
            "physical_carried_motion_samples"
        ],
        "simulator_motion_minus_physical_lift_start_samples": (
            first_planar
            - int(contract["thresholds"]["physical_lift_samples"][0])
        ),
        "simulator_motion_minus_physical_carried_start_samples": (
            first_planar
            - int(contract["thresholds"]["physical_carried_motion_samples"][0])
        ),
        "maximum_simulator_planar_displacement_m": float(np.max(planar)),
        "maximum_simulator_vertical_displacement_m": float(np.max(vertical)),
        "simulator_final_tilt_degrees": or19["outcome"][
            "final_upright_tilt_degrees"
        ],
        "physical_terminal_upright_reviewed": physical_outcome[
            "terminal_upright_reviewed"
        ],
        "simulator_final_d2_error_m": or19["outcome"][
            "final_planar_center_error_m"
        ],
        "simulator_other_piece_displacement_m": or19["outcome"][
            "maximum_other_piece_displacement_m"
        ],
        "earliest_remaining_causal_channel": (
            "object_orientation_and_contact_consequence_at_sample_248"
        ),
    }
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "proof_class": contract["proof_class"],
        "status": (
            "PASS_LOCALIZED_OBJECT_CONSEQUENCE_BLOCKED_IDENTIFIABILITY"
        ),
        "result": result,
        "admissible_next_mechanisms": [
            "metric_contact_height",
            "pawn_mass_or_center_of_mass",
            "pawn_board_friction",
            "contact_compliance_or_damping",
        ],
        "parameter_fit_allowed": False,
        "reason_parameter_fit_blocked": (
            "retained evidence lacks the required metric object orientation "
            "path and known contact force, and the candidate used task rows"
        ),
        "actions_changed": False,
        "global_mapping_approved": False,
        "transfer_claim": False,
        "authority": contract["authority"],
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(output_directory / "receipt.json", receipt)
    return receipt


def main() -> int:
    build_contact_consequence_localization_receipt()
    return 0
