from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from .scene import ROBOT_JOINTS
from .source_episode import RECEIPT_SCHEMA as RECORDING_RECEIPT_SCHEMA


MANIFEST_SCHEMA = "sim2claw.exact_replay_eligibility_manifest.v1"
REPORT_SCHEMA = "sim2claw.exact_replay_eligibility_report.v1"
ACTION_HASH_ENCODING = "little_endian_float64_c_order"
EXPECTED_UNITS = {
    "joint_position": "radian",
    "joint_velocity": "radian_per_second",
    "action": "radian",
}
MODIFICATION_FIELDS = (
    "clipping",
    "inverse_kinematics",
    "joint_offset",
    "corrective_suffix",
    "assistance",
)
PHYSICAL_SAMPLE_SCHEMA = "sim2claw.physical_teleoperation_sample.v1"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def action_sha256(actions: np.ndarray) -> str:
    canonical = np.asarray(actions, dtype="<f8", order="C")
    return hashlib.sha256(canonical.tobytes(order="C")).hexdigest()


def _finite_vector(value: Any) -> np.ndarray | None:
    try:
        vector = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError):
        return None
    if vector.shape != (len(ROBOT_JOINTS),) or not np.all(np.isfinite(vector)):
        return None
    return vector


def _finite_actions(value: Any) -> np.ndarray | None:
    try:
        actions = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError):
        return None
    if (
        actions.ndim != 2
        or actions.shape[0] < 1
        or actions.shape[1] != len(ROBOT_JOINTS)
        or not np.all(np.isfinite(actions))
    ):
        return None
    return actions


def _timestamps(value: Any) -> np.ndarray | None:
    try:
        timestamps = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError):
        return None
    if (
        timestamps.ndim != 1
        or timestamps.size < 1
        or not np.all(np.isfinite(timestamps))
    ):
        return None
    return timestamps


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def audit_exact_replay_manifest(path: Path) -> dict[str, Any]:
    reasons: list[dict[str, str]] = []

    def reject(code: str, detail: str) -> None:
        reasons.append({"code": code, "detail": detail})

    try:
        raw = path.read_text(encoding="utf-8")
        manifest_sha256 = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        payload = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return {
            "schema_version": REPORT_SCHEMA,
            "status": "reject",
            "exact_replay_eligible": False,
            "manifest_path": str(path),
            "manifest_sha256": None,
            "rejection_reasons": [
                {"code": "manifest_unreadable", "detail": str(error)}
            ],
            "proof_class": None,
            "evaluator_admission": False,
            "physical_authority": False,
        }
    if not isinstance(payload, Mapping):
        reject("manifest_not_object", "manifest must be a JSON object")
        payload = {}

    if payload.get("schema_version") != MANIFEST_SCHEMA:
        reject("schema_mismatch", f"required schema is {MANIFEST_SCHEMA}")
    episode_id = str(payload.get("episode_id") or "").strip()
    if not episode_id:
        reject("episode_id_missing", "episode_id must be non-empty")
    proof_class = str(payload.get("proof_class") or "").strip()
    if not proof_class:
        reject("proof_class_missing", "proof_class must be explicit")
    if payload.get("evaluator_admission") is not False:
        reject(
            "evaluator_admission_open",
            "eligibility audit input must not grant evaluator admission",
        )
    if payload.get("physical_authority") is not False:
        reject(
            "physical_authority_open",
            "eligibility audit input must not grant physical authority",
        )

    joint_order_ok = payload.get("joint_order") == list(ROBOT_JOINTS)
    if not joint_order_ok:
        reject(
            "joint_order_mismatch",
            "joint_order must exactly match the canonical SO-101 order",
        )
    units_ok = payload.get("units") == EXPECTED_UNITS
    if not units_ok:
        reject("units_mismatch", f"units must exactly equal {EXPECTED_UNITS}")

    transform = payload.get("joint_transform")
    transform_identity = False
    if isinstance(transform, Mapping):
        sign = _finite_vector(transform.get("sign"))
        scale = _finite_vector(transform.get("scale"))
        zero = _finite_vector(transform.get("zero_offset"))
        transform_identity = bool(
            transform.get("source_joint_order") == list(ROBOT_JOINTS)
            and transform.get("target_joint_order") == list(ROBOT_JOINTS)
            and sign is not None
            and scale is not None
            and zero is not None
            and np.array_equal(sign, np.ones(len(ROBOT_JOINTS)))
            and np.array_equal(scale, np.ones(len(ROBOT_JOINTS)))
            and np.array_equal(zero, np.zeros(len(ROBOT_JOINTS)))
        )
    if not transform_identity:
        reject(
            "joint_transform_not_identity",
            "source/target order, sign, scale, and zero offset must be exact identity",
        )

    initial = payload.get("initial_state")
    initial_position_ok = False
    initial_velocity_ok = False
    initial_measured = False
    if isinstance(initial, Mapping):
        initial_position_ok = _finite_vector(initial.get("joint_position")) is not None
        initial_velocity_ok = _finite_vector(initial.get("joint_velocity")) is not None
        initial_measured = bool(
            initial.get("joint_position_source") == "measured"
            and initial.get("joint_velocity_source") == "measured"
            and str(initial.get("measurement_id") or "").strip()
        )
    if not initial_position_ok:
        reject(
            "initial_position_missing",
            "initial joint position must contain six finite measured values",
        )
    if not initial_velocity_ok:
        reject(
            "initial_velocity_missing",
            "initial joint velocity must contain six finite measured values",
        )
    if not initial_measured:
        reject(
            "initial_state_not_measured",
            "position and velocity require measured sources and a measurement_id",
        )

    timestamps = _timestamps(payload.get("timestamps_seconds"))
    timestamps_monotonic = bool(
        timestamps is not None
        and (timestamps.size == 1 or np.all(np.diff(timestamps) > 0.0))
    )
    if timestamps is None:
        reject(
            "timestamps_invalid",
            "timestamps_seconds must contain finite values",
        )
    elif not timestamps_monotonic:
        reject(
            "timestamps_not_monotonic",
            "timestamps must be strictly increasing; the audit never repairs order",
        )

    requested = _finite_actions(payload.get("requested_actions"))
    applied = _finite_actions(payload.get("applied_actions"))
    action_shape_ok = bool(
        requested is not None
        and applied is not None
        and requested.shape == applied.shape
        and timestamps is not None
        and requested.shape[0] == timestamps.size
    )
    if not action_shape_ok:
        reject(
            "action_shape_invalid",
            "requested/applied actions must be aligned N-by-6 float64-compatible arrays",
        )
    dtype_ok = payload.get("action_dtype") == "float64"
    if not dtype_ok:
        reject("action_dtype_mismatch", "action_dtype must be float64")

    requested_hash = action_sha256(requested) if requested is not None else None
    applied_hash = action_sha256(applied) if applied is not None else None
    requested_hash_ok = (
        requested_hash is not None
        and payload.get("requested_action_sha256") == requested_hash
    )
    applied_hash_ok = (
        applied_hash is not None
        and payload.get("applied_action_sha256") == applied_hash
    )
    if not requested_hash_ok:
        reject(
            "requested_action_hash_mismatch",
            "declared requested-action hash does not match float64 bytes",
        )
    if not applied_hash_ok:
        reject(
            "applied_action_hash_mismatch",
            "declared applied-action hash does not match float64 bytes",
        )
    requested_applied_exact = bool(
        requested is not None
        and applied is not None
        and requested.shape == applied.shape
        and np.array_equal(requested, applied)
    )
    if not requested_applied_exact:
        reject(
            "requested_applied_mismatch",
            "exact replay requires distinct requested/applied records to agree exactly",
        )
    action_semantics = payload.get("action_semantics")
    action_semantics_ok = bool(
        action_semantics is None
        or (
            isinstance(action_semantics, Mapping)
            and action_semantics.get("applied_field_compatibility_meaning")
            == "gateway_sent_command"
            and action_semantics.get("actuator_applied_or_acknowledged") is False
        )
    )
    if not action_semantics_ok:
        reject(
            "action_semantics_invalid",
            "optional v1 action semantics must identify gateway-sent, non-acknowledged commands",
        )

    modifications = payload.get("modifications")
    modifications_absent = bool(
        isinstance(modifications, Mapping)
        and set(modifications) == set(MODIFICATION_FIELDS)
        and all(modifications.get(field) is False for field in MODIFICATION_FIELDS)
    )
    if not modifications_absent:
        reject(
            "action_modification_present",
            "clipping, IK, offsets, suffixes, and assistance must all be explicitly false",
        )

    checks = {
        "joint_order_exact": joint_order_ok,
        "units_exact": units_ok,
        "joint_transform_identity": transform_identity,
        "initial_position_measured": initial_position_ok and initial_measured,
        "initial_velocity_measured": initial_velocity_ok and initial_measured,
        "timestamps_strictly_monotonic": timestamps_monotonic,
        "action_shape_n_by_6": action_shape_ok,
        "action_dtype_float64": dtype_ok,
        "requested_action_hash_valid": requested_hash_ok,
        "applied_action_hash_valid": applied_hash_ok,
        "requested_applied_exact": requested_applied_exact,
        "action_semantics_non_overclaiming": action_semantics_ok,
        "action_modifications_absent": modifications_absent,
    }
    eligible = not reasons
    return {
        "schema_version": REPORT_SCHEMA,
        "status": "admit" if eligible else "reject",
        "exact_replay_eligible": eligible,
        "manifest_path": str(path),
        "manifest_sha256": manifest_sha256,
        "episode_id": episode_id or None,
        "proof_class": proof_class or None,
        "evaluator_admission": False,
        "physical_authority": False,
        "joint_order": list(ROBOT_JOINTS),
        "sample_count": int(requested.shape[0]) if requested is not None else 0,
        "action_hash_encoding": ACTION_HASH_ENCODING,
        "requested_action_sha256": requested_hash,
        "applied_action_sha256": applied_hash,
        "action_semantics": action_semantics,
        "checks": checks,
        "rejection_reasons": reasons,
        "claim_limits": {
            "eligibility_only": True,
            "simulator_replay_executed": False,
            "physical_episode_admitted": False,
            "task_success": False,
        },
    }


def _read_json_object(path: Path, label: str) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is unreadable: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload, hashlib.sha256(raw).hexdigest()


def _read_physical_samples(path: Path) -> tuple[list[dict[str, Any]], str]:
    try:
        raw = path.read_bytes()
        lines = raw.decode("utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError(f"samples are unreadable: {error}") from error
    if not lines:
        raise ValueError("samples.jsonl must contain at least one sample")
    rows: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"sample {index} is invalid JSON: {error}") from error
        if not isinstance(row, dict):
            raise ValueError(f"sample {index} must be a JSON object")
        rows.append(row)
    return rows, hashlib.sha256(raw).hexdigest()


def materialize_physical_recording_exact_replay(
    recording_directory: Path,
    manifest_output: Path,
    report_output: Path,
) -> dict[str, Any]:
    """Convert a finalized physical recording into the existing v1 audit contract.

    The legacy ``applied_actions`` field is populated with commands sent to the
    gateway. It never means actuator-applied or actuator-acknowledged positions.
    """

    recording_directory = recording_directory.resolve()
    receipt_path = recording_directory / "recording_receipt.json"
    receipt, receipt_sha256 = _read_json_object(receipt_path, "recording receipt")
    if receipt.get("schema_version") != RECORDING_RECEIPT_SCHEMA:
        raise ValueError("recording receipt schema is not finalized-recorder v1")
    if receipt.get("mode") != "physical_follower":
        raise ValueError("recording receipt mode must be physical_follower")
    if receipt.get("source_sample_schema") != PHYSICAL_SAMPLE_SCHEMA:
        raise ValueError("recording receipt has the wrong physical sample schema")
    samples_relative = receipt.get("samples_path")
    if samples_relative != "samples.jsonl":
        raise ValueError("recording receipt samples_path must be samples.jsonl")
    samples_path = recording_directory / samples_relative
    rows, samples_sha256 = _read_physical_samples(samples_path)
    if receipt.get("samples_sha256") != samples_sha256:
        raise ValueError("recording receipt samples hash does not match samples.jsonl")
    if receipt.get("sample_count") != len(rows):
        raise ValueError("recording receipt sample_count does not match samples.jsonl")
    episode_id = str(receipt.get("recording_id") or "").strip()
    if not episode_id:
        raise ValueError("recording receipt recording_id is required")
    if receipt.get("proof_class") != "physical_teleoperation_source_unqualified":
        raise ValueError("recording receipt proof class is not physical unqualified")
    source_identity = receipt.get("source_identity")
    backend = receipt.get("backend")
    if (
        not isinstance(source_identity, Mapping)
        or source_identity.get("kind") != "leader_teleoperation"
        or source_identity.get("proof_class")
        != "physical_teleoperation_source_unqualified"
        or not isinstance(backend, Mapping)
        or backend.get("schema_version") != "sim2claw.so101_physical_gateway.v2"
    ):
        raise ValueError("recording receipt is not from the direct physical gateway")
    if receipt.get("assistance_frames") != 0 or receipt.get("intervention_frames") != 0:
        raise ValueError("recording receipt records assistance or intervention")
    lineage = receipt.get("lineage")
    if (
        not isinstance(lineage, Mapping)
        or lineage.get("collection_kind") != "original_source_episode"
        or lineage.get("corrective_suffix_parent_state_sha256") is not None
    ):
        raise ValueError("recording receipt lineage is modified or incomplete")

    timestamps: list[float] = []
    requested_degrees: list[list[float]] = []
    sent_degrees: list[list[float]] = []
    for index, row in enumerate(rows):
        if row.get("schema_version") != PHYSICAL_SAMPLE_SCHEMA:
            raise ValueError(f"sample {index} has the wrong physical sample schema")
        if row.get("episode_id") != episode_id or row.get("sample_index") != index:
            raise ValueError(f"sample {index} identity/index does not match the receipt")
        if bool(row.get("assistance")) or bool(row.get("intervention")):
            raise ValueError(f"sample {index} records assistance or intervention")
        if bool(row.get("rate_limited")) or bool(row.get("safety_clamped")):
            raise ValueError(f"sample {index} records rate limiting or safety clamping")
        for field in (
            "clipping",
            "inverse_kinematics",
            "joint_offset",
            "corrective_suffix",
            "offset",
            "suffix",
        ):
            if field in row and bool(row[field]):
                raise ValueError(f"sample {index} records action modification {field}")
        try:
            timestamp = float(row["timestamp_monotonic_seconds"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"sample {index} has an invalid monotonic timestamp") from error
        if not math.isfinite(timestamp):
            raise ValueError(f"sample {index} has an invalid monotonic timestamp")
        timestamps.append(timestamp)
        for field, target in (
            ("follower_requested_degrees", requested_degrees),
            ("follower_command_degrees", sent_degrees),
        ):
            vector = _finite_vector(row.get(field))
            if vector is None:
                raise ValueError(f"sample {index} has invalid {field}")
            target.append(vector.tolist())

    timestamps_array = np.asarray(timestamps, dtype=np.float64)
    if timestamps_array.size > 1 and not np.all(np.diff(timestamps_array) > 0):
        raise ValueError("recorded monotonic timestamps are not strictly increasing")
    requested = np.deg2rad(np.asarray(requested_degrees, dtype=np.float64))
    sent = np.deg2rad(np.asarray(sent_degrees, dtype=np.float64))
    first_position = _finite_vector(rows[0].get("follower_actual_position_degrees"))
    first_velocity = _finite_vector(rows[0].get("follower_actual_velocity_degrees_s"))
    if first_position is None:
        raise ValueError("first sample has no valid measured follower position")
    if first_velocity is None:
        raise ValueError("first sample has no valid measured follower velocity")

    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "episode_id": episode_id,
        "proof_class": "physical_teleoperation_source_unqualified",
        "evaluator_admission": False,
        "physical_authority": False,
        "joint_order": list(ROBOT_JOINTS),
        "units": EXPECTED_UNITS,
        "joint_transform": {
            "source_joint_order": list(ROBOT_JOINTS),
            "target_joint_order": list(ROBOT_JOINTS),
            "sign": [1.0] * len(ROBOT_JOINTS),
            "scale": [1.0] * len(ROBOT_JOINTS),
            "zero_offset": [0.0] * len(ROBOT_JOINTS),
        },
        "initial_state": {
            "joint_position": np.deg2rad(first_position).tolist(),
            "joint_velocity": np.deg2rad(first_velocity).tolist(),
            "joint_position_source": "measured",
            "joint_velocity_source": "measured",
            "measurement_id": f"{episode_id}:samples.jsonl:0",
        },
        "timestamps_seconds": timestamps,
        "requested_actions": requested.tolist(),
        "applied_actions": sent.tolist(),
        "action_dtype": "float64",
        "requested_action_sha256": action_sha256(requested),
        "applied_action_sha256": action_sha256(sent),
        "action_semantics": {
            "requested_actions_source": "samples.jsonl#follower_requested_degrees",
            "applied_actions_source": "samples.jsonl#follower_command_degrees",
            "applied_field_compatibility_meaning": "gateway_sent_command",
            "actuator_applied_or_acknowledged": False,
        },
        "modifications": {field: False for field in MODIFICATION_FIELDS},
        "conversion_provenance": {
            "adapter": "sim2claw.replay_eligibility.materialize_physical_recording_exact_replay",
            "conversion": "degrees_to_radians_float64",
            "timestamp_source": "samples.jsonl#timestamp_monotonic_seconds",
            "timestamp_repaired_or_reordered": False,
            "initial_position_source": "samples.jsonl:0#follower_actual_position_degrees",
            "initial_velocity_source": "samples.jsonl:0#follower_actual_velocity_degrees_s",
            "recording_receipt_path": "recording_receipt.json",
            "recording_receipt_sha256": receipt_sha256,
            "samples_path": "samples.jsonl",
            "samples_sha256": samples_sha256,
            "modification_checks": {
                "receipt_gateway_schema": "sim2claw.so101_physical_gateway.v2",
                "receipt_assistance_frames": "must_equal_zero",
                "receipt_intervention_frames": "must_equal_zero",
                "receipt_collection_kind": "must_equal_original_source_episode",
                "receipt_corrective_suffix_parent": "must_be_null",
                "sample_assistance": "must_be_false_for_every_sample",
                "sample_intervention": "must_be_false_for_every_sample",
                "sample_rate_limited": "must_be_false_for_every_sample",
                "sample_safety_clamped": "must_be_false_for_every_sample",
                "requested_sent_identity": "audited_after_float64_radian_conversion",
                "ik_offsets_suffixes": "not_present_in_direct_physical_gateway_sample_contract",
            },
        },
    }
    if receipt.get("evidence_identity") is not None:
        manifest["evidence_identity"] = receipt["evidence_identity"]
    _atomic_write_json(manifest_output, manifest)
    report = audit_and_write_exact_replay_manifest(manifest_output, report_output)
    report["source_recording"] = {
        "recording_receipt_sha256": receipt_sha256,
        "samples_sha256": samples_sha256,
    }
    report["claim_limits"].update(
        {
            "gateway_sent_is_actuator_ack": False,
            "device_clock_synchronized": False,
            "timing_identified": False,
        }
    )
    _atomic_write_json(report_output, report)
    return report


def audit_and_write_exact_replay_manifest(
    manifest_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    report = audit_exact_replay_manifest(manifest_path)
    _atomic_write_json(output_path, report)
    return report
