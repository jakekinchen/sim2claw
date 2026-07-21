"""Typed, fail-closed contracts for the hardware-free Sim2Claw GapBench."""

from __future__ import annotations

import copy
import json
import math
import shutil
from pathlib import Path
from typing import Any

from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
    sha256_file,
)


CASE_SCHEMA = "sim2claw.gapbench_case.v1"
ATTEMPT_SCHEMA = "sim2claw.gapbench_agent_attempt.v1"
CAMPAIGN_SCHEMA = "sim2claw.gapbench_campaign_summary.v1"
RECEIPT_SCHEMA = "sim2claw.gapbench_score_receipt.v1"
PROOF_CLASS = "synthetic_benchmark"
CLAIM_BOUNDARY = "synthetic_only"

FAULT_FAMILIES = (
    "reset_support",
    "coordinate_frame",
    "camera_preprocessing",
    "control_latency",
    "joint_convention",
    "contact_prior",
)

REQUIRED_BUDGETS = ("probes", "public_evaluations", "terminal_submissions")


class GapBenchContractError(FactoryArtifactError):
    """Raised when a benchmark artifact crosses or violates its contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GapBenchContractError(message)


def _finite(value: Any, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise GapBenchContractError(f"{label} must be numeric") from error
    _require(math.isfinite(result), f"{label} must be finite")
    return result


def _safe_relative_path(value: Any, label: str) -> Path:
    _require(isinstance(value, str) and value, f"{label} must be a path string")
    path = Path(value)
    _require(not path.is_absolute(), f"{label} must be relative")
    _require(".." not in path.parts, f"{label} may not traverse parents")
    _require(path.parts[0] not in {"~", ".git"}, f"{label} uses a forbidden root")
    return path


def validate_case(case: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize a public case without consulting sealed data."""

    _require(case.get("schema_version") == CASE_SCHEMA, "unsupported case schema")
    case_id = case.get("case_id")
    _require(isinstance(case_id, str) and case_id, "case_id is required")
    _require(case.get("proof_class") == PROOF_CLASS, "invalid proof class")
    _require(case.get("role") == "public", "agent cases must have public role")
    _require(case.get("fault_family") == "unknown", "public case may not disclose its seeded fault family")

    identities = case.get("identities")
    _require(isinstance(identities, dict), "identities must be an object")
    for name in (
        "dataset",
        "policy",
        "baseline_simulator",
        "public_evaluator",
        "sealed_evaluator_service",
    ):
        _require(isinstance(identities.get(name), str) and identities[name], f"missing identity: {name}")

    envelopes = case.get("parameter_envelopes")
    _require(isinstance(envelopes, dict) and envelopes, "parameter envelopes are required")
    for name, bounds in envelopes.items():
        _require(isinstance(name, str) and name, "parameter name is invalid")
        _require(isinstance(bounds, list) and len(bounds) == 2, f"bounds invalid: {name}")
        lower, upper = (_finite(bounds[0], f"{name}.lower"), _finite(bounds[1], f"{name}.upper"))
        _require(lower < upper, f"bounds are unordered: {name}")

    baseline = case.get("baseline_candidate")
    validate_candidate(case, baseline)

    evidence = case.get("evidence_manifest")
    _require(isinstance(evidence, list) and evidence, "evidence manifest is required")
    artifact_ids: set[str] = set()
    for row in evidence:
        _require(isinstance(row, dict), "evidence row must be an object")
        artifact_id = row.get("artifact_id")
        _require(isinstance(artifact_id, str) and artifact_id not in artifact_ids, "evidence artifact_id is invalid or duplicated")
        artifact_ids.add(artifact_id)
        _safe_relative_path(row.get("path"), "evidence path")
        digest = row.get("sha256")
        _require(isinstance(digest, str) and len(digest) == 64, "evidence digest is invalid")

    probes = case.get("probe_menu")
    _require(isinstance(probes, list), "probe menu must be a list")
    probe_ids: set[str] = set()
    for probe in probes:
        _require(isinstance(probe, dict), "probe entry must be an object")
        probe_id = probe.get("probe_id")
        _require(isinstance(probe_id, str) and probe_id not in probe_ids, "probe_id is invalid or duplicated")
        probe_ids.add(probe_id)
        _require(probe.get("mode") in {"simulated", "read_only"}, "physical probes are forbidden")
        _require(_finite(probe.get("cost", 1), "probe cost") > 0, "probe cost must be positive")

    budgets = case.get("budgets")
    _require(isinstance(budgets, dict), "budgets must be an object")
    for key in REQUIRED_BUDGETS:
        _require(isinstance(budgets.get(key), int) and budgets[key] >= 0, f"invalid budget: {key}")
    _require(budgets["terminal_submissions"] == 1, "exactly one terminal submission is required")

    bindings = case.get("bindings")
    _require(isinstance(bindings, dict), "benchmark bindings are required")
    for name in ("prompt_sha256", "skill_bundle_sha256", "tool_contract_sha256"):
        digest = bindings.get(name)
        _require(isinstance(digest, str) and len(digest) == 64, f"invalid binding digest: {name}")
    _require(bindings.get("sandbox_image") == "sim2claw-gapbench:0.1.0", "sandbox image identity mismatch")

    forbidden = case.get("forbidden_actions")
    _require(isinstance(forbidden, list) and forbidden, "forbidden actions must be explicit")
    forbidden_text = " ".join(str(item).lower() for item in forbidden)
    for boundary in ("hidden", "credential", "robot", "docker socket", "network"):
        _require(boundary in forbidden_text, f"forbidden action boundary is missing: {boundary}")

    stored_digest = case.get("case_sha256")
    if stored_digest is not None:
        unsigned = {key: value for key, value in case.items() if key != "case_sha256"}
        _require(stored_digest == canonical_digest(unsigned), "case digest mismatch")
    return copy.deepcopy(case)


def validate_candidate(case: dict[str, Any], candidate: Any) -> dict[str, float]:
    _require(isinstance(candidate, dict), "candidate must be an object")
    parameters = candidate.get("parameters")
    _require(isinstance(parameters, dict), "candidate.parameters must be an object")
    envelopes = case.get("parameter_envelopes")
    _require(isinstance(envelopes, dict), "case parameter envelopes are missing")
    _require(set(parameters) == set(envelopes), "candidate parameters must exactly match the editable surface")
    normalized: dict[str, float] = {}
    for name, bounds in envelopes.items():
        value = _finite(parameters[name], f"candidate parameter {name}")
        lower, upper = float(bounds[0]), float(bounds[1])
        _require(lower <= value <= upper, f"candidate parameter outside envelope: {name}")
        normalized[name] = value
    return normalized


def validate_hypotheses(value: Any) -> list[dict[str, Any]]:
    _require(isinstance(value, list) and value, "hypotheses must be a non-empty list")
    _require(len(value) <= len(FAULT_FAMILIES), "too many hypotheses")
    normalized: list[dict[str, Any]] = []
    mechanisms: set[str] = set()
    for index, row in enumerate(value, start=1):
        _require(isinstance(row, dict), "hypothesis must be an object")
        mechanism = row.get("mechanism")
        _require(mechanism in FAULT_FAMILIES and mechanism not in mechanisms, "invalid or duplicate hypothesis mechanism")
        mechanisms.add(mechanism)
        _require(row.get("rank") == index, "hypothesis ranks must be contiguous and ordered")
        for field in ("evidence", "discriminating_prediction"):
            _require(isinstance(row.get(field), str) and row[field].strip(), f"hypothesis {field} is required")
        uncertainty = _finite(row.get("uncertainty"), "hypothesis uncertainty")
        _require(0.0 <= uncertainty <= 1.0, "hypothesis uncertainty must be in [0, 1]")
        abstain = row.get("abstain", False)
        _require(isinstance(abstain, bool), "hypothesis abstain must be boolean")
        normalized.append({
            "rank": index,
            "mechanism": mechanism,
            "evidence": row["evidence"].strip(),
            "discriminating_prediction": row["discriminating_prediction"].strip(),
            "uncertainty": uncertainty,
            "abstain": abstain,
        })
    return normalized


def validate_prediction(value: Any) -> dict[str, Any]:
    _require(isinstance(value, dict), "prediction must be an object")
    family = value.get("fault_family")
    _require(family in FAULT_FAMILIES, "prediction fault_family is invalid")
    uncertainty = _finite(value.get("uncertainty"), "prediction uncertainty")
    _require(0.0 <= uncertainty <= 1.0, "prediction uncertainty must be in [0, 1]")
    rationale = value.get("heldout_consequence")
    _require(isinstance(rationale, str) and rationale.strip(), "heldout_consequence is required")
    return {
        "fault_family": family,
        "uncertainty": uncertainty,
        "heldout_consequence": rationale.strip(),
    }


def freeze_public_case(source: dict[str, Any], destination: Path) -> Path:
    """Materialize one public packet and intentionally discard sealed-looking keys."""

    _require(source.get("schema_version") == CASE_SCHEMA, "unsupported source case schema")
    public = copy.deepcopy(source)
    evidence = public.pop("public_evidence", None)
    _require(isinstance(evidence, dict) and evidence, "source case needs public_evidence")
    for forbidden_key in ("target_parameters", "hidden_rows", "probe_results", "promotion_thresholds"):
        _require(forbidden_key not in public, f"public source includes sealed key: {forbidden_key}")

    if destination.exists():
        shutil.rmtree(destination)
    evidence_dir = destination / "evidence"
    candidate_dir = destination / "candidate"
    evidence_dir.mkdir(parents=True)
    candidate_dir.mkdir(parents=True)

    manifest: list[dict[str, Any]] = []
    for artifact_id, artifact in sorted(evidence.items()):
        _require(isinstance(artifact_id, str) and artifact_id, "public evidence id is invalid")
        _require(isinstance(artifact, dict), "public evidence artifact must be an object")
        relative = Path("evidence") / f"{artifact_id}.json"
        path = destination / relative
        atomic_write_json(path, artifact)
        manifest.append({
            "artifact_id": artifact_id,
            "path": relative.as_posix(),
            "media_type": "application/json",
            "sha256": sha256_file(path),
        })

    public["evidence_manifest"] = manifest
    public["case_sha256"] = canonical_digest(public)
    validate_case(public)
    atomic_write_json(destination / "case.json", public)
    atomic_write_json(destination / "candidate" / "baseline.json", public["baseline_candidate"])
    return destination


def load_public_case(packet_root: Path) -> dict[str, Any]:
    case = validate_case(load_json_object(packet_root / "case.json", label="GapBench case"))
    for row in case["evidence_manifest"]:
        path = packet_root / _safe_relative_path(row["path"], "evidence path")
        _require(path.is_file(), f"missing evidence artifact: {row['artifact_id']}")
        _require(sha256_file(path) == row["sha256"], f"evidence digest mismatch: {row['artifact_id']}")
    return case


def load_candidate(packet_root: Path, candidate_ref: str, case: dict[str, Any]) -> dict[str, Any]:
    relative = _safe_relative_path(candidate_ref, "candidate_ref")
    _require(relative.parts[0] == "candidate", "candidate_ref must be inside candidate/")
    path = packet_root / relative
    _require(path.is_file(), "candidate_ref does not exist")
    candidate = load_json_object(path, label="GapBench candidate")
    normalized = validate_candidate(case, candidate)
    return {"parameters": normalized, "candidate_sha256": sha256_file(path), "candidate_ref": relative.as_posix()}


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))
