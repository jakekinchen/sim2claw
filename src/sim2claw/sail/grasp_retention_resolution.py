"""Frozen, action-invariant campaign for the C2 grasp-retention gap."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from ..paths import REPO_ROOT
from ..pawn_bg_grasp_coordinate_descent import run_grasp_episode_probe


CONTRACT_PATH = (
    REPO_ROOT / "configs" / "sail" / "grasp_retention_resolution_v1.json"
)
SCHEMA = "sim2claw.sail_grasp_retention_resolution_campaign.v1"
FOLLOWUP_SCHEMA = "sim2claw.sail_grasp_retention_force_contact_campaign.v1"
COMPLIANCE_SCHEMA = "sim2claw.sail_grasp_retention_contact_compliance_campaign.v1"
TORQUE_SCHEMA = "sim2claw.sail_grasp_retention_current_torque_campaign.v1"
LOAD_HOLD_SCHEMA = "sim2claw.sail_grasp_retention_load_hold_campaign.v1"
CALIBRATED_HOLD_SCHEMA = "sim2claw.sail_grasp_retention_calibrated_hold_campaign.v1"
COMPOSITE_SCHEMA = "sim2claw.sail_grasp_retention_composite_campaign.v1"
CAPSULE_SCHEMA = "sim2claw.sail_grasp_retention_capsule_pad_campaign.v1"
NORMAL_COMPLIANCE_SCHEMA = (
    "sim2claw.sail_grasp_retention_normal_compliance_campaign.v1"
)
COMPLIANT_FOOTPRINT_SCHEMA = (
    "sim2claw.sail_grasp_retention_compliant_footprint_campaign.v1"
)
LAYERED_CAP_SCHEMA = "sim2claw.sail_grasp_retention_layered_cap_campaign.v1"
CORE_ANCHORED_CAP_SCHEMA = (
    "sim2claw.sail_grasp_retention_core_anchored_cap_campaign.v1"
)
CORE_CAP_LOAD_SCHEMA = (
    "sim2claw.sail_grasp_retention_core_cap_load_response_campaign.v1"
)
TORQUE_LATCH_SCHEMA = (
    "sim2claw.sail_grasp_retention_torque_latch_campaign.v1"
)
LONG_WRAP_TORQUE_SCHEMA = (
    "sim2claw.sail_grasp_retention_long_wrap_torque_campaign.v1"
)
COLLISION_SKIN_SCHEMA = (
    "sim2claw.sail_grasp_retention_collision_skin_campaign.v1"
)
MOVING_OVERHANG_SCHEMA = (
    "sim2claw.sail_grasp_retention_moving_overhang_campaign.v1"
)
COMPLIANT_SKIN_SCHEMA = (
    "sim2claw.sail_grasp_retention_compliant_skin_campaign.v1"
)
STABLE_COMPLIANCE_SCHEMA = (
    "sim2claw.sail_grasp_retention_stable_compliance_campaign.v1"
)
CONTACT_HEIGHT_SCHEMA = (
    "sim2claw.sail_grasp_retention_contact_height_campaign.v1"
)
SCREEN_SCHEMA = "sim2claw.sail_grasp_retention_anchor_screen.v1"


class GraspRetentionResolutionError(RuntimeError):
    """The frozen grasp-retention campaign failed closed."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GraspRetentionResolutionError(
            f"cannot read JSON {path}: {error}"
        ) from error
    if not isinstance(value, dict):
        raise GraspRetentionResolutionError(f"JSON root must be an object: {path}")
    return value


def _resolve(root: Path, relative: str) -> Path:
    resolved = (root / relative).resolve()
    if resolved != root and root not in resolved.parents:
        raise GraspRetentionResolutionError(
            f"source binding escapes repository root: {relative}"
        )
    return resolved


def load_grasp_retention_contract(
    *,
    repository_root: Path = REPO_ROOT,
    contract_path: Path = CONTRACT_PATH,
) -> dict[str, Any]:
    """Load and validate the frozen campaign before any simulation is run."""

    root = repository_root.resolve()
    contract = _load_json(contract_path)
    if contract.get("schema_version") not in {
        SCHEMA,
        FOLLOWUP_SCHEMA,
        COMPLIANCE_SCHEMA,
        TORQUE_SCHEMA,
        LOAD_HOLD_SCHEMA,
        CALIBRATED_HOLD_SCHEMA,
        COMPOSITE_SCHEMA,
        CAPSULE_SCHEMA,
        NORMAL_COMPLIANCE_SCHEMA,
        COMPLIANT_FOOTPRINT_SCHEMA,
        LAYERED_CAP_SCHEMA,
        CORE_ANCHORED_CAP_SCHEMA,
        CORE_CAP_LOAD_SCHEMA,
        TORQUE_LATCH_SCHEMA,
        LONG_WRAP_TORQUE_SCHEMA,
        COLLISION_SKIN_SCHEMA,
        MOVING_OVERHANG_SCHEMA,
        COMPLIANT_SKIN_SCHEMA,
        STABLE_COMPLIANCE_SCHEMA,
        CONTACT_HEIGHT_SCHEMA,
    }:
        raise GraspRetentionResolutionError("grasp-retention schema drifted")
    if contract.get("campaign_id") not in {
        "sail-grasp-retention-resolution-v1",
        "sail-grasp-retention-force-contact-v1",
        "sail-grasp-retention-contact-compliance-v1",
        "sail-grasp-retention-current-torque-v1",
        "sail-grasp-retention-load-hold-v1",
        "sail-grasp-retention-calibrated-hold-v1",
        "sail-grasp-retention-composite-v1",
        "sail-grasp-retention-capsule-pad-v1",
        "sail-grasp-retention-normal-compliance-v1",
        "sail-grasp-retention-compliant-footprint-v1",
        "sail-grasp-retention-layered-cap-v1",
        "sail-grasp-retention-core-anchored-cap-v1",
        "sail-grasp-retention-core-cap-load-response-v1",
        "sail-grasp-retention-torque-latch-v1",
        "sail-grasp-retention-long-wrap-torque-v1",
        "sail-grasp-retention-collision-skin-v1",
        "sail-grasp-retention-moving-overhang-v1",
        "sail-grasp-retention-compliant-skin-v1",
        "sail-grasp-retention-stable-compliance-v1",
        "sail-grasp-retention-contact-height-v1",
    }:
        raise GraspRetentionResolutionError("grasp-retention campaign id drifted")

    candidates = contract.get("frozen_candidate_family")
    maximum = int(contract["selection"]["maximum_anchor_candidates"])
    if not isinstance(candidates, list) or len(candidates) != maximum:
        raise GraspRetentionResolutionError(
            "candidate inventory does not match the frozen anchor budget"
        )
    identifiers = [str(row.get("candidate_id")) for row in candidates]
    if len(set(identifiers)) != len(identifiers) or identifiers[0] != "baseline":
        raise GraspRetentionResolutionError(
            "candidate ids must be unique and begin with baseline"
        )
    if bool(contract["selection"]["post_hoc_candidate_expansion"]):
        raise GraspRetentionResolutionError("post-hoc candidate expansion is forbidden")
    for row in candidates:
        if not isinstance(row.get("overrides"), dict):
            raise GraspRetentionResolutionError(
                f"candidate overrides must be an object: {row.get('candidate_id')}"
            )

    verified: dict[str, dict[str, str]] = {}
    for label, binding in contract["source_bindings"].items():
        path = _resolve(root, str(binding["path"]))
        actual = sha256_file(path)
        expected = str(binding["sha256"])
        if actual != expected:
            raise GraspRetentionResolutionError(
                f"{label} SHA-256 drifted: expected {expected}, got {actual}"
            )
        verified[label] = {"path": str(path), "sha256": actual}

    application = _load_json(
        _resolve(root, contract["source_bindings"]["project_application_contract"]["path"])
    )
    recording_id = str(contract["diagnosis_anchor"]["recording_id"])
    expected_action = str(contract["diagnosis_anchor"]["action_array_sha256"])
    if application["episode_roles"]["diagnosis_anchor"] != recording_id:
        raise GraspRetentionResolutionError("diagnosis anchor recording drifted")
    if application["action_sha256_by_recording_id"][recording_id] != expected_action:
        raise GraspRetentionResolutionError("diagnosis anchor action identity drifted")

    return {**contract, "verified_source_bindings": verified}


def candidate_parameters(
    contract: dict[str, Any], candidate: dict[str, Any]
) -> dict[str, Any]:
    parameters = dict(contract["base_parameters"])
    parameters.update(candidate["overrides"])
    return parameters


def _contact_loss_index(episode: dict[str, Any]) -> int | None:
    loss = episode.get("retention_event_summary", {}).get(
        "first_bilateral_contact_loss_after_lift"
    )
    if not loss:
        return None
    return int(loss["source_index"])


def _anchor_result(
    *,
    episode: dict[str, Any],
    contract: dict[str, Any],
    baseline_slip_m: float,
) -> dict[str, Any]:
    acceptance = contract["acceptance"]
    expected_action = contract["diagnosis_anchor"]["action_array_sha256"]
    release_index = int(contract["diagnosis_anchor"]["release_onset_source_index"])
    loss_index = _contact_loss_index(episode)
    retained = bool(episode["bilateral_lift_retention"]) and (
        loss_index is None or loss_index >= release_index
    )
    bias = float(
        episode["event_aligned_gripper_metrics"][
            "simulated_minus_measured_bias_degrees"
        ]
    )
    slip = float(episode["maximum_post_grasp_slip_m"])
    reduction = 0.0 if baseline_slip_m == 0.0 else (baseline_slip_m - slip) / baseline_slip_m
    post_lift_pairs = [
        row["load_bearing_pair"]
        for row in episode.get("retention_trace") or []
        if row.get("mechanism_phase") == "after_lift"
        and row.get("load_bearing_pair") is not None
    ]
    rubber_pair_count = sum(
        "_rubber_tip_" in str(pair[side]["jaw_geom_name"])
        for pair in post_lift_pairs
        for side in ("fixed", "moving")
    )
    rubber_pair_fraction = (
        0.0
        if not post_lift_pairs
        else rubber_pair_count / (2.0 * len(post_lift_pairs))
    )
    reasons: list[str] = []
    if (
        episode.get("action_array_sha256") != expected_action
        or not episode.get("action_byte_identical")
    ):
        reasons.append("action_identity_drift")
    if not retained:
        reasons.append("bilateral_contact_lost_before_release")
    if abs(bias) > float(
        acceptance["anchor_absolute_loaded_aperture_bias_degrees_maximum"]
    ):
        reasons.append("loaded_aperture_mismatch")
    if not episode["lift_and_transport"]:
        reasons.append("anchor_transport_failure")
    if reduction < float(
        acceptance["anchor_post_grasp_slip_relative_reduction_minimum"]
    ):
        reasons.append("insufficient_slip_reduction")
    minimum_rubber_fraction = acceptance.get(
        "anchor_minimum_rubber_load_pair_fraction_after_lift"
    )
    if minimum_rubber_fraction is not None and rubber_pair_fraction < float(
        minimum_rubber_fraction
    ):
        reasons.append("rigid_or_missing_post_lift_load_path")
    stability = episode.get("simulation_stability")
    if acceptance.get("anchor_simulation_stability_required") and (
        not isinstance(stability, dict) or not stability.get("passed")
    ):
        reasons.append("simulation_instability")
    return {
        "status": "anchor_pass" if not reasons else "rejected",
        "reasons": reasons,
        "action_sha256": episode["action_array_sha256"],
        "contact_loss_source_index": loss_index,
        "contact_retained_through_release_onset": retained,
        "loaded_aperture_bias_degrees": bias,
        "absolute_loaded_aperture_bias_degrees": abs(bias),
        "lift_and_transport": bool(episode["lift_and_transport"]),
        "piece_lifted": bool(episode["piece_lifted"]),
        "bilateral_lift_retention": bool(episode["bilateral_lift_retention"]),
        "bilateral_lift_retention_seconds": float(
            episode["maximum_bilateral_lift_retention_seconds"]
        ),
        "post_grasp_slip_m": slip,
        "post_grasp_slip_relative_reduction": reduction,
        "post_lift_load_pair_count": len(post_lift_pairs),
        "rubber_load_pair_fraction_after_lift": rubber_pair_fraction,
        "simulation_stability": stability,
        "first_qualified_contact_height_relative_piece_center_m": episode.get(
            "first_qualified_contact_height_relative_piece_center_m"
        ),
        "maximum_piece_rise_m": episode.get("maximum_piece_rise_m"),
        "maximum_transport_progress_after_lift": episode.get(
            "maximum_transport_progress_after_lift"
        ),
        "trace_metrics": {
            "overall_joint_rms_degrees": float(
                episode["trace_metrics"]["overall_joint_rms_degrees"]
            ),
            "ee_rms_m": float(episode["trace_metrics"]["ee_rms_m"]),
        },
    }


def _rank_key(row: dict[str, Any]) -> tuple[float, ...]:
    result = row["result"]
    loss = result["contact_loss_source_index"]
    return (
        float(result["contact_retained_through_release_onset"]),
        -float(result["absolute_loaded_aperture_bias_degrees"]),
        float(result["bilateral_lift_retention_seconds"]),
        float(result["lift_and_transport"]),
        -float(result["post_grasp_slip_m"]),
        float(loss if loss is not None else 10**9),
    )


def run_anchor_screen(
    *,
    repository_root: Path = REPO_ROOT,
    contract_path: Path = CONTRACT_PATH,
    output_root: Path | None = None,
) -> dict[str, Any]:
    """Run or safely resume the frozen 18-member C2 anchor screen."""

    root = repository_root.resolve()
    contract = load_grasp_retention_contract(
        repository_root=root, contract_path=contract_path
    )
    destination = output_root or _resolve(root, contract["output_root"])
    anchor_directory = destination / "anchor"
    anchor_directory.mkdir(parents=True, exist_ok=True)
    recording_id = str(contract["diagnosis_anchor"]["recording_id"])
    baseline_slip_m = float(
        _load_json(
            _resolve(
                root,
                contract["source_bindings"]["c2_surface_witness"]["path"],
            )
        )["episode"]["maximum_post_grasp_slip_m"]
    )

    rows: list[dict[str, Any]] = []
    for candidate in contract["frozen_candidate_family"]:
        candidate_id = str(candidate["candidate_id"])
        parameters = candidate_parameters(contract, candidate)
        parameter_digest = canonical_digest(parameters)
        path = anchor_directory / f"{candidate_id}.json"
        if path.exists():
            receipt = _load_json(path)
            if receipt.get("parameter_digest") != parameter_digest:
                raise GraspRetentionResolutionError(
                    f"resumed candidate parameter drift: {candidate_id}"
                )
        else:
            receipt = run_grasp_episode_probe(
                source_repository_root=root,
                recording_id=recording_id,
                parameters=parameters,
                retention_trace_enabled=True,
            )
            atomic_write_json(path, receipt)
        episode = receipt["episode"]
        rows.append(
            {
                "candidate_id": candidate_id,
                "overrides": candidate["overrides"],
                "parameters": parameters,
                "parameter_digest": parameter_digest,
                "artifact_path": str(path.resolve()),
                "artifact_sha256": sha256_file(path),
                "result": _anchor_result(
                    episode=episode,
                    contract=contract,
                    baseline_slip_m=baseline_slip_m,
                ),
            }
        )

    ranked = sorted(rows, key=_rank_key, reverse=True)
    receipt = {
        "schema_version": SCREEN_SCHEMA,
        "campaign_id": contract["campaign_id"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "contract_path": str(contract_path.resolve()),
        "contract_sha256": sha256_file(contract_path),
        "proof_class": contract["proof_boundary"]["proof_class"],
        "recording_id": recording_id,
        "action_array_sha256": contract["diagnosis_anchor"]["action_array_sha256"],
        "candidate_budget": len(contract["frozen_candidate_family"]),
        "candidate_count": len(rows),
        "all_actions_byte_identical": all(
            row["result"]["action_sha256"]
            == contract["diagnosis_anchor"]["action_array_sha256"]
            for row in rows
        ),
        "anchor_pass_count": sum(
            row["result"]["status"] == "anchor_pass" for row in rows
        ),
        "ranking": [row["candidate_id"] for row in ranked],
        "candidates": rows,
        "selection_is_frozen": True,
        "post_hoc_candidate_expansion": False,
    }
    receipt["receipt_digest"] = canonical_digest(receipt)
    atomic_write_json(destination / "anchor-screen-receipt.json", receipt)
    return receipt
