"""Fail-closed loader for the overnight current-workcell calibration packet."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .learning_factory_artifacts import canonical_digest, sha256_file
from .paths import REPO_ROOT
from .sail.importers import load_json_object


SCHEMA_VERSION = "sim2claw.overnight_calibration_publication.v1"
DEFAULT_PUBLICATION_PATH = Path(
    "configs/evaluations/overnight_calibration_publication_v1.json"
)


class OvernightCalibrationPublicationError(ValueError):
    """The publication or one of its hash-bound evidence artifacts is invalid."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise OvernightCalibrationPublicationError(message)


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping), f"{label} must be an object.")
    return value


def _repo_path(repo_root: Path, value: object, *, label: str) -> Path:
    root = repo_root.resolve()
    path = (root / str(value)).resolve()
    _require(path.is_relative_to(root), f"{label} escapes the repository.")
    return path


def load_overnight_calibration_binding(
    *,
    repo_root: Path = REPO_ROOT,
    publication_path: Path = DEFAULT_PUBLICATION_PATH,
) -> dict[str, Any]:
    """Load only the tracked publication identity used to select an episode."""

    path = _repo_path(repo_root, publication_path, label="Publication path")
    publication = load_json_object(path, label="Overnight calibration publication")
    _require(
        publication.get("schema_version") == SCHEMA_VERSION,
        "Unsupported overnight calibration publication.",
    )
    _require(
        publication.get("status") == "frozen_after_single_authorized_comparison",
        "Overnight calibration publication is not frozen.",
    )
    recording_id = str(publication.get("source_recording_id") or "")
    _require(bool(recording_id), "Publication source recording ID is missing.")
    return publication


def _verify_file(path: Path, expected: object, *, label: str) -> None:
    _require(path.is_file(), f"{label} is unavailable.")
    _require(sha256_file(path) == str(expected), f"{label} hash changed.")


def _verify_receipt(
    receipt: Mapping[str, Any],
    *,
    expected_embedded_digest: object,
    label: str,
) -> None:
    embedded = str(receipt.get("receipt_sha256") or "")
    unsigned = {key: value for key, value in receipt.items() if key != "receipt_sha256"}
    _require(
        embedded == str(expected_embedded_digest),
        f"{label} embedded digest changed.",
    )
    _require(canonical_digest(unsigned) == embedded, f"{label} digest is invalid.")


def verify_overnight_calibration_publication(
    *,
    repo_root: Path = REPO_ROOT,
    publication_path: Path = DEFAULT_PUBLICATION_PATH,
) -> dict[str, Any]:
    """Verify and load the immutable diagnostic and comparison artifacts.

    This is byte-integrity and semantic-boundary verification, not a hostile
    code sandbox or a rerun of either evaluator.
    """

    root = repo_root.resolve()
    publication = load_overnight_calibration_binding(
        repo_root=root,
        publication_path=publication_path,
    )
    diagnostic_binding = _mapping(publication.get("diagnostic"), "Diagnostic binding")
    comparison_binding = _mapping(publication.get("comparison"), "Comparison binding")
    required = _mapping(publication.get("required_claims"), "Required claims")
    authority = _mapping(publication.get("authority"), "Publication authority")
    _require(
        authority and all(value is False for value in authority.values()),
        "Publication authority widened.",
    )

    diagnostic_root = _repo_path(
        root, diagnostic_binding.get("output_root"), label="Diagnostic output root"
    )
    comparison_root = _repo_path(
        root, comparison_binding.get("output_root"), label="Comparison output root"
    )
    diagnostic_contract_path = _repo_path(
        root, diagnostic_binding.get("contract_path"), label="Diagnostic contract"
    )
    comparison_contract_path = _repo_path(
        root, comparison_binding.get("contract_path"), label="Comparison contract"
    )
    diagnostic_path = diagnostic_root / str(diagnostic_binding.get("diagnostic_path"))
    diagnostic_receipt_path = diagnostic_root / str(
        diagnostic_binding.get("receipt_path")
    )
    raw_path = comparison_root / str(comparison_binding.get("raw_comparison_path"))
    evaluation_path = comparison_root / str(
        comparison_binding.get("evaluation_path")
    )
    comparison_receipt_path = comparison_root / str(
        comparison_binding.get("receipt_path")
    )
    for path, expected, label in (
        (
            diagnostic_contract_path,
            diagnostic_binding.get("contract_sha256"),
            "Diagnostic contract",
        ),
        (
            comparison_contract_path,
            comparison_binding.get("contract_sha256"),
            "Comparison contract",
        ),
        (
            diagnostic_path,
            diagnostic_binding.get("diagnostic_sha256"),
            "Diagnostic artifact",
        ),
        (
            diagnostic_receipt_path,
            diagnostic_binding.get("receipt_sha256"),
            "Diagnostic receipt",
        ),
        (
            raw_path,
            comparison_binding.get("raw_comparison_sha256"),
            "Raw comparison",
        ),
        (
            evaluation_path,
            comparison_binding.get("evaluation_sha256"),
            "Comparison evaluation",
        ),
        (
            comparison_receipt_path,
            comparison_binding.get("receipt_sha256"),
            "Comparison receipt",
        ),
    ):
        _verify_file(path, expected, label=label)

    traces = _mapping(comparison_binding.get("traces"), "Trace bindings")
    for relative, expected in traces.items():
        trace_path = comparison_root / str(relative)
        _verify_file(trace_path, expected, label=f"Comparison trace {relative}")

    diagnostic = load_json_object(diagnostic_path, label="Overnight diagnostic")
    diagnostic_receipt = load_json_object(
        diagnostic_receipt_path, label="Overnight diagnostic receipt"
    )
    raw = load_json_object(raw_path, label="Overnight raw comparison")
    evaluation = load_json_object(
        evaluation_path, label="Overnight comparison evaluation"
    )
    comparison_receipt = load_json_object(
        comparison_receipt_path, label="Overnight comparison receipt"
    )
    _verify_receipt(
        diagnostic_receipt,
        expected_embedded_digest=diagnostic_binding.get("embedded_receipt_sha256"),
        label="Diagnostic receipt",
    )
    _verify_receipt(
        comparison_receipt,
        expected_embedded_digest=comparison_binding.get("embedded_receipt_sha256"),
        label="Comparison receipt",
    )

    recording_id = str(publication["source_recording_id"])
    _require(
        diagnostic.get("source_recording_id") == recording_id
        and diagnostic_receipt.get("source_recording_id") == recording_id
        and raw.get("source_recording_id") == recording_id
        and comparison_receipt.get("source_recording_id") == recording_id,
        "Publication artifacts do not bind the same source recording.",
    )
    proof_classes = publication.get("proof_classes")
    _require(
        isinstance(proof_classes, list)
        and diagnostic.get("proof_class") in proof_classes
        and diagnostic_receipt.get("proof_class") in proof_classes
        and comparison_receipt.get("proof_class") in proof_classes,
        "Publication proof-class binding changed.",
    )
    _require(
        diagnostic_receipt.get("diagnostic_sha256")
        == diagnostic_binding.get("diagnostic_sha256"),
        "Diagnostic receipt artifact binding changed.",
    )
    _require(
        comparison_receipt.get("raw_comparison_sha256")
        == comparison_binding.get("raw_comparison_sha256")
        and comparison_receipt.get("evaluation_sha256")
        == comparison_binding.get("evaluation_sha256"),
        "Comparison receipt artifact binding changed.",
    )
    exact_action_sha256 = str(comparison_binding.get("exact_action_sha256") or "")
    variants = raw.get("variants")
    _require(
        isinstance(variants, list) and len(variants) == 2,
        "Comparison must contain exactly two variants.",
    )
    _require(
        raw.get("exact_action_sha256") == exact_action_sha256
        and comparison_receipt.get("exact_action_sha256") == exact_action_sha256
        and all(row.get("input_action_sha256") == exact_action_sha256 for row in variants),
        "Comparison action identity changed.",
    )
    _require(
        all(row.get("external_preclip_applied") is False for row in variants),
        "Comparison introduced external preclipping.",
    )
    for row in variants:
        trace_name = str(row.get("raw_trace_path") or "")
        _require(
            traces.get(trace_name) == row.get("raw_trace_sha256"),
            f"Comparison trace receipt changed: {trace_name}.",
        )
    segmentation = _mapping(diagnostic.get("segmentation"), "Diagnostic segmentation")
    _require(
        segmentation.get("procedure_count_matches")
        is required.get("procedure_count_matches")
        and segmentation.get("observed_excursion_count")
        == required.get("observed_excursion_count")
        and segmentation.get("owner_intended_excursion_count")
        == required.get("owner_intended_excursion_count"),
        "Diagnostic procedure accounting changed.",
    )
    _require(
        evaluation.get("action_tensor_byte_identical")
        is required.get("action_tensor_byte_identical")
        and evaluation.get("simulator_parameter_promoted")
        is required.get("simulator_parameter_promoted")
        and evaluation.get("task_score_changed")
        is required.get("task_score_changed")
        and evaluation.get("verdict") == required.get("verdict"),
        "Comparison claim boundary changed.",
    )
    evaluation_gates = _mapping(evaluation.get("gates"), "Comparison gates")
    _require(
        evaluation_gates.get("strict_task_consequence")
        is required.get("strict_task_consequence_available"),
        "Strict task-consequence availability changed.",
    )
    _require(
        comparison_receipt.get("simulator_parameter_promoted")
        is required.get("simulator_parameter_promoted")
        and comparison_receipt.get("task_score_changed")
        is required.get("task_score_changed")
        and diagnostic_receipt.get("simulator_parameter_promoted")
        is required.get("simulator_parameter_promoted")
        and diagnostic_receipt.get("task_score_changed")
        is required.get("task_score_changed"),
        "Receipt promotion or task-score boundary changed.",
    )
    _require(
        raw.get("simulator_replays_used")
        == comparison_binding.get("simulator_replays_used")
        and raw.get("adaptive_retries") == comparison_binding.get("adaptive_retries")
        and comparison_receipt.get("simulator_replays_used")
        == comparison_binding.get("simulator_replays_used"),
        "Comparison budget accounting changed.",
    )
    _require(
        diagnostic_receipt.get("simulator_replays_used")
        == diagnostic_binding.get("simulator_replays_used"),
        "Diagnostic replay accounting changed.",
    )
    for artifact in (diagnostic, diagnostic_receipt, raw, comparison_receipt):
        artifact_authority = _mapping(
            artifact.get("authority"), "Evidence artifact authority"
        )
        _require(
            artifact_authority
            and all(value is False for value in artifact_authority.values()),
            "Evidence artifact widened authority.",
        )
    return {
        "publication": publication,
        "publication_sha256": sha256_file(
            _repo_path(root, publication_path, label="Publication path")
        ),
        "diagnostic": diagnostic,
        "diagnostic_receipt": diagnostic_receipt,
        "raw_comparison": raw,
        "evaluation": evaluation,
        "comparison_receipt": comparison_receipt,
    }


__all__ = [
    "DEFAULT_PUBLICATION_PATH",
    "OvernightCalibrationPublicationError",
    "SCHEMA_VERSION",
    "load_overnight_calibration_binding",
    "verify_overnight_calibration_publication",
]
