"""Reviewed, setup-only phase gateway for geometric physical replay.

The geometric task packet remains owned by :mod:`geometric_physical_gateway`.
This module can only move the follower between reviewed setup waypoints.  It
binds every setup phase to the unchanged admitted task action digest, requires
an independently approved physical transform and metric P13 lineage, previews
each phase in simulation, and powers the follower down after exactly one phase.

Later phases cannot be compiled until the preceding phase has a completed,
torque-off execution receipt.  This makes the fresh torque-off hardware read at
each phase boundary the rebase authority instead of assuming that the previous
command was reached.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping

import numpy as np

from .geometric_physical_gateway import (
    GeometricPhysicalGatewayError,
    _excursion_audit,
    _frozen_payload,
    _plan_sha256,
    _rate_audit,
    _read_json,
    _source_actions,
    _validated_candidate,
    _validated_source,
    _write_once,
)
from .physical_canary import (
    CANARY_START_TOLERANCE_DEGREES,
    _anchor_delta,
    _default_gateway,
    _default_preflight,
    _gateway_identity,
    _identity_from_preflight,
    _validate_limits,
)
from .recorded_replay import _compile_model, canonical_json_sha256
from .replay_eligibility import ACTION_HASH_ENCODING, action_sha256
from .scene import ROBOT_JOINTS
from .source_episode import sha256_file


TRANSFER_INPUT_SCHEMA = "sim2claw.geometric_transfer_compile_inputs.v1"
SETUP_PACKET_SCHEMA = "sim2claw.geometric_setup_phase_packet.v1"
SETUP_REVIEW_SCHEMA = "sim2claw.geometric_setup_phase_review.v1"
SETUP_EXECUTION_SCHEMA = "sim2claw.geometric_setup_phase_execution.v1"
SETUP_SIM_ACTION_ENCODING = "little_endian_float64_c_order"
SAMPLE_HZ = 20
PHYSICS_STEPS_PER_ACTION = 10
PREEXISTING_SELF_CONTACT_MAX_PENETRATION_M = 1e-4
CONTACT_NUMERICAL_EPSILON_M = 1e-9
MAX_EGRESS_RESOLUTION_PHYSICS_SUBSTEP = 2


PreviewFunction = Callable[
    [np.ndarray, Path, Mapping[str, Any], Mapping[str, Any]],
    dict[str, Any],
]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GeometricPhysicalGatewayError(message)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_payload(value: Mapping[str, Any], digest_field: str) -> str:
    return canonical_json_sha256(
        {key: item for key, item in value.items() if key != digest_field}
    )


def _load_float64_npy(
    descriptor: Mapping[str, Any],
    *,
    label: str,
) -> np.ndarray:
    try:
        path = Path(str(descriptor["path"])).resolve()
        expected_shape = tuple(int(value) for value in descriptor["shape"])
    except (KeyError, TypeError, ValueError) as error:
        raise GeometricPhysicalGatewayError(
            f"{label} descriptor is malformed"
        ) from error
    _require(
        descriptor.get("dtype") == "float64_little_endian"
        and sha256_file(path) == descriptor.get("npy_sha256"),
        f"{label} file or dtype drifted",
    )
    try:
        values = np.load(path, allow_pickle=False)
    except (OSError, ValueError) as error:
        raise GeometricPhysicalGatewayError(
            f"could not load {label}: {error}"
        ) from error
    values = np.asarray(values, dtype="<f8", order="C")
    _require(
        values.shape == expected_shape
        and values.ndim == 2
        and values.shape[1] == len(ROBOT_JOINTS)
        and np.all(np.isfinite(values))
        and _sha256_bytes(values.tobytes(order="C"))
        == descriptor.get("raw_c_order_sha256"),
        f"{label} shape or exact bytes drifted",
    )
    return values


def _forward_transform(
    physical: np.ndarray,
    transform: Mapping[str, Any],
) -> np.ndarray:
    simulator = np.empty(physical.shape, dtype="<f8")
    entries = list(transform.get("joints") or [])
    _require(
        len(entries) == len(ROBOT_JOINTS),
        "setup physical transform does not contain six joints",
    )
    for index, entry in enumerate(entries):
        simulator[:, index] = (
            physical[:, index]
            * float(entry["sign"])
            * float(entry["scale"])
            + float(entry["zero_offset"])
        )
    return simulator


def _load_transfer_inputs(
    compile_inputs_path: Path,
) -> tuple[
    dict[str, Any],
    Path,
    dict[str, Any],
    list[dict[str, Any]],
    dict[str, Any],
    dict[str, Any],
    Mapping[str, Any],
    np.ndarray,
    np.ndarray,
    np.ndarray,
    list[dict[str, Any]],
]:
    """Revalidate task lineage, promotion gates, and all setup array bytes."""

    compile_inputs_path = compile_inputs_path.resolve()
    inputs = _read_json(compile_inputs_path, "geometric transfer compile inputs")
    _require(
        inputs.get("schema_version") == TRANSFER_INPUT_SCHEMA
        and inputs.get("canonical_payload_sha256")
        == _canonical_payload(inputs, "canonical_payload_sha256"),
        "geometric transfer compile inputs digest changed",
    )
    _require(
        inputs.get("physical_motion_performed") is False
        and inputs.get("physical_authority_created") is False,
        "setup inputs improperly claim prior physical authority",
    )

    task = inputs.get("canonical_task_source") or {}
    admission = inputs.get("strict_admission") or {}
    candidate_descriptor = inputs.get("candidate_manifest") or {}
    episode_directory = Path(str(task.get("episode_directory") or "")).resolve()
    admission_path = Path(str(admission.get("path") or "")).resolve()
    candidate_path = Path(
        str(candidate_descriptor.get("path") or "")
    ).resolve()
    _require(
        task.get("task_actions_copied_into_bundle") is False
        and task.get("task_bytes_owner") == "canonical source samples.jsonl",
        "setup bundle must not own or replace task action bytes",
    )
    _require(
        sha256_file(episode_directory / "recording_receipt.json")
        == task.get("recording_receipt_sha256")
        and sha256_file(episode_directory / "samples.jsonl")
        == task.get("samples_file_sha256")
        and sha256_file(admission_path) == admission.get("file_sha256")
        and sha256_file(candidate_path)
        == candidate_descriptor.get("file_sha256"),
        "setup task, admission, or candidate lineage drifted",
    )

    receipt, rows, verdict, _ = _validated_source(
        episode_directory,
        admission_path,
    )
    # This is intentionally the same validator used by task compilation.  It
    # rejects a provisional transform or missing metric P13 before hardware.
    manifest, config, transform = _validated_candidate(candidate_path, receipt)
    source_actions, _, source_raw = _source_actions(rows)
    task_action_sha256 = _sha256_bytes(source_raw)
    _require(
        task_action_sha256 == task.get("source_action_raw_sha256")
        and verdict.get("strict_success") is True
        and manifest.get("candidate_digest")
        == candidate_descriptor.get("candidate_digest")
        and config["physical_adapter"]["joint_transform_sha256"]
        == candidate_descriptor.get("joint_transform_sha256"),
        "setup bundle differs from its admitted task or approved candidate",
    )

    setup = inputs.get("setup") or {}
    physical = _load_float64_npy(
        setup.get("physical_array") or {},
        label="setup physical action array",
    )
    simulator = _load_float64_npy(
        setup.get("sim_array") or {},
        label="setup simulator action array",
    )
    _require(
        physical.shape == simulator.shape
        and physical.shape[0] == int(setup.get("combined_sample_count", -1))
        and int(setup.get("sample_hz", 0)) == SAMPLE_HZ,
        "setup physical/simulator action shapes or rate differ",
    )
    expected_simulator = _forward_transform(physical, transform)
    _require(
        np.allclose(simulator, expected_simulator, atol=1e-14, rtol=0.0),
        "setup simulator actions differ from the approved physical transform",
    )

    segments = list(setup.get("segments") or [])
    _require(
        len(segments) >= 2,
        "multi-phase setup requires at least two reviewed phases",
    )
    expected_start = 0
    for phase_index, segment in enumerate(segments, start=1):
        start = int(segment.get("combined_start_index", -1))
        stop = int(segment.get("combined_end_index_exclusive", -1))
        sample_count = int(segment.get("sample_count", -1))
        _require(
            segment.get("phase_index") == phase_index
            and start == expected_start
            and stop - start == sample_count
            and sample_count >= 2
            and stop <= len(physical)
            and int(segment.get("sample_hz", 0)) == SAMPLE_HZ,
            f"setup phase {phase_index} boundaries drifted",
        )
        phase_physical = physical[start:stop]
        _require(
            _sha256_bytes(phase_physical.tobytes(order="C"))
            == segment.get("raw_float64_c_order_sha256")
            and np.array_equal(
                phase_physical[0],
                np.asarray(segment.get("origin_physical_units"), dtype="<f8"),
            )
            and np.array_equal(
                phase_physical[-1],
                np.asarray(segment.get("target_physical_units"), dtype="<f8"),
            ),
            f"setup phase {phase_index} exact bytes or endpoints drifted",
        )
        if phase_index > 1:
            previous = segments[phase_index - 2]
            _require(
                np.array_equal(
                    np.asarray(
                        previous.get("target_physical_units"),
                        dtype="<f8",
                    ),
                    phase_physical[0],
                ),
                f"setup phase {phase_index} is not continuous",
            )
        expected_start = stop
    _require(
        expected_start == len(physical),
        "setup phase boundaries do not cover the frozen action array",
    )
    _require(
        np.array_equal(
            simulator[-1].astype("<f4"),
            source_actions[0],
        ),
        "final setup target does not round-trip to exact task action byte zero",
    )
    return (
        inputs,
        episode_directory,
        receipt,
        rows,
        verdict,
        config,
        transform,
        source_actions,
        physical,
        simulator,
        segments,
    )


def _phase_arrays(
    physical: np.ndarray,
    simulator: np.ndarray,
    segments: list[dict[str, Any]],
    phase_index: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    _require(
        isinstance(phase_index, int)
        and not isinstance(phase_index, bool)
        and 1 <= phase_index <= len(segments),
        "setup phase index is outside the reviewed sequence",
    )
    segment = segments[phase_index - 1]
    start = int(segment["combined_start_index"])
    stop = int(segment["combined_end_index_exclusive"])
    phase_physical = physical[start:stop]
    phase_simulator = simulator[start:stop]
    timestamps = np.arange(len(phase_physical), dtype="<f8") / float(SAMPLE_HZ)
    return phase_physical, phase_simulator, timestamps, segment


def _validate_previous_execution(
    previous_execution_path: Path | None,
    *,
    phase_index: int,
    compile_inputs_path: Path,
    task_action_sha256: str,
    expected_origin: np.ndarray,
) -> dict[str, Any] | None:
    if phase_index == 1:
        _require(
            previous_execution_path is None,
            "setup phase one must not claim a previous execution",
        )
        return None
    _require(
        previous_execution_path is not None,
        f"setup phase {phase_index} requires phase {phase_index - 1} receipt",
    )
    path = previous_execution_path.resolve()
    receipt = _read_json(path, "previous setup phase execution")
    _require(
        receipt.get("schema_version") == SETUP_EXECUTION_SCHEMA
        and receipt.get("status") == "completed_setup_phase_torque_off"
        and receipt.get("phase_index") == phase_index - 1
        and receipt.get("compile_inputs_path") == str(compile_inputs_path)
        and receipt.get("task_source_action_sha256") == task_action_sha256
        and receipt.get("physical_follower_torque_enabled") is False
        and receipt.get("stop_before_next_phase") is True
        and np.array_equal(
            np.asarray(receipt.get("phase_target_physical_units"), dtype="<f8"),
            expected_origin,
        ),
        "previous setup phase receipt cannot authorize this rebase",
    )
    return {
        "path": str(path),
        "sha256": sha256_file(path),
        "phase_index": phase_index - 1,
        "physical_follower_torque_enabled": False,
    }


def _validate_preview(
    preview: Mapping[str, Any],
    phase_simulator: np.ndarray,
) -> None:
    raw_sha256 = _sha256_bytes(phase_simulator.tobytes(order="C"))
    contact_mode = preview.get("contact_gate_mode")
    resolving_baseline_valid = (
        contact_mode == "resolving_preexisting_self_contact"
        and preview.get("preexisting_self_contact_only") is True
        and float(
            preview.get("preexisting_contact_max_penetration_m", float("inf"))
        )
        <= PREEXISTING_SELF_CONTACT_MAX_PENETRATION_M
        + CONTACT_NUMERICAL_EPSILON_M
        and preview.get("preexisting_contact_never_worsened") is True
        and preview.get("preexisting_contact_resolved_during_egress") is True
        and int(preview.get("new_contact_pair_count", -1)) == 0
        and int(preview.get("recurrent_contact_pair_count", -1)) == 0
    )
    _require(
        preview.get("passed") is True
        and preview.get("sample_count") == len(phase_simulator)
        and preview.get("exact_setup_sim_action_sha256") == raw_sha256
        and int(preview.get("forbidden_robot_contact_count", -1)) == 0
        and int(preview.get("robot_pawn_contact_count", -1)) == 0,
        "setup phase simulation contact preview rejected or used other bytes",
    )
    _require(
        contact_mode == "strict_zero_contact" or resolving_baseline_valid,
        "setup preview contact mode does not prove zero or resolving baseline contact",
    )


def _classify_contact_snapshots(
    snapshots: list[dict[str, Any]],
    *,
    first_changed_sample_index: int | None,
) -> dict[str, Any]:
    """Admit only a tiny, internal, monotonically resolving origin overlap.

    A literal zero-contact gate is retained whenever the origin is clear.  If
    CAD reports contact at the exact origin, the only exception is the same
    robot/robot pair already present at the initial ``mj_forward``.  It must be
    shallower than 0.1 mm, never deepen, disappear during the first changing
    command, and never recur.  Pawn, environment, new-pair, and worsened
    contacts remain forbidden.
    """

    _require(bool(snapshots), "setup preview produced no contact snapshots")
    baseline_records = list(snapshots[0].get("contacts") or [])
    observed_count = sum(
        len(snapshot.get("contacts") or []) for snapshot in snapshots
    )
    if not baseline_records:
        forbidden_count = observed_count
        return {
            "contact_gate_mode": "strict_zero_contact",
            "observed_robot_contact_count": observed_count,
            "allowed_preexisting_self_contact_observation_count": 0,
            "forbidden_robot_contact_count": forbidden_count,
            "robot_pawn_contact_count": sum(
                int(record.get("touches_pawn") is True)
                for snapshot in snapshots
                for record in snapshot.get("contacts") or []
            ),
            "new_contact_pair_count": forbidden_count,
            "recurrent_contact_pair_count": 0,
            "preexisting_self_contact_only": True,
            "preexisting_contact_max_penetration_m": 0.0,
            "preexisting_contact_never_worsened": True,
            "preexisting_contact_resolved_during_egress": True,
            "passed": forbidden_count == 0,
        }

    baseline_pairs = {
        tuple(str(value) for value in record["pair"])
        for record in baseline_records
    }
    baseline_internal = all(
        record.get("both_robot") is True
        and record.get("touches_pawn") is False
        for record in baseline_records
    )
    baseline_penetration = max(
        max(0.0, -float(record["distance_m"]))
        for record in baseline_records
    )
    baseline_within_cap = (
        baseline_penetration
        <= PREEXISTING_SELF_CONTACT_MAX_PENETRATION_M
        + CONTACT_NUMERICAL_EPSILON_M
    )
    previous_severity = {
        pair: max(
            max(0.0, -float(record["distance_m"]))
            for record in baseline_records
            if tuple(str(value) for value in record["pair"]) == pair
        )
        for pair in baseline_pairs
    }
    resolved_pairs: set[tuple[str, str]] = set()
    new_pairs: set[tuple[str, str]] = set()
    recurrent_pairs: set[tuple[str, str]] = set()
    worsened_pairs: set[tuple[str, str]] = set()
    external_or_pawn_count = 0
    allowed_observations = len(baseline_records)
    last_baseline_sample = int(snapshots[0]["sample_index"])
    last_baseline_substep = int(snapshots[0]["physics_substep"])

    for snapshot in snapshots[1:]:
        records = list(snapshot.get("contacts") or [])
        current: dict[tuple[str, str], float] = {}
        for record in records:
            pair = tuple(str(value) for value in record["pair"])
            severity = max(0.0, -float(record["distance_m"]))
            current[pair] = max(current.get(pair, 0.0), severity)
            if (
                record.get("both_robot") is not True
                or record.get("touches_pawn") is True
            ):
                external_or_pawn_count += 1
            if pair not in baseline_pairs:
                new_pairs.add(pair)
            else:
                allowed_observations += 1
                last_baseline_sample = int(snapshot["sample_index"])
                last_baseline_substep = int(snapshot["physics_substep"])
        for pair in baseline_pairs:
            severity = current.get(pair, 0.0)
            if pair in resolved_pairs and pair in current:
                recurrent_pairs.add(pair)
            if (
                severity
                > previous_severity[pair] + CONTACT_NUMERICAL_EPSILON_M
            ):
                worsened_pairs.add(pair)
            if pair not in current:
                resolved_pairs.add(pair)
            previous_severity[pair] = severity

    all_resolved = resolved_pairs == baseline_pairs
    resolved_during_egress = (
        first_changed_sample_index is not None
        and all_resolved
        and (
            last_baseline_sample < first_changed_sample_index
            or (
                last_baseline_sample == first_changed_sample_index
                and last_baseline_substep
                <= MAX_EGRESS_RESOLUTION_PHYSICS_SUBSTEP
            )
        )
    )
    forbidden_count = (
        external_or_pawn_count
        + len(new_pairs)
        + len(recurrent_pairs)
        + len(worsened_pairs)
        + int(not baseline_internal)
        + int(not baseline_within_cap)
        + int(not resolved_during_egress)
    )
    return {
        "contact_gate_mode": "resolving_preexisting_self_contact",
        "observed_robot_contact_count": observed_count,
        "allowed_preexisting_self_contact_observation_count": (
            allowed_observations
        ),
        "forbidden_robot_contact_count": forbidden_count,
        "robot_pawn_contact_count": sum(
            int(record.get("touches_pawn") is True)
            for snapshot in snapshots
            for record in snapshot.get("contacts") or []
        ),
        "baseline_contact_pairs": [list(pair) for pair in sorted(baseline_pairs)],
        "new_contact_pair_count": len(new_pairs),
        "recurrent_contact_pair_count": len(recurrent_pairs),
        "worsened_contact_pair_count": len(worsened_pairs),
        "preexisting_self_contact_only": baseline_internal,
        "preexisting_contact_max_penetration_m": baseline_penetration,
        "preexisting_contact_penetration_limit_m": (
            PREEXISTING_SELF_CONTACT_MAX_PENETRATION_M
        ),
        "preexisting_contact_never_worsened": not worsened_pairs,
        "preexisting_contact_resolved_during_egress": resolved_during_egress,
        "last_preexisting_contact_sample_index": last_baseline_sample,
        "last_preexisting_contact_physics_substep": last_baseline_substep,
        "first_changed_sample_index": first_changed_sample_index,
        "passed": forbidden_count == 0,
    }


def _dynamic_setup_preview(
    phase_simulator: np.ndarray,
    episode_directory: Path,
    receipt: Mapping[str, Any],
    candidate_config: Mapping[str, Any],
) -> dict[str, Any]:
    """Step one phase from its exact origin and reject every robot contact."""

    import mujoco

    model, _ = _compile_model(dict(candidate_config), base_directory=None)
    data = mujoco.MjData(model)
    initial_path = episode_directory / str(
        receipt["initial_evaluator_privileged_state_path"]
    )
    initial = _read_json(initial_path, "initial evaluator privileged state")
    state = np.asarray(
        initial["state"]["integration_state_float64"],
        dtype=np.float64,
    )
    state_size = mujoco.mj_stateSize(
        model,
        mujoco.mjtState.mjSTATE_INTEGRATION,
    )
    _require(
        state.shape == (state_size,),
        "setup preview state is incompatible with the candidate model",
    )
    mujoco.mj_setState(
        model,
        data,
        state,
        mujoco.mjtState.mjSTATE_INTEGRATION,
    )

    joint_ids: list[int] = []
    actuator_ids: list[int] = []
    for name in candidate_config["bindings"]["joint_names"]:
        joint_id = mujoco.mj_name2id(
            model,
            mujoco.mjtObj.mjOBJ_JOINT,
            str(name),
        )
        actuator_id = mujoco.mj_name2id(
            model,
            mujoco.mjtObj.mjOBJ_ACTUATOR,
            str(name),
        )
        _require(
            joint_id >= 0 and actuator_id >= 0,
            f"candidate model lacks setup command binding: {name}",
        )
        joint_ids.append(joint_id)
        actuator_ids.append(actuator_id)
    actuator_array = np.asarray(actuator_ids, dtype=np.int32)
    ctrl_range = model.actuator_ctrlrange[actuator_array]
    _require(
        np.all(phase_simulator >= ctrl_range[:, 0])
        and np.all(phase_simulator <= ctrl_range[:, 1]),
        "setup simulator actions require actuator clipping",
    )

    for index, joint_id in enumerate(joint_ids):
        data.qpos[int(model.jnt_qposadr[joint_id])] = float(
            phase_simulator[0, index]
        )
    data.qvel[:] = 0.0
    data.ctrl[actuator_array] = phase_simulator[0]
    mujoco.mj_forward(model, data)

    robot_ids = {
        body_id
        for body_id in range(model.nbody)
        if str(
            mujoco.mj_id2name(
                model,
                mujoco.mjtObj.mjOBJ_BODY,
                body_id,
            )
            or ""
        ).startswith("left_")
    }
    pawn_ids = {
        body_id
        for body_id in range(model.nbody)
        if "pawn_"
        in str(
            mujoco.mj_id2name(
                model,
                mujoco.mjtObj.mjOBJ_BODY,
                body_id,
            )
            or ""
        )
    }
    snapshots: list[dict[str, Any]] = []
    first_contacts: list[dict[str, Any]] = []

    def audit(sample_index: int, physics_substep: int) -> None:
        snapshot_contacts: list[dict[str, Any]] = []
        for contact_index in range(data.ncon):
            contact = data.contact[contact_index]
            body_a = int(model.geom_bodyid[int(contact.geom1)])
            body_b = int(model.geom_bodyid[int(contact.geom2)])
            bodies = {body_a, body_b}
            if not bodies & robot_ids:
                continue
            name_a = str(
                mujoco.mj_id2name(
                    model,
                    mujoco.mjtObj.mjOBJ_BODY,
                    body_a,
                )
                or f"body#{body_a}"
            )
            name_b = str(
                mujoco.mj_id2name(
                    model,
                    mujoco.mjtObj.mjOBJ_BODY,
                    body_b,
                )
                or f"body#{body_b}"
            )
            record = {
                "pair": sorted([name_a, name_b]),
                "body_a": name_a,
                "body_b": name_b,
                "distance_m": float(contact.dist),
                "both_robot": body_a in robot_ids and body_b in robot_ids,
                "touches_pawn": bool(bodies & pawn_ids),
            }
            snapshot_contacts.append(record)
            if len(first_contacts) < 32:
                first_contacts.append(
                    {
                        "sample_index": sample_index,
                        "physics_substep": physics_substep,
                        **record,
                    }
                )
        snapshots.append(
            {
                "sample_index": sample_index,
                "physics_substep": physics_substep,
                "contacts": snapshot_contacts,
            }
        )

    audit(0, -1)
    for sample_index, action in enumerate(phase_simulator):
        data.ctrl[actuator_array] = action
        for physics_substep in range(PHYSICS_STEPS_PER_ACTION):
            mujoco.mj_step(model, data)
            audit(sample_index, physics_substep)
    changed = np.flatnonzero(
        np.any(phase_simulator != phase_simulator[0], axis=1)
    )
    first_changed_sample_index = int(changed[0]) if len(changed) else None
    contact_gate = _classify_contact_snapshots(
        snapshots,
        first_changed_sample_index=first_changed_sample_index,
    )
    return {
        "runtime": "cpu_mujoco_fp64_dynamic_setup_preview",
        "sample_count": len(phase_simulator),
        "sample_hz": SAMPLE_HZ,
        "physics_steps_per_action": PHYSICS_STEPS_PER_ACTION,
        "exact_setup_sim_action_sha256": _sha256_bytes(
            phase_simulator.tobytes(order="C")
        ),
        "first_observed_robot_contacts": first_contacts,
        **contact_gate,
    }


def compile_geometric_setup_phase_packet(
    compile_inputs_path: Path,
    phase_index: int,
    packet_path: Path,
    *,
    previous_execution_path: Path | None = None,
    preflight_fn: Callable[[], dict[str, Any]] | None = None,
    preview_fn: PreviewFunction | None = None,
) -> dict[str, Any]:
    """Compile one setup-only phase from a fresh torque-off follower read."""

    compile_inputs_path = compile_inputs_path.resolve()
    packet_path = packet_path.resolve()
    _require(
        not packet_path.exists(),
        f"refusing to overwrite setup phase packet: {packet_path}",
    )
    (
        inputs,
        episode_directory,
        receipt,
        _,
        _,
        config,
        _,
        source_actions,
        physical,
        simulator,
        segments,
    ) = _load_transfer_inputs(compile_inputs_path)
    phase_physical, phase_simulator, timestamps, segment = _phase_arrays(
        physical,
        simulator,
        segments,
        phase_index,
    )
    task_action_sha256 = _sha256_bytes(
        source_actions.tobytes(order="C")
    )
    previous = _validate_previous_execution(
        previous_execution_path,
        phase_index=phase_index,
        compile_inputs_path=compile_inputs_path,
        task_action_sha256=task_action_sha256,
        expected_origin=phase_physical[0],
    )

    preview = (preview_fn or _dynamic_setup_preview)(
        phase_simulator,
        episode_directory,
        receipt,
        config,
    )
    _validate_preview(preview, phase_simulator)

    preflight = (preflight_fn or _default_preflight)()
    identity = _identity_from_preflight(preflight)
    current, lower, upper = _validate_limits(preflight)
    candidate_identity = (
        (
            _read_json(
                Path(inputs["candidate_manifest"]["path"]),
                "candidate manifest",
            ).get("identity")
            or {}
        ).get("robot")
        or {}
    )
    _require(
        candidate_identity.get("gateway_schema") == identity["gateway_schema"]
        and candidate_identity.get("follower_port") == identity["follower_port"]
        and candidate_identity.get("follower_calibration_sha256")
        == identity["follower_calibration_sha256"],
        "setup candidate/fresh follower identity drifted",
    )
    _require(
        np.all(
            np.abs(_anchor_delta(current, phase_physical[0]))
            <= CANARY_START_TOLERANCE_DEGREES
        ),
        "fresh torque-off follower anchor does not match setup phase origin",
    )
    _require(
        np.all(phase_physical >= lower)
        and np.all(phase_physical <= upper),
        "setup phase exceeds fresh calibrated follower limits",
    )
    rate_audit = _rate_audit(phase_physical, timestamps)
    excursion_audit = _excursion_audit(phase_physical)

    packet: dict[str, Any] = {
        "schema_version": SETUP_PACKET_SCHEMA,
        "kind": "geometric_follower_setup_only_phase",
        "single_use": True,
        "setup_phase_execution_admitted": False,
        "compile_inputs_path": str(compile_inputs_path),
        "compile_inputs_sha256": sha256_file(compile_inputs_path),
        "compile_inputs_canonical_payload_sha256": inputs[
            "canonical_payload_sha256"
        ],
        "phase_index": phase_index,
        "phase_count": len(segments),
        "previous_phase_execution": previous,
        "task_binding": {
            "source_episode_directory": str(episode_directory),
            "recording_id": receipt["recording_id"],
            "source_action_sha256": task_action_sha256,
            "source_action_shape": list(source_actions.shape),
            "task_action_payload_present": False,
            "task_bytes_must_be_compiled_separately_and_unchanged": True,
        },
        "candidate_binding": inputs["candidate_manifest"],
        "hardware_identity": identity,
        "fresh_compile_torque_off_preflight": {
            "follower_start_degrees": current.tolist(),
            "calibrated_minimum": lower.tolist(),
            "calibrated_maximum": upper.tolist(),
            "physical_follower_torque_enabled": False,
            "device_configuration_rewritten": False,
        },
        "sample_hz": SAMPLE_HZ,
        "timestamps_seconds": timestamps.tolist(),
        "frozen_physical_action_payload": _frozen_payload(
            phase_physical,
            phase_physical.tobytes(order="C"),
            encoding=ACTION_HASH_ENCODING,
            units=["degree"] * 5 + ["percent"],
        ),
        "frozen_simulator_action_payload": _frozen_payload(
            phase_simulator,
            phase_simulator.tobytes(order="C"),
            encoding=SETUP_SIM_ACTION_ENCODING,
            units=["radian"] * len(ROBOT_JOINTS),
        ),
        "rate_audit": rate_audit,
        "excursion_audit": excursion_audit,
        "simulation_contact_preview": preview,
        "simulation_contact_preview_sha256": canonical_json_sha256(preview),
        "phase_origin_physical_units": phase_physical[0].tolist(),
        "phase_target_physical_units": phase_physical[-1].tolist(),
        "execution_contract": {
            "follower_only": True,
            "setup_only": True,
            "exact_precompiled_targets_required": True,
            "rate_limit_clamp_stall_or_tracking_error_result": (
                "abort_and_torque_off"
            ),
            "fresh_torque_off_anchor_required": True,
            "fresh_simulation_preview_required": True,
            "torque_off_postflight_required": True,
            "one_phase_per_execution": True,
            "task_action_execution_forbidden": True,
        },
        "compiled_at": datetime.now(UTC).isoformat(),
        "physical_motion_commanded": False,
        "physical_follower_torque_enabled": False,
        "physical_task_consequence_admitted": False,
        "physical_authority": False,
    }
    packet["plan_sha256"] = _plan_sha256(packet)
    _write_once(packet_path, packet)
    return packet


def _decode_phase_payloads(
    packet: Mapping[str, Any],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    try:
        physical_payload = packet["frozen_physical_action_payload"]
        physical_raw = base64.b64decode(
            physical_payload["base64"],
            validate=True,
        )
        physical = np.frombuffer(physical_raw, dtype="<f8").reshape(
            tuple(physical_payload["shape"])
        )
        simulator_payload = packet["frozen_simulator_action_payload"]
        simulator_raw = base64.b64decode(
            simulator_payload["base64"],
            validate=True,
        )
        simulator = np.frombuffer(simulator_raw, dtype="<f8").reshape(
            tuple(simulator_payload["shape"])
        )
        timestamps = np.asarray(packet["timestamps_seconds"], dtype="<f8")
    except (KeyError, TypeError, ValueError) as error:
        raise GeometricPhysicalGatewayError(
            "setup phase packet payload is malformed"
        ) from error
    _require(
        physical_payload.get("encoding") == ACTION_HASH_ENCODING
        and simulator_payload.get("encoding") == SETUP_SIM_ACTION_ENCODING
        and physical_payload.get("sha256") == _sha256_bytes(physical_raw)
        and simulator_payload.get("sha256") == _sha256_bytes(simulator_raw)
        and physical.shape == simulator.shape
        and timestamps.shape == (len(physical),),
        "setup phase packet action bytes or shapes drifted",
    )
    return physical, simulator, timestamps


def _verify_phase_packet(
    packet_path: Path,
    *,
    rerun_preview: bool,
    preview_fn: PreviewFunction | None = None,
) -> tuple[
    dict[str, Any],
    np.ndarray,
    np.ndarray,
    np.ndarray,
    dict[str, Any],
]:
    packet_path = packet_path.resolve()
    packet = _read_json(packet_path, "geometric setup phase packet")
    _require(
        packet.get("schema_version") == SETUP_PACKET_SCHEMA
        and packet.get("plan_sha256") == _plan_sha256(packet),
        "geometric setup phase packet digest changed",
    )
    compile_inputs_path = Path(packet["compile_inputs_path"]).resolve()
    _require(
        sha256_file(compile_inputs_path) == packet["compile_inputs_sha256"],
        "setup compile inputs drifted after phase compilation",
    )
    (
        inputs,
        episode_directory,
        receipt,
        _,
        _,
        config,
        _,
        source_actions,
        all_physical,
        all_simulator,
        segments,
    ) = _load_transfer_inputs(compile_inputs_path)
    phase_index = int(packet["phase_index"])
    expected_physical, expected_simulator, expected_timestamps, _ = (
        _phase_arrays(
            all_physical,
            all_simulator,
            segments,
            phase_index,
        )
    )
    physical, simulator, timestamps = _decode_phase_payloads(packet)
    _require(
        physical.tobytes(order="C")
        == expected_physical.tobytes(order="C")
        and simulator.tobytes(order="C")
        == expected_simulator.tobytes(order="C")
        and np.array_equal(timestamps, expected_timestamps)
        and packet["task_binding"]["source_action_sha256"]
        == _sha256_bytes(source_actions.tobytes(order="C"))
        and packet["task_binding"]["task_action_payload_present"] is False,
        "setup packet differs from frozen setup or exact task binding",
    )
    previous_path = None
    if packet.get("previous_phase_execution") is not None:
        previous_path = Path(packet["previous_phase_execution"]["path"])
    previous = _validate_previous_execution(
        previous_path,
        phase_index=phase_index,
        compile_inputs_path=compile_inputs_path,
        task_action_sha256=packet["task_binding"]["source_action_sha256"],
        expected_origin=physical[0],
    )
    _require(
        previous == packet.get("previous_phase_execution"),
        "setup previous-phase binding drifted",
    )
    _require(
        packet.get("rate_audit") == _rate_audit(physical, timestamps)
        and packet.get("excursion_audit") == _excursion_audit(physical),
        "setup phase safety audit drifted",
    )
    if rerun_preview:
        preview = (preview_fn or _dynamic_setup_preview)(
            simulator,
            episode_directory,
            receipt,
            config,
        )
        _validate_preview(preview, simulator)
        _require(
            canonical_json_sha256(preview)
            == packet["simulation_contact_preview_sha256"],
            "independent setup simulation preview differs from compilation",
        )
    return packet, physical, simulator, timestamps, inputs


def review_geometric_setup_phase_packet(
    packet_path: Path,
    review_path: Path,
    *,
    reviewer: str,
    decision_id: str,
    preview_fn: PreviewFunction | None = None,
) -> dict[str, Any]:
    """Independently repeat setup lineage, byte, safety, and contact checks."""

    reviewer = reviewer.strip()
    decision_id = decision_id.strip()
    _require(reviewer and decision_id, "reviewer and decision id are required")
    packet_path = packet_path.resolve()
    packet, physical, _, _, _ = _verify_phase_packet(
        packet_path,
        rerun_preview=True,
        preview_fn=preview_fn,
    )
    review: dict[str, Any] = {
        "schema_version": SETUP_REVIEW_SCHEMA,
        "decision": "admit_single_setup_phase_only",
        "execution_admitted": True,
        "reviewer": reviewer,
        "decision_id": decision_id,
        "reviewed_at": datetime.now(UTC).isoformat(),
        "packet_path": str(packet_path),
        "packet_sha256": sha256_file(packet_path),
        "packet_plan_sha256": packet["plan_sha256"],
        "phase_index": packet["phase_index"],
        "task_source_action_sha256": packet["task_binding"][
            "source_action_sha256"
        ],
        "physical_action_sha256": action_sha256(physical),
        "fresh_compile_anchor_reviewed": True,
        "simulation_contact_preview_repeated": True,
        "rate_range_excursion_gates_reviewed": True,
        "torque_off_between_phases_reviewed": True,
        "task_action_execution_admitted": False,
        "physical_motion_commanded": False,
        "physical_follower_torque_enabled": False,
        "physical_task_consequence_admitted": False,
        "physical_authority": False,
    }
    review["review_sha256"] = _canonical_payload(
        review,
        "review_sha256",
    )
    _write_once(review_path.resolve(), review)
    return review


def execute_geometric_setup_phase_packet(
    packet_path: Path,
    review_path: Path,
    output_directory: Path,
    *,
    operator_acknowledged: bool = False,
    preflight_fn: Callable[[], dict[str, Any]] | None = None,
    gateway_factory: Callable[[Any], Any] | None = None,
    clock_fn: Callable[[], float] = time.monotonic,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Execute exactly one reviewed setup phase and leave follower torque off."""

    _require(operator_acknowledged, "fresh operator acknowledgement is required")
    packet_path = packet_path.resolve()
    review_path = review_path.resolve()
    output_directory = output_directory.resolve()
    output_path = output_directory / "execution_receipt.json"
    actions_path = output_directory / "actions.float64le"
    samples_path = output_directory / "joint_samples.jsonl"
    _require(
        not output_path.exists()
        and not actions_path.exists()
        and not samples_path.exists(),
        "refusing to overwrite setup phase execution output",
    )
    packet, physical, _, timestamps, _ = _verify_phase_packet(
        packet_path,
        rerun_preview=False,
    )
    review = _read_json(review_path, "geometric setup phase review")
    _require(
        review.get("schema_version") == SETUP_REVIEW_SCHEMA
        and review.get("review_sha256")
        == _canonical_payload(review, "review_sha256")
        and review.get("execution_admitted") is True
        and review.get("packet_sha256") == sha256_file(packet_path)
        and review.get("packet_plan_sha256") == packet["plan_sha256"]
        and review.get("phase_index") == packet["phase_index"]
        and review.get("physical_action_sha256")
        == action_sha256(physical)
        and review.get("task_action_execution_admitted") is False,
        "setup phase lacks a matching independent execution review",
    )

    preflight = (preflight_fn or _default_preflight)()
    identity = _identity_from_preflight(preflight)
    current, lower, upper = _validate_limits(preflight)
    _require(
        identity == packet["hardware_identity"],
        "setup follower hardware identity drifted after review",
    )
    _require(
        np.all(
            np.abs(_anchor_delta(current, physical[0]))
            <= CANARY_START_TOLERANCE_DEGREES
        ),
        "fresh torque-off follower pose differs from setup phase origin",
    )
    _require(
        np.all(physical >= lower) and np.all(physical <= upper),
        "setup phase exceeds fresh calibrated limits",
    )
    _rate_audit(physical, timestamps)
    _excursion_audit(physical)

    gateway = (gateway_factory or _default_gateway)(
        _gateway_identity(identity) if gateway_factory is None else identity
    )
    completed = 0
    final_actual = current.copy()
    started: float | None = None
    stopped: float | None = None
    error: Exception | None = None
    output_directory.mkdir(parents=True, exist_ok=True)
    actions_path.write_bytes(physical.tobytes(order="C"))
    samples_path.open("x").close()
    try:
        opened = gateway.open(
            enable_motion=True,
            paired_pose_confirmed=True,
        )
        opened_start = np.asarray(
            opened["follower_start_degrees"],
            dtype=np.float64,
        )
        _require(
            np.all(
                np.abs(_anchor_delta(opened_start, physical[0]))
                <= CANARY_START_TOLERANCE_DEGREES
            ),
            "setup follower origin drifted while arming phase",
        )
        started = clock_fn()
        with samples_path.open("a", encoding="utf-8") as handle:
            for sample_index, (timestamp, target) in enumerate(
                zip(timestamps, physical, strict=True)
            ):
                delay = started + float(timestamp) - clock_fn()
                if delay > 0.0:
                    sleep_fn(delay)
                sample = gateway.sample(
                    float(timestamp),
                    exact_requested_degrees=target,
                )
                requested = np.asarray(
                    sample.get("follower_requested_degrees"),
                    dtype="<f8",
                )
                sent = np.asarray(
                    sample.get("follower_command_degrees"),
                    dtype="<f8",
                )
                final_actual = np.asarray(
                    sample.get("follower_actual_position_degrees"),
                    dtype=np.float64,
                )
                _require(
                    requested.shape == target.shape
                    and sent.shape == target.shape
                    and requested.tobytes(order="C")
                    == target.tobytes(order="C")
                    and sent.tobytes(order="C") == target.tobytes(order="C")
                    and sample.get("rate_limited") is False
                    and sample.get("safety_clamped") is False,
                    "gateway modified, clipped, or rate-limited setup target",
                )
                _require(
                    sample.get("stalled") is False
                    and not sample.get("stalled_joints"),
                    "gateway reported a setup body-joint stall",
                )
                tracking_limits = np.asarray(
                    sample.get("tracking_error_limits"),
                    dtype=np.float64,
                )
                tracking = sent - final_actual
                tracking[4] = (
                    float(sent[4]) - float(final_actual[4]) + 180.0
                ) % 360.0 - 180.0
                _require(
                    tracking_limits.shape == (6,)
                    and np.all(
                        np.abs(tracking[:5])
                        <= tracking_limits[:5] + 1e-9
                    )
                    and (
                        abs(float(tracking[5]))
                        <= float(tracking_limits[5]) + 1e-9
                        or sample.get("gripper_contact_hold") is True
                    ),
                    "setup follower tracking exceeded reviewed envelope",
                )
                handle.write(
                    json.dumps(
                        {
                            "sample_index": sample_index,
                            "timestamp_seconds": float(timestamp),
                            "setup_action_sha256": packet[
                                "frozen_physical_action_payload"
                            ]["sha256"],
                            "requested_physical_units": target.tolist(),
                            **sample,
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )
                completed += 1
        stopped = clock_fn()
    except Exception as caught:
        error = caught
    finally:
        try:
            # close() owns the fail-closed torque disable and disconnect.
            gateway.close()
        except Exception as caught:
            error = error or caught

    postflight: dict[str, Any] | None = None
    try:
        postflight = (preflight_fn or _default_preflight)()
        _require(
            _identity_from_preflight(postflight) == identity
            and postflight.get("physical_follower_torque_enabled") is False,
            "setup phase postflight did not prove follower torque off",
        )
    except Exception as caught:
        error = error or caught
    if error is not None:
        raise GeometricPhysicalGatewayError(
            f"geometric setup phase stopped safely with torque off: {error}"
        ) from error
    _require(
        completed == len(physical),
        "setup phase did not send every frozen sample",
    )
    _require(
        np.all(
            np.abs(_anchor_delta(final_actual, physical[-1]))
            <= CANARY_START_TOLERANCE_DEGREES
        ),
        "setup phase ended outside the next fresh-rebase tolerance",
    )

    execution: dict[str, Any] = {
        "schema_version": SETUP_EXECUTION_SCHEMA,
        "status": "completed_setup_phase_torque_off",
        "packet_path": str(packet_path),
        "packet_sha256": sha256_file(packet_path),
        "review_path": str(review_path),
        "review_sha256": sha256_file(review_path),
        "compile_inputs_path": packet["compile_inputs_path"],
        "compile_inputs_sha256": packet["compile_inputs_sha256"],
        "phase_index": packet["phase_index"],
        "phase_count": packet["phase_count"],
        "task_source_action_sha256": packet["task_binding"][
            "source_action_sha256"
        ],
        "setup_physical_action_sha256": packet[
            "frozen_physical_action_payload"
        ]["sha256"],
        "actions_path": str(actions_path),
        "actions_sha256": sha256_file(actions_path),
        "joint_samples_path": str(samples_path),
        "joint_samples_sha256": sha256_file(samples_path),
        "completed_samples": completed,
        "phase_origin_physical_units": physical[0].tolist(),
        "phase_target_physical_units": physical[-1].tolist(),
        "final_actual_physical_units": final_actual.tolist(),
        "action_started_monotonic": started,
        "action_stopped_monotonic": stopped,
        "postflight": {
            "hardware_identity": identity,
            "physical_follower_torque_enabled": False,
        },
        "physical_motion_commanded": True,
        "physical_follower_torque_enabled": False,
        "physical_task_consequence_admitted": False,
        "physical_authority": False,
        "stop_before_next_phase": True,
        "task_action_execution_forbidden": True,
    }
    _write_once(output_path, execution)
    return execution
