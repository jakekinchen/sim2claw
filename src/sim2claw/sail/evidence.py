"""Inventory and compile the retained B--G evidence campaign."""

from __future__ import annotations

import copy
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from ..learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .contracts import REPO_ROOT, SailContractError, verify_contract, verify_source_binding
from .importers import (
    EvidenceImportError,
    import_physical_evidence,
    import_simulator_evidence,
    load_json_object,
)
from .receipts import build_compile_receipt, verify_compile_receipt


CAMPAIGN_SCHEMA = "sim2claw.sail_retained_evidence_campaign.v1"
CATALOG_SCHEMA = "sim2claw.sail_evidence_catalog.v1"
OMISSIONS_SCHEMA = "sim2claw.sail_evidence_omissions.v1"


def load_campaign(path: Path, *, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    campaign_path = path if path.is_absolute() else repo_root / path
    campaign = load_json_object(campaign_path, label="SAIL evidence campaign")
    if campaign.get("schema_version") != CAMPAIGN_SCHEMA:
        raise EvidenceImportError("unexpected SAIL evidence campaign schema")
    required = (
        "campaign_id",
        "workcell_id",
        "source_owner",
        "source_bindings",
        "context_artifacts",
        "declared_omissions",
        "expected_inventory",
        "physical_import",
        "simulator_import",
        "determinism",
        "authority",
    )
    missing = [name for name in required if name not in campaign]
    if missing:
        raise EvidenceImportError("campaign is missing fields: " + ", ".join(missing))
    authority = campaign["authority"]
    if not isinstance(authority, dict) or not authority or any(authority.values()):
        raise EvidenceImportError("retained evidence campaign widened authority")
    expected_bindings = {
        "physical_catalog",
        "physical_split",
        "telemetry_contract",
        "event_contract",
        "action_frozen_contract",
        "fidelity_contract",
        "servo_load_bias_receipt",
        "fidelity_receipt",
    }
    if set(campaign["source_bindings"]) != expected_bindings:
        raise EvidenceImportError("retained evidence source binding set changed")
    if len(campaign["context_artifacts"]) != int(
        campaign["expected_inventory"]["context_artifact_count"]
    ):
        raise EvidenceImportError("retained context artifact count changed")
    return campaign


def _load_bound_sources(
    campaign: Mapping[str, Any], *, repo_root: Path
) -> tuple[dict[str, Path], dict[str, dict[str, Any]]]:
    paths: dict[str, Path] = {}
    values: dict[str, dict[str, Any]] = {}
    for name, binding in campaign["source_bindings"].items():
        path = verify_source_binding(binding, repo_root=repo_root)
        paths[name] = path
        values[name] = load_json_object(path, label=f"campaign source {name}")
    return paths, values


def _verify_context(
    campaign: Mapping[str, Any], *, repo_root: Path
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in sorted(campaign["context_artifacts"], key=lambda item: str(item["id"])):
        path = verify_source_binding(row, repo_root=repo_root)
        result.append(
            {
                "id": str(row["id"]),
                "path": path.resolve().relative_to(repo_root.resolve()).as_posix(),
                "sha256": str(row["sha256"]),
                "proof_class": str(row["proof_class"]),
                "interpretation": str(row["interpretation"]),
                "status": "verified",
            }
        )
    return result


def _compile_in_memory(
    campaign_path: Path, *, repo_root: Path
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    campaign = load_campaign(campaign_path, repo_root=repo_root)
    paths, sources = _load_bound_sources(campaign, repo_root=repo_root)
    catalog = sources["physical_catalog"]
    split = sources["physical_split"]
    telemetry = sources["telemetry_contract"]
    expected = campaign["expected_inventory"]
    if len(catalog.get("episodes") or []) != int(expected["physical_episode_count"]):
        raise EvidenceImportError("physical episode count changed")
    if sum(int(row["sample_count"]) for row in catalog["episodes"]) != int(
        expected["physical_sample_count"]
    ):
        raise EvidenceImportError("physical sample count changed")
    if split.get("split_counts") != {
        "train": int(expected["physical_train_episode_count"]),
        "held_out": int(expected["physical_held_out_episode_count"]),
    }:
        raise EvidenceImportError("physical split counts changed")
    telemetry_expected = telemetry.get("expected_inventory") or {}
    if telemetry_expected.get("episode_count") != expected["physical_episode_count"] or telemetry_expected.get(
        "sample_count"
    ) != expected["physical_sample_count"]:
        raise EvidenceImportError("telemetry contract inventory disagrees with campaign")
    if sources["event_contract"].get("authority") and any(
        sources["event_contract"]["authority"].values()
    ):
        raise EvidenceImportError("event contract widened authority")
    action_invariance = sources["action_frozen_contract"].get("action_invariance") or {}
    required_invariance = (
        "no_ik_corrections",
        "no_post_policy_offsets",
        "no_corrective_suffix",
        "no_assistance",
        "no_candidate_specific_action_mapping",
        "no_clipping",
        "require_identical_shape_dtype_and_sha256",
    )
    if any(action_invariance.get(name) is not True for name in required_invariance):
        raise EvidenceImportError("action-frozen invariance contract changed")

    physical = import_physical_evidence(campaign, catalog, split, repo_root=repo_root)
    simulator = import_simulator_evidence(
        campaign,
        sources["servo_load_bias_receipt"],
        receipt_path=paths["servo_load_bias_receipt"],
        repo_root=repo_root,
    )
    evidence = sorted(
        [*physical, *simulator],
        key=lambda row: (str(row["proof_class"]), str(row["evidence_id"])),
    )
    for row in evidence:
        verify_contract(row)
    roles = Counter(str(row["split_role"]) for row in evidence)
    classes = Counter(str(row["proof_class"]) for row in evidence)
    dev_count = roles["validation"]
    confirmation_count = roles["already_open_regression"]
    counts = {
        "evidence_count": len(evidence),
        "physical_episode_count": len(physical),
        "physical_sample_count": sum(int(row["action"]["shape"][0]) for row in physical),
        "action_frozen_development_episode_count": dev_count,
        "already_open_confirmation_episode_count": confirmation_count,
        "by_proof_class": dict(sorted(classes.items())),
        "by_split_role": dict(sorted(roles.items())),
    }
    required_counts = {
        "evidence_count": expected["emitted_evidence_count"],
        "physical_episode_count": expected["physical_episode_count"],
        "physical_sample_count": expected["physical_sample_count"],
        "action_frozen_development_episode_count": expected[
            "action_frozen_development_episode_count"
        ],
        "already_open_confirmation_episode_count": expected[
            "already_open_confirmation_episode_count"
        ],
    }
    for name, required in required_counts.items():
        if counts[name] != required:
            raise EvidenceImportError(
                f"compiled count changed for {name}: expected {required}, observed {counts[name]}"
            )
    context = _verify_context(campaign, repo_root=repo_root)
    return campaign, evidence, context, counts


def _omissions(
    campaign: Mapping[str, Any], evidence: list[Mapping[str, Any]], physical_catalog: Mapping[str, Any]
) -> dict[str, Any]:
    simulated_sessions = {
        str(row["session_id"])
        for row in evidence
        if row["proof_class"] == campaign["simulator_import"]["proof_class"]
    }
    physical_sessions = {
        str(row["session_id"])
        for row in evidence
        if row["proof_class"] == campaign["physical_import"]["proof_class"]
    }
    rows = [
        *copy.deepcopy(list(campaign["declared_omissions"])),
        {
            "id": "physical_recordings_without_action_frozen_trace",
            "recording_ids": sorted(physical_sessions - simulated_sessions),
            "reason": "No selected-campaign per-row simulator trace was retained for these physical episodes.",
            "effect": "Physical telemetry remains cataloged; no simulator residual is manufactured.",
        },
        {
            "id": "confirmation_per_episode_trace_values",
            "recording_ids": sorted(
                str(row["session_id"])
                for row in evidence
                if row["split_role"] == "already_open_regression"
            ),
            "reason": "The receipt retains action descriptors and two-episode aggregate metrics, not per-row confirmation traces.",
            "effect": "Confirmation evidence carries unavailable masks and is regression-only.",
        },
        {
            "id": "discarded_source_recording",
            "recordings": copy.deepcopy(list(physical_catalog.get("discarded_recordings") or [])),
            "reason": "The source catalog records the replaced attempt but its bytes are in user trash.",
            "effect": "The discarded attempt is not counted among the 18 source episodes.",
        },
        {
            "id": "unobserved_physical_channels",
            "channels": [
                "metric_object_trajectory",
                "physical_contact_state",
                "physical_contact_force",
                "instrumented_grasp_outcome",
                "command_to_actuation_latency",
                "camera_capture_latency",
            ],
            "reason": "The retained recordings did not instrument these channels.",
            "effect": "Every physical item carries null values with false availability masks; no imputation is allowed.",
        },
        {
            "id": "visual_and_scale_authority_limits",
            "reason": "The 3DGS is monocular relative-scale visual context and the AprilTag result is conditioned on nominal, unmeasured print size.",
            "effect": "Neither artifact supplies metric geometry, collision geometry, or physical calibration authority.",
        },
    ]
    unsigned = {
        "schema_version": OMISSIONS_SCHEMA,
        "campaign_id": str(campaign["campaign_id"]),
        "generated_at": str(campaign["determinism"]["generated_at"]),
        "omissions": sorted(rows, key=lambda row: str(row["id"])),
        "claim_boundary": "An omission is an explicit absence or proof boundary, never an inferred zero or negative observation.",
    }
    return {**unsigned, "omissions_digest": canonical_digest(unsigned)}


def inventory_campaign(
    campaign_path: Path, *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    campaign, evidence, context, counts = _compile_in_memory(
        campaign_path, repo_root=repo_root
    )
    physical_catalog_path = verify_source_binding(
        campaign["source_bindings"]["physical_catalog"], repo_root=repo_root
    )
    physical_catalog = load_json_object(physical_catalog_path, label="physical catalog")
    omissions = _omissions(campaign, evidence, physical_catalog)
    return {
        "schema_version": "sim2claw.sail_evidence_inventory.v1",
        "campaign_id": str(campaign["campaign_id"]),
        "status": "ready",
        "counts": counts,
        "context_artifacts": context,
        "omission_count": len(omissions["omissions"]),
        "proof_classes_separated": True,
        "action_bytes_reconciled": True,
        "sources_hash_verified": True,
        "physical_authority": False,
        "training_admitted": False,
    }


def compile_campaign(
    campaign_path: Path,
    output_root: Path,
    *,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    resolved_campaign = campaign_path if campaign_path.is_absolute() else repo_root / campaign_path
    campaign, evidence, context, counts = _compile_in_memory(
        resolved_campaign, repo_root=repo_root
    )
    physical_catalog_path = verify_source_binding(
        campaign["source_bindings"]["physical_catalog"], repo_root=repo_root
    )
    physical_catalog = load_json_object(physical_catalog_path, label="physical catalog")
    omissions = _omissions(campaign, evidence, physical_catalog)
    output_root.mkdir(parents=True, exist_ok=True)
    evidence_root = output_root / "calibration"
    evidence_bindings: list[dict[str, Any]] = []
    for row in evidence:
        filename = str(row["evidence_id"]).replace(":", "__") + ".json"
        path = evidence_root / filename
        atomic_write_json(path, row)
        evidence_bindings.append(
            {
                "evidence_id": str(row["evidence_id"]),
                "path": f"calibration/{filename}",
                "sha256": sha256_file(path),
                "canonical_digest": str(row["canonical_digest"]),
                "proof_class": str(row["proof_class"]),
                "split_role": str(row["split_role"]),
            }
        )
    omissions_path = output_root / "omissions.json"
    atomic_write_json(omissions_path, omissions)
    catalog_unsigned = {
        "schema_version": CATALOG_SCHEMA,
        "campaign_id": str(campaign["campaign_id"]),
        "generated_at": str(campaign["determinism"]["generated_at"]),
        "proof_class": "proof_separated_retained_evidence_catalog",
        "counts": counts,
        "entries": evidence_bindings,
        "context_artifacts": context,
        "omissions": {"path": "omissions.json", "sha256": sha256_file(omissions_path)},
        "authority": copy.deepcopy(campaign["authority"]),
        "claim_boundary": "The catalog binds retrospective physical teleoperation observations and retained action-frozen simulator replay as distinct proof classes. It grants no promotion, training, policy-selection, or physical authority.",
    }
    catalog = {**catalog_unsigned, "catalog_digest": canonical_digest(catalog_unsigned)}
    catalog_path = output_root / "catalog.json"
    atomic_write_json(catalog_path, catalog)
    receipt = build_compile_receipt(
        campaign_path=resolved_campaign,
        campaign=campaign,
        catalog_path=catalog_path,
        omissions_path=omissions_path,
        evidence_files=evidence_bindings,
        counts=counts,
        repo_root=repo_root,
    )
    receipt_path = output_root / "receipt.json"
    atomic_write_json(receipt_path, receipt)
    verify_compile_receipt(receipt, output_root=output_root)
    for binding in evidence_bindings:
        value = load_json_object(output_root / binding["path"], label="compiled evidence")
        verify_contract(value)
    return {
        "schema_version": "sim2claw.sail_evidence_compile_result.v1",
        "campaign_id": str(campaign["campaign_id"]),
        "status": "compiled",
        "counts": counts,
        "catalog_sha256": sha256_file(catalog_path),
        "omissions_sha256": sha256_file(omissions_path),
        "receipt_sha256": sha256_file(receipt_path),
        "receipt_digest": receipt["receipt_digest"],
        "output_root": str(output_root),
        "physical_authority": False,
        "training_admitted": False,
    }


__all__ = [
    "CATALOG_SCHEMA",
    "CAMPAIGN_SCHEMA",
    "EvidenceImportError",
    "SailContractError",
    "compile_campaign",
    "inventory_campaign",
    "load_campaign",
]
