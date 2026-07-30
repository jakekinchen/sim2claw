"""Task-specific unilateral push-contact diagnostic for the retained replay."""

from __future__ import annotations

import copy
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
from .post_hackathon_home_workspace_geometry_camera import (
    _contact_phase_candidate,
    load_geometry_camera_contract,
)

SCHEMA = "sim2claw.observable_registration_unilateral_push_contact_contract.v1"
RECEIPT_SCHEMA = (
    "sim2claw.observable_registration_unilateral_push_contact_receipt.v1"
)
CONTRACT_PATH = (
    REPO_ROOT
    / "configs/evaluations/observable_registration_unilateral_push_contact_v1.json"
)
OUTPUT_DIRECTORY = (
    REPO_ROOT / "outputs/observable_registration_unilateral_push_contact_v1"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def load_unilateral_push_contact_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="unilateral push contact")
    _require(contract.get("schema_version") == SCHEMA, "unsupported contract")
    for name, binding in contract["sources"].items():
        _bound_path(binding, root=root, label=name)
    evaluator = contract["task_specific_evaluator"]
    _require(
        evaluator["mode"] == "unilateral_named_jaw_push_contact"
        and evaluator["bilateral_contact_required"] is False
        and evaluator["pawn_center_bracketing_required"] is False,
        "push evaluator widened",
    )
    limits = contract["limits"]
    _require(not any(limits.values()), "diagnostic limits widened")
    _require(not any(contract["authority"].values()), "authority widened")
    _require(
        contract["candidate"]["selection_used_task_contact_rows"] is True
        and contract["candidate"]["globally_approved"] is False,
        "outcome-informed boundary changed",
    )
    return contract


def evaluate_unilateral_push_contact(
    contract: dict[str, Any], *, root: Path = REPO_ROOT
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    sources = contract["sources"]
    scene = copy.deepcopy(
        _bound_json(sources["or13_scene"], root=root, label="OR13 scene")
    )
    candidate = contract["candidate"]
    left = next(
        robot
        for robot in scene["simulation_estimates"]["robots"]
        if robot["name"] == "left"
    )
    left["yaw_relative_to_table_degrees"] += float(
        candidate["left_robot_yaw_delta_degrees"]
    )
    for index, delta in enumerate(
        candidate["left_robot_base_translation_delta_m"]
    ):
        left["mount_in_table_frame_xyz_m"][index] += float(delta)
    derived_path = OUTPUT_DIRECTORY / "derived_scene_config.json"
    atomic_write_json(derived_path, scene)

    historical = _bound_json(
        sources["historical_mapping_receipt"],
        root=root,
        label="historical mapping",
    )
    body_offsets = historical["mapping"]["candidate"][
        "joint_zero_offsets_rad"
    ]
    offsets = {
        **{index: float(value) for index, value in enumerate(body_offsets)},
        5: float(candidate["gripper_zero_offset_rad"]),
    }
    or13_receipt = _bound_json(
        sources["or13_receipt"], root=root, label="OR13 receipt"
    )
    or13_contract, _ = load_geometry_camera_contract(
        _bound_path(
            sources["or13_contract"], root=root, label="OR13 contract"
        ),
        root=root,
    )
    phase, trace = _contact_phase_candidate(
        contract=or13_contract,
        scene_path=derived_path,
        pawn_height_m=float(
            or13_receipt["board_object_geometry"]["pawn_height_m"]
        ),
        board_thickness_m=float(
            scene["simulation_estimates"]["board"]["thickness_m"]
        ),
        root=root,
        joint_zero_overrides=offsets,
    )

    evaluator = contract["task_specific_evaluator"]
    precontact = [
        row
        for row in trace["rows"]
        if int(row["source_sample_index"])
        <= int(evaluator["last_definitely_separate_sample"])
    ]
    contact = [
        row
        for row in trace["rows"]
        if int(evaluator["candidate_contact_samples"][0])
        <= int(row["source_sample_index"])
        <= int(evaluator["candidate_contact_samples"][1])
    ]
    precontact_minimum = min(
        min(
            float(row["fixed"]["signed_distance_m"]),
            float(row["moving"]["signed_distance_m"]),
        )
        for row in precontact
    )
    precontact_clear = bool(
        precontact_minimum
        >= float(evaluator["minimum_precontact_clearance_m"])
        and all(not row["exact_named_contact_pairs"] for row in precontact)
    )
    first_contact = next(
        (
            row
            for row in contact
            if row["exact_named_contact_pairs"]
            and min(
                float(row["fixed"]["signed_distance_m"]),
                float(row["moving"]["signed_distance_m"]),
            )
            <= float(evaluator["contact_signed_distance_m"])
        ),
        None,
    )
    passed = bool(precontact_clear and first_contact is not None)
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "proof_class": contract["proof_class"],
        "status": (
            "PASS_QUARANTINED_UNILATERAL_NAMED_CONTACT_NO_DYNAMICS"
            if passed
            else "TERMINAL_NEGATIVE_NO_PHASE_CORRECT_UNILATERAL_CONTACT"
        ),
        "candidate": candidate,
        "source_hashes": {
            name: binding["sha256"]
            for name, binding in sources.items()
        },
        "evaluator": {
            **evaluator,
            "precontact_minimum_clearance_m": precontact_minimum,
            "precontact_clear": precontact_clear,
            "first_named_unilateral_contact_source_sample": (
                int(first_contact["source_sample_index"])
                if first_contact is not None
                else None
            ),
            "first_named_unilateral_contact_pairs": (
                first_contact["exact_named_contact_pairs"]
                if first_contact is not None
                else []
            ),
            "static_gate_passed": passed,
        },
        "sample_232": phase["sample_232"],
        "support_contacts_reported_but_not_misclassified_as_jaw_contact": True,
        "task_rows_used_for_candidate_selection": True,
        "actions_changed": False,
        "physics_integration_steps": 0,
        "dynamic_replays": 0,
        "global_mapping_approved": False,
        "transfer_claim": False,
        "authority": contract["authority"],
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    return receipt, trace, scene


def build_unilateral_push_contact_receipt(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    contract = load_unilateral_push_contact_contract(
        contract_path, root=root
    )
    receipt, trace, _ = evaluate_unilateral_push_contact(
        contract, root=root
    )
    atomic_write_json(output_directory / "trace.json", trace)
    atomic_write_json(output_directory / "receipt.json", receipt)
    return receipt


def main() -> int:
    build_unilateral_push_contact_receipt()
    return 0
