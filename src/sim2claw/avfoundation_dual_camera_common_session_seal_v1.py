"""Seal the common-session observation with one Codable-null correction."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import sim2claw.avfoundation_dual_camera_common_session_v1 as original
from sim2claw.avfoundation_format_inventory import (
    AVFoundationFormatInventoryError,
    _canonical_digest,
    _load_json,
    _sha256_file,
    _write_json,
)


SEALER_SCHEMA = (
    "sim2claw.avfoundation_dual_camera_common_session_sealed_receipt.v1"
)
OBSERVED_EVALUATOR_SHA256 = (
    "380510825d3871e43408a285faca028ff2fcb6b8f72212c4c734786f310e52f5"
)
OBSERVED_SWIFT_SHA256 = (
    "8ee7ddc0a298c2ffc960961e58c8d86708f92a3d9015ce2be148a694c39e8e51"
)
CODABLE_COMPLETED_KEYS = original.RAW_KEYS - {"failure_reason"}
CODABLE_OUTPUT_EVENT_KEYS = original.EVENT_KEYS - {"drop_reason"}
SOLE_RAW_SHA256 = (
    "f78c363d3e45f4f6a191d8156f047e338d4ee786c9cb47fe10ab58af3b6a44d5"
)
SOLE_ATTEMPT_SHA256 = (
    "e5c9e02e207f38c2c05b67d000928aeb41c51edf34fb3f3a4cf27a669b6968d5"
)


def seal_observation(
    *,
    contract_path: Path,
    observation_root: Path,
    output_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if output_root.exists():
        raise AVFoundationFormatInventoryError(
            "Common-session sealed output already exists."
        )
    raw_path = observation_root / "raw/observation.json"
    attempt_path = observation_root / "attempt.json"
    if (
        _sha256_file(raw_path) != SOLE_RAW_SHA256
        or _sha256_file(attempt_path) != SOLE_ATTEMPT_SHA256
    ):
        raise AVFoundationFormatInventoryError(
            "Observation is not the exact sole authorized attempt."
        )
    raw = _load_json(raw_path, label="common-session raw observation")
    if (
        set(raw) != CODABLE_COMPLETED_KEYS
        or raw.get("status") != "completed"
        or "failure_reason" in raw
    ):
        raise AVFoundationFormatInventoryError(
            "Raw observation is not the exact completed Codable-nil shape."
        )
    events = raw.get("events")
    if (
        not isinstance(events, list)
        or any(
            not isinstance(event, dict)
            or set(event) != CODABLE_OUTPUT_EVENT_KEYS
            or event.get("kind") != "output"
            or "drop_reason" in event
            for event in events
        )
    ):
        raise AVFoundationFormatInventoryError(
            "Callback events are not the exact output-only Codable-nil shape."
        )
    attempt = _load_json(
        attempt_path,
        label="common-session attempt",
    )
    runtime = attempt.get("runtime_identity")
    if (
        not isinstance(runtime, dict)
        or runtime.get("evaluator_sha256") != OBSERVED_EVALUATOR_SHA256
        or runtime.get("source_sha256") != OBSERVED_SWIFT_SHA256
    ):
        raise AVFoundationFormatInventoryError(
            "Observed source/evaluator identity changed."
        )

    saved_keys = original.RAW_KEYS
    saved_event_keys = original.EVENT_KEYS
    with tempfile.TemporaryDirectory(
        prefix="sim2claw-common-session-seal-"
    ) as temporary:
        temporary_output = Path(temporary) / "evaluated"
        original.RAW_KEYS = CODABLE_COMPLETED_KEYS
        original.EVENT_KEYS = CODABLE_OUTPUT_EVENT_KEYS
        try:
            evaluation, _ = original.evaluate(
                contract_path=contract_path,
                observation_root=observation_root,
                output_root=temporary_output,
            )
        finally:
            original.RAW_KEYS = saved_keys
            original.EVENT_KEYS = saved_event_keys

    output_root.mkdir(parents=True)
    _write_json(output_root / "evaluation.json", evaluation)
    receipt_base = {
        "schema_version": SEALER_SCHEMA,
        "contract_sha256": original.CONTRACT_SHA256,
        "observed_source_sha256": OBSERVED_SWIFT_SHA256,
        "observed_evaluator_sha256": OBSERVED_EVALUATOR_SHA256,
        "sealing_evaluator_path": str(Path(__file__).resolve()),
        "sealing_evaluator_sha256": _sha256_file(Path(__file__).resolve()),
        "attempt_manifest_sha256": _sha256_file(
            observation_root / "attempt.json"
        ),
        "raw_observation_sha256": _sha256_file(raw_path),
        "evaluation_digest": _canonical_digest(evaluation),
        "normalization": {
            "field": "failure_reason",
            "observed_representation": "absent",
            "typed_meaning": "null",
            "output_event_field": "drop_reason",
            "output_event_observed_representation": "absent",
            "output_event_typed_meaning": "null",
            "scientific_thresholds_changed": False,
            "callback_or_stage_values_changed": False,
        },
        "proof_class": original.PROOF_CLASS,
        "verdict": evaluation["verdict"],
        "budget": attempt["budget"],
        "authority": attempt["authority"],
    }
    receipt = {
        **receipt_base,
        "receipt_digest": _canonical_digest(receipt_base),
    }
    _write_json(output_root / "receipt.json", receipt)
    return evaluation, receipt
