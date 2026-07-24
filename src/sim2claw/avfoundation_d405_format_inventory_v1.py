"""Evaluator-owned D405 AVFoundation format inventory v1."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from sim2claw.avfoundation_format_inventory import (
    AVFoundationFormatInventoryError,
    _canonical_digest,
    _load_json,
    _sha256_file,
    _write_json,
)
from sim2claw.avfoundation_format_inventory_v2 import (
    _rank_candidates,
    _validate_v2_observed_formats,
    validate_v2_source_is_primitive_observer,
)


CONTRACT_SCHEMA = "sim2claw.avfoundation_d405_format_inventory_contract.v1"
OBSERVATION_SCHEMA = "sim2claw.avfoundation_format_inventory_observation.v2"
PRELAUNCH_SCHEMA = "sim2claw.avfoundation_d405_format_inventory_prelaunch.v1"
ATTEMPT_SCHEMA = "sim2claw.avfoundation_d405_format_inventory_attempt.v1"
EVALUATION_SCHEMA = "sim2claw.avfoundation_d405_format_inventory_evaluation.v1"
RECEIPT_SCHEMA = "sim2claw.avfoundation_d405_format_inventory_receipt.v1"
PROOF_CLASS = "d405_camera_device_format_inventory"
BINARY_RELATIVE_PATH = "runtime/avfoundation-d405-format-inventory-v1"
CANONICAL_OUTPUT_ROOT = Path(
    "outputs/avfoundation-d405-format-inventory-v1/observed"
)

EXPECTED_DEVICE = {
    "media_type": "video",
    "exact_localized_name": "Intel(R) RealSense(TM) Depth Camera 405  Depth",
    "exact_unique_id": "0x20000080860b5b",
    "exact_model_id": "UVC Camera VendorID_32902 ProductID_2907",
    "exact_match_count_required": 1,
}
EXPECTED_SELECTION_RULE = {
    "target_width": 424,
    "target_height": 240,
    "target_fps": 5.0,
    "exact_dimensions_required": True,
    "maximum_fractional_fps_deviation": 0.01,
    "nearest_supported_fps": "clamp_target_to_each_closed_min_max_range",
    "media_subtype_preference": ["2vuy", "yuvs", "420v", "BGRA"],
    "rank_order": [
        "fps_deviation_ascending",
        "media_subtype_preference_index_ascending",
        "media_subtype_fourcc_ascending",
        "format_index_ascending",
        "frame_rate_range_index_ascending",
    ],
    "verdicts": [
        "supported_d405_common_session_candidate",
        "no_supported_d405_common_session_candidate",
        "prerequisite_abstention",
    ],
    "selection_does_not_authorize_stream_execution": True,
}
EXPECTED_BUDGET = {
    "inventory_observations_maximum": 1,
    "capture_sessions_maximum": 0,
    "source_samples_maximum": 0,
    "c922_lifecycle_operations_maximum": 0,
    "d405_lifecycle_operations_maximum": 0,
    "robot_motion_trials_maximum": 0,
    "simulator_replays_maximum": 0,
    "provider_calls_maximum": 0,
}
USED_BUDGET = {
    "inventory_observations_used": 1,
    "capture_sessions_used": 0,
    "source_samples_used": 0,
    "c922_lifecycle_operations_used": 0,
    "d405_lifecycle_operations_used": 0,
    "robot_motion_trials_used": 0,
    "simulator_replays_used": 0,
    "provider_calls_used": 0,
}
EXPECTED_OBSERVER = {
    "source_path": "tools/macos/AVFoundationFormatInventoryV2.swift",
    "role": "device_and_format_enumeration_only",
    "capture_session_created": False,
    "capture_session_started": False,
    "source_samples": 0,
    "serialization": "Swift Codable structs through Foundation.JSONEncoder",
}


def load_d405_format_inventory_contract(path: Path) -> dict[str, Any]:
    contract = _load_json(path, label="D405 format-inventory contract")
    if contract.get("schema_version") != CONTRACT_SCHEMA:
        raise AVFoundationFormatInventoryError("D405 contract schema changed.")
    if contract.get("status") != "preregistered_before_implementation":
        raise AVFoundationFormatInventoryError("D405 contract status changed.")
    if contract.get("device") != EXPECTED_DEVICE:
        raise AVFoundationFormatInventoryError("D405 device contract changed.")
    if contract.get("observer") != EXPECTED_OBSERVER:
        raise AVFoundationFormatInventoryError("D405 observer contract changed.")
    if contract.get("selection_rule") != EXPECTED_SELECTION_RULE:
        raise AVFoundationFormatInventoryError("D405 selection rule changed.")
    if contract.get("operation_budget") != EXPECTED_BUDGET:
        raise AVFoundationFormatInventoryError("D405 operation budget changed.")
    authority = contract.get("authority")
    if not isinstance(authority, dict):
        raise AVFoundationFormatInventoryError("D405 authority is missing.")
    if authority.get("device_and_format_enumeration") is not True or any(
        value is not False
        for key, value in authority.items()
        if key != "device_and_format_enumeration"
    ):
        raise AVFoundationFormatInventoryError("D405 authority widened.")
    return contract


def compile_d405_format_inventory(
    *,
    contract_path: Path,
    source_path: Path,
    evaluator_path: Path,
    binary_path: Path,
) -> dict[str, Any]:
    contract = load_d405_format_inventory_contract(contract_path)
    validate_v2_source_is_primitive_observer(source_path)
    runtime_contract = contract["runtime_identity"]
    if Path(runtime_contract["observer_source_path"]) != source_path:
        raise AVFoundationFormatInventoryError("D405 source path changed.")
    if Path(runtime_contract["evaluator_path"]) != evaluator_path:
        raise AVFoundationFormatInventoryError("D405 evaluator path changed.")
    compiler = Path(runtime_contract["compiler_path"])
    if not compiler.is_file():
        raise AVFoundationFormatInventoryError("D405 compiler is missing.")
    version = subprocess.run(
        [str(compiler), "--version"],
        check=False,
        capture_output=True,
        text=True,
    )
    if version.returncode != 0 or not version.stdout.startswith(
        runtime_contract["swift_version_prefix"]
    ):
        raise AVFoundationFormatInventoryError("D405 compiler identity changed.")
    binary_path.parent.mkdir(parents=True, exist_ok=True)
    compiled = subprocess.run(
        [str(compiler), str(source_path), "-o", str(binary_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if compiled.returncode != 0:
        raise AVFoundationFormatInventoryError(
            f"D405 Swift compilation failed: {compiled.stderr.strip()}"
        )
    return {
        "contract_sha256": _sha256_file(contract_path),
        "source_sha256": _sha256_file(source_path),
        "evaluator_sha256": _sha256_file(evaluator_path),
        "compiler_path": str(compiler),
        "compiler_sha256": _sha256_file(compiler),
        "swift_version": version.stdout.strip(),
        "binary_path": BINARY_RELATIVE_PATH,
        "binary_sha256": _sha256_file(binary_path),
    }


def run_d405_format_inventory_observation(
    *,
    contract_path: Path,
    source_path: Path,
    evaluator_path: Path,
    output_root: Path,
) -> dict[str, Any]:
    contract = load_d405_format_inventory_contract(contract_path)
    if output_root.resolve() != CANONICAL_OUTPUT_ROOT.resolve():
        raise AVFoundationFormatInventoryError(
            "D405 observation root is not the authorized canonical root."
        )
    if output_root.exists():
        raise AVFoundationFormatInventoryError(
            "D405 observation output already exists; replay is forbidden."
        )
    binary_path = output_root / BINARY_RELATIVE_PATH
    runtime = compile_d405_format_inventory(
        contract_path=contract_path,
        source_path=source_path,
        evaluator_path=evaluator_path,
        binary_path=binary_path,
    )
    raw_path = output_root / "raw/inventory.json"
    stderr_path = output_root / "raw/inventory.stderr.log"
    prelaunch = {
        "schema_version": PRELAUNCH_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": runtime["contract_sha256"],
        "proof_class": PROOF_CLASS,
        "status": "prepared_before_observer_launch",
        "runtime_identity": runtime,
        "raw_inventory_path": "raw/inventory.json",
        "stderr_path": "raw/inventory.stderr.log",
        "budget": USED_BUDGET,
        "authority": contract["authority"],
    }
    prelaunch_path = output_root / "attempt-prelaunch.json"
    _write_json(prelaunch_path, prelaunch)
    completed = subprocess.run(
        [
            str(binary_path),
            "--camera-name",
            contract["device"]["exact_localized_name"],
            "--contract-sha256",
            runtime["contract_sha256"],
            "--output",
            str(raw_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.write_text(completed.stderr, encoding="utf-8")
    attempt = {
        "schema_version": ATTEMPT_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": runtime["contract_sha256"],
        "proof_class": PROOF_CLASS,
        "status": (
            "observer_completed_with_raw"
            if raw_path.is_file()
            else "observer_failed_without_raw"
        ),
        "prelaunch_manifest_path": "attempt-prelaunch.json",
        "prelaunch_manifest_sha256": _sha256_file(prelaunch_path),
        "runtime_identity": runtime,
        "return_code": completed.returncode,
        "raw_inventory_path": "raw/inventory.json",
        "raw_inventory_sha256": (
            _sha256_file(raw_path) if raw_path.is_file() else None
        ),
        "stderr_path": "raw/inventory.stderr.log",
        "stderr_sha256": _sha256_file(stderr_path),
        "budget": USED_BUDGET,
        "authority": contract["authority"],
    }
    _write_json(output_root / "attempt.json", attempt)
    return attempt


def _verify_runtime(
    *,
    contract: dict[str, Any],
    contract_sha256: str,
    observation_root: Path,
    runtime: dict[str, Any],
) -> None:
    source_path = Path(contract["runtime_identity"]["observer_source_path"])
    evaluator_path = Path(contract["runtime_identity"]["evaluator_path"])
    compiler_path = Path(contract["runtime_identity"]["compiler_path"])
    binary_relative = runtime.get("binary_path")
    if binary_relative != BINARY_RELATIVE_PATH:
        raise AVFoundationFormatInventoryError("D405 binary path changed.")
    binary_path = observation_root / BINARY_RELATIVE_PATH
    if (
        runtime.get("contract_sha256") != contract_sha256
        or not source_path.is_file()
        or _sha256_file(source_path) != runtime.get("source_sha256")
        or not evaluator_path.is_file()
        or _sha256_file(evaluator_path) != runtime.get("evaluator_sha256")
        or runtime.get("compiler_path") != str(compiler_path)
        or not compiler_path.is_file()
        or _sha256_file(compiler_path) != runtime.get("compiler_sha256")
        or not binary_path.is_file()
        or _sha256_file(binary_path) != runtime.get("binary_sha256")
    ):
        raise AVFoundationFormatInventoryError("D405 runtime identity changed.")
    validate_v2_source_is_primitive_observer(source_path)


def evaluate_d405_format_inventory(
    *,
    contract_path: Path,
    observation_root: Path,
    output_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    contract = load_d405_format_inventory_contract(contract_path)
    if output_root.exists():
        raise AVFoundationFormatInventoryError(
            "D405 evaluation output already exists; replay is forbidden."
        )
    contract_sha256 = _sha256_file(contract_path)
    prelaunch_path = observation_root / "attempt-prelaunch.json"
    attempt_path = observation_root / "attempt.json"
    prelaunch = _load_json(prelaunch_path, label="D405 prelaunch manifest")
    attempt = _load_json(attempt_path, label="D405 attempt manifest")
    if prelaunch.get("schema_version") != PRELAUNCH_SCHEMA:
        raise AVFoundationFormatInventoryError("D405 prelaunch schema changed.")
    if attempt.get("schema_version") != ATTEMPT_SCHEMA:
        raise AVFoundationFormatInventoryError("D405 attempt schema changed.")
    if (
        prelaunch.get("status") != "prepared_before_observer_launch"
        or prelaunch.get("raw_inventory_path") != "raw/inventory.json"
        or prelaunch.get("stderr_path") != "raw/inventory.stderr.log"
    ):
        raise AVFoundationFormatInventoryError(
            "D405 prelaunch state or paths changed."
        )
    for label, payload in (("prelaunch", prelaunch), ("attempt", attempt)):
        if (
            payload.get("contract_id") != contract["contract_id"]
            or payload.get("contract_sha256") != contract_sha256
            or payload.get("proof_class") != PROOF_CLASS
            or payload.get("budget") != USED_BUDGET
            or payload.get("authority") != contract["authority"]
        ):
            raise AVFoundationFormatInventoryError(
                f"D405 {label} identity, budget, or authority changed."
            )
    if (
        attempt.get("prelaunch_manifest_path") != "attempt-prelaunch.json"
        or attempt.get("prelaunch_manifest_sha256") != _sha256_file(prelaunch_path)
        or attempt.get("runtime_identity") != prelaunch.get("runtime_identity")
    ):
        raise AVFoundationFormatInventoryError(
            "D405 prelaunch binding changed."
        )
    runtime = attempt.get("runtime_identity")
    if not isinstance(runtime, dict):
        raise AVFoundationFormatInventoryError("D405 runtime identity is missing.")
    _verify_runtime(
        contract=contract,
        contract_sha256=contract_sha256,
        observation_root=observation_root,
        runtime=runtime,
    )
    stderr_path = observation_root / "raw/inventory.stderr.log"
    if (
        attempt.get("stderr_path") != "raw/inventory.stderr.log"
        or not stderr_path.is_file()
        or _sha256_file(stderr_path) != attempt.get("stderr_sha256")
    ):
        raise AVFoundationFormatInventoryError("D405 stderr identity changed.")
    raw_path = observation_root / "raw/inventory.json"
    raw_available = raw_path.is_file()
    return_code = attempt.get("return_code")
    if isinstance(return_code, bool) or not isinstance(return_code, int):
        raise AVFoundationFormatInventoryError(
            "D405 observer return code is not an integer."
        )
    expected_attempt_status = (
        "observer_completed_with_raw"
        if raw_available
        else "observer_failed_without_raw"
    )
    if attempt.get("status") != expected_attempt_status:
        raise AVFoundationFormatInventoryError(
            "D405 attempt status contradicts raw availability."
        )
    if raw_available != isinstance(attempt.get("raw_inventory_sha256"), str):
        raise AVFoundationFormatInventoryError("D405 raw availability changed.")
    if raw_available and (
        attempt.get("raw_inventory_path") != "raw/inventory.json"
        or _sha256_file(raw_path) != attempt.get("raw_inventory_sha256")
    ):
        raise AVFoundationFormatInventoryError("D405 raw identity changed.")

    observation: dict[str, Any] | None = None
    formats: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    eligible: list[dict[str, Any]] = []
    selected: dict[str, Any] | None = None
    if raw_available:
        observation = _load_json(raw_path, label="D405 raw inventory")
        if observation.get("schema_version") != OBSERVATION_SCHEMA:
            raise AVFoundationFormatInventoryError(
                "D405 observation schema changed."
            )
        if observation.get("contract_sha256") != contract_sha256:
            raise AVFoundationFormatInventoryError(
                "D405 observation contract changed."
            )
        if observation.get("observer_role") != "device_format_enumeration_only":
            raise AVFoundationFormatInventoryError("D405 observer role changed.")
        if (
            observation.get("capture_session_created") is not False
            or observation.get("capture_session_started") is not False
            or observation.get("source_sample_count") != 0
        ):
            raise AVFoundationFormatInventoryError(
                "D405 observer widened into capture behavior."
            )
        if (
            observation.get("camera_name_requested")
            != contract["device"]["exact_localized_name"]
        ):
            raise AVFoundationFormatInventoryError(
                "D405 requested camera identity changed."
            )
        detected = observation.get("detected_device_names")
        if (
            not isinstance(detected, list)
            or any(not isinstance(name, str) for name in detected)
            or detected != sorted(detected)
        ):
            raise AVFoundationFormatInventoryError(
                "D405 detected camera inventory is malformed."
            )
        match_count = observation.get("device_match_count")
        if (
            isinstance(match_count, bool)
            or not isinstance(match_count, int)
            or match_count < 0
            or detected.count(contract["device"]["exact_localized_name"])
            != match_count
        ):
            raise AVFoundationFormatInventoryError(
                "D405 device match count contradicts detected inventory."
            )

    prerequisite_available = (
        raw_available
        and return_code == 0
        and observation is not None
        and observation.get("status") == "observed"
        and observation.get("device_match_count") == 1
    )
    if prerequisite_available and observation is not None:
        if (
            observation.get("device_localized_name")
            != contract["device"]["exact_localized_name"]
            or observation.get("device_unique_id")
            != contract["device"]["exact_unique_id"]
            or observation.get("device_model_id")
            != contract["device"]["exact_model_id"]
        ):
            raise AVFoundationFormatInventoryError(
                "D405 observed device identity changed."
            )
        formats = _validate_v2_observed_formats(observation)
        candidates, eligible = _rank_candidates(
            formats,
            contract["selection_rule"],
        )
        selected = eligible[0] if eligible else None
        verdict = (
            "supported_d405_common_session_candidate"
            if selected is not None
            else "no_supported_d405_common_session_candidate"
        )
    else:
        if return_code == 0:
            raise AVFoundationFormatInventoryError(
                "D405 successful attempt has inconsistent raw identity."
            )
        if observation is not None:
            failure_reason = observation.get("failure_reason")
            authorization = observation.get("authorization_status_raw_value")
            match_count = observation.get("device_match_count")
            if (
                observation.get("status") != "prerequisite_unavailable"
                or failure_reason
                not in {
                    "camera_authorization_not_granted",
                    "exact_device_match_count_invalid",
                }
                or isinstance(authorization, bool)
                or not isinstance(authorization, int)
                or isinstance(match_count, bool)
                or not isinstance(match_count, int)
                or match_count < 0
                or observation.get("device_localized_name") is not None
                or observation.get("device_unique_id") is not None
                or observation.get("device_model_id") is not None
                or observation.get("formats") != []
            ):
                raise AVFoundationFormatInventoryError(
                    "D405 prerequisite-unavailable payload is malformed."
                )
            if (
                failure_reason == "camera_authorization_not_granted"
                and authorization == 3
            ):
                raise AVFoundationFormatInventoryError(
                    "D405 authorization abstention contradicts raw status."
                )
            if (
                failure_reason == "exact_device_match_count_invalid"
                and (authorization != 3 or match_count == 1)
            ):
                raise AVFoundationFormatInventoryError(
                    "D405 match-count abstention contradicts raw status."
                )
        verdict = "prerequisite_abstention"

    evaluation = {
        "schema_version": EVALUATION_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": contract_sha256,
        "prelaunch_manifest_sha256": _sha256_file(prelaunch_path),
        "attempt_manifest_sha256": _sha256_file(attempt_path),
        "raw_inventory_sha256": (
            _sha256_file(raw_path) if raw_available else None
        ),
        "proof_class": PROOF_CLASS,
        "verdict": verdict,
        "observer_return_code": return_code,
        "raw_inventory_available": raw_available,
        "device_match_count": (
            observation.get("device_match_count") if observation else None
        ),
        "device_localized_name": (
            observation.get("device_localized_name") if observation else None
        ),
        "device_unique_id": (
            observation.get("device_unique_id") if observation else None
        ),
        "device_model_id": (
            observation.get("device_model_id") if observation else None
        ),
        "format_count": len(formats) if prerequisite_available else None,
        "frame_rate_range_count": (
            sum(len(row["frame_rate_ranges"]) for row in formats)
            if prerequisite_available
            else None
        ),
        "exact_dimension_candidate_count": len(candidates),
        "eligible_candidate_count": len(eligible),
        "eligible_candidates": eligible,
        "selected_candidate": selected,
        "selection_does_not_authorize_stream_execution": True,
        "budget": USED_BUDGET,
        "claim_limits": contract["claim_limits"],
    }
    output_root.mkdir(parents=True)
    _write_json(output_root / "evaluation.json", evaluation)
    receipt_without_digest = {
        "schema_version": RECEIPT_SCHEMA,
        "contract_sha256": contract_sha256,
        "source_sha256": runtime["source_sha256"],
        "evaluator_sha256": runtime["evaluator_sha256"],
        "compiler_sha256": runtime["compiler_sha256"],
        "binary_sha256": runtime["binary_sha256"],
        "prelaunch_manifest_sha256": _sha256_file(prelaunch_path),
        "attempt_manifest_sha256": _sha256_file(attempt_path),
        "raw_inventory_sha256": (
            _sha256_file(raw_path) if raw_available else None
        ),
        "stderr_sha256": _sha256_file(stderr_path),
        "evaluation_digest": _canonical_digest(evaluation),
        "proof_class": PROOF_CLASS,
        "verdict": verdict,
        "budget": USED_BUDGET,
        "authority": contract["authority"],
    }
    receipt = {
        **receipt_without_digest,
        "receipt_digest": _canonical_digest(receipt_without_digest),
    }
    _write_json(output_root / "receipt.json", receipt)
    return evaluation, receipt
