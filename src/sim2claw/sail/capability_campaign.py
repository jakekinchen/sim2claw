"""Compile TwinWorthiness capability kill-switch and reachability evidence."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Mapping

from ..learning_factory_artifacts import (
    atomic_write_json,
    canonical_digest,
    load_json_object,
    sha256_file,
)
from .contracts import REPO_ROOT, SailContractError, seal_contract, verify_contract
from .twin_worthiness import (
    capability_decision,
    issue_capability_certificate,
    load_capability_contract,
    revoke_capability_certificate,
    validate_capability_certificate,
)

CONFIG_SCHEMA = "sim2claw.sail_twin_capability_campaign.v1"
REPORT_SCHEMA = "sim2claw.sail_twin_capability_report.v1"
RECEIPT_SCHEMA = "sim2claw.sail_twin_capability_receipt.v1"


class CapabilityCampaignError(SailContractError):
    """The capability campaign changed a frozen identity or authority boundary."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CapabilityCampaignError(message)


def _repo_path(repo_root: Path, value: str, label: str) -> Path:
    root = repo_root.resolve()
    path = (root / value).resolve()
    try:
        path.relative_to(root)
    except ValueError as error:
        raise CapabilityCampaignError(f"{label} escapes repository") from error
    return path


def load_config(path: Path, *, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    resolved = path if path.is_absolute() else repo_root / path
    config = load_json_object(resolved, label="SAIL TwinWorthiness capability campaign")
    _require(config.get("schema_version") == CONFIG_SCHEMA, "unsupported capability campaign schema")
    _require(config.get("proof_class") == "deterministic_capability_gate_evaluation", "capability proof class changed")
    _require(not any(config.get("authority", {}).values()), "capability campaign authority widened")
    for name, binding in config["source_bindings"].items():
        source = _repo_path(repo_root, binding["path"], name)
        _require(source.is_file(), f"capability campaign source missing: {name}")
        _require(sha256_file(source) == binding["sha256"], f"capability campaign source changed: {name}")
    contract = load_capability_contract(
        _repo_path(repo_root, config["source_bindings"]["operational_contract"]["path"], "operational contract")
    )
    _require(
        list(contract["learning_factory_stage_requirements"])
        == config["acceptance"]["require_learning_factory_stage_bindings"],
        "Learning Factory capability stage bindings changed",
    )
    _require(config["capability_order"] == ["diagnostics", "data_generation", "policy_selection", "physical_canary", "robot_motion"], "capability order changed")
    _require(len(config["negative_scenarios"]) == len(set(config["negative_scenarios"])) == 7, "negative scenario inventory changed")
    return config


def _request(
    capability: str,
    *,
    scope: Mapping[str, Any],
    identities: Mapping[str, Any],
    external: Mapping[str, Any] | None = None,
    stage_id: str | None = None,
) -> dict[str, Any]:
    return {
        "capability": capability,
        "stage_id": stage_id,
        "consumer": "learning_factory" if stage_id else "capability_campaign",
        "scope": copy.deepcopy(dict(scope)),
        "expected_identities": copy.deepcopy(dict(identities)),
        "external_authority": copy.deepcopy(dict(external or {})),
    }


def _synthetic_base(level: str, certificate_id: str) -> dict[str, Any]:
    physical = level == "TW-PHYSICAL-CANARY"
    identities = {
        "evidence": ["5" * 64],
        "graph": "6" * 64,
        "posterior": "7" * 64,
        "simulator": "8" * 64,
        "evaluator": "9" * 64,
        "policy_candidates": ["a" * 64, "b" * 64, "c" * 64],
    }
    return seal_contract(
        {
            "schema_version": "sim2claw.twin_worthiness_certificate.v1",
            "certificate_id": certificate_id,
            "campaign_id": "synthetic-capability-reachability-fixture",
            "identities": identities,
            "gates": {
                f"TW-G{index}": {
                    "status": "pass",
                    "reason": "synthetic branch-reachability fixture only",
                    "evidence_ids": [f"synthetic-g{index}"],
                }
                for index in range(5)
            },
            "level": level,
            "authority": {
                "data_generation": True,
                "policy_selection": True,
                "physical_canary": physical,
                "robot_motion": False,
            },
            "issued_at": "2026-07-22T09:00:00-05:00",
        }
    )


def _matrix(
    *,
    config: Mapping[str, Any],
    certificate: Mapping[str, Any],
    scope: Mapping[str, Any],
    identities: Mapping[str, Any],
    external: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    rows = {}
    for capability in config["capability_order"]:
        rows[capability] = capability_decision(
            certificate,
            _request(
                capability,
                scope=scope,
                identities=identities,
                external=external,
            ),
            at_time=config["validity"]["decision_time"],
        )
    return rows


def build_report(config: Mapping[str, Any], sources: Mapping[str, Mapping[str, Any]]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    current_base = verify_contract(sources["current_base_certificate"])
    _require(current_base["level"] == config["acceptance"]["expected_current_level"], "current TwinWorthiness level changed")
    issuance = {
        "issuer_owner": "deterministic_sail_evaluator",
        "request_id": "current-retired-workcell-exact-scope-v1",
        "base_certificate_digest": current_base["canonical_digest"],
        "scope": copy.deepcopy(config["current_scope"]),
    }
    current = issue_capability_certificate(
        base_certificate=current_base,
        scope=config["current_scope"],
        not_before=config["validity"]["not_before"],
        expires_at=config["validity"]["expires_at"],
        issuance_request=issuance,
        capability_certificate_id="twcap-retired-workcell-current-20260722-v1",
    )
    current_matrix = _matrix(
        config=config,
        certificate=current,
        scope=config["current_scope"],
        identities=current_base["identities"],
    )
    allowed_current = [name for name, row in current_matrix.items() if row["allowed"]]
    denied_current = [name for name, row in current_matrix.items() if not row["allowed"]]
    _require(allowed_current == config["acceptance"]["expected_current_allowed_capabilities"], "current capability allow-list changed")
    _require(denied_current == config["acceptance"]["expected_current_denied_capabilities"], "current capability deny-list changed")

    selection_base = _synthetic_base("TW-SELECTION", "synthetic-selection-reachability-v1")
    selection = issue_capability_certificate(
        base_certificate=selection_base,
        scope=config["synthetic_fixture"]["selection_scope"],
        not_before=config["validity"]["not_before"],
        expires_at=config["validity"]["expires_at"],
        issuance_request={"issuer_owner": "deterministic_sail_evaluator", "request_id": "synthetic-selection-reachability-v1"},
    )
    selection_matrix = _matrix(
        config=config,
        certificate=selection,
        scope=config["synthetic_fixture"]["selection_scope"],
        identities=selection_base["identities"],
    )
    _require(selection_matrix["data_generation"]["allowed"] and selection_matrix["policy_selection"]["allowed"], "selection fixture branches are unreachable")
    _require(not selection_matrix["physical_canary"]["allowed"] and not selection_matrix["robot_motion"]["allowed"], "selection fixture gained physical authority")

    physical_base = _synthetic_base("TW-PHYSICAL-CANARY", "synthetic-physical-reachability-v1")
    physical = issue_capability_certificate(
        base_certificate=physical_base,
        scope=config["synthetic_fixture"]["physical_scope"],
        not_before=config["validity"]["not_before"],
        expires_at=config["validity"]["expires_at"],
        issuance_request={"issuer_owner": "deterministic_sail_evaluator", "request_id": "synthetic-physical-reachability-v1"},
    )
    physical_matrix = _matrix(
        config=config,
        certificate=physical,
        scope=config["synthetic_fixture"]["physical_scope"],
        identities=physical_base["identities"],
        external=config["synthetic_fixture"]["external_physical_authority"],
    )
    _require(physical_matrix["physical_canary"]["allowed"] and physical_matrix["robot_motion"]["allowed"], "physical fixture branches are unreachable")

    base_request = _request(
        "data_generation",
        scope=config["current_scope"],
        identities=current_base["identities"],
        stage_id="LF-08",
    )
    negative: dict[str, dict[str, Any]] = {}
    negative["missing_certificate"] = capability_decision(None, base_request, at_time=config["validity"]["decision_time"])
    negative["legacy_unscoped_certificate"] = capability_decision(current_base, base_request, at_time=config["validity"]["decision_time"])
    tampered = copy.deepcopy(current)
    tampered["scope"]["twin_id"] = "tampered"
    negative["tampered_certificate"] = capability_decision(tampered, base_request, at_time=config["validity"]["decision_time"])
    scope_request = copy.deepcopy(base_request)
    scope_request["scope"]["distribution_id"] = "wrong-distribution"
    negative["scope_mismatch"] = capability_decision(current, scope_request, at_time=config["validity"]["decision_time"])
    identity_request = copy.deepcopy(base_request)
    identity_request["expected_identities"]["simulator"] = "0" * 64
    negative["identity_mismatch"] = capability_decision(current, identity_request, at_time=config["validity"]["decision_time"])
    negative["expired_certificate"] = capability_decision(current, base_request, at_time="2028-07-22T09:01:00-05:00")
    revoked = revoke_capability_certificate(
        current,
        reason="synthetic revocation-path evaluation",
        issuer_owner="deterministic_sail_evaluator",
    )
    negative["revoked_certificate"] = capability_decision(revoked, base_request, at_time=config["validity"]["decision_time"])
    _require(list(negative) == config["negative_scenarios"], "negative scenario order changed")
    _require(all(not row["allowed"] for row in negative.values()), "a negative capability scenario was allowed")

    contract = load_capability_contract()
    unsigned = {
        "schema_version": REPORT_SCHEMA,
        "campaign_id": config["campaign_id"],
        "proof_class": config["proof_class"],
        "claim_boundary": config["claim_boundary"],
        "current": {
            "base_certificate_id": current_base["certificate_id"],
            "base_certificate_level": current_base["level"],
            "capability_certificate_digest": current["canonical_digest"],
            "scope": copy.deepcopy(config["current_scope"]),
            "matrix": current_matrix,
            "allowed_capabilities": allowed_current,
            "denied_capabilities": denied_current,
            "training_admitted": False,
            "policy_selection_admitted": False,
            "physical_authority": False,
        },
        "synthetic_reachability": {
            "proof_class": "synthetic_capability_fixture_not_real_authority",
            "selection": {"certificate_digest": selection["canonical_digest"], "matrix": selection_matrix},
            "physical": {"certificate_digest": physical["canonical_digest"], "matrix": physical_matrix},
            "real_capability_claim": False,
        },
        "revocation_evaluation": negative,
        "learning_factory_stage_requirements": copy.deepcopy(contract["learning_factory_stage_requirements"]),
        "minimum_new_evidence": copy.deepcopy(contract["minimum_new_evidence"]),
        "proof_class_boundaries": copy.deepcopy(contract["proof_classes"]),
        "proof_class_promotion_is_implicit": False,
        "golden_cases": {
            "GOLD-17": current_base["gates"]["TW-G2"]["status"] == "not_evaluable" and not current_matrix["data_generation"]["allowed"],
            "GOLD-18": current_base["gates"]["TW-G3"]["status"] == "not_evaluable" and not current_matrix["policy_selection"]["allowed"],
            "GOLD-19": not negative["tampered_certificate"]["allowed"],
        },
        "authority": copy.deepcopy(config["authority"]),
    }
    _require(all(unsigned["golden_cases"].values()), "GOLD-17 through GOLD-19 did not pass")
    report = {**unsigned, "report_digest": canonical_digest(unsigned)}
    return report, current, selection, physical


def verify_receipt(receipt: Mapping[str, Any], *, output_root: Path, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(receipt))
    _require(normalized.get("schema_version") == RECEIPT_SCHEMA, "unexpected capability receipt schema")
    observed = normalized.pop("receipt_digest", None)
    _require(observed == canonical_digest(normalized), "capability receipt digest mismatch")
    _require(not any(normalized["authority"].values()), "capability receipt authority widened")
    config_path = _repo_path(repo_root, normalized["config"]["path"], "receipt config")
    _require(sha256_file(config_path) == normalized["config"]["sha256"], "capability campaign config changed")
    for name, binding in normalized["outputs"].items():
        output = output_root / binding["path"]
        _require(output.is_file() and sha256_file(output) == binding["sha256"], f"capability output changed: {name}")
    return {**normalized, "receipt_digest": observed}


def compile_campaign(config_path: Path, *, output_root: Path, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    resolved = config_path if config_path.is_absolute() else repo_root / config_path
    config = load_config(resolved, repo_root=repo_root)
    sources = {
        name: load_json_object(_repo_path(repo_root, binding["path"], name), label=name)
        for name, binding in config["source_bindings"].items()
    }
    report, current, selection, physical = build_report(config, sources)
    output_root.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "report": ("capability_report.json", report),
        "current_capability_certificate": ("current_capability_certificate.json", current),
        "synthetic_selection_certificate": ("synthetic_selection_certificate.json", selection),
        "synthetic_physical_certificate": ("synthetic_physical_certificate.json", physical),
    }
    for _name, (filename, artifact) in artifacts.items():
        atomic_write_json(output_root / filename, artifact)
    outputs = {
        name: {"path": filename, "sha256": sha256_file(output_root / filename)}
        for name, (filename, _artifact) in artifacts.items()
    }
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "campaign_id": config["campaign_id"],
        "generated_at": config["generated_at"],
        "config": {"path": resolved.resolve().relative_to(repo_root.resolve()).as_posix(), "sha256": sha256_file(resolved)},
        "compiler_sha256": sha256_file(Path(__file__).resolve()),
        "source_sha256": {name: binding["sha256"] for name, binding in sorted(config["source_bindings"].items())},
        "outputs": outputs,
        "current_level": report["current"]["base_certificate_level"],
        "current_allowed_capabilities": report["current"]["allowed_capabilities"],
        "current_denied_capabilities": report["current"]["denied_capabilities"],
        "negative_scenario_count": len(report["revocation_evaluation"]),
        "all_negative_scenarios_denied": all(not row["allowed"] for row in report["revocation_evaluation"].values()),
        "golden_cases": copy.deepcopy(report["golden_cases"]),
        "authority": copy.deepcopy(config["authority"]),
    }
    receipt = {**unsigned, "receipt_digest": canonical_digest(unsigned)}
    atomic_write_json(output_root / "receipt.json", receipt)
    verify_receipt(receipt, output_root=output_root, repo_root=repo_root)
    return {
        "schema_version": "sim2claw.sail_twin_capability_compile_result.v1",
        "status": "compiled",
        "current_level": receipt["current_level"],
        "current_allowed_capabilities": receipt["current_allowed_capabilities"],
        "negative_scenario_count": receipt["negative_scenario_count"],
        "golden_cases": receipt["golden_cases"],
        "report_sha256": outputs["report"]["sha256"],
        "current_capability_certificate_sha256": outputs["current_capability_certificate"]["sha256"],
        "receipt_sha256": sha256_file(output_root / "receipt.json"),
        "receipt_digest": receipt["receipt_digest"],
        "output_root": str(output_root),
        "training_admitted": False,
        "physical_authority": False,
    }


__all__ = [
    "CapabilityCampaignError",
    "build_report",
    "compile_campaign",
    "load_config",
    "verify_receipt",
]
