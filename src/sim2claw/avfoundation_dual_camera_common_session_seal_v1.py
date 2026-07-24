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


def seal_observation(
    *,
    contract_path: Path,
    observation_root: Path,
    output_root: Path,
    sealer_path: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if output_root.exists():
        raise AVFoundationFormatInventoryError(
            "Common-session sealed output already exists."
        )
    raw_path = observation_root / "raw/observation.json"
    raw = _load_json(raw_path, label="common-session raw observation")
    if (
        set(raw) != CODABLE_COMPLETED_KEYS
        or raw.get("status") != "completed"
        or "failure_reason" in raw
    ):
        raise AVFoundationFormatInventoryError(
            "Raw observation is not the exact completed Codable-nil shape."
        )
    attempt = _load_json(
        observation_root / "attempt.json",
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
    with tempfile.TemporaryDirectory(
        prefix="sim2claw-common-session-seal-"
    ) as temporary:
        temporary_output = Path(temporary) / "evaluated"
        original.RAW_KEYS = CODABLE_COMPLETED_KEYS
        try:
            evaluation, _ = original.evaluate(
                contract_path=contract_path,
                observation_root=observation_root,
                output_root=temporary_output,
            )
        finally:
            original.RAW_KEYS = saved_keys

    output_root.mkdir(parents=True)
    _write_json(output_root / "evaluation.json", evaluation)
    receipt_base = {
        "schema_version": SEALER_SCHEMA,
        "contract_sha256": original.CONTRACT_SHA256,
        "observed_source_sha256": OBSERVED_SWIFT_SHA256,
        "observed_evaluator_sha256": OBSERVED_EVALUATOR_SHA256,
        "sealing_evaluator_sha256": _sha256_file(sealer_path),
        "attempt_manifest_sha256": _sha256_file(
            observation_root / "attempt.json"
        ),
        "raw_observation_sha256": _sha256_file(raw_path),
        "evaluation_digest": _canonical_digest(evaluation),
        "normalization": {
            "field": "failure_reason",
            "observed_representation": "absent",
            "typed_meaning": "null",
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
