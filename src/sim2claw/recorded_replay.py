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

from .physical_sim_replay import physical_values_to_sim
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

PROOF_CLASS_CATEGORIES = {
    "fixture",
    "synthetic",
    "simulation",
    "replay",
    "learned_policy",
    "physical_read_only",
    "physical_task",
}

OBSERVABLE_FIELDS = {
    "joint_position": "joint_position",
    "end_effector_position": "end_effector_position_m",
    "end_effector_orientation": "end_effector_quaternion_wxyz",
    "gripper_position": "gripper_position",
    "pawn_position": "pawn_position_m",
    "pawn_orientation": "pawn_quaternion_wxyz",
    "contact_active": "contact_active",
    "contact_force": "contact_force_n",
}


class ReplayContractError(ValueError):
    """A replay input would require guessing, repair, or authority widening."""


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
    unavailable_observables: Mapping[str, str]
    source_path: Path
    source_sha256: str
    source_schema_version: str

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
        unavailable_observables=dict(unavailable),
        source_path=path,
        source_sha256=sha256_file(path),
        source_schema_version=EPISODE_SCHEMA,
    )
    available = episode.available_observables()
    conflict = available.intersection(unavailable)
    if conflict:
        raise ReplayContractError(
            f"observables cannot be both present and unavailable: {sorted(conflict)}"
        )
    return episode


def _load_physical_recording(
    directory: Path,
    config: Mapping[str, Any],
) -> RecordedEpisode:
    receipt_path = directory / "recording_receipt.json"
    samples_path = directory / "samples.jsonl"
    if not receipt_path.is_file() or not samples_path.is_file():
        raise ReplayContractError(
            "physical recording requires recording_receipt.json and samples.jsonl"
        )
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("mode") != "physical_follower":
        raise ReplayContractError("recording is not a physical-follower command trace")
    samples_sha256 = sha256_file(samples_path)
    if samples_sha256 != receipt.get("samples_sha256"):
        raise ReplayContractError("physical recording samples do not match receipt")
    samples = [
        json.loads(line)
        for line in samples_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not samples:
        raise ReplayContractError("physical recording is empty")
    expected_joint_names = tuple(config["bindings"]["joint_names"])
    if expected_joint_names != tuple(f"left_{name}" for name in ROBOT_JOINTS):
        raise ReplayContractError(
            "physical recording adapter only supports the current left SO-101 binding"
        )
    model = build_scene_spec(piece_layout=CURRENT_TASK_PIECE_LAYOUT).compile()
    gripper_actuator = model.actuator("left_gripper").id
    gripper_bounds = model.actuator_ctrlrange[gripper_actuator]
    commands: list[np.ndarray] = []
    measured: list[dict[str, Any]] = []
    for index, sample in enumerate(samples):
        schema = sample.get("schema_version")
        if schema not in {None, PHYSICAL_SAMPLE_SCHEMA}:
            raise ReplayContractError(
                f"physical sample {index} uses unsupported schema {schema}"
            )
        command = physical_values_to_sim(
            sample.get("follower_command_degrees"), gripper_bounds
        )
        actual = physical_values_to_sim(
            sample.get("follower_actual_position_degrees"), gripper_bounds
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
    return RecordedEpisode(
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
        unavailable_observables=unavailable,
        source_path=samples_path,
        source_sha256=samples_sha256,
        source_schema_version=PHYSICAL_SAMPLE_SCHEMA,
    )


def load_recorded_episode(
    path: Path,
    config: Mapping[str, Any],
) -> RecordedEpisode:
    path = path.resolve()
    validate_sysid_config(config)
    if path.is_dir():
        return _load_physical_recording(path, config)
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
) -> None:
    bindings = config["bindings"]
    joint_names = tuple(bindings["joint_names"])
    actuator_names = tuple(bindings["actuator_names"])
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
            pawn_body = bindings.get("pawn_body")
            if pawn_body:
                body_id = mujoco.mj_name2id(
                    model, mujoco.mjtObj.mjOBJ_BODY, str(pawn_body)
                )
                if body_id < 0:
                    raise ReplayContractError(f"model is missing pawn body {pawn_body}")
                model.body_mass[body_id] *= value
            elif not math.isclose(value, float(descriptor["nominal"])):
                raise ReplayContractError(
                    f"parameter {name} requires a configured pawn_body binding"
                )
        elif target == "pawn_friction_scale":
            pawn_body = bindings.get("pawn_body")
            if pawn_body:
                body_ids = _body_subtree_ids(model, [str(pawn_body)])
                for geom_id in range(model.ngeom):
                    if int(model.geom_bodyid[geom_id]) in body_ids:
                        model.geom_friction[geom_id] *= value
            elif not math.isclose(value, float(descriptor["nominal"])):
                raise ReplayContractError(
                    f"parameter {name} requires a configured pawn_body binding"
                )
        elif target == "command_latency_seconds":
            continue
        else:
            raise ReplayContractError(f"unsupported parameter target: {target}")


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
    if bindings.get("pawn_body"):
        candidate = mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_BODY, str(bindings["pawn_body"])
        )
        if candidate < 0:
            raise ReplayContractError(
                f"model is missing pawn body {bindings['pawn_body']}"
            )
        pawn_body_id = candidate
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
            contact_body_sets = (
                _body_subtree_ids(model, contact_groups[0]),
                _body_subtree_ids(model, contact_groups[1]),
            )
    return {
        "joint_ids": joint_ids,
        "qpos_addresses": np.asarray(qpos_addresses, dtype=np.int64),
        "dof_addresses": np.asarray(dof_addresses, dtype=np.int64),
        "actuator_ids": np.asarray(actuator_ids, dtype=np.int64),
        "site_id": site_id,
        "gripper_index": gripper_index,
        "pawn_body_id": pawn_body_id,
        "contact_body_sets": contact_body_sets,
    }


def _clip_controls(
    model: mujoco.MjModel,
    actuator_ids: np.ndarray,
    command: np.ndarray,
) -> np.ndarray:
    result = command.copy()
    for local_index, actuator_id in enumerate(actuator_ids):
        if bool(model.actuator_ctrllimited[actuator_id]):
            low, high = model.actuator_ctrlrange[actuator_id]
            result[local_index] = np.clip(result[local_index], low, high)
    return result


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
) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    if array.ndim == 1:
        return np.interp(target_times, native_times, array)
    if array.shape[1] == 4:
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
    if array.shape[1] == 4:
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
    _apply_parameters(model, config, parameters)
    ids = _binding_ids(model, episode, config)
    data = mujoco.MjData(model)
    if current_scene:
        initialize_robot_poses(model, data)
    else:
        mujoco.mj_resetData(model, data)
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
    data.ctrl[ids["actuator_ids"]] = _clip_controls(
        model, ids["actuator_ids"], initial_command
    )
    mujoco.mj_forward(model, data)
    native_times: list[float] = [float(data.time)]
    native_rows: list[dict[str, Any]] = [
        _simulation_observables(model, data, ids)
    ]
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
        data.ctrl[ids["actuator_ids"]] = _clip_controls(
            model, ids["actuator_ids"], command
        )
        mujoco.mj_step(model, data)
        native_times.append(float(data.time))
        native_rows.append(_simulation_observables(model, data, ids))
    if native_times[-1] + 1e-12 < episode.duration_seconds:
        raise ReplayContractError("bounded replay did not reach the final timestamp")
    native_time_array = np.asarray(native_times, dtype=np.float64)
    simulated: dict[str, np.ndarray] = {}
    for observable, field in OBSERVABLE_FIELDS.items():
        values = [row.get(field) for row in native_rows]
        if any(value is None for value in values):
            continue
        if observable == "contact_active":
            simulated[observable] = _align_discrete(
                native_time_array, values, episode.timestamps
            ).astype(bool)
        else:
            simulated[observable] = _align_continuous(
                native_time_array, values, episode.timestamps
            )
    synchronized_rows = _synchronized_rows(episode, simulated)
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
        "synchronized_rows": synchronized_rows,
    }


def _synchronized_rows(
    episode: RecordedEpisode,
    simulated: Mapping[str, np.ndarray],
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
            "path": str(episode.source_path),
            "sha256": episode.source_sha256,
            "schema_version": episode.source_schema_version,
            "proof_class": episode.proof_class,
            "proof_class_category": episode.proof_class_category,
        },
        "config": {
            "config_id": config["config_id"],
            "schema_version": config["schema_version"],
            "path": config.get("_config_path"),
            "sha256": config.get("_config_sha256"),
        },
        "parameters": replay["parameters"],
        "timing": replay["timing"],
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
    receipt["receipt_path"] = str(receipt_path)
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
