"""Frozen one-branch-or-insufficient contact consequence discriminator."""

from __future__ import annotations

from pathlib import Path
from typing import Any

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
    "sim2claw.contact_consequence_mechanism_discriminator_contract.v1"
)
RECEIPT_SCHEMA = (
    "sim2claw.contact_consequence_mechanism_discriminator_receipt.v1"
)
CONTRACT_PATH = (
    REPO_ROOT
    / "configs/evaluations/contact_consequence_mechanism_discriminator_v1.json"
)
OUTPUT_DIRECTORY = (
    REPO_ROOT / "outputs/contact_consequence_mechanism_discriminator_v1"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def load_contact_consequence_mechanism_discriminator_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="contact discriminator")
    _require(contract.get("schema_version") == SCHEMA, "unsupported contract")
    for name, binding in contract["sources"].items():
        _bound_path(binding, root=root, label=name)
    analysis = contract["analysis"]
    _require(
        analysis["source_sample_start"] == 210
        and analysis["source_sample_end"] == 300
        and analysis["exactly_one_branch_or_insufficient"] is True
        and analysis["terminal_task_outcome_allowed"] is False
        and analysis["parameter_fit_allowed"] is False
        and analysis["second_simulator_replay_allowed"] is False,
        "discriminator boundary widened",
    )
    _require(
        [branch["branch_id"] for branch in contract["branches"]]
        == [
            "off_center_contact_moment",
            "jaw_pawn_slip",
            "support_transition",
            "downstream_collision",
        ],
        "discriminator branch set changed",
    )
    _require(
        not any(contract["authority"].values()),
        "discriminator authority widened",
    )
    return contract


def build_contact_consequence_mechanism_discriminator(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    _require(not receipt_path.exists(), "OR23 output already exists")
    contract = load_contact_consequence_mechanism_discriminator_contract(
        contract_path, root=root
    )
    or21 = _bound_json(
        contract["sources"]["or21_closeout"],
        root=root,
        label="OR21",
    )
    or22 = _bound_json(
        contract["sources"]["or22_closeout"],
        root=root,
        label="OR22",
    )
    _require(
        or21["status"] == "PASS_EXACT_REPRODUCTION_CONTACT_TRACE"
        and or22["status"]
        == "PASS_BOUNDED_JAW_CROWN_EVENT_PROXY_PAWN_AXIS_INSUFFICIENT",
        "discriminator prerequisite changed",
    )
    available = {
        "metric_contact_point_relative_to_pawn_com": False,
        "physical_pawn_orientation_path": bool(
            or22["result"]["pawn_axis_orientation_available"]
        ),
        "instrumented_or_visually_resolved_contact_state": False,
        "relative_jaw_pawn_contact_velocity": False,
        "pixel_or_metric_board_support_contact_state": False,
        "named_physical_collision_witness_before_orientation_divergence": False,
    }
    simulator_witnesses = {
        "off_center_contact_moment": {
            "contact_position_trace_available": True,
            "orientation_onset_sample": or21["result"][
                "first_orientation_over_5_degrees_source_sample"
            ],
        },
        "jaw_pawn_slip": {
            "slip_observed": True,
            "first_slip_sample": or21["result"][
                "first_slip_over_0_02_m_s_source_sample"
            ],
        },
        "support_transition": {
            "support_loss_observed": True,
            "first_support_loss_sample": or21["result"][
                "first_sustained_support_loss_source_sample"
            ],
        },
        "downstream_collision": {
            "named_preorientation_collision_observed": False
        },
    }
    evaluations: list[dict[str, Any]] = []
    for branch in contract["branches"]:
        required = branch["required_physical_channels"]
        missing = [name for name in required if not available[name]]
        evaluations.append(
            {
                "branch_id": branch["branch_id"],
                "simulator_witness": simulator_witnesses[
                    branch["branch_id"]
                ],
                "required_physical_channels": required,
                "missing_physical_channels": missing,
                "physical_discriminator_complete": not missing,
                "selected": False,
            }
        )
    complete = [
        item for item in evaluations if item["physical_discriminator_complete"]
    ]
    _require(
        len(complete) <= 1,
        "more than one discriminator branch unexpectedly complete",
    )
    selected = complete[0]["branch_id"] if len(complete) == 1 else None
    if selected is not None:
        next(
            item for item in evaluations if item["branch_id"] == selected
        )["selected"] = True
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "proof_class": contract["proof_class"],
        "status": (
            "PASS_SINGLE_MECHANISM_BRANCH"
            if selected is not None
            else "MECHANISM_NOT_IDENTIFIABLE"
        ),
        "analysis_source_sample_window": [210, 300],
        "terminal_task_outcome_used": False,
        "simulator_event_timing": {
            "unilateral_contact_sample": or21["result"][
                "first_unilateral_jaw_contact_source_sample"
            ],
            "orientation_onset_sample": or21["result"][
                "first_orientation_over_5_degrees_source_sample"
            ],
            "bilateral_contact_sample": or21["result"][
                "first_bilateral_jaw_contact_source_sample"
            ],
            "support_loss_sample": or21["result"][
                "first_sustained_support_loss_source_sample"
            ],
        },
        "physical_event_timing_correspondence": {
            "contact_corresponds": or22["result"][
                "sim_contact_inside_physical_contact_interval"
            ],
            "lift_corresponds": or22["result"][
                "sim_orientation_onset_inside_physical_lift_interval"
            ],
            "carry_start_corresponds": or22["result"][
                "sim_support_loss_equals_physical_carry_start"
            ],
        },
        "branch_evaluations": evaluations,
        "selected_branch": selected,
        "reason": (
            None
            if selected is not None
            else (
                "coarse event timing corresponds, but retained physical "
                "evidence has no pawn-axis orientation, metric contact point, "
                "resolved slip, support-contact state, or named collision "
                "witness to distinguish the co-occurring simulator channels"
            )
        ),
        "parameter_fit_performed": False,
        "simulator_replay_performed": False,
        "simulator_correction_allowed": selected is not None,
        "global_mapping_approved": False,
        "task_success_claim": False,
        "transfer_claim": False,
        "authority": contract["authority"],
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


def main() -> int:
    build_contact_consequence_mechanism_discriminator()
    return 0
