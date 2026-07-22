"""Validation and immutable identity helpers for the SAIL v1 contracts."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError

from ..learning_factory_artifacts import canonical_digest, sha256_file


REPO_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_ROOT = REPO_ROOT / "configs" / "sail" / "schemas"
DIGEST_FIELD = "canonical_digest"

SCHEMA_PATHS = {
    "CalibrationEvidence.v1": SCHEMA_ROOT / "calibration_evidence_v1.json",
    "ResidualField.v1": SCHEMA_ROOT / "residual_field_v1.json",
    "PhysicalMechanism.v1": SCHEMA_ROOT / "physical_mechanism_v1.json",
    "Intervention.v1": SCHEMA_ROOT / "intervention_v1.json",
    "TwinWorthinessCertificate.v1": SCHEMA_ROOT
    / "twin_worthiness_certificate_v1.json",
}

VERSION_TO_CONTRACT = {
    "sim2claw.calibration_evidence.v1": "CalibrationEvidence.v1",
    "sim2claw.residual_field.v1": "ResidualField.v1",
    "sim2claw.physical_mechanism.v1": "PhysicalMechanism.v1",
    "sim2claw.intervention.v1": "Intervention.v1",
    "sim2claw.twin_worthiness_certificate.v1": "TwinWorthinessCertificate.v1",
}


class SailContractError(ValueError):
    """A SAIL artifact failed schema, identity, or authority validation."""


def load_schema(contract_name: str) -> dict[str, Any]:
    try:
        schema_path = SCHEMA_PATHS[contract_name]
    except KeyError as error:
        raise SailContractError(f"unknown SAIL contract: {contract_name}") from error
    try:
        value = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(value)
    except (OSError, json.JSONDecodeError, SchemaError) as error:
        raise SailContractError(f"invalid SAIL schema {schema_path}: {error}") from error
    return value


def _contract_name(payload: Mapping[str, Any]) -> str:
    version = payload.get("schema_version")
    try:
        return VERSION_TO_CONTRACT[str(version)]
    except KeyError as error:
        raise SailContractError(f"unknown SAIL schema_version: {version!r}") from error


def _semantic_validation(contract_name: str, payload: Mapping[str, Any]) -> None:
    if contract_name == "CalibrationEvidence.v1":
        action = payload["action"]
        if action["application_time_seconds"] and (
            len(action["application_time_seconds"]) != action["shape"][0]
        ):
            raise SailContractError("action application time count does not match shape")
        for channel_name, channel in payload["observations"].items():
            if len(channel["values"]) != len(channel["available"]):
                raise SailContractError(
                    f"observation availability mask changed length: {channel_name}"
                )
            if channel_name in payload["missing_channels"] and any(
                channel["available"]
            ):
                raise SailContractError(
                    f"missing channel contains available values: {channel_name}"
                )
    elif contract_name == "PhysicalMechanism.v1":
        seen: set[str] = set()
        for parameter in payload["parameters"]:
            name = str(parameter["name"])
            if name in seen:
                raise SailContractError(f"duplicate mechanism parameter: {name}")
            seen.add(name)
            if float(parameter["minimum"]) >= float(parameter["maximum"]):
                raise SailContractError(f"invalid parameter bounds: {name}")
    elif contract_name == "Intervention.v1":
        if payload["proof_class"] != "physical_motion" and (
            payload["authority"]["physical_capture"]
            or payload["authority"]["robot_motion"]
        ):
            raise SailContractError("non-physical intervention requests hardware authority")
    elif contract_name == "TwinWorthinessCertificate.v1":
        level = payload["level"]
        authority = payload["authority"]
        level_requirements = {
            "NONE": (),
            "TW-DIAGNOSTIC": ("TW-G0",),
            "TW-REPLAY": ("TW-G0", "TW-G1"),
            "TW-DATA": ("TW-G0", "TW-G1", "TW-G2"),
            "TW-SELECTION": ("TW-G0", "TW-G1", "TW-G2", "TW-G3", "TW-G4"),
            "TW-PHYSICAL-CANARY": (
                "TW-G0",
                "TW-G1",
                "TW-G2",
                "TW-G3",
                "TW-G4",
            ),
        }
        if any(
            payload["gates"][gate]["status"] != "pass"
            for gate in level_requirements[level]
        ):
            raise SailContractError("certificate level exceeds its passing gates")
        if authority["data_generation"] and level not in {
            "TW-DATA",
            "TW-SELECTION",
            "TW-PHYSICAL-CANARY",
        }:
            raise SailContractError("certificate overstates data-generation authority")
        if authority["policy_selection"] and level not in {
            "TW-SELECTION",
            "TW-PHYSICAL-CANARY",
        }:
            raise SailContractError("certificate overstates policy-selection authority")
        if authority["physical_canary"] and level != "TW-PHYSICAL-CANARY":
            raise SailContractError("certificate overstates physical-canary authority")


def validate_contract(
    payload: Mapping[str, Any], *, contract_name: str | None = None
) -> dict[str, Any]:
    """Return a deep copy after Draft 2020-12 and semantic validation."""

    normalized = copy.deepcopy(dict(payload))
    selected_name = contract_name or _contract_name(normalized)
    validator = Draft202012Validator(
        load_schema(selected_name), format_checker=FormatChecker()
    )
    errors = sorted(validator.iter_errors(normalized), key=lambda item: list(item.path))
    if errors:
        error: ValidationError = errors[0]
        location = ".".join(str(part) for part in error.path) or "<root>"
        raise SailContractError(f"{selected_name} invalid at {location}: {error.message}")
    _semantic_validation(selected_name, normalized)
    return normalized


def seal_contract(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Attach a canonical digest and validate the resulting immutable artifact."""

    unsigned = copy.deepcopy(dict(payload))
    unsigned.pop(DIGEST_FIELD, None)
    result = {**unsigned, DIGEST_FIELD: canonical_digest(unsigned)}
    return validate_contract(result)


def verify_contract(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate an artifact and fail closed if any signed field changed."""

    normalized = validate_contract(payload)
    observed = normalized[DIGEST_FIELD]
    unsigned = {key: value for key, value in normalized.items() if key != DIGEST_FIELD}
    expected = canonical_digest(unsigned)
    if observed != expected:
        raise SailContractError(
            f"SAIL canonical digest mismatch: expected {expected}, observed {observed}"
        )
    return normalized


def verify_source_binding(binding: Mapping[str, Any], *, repo_root: Path = REPO_ROOT) -> Path:
    """Resolve and hash-check a source before any fit or certificate is allowed."""

    source_path = Path(str(binding.get("path", "")))
    if source_path.is_absolute():
        resolved = source_path.resolve()
    else:
        resolved = (repo_root / source_path).resolve()
    if not resolved.is_file():
        raise SailContractError(f"source artifact is missing: {source_path}")
    expected = str(binding.get("sha256", ""))
    observed = sha256_file(resolved)
    if observed != expected:
        raise SailContractError(
            f"source artifact digest mismatch: expected {expected}, observed {observed}"
        )
    return resolved


def action_descriptor(
    action_bytes: bytes,
    *,
    shape: Sequence[int],
    dtype: str,
    ordering: str,
) -> dict[str, Any]:
    if not action_bytes:
        raise SailContractError("action bytes are empty")
    if dtype not in {"float32", "float64"}:
        raise SailContractError(f"unsupported action dtype: {dtype}")
    normalized_shape = [int(value) for value in shape]
    if not normalized_shape or any(value <= 0 for value in normalized_shape):
        raise SailContractError("action shape is invalid")
    if not ordering:
        raise SailContractError("action ordering is empty")
    return {
        "shape": normalized_shape,
        "dtype": dtype,
        "ordering": ordering,
        "sha256": hashlib.sha256(action_bytes).hexdigest(),
    }


def assert_action_invariant(
    expected: Mapping[str, Any], observed: Mapping[str, Any]
) -> None:
    fields = ("shape", "dtype", "ordering", "sha256")
    changed = [field for field in fields if expected.get(field) != observed.get(field)]
    if changed:
        raise SailContractError(
            "action invariance failed for: " + ", ".join(changed)
        )


def sealed_access_allowed(*, actor_role: str, evaluator_owned: bool) -> bool:
    return actor_role == "deterministic_evaluator" and evaluator_owned


def assert_parameter_within_bounds(
    mechanism: Mapping[str, Any], values: Mapping[str, float]
) -> None:
    parameters = {str(row["name"]): row for row in mechanism["parameters"]}
    for name, value in values.items():
        if name not in parameters:
            raise SailContractError(f"unknown mechanism parameter: {name}")
        bound = parameters[name]
        if not float(bound["minimum"]) <= float(value) <= float(bound["maximum"]):
            raise SailContractError(f"mechanism parameter is out of bounds: {name}")


def admitted_corrective_row_count(
    *, trajectory_succeeded: bool, suffix_succeeded: bool, suffix_row_count: int
) -> int:
    if suffix_row_count < 0:
        raise SailContractError("suffix row count cannot be negative")
    if not trajectory_succeeded or not suffix_succeeded:
        return 0
    return suffix_row_count


def assert_split_integrity(
    *, training_ids: Sequence[str], hardware_evaluation_ids: Sequence[str]
) -> None:
    overlap = sorted(set(training_ids) & set(hardware_evaluation_ids))
    if overlap:
        raise SailContractError(
            "hardware evaluation trial appears in training input: " + ", ".join(overlap)
        )


def assert_provider_identity_stable(attempts: Sequence[Mapping[str, Any]]) -> None:
    identities = {
        (
            attempt.get("provider"),
            attempt.get("model"),
            attempt.get("model_revision"),
            attempt.get("harness_sha256"),
        )
        for attempt in attempts
    }
    if len(identities) > 1:
        raise SailContractError("provider/model identity changed inside one condition")


def phase_timing_error(
    expected: Sequence[float], observed: Sequence[float]
) -> float:
    """A phase-aware pointwise error that cannot collapse to a shared minimum."""

    if len(expected) != len(observed) or not expected:
        raise SailContractError("phase curves must have equal non-zero length")
    return sum(abs(float(left) - float(right)) for left, right in zip(expected, observed, strict=True)) / len(expected)
