"""Compile an admitted geometric source episode for guarded follower replay.

The source episode remains the owner of the simulator action sequence.  This
module only inverts an independently approved physical joint transform,
freezes the resulting follower bytes, previews those exact poses with
``mj_forward``, and routes a separately reviewed packet through the existing
follower-only gateway and native dual-camera recorder.

Compilation and review never enable torque or command motion.  Execution is
single-use, fail closed, and leaves task consequence unadmitted: completing
the command stream and camera capture is not proof that a physical pawn moved.
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

from . import grasp, pawn_source_evaluator, scene, source_episode
from .pawn_source_evaluator import (
    evaluator_path_for_scene,
    load_pawn_evaluator_contract,
)
from .physical_canary import (
    CANARY_BODY_RATE_DEGREES_S,
    CANARY_GRIPPER_RATE_S,
    CANARY_START_TOLERANCE_DEGREES,
    CANARY_WRIST_ROLL_RATE_DEGREES_S,
    CameraCapture,
    _anchor_delta,
    _default_capture,
    _default_gateway,
    _default_preflight,
    _gateway_identity,
    _identity_from_preflight,
    _validate_limits,
)
from .recorded_replay import (
    ReplayContractError,
    _compile_model,
    _validated_physical_transform,
    canonical_json_sha256,
)
from .replay_eligibility import ACTION_HASH_ENCODING, action_sha256
from .scene import CURRENT_TASK_PIECE_LAYOUT, ROBOT_JOINTS
from .source_episode import (
    ADMISSION_SCHEMA,
    adapt_source_episode,
    admission_payload_sha256,
    load_source_episode,
    sha256_file,
)
from .twin_candidate import CANDIDATE_SCHEMA


PACKET_SCHEMA = "sim2claw.geometric_physical_packet.v1"
REVIEW_SCHEMA = "sim2claw.geometric_physical_review_receipt.v1"
EXECUTION_SCHEMA = "sim2claw.geometric_physical_execution_receipt.v1"
SOURCE_ACTION_ENCODING = "little_endian_float32_c_order"
SAMPLE_HZ = 20
POST_ROLL_SECONDS = 0.5


class GeometricPhysicalGatewayError(RuntimeError):
    """A source, transform, preview, review, or execution gate failed closed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GeometricPhysicalGatewayError(message)


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GeometricPhysicalGatewayError(
            f"could not load {label}: {error}"
        ) from error
    _require(isinstance(value, dict), f"{label} must be an object")
    return value


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _write_once(path: Path, value: Mapping[str, Any]) -> None:
    _require(not path.exists(), f"refusing to overwrite existing output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _plan_sha256(value: Mapping[str, Any]) -> str:
    return canonical_json_sha256(
        {key: item for key, item in value.items() if key != "plan_sha256"}
    )


def _evaluator_identity() -> dict[str, str]:
    modules = {
        "evaluator_module_sha256": pawn_source_evaluator,
        "grasp_module_sha256": grasp,
        "scene_module_sha256": scene,
        "source_episode_module_sha256": source_episode,
    }
    return {
        field: sha256_file(Path(module.__file__).resolve())
        for field, module in modules.items()
    }


def _validated_source(
    episode_directory: Path,
    admission_verdict_path: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any], Path]:
    episode_directory = episode_directory.resolve()
    admission_verdict_path = admission_verdict_path.resolve()
    receipt, rows = load_source_episode(episode_directory)
    verdict = _read_json(admission_verdict_path, "source evaluator verdict")

    # Reuse the policy-adapter admission boundary to preserve all strict source
    # receipt, action, held-out, assistance, and replay gates.
    adapted = adapt_source_episode(
        episode_directory,
        adapter="act",
        admission_verdict=verdict,
    )
    _require(
        len(adapted) == len(rows),
        "physical compilation requires ordinary full-episode admission",
    )
    _require(
        verdict.get("schema_version") == ADMISSION_SCHEMA
        and verdict.get("canonical_payload_sha256")
        == admission_payload_sha256(verdict),
        "source evaluator verdict digest drifted",
    )
    _require(
        verdict.get("terminal_outcome") == "pawn_released_upright_on_target"
        and verdict.get("selected_piece_id") == receipt.get("piece_id"),
        "source evaluator verdict does not admit the selected pawn consequence",
    )
    _require(
        receipt.get("piece_layout") == CURRENT_TASK_PIECE_LAYOUT
        and int(receipt.get("sample_hz", 0)) == SAMPLE_HZ,
        "source episode is not the current 20 Hz pawn workcell contract",
    )
    _require(
        all(
            row["action"].get("owner") == "geometric_expert"
            and int(row["action"].get("assistance", -1)) == 0
            and int(row["action"].get("intervention", -1)) == 0
            for row in rows
        ),
        "physical compilation requires unassisted geometric-expert actions",
    )

    evaluator_path = evaluator_path_for_scene(
        str(receipt["scene_id"]),
        source_contract_id=str(receipt["task_id"]),
    ).resolve()
    load_pawn_evaluator_contract(evaluator_path)
    _require(
        verdict.get("evaluator_contract_sha256") == sha256_file(evaluator_path),
        "source evaluator contract drifted after admission",
    )
    _require(
        verdict.get("evaluator_identity") == _evaluator_identity(),
        "source evaluator implementation drifted after admission",
    )
    return receipt, rows, verdict, evaluator_path


def _validated_candidate(
    candidate_manifest_path: Path,
    receipt: Mapping[str, Any],
) -> tuple[dict[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    candidate_manifest_path = candidate_manifest_path.resolve()
    manifest = _read_json(candidate_manifest_path, "candidate manifest")
    _require(
        manifest.get("schema_version") == CANDIDATE_SCHEMA,
        "unsupported candidate manifest schema",
    )
    config = manifest.get("candidate_config")
    _require(isinstance(config, Mapping), "candidate manifest lacks its config")
    _require(
        manifest.get("candidate_config_sha256")
        == canonical_json_sha256(config),
        "candidate config hash drifted",
    )
    try:
        transform = _validated_physical_transform(config)
    except (ReplayContractError, TypeError, ValueError) as error:
        raise GeometricPhysicalGatewayError(
            f"candidate physical transform is invalid: {error}"
        ) from error
    _require(transform is not None, "candidate has no physical joint transform")
    _require(
        transform.get("calibration_approved") is True,
        "candidate physical transform is not calibration-approved",
    )

    registration = (
        (manifest.get("geometry_provenance") or {}).get(
            "workcell_registration"
        )
        or {}
    )
    if registration:
        _require(
            registration.get("board_scene_id") == receipt.get("scene_id")
            and registration.get("board_pose_id") == receipt.get("board_pose_id"),
            "candidate geometry is registered to another source workcell",
        )
    sources = manifest.get("sources") or {}
    geometry = manifest.get("geometry_provenance") or {}
    metric_geometry_bound = bool(
        geometry.get("metric_geometry_available") is True
        and geometry.get("physical_promotion_requires_p13") is False
    ) or bool(
        isinstance(sources, Mapping)
        and "p13_transform" in sources
        and "p13_board_fit" in sources
    )
    _require(
        metric_geometry_bound,
        "candidate lacks metric P13 transform and board-fit lineage",
    )
    _require(
        (config.get("model") or {}).get("piece_layout")
        == receipt.get("piece_layout"),
        "candidate/source pawn layouts differ",
    )
    _require(
        list((config.get("bindings") or {}).get("joint_names") or [])
        == [f"left_{joint}" for joint in ROBOT_JOINTS],
        "candidate joint order differs from the physical gateway order",
    )
    return manifest, config, transform


def _source_actions(
    rows: list[dict[str, Any]],
) -> tuple[np.ndarray, np.ndarray, bytes]:
    actions = np.asarray(
        [row["action"]["joint_target_rad"] for row in rows],
        dtype="<f4",
        order="C",
    )
    timestamps = np.asarray(
        [row["timestamp_monotonic_seconds"] for row in rows],
        dtype="<f8",
    )
    _require(
        actions.shape == (len(rows), len(ROBOT_JOINTS))
        and len(rows) >= 2
        and np.all(np.isfinite(actions)),
        "source action tensor is not a finite multi-sample six-vector sequence",
    )
    _require(
        np.array_equal(
            timestamps,
            np.arange(len(rows), dtype="<f8") / float(SAMPLE_HZ),
        ),
        "source timestamps are not the exact 20 Hz sample-hold sequence",
    )
    raw = actions.tobytes(order="C")
    return actions, timestamps, raw


def _inverse_transform(
    source_actions: np.ndarray,
    transform: Mapping[str, Any],
) -> tuple[np.ndarray, bytes]:
    physical = np.empty(source_actions.shape, dtype="<f8")
    for index, entry in enumerate(transform["joints"]):
        scale = float(entry["scale"])
        sign = float(entry["sign"])
        offset = float(entry["zero_offset"])
        physical[:, index] = (
            source_actions[:, index].astype(np.float64) - offset
        ) / (sign * scale)
    _require(
        np.all(np.isfinite(physical)),
        "inverse physical transform produced non-finite commands",
    )
    round_trip = np.empty(source_actions.shape, dtype="<f4")
    for index, entry in enumerate(transform["joints"]):
        round_trip[:, index] = (
            physical[:, index]
            * float(entry["sign"])
            * float(entry["scale"])
            + float(entry["zero_offset"])
        ).astype("<f4")
    _require(
        round_trip.tobytes(order="C") == source_actions.tobytes(order="C"),
        "inverse transform cannot round-trip the exact source float32 bytes",
    )
    raw = physical.tobytes(order="C")
    return physical, raw


def _rate_audit(actions: np.ndarray, timestamps: np.ndarray) -> dict[str, Any]:
    rates = np.diff(actions, axis=0) / np.diff(timestamps)[:, None]
    maximum = np.max(np.abs(rates), axis=0)
    limits = np.asarray(
        [
            CANARY_BODY_RATE_DEGREES_S,
            CANARY_BODY_RATE_DEGREES_S,
            CANARY_BODY_RATE_DEGREES_S,
            CANARY_BODY_RATE_DEGREES_S,
            CANARY_WRIST_ROLL_RATE_DEGREES_S,
            CANARY_GRIPPER_RATE_S,
        ],
        dtype=np.float64,
    )
    _require(
        np.all(maximum <= limits + 1e-9),
        "inverse-mapped source actions exceed reviewed gateway rate limits",
    )
    return {
        "maximum_absolute_rate_per_second": maximum.tolist(),
        "reviewed_rate_limit_per_second": limits.tolist(),
        "all_rates_within_reviewed_gateway_limits": True,
    }


def _mj_forward_preview(
    source_actions: np.ndarray,
    episode_directory: Path,
    receipt: Mapping[str, Any],
    candidate_config: Mapping[str, Any],
) -> dict[str, Any]:
    """Audit every exact commanded pose against recorded dynamic piece state."""

    import mujoco

    model, _ = _compile_model(dict(candidate_config), base_directory=None)
    data = mujoco.MjData(model)
    state_size = mujoco.mj_stateSize(
        model, mujoco.mjtState.mjSTATE_INTEGRATION
    )
    privileged_path = episode_directory / str(
        receipt["evaluator_privileged_state_path"]
    )
    privileged_rows = [
        json.loads(line)
        for line in privileged_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    _require(
        len(privileged_rows) == len(source_actions),
        "source privileged-state count drifted before contact preview",
    )

    joint_ids: list[int] = []
    actuator_ids: list[int] = []
    for name in candidate_config["bindings"]["joint_names"]:
        joint_id = mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_JOINT, str(name)
        )
        actuator_id = mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_ACTUATOR, str(name)
        )
        _require(
            joint_id >= 0 and actuator_id >= 0,
            f"candidate model lacks source command binding: {name}",
        )
        joint_ids.append(joint_id)
        actuator_ids.append(actuator_id)
    ctrl_range = model.actuator_ctrlrange[np.asarray(actuator_ids, dtype=np.int32)]
    _require(
        np.all(source_actions >= ctrl_range[:, 0])
        and np.all(source_actions <= ctrl_range[:, 1]),
        "source evaluator actions require candidate actuator clipping",
    )

    selected_piece = str(receipt["piece_id"])
    selected_id = mujoco.mj_name2id(
        model, mujoco.mjtObj.mjOBJ_BODY, selected_piece
    )
    _require(selected_id >= 0, "candidate model lacks the selected source pawn")
    jaw_ids = grasp._jaw_body_ids(model, "left")
    robot_ids = {
        body_id
        for body_id in range(model.nbody)
        if str(
            mujoco.mj_id2name(
                model, mujoco.mjtObj.mjOBJ_BODY, body_id
            )
            or ""
        ).startswith("left_")
    }
    forbidden: list[dict[str, Any]] = []
    forbidden_count = 0
    intentional_target_contact_samples = 0
    for sample_index, (action, privileged) in enumerate(
        zip(source_actions, privileged_rows, strict=True)
    ):
        state = np.asarray(
            privileged["state"]["integration_state_float64"],
            dtype=np.float64,
        )
        _require(
            state.shape == (state_size,),
            "source integration state is incompatible with the candidate model",
        )
        mujoco.mj_setState(
            model,
            data,
            state,
            mujoco.mjtState.mjSTATE_INTEGRATION,
        )
        for index, joint_id in enumerate(joint_ids):
            data.qpos[int(model.jnt_qposadr[joint_id])] = float(action[index])
        data.qvel[:] = 0.0
        mujoco.mj_forward(model, data)
        target_contact = False
        for contact_index in range(data.ncon):
            contact = data.contact[contact_index]
            body_a = int(model.geom_bodyid[int(contact.geom1)])
            body_b = int(model.geom_bodyid[int(contact.geom2)])
            bodies = {body_a, body_b}
            if not bodies & robot_ids:
                continue
            allowed_target_contact = (
                selected_id in bodies and bool(bodies & jaw_ids)
            )
            if allowed_target_contact:
                target_contact = True
                continue
            forbidden_count += 1
            name_a = (
                mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_a)
                or f"body#{body_a}"
            )
            name_b = (
                mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_b)
                or f"body#{body_b}"
            )
            if len(forbidden) < 32:
                forbidden.append(
                    {
                        "sample_index": sample_index,
                        "body_a": str(name_a),
                        "body_b": str(name_b),
                        "distance_m": float(contact.dist),
                    }
                )
        intentional_target_contact_samples += int(target_contact)
    return {
        "runtime": "cpu_mujoco_mj_forward",
        "sample_count": int(source_actions.shape[0]),
        "exact_source_action_sha256": _sha256_bytes(
            source_actions.tobytes(order="C")
        ),
        "selected_piece_id": selected_piece,
        "intentional_jaw_target_contact_sample_count": (
            intentional_target_contact_samples
        ),
        "forbidden_robot_contact_count": forbidden_count,
        "first_forbidden_robot_contacts": forbidden,
        "passed": forbidden_count == 0,
    }


def _frozen_payload(
    values: np.ndarray,
    raw: bytes,
    *,
    encoding: str,
    units: list[str],
) -> dict[str, Any]:
    return {
        "encoding": encoding,
        "shape": list(values.shape),
        "base64": base64.b64encode(raw).decode("ascii"),
        "sha256": _sha256_bytes(raw),
        "units": units,
    }


def compile_geometric_physical_packet(
    episode_directory: Path,
    admission_verdict_path: Path,
    candidate_manifest_path: Path,
    packet_path: Path,
    *,
    preflight_fn: Callable[[], dict[str, Any]] | None = None,
    preview_fn: Callable[
        [np.ndarray, Path, Mapping[str, Any], Mapping[str, Any]],
        dict[str, Any],
    ]
    | None = None,
) -> dict[str, Any]:
    """Compile exact follower bytes without enabling torque or commanding motion."""

    episode_directory = episode_directory.resolve()
    admission_verdict_path = admission_verdict_path.resolve()
    candidate_manifest_path = candidate_manifest_path.resolve()
    packet_path = packet_path.resolve()
    _require(not packet_path.exists(), f"refusing to overwrite packet: {packet_path}")

    receipt, rows, verdict, evaluator_path = _validated_source(
        episode_directory, admission_verdict_path
    )
    manifest, config, transform = _validated_candidate(
        candidate_manifest_path, receipt
    )
    source_actions, timestamps, source_raw = _source_actions(rows)
    physical_actions, physical_raw = _inverse_transform(
        source_actions, transform
    )

    preflight = (preflight_fn or _default_preflight)()
    identity = _identity_from_preflight(preflight)
    current, lower, upper = _validate_limits(preflight)
    manifest_identity = (manifest.get("identity") or {}).get("robot") or {}
    _require(
        manifest_identity.get("gateway_schema") == identity["gateway_schema"]
        and manifest_identity.get("follower_port") == identity["follower_port"]
        and manifest_identity.get("follower_calibration_sha256")
        == identity["follower_calibration_sha256"],
        "candidate/fresh follower hardware identity drifted",
    )
    _require(
        np.all(
            np.abs(_anchor_delta(current, physical_actions[0]))
            <= CANARY_START_TOLERANCE_DEGREES
        ),
        "fresh follower start does not match the inverse-mapped source start",
    )
    _require(
        np.all(physical_actions >= lower)
        and np.all(physical_actions <= upper),
        "inverse-mapped source actions exceed fresh calibrated follower limits",
    )
    rate_audit = _rate_audit(physical_actions, timestamps)
    preview = (preview_fn or _mj_forward_preview)(
        source_actions,
        episode_directory,
        receipt,
        config,
    )
    source_action_sha256 = _sha256_bytes(source_raw)
    _require(
        preview.get("passed") is True
        and preview.get("sample_count") == len(rows)
        and preview.get("exact_source_action_sha256") == source_action_sha256,
        "mj_forward preview rejected or consumed different source action bytes",
    )

    packet: dict[str, Any] = {
        "schema_version": PACKET_SCHEMA,
        "kind": "admitted_geometric_pawn_source_to_follower_exact_replay",
        "single_use": True,
        "physical_packet_execution_admitted": False,
        "source_episode": {
            "directory": str(episode_directory),
            "recording_id": receipt["recording_id"],
            "recording_receipt_sha256": sha256_file(
                episode_directory / "recording_receipt.json"
            ),
            "samples_sha256": receipt["samples_sha256"],
            "scene_id": receipt["scene_id"],
            "board_pose_id": receipt["board_pose_id"],
            "piece_id": receipt["piece_id"],
            "destination_square": receipt["destination_square"],
        },
        "source_admission_verdict": {
            "path": str(admission_verdict_path),
            "sha256": sha256_file(admission_verdict_path),
            "canonical_payload_sha256": verdict["canonical_payload_sha256"],
            "strict_success": True,
        },
        "source_evaluator": {
            "path": str(evaluator_path),
            "sha256": sha256_file(evaluator_path),
            "implementation_identity": _evaluator_identity(),
        },
        "candidate_manifest": {
            "path": str(candidate_manifest_path),
            "sha256": sha256_file(candidate_manifest_path),
            "candidate_digest": manifest["candidate_digest"],
            "candidate_config_sha256": manifest["candidate_config_sha256"],
        },
        "physical_joint_transform": {
            "transform_id": transform["transform_id"],
            "sha256": config["physical_adapter"]["joint_transform_sha256"],
            "calibration_approved": True,
            "review": transform["review"],
            "exact_formula": "physical=(simulator-zero_offset)/(sign*scale)",
        },
        "hardware_identity": identity,
        "fresh_compile_preflight": {
            "follower_start_degrees": current.tolist(),
            "calibrated_minimum_degrees": lower.tolist(),
            "calibrated_maximum_degrees": upper.tolist(),
            "physical_follower_torque_enabled": False,
            "device_configuration_rewritten": False,
        },
        "sample_hz": SAMPLE_HZ,
        "timestamps_seconds": timestamps.tolist(),
        "source_action_payload": _frozen_payload(
            source_actions,
            source_raw,
            encoding=SOURCE_ACTION_ENCODING,
            units=["radian"] * len(ROBOT_JOINTS),
        ),
        "frozen_physical_action_payload": {
            **_frozen_payload(
                physical_actions,
                physical_raw,
                encoding=ACTION_HASH_ENCODING,
                units=["degree"] * 5 + ["percent"],
            ),
            "simulation_consumer_source_sha256": source_action_sha256,
            "hardware_consumer_must_use_same_bytes": True,
        },
        "rate_audit": rate_audit,
        "mj_forward_contact_preview": preview,
        "mj_forward_contact_preview_sha256": canonical_json_sha256(preview),
        "execution_contract": {
            "gateway": "existing_follower_only_physical_gateway",
            "exact_precompiled_targets_required": True,
            "rate_limit_or_clamp_result": "abort_before_send",
            "body_tracking_error_result": "abort_and_torque_off",
            "body_stall_result": "abort_and_torque_off",
            "gripper_contact_deflection_is_not_body_stall": True,
            "dual_camera_completion_required": True,
            "torque_off_postflight_required": True,
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


def _decode_packet_actions(
    packet: Mapping[str, Any],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    try:
        source_payload = packet["source_action_payload"]
        source_raw = base64.b64decode(
            source_payload["base64"], validate=True
        )
        source_actions = np.frombuffer(source_raw, dtype="<f4").reshape(
            tuple(source_payload["shape"])
        )
        physical_payload = packet["frozen_physical_action_payload"]
        physical_raw = base64.b64decode(
            physical_payload["base64"], validate=True
        )
        physical_actions = np.frombuffer(physical_raw, dtype="<f8").reshape(
            tuple(physical_payload["shape"])
        )
        timestamps = np.asarray(packet["timestamps_seconds"], dtype="<f8")
    except (KeyError, TypeError, ValueError) as error:
        raise GeometricPhysicalGatewayError(
            "geometric physical packet payload is malformed"
        ) from error
    _require(
        source_payload.get("encoding") == SOURCE_ACTION_ENCODING
        and physical_payload.get("encoding") == ACTION_HASH_ENCODING
        and source_payload.get("sha256") == _sha256_bytes(source_raw)
        and physical_payload.get("sha256") == _sha256_bytes(physical_raw),
        "geometric physical packet action bytes drifted",
    )
    _require(
        source_actions.shape == physical_actions.shape
        and timestamps.shape == (source_actions.shape[0],),
        "geometric physical packet action shapes drifted",
    )
    return source_actions, physical_actions, timestamps


def _verify_packet_static(
    packet_path: Path,
    *,
    rerun_preview: bool,
    preview_fn: Callable[
        [np.ndarray, Path, Mapping[str, Any], Mapping[str, Any]],
        dict[str, Any],
    ]
    | None = None,
) -> tuple[
    dict[str, Any],
    np.ndarray,
    np.ndarray,
    np.ndarray,
    dict[str, Any],
]:
    packet_path = packet_path.resolve()
    packet = _read_json(packet_path, "geometric physical packet")
    _require(
        packet.get("schema_version") == PACKET_SCHEMA
        and packet.get("plan_sha256") == _plan_sha256(packet),
        "geometric physical packet digest changed",
    )
    source = packet["source_episode"]
    episode_directory = Path(source["directory"]).resolve()
    admission_path = Path(
        packet["source_admission_verdict"]["path"]
    ).resolve()
    receipt, rows, verdict, evaluator_path = _validated_source(
        episode_directory, admission_path
    )
    _require(
        sha256_file(episode_directory / "recording_receipt.json")
        == source["recording_receipt_sha256"]
        and receipt["samples_sha256"] == source["samples_sha256"]
        and sha256_file(admission_path)
        == packet["source_admission_verdict"]["sha256"]
        and verdict["canonical_payload_sha256"]
        == packet["source_admission_verdict"]["canonical_payload_sha256"]
        and sha256_file(evaluator_path) == packet["source_evaluator"]["sha256"],
        "source or evaluator lineage drifted after physical compilation",
    )
    candidate_path = Path(packet["candidate_manifest"]["path"]).resolve()
    _require(
        sha256_file(candidate_path) == packet["candidate_manifest"]["sha256"],
        "candidate manifest drifted after physical compilation",
    )
    manifest, config, transform = _validated_candidate(candidate_path, receipt)
    _require(
        manifest["candidate_digest"]
        == packet["candidate_manifest"]["candidate_digest"]
        and config["physical_adapter"]["joint_transform_sha256"]
        == packet["physical_joint_transform"]["sha256"],
        "candidate or physical transform identity drifted",
    )
    source_actions, physical_actions, timestamps = _decode_packet_actions(packet)
    expected_source, expected_timestamps, source_raw = _source_actions(rows)
    expected_physical, physical_raw = _inverse_transform(
        expected_source, transform
    )
    _require(
        source_actions.tobytes(order="C") == source_raw
        and physical_actions.tobytes(order="C") == physical_raw
        and np.array_equal(timestamps, expected_timestamps),
        "packet actions differ from the admitted source or inverse transform",
    )
    if rerun_preview:
        preview = (preview_fn or _mj_forward_preview)(
            source_actions,
            episode_directory,
            receipt,
            config,
        )
        _require(
            preview.get("passed") is True
            and canonical_json_sha256(preview)
            == packet["mj_forward_contact_preview_sha256"],
            "independent mj_forward review differs from compilation",
        )
    return packet, source_actions, physical_actions, timestamps, receipt


def review_geometric_physical_packet(
    packet_path: Path,
    review_path: Path,
    *,
    reviewer: str,
    decision_id: str,
    preview_fn: Callable[
        [np.ndarray, Path, Mapping[str, Any], Mapping[str, Any]],
        dict[str, Any],
    ]
    | None = None,
) -> dict[str, Any]:
    """Independently revalidate lineage, bytes, inverse mapping, and preview."""

    reviewer = reviewer.strip()
    decision_id = decision_id.strip()
    _require(reviewer and decision_id, "reviewer and decision id are required")
    packet_path = packet_path.resolve()
    packet, source_actions, physical_actions, _, _ = _verify_packet_static(
        packet_path,
        rerun_preview=True,
        preview_fn=preview_fn,
    )
    review = {
        "schema_version": REVIEW_SCHEMA,
        "decision": "admit_single_use_physical_execution",
        "execution_admitted": True,
        "reviewer": reviewer,
        "decision_id": decision_id,
        "reviewed_at": datetime.now(UTC).isoformat(),
        "packet_path": str(packet_path),
        "packet_sha256": sha256_file(packet_path),
        "packet_plan_sha256": packet["plan_sha256"],
        "source_action_sha256": _sha256_bytes(
            source_actions.tobytes(order="C")
        ),
        "physical_action_sha256": action_sha256(physical_actions),
        "candidate_manifest_sha256": packet["candidate_manifest"]["sha256"],
        "physical_joint_transform_sha256": packet[
            "physical_joint_transform"
        ]["sha256"],
        "source_evaluator_sha256": packet["source_evaluator"]["sha256"],
        "exact_inverse_mapping_reviewed": True,
        "fresh_start_and_limits_reviewed": True,
        "mj_forward_contact_preview_repeated": True,
        "dual_camera_tracking_stall_and_torque_off_contract_reviewed": True,
        "physical_motion_commanded": False,
        "physical_follower_torque_enabled": False,
        "physical_task_consequence_admitted": False,
        "physical_authority": False,
    }
    review["review_sha256"] = canonical_json_sha256(review)
    _write_once(review_path.resolve(), review)
    return review


def _camera_started(camera: Mapping[str, Any]) -> bool:
    return (
        camera.get("status") == "recording"
        and (camera.get("overhead") or {}).get("status") == "recording"
        and (camera.get("wrist") or {}).get("status") == "recording"
    )


def _camera_completed(camera: Mapping[str, Any]) -> bool:
    return (
        (camera.get("overhead") or {}).get("status") == "completed"
        and int((camera.get("overhead") or {}).get("container_frame_count", 0))
        > 0
        and (camera.get("wrist") or {}).get("status") == "completed"
        and int((camera.get("wrist") or {}).get("container_frame_count", 0)) > 0
    )


def execute_geometric_physical_packet(
    packet_path: Path,
    review_path: Path,
    output_directory: Path,
    *,
    operator_acknowledged: bool = False,
    preflight_fn: Callable[[], dict[str, Any]] | None = None,
    gateway_factory: Callable[[Any], Any] | None = None,
    capture_factory: Callable[[Path], CameraCapture] | None = None,
    clock_fn: Callable[[], float] = time.monotonic,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Execute reviewed bytes once, with cameras, fail-closed telemetry, and torque-off."""

    _require(operator_acknowledged, "fresh operator acknowledgement is required")
    packet_path = packet_path.resolve()
    review_path = review_path.resolve()
    output_directory = output_directory.resolve()
    output_path = output_directory / "execution_receipt.json"
    samples_path = output_directory / "joint_samples.jsonl"
    actions_path = output_directory / "actions.float64le"
    _require(
        not output_path.exists()
        and not samples_path.exists()
        and not actions_path.exists(),
        "refusing to overwrite geometric physical execution output",
    )
    packet, _, physical_actions, timestamps, _ = _verify_packet_static(
        packet_path,
        rerun_preview=False,
    )
    review = _read_json(review_path, "geometric physical review")
    _require(
        review.get("schema_version") == REVIEW_SCHEMA
        and review.get("review_sha256")
        == canonical_json_sha256(
            {key: value for key, value in review.items() if key != "review_sha256"}
        )
        and review.get("execution_admitted") is True
        and review.get("packet_sha256") == sha256_file(packet_path)
        and review.get("packet_plan_sha256") == packet["plan_sha256"]
        and review.get("physical_action_sha256")
        == action_sha256(physical_actions),
        "packet lacks a matching independent execution review",
    )

    fresh_preflight = (preflight_fn or _default_preflight)()
    identity = _identity_from_preflight(fresh_preflight)
    current, lower, upper = _validate_limits(fresh_preflight)
    _require(
        identity == packet["hardware_identity"],
        "follower hardware identity drifted after review",
    )
    _require(
        np.all(
            np.abs(_anchor_delta(current, physical_actions[0]))
            <= CANARY_START_TOLERANCE_DEGREES
        ),
        "fresh follower pose differs from the reviewed source start",
    )
    _require(
        np.all(physical_actions >= lower)
        and np.all(physical_actions <= upper),
        "reviewed physical actions exceed fresh calibrated limits",
    )
    _rate_audit(physical_actions, timestamps)

    gateway = (gateway_factory or _default_gateway)(
        _gateway_identity(identity) if gateway_factory is None else identity
    )
    capture: CameraCapture | None = None
    camera_started: dict[str, Any] | None = None
    camera_finished: dict[str, Any] | None = None
    completed = 0
    action_started: float | None = None
    action_stopped: float | None = None
    error: Exception | None = None
    output_directory.mkdir(parents=True, exist_ok=True)
    actions_path.write_bytes(physical_actions.tobytes(order="C"))
    samples_path.open("x").close()
    try:
        capture = (capture_factory or _default_capture)(
            output_directory / "dual_camera"
        )
        camera_started = capture.start()
        _require(
            _camera_started(camera_started),
            "native dual-camera capture did not start both streams",
        )
        opened = gateway.open(enable_motion=True, paired_pose_confirmed=True)
        opened_start = np.asarray(
            opened["follower_start_degrees"], dtype=np.float64
        )
        _require(
            np.all(
                np.abs(_anchor_delta(opened_start, physical_actions[0]))
                <= CANARY_START_TOLERANCE_DEGREES
            ),
            "follower start drifted while arming the reviewed packet",
        )
        action_started = clock_fn()
        with samples_path.open("a", encoding="utf-8") as handle:
            for sample_index, (timestamp, target) in enumerate(
                zip(timestamps, physical_actions, strict=True)
            ):
                delay = action_started + float(timestamp) - clock_fn()
                if delay > 0:
                    sleep_fn(delay)
                sample = gateway.sample(
                    float(timestamp),
                    exact_requested_degrees=target,
                )
                requested = np.asarray(
                    sample.get("follower_requested_degrees"), dtype="<f8"
                )
                sent = np.asarray(
                    sample.get("follower_command_degrees"), dtype="<f8"
                )
                actual = np.asarray(
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
                    "gateway modified, clipped, or rate-limited a frozen target",
                )
                _require(
                    sample.get("stalled") is False
                    and not sample.get("stalled_joints"),
                    "gateway reported a body-joint stall",
                )
                tracking_limits = np.asarray(
                    sample.get("tracking_error_limits"), dtype=np.float64
                )
                tracking = sent - actual
                tracking[4] = (
                    float(sent[4]) - float(actual[4]) + 180.0
                ) % 360.0 - 180.0
                body_tracking_ok = (
                    tracking_limits.shape == (6,)
                    and np.all(
                        np.abs(tracking[:5]) <= tracking_limits[:5] + 1e-9
                    )
                )
                gripper_tracking_ok = (
                    tracking_limits.shape == (6,)
                    and (
                        abs(float(tracking[5]))
                        <= float(tracking_limits[5]) + 1e-9
                        or sample.get("gripper_contact_hold") is True
                    )
                )
                _require(
                    body_tracking_ok and gripper_tracking_ok,
                    "fresh follower tracking exceeded the reviewed envelope",
                )
                handle.write(
                    json.dumps(
                        {
                            "sample_index": sample_index,
                            "timestamp_seconds": float(timestamp),
                            "physical_action_sha256": packet[
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
        action_stopped = clock_fn()
    except Exception as caught:
        error = caught
    finally:
        try:
            gateway.close()
        except Exception as caught:
            error = error or caught
        if capture is not None and camera_started is not None:
            try:
                camera_finished = capture.finish(
                    action_started_monotonic=action_started,
                    action_stopped_monotonic=action_stopped,
                    post_roll_seconds=POST_ROLL_SECONDS,
                )
            except Exception as caught:
                error = error or caught

    postflight: dict[str, Any] | None = None
    try:
        postflight = (preflight_fn or _default_preflight)()
        _require(
            _identity_from_preflight(postflight) == identity
            and postflight.get("physical_follower_torque_enabled") is False,
            "post-execution follower torque-off identity check failed",
        )
    except Exception as caught:
        error = error or caught
    if error is not None:
        raise GeometricPhysicalGatewayError(
            f"geometric physical replay stopped safely with torque off: {error}"
        ) from error
    _require(
        completed == len(physical_actions),
        "geometric physical replay did not send every frozen sample",
    )
    _require(
        camera_finished is not None and _camera_completed(camera_finished),
        "native dual-camera capture did not complete both streams",
    )

    receipt = {
        "schema_version": EXECUTION_SCHEMA,
        "status": "completed_geometric_physical_command_replay",
        "packet_path": str(packet_path),
        "packet_sha256": sha256_file(packet_path),
        "review_path": str(review_path),
        "review_sha256": sha256_file(review_path),
        "source_recording_id": packet["source_episode"]["recording_id"],
        "source_action_sha256": packet["source_action_payload"]["sha256"],
        "physical_action_sha256": packet[
            "frozen_physical_action_payload"
        ]["sha256"],
        "actions_path": str(actions_path),
        "actions_sha256": sha256_file(actions_path),
        "joint_samples_path": str(samples_path),
        "joint_samples_sha256": sha256_file(samples_path),
        "completed_samples": completed,
        "camera_started": camera_started,
        "camera_finished": camera_finished,
        "postflight": {
            "hardware_identity": identity,
            "physical_follower_torque_enabled": False,
        },
        "physical_motion_commanded": True,
        "physical_follower_torque_enabled": False,
        "tracking_or_stall_failure_observed": False,
        "physical_task_consequence_admitted": False,
        "physical_authority": False,
        "stop_before_unreviewed_robot_command": True,
    }
    _write_once(output_path, receipt)
    return receipt
