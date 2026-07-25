"""Immutable P15 twin-candidate composition and action-frozen canary compilation."""

from __future__ import annotations

import base64
import copy
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from .recorded_replay import (
    RecordedEpisode,
    canonical_json_sha256,
    load_sysid_config,
    sha256_file,
    simulate_and_align,
    validate_parameter_values,
)
from .replay_eligibility import (
    ACTION_HASH_ENCODING,
    EXPECTED_UNITS,
    MANIFEST_SCHEMA,
    MODIFICATION_FIELDS,
    action_sha256,
    audit_exact_replay_manifest,
)
from .scene import ROBOT_JOINTS
from .system_identification import TIMING_ADMISSION_SCHEMA
from .workcell_registration import BOARD_FIT_SCHEMA, TRANSFORM_SCHEMA


CANDIDATE_SCHEMA = "sim2claw.geometry_timing_twin_candidate.v1"
CANARY_INPUT_SCHEMA = "sim2claw.zero_contact_canary_input.v1"
CANARY_SCHEMA = "sim2claw.zero_contact_canary_bundle.v1"
SUPPORTED_TIMING_TARGETS = {
    "command_latency_seconds": "second",
    "actuator_gain_scale": "dimensionless_scale",
    "joint_damping_scale": "dimensionless_scale",
}
CANARY_SAMPLE_HZ = 20
CANARY_INITIAL_HOLD_SAMPLES = 5
CANARY_EXCURSION_RADIANS = math.radians(1.0)
CANARY_MAX_VELOCITY_RADIANS_S = 0.05
CANARY_MAX_ACCELERATION_RADIANS_S2 = 0.12
CANARY_LIMIT_MARGIN_RADIANS = math.radians(0.5)


class TwinCandidateError(RuntimeError):
    """P15 input lineage or representability failed closed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise TwinCandidateError(message)


def _is_sha256(value: Any) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(character in "0123456789abcdef" for character in text)


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise TwinCandidateError(f"could not load {label}: {error}") from error
    _require(isinstance(value, dict), f"{label} must be an object")
    return value


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")


def _write_once(path: Path, value: Mapping[str, Any]) -> None:
    data = _json_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    _require(not path.exists(), f"refusing to overwrite existing output: {path}")
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def _rigid_transform(value: Any) -> bool:
    try:
        matrix = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError):
        return False
    if matrix.shape != (4, 4) or not np.all(np.isfinite(matrix)):
        return False
    rotation = matrix[:3, :3]
    return bool(
        np.allclose(matrix[3], [0.0, 0.0, 0.0, 1.0], atol=1e-9)
        and np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-6)
        and math.isclose(float(np.linalg.det(rotation)), 1.0, abs_tol=1e-6)
    )


def _validate_p13(
    transform: Mapping[str, Any],
    board_fit: Mapping[str, Any],
    *,
    synthetic_fixture_mode: bool,
) -> dict[str, Any]:
    _require(transform.get("schema_version") == TRANSFORM_SCHEMA, "P13 transform schema changed")
    _require(board_fit.get("schema_version") == BOARD_FIT_SCHEMA, "P13 board-fit schema changed")
    for label, value in (("transform", transform), ("board fit", board_fit)):
        _require(value.get("evaluator_owned") is True, f"P13 {label} is not evaluator-owned")
        _require(value.get("self_scored") is False, f"P13 {label} is self-scored")
    expected_synthetic = bool(synthetic_fixture_mode)
    _require(
        transform.get("synthetic") is expected_synthetic,
        "P13 transform synthetic proof class does not match fixture mode",
    )
    board_synthetic = board_fit.get("synthetic", False)
    _require(
        board_synthetic is expected_synthetic,
        "P13 board-fit synthetic proof class does not match fixture mode",
    )
    _require(_rigid_transform(transform.get("transform_4x4")), "P13 transform is not rigid")
    convention = transform.get("transform_convention")
    _require(
        isinstance(convention, Mapping)
        and convention.get("matrix_direction") == "workcell_from_camera"
        and convention.get("camera_axes") == "opencv_x_right_y_down_z_forward"
        and convention.get("composition")
        == "workcell_from_board @ inverse(camera_from_board)",
        "P13 transform convention changed",
    )
    _require(
        isinstance(transform.get("camera_id"), str)
        and bool(transform["camera_id"])
        and isinstance(transform.get("workspace_pose_id"), str)
        and bool(transform["workspace_pose_id"]),
        "P13 camera/workspace identity is missing",
    )
    _require(
        board_fit.get("evaluation_method") == "leave_one_out"
        and board_fit.get("uncertainty_propagated") is True,
        "P13 board fit is not held-out leave-one-out evidence",
    )
    thresholds = transform.get("thresholds")
    _require(isinstance(thresholds, Mapping), "P13 thresholds are missing")
    comparisons = (
        ("board_rms_m", "maximum_leave_one_out_board_rms_m"),
        ("max_annotator_disagreement_m", "maximum_annotator_disagreement_m"),
        (
            "leave_one_out_reprojection_rms_px",
            "maximum_leave_one_out_reprojection_rms_px",
        ),
    )
    for measured, maximum in comparisons:
        try:
            passed = float(board_fit[measured]) <= float(thresholds[maximum])
        except (KeyError, TypeError, ValueError) as error:
            raise TwinCandidateError(f"P13 board-fit field is invalid: {measured}") from error
        _require(passed, f"P13 board-fit gate failed: {measured}")
    _require(
        board_fit.get("assignment_digest") == transform.get("assignment_digest")
        and _is_sha256(transform.get("assignment_digest")),
        "P13 board-fit assignment lineage drifted",
    )
    transform_hashes = transform.get("input_hashes")
    _require(isinstance(transform_hashes, Mapping), "P13 input hashes are missing")
    _require(
        transform_hashes.get("correspondences_digest")
        == board_fit.get("correspondences_digest")
        and all(_is_sha256(value) for value in transform_hashes.values()),
        "P13 input hash lineage drifted",
    )
    _require(
        transform.get("evaluator_identity") == board_fit.get("evaluator_identity"),
        "P13 evaluator identity drifted",
    )
    return {
        "camera_id": transform["camera_id"],
        "workspace_pose_id": transform["workspace_pose_id"],
        "board_pose_id": transform.get("board_pose_id"),
    }


def _family_digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            {key: item for key, item in value.items() if key != "digest"},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def _validate_p9(
    receipt: Mapping[str, Any],
    baseline: Mapping[str, Any],
    *,
    baseline_sha256: str,
    synthetic_fixture_mode: bool,
) -> dict[str, Any]:
    _require(
        receipt.get("schema_version") == TIMING_ADMISSION_SCHEMA,
        "P9 independent admission schema changed",
    )
    _require(receipt.get("evaluator_owned") is True, "P9 is not evaluator-owned")
    _require(receipt.get("self_scored") is False, "P9 is self-scored")
    expected_synthetic = bool(synthetic_fixture_mode)
    _require(
        receipt.get("synthetic") is expected_synthetic,
        "P9 synthetic proof class does not match fixture mode",
    )
    if synthetic_fixture_mode:
        _require(
            receipt.get("evaluator_admission") is False
            and receipt.get("physical_authority") is False,
            "synthetic P9 fixture cannot grant authority",
        )
    else:
        _require(
            receipt.get("status") == "admitted_configuration_input"
            and receipt.get("evaluator_admission") is True,
            "P9 independent held-out admission did not pass",
        )
    _require(
        receipt.get("parameters_promoted") is False
        and receipt.get("physical_authority") is False,
        "P9 widened promotion or physical authority",
    )
    identity = receipt.get("identity")
    _require(
        isinstance(identity, Mapping)
        and isinstance(identity.get("robot"), Mapping)
        and isinstance(identity.get("workspace_pose_id"), str)
        and bool(identity["workspace_pose_id"]),
        "P9 robot/workspace identity is missing",
    )
    robot = identity["robot"]
    _require(
        all(
            str(robot.get(field) or "").strip()
            for field in ("robot_id", "follower_port", "gateway_schema")
        )
        and _is_sha256(robot.get("follower_calibration_sha256")),
        "P9 robot identity is incomplete",
    )
    family = receipt.get("candidate_family")
    _require(isinstance(family, Mapping), "P9 candidate family is missing")
    _require(family.get("digest") == _family_digest(family), "P9 candidate family digest drifted")
    timing_stages = [
        stage for stage in baseline["parameter_stages"] if stage["name"] == "timing_control"
    ]
    _require(len(timing_stages) == 1, "baseline timing stage is ambiguous")
    baseline_parameters = timing_stages[0]["parameters"]
    _require(
        family.get("parameters") == baseline_parameters,
        "P9 candidate family ordering drifted from baseline",
    )
    selected = receipt.get("selected_parameters")
    names = [parameter["name"] for parameter in baseline_parameters]
    _require(
        isinstance(selected, Mapping) and set(selected) == set(names),
        "P9 selected parameter membership drifted",
    )
    _require(
        all(parameter["target"] in SUPPORTED_TIMING_TARGETS for parameter in baseline_parameters),
        "P9 contains an unsupported admitted runtime field",
    )
    validate_parameter_values(baseline, selected)
    split = receipt.get("frozen_split")
    _require(
        isinstance(split, Mapping)
        and split.get("unit") == "whole_episode"
        and split.get("counts", {}).get("train", 0) > 0
        and split.get("counts", {}).get("validation", 0) > 0
        and split.get("counts", {}).get("held_out", 0) > 0,
        "P9 grouped split is missing or empty",
    )
    split_payload = {key: item for key, item in split.items() if key != "digest"}
    _require(
        split.get("digest") == canonical_json_sha256(split_payload),
        "P9 grouped split digest drifted",
    )
    action_identity = receipt.get("action_identity")
    _require(
        isinstance(action_identity, Mapping)
        and action_identity.get("byte_identical") is True
        and isinstance(action_identity.get("sha256_by_episode"), Mapping)
        and set(action_identity["sha256_by_episode"]) == set(split["assignments"])
        and all(_is_sha256(value) for value in action_identity["sha256_by_episode"].values()),
        "P9 sealed action lineage is invalid",
    )
    held_out = receipt.get("held_out_replay")
    _require(
        isinstance(held_out, Mapping)
        and held_out.get("fit_or_selection_performed") is False
        and held_out.get("improvement_gate", {}).get("passed") is True,
        "P9 independent held-out replay gate failed",
    )
    for source in ("source_fit", "source_cohort", "source_config"):
        _require(
            isinstance(receipt.get(source), Mapping)
            and _is_sha256(receipt[source].get("sha256")),
            f"P9 {source} hash is missing",
        )
    _require(
        receipt["source_config"]["sha256"] == baseline_sha256
        and receipt["source_config"].get("config_id") == baseline["config_id"],
        "P9 source config hash or identity drifted from baseline",
    )
    return copy.deepcopy(dict(selected))


def _validate_canary_input(
    value: Mapping[str, Any],
    *,
    identity: Mapping[str, Any],
    synthetic_fixture_mode: bool,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    _require(value.get("schema_version") == CANARY_INPUT_SCHEMA, "canary input schema changed")
    _require(
        value.get("synthetic") is bool(synthetic_fixture_mode),
        "canary input synthetic proof class does not match fixture mode",
    )
    _require(value.get("identity") == identity, "canary robot/workspace/camera identity drifted")
    initial = value.get("initial_state")
    limits = value.get("joint_limits")
    _require(
        isinstance(initial, Mapping) and isinstance(limits, Mapping),
        "canary state or limits missing",
    )
    _require(
        initial.get("joint_position_source") == "measured"
        and initial.get("joint_velocity_source") == "measured"
        and str(initial.get("measurement_id") or "").strip()
        and _is_sha256(initial.get("measurement_sha256")),
        "canary initial state is not hash-bound measured evidence",
    )
    _require(
        limits.get("unit") == "radian"
        and str(limits.get("source_id") or "").strip()
        and _is_sha256(limits.get("source_sha256")),
        "canary joint limits are not hash-bound radians",
    )
    try:
        start = np.asarray(initial["joint_position"], dtype=np.float64)
        velocity = np.asarray(initial["joint_velocity"], dtype=np.float64)
        lower = np.asarray(limits["minimum"], dtype=np.float64)
        upper = np.asarray(limits["maximum"], dtype=np.float64)
    except (KeyError, TypeError, ValueError) as error:
        raise TwinCandidateError("canary state/limit vectors are invalid") from error
    _require(
        all(vector.shape == (len(ROBOT_JOINTS),) for vector in (start, velocity, lower, upper))
        and all(np.all(np.isfinite(vector)) for vector in (start, velocity, lower, upper)),
        "canary state/limit vectors must be finite six-vectors",
    )
    _require(np.all(lower < upper), "canary joint limits are unordered")
    _require(
        np.max(np.abs(velocity)) <= 0.01,
        "canary initial state is not stationary enough to compile",
    )
    _require(
        np.all(start >= lower + CANARY_LIMIT_MARGIN_RADIANS)
        and np.all(start <= upper - CANARY_LIMIT_MARGIN_RADIANS),
        "canary start lacks conservative joint-limit margin",
    )
    return start, velocity, lower, upper


def _compile_actions(start: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    rows = [start.copy() for _ in range(CANARY_INITIAL_HOLD_SAMPLES)]
    segment_steps = CANARY_SAMPLE_HZ
    for joint_index, direction in ((0, 1.0), (2, -1.0)):
        for step in range(1, segment_steps + 1):
            phase = math.pi * step / segment_steps
            row = start.copy()
            row[joint_index] += (
                direction * CANARY_EXCURSION_RADIANS * 0.5 * (1.0 - math.cos(phase))
            )
            rows.append(row)
        for step in range(1, segment_steps + 1):
            phase = math.pi * step / segment_steps
            row = start.copy()
            row[joint_index] += (
                direction * CANARY_EXCURSION_RADIANS * 0.5 * (1.0 + math.cos(phase))
            )
            rows.append(row)
    actions = np.asarray(rows, dtype=np.float64)
    actions[-1] = start
    timestamps = np.arange(actions.shape[0], dtype=np.float64) / CANARY_SAMPLE_HZ
    return timestamps, actions


def compose_twin_candidate_and_canary(
    *,
    p9_admission_path: Path,
    p13_transform_path: Path,
    p13_board_fit_path: Path,
    baseline_config_path: Path,
    canary_input_path: Path,
    output_directory: Path,
    synthetic_fixture_mode: bool = False,
) -> dict[str, Any]:
    """Compose exactly one immutable candidate and one exact-replay canary bundle."""

    output = output_directory.resolve()
    candidate_path = output / "candidate_manifest.json"
    canary_path = output / "canary_bundle.json"
    _require(
        not candidate_path.exists() and not canary_path.exists(),
        "refusing to overwrite pre-existing P15 output",
    )
    paths = {
        "p9": p9_admission_path.resolve(),
        "p13_transform": p13_transform_path.resolve(),
        "p13_board_fit": p13_board_fit_path.resolve(),
        "baseline": baseline_config_path.resolve(),
        "canary_input": canary_input_path.resolve(),
    }
    before = paths["baseline"].read_bytes()
    baseline_sha256 = sha256_file(paths["baseline"])
    baseline = load_sysid_config(paths["baseline"])
    baseline.pop("_config_path", None)
    baseline.pop("_config_sha256", None)
    p9 = _read_json(paths["p9"], "P9 admission")
    transform = _read_json(paths["p13_transform"], "P13 transform")
    board_fit = _read_json(paths["p13_board_fit"], "P13 board fit")
    canary_input = _read_json(paths["canary_input"], "canary input")
    selected = _validate_p9(
        p9,
        baseline,
        baseline_sha256=baseline_sha256,
        synthetic_fixture_mode=synthetic_fixture_mode,
    )
    p13_identity = _validate_p13(
        transform, board_fit, synthetic_fixture_mode=synthetic_fixture_mode
    )
    _require(
        p9["identity"]["workspace_pose_id"] == p13_identity["workspace_pose_id"],
        "P9/P13 workspace identity drifted",
    )
    identity = {
        "robot": copy.deepcopy(p9["identity"]["robot"]),
        **p13_identity,
    }
    start, initial_velocity, lower, upper = _validate_canary_input(
        canary_input,
        identity=identity,
        synthetic_fixture_mode=synthetic_fixture_mode,
    )

    candidate_config = copy.deepcopy(baseline)
    timing_stage = [
        stage
        for stage in candidate_config["parameter_stages"]
        if stage["name"] == "timing_control"
    ][0]
    applied: list[dict[str, Any]] = []
    for descriptor in timing_stage["parameters"]:
        name = descriptor["name"]
        target = descriptor["target"]
        _require(
            target in SUPPORTED_TIMING_TARGETS,
            f"unsupported admitted runtime field: {target}",
        )
        descriptor["nominal"] = float(selected[name])
        applied.append(
            {
                "source": "P9",
                "field": name,
                "runtime_target": target,
                "value": float(selected[name]),
                "unit": SUPPORTED_TIMING_TARGETS[target],
                "application": "recorded_replay_parameter_nominal",
            }
        )
    validate_parameter_values(candidate_config, selected)
    candidate_config_sha256 = canonical_json_sha256(candidate_config)
    source_hashes = {name: sha256_file(path) for name, path in paths.items()}
    candidate_source_hashes = {
        name: source_hashes[name]
        for name in ("p9", "p13_transform", "p13_board_fit", "baseline")
    }
    candidate_core = {
        "identity": identity,
        "source_hashes": candidate_source_hashes,
        "baseline_sha256": baseline_sha256,
        "candidate_config_sha256": candidate_config_sha256,
        "applied_parameters": applied,
        "unapplied_fields": [
            {
                "source": "P13",
                "field": "transform_4x4",
                "unit": "metre_and_dimensionless_rotation",
                "convention": "workcell_from_camera",
                "reason": "recorded-action MuJoCo runtime has no camera transform field",
            }
        ],
    }
    candidate_digest = canonical_json_sha256(candidate_core)

    timestamps, actions = _compile_actions(start)
    _require(
        np.all(actions >= lower) and np.all(actions <= upper),
        "compiled canary exceeds measured joint limits",
    )
    velocities = np.diff(actions, axis=0) * CANARY_SAMPLE_HZ
    accelerations = np.diff(velocities, axis=0) * CANARY_SAMPLE_HZ
    maximum_velocity = float(np.max(np.abs(velocities)))
    maximum_acceleration = float(np.max(np.abs(accelerations)))
    _require(
        maximum_velocity <= CANARY_MAX_VELOCITY_RADIANS_S + 1e-12,
        "compiled canary exceeds velocity bound",
    )
    _require(
        maximum_acceleration <= CANARY_MAX_ACCELERATION_RADIANS_S2 + 1e-12,
        "compiled canary exceeds acceleration bound",
    )
    _require(
        np.array_equal(actions[0], start)
        and np.array_equal(actions[-1], start),
        "canary does not return exactly to start",
    )
    _require(
        np.array_equal(actions[:, 5], np.full(actions.shape[0], start[5])),
        "canary changes the gripper",
    )
    action_hash = action_sha256(actions)
    action_bytes = np.asarray(actions, dtype="<f8", order="C").tobytes(order="C")

    episode = RecordedEpisode(
        episode_id=f"p15-zero-contact-canary-{candidate_digest[:16]}",
        proof_class=(
            "synthetic_contract_fixture"
            if synthetic_fixture_mode
            else "simulation_replay_canary_physical_unexecuted"
        ),
        proof_class_category="synthetic" if synthetic_fixture_mode else "replay",
        column=None,
        joint_names=tuple(baseline["bindings"]["joint_names"]),
        initial_joint_position=start.copy(),
        initial_joint_position_units=("radian",) * len(ROBOT_JOINTS),
        initial_joint_velocity=initial_velocity.copy(),
        initial_joint_velocity_units=("radian_per_second",) * len(ROBOT_JOINTS),
        timestamps=timestamps,
        original_timestamps=timestamps.copy(),
        commands=actions.copy(),
        measured=tuple({"joint_position": row.tolist()} for row in actions),
        initial_object_state={"status": "unavailable"},
        unavailable_observables={},
        source_path=paths["canary_input"],
        source_sha256=source_hashes["canary_input"],
        source_schema_version=CANARY_INPUT_SCHEMA,
        source_provenance={"chain_complete": True},
        joint_transform=None,
    )
    replay = simulate_and_align(
        episode,
        candidate_config,
        model_base_directory=paths["baseline"].parent,
    )
    consumed_hash = replay["control_diagnostics"]["replay_input_action_sha256"]
    _require(consumed_hash == action_hash, "simulation did not consume the frozen canary bytes")
    contact_observable = replay["simulated"].get("contact_active")
    declared_contacts_clear = (
        bool(not np.any(np.asarray(contact_observable, dtype=np.float64)))
        if contact_observable is not None
        else None
    )

    candidate_manifest = {
        "schema_version": CANDIDATE_SCHEMA,
        "status": "synthetic_fixture_valid" if synthetic_fixture_mode else "configuration_valid",
        "proof_class": "synthetic_fixture" if synthetic_fixture_mode else "configuration_candidate",
        "identity": identity,
        "sources": {
            name: {"sha256": digest}
            for name, digest in candidate_source_hashes.items()
        },
        "baseline": {
            "config_id": baseline["config_id"],
            "sha256": baseline_sha256,
            "immutable": True,
        },
        "candidate_config": candidate_config,
        "candidate_config_sha256": candidate_config_sha256,
        "applied_parameters": applied,
        "unapplied_fields": candidate_core["unapplied_fields"],
        "candidate_digest": candidate_digest,
        "runtime": {
            "consumer": "sim2claw.recorded_replay.simulate_and_align",
            "candidate_consumed": True,
            "numeric_runtime": "cpu_mujoco_fp64",
            "camera_transform_supported": False,
            "zero_contact_observable": contact_observable is not None,
            "p16_runtime_blocker": (
                None
                if contact_observable is not None
                else "recorded_action_sysid_v1 bindings.pawn_body is null, so "
                "simulate_and_align emits no contact_active channel"
            ),
        },
        "evaluator_admission": False,
        "physical_authority": False,
        "claim_limits": [
            "configuration validity and bounded simulation replay only",
            "P13 transform is lineage-bound but unapplied",
            "no physical execution or task authority",
        ],
    }
    canary_bundle = {
        "schema_version": MANIFEST_SCHEMA,
        "canary_schema_version": CANARY_SCHEMA,
        "episode_id": episode.episode_id,
        "proof_class": episode.proof_class,
        "synthetic": bool(synthetic_fixture_mode),
        "evaluator_admission": False,
        "physical_authority": False,
        "identity": identity,
        "candidate_digest": candidate_digest,
        "source_canary_input": {
            "sha256": source_hashes["canary_input"],
            "schema_version": CANARY_INPUT_SCHEMA,
        },
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
            "joint_position": start.tolist(),
            "joint_velocity": initial_velocity.tolist(),
            "joint_position_source": "measured",
            "joint_velocity_source": "measured",
            "measurement_id": canary_input["initial_state"]["measurement_id"],
            "measurement_sha256": canary_input["initial_state"]["measurement_sha256"],
        },
        "timestamps_seconds": timestamps.tolist(),
        "requested_actions": actions.tolist(),
        "applied_actions": actions.tolist(),
        "action_dtype": "float64",
        "requested_action_sha256": action_hash,
        "applied_action_sha256": action_hash,
        "action_semantics": {
            "requested_actions_source": "frozen_action_payload",
            "applied_actions_source": "frozen_action_payload",
            "applied_field_compatibility_meaning": "gateway_sent_command",
            "actuator_applied_or_acknowledged": False,
        },
        "modifications": {field: False for field in MODIFICATION_FIELDS},
        "frozen_action_payload": {
            "encoding": ACTION_HASH_ENCODING,
            "shape": list(actions.shape),
            "sha256": action_hash,
            "base64": base64.b64encode(action_bytes).decode("ascii"),
            "simulation_consumer_sha256": consumed_hash,
            "future_physical_consumer_must_use_same_bytes": True,
        },
        "safety": {
            "intent": "zero_contact",
            "initial_hold_samples": CANARY_INITIAL_HOLD_SAMPLES,
            "sample_hz": CANARY_SAMPLE_HZ,
            "excursion_radians": CANARY_EXCURSION_RADIANS,
            "maximum_velocity_radians_s": maximum_velocity,
            "velocity_bound_radians_s": CANARY_MAX_VELOCITY_RADIANS_S,
            "maximum_acceleration_radians_s2": maximum_acceleration,
            "acceleration_bound_radians_s2": CANARY_MAX_ACCELERATION_RADIANS_S2,
            "joint_limits_source_sha256": canary_input["joint_limits"]["source_sha256"],
            "within_joint_limits": True,
            "return_to_exact_start": True,
            "gripper_unchanged": True,
            "ik_assistance_clipping_suffix_offsets": False,
        },
        "simulation": {
            "executed": True,
            "runtime": "cpu_mujoco_fp64",
            "declared_contact_groups_clear": declared_contacts_clear,
            "zero_contact_verified": declared_contacts_clear is True,
            "contact_observable_available": contact_observable is not None,
            "action_byte_identical": True,
            "physical_execution_admitted": False,
        },
    }
    _require(paths["baseline"].read_bytes() == before, "baseline config mutated during composition")
    _write_once(candidate_path, candidate_manifest)
    _write_once(canary_path, canary_bundle)
    eligibility = audit_exact_replay_manifest(canary_path)
    _require(
        eligibility["exact_replay_eligible"] is True,
        "compiled canary failed existing replay eligibility",
    )
    return {
        "status": candidate_manifest["status"],
        "candidate_manifest_path": str(candidate_path),
        "candidate_manifest_sha256": sha256_file(candidate_path),
        "canary_bundle_path": str(canary_path),
        "canary_bundle_sha256": sha256_file(canary_path),
        "candidate_digest": candidate_digest,
        "action_sha256": action_hash,
        "simulation_action_byte_identical": True,
        "exact_replay_eligible": True,
        "physical_authority": False,
    }
