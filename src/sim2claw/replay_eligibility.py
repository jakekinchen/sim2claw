from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from .scene import ROBOT_JOINTS


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
        "checks": checks,
        "rejection_reasons": reasons,
        "claim_limits": {
            "eligibility_only": True,
            "simulator_replay_executed": False,
            "physical_episode_admitted": False,
            "task_success": False,
        },
    }


def audit_and_write_exact_replay_manifest(
    manifest_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    report = audit_exact_replay_manifest(manifest_path)
    _atomic_write_json(output_path, report)
    return report
