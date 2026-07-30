"""Publish the observable-registration successor beside the immutable proof."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
    sha256_file,
)
from .paths import REPO_ROOT
from .realized_action_studio_proof import load_realized_action_studio_proof


CONTRACT_SCHEMA = (
    "sim2claw.observable_registration_studio_publication_contract.v1"
)
SUPPLEMENT_SCHEMA = "sim2claw.observable_registration_studio_supplement.v1"
RECEIPT_SCHEMA = (
    "sim2claw.observable_registration_studio_publication_receipt.v1"
)
CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "observable_registration_studio_publication_v1.json"
)
OUTPUT_DIRECTORY = (
    REPO_ROOT / "outputs" / "observable_registration_studio_publication_v1"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def _bound_json(
    root: Path, entry: dict[str, Any], label: str
) -> dict[str, Any]:
    path = root / str(entry.get("path") or "")
    _require(path.is_file(), f"{label} source is missing")
    _require(sha256_file(path) == entry.get("sha256"), f"{label} hash drifted")
    return load_json_object(path, label=label)


def load_publication_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="registration Studio publication")
    _require(
        contract.get("schema_version") == CONTRACT_SCHEMA,
        "unsupported registration publication schema",
    )
    _require(
        contract.get("proof_class")
        == "read_only_observable_registration_successor_projection",
        "registration publication proof class widened",
    )
    sources = contract.get("sources")
    _require(
        isinstance(sources, dict) and sources,
        "registration publication sources are missing",
    )
    for label, entry in sources.items():
        _require(isinstance(entry, dict), f"invalid publication source: {label}")
        _bound_json(root, entry, label)
    rules = contract.get("rules")
    _require(
        isinstance(rules, dict)
        and rules.get("base_proof_may_be_rewritten") is False
        and rules.get("base_timeline_may_be_changed") is False
        and rules.get("proof_class_may_be_promoted") is False
        and rules.get("missing_metric_depth_may_be_imputed") is False
        and rules.get("global_mapping_must_remain_unapproved") is True,
        "registration publication rules widened",
    )
    authority = contract.get("authority")
    _require(
        isinstance(authority, dict) and authority and not any(authority.values()),
        "registration publication authority widened",
    )
    return contract


def compile_observable_registration_publication(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    contract = load_publication_contract(contract_path, root=root)
    payloads = {
        label: _bound_json(root, entry, label)
        for label, entry in contract["sources"].items()
    }
    base_bundle = payloads["base_proof_bundle"]
    base_receipt = payloads["base_proof_receipt"]
    _require(
        base_bundle.get("artifact_sha256")
        == base_receipt.get("bundle", {}).get("artifact_sha256"),
        "base proof artifact binding changed",
    )
    or0 = payloads["or0_closeout"]
    or1 = payloads["or1_closeout"]
    or2 = payloads["or2_closeout"]
    or3 = payloads["or3_closeout"]
    or4 = payloads["or4_closeout"]
    or6 = payloads["or6_closeout"]
    or7 = payloads["or7_closeout"]
    or7a = payloads["or7a_closeout"]
    or7b = payloads["or7b_closeout"]
    rules = contract["rules"]
    _require(
        or2["global_physical_model_mapping_approved"] is False
        and or7["ledger"][
            "realized_physical_action_trajectory_to_matching_simulator_task_outcome"
        ]
        == {
            "successes": int(rules["exact_replay_successes_must_equal"]),
            "attempts": int(rules["exact_replay_attempts_must_equal"]),
        }
        and or7b["validation_reservation"]["admissible_pose_count"]
        == int(rules["validation_admissible_pose_count"])
        and or7b["next_evidence_requirement"][
            "minimum_new_no_contact_static_pose_count"
        ]
        == int(rules["validation_required_pose_count"]),
        "registration successor proof boundary changed",
    )
    camera = or1["bounded_physical_pinhole"]
    physical = or3["physical_events"]
    causal = or4["causal_localization"]
    gap = or7a["geometric_gap"]
    fit = or7b["fit_identifiability"]
    unsigned = {
        "schema_version": SUPPLEMENT_SCHEMA,
        "available": True,
        "read_only": True,
        "physical_authority": False,
        "status": "EVIDENCE_LIMITED_SPATIAL_REGISTRATION_BOUNDARY",
        "initial_alignment": {
            "camera_board_reprojection_rms_px": camera[
                "board_reprojection_rms_px"
            ],
            "camera_board_reprojection_max_px": camera[
                "board_reprojection_max_px"
            ],
            "exact_intrinsics_approved": or1["exact_calibration_boundary"][
                "exact_intrinsic_calibration_approved"
            ],
            "robot_jaw_fit_rms_px": or2["fit"]["tip_reprojection_rms_px"],
            "robot_jaw_validation_rms_px": or2["known_outcome_validation"][
                "tip_reprojection_rms_px"
            ],
            "global_mapping_approved": False,
        },
        "physical_observation": {
            "c922_frame_count": or0["camera_streams"]["c922"]["frame_count"],
            "wrist_rgb_frame_count": or0["camera_streams"]["d405_rgb"][
                "frame_count"
            ],
            "metric_depth_available": False,
            "first_definite_enclosure_sample": physical[
                "first_definite_enclosure_sample"
            ],
            "carried_motion_interval_samples": physical[
                "definite_carried_motion_interval_samples"
            ],
            "release_interval_samples": physical[
                "candidate_release_interval_samples"
            ],
        },
        "first_contact_divergence": {
            "channel": causal["earliest_divergence_channel"],
            "physical_enclosure_sample": physical[
                "first_definite_enclosure_sample"
            ],
            "simulator_first_pawn_motion_sample": or4["simulator_event"][
                "first_planar_motion_over_1mm_sample"
            ],
            "gap_samples": causal[
                "physical_enclosure_to_simulator_motion_gap_samples"
            ],
            "gap_seconds": causal[
                "physical_enclosure_to_simulator_motion_gap_seconds"
            ],
            "gripper_error_degrees_at_enclosure": causal[
                "enclosure_gripper_absolute_error_degrees"
            ],
        },
        "aperture_correction": {
            "gripper_zero_offset_rad": or6["parameter"]["fitted_value"],
            "fit_aperture_rms_before_px": or6["fit"][
                "baseline_aperture_rms_px"
            ],
            "fit_aperture_rms_after_px": or6["fit"][
                "candidate_aperture_rms_px"
            ],
            "validation_aperture_rms_before_px": or6["validation"][
                "baseline_aperture_rms_px"
            ],
            "validation_aperture_rms_after_px": or6["validation"][
                "candidate_aperture_rms_px"
            ],
            "only_gripper_zero_offset_changed": or6["identity"][
                "only_gripper_zero_offset_changed"
            ],
        },
        "exact_replay": {
            "successes": int(rules["exact_replay_successes_must_equal"]),
            "attempts": int(rules["exact_replay_attempts_must_equal"]),
            "selected_jaw_contact_steps": or7["dynamics"][
                "selected_jaw_contact_steps"
            ],
            "first_pawn_motion_sample": or7["dynamics"][
                "first_planar_motion_over_1mm_sample"
            ],
            "catastrophic_jump_sample": or7["dynamics"][
                "first_catastrophic_jump_sample"
            ],
            "final_center_error_mm": or7["outcome"][
                "final_planar_center_error_m"
            ]
            * 1000.0,
            "pawn_trace_byte_identical_to_c6": or7["dynamics"][
                "byte_identical_to_c6_pawn_trace"
            ],
        },
        "signed_geometric_gap": {
            "minimum_fixed_jaw_gap_mm": gap[
                "baseline_minimum_signed_distance_m"
            ]
            * 1000.0,
            "enclosure_fixed_jaw_gap_mm": gap[
                "enclosure_baseline_signed_distance_m"
            ]
            * 1000.0,
            "aperture_gap_reduction_mm": gap["minimum_gap_reduction_m"]
            * 1000.0,
            "enclosure_midpoint_to_pawn_vector_mm": [
                value * 1000.0
                for value in gap[
                    "enclosure_candidate_midpoint_to_pawn_vector_m"
                ]
            ],
        },
        "spatial_mechanism": {
            "family": or7b["declared_family"]["parameters"],
            "fit_identifiable": fit["accepted"],
            "jacobian_rank": fit["jacobian_rank"],
            "jacobian_singular_values_px_per_rad": fit[
                "jacobian_singular_values_px_per_rad"
            ],
            "jacobian_condition_number": fit[
                "jacobian_condition_number"
            ],
            "parameter_values_produced": or7b["declared_family"][
                "fit_parameter_values_produced"
            ],
            "validation_admissible_pose_count": or7b[
                "validation_reservation"
            ]["admissible_pose_count"],
            "validation_required_pose_count": or7b[
                "validation_reservation"
            ]["minimum_required_pose_count"],
        },
        "next_evidence_requirement": or7b["next_evidence_requirement"],
        "claim_boundary": (
            "This supplement projects retained OR0-OR7B evidence beside the "
            "immutable C6 Studio proof. It performs no fit, replay, validation "
            "open, promotion, or physical action. Global mapping, matching "
            "action-to-task transfer, and metric wrist depth remain unapproved."
        ),
        "hashes": {
            label: {
                "path": entry["path"],
                "sha256": entry["sha256"],
            }
            for label, entry in contract["sources"].items()
        },
        "authority": contract["authority"],
    }
    supplement = {
        **unsigned,
        "artifact_sha256": canonical_digest(unsigned),
    }
    output_directory.mkdir(parents=True, exist_ok=True)
    supplement_path = output_directory / "supplement.json"
    atomic_write_json(supplement_path, supplement)
    try:
        listed_path = supplement_path.relative_to(root).as_posix()
    except ValueError:
        listed_path = supplement_path.as_posix()
    unsigned_receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "contract_sha256": sha256_file(contract_path),
        "supplement": {
            "path": listed_path,
            "sha256": sha256_file(supplement_path),
            "artifact_sha256": supplement["artifact_sha256"],
        },
        "base_proof_unchanged": {
            "bundle_sha256": contract["sources"]["base_proof_bundle"][
                "sha256"
            ],
            "receipt_sha256": contract["sources"]["base_proof_receipt"][
                "sha256"
            ],
        },
        "acceptance": {
            "registration_cards_present": True,
            "exact_replay_denominator": 2,
            "validation_boundary_explicit": True,
            "missing_depth_explicit": True,
            "global_mapping_approved": False,
            "desktop_and_mobile_surface_required": True,
        },
        "authority": contract["authority"],
    }
    receipt = {
        **unsigned_receipt,
        "artifact_sha256": canonical_digest(unsigned_receipt),
    }
    atomic_write_json(output_directory / "receipt.json", receipt)
    return receipt


def load_observable_registration_studio_proof(
    *,
    root: Path = REPO_ROOT,
    contract_path: Path | None = None,
    output_directory: Path | None = None,
) -> dict[str, Any]:
    contract_path = contract_path or (
        root / CONTRACT_PATH.relative_to(REPO_ROOT)
    )
    output_directory = output_directory or (
        root / OUTPUT_DIRECTORY.relative_to(REPO_ROOT)
    )
    contract = load_publication_contract(contract_path, root=root)
    receipt_path = output_directory / "receipt.json"
    receipt = load_json_object(receipt_path, label="registration publication receipt")
    _require(
        receipt.get("schema_version") == RECEIPT_SCHEMA,
        "unsupported registration publication receipt",
    )
    unsigned_receipt = {
        key: value for key, value in receipt.items() if key != "artifact_sha256"
    }
    _require(
        receipt.get("artifact_sha256") == canonical_digest(unsigned_receipt),
        "registration publication receipt changed",
    )
    _require(
        receipt.get("contract_sha256") == sha256_file(contract_path),
        "registration publication contract binding changed",
    )
    supplement_path = root / str(receipt["supplement"]["path"])
    _require(
        supplement_path.is_file()
        and sha256_file(supplement_path) == receipt["supplement"]["sha256"],
        "registration publication supplement changed",
    )
    supplement = load_json_object(
        supplement_path, label="registration publication supplement"
    )
    unsigned_supplement = {
        key: value
        for key, value in supplement.items()
        if key != "artifact_sha256"
    }
    _require(
        supplement.get("schema_version") == SUPPLEMENT_SCHEMA
        and supplement.get("artifact_sha256")
        == canonical_digest(unsigned_supplement)
        and supplement.get("artifact_sha256")
        == receipt["supplement"]["artifact_sha256"],
        "registration publication supplement artifact changed",
    )
    base = load_realized_action_studio_proof(root=root)
    base["base_receipt_sha256"] = base["receipt_sha256"]
    base["receipt_sha256"] = sha256_file(receipt_path)
    base["receipt_artifact_sha256"] = receipt["artifact_sha256"]
    base["title"] = "Observable registration and realized-action proof"
    base["subtitle"] = (
        "Retained physical D1 to D2 evidence, exact simulator outcomes, and "
        "the bounded spatial-registration frontier"
    )
    base["registration_successor"] = supplement
    base["hashes"].update(supplement["hashes"])
    return base
