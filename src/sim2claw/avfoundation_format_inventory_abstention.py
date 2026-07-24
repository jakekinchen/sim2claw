"""Seal the one failed AVFoundation format-inventory observation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sim2claw.avfoundation_format_inventory import (
    AVFoundationFormatInventoryError,
    EVALUATION_SCHEMA,
    RECEIPT_SCHEMA,
    _canonical_digest,
    _sha256_file,
    _write_json,
    load_format_inventory_contract,
    validate_inventory_source_is_observer_only,
)


EXECUTION_COMMIT = "c868038cdd4ee0d56d524155f2678f743b7bcfc8"
EXECUTION_SOURCE_SHA256 = (
    "289c3fc2ca3f66ff9da18d783c70936bbb8c4c3d823c5e522ec6c26ff8e09750"
)
EXECUTION_EVALUATOR_SHA256 = (
    "3ec4e50acf2ae052dab70616efe2b2ed561a4763d3460cbddb3298e0cc7d54aa"
)
FAILURE_SIGNATURE = "Invalid type in JSON write (__SwiftValue)"


def seal_format_inventory_prerequisite_abstention(
    *,
    contract_path: Path,
    observation_root: Path,
    output_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Verify the failed attempt artifacts without inventing inventory rows."""

    contract = load_format_inventory_contract(contract_path)
    if output_root.exists():
        raise AVFoundationFormatInventoryError(
            "Evaluation output already exists; replay is forbidden."
        )
    source_path = Path(contract["runtime_identity"]["inventory_source_path"])
    evaluator_path = Path(contract["runtime_identity"]["evaluator_path"])
    compiler_path = Path(contract["runtime_identity"]["compiler_path"])
    binary_path = observation_root / "runtime/avfoundation-format-inventory"
    stderr_path = observation_root / "raw/inventory.stderr.log"
    raw_path = observation_root / "raw/inventory.json"
    manifest_path = observation_root / "observation.json"
    if raw_path.exists() or manifest_path.exists():
        raise AVFoundationFormatInventoryError(
            "Abstention sealer cannot discard a raw inventory or manifest."
        )
    if (
        not source_path.is_file()
        or _sha256_file(source_path) != EXECUTION_SOURCE_SHA256
        or not evaluator_path.is_file()
        or _sha256_file(evaluator_path) != EXECUTION_EVALUATOR_SHA256
        or not compiler_path.is_file()
        or not binary_path.is_file()
        or not stderr_path.is_file()
    ):
        raise AVFoundationFormatInventoryError(
            "Execution source, evaluator, compiler, binary, or stderr is missing "
            "or changed."
        )
    validate_inventory_source_is_observer_only(source_path)
    try:
        stderr_text = stderr_path.read_text(encoding="utf-8")
    except OSError as error:
        raise AVFoundationFormatInventoryError(
            f"Could not read inventory stderr: {error}"
        ) from error
    if FAILURE_SIGNATURE not in stderr_text:
        raise AVFoundationFormatInventoryError(
            "Failed observation does not contain the frozen JSON-bridge signature."
        )

    budget = {
        "inventory_observations_used": 1,
        "capture_sessions_used": 0,
        "source_samples_used": 0,
        "d405_lifecycle_operations_used": 0,
        "robot_motion_trials_used": 0,
        "provider_calls_used": 0,
    }
    evaluation = {
        "schema_version": EVALUATION_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": _sha256_file(contract_path),
        "execution_commit": EXECUTION_COMMIT,
        "execution_source_sha256": EXECUTION_SOURCE_SHA256,
        "execution_evaluator_sha256": EXECUTION_EVALUATOR_SHA256,
        "compiler_sha256": _sha256_file(compiler_path),
        "binary_sha256": _sha256_file(binary_path),
        "stderr_sha256": _sha256_file(stderr_path),
        "proof_class": "camera_device_format_inventory",
        "verdict": "prerequisite_abstention",
        "failure_stage": "observer_json_serialization",
        "failure_signature": FAILURE_SIGNATURE,
        "inventory_observation_attempt_count": 1,
        "raw_inventory_available": False,
        "usable_inventory_observation_count": 0,
        "device_match_count": None,
        "format_count": None,
        "frame_rate_range_count": None,
        "exact_dimension_candidate_count": 0,
        "eligible_candidate_count": 0,
        "eligible_candidates": [],
        "selected_candidate": None,
        "missing_prerequisite": (
            "A separately authorized observer version must convert every "
            "AVFoundation value to a JSONSerialization-compatible primitive "
            "before another inventory observation."
        ),
        "selection_does_not_authorize_stream_execution": True,
        "budget": budget,
        "claim_limits": {
            "native_format_surface_observed": False,
            "capture_session_started": False,
            "source_delivery_measured": False,
            "container_timing_measured": False,
            "physical_exposure_continuity": False,
            "cross_camera_exposure_synchronization": False,
            "metric_depth": False,
            "simulator_calibration": False,
            "task_success": False,
            "future_campaign_authorized": False,
        },
    }
    output_root.mkdir(parents=True)
    _write_json(output_root / "evaluation.json", evaluation)
    receipt_without_digest = {
        "schema_version": RECEIPT_SCHEMA,
        "contract_sha256": _sha256_file(contract_path),
        "execution_commit": EXECUTION_COMMIT,
        "source_sha256": EXECUTION_SOURCE_SHA256,
        "evaluator_sha256": EXECUTION_EVALUATOR_SHA256,
        "abstention_sealer_sha256": _sha256_file(Path(__file__)),
        "compiler_sha256": _sha256_file(compiler_path),
        "binary_sha256": _sha256_file(binary_path),
        "stderr_sha256": _sha256_file(stderr_path),
        "evaluation_digest": _canonical_digest(evaluation),
        "proof_class": "camera_device_format_inventory",
        "verdict": "prerequisite_abstention",
        "budget": budget,
        "authority": contract["authority"],
    }
    receipt = {
        **receipt_without_digest,
        "receipt_digest": _canonical_digest(receipt_without_digest),
    }
    _write_json(output_root / "receipt.json", receipt)
    return evaluation, receipt
