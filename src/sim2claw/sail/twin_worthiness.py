"""TwinWorthiness truth tables and exact-scope downstream capability gates."""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from jsonschema import Draft202012Validator, FormatChecker

from ..learning_factory_artifacts import canonical_digest, sha256_file
from .contracts import REPO_ROOT, SailContractError, seal_contract, verify_contract


CONTRACT_PATH = REPO_ROOT / "configs" / "sail" / "twin_worthiness_v1.json"
CAPABILITY_CONTRACT_PATH = REPO_ROOT / "configs" / "sail" / "twin_capability_v1.json"
CAPABILITY_SCHEMA_VERSION = "sim2claw.twin_worthiness_capability_certificate.v1"
CAPABILITY_DECISION_SCHEMA = "sim2claw.twin_capability_decision.v1"


class TwinCapabilityDenied(SailContractError):
    """A downstream consumer lacks a valid exact-scope capability."""

    def __init__(self, decision: Mapping[str, Any]):
        self.decision = copy.deepcopy(dict(decision))
        reasons = ", ".join(self.decision.get("denial_codes", [])) or "denied"
        super().__init__(f"TwinWorthiness capability denied: {reasons}")


def load_twin_worthiness_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != "sim2claw.twin_worthiness_contract.v1":
        raise SailContractError("TwinWorthiness contract version changed")
    return value


def load_capability_contract(path: Path = CAPABILITY_CONTRACT_PATH) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != "sim2claw.twin_capability_contract.v1":
        raise SailContractError("TwinWorthiness capability contract version changed")
    base = (REPO_ROOT / value["base_contract"]["path"]).resolve()
    if not base.is_file() or sha256_file(base) != value["base_contract"]["sha256"]:
        raise SailContractError("TwinWorthiness base contract identity changed")
    schema = (REPO_ROOT / value["schema"]["path"]).resolve()
    if not schema.is_file():
        raise SailContractError("TwinWorthiness capability schema is missing")
    if value.get("training_code_can_issue_or_widen_certificate") is not False:
        raise SailContractError("training code gained certificate issuance authority")
    if value.get("proof_class_promotion_is_implicit") is not False:
        raise SailContractError("proof classes may not promote implicitly")
    return value


def _parse_time(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise SailContractError(f"invalid {label}: {value!r}") from error
    if parsed.tzinfo is None:
        raise SailContractError(f"{label} must be timezone-aware")
    return parsed.astimezone(UTC)


def _capability_schema(contract: Mapping[str, Any]) -> dict[str, Any]:
    path = (REPO_ROOT / contract["schema"]["path"]).resolve()
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SailContractError(f"invalid TwinWorthiness capability schema: {error}") from error
    Draft202012Validator.check_schema(schema)
    return schema


def validate_capability_certificate(
    certificate: Mapping[str, Any],
    *,
    contract_path: Path = CAPABILITY_CONTRACT_PATH,
) -> dict[str, Any]:
    """Validate the operational envelope and its immutable scientific verdict."""

    normalized = copy.deepcopy(dict(certificate))
    contract = load_capability_contract(contract_path)
    validator = Draft202012Validator(
        _capability_schema(contract), format_checker=FormatChecker()
    )
    errors = sorted(validator.iter_errors(normalized), key=lambda item: list(item.path))
    if errors:
        error = errors[0]
        location = ".".join(str(part) for part in error.path) or "<root>"
        raise SailContractError(f"TwinWorthiness capability schema failed at {location}: {error.message}")
    observed = normalized.pop("canonical_digest", None)
    if observed != canonical_digest(normalized):
        raise SailContractError("TwinWorthiness capability canonical digest mismatch")
    base = verify_contract(normalized["base_certificate"])
    issuance = normalized["issuance"]
    if issuance["base_certificate_digest"] != base["canonical_digest"]:
        raise SailContractError("capability envelope binds another base certificate")
    if issuance["base_contract_sha256"] != contract["base_contract"]["sha256"]:
        raise SailContractError("capability envelope binds another base contract")
    if issuance["operational_contract_sha256"] != sha256_file(contract_path):
        raise SailContractError("capability envelope binds another operational contract")
    validity = normalized["validity"]
    not_before = _parse_time(validity["not_before"], "not_before")
    expires_at = _parse_time(validity["expires_at"], "expires_at")
    if expires_at <= not_before:
        raise SailContractError("capability expiry must follow not_before")
    if (expires_at - not_before).total_seconds() > float(contract["maximum_validity_seconds"]):
        raise SailContractError("capability validity exceeds the frozen maximum")
    if validity["revoked"] and not validity["revocation_reason"]:
        raise SailContractError("revoked capability lacks a reason")
    if not validity["revoked"] and validity["revocation_reason"] is not None:
        raise SailContractError("unrevoked capability carries a revocation reason")
    return {**normalized, "canonical_digest": observed}


def issue_capability_certificate(
    *,
    base_certificate: Mapping[str, Any],
    scope: Mapping[str, Any],
    not_before: str,
    expires_at: str,
    issuance_request: Mapping[str, Any],
    capability_certificate_id: str | None = None,
    contract_path: Path = CAPABILITY_CONTRACT_PATH,
) -> dict[str, Any]:
    """Evaluator-only issuance; consumers cannot infer or widen authority."""

    contract = load_capability_contract(contract_path)
    request = copy.deepcopy(dict(issuance_request))
    if request.get("issuer_owner") != contract["evaluator_owner"]:
        raise SailContractError("only the deterministic SAIL evaluator may issue capability envelopes")
    base = verify_contract(base_certificate)
    required_scope = contract["required_scope_fields"]
    if set(scope) != set(required_scope):
        raise SailContractError("capability scope fields changed")
    if any(not str(scope[name]) for name in required_scope):
        raise SailContractError("capability scope contains an empty identity")
    for name in ("task_contract_sha256", "distribution_sha256"):
        value = str(scope[name])
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise SailContractError(f"capability scope has invalid {name}")
    scope_digest = canonical_digest(dict(scope))
    unsigned = {
        "schema_version": CAPABILITY_SCHEMA_VERSION,
        "capability_certificate_id": capability_certificate_id
        or f"twcap-{base['certificate_id']}-{scope_digest[:16]}",
        "base_certificate": copy.deepcopy(base),
        "scope": copy.deepcopy(dict(scope)),
        "validity": {
            "not_before": not_before,
            "expires_at": expires_at,
            "revoked": False,
            "revocation_reason": None,
        },
        "issuance": {
            "issuer_owner": contract["evaluator_owner"],
            "request_digest": canonical_digest(request),
            "base_certificate_digest": base["canonical_digest"],
            "base_contract_sha256": contract["base_contract"]["sha256"],
            "operational_contract_sha256": sha256_file(contract_path),
        },
    }
    certificate = {**unsigned, "canonical_digest": canonical_digest(unsigned)}
    return validate_capability_certificate(certificate, contract_path=contract_path)


def revoke_capability_certificate(
    certificate: Mapping[str, Any],
    *,
    reason: str,
    issuer_owner: str,
    contract_path: Path = CAPABILITY_CONTRACT_PATH,
) -> dict[str, Any]:
    contract = load_capability_contract(contract_path)
    if issuer_owner != contract["evaluator_owner"] or not reason.strip():
        raise SailContractError("revocation requires the evaluator owner and a reason")
    normalized = validate_capability_certificate(certificate, contract_path=contract_path)
    unsigned = copy.deepcopy(normalized)
    unsigned.pop("canonical_digest")
    unsigned["validity"]["revoked"] = True
    unsigned["validity"]["revocation_reason"] = reason.strip()
    revoked = {**unsigned, "canonical_digest": canonical_digest(unsigned)}
    return validate_capability_certificate(revoked, contract_path=contract_path)


def _level_at_least(observed: str, required: str) -> bool:
    order = (
        "NONE",
        "TW-DIAGNOSTIC",
        "TW-REPLAY",
        "TW-DATA",
        "TW-SELECTION",
        "TW-PHYSICAL-CANARY",
    )
    try:
        return order.index(observed) >= order.index(required)
    except ValueError:
        return False


def _decision(
    *,
    request: Mapping[str, Any],
    allowed: bool,
    denial_codes: Sequence[str],
    failed_gates: Sequence[str],
    minimum_new_evidence: Sequence[str],
    certificate_digest: str | None,
    certificate_level: str | None,
) -> dict[str, Any]:
    unsigned = {
        "schema_version": CAPABILITY_DECISION_SCHEMA,
        "capability": str(request.get("capability", "")),
        "stage_id": request.get("stage_id"),
        "allowed": bool(allowed),
        "denial_codes": sorted(set(str(item) for item in denial_codes)),
        "failed_gates": sorted(set(str(item) for item in failed_gates)),
        "minimum_new_evidence": list(dict.fromkeys(str(item) for item in minimum_new_evidence)),
        "certificate_digest": certificate_digest,
        "certificate_level": certificate_level,
        "request_digest": canonical_digest(dict(request)),
        "verdict_owner": "learning_factory",
        "training_or_policy_code_can_override": False,
    }
    return {**unsigned, "decision_digest": canonical_digest(unsigned)}


def capability_decision(
    certificate: Mapping[str, Any] | None,
    request: Mapping[str, Any],
    *,
    at_time: str | None = None,
    contract_path: Path = CAPABILITY_CONTRACT_PATH,
) -> dict[str, Any]:
    """Return a non-throwing, content-addressed allow/deny verdict for one use."""

    contract = load_capability_contract(contract_path)
    requested = copy.deepcopy(dict(request))
    capability = str(requested.get("capability", ""))
    requirements = contract["capability_requirements"].get(capability)
    if requirements is None:
        return _decision(
            request=requested,
            allowed=False,
            denial_codes=["unknown_capability"],
            failed_gates=[],
            minimum_new_evidence=[],
            certificate_digest=None,
            certificate_level=None,
        )
    if certificate is None:
        return _decision(
            request=requested,
            allowed=False,
            denial_codes=["missing_capability_certificate"],
            failed_gates=[],
            minimum_new_evidence=["Provide an evaluator-issued, exact-scope TwinWorthiness capability certificate."],
            certificate_digest=None,
            certificate_level=None,
        )
    if certificate.get("schema_version") == "sim2claw.twin_worthiness_certificate.v1":
        return _decision(
            request=requested,
            allowed=False,
            denial_codes=["legacy_unscoped_certificate"],
            failed_gates=[],
            minimum_new_evidence=["Wrap the verified scientific verdict in an evaluator-issued exact-scope, expiring capability certificate."],
            certificate_digest=certificate.get("canonical_digest"),
            certificate_level=certificate.get("level"),
        )
    try:
        normalized = validate_capability_certificate(certificate, contract_path=contract_path)
    except (SailContractError, KeyError, TypeError, ValueError):
        return _decision(
            request=requested,
            allowed=False,
            denial_codes=["invalid_or_tampered_certificate"],
            failed_gates=[],
            minimum_new_evidence=["Restore the last evaluator-issued canonical certificate or request a new evaluation."],
            certificate_digest=None,
            certificate_level=None,
        )

    base = normalized["base_certificate"]
    denials: list[str] = []
    failed_gates: list[str] = []
    minimum: list[str] = []
    now = _parse_time(at_time or datetime.now(UTC).isoformat(), "decision time")
    validity = normalized["validity"]
    if now < _parse_time(validity["not_before"], "not_before"):
        denials.append("certificate_not_yet_valid")
    if now >= _parse_time(validity["expires_at"], "expires_at"):
        denials.append("certificate_expired")
    if validity["revoked"]:
        denials.append("certificate_revoked")

    requested_scope = requested.get("scope")
    if not isinstance(requested_scope, Mapping) or dict(requested_scope) != normalized["scope"]:
        denials.append("scope_mismatch")
        minimum.append("Request a certificate for the exact twin, workcell, task, and distribution identities.")
    expected_identities = requested.get("expected_identities")
    if not isinstance(expected_identities, Mapping) or dict(expected_identities) != base["identities"]:
        denials.append("identity_mismatch")
        minimum.append("Re-evaluate or reissue after binding the exact evidence, graph, posterior, simulator, evaluator, and policy identities.")

    required_level = requirements["minimum_level"]
    if not _level_at_least(str(base["level"]), required_level):
        denials.append("insufficient_twin_worthiness_level")
        for gate in load_twin_worthiness_contract()["levels"][required_level]:
            if base["gates"][gate]["status"] != "pass":
                failed_gates.append(gate)
                minimum.append(contract["minimum_new_evidence"][gate])
    authority_field = requirements["base_authority_field"]
    if authority_field is not None and base["authority"].get(authority_field) is not True:
        denials.append("base_authority_closed")
    external = requested.get("external_authority")
    external = dict(external) if isinstance(external, Mapping) else {}
    missing_external = [
        field for field in requirements["external_authority_fields"] if external.get(field) is not True
    ]
    if missing_external:
        denials.append("external_physical_authority_missing")
        minimum.append(contract["minimum_new_evidence"]["physical_authority"])

    return _decision(
        request=requested,
        allowed=not denials,
        denial_codes=denials,
        failed_gates=failed_gates,
        minimum_new_evidence=minimum,
        certificate_digest=normalized["canonical_digest"],
        certificate_level=base["level"],
    )


def require_capability_decision(
    decision: Mapping[str, Any], *, capability: str
) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(decision))
    observed = normalized.pop("decision_digest", None)
    if observed != canonical_digest(normalized):
        raise TwinCapabilityDenied(
            _decision(
                request={"capability": capability},
                allowed=False,
                denial_codes=["invalid_capability_decision"],
                failed_gates=[],
                minimum_new_evidence=[],
                certificate_digest=None,
                certificate_level=None,
            )
        )
    if normalized.get("capability") != capability or normalized.get("allowed") is not True:
        raise TwinCapabilityDenied({**normalized, "decision_digest": observed})
    return {**normalized, "decision_digest": observed}


def require_capability_context(
    context: Mapping[str, Any], *, capability: str
) -> dict[str, Any]:
    """Recompute a decision from certificate bytes before a consumer mutates state."""

    certificate = context.get("certificate")
    request = context.get("request")
    if not isinstance(certificate, Mapping) or not isinstance(request, Mapping):
        raise TwinCapabilityDenied(
            capability_decision(None, {"capability": capability})
        )
    decision = capability_decision(
        certificate,
        request,
        at_time=str(context.get("at_time") or datetime.now(UTC).isoformat()),
    )
    return require_capability_decision(decision, capability=capability)


def gate_verdict(
    *,
    required: Sequence[str],
    available: Mapping[str, bool],
    threshold_failures: Sequence[str],
) -> dict[str, Any]:
    missing = sorted(name for name in required if not available.get(name, False))
    if missing:
        return {
            "status": "not_evaluable",
            "reason": "missing required observations: " + ", ".join(missing),
            "evidence_ids": [],
        }
    if threshold_failures:
        return {
            "status": "fail",
            "reason": "frozen thresholds failed: " + ", ".join(threshold_failures),
            "evidence_ids": [],
        }
    return {"status": "pass", "reason": "all frozen requirements pass", "evidence_ids": []}


def resolve_level(
    gates: Mapping[str, Mapping[str, Any]], *, physical_canary_authorized: bool = False
) -> str:
    contract = load_twin_worthiness_contract()
    ordered = [
        "TW-DIAGNOSTIC",
        "TW-REPLAY",
        "TW-DATA",
        "TW-SELECTION",
    ]
    level = "NONE"
    for candidate in ordered:
        required = contract["levels"][candidate]
        if all(gates.get(gate, {}).get("status") == "pass" for gate in required):
            level = candidate
        else:
            break
    if level == "TW-SELECTION" and physical_canary_authorized:
        return "TW-PHYSICAL-CANARY"
    return level


def capabilities_for_level(level: str) -> dict[str, bool]:
    contract = load_twin_worthiness_contract()
    if level == "NONE":
        return {
            "diagnostics": False,
            "data_generation": False,
            "policy_selection": False,
            "physical_canary": False,
        }
    try:
        return dict(contract["capabilities"][level])
    except KeyError as error:
        raise SailContractError(f"unknown TwinWorthiness level: {level}") from error


def issue_fixture_certificate(unsigned: Mapping[str, Any]) -> dict[str, Any]:
    """Seal a certificate fixture after its level and authority agree."""

    return seal_contract(unsigned)


def certificate_is_available(certificate: Mapping[str, Any]) -> bool:
    try:
        verify_contract(certificate)
    except SailContractError:
        return False
    return True
