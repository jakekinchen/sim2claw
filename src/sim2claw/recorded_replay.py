"""Strict recorded-action replay and observable synchronization.

This module is deliberately upstream of calibration.  It accepts measured
initial state plus exact commands, replays those commands in MuJoCo under an
explicit timing contract, and emits replay-class evidence.  Missing physical
observables remain missing; labels and diagnostic video are never converted
into end-effector, pawn, or contact trajectories.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import mujoco
import numpy as np

from .paths import REPO_ROOT
from .scene import (
    CURRENT_TASK_PIECE_LAYOUT,
    ROBOT_JOINTS,
    build_scene_spec,
    initialize_robot_poses,
)


EPISODE_SCHEMA = "sim2claw.recorded_action_episode.v1"
REPLAY_RECEIPT_SCHEMA = "sim2claw.recorded_action_replay_receipt.v1"
SYNCHRONIZED_ROW_SCHEMA = "sim2claw.synchronized_replay_row.v1"
CONFIG_SCHEMA = "sim2claw.recorded_action_sysid_config.v1"
PHYSICAL_SAMPLE_SCHEMA = "sim2claw.physical_teleoperation_sample.v1"
PHYSICAL_JOINT_TRANSFORM_SCHEMA = "sim2claw.physical_joint_transform.v1"

PROOF_CLASS_CATEGORIES = {
    "fixture",
    "synthetic",
    "simulation",
    "replay",
    "learned_policy",
    "physical_read_only",
    "physical_task",
}

OBSERVABLE_METADATA = {
    "joint_position": {"field": "joint_position", "alignment": "continuous", "semantic": "vector"},
    "end_effector_position": {"field": "end_effector_position_m", "alignment": "continuous", "semantic": "vector"},
    "end_effector_orientation": {"field": "end_effector_quaternion_wxyz", "alignment": "continuous", "semantic": "quaternion_wxyz"},
    "gripper_position": {"field": "gripper_position", "alignment": "continuous", "semantic": "scalar"},
    "pawn_position": {"field": "pawn_position_m", "alignment": "continuous", "semantic": "vector"},
    "pawn_orientation": {"field": "pawn_quaternion_wxyz", "alignment": "continuous", "semantic": "quaternion_wxyz"},
    "contact_active": {"field": "contact_active", "alignment": "discrete", "semantic": "boolean"},
    "contact_force": {"field": "contact_force_n", "alignment": "continuous", "semantic": "scalar"},
}
OBSERVABLE_FIELDS = {
    name: str(metadata["field"]) for name, metadata in OBSERVABLE_METADATA.items()
}

TARGET_SUPPORTED_OBSERVABLES = {
    "end_effector_site_offset_x": {"end_effector_position"},
    "end_effector_site_offset_y": {"end_effector_position"},
    "end_effector_site_offset_z": {"end_effector_position"},
    "command_latency_seconds": {
        "joint_position",
        "end_effector_position",
        "end_effector_orientation",
        "gripper_position",
    },
    "actuator_gain_scale": {
        "joint_position",
        "end_effector_position",
        "end_effector_orientation",
        "gripper_position",
    },
    "joint_damping_scale": {
        "joint_position",
        "end_effector_position",
        "end_effector_orientation",
        "gripper_position",
    },
    "pawn_mass_scale": {
        "pawn_position",
        "pawn_orientation",
        "contact_active",
        "contact_force",
    },
    "pawn_friction_scale": {
        "pawn_position",
        "pawn_orientation",
        "contact_active",
        "contact_force",
    },
}


class ReplayContractError(ValueError):
    """A replay input would require guessing, repair, or authority widening."""


class ReplayRangeError(ReplayContractError):
    """A measured state or exact requested command is outside model limits."""

    def __init__(self, message: str, diagnostics: Mapping[str, Any]):
        super().__init__(message)
        self.diagnostics = dict(diagnostics)


@dataclass(frozen=True)
class RecordedEpisode:
    episode_id: str
    proof_class: str
    proof_class_category: str
    column: str | None
    joint_names: tuple[str, ...]
    initial_joint_position: np.ndarray
    initial_joint_velocity: np.ndarray
    timestamps: np.ndarray
    original_timestamps: np.ndarray
    commands: np.ndarray
    measured: tuple[dict[str, Any], ...]
    initial_object_state: Mapping[str, Any]
    unavailable_observables: Mapping[str, str]
    source_path: Path
    source_sha256: str
    source_schema_version: str
    source_provenance: Mapping[str, Any]
    joint_transform: Mapping[str, Any] | None

    @property
    def duration_seconds(self) -> float:
        return float(self.timestamps[-1])

    def measured_array(self, observable: str) -> np.ndarray | None:
        field = OBSERVABLE_FIELDS[observable]
        values = [sample.get(field) for sample in self.measured]
        present = [value is not None for value in values]
        if not any(present):
            return None
        if not all(present):
            raise ReplayContractError(
                f"episode {self.episode_id} has a partial {observable} series"
            )
        return np.asarray(values, dtype=np.float64)

    def available_observables(self) -> set[str]:
        return {
            name
            for name in OBSERVABLE_FIELDS
            if self.measured_array(name) is not None
        }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def canonical_json_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        separators=(",", ":"),
        sort_keys=True,
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _is_sha256(value: Any) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(character in "0123456789abcdef" for character in text)


def portable_content_identity(path: Path, sha256: str) -> dict[str, str]:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return {"kind": "content_addressed", "sha256": sha256}
    return {"kind": "repo_relative", "path": relative, "sha256": sha256}


def _validated_physical_transform(
    config: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    adapter = config.get("physical_adapter")
    if adapter is None:
        return None
    if not isinstance(adapter, Mapping):
        raise ReplayContractError("physical_adapter must be an object")
    transform = adapter.get("joint_transform")
    if not isinstance(transform, Mapping):
        raise ReplayContractError("physical_adapter.joint_transform is required")
    declared_hash = adapter.get("joint_transform_sha256")
    if not _is_sha256(declared_hash) or declared_hash != canonical_json_sha256(transform):
        raise ReplayContractError("physical joint transform hash binding does not match")
    if transform.get("schema_version") != PHYSICAL_JOINT_TRANSFORM_SCHEMA:
        raise ReplayContractError("unsupported physical joint transform schema")
    source_names = transform.get("source_joint_names")
    simulator_names = transform.get("simulator_joint_names")
    entries = transform.get("joints")
    if not (
        isinstance(source_names, list)
        and isinstance(simulator_names, list)
        and isinstance(entries, list)
        and source_names
        and len(source_names) == len(simulator_names) == len(entries)
        and len(source_names) == len(set(source_names))
        and len(simulator_names) == len(set(simulator_names))
    ):
        raise ReplayContractError(
            "physical joint transform names/order and per-joint entries must have equal unique shape"
        )
    if tuple(str(name) for name in simulator_names) != tuple(
        str(name) for name in config["bindings"]["joint_names"]
    ):
        raise ReplayContractError(
            "physical joint transform simulator order must match replay bindings"
        )
    for index, (source_name, simulator_name, entry) in enumerate(
        zip(source_names, simulator_names, entries, strict=True)
    ):
        if not isinstance(entry, Mapping):
            raise ReplayContractError(f"physical joint transform entry {index} is invalid")
        if entry.get("source_joint") != source_name or entry.get(
            "simulator_joint"
        ) != simulator_name:
            raise ReplayContractError(
                f"physical joint transform entry {index} identity/order drifted"
            )
        sign = entry.get("sign")
        scale = float(entry.get("scale", math.nan))
        offset = float(entry.get("zero_offset", math.nan))
        if sign not in {-1, 1} or not math.isfinite(scale) or scale <= 0:
            raise ReplayContractError(
                f"physical joint transform entry {index} sign/scale is invalid"
            )
        if not math.isfinite(offset):
            raise ReplayContractError(
                f"physical joint transform entry {index} zero_offset is invalid"
            )
        if not str(entry.get("input_unit") or "") or not str(
            entry.get("output_unit") or ""
        ):
            raise ReplayContractError(
                f"physical joint transform entry {index} units are required"
            )
    approved = transform.get("calibration_approved")
    if not isinstance(approved, bool):
        raise ReplayContractError(
            "physical joint transform calibration_approved must be boolean"
        )
    if approved:
        review = transform.get("review")
        if not isinstance(review, Mapping) or any(
            not str(review.get(field) or "").strip()
            for field in ("reviewer", "reviewed_at", "decision_id")
        ) or not _is_sha256(review.get("evidence_sha256")):
            raise ReplayContractError(
                "approved physical joint transform requires hash-bound review lineage"
            )
    return transform


def physical_values_through_transform(
    values: Any,
    transform: Mapping[str, Any],
    *,
    field: str,
) -> np.ndarray:
    entries = transform["joints"]
    raw = _finite_vector(values, size=len(entries), field=field)
    converted = np.asarray(
        [
            float(entry["sign"]) * raw[index] * float(entry["scale"])
            + float(entry["zero_offset"])
            for index, entry in enumerate(entries)
        ],
        dtype=np.float64,
    )
    if not np.all(np.isfinite(converted)):
        raise ReplayContractError(f"{field} transform produced non-finite values")
    return converted


def _validated_initial_object_state(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ReplayContractError("initial_object_state is required")
    status = value.get("status")
    if status == "unavailable":
        reason = str(value.get("reason") or "").strip()
        if not reason:
            raise ReplayContractError(
                "unavailable initial_object_state requires an explicit reason"
            )
        return {"status": "unavailable", "reason": reason}
    if status != "available":
        raise ReplayContractError(
            "initial_object_state status must be available or unavailable"
        )
    body_name = str(value.get("body_name") or "").strip()
    free_joint_name = str(value.get("free_joint_name") or "").strip()
    if not body_name or not free_joint_name:
        raise ReplayContractError(
            "available initial_object_state requires body and free-joint identity"
        )
    if value.get("frame") != "world":
        raise ReplayContractError("initial object pose frame must be world")
    unit_contract = {
        "position_unit": "m",
        "orientation_convention": "wxyz_unit_quaternion",
        "linear_velocity_unit": "m/s",
        "angular_velocity_unit": "rad/s",
    }
    for field, expected in unit_contract.items():
        if value.get(field) != expected:
            raise ReplayContractError(
                f"initial_object_state {field} must be {expected}"
            )
    position = _finite_vector(
        value.get("position"), size=3, field="initial_object_state.position"
    )
    quaternion = _finite_vector(
        value.get("quaternion_wxyz"),
        size=4,
        field="initial_object_state.quaternion_wxyz",
    )
    quaternion_norm = float(np.linalg.norm(quaternion))
    if not math.isclose(quaternion_norm, 1.0, rel_tol=0.0, abs_tol=1e-6):
        raise ReplayContractError(
            "initial object quaternion must already be unit length; replay never repairs it"
        )
    linear_velocity = _finite_vector(
        value.get("linear_velocity"),
        size=3,
        field="initial_object_state.linear_velocity",
    )
    angular_velocity = _finite_vector(
        value.get("angular_velocity"),
        size=3,
        field="initial_object_state.angular_velocity",
    )
    provenance = value.get("measurement_provenance")
    if not isinstance(provenance, Mapping) or any(
        not str(provenance.get(field) or "").strip()
        for field in ("source_id", "measurement_method")
    ) or not _is_sha256(provenance.get("sha256")):
        raise ReplayContractError(
            "available initial_object_state requires hash-bound measurement provenance"
        )
    return {
        "status": "available",
        "body_name": body_name,
        "free_joint_name": free_joint_name,
        "frame": "world",
        **unit_contract,
        "position": position.tolist(),
        "quaternion_wxyz": quaternion.tolist(),
        "linear_velocity": linear_velocity.tolist(),
        "angular_velocity": angular_velocity.tolist(),
        "measurement_provenance": dict(provenance),
    }


def load_sysid_config(path: Path) -> dict[str, Any]:
    path = path.resolve()
    config = json.loads(path.read_text(encoding="utf-8"))
    validate_sysid_config(config)
    config["_config_path"] = str(path)
    config["_config_sha256"] = sha256_file(path)
    return config


def validate_sysid_config(config: Mapping[str, Any]) -> None:
    if config.get("schema_version") != CONFIG_SCHEMA:
        raise ReplayContractError("unsupported recorded-action sysid config schema")
    replay = config.get("replay")
    if not isinstance(replay, Mapping):
        raise ReplayContractError("replay timing contract is required")
    if replay.get("command_interpolation") not in {
        "zero_order_hold",
        "linear",
    }:
        raise ReplayContractError("command interpolation must be explicit")
    stages = config.get("parameter_stages")
    if not isinstance(stages, list) or [stage.get("name") for stage in stages] != [
        "geometry",
        "timing_control",
        "contact_object",
    ]:
        raise ReplayContractError(
            "parameter stages must be geometry, timing_control, contact_object"
        )
    if [stage.get("order") for stage in stages] != [1, 2, 3]:
        raise ReplayContractError("parameter stages have invalid order")
    names: set[str] = set()
    for stage in stages:
        for parameter in stage.get("parameters", []):
            name = parameter.get("name")
            if not isinstance(name, str) or not name or name in names:
                raise ReplayContractError("parameter names must be unique")
            names.add(name)
            minimum = float(parameter["minimum"])
            nominal = float(parameter["nominal"])
            maximum = float(parameter["maximum"])
            if not (math.isfinite(minimum) and minimum <= nominal <= maximum):
                raise ReplayContractError(f"invalid bounds for parameter {name}")
            target = str(parameter.get("target") or "")
            declared_support = parameter.get("supports_observables")
            expected_support = TARGET_SUPPORTED_OBSERVABLES.get(target)
            if expected_support is None:
                raise ReplayContractError(f"unsupported parameter target: {target}")
            if not isinstance(declared_support, list) or set(
                str(observable) for observable in declared_support
            ) != expected_support:
                raise ReplayContractError(
                    f"parameter {name} supporting observables do not match target semantics"
                )
    optimizer = config.get("optimizer")
    try:
        minimum_sensitivity = float(optimizer["minimum_parameter_sensitivity"])
    except (KeyError, TypeError, ValueError) as error:
        raise ReplayContractError(
            "optimizer minimum_parameter_sensitivity is required"
        ) from error
    if not math.isfinite(minimum_sensitivity) or minimum_sensitivity <= 0:
        raise ReplayContractError(
            "optimizer minimum_parameter_sensitivity must be finite and positive"
        )
    split = config.get("split")
    if not isinstance(split, Mapping):
        raise ReplayContractError("split authority config is required")
    allowed_strategies = split.get("allowed_strategies")
    if allowed_strategies != ["deterministic_hash", "leave_one_column_out"]:
        raise ReplayContractError(
            "split allowed_strategies must freeze deterministic hash and LOCO"
        )
    if split.get("default_strategy") not in allowed_strategies:
        raise ReplayContractError("split default_strategy must be allowed")
    if split.get("unit") != "whole_episode" or not str(
        split.get("owner") or ""
    ).strip():
        raise ReplayContractError("split owner and whole-episode unit are required")
    if not str(split.get("seed") or "").strip():
        raise ReplayContractError("split seed is required")
    holdout_fraction = float(split.get("holdout_fraction", math.nan))
    if not math.isfinite(holdout_fraction) or not 0.0 < holdout_fraction < 1.0:
        raise ReplayContractError("split holdout_fraction must be between zero and one")
    _validated_physical_transform(config)


def _finite_vector(value: Any, *, size: int, field: str) -> np.ndarray:
    array = np.asarray(value, dtype=np.float64)
    if array.shape != (size,) or not np.all(np.isfinite(array)):
        raise ReplayContractError(f"{field} must contain {size} finite values")
    return array


def _validate_timestamps(
    values: Sequence[Any],
    *,
    maximum_gap_seconds: float,
    maximum_duration_seconds: float,
) -> tuple[np.ndarray, np.ndarray]:
    original = np.asarray(values, dtype=np.float64)
    if original.ndim != 1 or original.size < 2 or not np.all(np.isfinite(original)):
        raise ReplayContractError("episode requires at least two finite timestamps")
    differences = np.diff(original)
    if np.any(differences <= 0.0):
        raise ReplayContractError(
            "timestamps must be strictly increasing; replay never repairs ordering"
        )
    if np.any(differences > maximum_gap_seconds):
        raise ReplayContractError(
            f"timestamp gap exceeds {maximum_gap_seconds:g} seconds"
        )
    normalized = original - original[0]
    if normalized[-1] > maximum_duration_seconds:
        raise ReplayContractError(
            f"episode exceeds {maximum_duration_seconds:g} second replay bound"
        )
    return normalized, original


def _validated_measured_sample(
    measured: Any,
    *,
    joint_count: int,
    sample_index: int,
) -> dict[str, Any]:
    if not isinstance(measured, Mapping):
        raise ReplayContractError(f"sample {sample_index} measured row is required")
    result: dict[str, Any] = {
        "joint_position": _finite_vector(
            measured.get("joint_position"),
            size=joint_count,
            field=f"sample {sample_index} measured joint_position",
        ).tolist()
    }
    vector_fields = {
        "end_effector_position_m": 3,
        "end_effector_quaternion_wxyz": 4,
        "pawn_position_m": 3,
        "pawn_quaternion_wxyz": 4,
    }
    for field, size in vector_fields.items():
        if measured.get(field) is not None:
            vector = _finite_vector(
                measured[field],
                size=size,
                field=f"sample {sample_index} {field}",
            )
            if "quaternion" in field and np.linalg.norm(vector) <= np.finfo(
                np.float64
            ).eps:
                raise ReplayContractError(
                    f"sample {sample_index} {field} cannot be a zero quaternion"
                )
            result[field] = vector.tolist()
    for field in ("gripper_position", "contact_force_n"):
        if measured.get(field) is not None:
            value = float(measured[field])
            if not math.isfinite(value) or (field == "contact_force_n" and value < 0):
                raise ReplayContractError(f"sample {sample_index} has invalid {field}")
            result[field] = value
    if measured.get("contact_active") is not None:
        if not isinstance(measured["contact_active"], bool):
            raise ReplayContractError(
                f"sample {sample_index} contact_active must be boolean"
            )
        result["contact_active"] = measured["contact_active"]
    return result


def _load_canonical_episode(
    path: Path,
    config: Mapping[str, Any],
) -> RecordedEpisode:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != EPISODE_SCHEMA:
        raise ReplayContractError("unsupported recorded-action episode schema")
    episode_id = str(payload.get("episode_id") or "").strip()
    if not episode_id:
        raise ReplayContractError("episode_id is required")
    proof_class = str(payload.get("proof_class") or "").strip()
    proof_class_category = str(payload.get("proof_class_category") or "")
    if not proof_class or proof_class_category not in PROOF_CLASS_CATEGORIES:
        raise ReplayContractError("episode proof class and category are required")
    joint_names = tuple(str(name) for name in payload.get("joint_names") or [])
    if not joint_names or len(joint_names) != len(set(joint_names)):
        raise ReplayContractError("joint_names must be non-empty and unique")
    joint_count = len(joint_names)
    initial = payload.get("initial_state")
    if not isinstance(initial, Mapping):
        raise ReplayContractError("measured initial_state is required")
    initial_position = _finite_vector(
        initial.get("joint_position"),
        size=joint_count,
        field="initial_state.joint_position",
    )
    if initial.get("joint_velocity") is None:
        initial_velocity = np.zeros(joint_count, dtype=np.float64)
    else:
        initial_velocity = _finite_vector(
            initial["joint_velocity"],
            size=joint_count,
            field="initial_state.joint_velocity",
        )
    initial_object_state = _validated_initial_object_state(
        payload.get("initial_object_state")
    )
    samples = payload.get("samples")
    if not isinstance(samples, list):
        raise ReplayContractError("samples must be an array")
    timestamps, original_timestamps = _validate_timestamps(
        [sample.get("timestamp_seconds") for sample in samples],
        maximum_gap_seconds=float(config["replay"]["maximum_gap_seconds"]),
        maximum_duration_seconds=float(
            config["replay"]["maximum_duration_seconds"]
        ),
    )
    commands = np.asarray(
        [
            _finite_vector(
                sample.get("command_joint_position"),
                size=joint_count,
                field=f"sample {index} command_joint_position",
            )
            for index, sample in enumerate(samples)
        ],
        dtype=np.float64,
    )
    measured = tuple(
        _validated_measured_sample(
            sample.get("measured"),
            joint_count=joint_count,
            sample_index=index,
        )
        for index, sample in enumerate(samples)
    )
    unavailable = payload.get("unavailable_observables") or {}
    if not isinstance(unavailable, Mapping) or not all(
        isinstance(name, str) and isinstance(reason, str) and reason
        for name, reason in unavailable.items()
    ):
        raise ReplayContractError("unavailable_observables must map names to reasons")
    unknown_unavailable = set(unavailable).difference(OBSERVABLE_FIELDS)
    if unknown_unavailable:
        raise ReplayContractError(
            "unavailable_observables contains unknown names: "
            f"{sorted(unknown_unavailable)}"
        )
    column = payload.get("column")
    if column is not None:
        column = str(column).lower()
        if column not in tuple("abcdefgh"):
            raise ReplayContractError("episode column must be a through h")
    episode = RecordedEpisode(
        episode_id=episode_id,
        proof_class=proof_class,
        proof_class_category=proof_class_category,
        column=column,
        joint_names=joint_names,
        initial_joint_position=initial_position,
        initial_joint_velocity=initial_velocity,
        timestamps=timestamps,
        original_timestamps=original_timestamps,
        commands=commands,
        measured=measured,
        initial_object_state=initial_object_state,
        unavailable_observables=dict(unavailable),
        source_path=path,
        source_sha256=sha256_file(path),
        source_schema_version=EPISODE_SCHEMA,
        source_provenance={
            "chain_complete": proof_class_category != "physical_read_only",
            "episode": portable_content_identity(path, sha256_file(path)),
            "catalog": None,
            "recording_receipt": None,
            "samples": portable_content_identity(path, sha256_file(path)),
            "incomplete_reason": (
                "canonical physical-read-only episode lacks catalog/receipt/sample chain"
                if proof_class_category == "physical_read_only"
                else None
            ),
        },
        joint_transform=None,
    )
    available = episode.available_observables()
    conflict = available.intersection(unavailable)
    if conflict:
        raise ReplayContractError(
            f"observables cannot be both present and unavailable: {sorted(conflict)}"
        )
    object_observables = available.intersection(
        {"pawn_position", "pawn_orientation", "contact_active", "contact_force"}
    )
    if object_observables and initial_object_state["status"] != "available":
        raise ReplayContractError(
            "pawn/contact observables require an available measured initial_object_state "
            f"binding: {sorted(object_observables)}"
        )
    return episode


def _bind_physical_catalog_provenance(
    *,
    directory: Path,
    episode_id: str,
    receipt_path: Path,
    samples_path: Path,
    receipt_sha256: str,
    samples_sha256: str,
    source_provenance: Mapping[str, Any],
) -> dict[str, Any]:
    """Open and verify the catalog entry before granting a complete-chain claim."""

    catalog_binding = source_provenance.get("catalog")
    receipt_binding = source_provenance.get("recording_receipt") or {}
    samples_binding = source_provenance.get("samples") or {}
    if not isinstance(catalog_binding, Mapping):
        catalog_binding = {}
    catalog_hash = catalog_binding.get("sha256")
    catalog_path_text = str(catalog_binding.get("path") or "")
    runtime_path_text = str(catalog_binding.get("_runtime_path") or "")
    portable_catalog = {
        key: catalog_binding[key]
        for key in ("kind", "path", "catalog_id", "sha256")
        if catalog_binding.get(key) is not None
    }
    base = {
        "episode_id": episode_id,
        "chain_complete": False,
        "catalog": portable_catalog or None,
        "recording_receipt": {
            key: receipt_binding[key]
            for key in ("kind", "path", "sha256")
            if receipt_binding.get(key) is not None
        },
        "samples": {
            key: samples_binding[key]
            for key in ("kind", "path", "sha256")
            if samples_binding.get(key) is not None
        },
    }
    if not runtime_path_text and not catalog_path_text:
        base["incomplete_reason"] = (
            "caller-supplied catalog identity had no resolvable catalog path; "
            "receipt/sample hashes alone do not prove the catalog entry"
        )
        return base
    if catalog_path_text and Path(catalog_path_text).is_absolute():
        raise ReplayContractError("physical catalog provenance path must be portable")
    if not _is_sha256(catalog_hash):
        raise ReplayContractError("physical catalog provenance hash is invalid")

    candidates: list[Path] = []
    if runtime_path_text:
        candidates.append(Path(runtime_path_text).resolve())
    if catalog_path_text:
        for ancestor in (directory.resolve(), *directory.resolve().parents):
            candidates.append((ancestor / catalog_path_text).resolve())
    matching_paths = {
        candidate
        for candidate in candidates
        if candidate.is_file() and sha256_file(candidate) == catalog_hash
    }
    if len(matching_paths) != 1:
        raise ReplayContractError(
            "physical catalog provenance cannot be uniquely opened and hash-verified"
        )
    catalog_path = matching_paths.pop()
    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReplayContractError(
            "physical catalog provenance is not a readable JSON catalog"
        ) from error
    if not isinstance(catalog, Mapping) or not isinstance(catalog.get("episodes"), list):
        raise ReplayContractError("physical catalog provenance has no episode list")
    if catalog.get("catalog_id") != catalog_binding.get("catalog_id"):
        raise ReplayContractError("physical catalog identity does not match payload")
    entries = [
        entry
        for entry in catalog["episodes"]
        if isinstance(entry, Mapping) and entry.get("recording_id") == episode_id
    ]
    if len(entries) != 1:
        raise ReplayContractError(
            "physical catalog must bind exactly one entry for the recording identity"
        )
    entry = entries[0]
    assets = entry.get("assets") or {}
    receipt_asset = str(assets.get("receipt") or "")
    samples_asset = str(assets.get("samples") or "")
    if (
        not receipt_asset
        or not samples_asset
        or Path(receipt_asset).is_absolute()
        or Path(samples_asset).is_absolute()
    ):
        raise ReplayContractError("physical catalog asset paths must be repo-relative")
    if (
        entry.get("receipt_sha256") != receipt_sha256
        or entry.get("samples_sha256") != samples_sha256
        or receipt_binding.get("sha256") != receipt_sha256
        or samples_binding.get("sha256") != samples_sha256
        or receipt_binding.get("path") != receipt_asset
        or samples_binding.get("path") != samples_asset
    ):
        raise ReplayContractError(
            "physical catalog entry does not bind the supplied receipt/sample provenance"
        )

    candidate_roots = {
        ancestor.resolve()
        for ancestor in (
            directory.resolve(),
            *directory.resolve().parents,
            catalog_path.parent.resolve(),
            *catalog_path.parent.resolve().parents,
        )
    }
    matching_roots = {
        root
        for root in candidate_roots
        if (root / receipt_asset).resolve() == receipt_path.resolve()
        and (root / samples_asset).resolve() == samples_path.resolve()
        and (
            not catalog_path_text
            or (root / catalog_path_text).resolve() == catalog_path
        )
    }
    if not matching_roots:
        raise ReplayContractError(
            "physical catalog asset paths do not resolve to the loaded recording"
        )
    base["chain_complete"] = True
    base["incomplete_reason"] = None
    return base


def _load_physical_recording(
    directory: Path,
    config: Mapping[str, Any],
    *,
    source_provenance: Mapping[str, Any] | None,
) -> RecordedEpisode:
    receipt_path = directory / "recording_receipt.json"
    samples_path = directory / "samples.jsonl"
    if not receipt_path.is_file() or not samples_path.is_file():
        raise ReplayContractError(
            "physical recording requires recording_receipt.json and samples.jsonl"
        )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if not isinstance(receipt, Mapping):
        raise ReplayContractError("physical recording receipt must be a JSON object")
    if receipt.get("mode") != "physical_follower":
        raise ReplayContractError("recording is not a physical-follower command trace")
    samples_sha256 = sha256_file(samples_path)
    if samples_sha256 != receipt.get("samples_sha256"):
        raise ReplayContractError("physical recording samples do not match receipt")
    try:
        samples = [
            json.loads(line)
            for line in samples_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except json.JSONDecodeError as error:
        raise ReplayContractError(
            f"physical recording contains malformed JSONL: {error}"
        ) from error
    if not samples:
        raise ReplayContractError("physical recording is empty")
    if receipt.get("sample_count") is not None and receipt.get("sample_count") != len(
        samples
    ):
        raise ReplayContractError("physical recording sample_count does not match payload")
    expected_joint_names = tuple(config["bindings"]["joint_names"])
    if expected_joint_names != tuple(f"left_{name}" for name in ROBOT_JOINTS):
        raise ReplayContractError(
            "physical recording adapter only supports the current left SO-101 binding"
        )
    transform = _validated_physical_transform(config)
    if transform is None:
        raise ReplayContractError(
            "physical recording requires an explicit hash-bound joint transform"
        )
    if tuple(str(name) for name in transform["source_joint_names"]) != tuple(
        ROBOT_JOINTS
    ):
        raise ReplayContractError(
            "physical source joint identity/order must match the recorded SO-101 schema"
        )
    commands: list[np.ndarray] = []
    measured: list[dict[str, Any]] = []
    for index, sample in enumerate(samples):
        if not isinstance(sample, Mapping):
            raise ReplayContractError(f"physical sample {index} must be a JSON object")
        schema = sample.get("schema_version")
        if schema not in {None, PHYSICAL_SAMPLE_SCHEMA}:
            raise ReplayContractError(
                f"physical sample {index} uses unsupported schema {schema}"
            )
        command = physical_values_through_transform(
            sample.get("follower_command_degrees"),
            transform,
            field=f"physical sample {index} follower_command_degrees",
        )
        actual = physical_values_through_transform(
            sample.get("follower_actual_position_degrees"),
            transform,
            field=f"physical sample {index} follower_actual_position_degrees",
        )
        commands.append(command)
        measured.append(
            {
                "joint_position": actual.tolist(),
                "gripper_position": float(actual[-1]),
            }
        )
    timestamps, original_timestamps = _validate_timestamps(
        [sample.get("timestamp_monotonic_seconds") for sample in samples],
        maximum_gap_seconds=float(config["replay"]["maximum_gap_seconds"]),
        maximum_duration_seconds=float(
            config["replay"]["maximum_duration_seconds"]
        ),
    )
    episode_id = str(receipt.get("recording_id") or directory.name)
    if not episode_id.strip():
        raise ReplayContractError("physical receipt recording_id is required")
    receipt_sha256 = sha256_file(receipt_path)
    if source_provenance is not None:
        expected_receipt = source_provenance.get("recording_receipt") or {}
        expected_samples = source_provenance.get("samples") or {}
        if (
            expected_receipt.get("sha256") != receipt_sha256
            or expected_samples.get("sha256") != samples_sha256
        ):
            raise ReplayContractError(
                "physical catalog/receipt/sample provenance chain does not match payload"
            )
        if source_provenance.get("episode_id") != episode_id:
            raise ReplayContractError(
                "physical provenance recording identity does not match receipt"
            )
        bound_provenance = _bind_physical_catalog_provenance(
            directory=directory,
            episode_id=episode_id,
            receipt_path=receipt_path,
            samples_path=samples_path,
            receipt_sha256=receipt_sha256,
            samples_sha256=samples_sha256,
            source_provenance=source_provenance,
        )
    else:
        bound_provenance = {
            "episode_id": episode_id,
            "chain_complete": False,
            "catalog": None,
            "recording_receipt": portable_content_identity(
                receipt_path, receipt_sha256
            ),
            "samples": portable_content_identity(samples_path, samples_sha256),
            "incomplete_reason": (
                "direct physical replay was not supplied a catalog content binding"
            ),
        }
    unavailable = {
        "end_effector_position": "physical source schema has no measured end-effector trajectory",
        "end_effector_orientation": (
            "physical source schema has no measured end-effector orientation"
        ),
        "pawn_position": "physical source schema has no reviewed metric pawn trajectory",
        "pawn_orientation": "physical source schema has no reviewed metric pawn orientation",
        "contact_active": "physical source schema has no measured contact observable",
        "contact_force": "physical source schema has no measured contact-force observable",
    }
    episode = RecordedEpisode(
        episode_id=episode_id,
        proof_class=str(
            receipt.get("proof_class")
            or "physical_teleoperation_source_unqualified"
        ),
        proof_class_category="physical_read_only",
        column=None,
        joint_names=expected_joint_names,
        initial_joint_position=np.asarray(measured[0]["joint_position"]),
        initial_joint_velocity=np.zeros(len(expected_joint_names), dtype=np.float64),
        timestamps=timestamps,
        original_timestamps=original_timestamps,
        commands=np.asarray(commands, dtype=np.float64),
        measured=tuple(measured),
        initial_object_state={
            "status": "unavailable",
            "reason": (
                "physical source schema has no measured object body/free-joint pose binding"
            ),
        },
        unavailable_observables=unavailable,
        source_path=samples_path,
        source_sha256=samples_sha256,
        source_schema_version=PHYSICAL_SAMPLE_SCHEMA,
        source_provenance=bound_provenance,
        joint_transform={
            "schema_version": transform["schema_version"],
            "transform_id": transform.get("transform_id"),
            "sha256": canonical_json_sha256(transform),
            "calibration_approved": transform["calibration_approved"],
        },
    )
    model, _ = _compile_model(config, base_directory=None)
    ids = _binding_ids(model, episode, config)
    _require_episode_joint_limits(model, ids, episode)
    return episode


def load_recorded_episode(
    path: Path,
    config: Mapping[str, Any],
    *,
    source_provenance: Mapping[str, Any] | None = None,
) -> RecordedEpisode:
    path = path.resolve()
    validate_sysid_config(config)
    if path.is_dir():
        return _load_physical_recording(
            path,
            config,
            source_provenance=source_provenance,
        )
    if source_provenance is not None:
        raise ReplayContractError(
            "catalog/receipt/sample provenance is only valid for physical directories"
        )
    if not path.is_file():
        raise ReplayContractError(f"episode input does not exist: {path}")
    return _load_canonical_episode(path, config)


def _compile_model(
    config: Mapping[str, Any],
    *,
    base_directory: Path | None,
) -> tuple[mujoco.MjModel, bool]:
    model_config = config["model"]
    kind = model_config.get("kind")
    if kind == "current_chess_scene":
        return (
            build_scene_spec(piece_layout=CURRENT_TASK_PIECE_LAYOUT).compile(),
            True,
        )
    if kind == "xml_path":
        xml_path = Path(model_config["path"])
        if not xml_path.is_absolute():
            if base_directory is None:
                raise ReplayContractError("relative model path needs a base directory")
            xml_path = base_directory / xml_path
        if not xml_path.is_file():
            raise ReplayContractError(f"MuJoCo model does not exist: {xml_path}")
        return mujoco.MjModel.from_xml_path(str(xml_path)), False
    if kind == "xml_string":
        return mujoco.MjModel.from_xml_string(str(model_config["xml"])), False
    raise ReplayContractError(f"unsupported MuJoCo model kind: {kind}")


def _parameter_descriptors(config: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        str(parameter["name"]): parameter
        for stage in config["parameter_stages"]
        for parameter in stage.get("parameters", [])
    }


def nominal_parameter_values(config: Mapping[str, Any]) -> dict[str, float]:
    return {
        name: float(descriptor["nominal"])
        for name, descriptor in _parameter_descriptors(config).items()
    }


def validate_parameter_values(
    config: Mapping[str, Any],
    parameter_values: Mapping[str, float],
) -> dict[str, float]:
    descriptors = _parameter_descriptors(config)
    unknown = set(parameter_values).difference(descriptors)
    if unknown:
        raise ReplayContractError(f"unknown replay parameters: {sorted(unknown)}")
    result = nominal_parameter_values(config)
    for name, raw_value in parameter_values.items():
        value = float(raw_value)
        descriptor = descriptors[name]
        if not math.isfinite(value) or not (
            float(descriptor["minimum"])
            <= value
            <= float(descriptor["maximum"])
        ):
            raise ReplayContractError(f"parameter {name} is outside its bounds")
        result[name] = value
    return result


def _body_subtree_ids(model: mujoco.MjModel, names: Iterable[str]) -> set[int]:
    roots: set[int] = set()
    for name in names:
        body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, name)
        if body_id < 0:
            raise ReplayContractError(f"model is missing body {name}")
        roots.add(body_id)
    result: set[int] = set()
    for body_id in range(model.nbody):
        cursor = body_id
        while cursor > 0:
            if cursor in roots:
                result.add(body_id)
                break
            cursor = int(model.body_parentid[cursor])
    return result


def _apply_parameters(
    model: mujoco.MjModel,
    config: Mapping[str, Any],
    values: Mapping[str, float],
    *,
    object_body_name: str | None,
) -> None:
    bindings = config["bindings"]
    joint_names = tuple(bindings["joint_names"])
    actuator_names = tuple(bindings["actuator_names"])
    mass_properties_changed = False
    for name, descriptor in _parameter_descriptors(config).items():
        value = values[name]
        target = descriptor["target"]
        if target.startswith("end_effector_site_offset_"):
            site_name = bindings.get("end_effector_site")
            if not site_name:
                raise ReplayContractError(
                    f"parameter {name} requires an end_effector_site binding"
                )
            site_id = mujoco.mj_name2id(
                model, mujoco.mjtObj.mjOBJ_SITE, str(site_name)
            )
            if site_id < 0:
                raise ReplayContractError(f"model is missing site {site_name}")
            axis = {"x": 0, "y": 1, "z": 2}[str(target)[-1]]
            model.site_pos[site_id, axis] += value
        elif target == "actuator_gain_scale":
            for actuator_name in actuator_names:
                actuator_id = mujoco.mj_name2id(
                    model, mujoco.mjtObj.mjOBJ_ACTUATOR, actuator_name
                )
                if actuator_id < 0:
                    raise ReplayContractError(
                        f"model is missing actuator {actuator_name}"
                    )
                model.actuator_gainprm[actuator_id] *= value
                model.actuator_biasprm[actuator_id] *= value
        elif target == "joint_damping_scale":
            for joint_name in joint_names:
                joint_id = mujoco.mj_name2id(
                    model, mujoco.mjtObj.mjOBJ_JOINT, joint_name
                )
                if joint_id < 0:
                    raise ReplayContractError(f"model is missing joint {joint_name}")
                dof_address = int(model.jnt_dofadr[joint_id])
                model.dof_damping[dof_address] *= value
        elif target == "pawn_mass_scale":
            pawn_body = object_body_name
            if pawn_body:
                body_id = mujoco.mj_name2id(
                    model, mujoco.mjtObj.mjOBJ_BODY, str(pawn_body)
                )
                if body_id < 0:
                    raise ReplayContractError(f"model is missing pawn body {pawn_body}")
                model.body_mass[body_id] *= value
                model.body_inertia[body_id] *= value
                mass_properties_changed = True
            elif not math.isclose(value, float(descriptor["nominal"])):
                raise ReplayContractError(
                    f"parameter {name} requires an episode object-body binding"
                )
        elif target == "pawn_friction_scale":
            pawn_body = object_body_name
            if pawn_body:
                body_ids = _body_subtree_ids(model, [str(pawn_body)])
                for geom_id in range(model.ngeom):
                    if int(model.geom_bodyid[geom_id]) in body_ids:
                        model.geom_friction[geom_id] *= value
            elif not math.isclose(value, float(descriptor["nominal"])):
                raise ReplayContractError(
                    f"parameter {name} requires an episode object-body binding"
                )
        elif target == "command_latency_seconds":
            continue
        else:
            raise ReplayContractError(f"unsupported parameter target: {target}")
    if mass_properties_changed:
        # MuJoCo caches subtree masses and other constants derived from body
        # mass/inertia.  Mutating model arrays without this call leaves the
        # actual dynamics internally inconsistent.
        mujoco.mj_setConst(model, mujoco.MjData(model))


def _binding_ids(
    model: mujoco.MjModel,
    episode: RecordedEpisode,
    config: Mapping[str, Any],
) -> dict[str, Any]:
    bindings = config["bindings"]
    joint_names = tuple(str(name) for name in bindings["joint_names"])
    actuator_names = tuple(str(name) for name in bindings["actuator_names"])
    if episode.joint_names != joint_names:
        raise ReplayContractError(
            "episode joint order must exactly match the replay binding order"
        )
    if len(actuator_names) != len(joint_names):
        raise ReplayContractError("one actuator binding is required per replay joint")
    joint_ids: list[int] = []
    qpos_addresses: list[int] = []
    dof_addresses: list[int] = []
    actuator_ids: list[int] = []
    for joint_name, actuator_name in zip(joint_names, actuator_names, strict=True):
        joint_id = mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_JOINT, joint_name
        )
        actuator_id = mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_ACTUATOR, actuator_name
        )
        if joint_id < 0 or actuator_id < 0:
            raise ReplayContractError(
                f"model is missing replay binding {joint_name}/{actuator_name}"
            )
        if model.jnt_type[joint_id] not in {
            mujoco.mjtJoint.mjJNT_HINGE,
            mujoco.mjtJoint.mjJNT_SLIDE,
        }:
            raise ReplayContractError(f"replay joint {joint_name} must be scalar")
        joint_ids.append(joint_id)
        qpos_addresses.append(int(model.jnt_qposadr[joint_id]))
        dof_addresses.append(int(model.jnt_dofadr[joint_id]))
        actuator_ids.append(actuator_id)
    site_id: int | None = None
    if bindings.get("end_effector_site"):
        candidate = mujoco.mj_name2id(
            model,
            mujoco.mjtObj.mjOBJ_SITE,
            str(bindings["end_effector_site"]),
        )
        if candidate < 0:
            raise ReplayContractError(
                f"model is missing end-effector site {bindings['end_effector_site']}"
            )
        site_id = candidate
    gripper_index: int | None = None
    if bindings.get("gripper_joint"):
        try:
            gripper_index = joint_names.index(str(bindings["gripper_joint"]))
        except ValueError as error:
            raise ReplayContractError(
                "gripper_joint must be one of the replay joint bindings"
            ) from error
    pawn_body_id: int | None = None
    object_qpos_address: int | None = None
    object_dof_address: int | None = None
    object_state = episode.initial_object_state
    object_body_name: str | None = None
    if object_state.get("status") == "available":
        object_body_name = str(object_state["body_name"])
        configured_pawn = bindings.get("pawn_body")
        if configured_pawn and str(configured_pawn) != object_body_name:
            raise ReplayContractError(
                "episode object body conflicts with the configured pawn_body"
            )
        candidate = mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_BODY, object_body_name
        )
        if candidate < 0:
            raise ReplayContractError(
                f"model is missing episode object body {object_body_name}"
            )
        pawn_body_id = candidate
        free_joint_name = str(object_state["free_joint_name"])
        free_joint_id = mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_JOINT, free_joint_name
        )
        if free_joint_id < 0:
            raise ReplayContractError(
                f"model is missing episode object free joint {free_joint_name}"
            )
        if model.jnt_type[free_joint_id] != mujoco.mjtJoint.mjJNT_FREE:
            raise ReplayContractError(
                f"episode object joint {free_joint_name} must be a free joint"
            )
        if int(model.jnt_bodyid[free_joint_id]) != pawn_body_id:
            raise ReplayContractError(
                "episode object free joint does not belong to the named object body"
            )
        object_qpos_address = int(model.jnt_qposadr[free_joint_id])
        object_dof_address = int(model.jnt_dofadr[free_joint_id])
    contact_body_sets: tuple[set[int], set[int]] | None = None
    contact_groups = bindings.get("contact_body_groups")
    if contact_groups:
        if not (
            isinstance(contact_groups, list)
            and len(contact_groups) == 2
            and all(isinstance(group, list) for group in contact_groups)
        ):
            raise ReplayContractError("contact_body_groups must contain two lists")
        if contact_groups[0] and contact_groups[1]:
            resolved_groups: list[list[str]] = []
            for group in contact_groups:
                resolved: list[str] = []
                for name in group:
                    if name == "$episode_object":
                        if object_body_name is None:
                            resolved = []
                            break
                        resolved.append(object_body_name)
                    else:
                        resolved.append(str(name))
                resolved_groups.append(resolved)
            if all(resolved_groups):
                contact_body_sets = (
                    _body_subtree_ids(model, resolved_groups[0]),
                    _body_subtree_ids(model, resolved_groups[1]),
                )
    return {
        "joint_ids": joint_ids,
        "qpos_addresses": np.asarray(qpos_addresses, dtype=np.int64),
        "dof_addresses": np.asarray(dof_addresses, dtype=np.int64),
        "actuator_ids": np.asarray(actuator_ids, dtype=np.int64),
        "site_id": site_id,
        "gripper_index": gripper_index,
        "pawn_body_id": pawn_body_id,
        "object_qpos_address": object_qpos_address,
        "object_dof_address": object_dof_address,
        "contact_body_sets": contact_body_sets,
    }


def _series_limit_report(
    values: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
    joint_names: Sequence[str],
) -> dict[str, Any]:
    array = np.asarray(values, dtype=np.float64)
    if array.ndim == 1:
        array = array.reshape(1, -1)
    below = np.maximum(lower - array, 0.0)
    above = np.maximum(array - upper, 0.0)
    exceedance = np.maximum(below, above)
    violations = exceedance > 1e-12
    return {
        "row_count": int(array.shape[0]),
        "violating_row_count": int(np.count_nonzero(np.any(violations, axis=1))),
        "violating_joint_value_count": int(np.count_nonzero(violations)),
        "maximum_exceedance": float(np.max(exceedance, initial=0.0)),
        "per_joint": {
            name: {
                "lower": float(lower[index]),
                "upper": float(upper[index]),
                "violating_row_count": int(np.count_nonzero(violations[:, index])),
                "maximum_exceedance": float(
                    np.max(exceedance[:, index], initial=0.0)
                ),
            }
            for index, name in enumerate(joint_names)
        },
    }


def episode_joint_limit_diagnostics(
    model: mujoco.MjModel,
    ids: Mapping[str, Any],
    episode: RecordedEpisode,
) -> dict[str, Any]:
    joint_lower: list[float] = []
    joint_upper: list[float] = []
    command_lower: list[float] = []
    command_upper: list[float] = []
    for joint_id, actuator_id in zip(
        ids["joint_ids"], ids["actuator_ids"], strict=True
    ):
        if bool(model.jnt_limited[joint_id]):
            low, high = (float(value) for value in model.jnt_range[joint_id])
        else:
            low, high = -math.inf, math.inf
        joint_lower.append(low)
        joint_upper.append(high)
        if bool(model.actuator_ctrllimited[actuator_id]):
            control_low, control_high = (
                float(value) for value in model.actuator_ctrlrange[actuator_id]
            )
            command_lower.append(max(low, control_low))
            command_upper.append(min(high, control_high))
        else:
            command_lower.append(low)
            command_upper.append(high)
    joint_low = np.asarray(joint_lower, dtype=np.float64)
    joint_high = np.asarray(joint_upper, dtype=np.float64)
    control_low = np.asarray(command_lower, dtype=np.float64)
    control_high = np.asarray(command_upper, dtype=np.float64)
    measured = np.asarray(
        [sample["joint_position"] for sample in episode.measured],
        dtype=np.float64,
    )
    reports = {
        "initial_measured_state": _series_limit_report(
            episode.initial_joint_position,
            joint_low,
            joint_high,
            episode.joint_names,
        ),
        "measured_trajectory": _series_limit_report(
            measured,
            joint_low,
            joint_high,
            episode.joint_names,
        ),
        "recorded_commands": _series_limit_report(
            episode.commands,
            control_low,
            control_high,
            episode.joint_names,
        ),
    }
    all_within_limits = all(
        report["violating_joint_value_count"] == 0 for report in reports.values()
    )
    return {
        "joint_names": list(episode.joint_names),
        **reports,
        "all_within_limits": all_within_limits,
        "exact_replay_eligible": all_within_limits,
    }


def _require_episode_joint_limits(
    model: mujoco.MjModel,
    ids: Mapping[str, Any],
    episode: RecordedEpisode,
) -> dict[str, Any]:
    diagnostics = episode_joint_limit_diagnostics(model, ids, episode)
    if not diagnostics["all_within_limits"]:
        raise ReplayRangeError(
            "episode initial state, measured trajectory, or exact recorded commands "
            "exceed simulator joint/control limits; replay refuses silent assignment or clipping",
            diagnostics,
        )
    return diagnostics


def inspect_episode_joint_limits(
    episode: RecordedEpisode,
    config: Mapping[str, Any],
    *,
    model_base_directory: Path | None = None,
) -> dict[str, Any]:
    model, _ = _compile_model(config, base_directory=model_base_directory)
    ids = _binding_ids(model, episode, config)
    return episode_joint_limit_diagnostics(model, ids, episode)


def _require_exact_control(
    model: mujoco.MjModel,
    actuator_ids: np.ndarray,
    command: np.ndarray,
) -> np.ndarray:
    applied = np.asarray(command, dtype=np.float64).copy()
    for local_index, actuator_id in enumerate(actuator_ids):
        if bool(model.actuator_ctrllimited[actuator_id]):
            low, high = model.actuator_ctrlrange[actuator_id]
            if applied[local_index] < low - 1e-12 or applied[local_index] > high + 1e-12:
                diagnostics = {
                    "actuator_id": int(actuator_id),
                    "local_joint_index": local_index,
                    "requested": float(applied[local_index]),
                    "lower": float(low),
                    "upper": float(high),
                    "would_clip": True,
                }
                raise ReplayRangeError(
                    "exact replay requested a control outside actuator limits; clipping is forbidden",
                    diagnostics,
                )
    return applied


def _command_at(
    episode: RecordedEpisode,
    time_seconds: float,
    *,
    latency_seconds: float,
    interpolation: str,
) -> np.ndarray:
    query = max(0.0, time_seconds - latency_seconds)
    query = min(query, episode.duration_seconds)
    if interpolation == "zero_order_hold":
        index = int(np.searchsorted(episode.timestamps, query, side="right") - 1)
        return episode.commands[max(index, 0)].copy()
    return np.asarray(
        [
            np.interp(query, episode.timestamps, episode.commands[:, column])
            for column in range(episode.commands.shape[1])
        ],
        dtype=np.float64,
    )


def _simulation_observables(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    ids: Mapping[str, Any],
) -> dict[str, Any]:
    qpos = data.qpos[ids["qpos_addresses"]].astype(float).copy()
    result: dict[str, Any] = {"joint_position": qpos.tolist()}
    site_id = ids["site_id"]
    if site_id is not None:
        quaternion = np.empty(4, dtype=np.float64)
        mujoco.mju_mat2Quat(quaternion, data.site_xmat[site_id])
        result["end_effector_position_m"] = data.site_xpos[site_id].astype(float).tolist()
        result["end_effector_quaternion_wxyz"] = quaternion.tolist()
    gripper_index = ids["gripper_index"]
    if gripper_index is not None:
        result["gripper_position"] = float(qpos[gripper_index])
    pawn_body_id = ids["pawn_body_id"]
    if pawn_body_id is not None:
        result["pawn_position_m"] = data.xpos[pawn_body_id].astype(float).tolist()
        result["pawn_quaternion_wxyz"] = data.xquat[pawn_body_id].astype(float).tolist()
    contact_sets = ids["contact_body_sets"]
    if contact_sets is not None:
        active = False
        force = 0.0
        for contact_index in range(data.ncon):
            contact = data.contact[contact_index]
            body_a = int(model.geom_bodyid[contact.geom[0]])
            body_b = int(model.geom_bodyid[contact.geom[1]])
            matches = (
                body_a in contact_sets[0] and body_b in contact_sets[1]
            ) or (body_a in contact_sets[1] and body_b in contact_sets[0])
            if matches:
                active = True
                contact_force = np.zeros(6, dtype=np.float64)
                mujoco.mj_contactForce(model, data, contact_index, contact_force)
                force += float(np.linalg.norm(contact_force[:3]))
        result["contact_active"] = active
        result["contact_force_n"] = force
    return result


def _align_continuous(
    native_times: np.ndarray,
    values: Sequence[Any],
    target_times: np.ndarray,
    *,
    semantic: str,
) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    if array.ndim == 1:
        return np.interp(target_times, native_times, array)
    if semantic == "quaternion_wxyz":
        if array.ndim != 2 or array.shape[1] != 4:
            raise ReplayContractError(
                "quaternion alignment requires an explicit Nx4 quaternion series"
            )
        array = array.copy()
        for index in range(1, len(array)):
            if float(np.dot(array[index - 1], array[index])) < 0.0:
                array[index] *= -1.0
    aligned = np.column_stack(
        [
            np.interp(target_times, native_times, array[:, column])
            for column in range(array.shape[1])
        ]
    )
    if semantic == "quaternion_wxyz":
        norms = np.linalg.norm(aligned, axis=1, keepdims=True)
        aligned = aligned / np.maximum(norms, np.finfo(np.float64).eps)
    return aligned


def _align_discrete(
    native_times: np.ndarray,
    values: Sequence[Any],
    target_times: np.ndarray,
) -> np.ndarray:
    indices = np.searchsorted(native_times, target_times, side="right") - 1
    indices = np.clip(indices, 0, len(native_times) - 1)
    return np.asarray(values)[indices]


def simulate_and_align(
    episode: RecordedEpisode,
    config: Mapping[str, Any],
    *,
    parameter_values: Mapping[str, float] | None = None,
    model_base_directory: Path | None = None,
) -> dict[str, Any]:
    """Replay an episode and align native simulation values to measured times."""

    validate_sysid_config(config)
    parameters = validate_parameter_values(config, parameter_values or {})
    model, current_scene = _compile_model(
        config,
        base_directory=model_base_directory,
    )
    object_body_name = (
        str(episode.initial_object_state["body_name"])
        if episode.initial_object_state.get("status") == "available"
        else None
    )
    _apply_parameters(
        model,
        config,
        parameters,
        object_body_name=object_body_name,
    )
    ids = _binding_ids(model, episode, config)
    joint_limit_diagnostics = _require_episode_joint_limits(model, ids, episode)
    if episode.joint_transform is not None and not bool(
        episode.joint_transform.get("calibration_approved")
    ):
        raise ReplayContractError(
            "physical joint transform is not calibration-approved; exact replay and fitting "
            "remain blocked even when individual rows are range-feasible"
        )
    data = mujoco.MjData(model)
    if current_scene:
        initialize_robot_poses(model, data)
    else:
        mujoco.mj_resetData(model, data)
    object_qpos_address = ids["object_qpos_address"]
    object_dof_address = ids["object_dof_address"]
    if object_qpos_address is not None and object_dof_address is not None:
        object_state = episode.initial_object_state
        data.qpos[object_qpos_address : object_qpos_address + 3] = object_state[
            "position"
        ]
        data.qpos[object_qpos_address + 3 : object_qpos_address + 7] = object_state[
            "quaternion_wxyz"
        ]
        data.qvel[object_dof_address : object_dof_address + 3] = object_state[
            "linear_velocity"
        ]
        data.qvel[object_dof_address + 3 : object_dof_address + 6] = object_state[
            "angular_velocity"
        ]
    data.qpos[ids["qpos_addresses"]] = episode.initial_joint_position
    data.qvel[ids["dof_addresses"]] = episode.initial_joint_velocity
    base_latency = float(config["replay"]["base_latency_seconds"])
    latency_parameter = next(
        (
            parameters[name]
            for name, descriptor in _parameter_descriptors(config).items()
            if descriptor["target"] == "command_latency_seconds"
        ),
        0.0,
    )
    latency_seconds = base_latency + latency_parameter
    if latency_seconds < 0 or not math.isfinite(latency_seconds):
        raise ReplayContractError("total command latency must be finite and non-negative")
    interpolation = str(config["replay"]["command_interpolation"])
    initial_command = _command_at(
        episode,
        0.0,
        latency_seconds=latency_seconds,
        interpolation=interpolation,
    )
    initial_applied = _require_exact_control(
        model, ids["actuator_ids"], initial_command
    )
    data.ctrl[ids["actuator_ids"]] = initial_applied
    mujoco.mj_forward(model, data)
    native_times: list[float] = [float(data.time)]
    native_rows: list[dict[str, Any]] = [
        _simulation_observables(model, data, ids)
    ]
    native_requested_controls: list[np.ndarray] = [initial_command.copy()]
    native_applied_controls: list[np.ndarray] = [initial_applied.copy()]
    maximum_steps = int(math.ceil(episode.duration_seconds / model.opt.timestep)) + 2
    for _ in range(maximum_steps):
        if data.time + np.finfo(np.float64).eps >= episode.duration_seconds:
            break
        command = _command_at(
            episode,
            float(data.time),
            latency_seconds=latency_seconds,
            interpolation=interpolation,
        )
        applied = _require_exact_control(model, ids["actuator_ids"], command)
        data.ctrl[ids["actuator_ids"]] = applied
        mujoco.mj_step(model, data)
        native_times.append(float(data.time))
        native_rows.append(_simulation_observables(model, data, ids))
        native_requested_controls.append(command.copy())
        native_applied_controls.append(applied.copy())
    if native_times[-1] + 1e-12 < episode.duration_seconds:
        raise ReplayContractError("bounded replay did not reach the final timestamp")
    native_time_array = np.asarray(native_times, dtype=np.float64)
    simulated: dict[str, np.ndarray] = {}
    for observable, metadata in OBSERVABLE_METADATA.items():
        field = str(metadata["field"])
        values = [row.get(field) for row in native_rows]
        if any(value is None for value in values):
            continue
        if metadata["alignment"] == "discrete":
            simulated[observable] = _align_discrete(
                native_time_array, values, episode.timestamps
            ).astype(bool)
        else:
            simulated[observable] = _align_continuous(
                native_time_array,
                values,
                episode.timestamps,
                semantic=str(metadata["semantic"]),
            )
    requested_controls = _align_discrete(
        native_time_array,
        native_requested_controls,
        episode.timestamps,
    ).astype(np.float64)
    applied_controls = _align_discrete(
        native_time_array,
        native_applied_controls,
        episode.timestamps,
    )
    applied_controls = applied_controls.astype(np.float64)
    synchronized_rows = _synchronized_rows(
        episode,
        simulated,
        requested_controls=requested_controls,
        applied_controls=applied_controls,
    )
    return {
        "episode": episode,
        "parameters": parameters,
        "timing": {
            "model_timestep_seconds": float(model.opt.timestep),
            "command_interpolation": interpolation,
            "latency_seconds": latency_seconds,
            "latency_semantics": config["replay"]["latency_semantics"],
            "continuous_alignment": config["replay"]["continuous_alignment"],
            "discrete_alignment": config["replay"]["discrete_alignment"],
            "native_sample_count": len(native_times),
        },
        "simulated": simulated,
        "control_diagnostics": {
            "exact_command_replay": True,
            "requested_equals_applied": True,
            "clipping_performed": False,
            "clipped_row_count": 0,
            "clipped_joint_value_count": 0,
            "maximum_requested_applied_delta": 0.0,
            "per_joint_clipped_row_count": {
                name: 0 for name in episode.joint_names
            },
            "joint_limit_validation": joint_limit_diagnostics,
        },
        "synchronized_rows": synchronized_rows,
    }


def _synchronized_rows(
    episode: RecordedEpisode,
    simulated: Mapping[str, np.ndarray],
    *,
    requested_controls: np.ndarray,
    applied_controls: np.ndarray,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    available = episode.available_observables()
    for index, (time_seconds, original_time, command, measured) in enumerate(
        zip(
            episode.timestamps,
            episode.original_timestamps,
            episode.commands,
            episode.measured,
            strict=True,
        )
    ):
        simulated_row: dict[str, Any] = {}
        errors: dict[str, Any] = {}
        availability: dict[str, Any] = {}
        for observable, field in OBSERVABLE_FIELDS.items():
            simulation_value: Any = None
            if observable in simulated:
                value = simulated[observable][index]
                simulation_value = value.tolist() if np.ndim(value) else value.item()
            simulated_row[field] = simulation_value
            if observable in available and simulation_value is not None:
                measured_value = np.asarray(measured[field], dtype=np.float64)
                error = np.asarray(simulation_value, dtype=np.float64) - measured_value
                errors[observable] = error.tolist() if error.ndim else float(error)
                availability[observable] = {"available": True, "reason": None}
            else:
                errors[observable] = None
                reason = episode.unavailable_observables.get(observable)
                if reason is None and observable not in available:
                    reason = f"episode does not contain measured {observable}"
                if simulation_value is None:
                    binding_reason = f"replay model has no configured {observable} output"
                    reason = f"{reason}; {binding_reason}" if reason else binding_reason
                availability[observable] = {"available": False, "reason": reason}
        rows.append(
            {
                "schema_version": SYNCHRONIZED_ROW_SCHEMA,
                "episode_id": episode.episode_id,
                "sample_index": index,
                "timestamp_seconds": float(time_seconds),
                "source_timestamp_seconds": float(original_time),
                "command_joint_position": command.astype(float).tolist(),
                "requested_control_joint_position": requested_controls[index]
                .astype(float)
                .tolist(),
                "applied_control_joint_position": applied_controls[index]
                .astype(float)
                .tolist(),
                "control_clipped": False,
                "measured": measured,
                "simulated": simulated_row,
                "sim_minus_measured": errors,
                "observable_availability": availability,
            }
        )
    return rows


def huber(values: np.ndarray, delta: float) -> np.ndarray:
    if not math.isfinite(delta) or delta <= 0:
        raise ReplayContractError("Huber delta must be finite and positive")
    absolute = np.abs(values)
    return np.where(
        absolute <= delta,
        0.5 * np.square(values),
        delta * (absolute - 0.5 * delta),
    )


def _quaternion_angle_error(
    simulated: np.ndarray,
    measured: np.ndarray,
) -> np.ndarray:
    simulated_norm = simulated / np.maximum(
        np.linalg.norm(simulated, axis=1, keepdims=True),
        np.finfo(np.float64).eps,
    )
    measured_norm = measured / np.maximum(
        np.linalg.norm(measured, axis=1, keepdims=True),
        np.finfo(np.float64).eps,
    )
    dots = np.abs(np.sum(simulated_norm * measured_norm, axis=1))
    return 2.0 * np.arccos(np.clip(dots, -1.0, 1.0))


def _continuous_metric(
    residual: np.ndarray,
    *,
    delta: float,
) -> dict[str, Any]:
    flattened = residual.reshape(-1)
    result: dict[str, Any] = {
        "available": True,
        "scalar_count": int(flattened.size),
        "rmse": float(np.sqrt(np.mean(np.square(flattened)))),
        "maximum_absolute_error": float(np.max(np.abs(flattened))),
        "mean_huber_loss": float(np.mean(huber(flattened, delta))),
    }
    if residual.ndim == 2:
        result["rmse_per_dimension"] = np.sqrt(
            np.mean(np.square(residual), axis=0)
        ).tolist()
        result["maximum_absolute_error_per_dimension"] = np.max(
            np.abs(residual), axis=0
        ).tolist()
        result["final_error"] = residual[-1].tolist()
        result["final_error_norm"] = float(np.linalg.norm(residual[-1]))
    else:
        result["final_error"] = float(residual[-1])
        result["final_absolute_error"] = float(abs(residual[-1]))
    return result


def calculate_metrics(
    replay: Mapping[str, Any],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    episode: RecordedEpisode = replay["episode"]
    simulated: Mapping[str, np.ndarray] = replay["simulated"]
    loss_config = config["loss"]
    weights = loss_config["weights"]
    deltas = loss_config["huber_delta"]
    metrics: dict[str, Any] = {}
    weighted_loss = 0.0
    weighted_observables: list[str] = []
    residuals = replay_residual_blocks(replay, config)
    for observable in OBSERVABLE_FIELDS:
        measured = episode.measured_array(observable)
        simulation = simulated.get(observable)
        if measured is None or simulation is None:
            reason = episode.unavailable_observables.get(observable)
            if measured is None and reason is None:
                reason = f"episode does not contain measured {observable}"
            if simulation is None:
                suffix = f"replay model has no configured {observable} output"
                reason = f"{reason}; {suffix}" if reason else suffix
            metrics[observable] = {"available": False, "reason": reason}
            continue
        if observable in {"end_effector_orientation", "pawn_orientation"}:
            error = _quaternion_angle_error(simulation, measured)
        else:
            error = simulation.astype(np.float64) - measured.astype(np.float64)
        metric = _continuous_metric(error, delta=float(deltas[observable]))
        if observable == "contact_active":
            predicted = simulation.astype(bool)
            truth = measured.astype(bool)
            true_positive = int(np.sum(predicted & truth))
            false_positive = int(np.sum(predicted & ~truth))
            false_negative = int(np.sum(~predicted & truth))
            true_negative = int(np.sum(~predicted & ~truth))
            precision = true_positive / max(1, true_positive + false_positive)
            recall = true_positive / max(1, true_positive + false_negative)
            metric.update(
                {
                    "true_positive": true_positive,
                    "false_positive": false_positive,
                    "false_negative": false_negative,
                    "true_negative": true_negative,
                    "precision": precision,
                    "recall": recall,
                    "f1": 2.0 * precision * recall / max(precision + recall, 1e-15),
                    "accuracy": float(np.mean(predicted == truth)),
                }
            )
        metrics[observable] = metric
        weight = float(weights.get(observable, 0.0))
        if weight > 0:
            weighted_loss += weight * metric["mean_huber_loss"]
            weighted_observables.append(observable)
    metrics["aggregate"] = {
        "loss_kind": "huber",
        "weighted_mean_huber_loss": weighted_loss,
        "weighted_observables": weighted_observables,
        "residual_scalar_count": int(
            sum(block.size for block in residuals.values())
        ),
    }
    metrics["final_pose"] = {
        "joint": (
            {
                "available": True,
                "error_norm": metrics["joint_position"]["final_error_norm"],
            }
            if metrics["joint_position"]["available"]
            else metrics["joint_position"]
        ),
        "end_effector_position": (
            {
                "available": True,
                "translation_error_m": metrics["end_effector_position"][
                    "final_error_norm"
                ],
            }
            if metrics["end_effector_position"]["available"]
            else metrics["end_effector_position"]
        ),
        "end_effector_orientation": (
            {
                "available": True,
                "angular_error_rad": abs(
                    metrics["end_effector_orientation"]["final_error"]
                ),
            }
            if metrics["end_effector_orientation"]["available"]
            else metrics["end_effector_orientation"]
        ),
        "pawn_position": (
            {
                "available": True,
                "translation_error_m": metrics["pawn_position"][
                    "final_error_norm"
                ],
            }
            if metrics["pawn_position"]["available"]
            else metrics["pawn_position"]
        ),
        "pawn_orientation": (
            {
                "available": True,
                "angular_error_rad": abs(
                    metrics["pawn_orientation"]["final_error"]
                ),
            }
            if metrics["pawn_orientation"]["available"]
            else metrics["pawn_orientation"]
        ),
    }
    return metrics


def replay_residual_blocks(
    replay: Mapping[str, Any],
    config: Mapping[str, Any],
    *,
    allowed_observables: set[str] | None = None,
) -> dict[str, np.ndarray]:
    """Return weighted pseudo-residuals whose squares reproduce Huber loss."""

    episode: RecordedEpisode = replay["episode"]
    simulated: Mapping[str, np.ndarray] = replay["simulated"]
    weights = config["loss"]["weights"]
    deltas = config["loss"]["huber_delta"]
    result: dict[str, np.ndarray] = {}
    for observable in OBSERVABLE_FIELDS:
        if allowed_observables is not None and observable not in allowed_observables:
            continue
        weight = float(weights.get(observable, 0.0))
        measured = episode.measured_array(observable)
        simulation = simulated.get(observable)
        if weight <= 0 or measured is None or simulation is None:
            continue
        if observable in {"end_effector_orientation", "pawn_orientation"}:
            raw = _quaternion_angle_error(simulation, measured)
        else:
            raw = simulation.astype(np.float64) - measured.astype(np.float64)
        flattened = raw.reshape(-1)
        robust = huber(flattened, float(deltas[observable]))
        pseudo = np.sign(flattened) * np.sqrt(2.0 * robust)
        result[observable] = pseudo * math.sqrt(weight / max(1, pseudo.size))
    return result


def write_replay_receipt(
    replay: Mapping[str, Any],
    config: Mapping[str, Any],
    output_directory: Path,
) -> dict[str, Any]:
    output_directory = output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    synchronized_path = output_directory / "synchronized.jsonl"
    with synchronized_path.open("w", encoding="utf-8") as handle:
        for row in replay["synchronized_rows"]:
            handle.write(json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n")
    metrics = calculate_metrics(replay, config)
    episode: RecordedEpisode = replay["episode"]
    availability = {
        name: (
            {"available": True, "reason": None}
            if metrics[name]["available"]
            else {"available": False, "reason": metrics[name]["reason"]}
        )
        for name in OBSERVABLE_FIELDS
    }
    receipt = {
        "schema_version": REPLAY_RECEIPT_SCHEMA,
        "episode_id": episode.episode_id,
        "source": {
            "identity": portable_content_identity(
                episode.source_path, episode.source_sha256
            ),
            "schema_version": episode.source_schema_version,
            "proof_class": episode.proof_class,
            "proof_class_category": episode.proof_class_category,
            "provenance": episode.source_provenance,
            "full_physical_provenance_bound": bool(
                episode.proof_class_category != "physical_read_only"
                or episode.source_provenance.get("chain_complete")
            ),
        },
        "config": {
            "config_id": config["config_id"],
            "schema_version": config["schema_version"],
            "sha256": config.get("_config_sha256"),
            "identity": (
                portable_content_identity(
                    Path(str(config["_config_path"])),
                    str(config["_config_sha256"]),
                )
                if config.get("_config_path") and config.get("_config_sha256")
                else {"kind": "embedded_runtime_config"}
            ),
        },
        "initial_object_state": episode.initial_object_state,
        "joint_transform": episode.joint_transform,
        "parameters": replay["parameters"],
        "timing": replay["timing"],
        "control_diagnostics": replay["control_diagnostics"],
        "sample_count": int(episode.timestamps.size),
        "duration_seconds": episode.duration_seconds,
        "observable_availability": availability,
        "metrics": metrics,
        "synchronized_table": {
            "path": synchronized_path.name,
            "sha256": sha256_file(synchronized_path),
            "schema_version": SYNCHRONIZED_ROW_SCHEMA,
            "row_count": len(replay["synchronized_rows"]),
        },
        "proof": {
            "proof_class": "replay",
            "fixture": episode.proof_class_category == "fixture",
            "synthetic": episode.proof_class_category == "synthetic",
            "simulation": True,
            "physical_read_only_input": (
                episode.proof_class_category == "physical_read_only"
            ),
            "physical_task_verified": False,
            "learned_policy_verified": False,
            "training_performed": False,
            "gateway_or_motion_authority": False,
        },
        "created_at": datetime.now(UTC).isoformat(),
    }
    receipt_path = output_directory / "replay_receipt.json"
    _atomic_json(receipt_path, receipt)
    receipt["receipt_path"] = receipt_path.name
    receipt["receipt_sha256"] = sha256_file(receipt_path)
    return receipt


def replay_recorded_episode(
    episode_path: Path,
    *,
    config_path: Path,
    output_directory: Path,
    parameter_values: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    config = load_sysid_config(config_path)
    episode = load_recorded_episode(episode_path, config)
    replay = simulate_and_align(
        episode,
        config,
        parameter_values=parameter_values,
        model_base_directory=config_path.resolve().parent,
    )
    return write_replay_receipt(replay, config, output_directory)
