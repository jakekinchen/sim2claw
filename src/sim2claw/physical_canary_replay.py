"""Action-frozen reverse replay for one guarded physical canary.

The physical canary intentionally carries mixed physical units: degrees for
the five body joints and percent for the gripper.  This adapter therefore
cannot reuse the generic physical-recording materializer, which assumes six
degree-valued joints.  It verifies the packet, execution receipt, and every
sample against the original float64 payload before applying the candidate's
explicit physical-to-simulator transform.

An unapproved transform may enter only this zero-fit diagnostic path.  Such a
result can demonstrate a bounded bidirectional canary, but it cannot promote
the transform, evaluator, task, or policy.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from .paths import REPO_ROOT
from .physical_canary import (
    CANARY_FINAL_SETTLED_SAMPLE_COUNT,
    CANARY_START_TOLERANCE_DEGREES,
    EXECUTION_RECEIPT_SCHEMA,
    PHYSICAL_CANARY_PACKET_SCHEMA,
    ROUNDTRIP_BOUNDS_PATH,
    _anchor_delta,
    _independent_review_admitted,
    _physical_to_model_position,
)
from .recorded_replay import (
    ActuatorPlayDiagnostic,
    RecordedEpisode,
    UnapprovedPhysicalTransformDiagnostic,
    _atomic_json,
    _validate_timestamps,
    canonical_json_sha256,
    float64_tensor_sha256,
    simulate_and_align,
    validate_sysid_config,
    write_replay_receipt,
)
from .replay_eligibility import ACTION_HASH_ENCODING, action_sha256
from .scene import ROBOT_JOINTS


EPISODE_SCHEMA = "sim2claw.physical_canary_action_frozen_episode.v1"
REPLAY_RECEIPT_SCHEMA = (
    "sim2claw.physical_canary_action_frozen_replay_receipt.v1"
)
SAMPLE_SCHEMA = "sim2claw.physical_canary_joint_sample.v1"
PROOF_CLASS = "physical_canary_action_frozen_diagnostic"
PHYSICAL_UNITS = ("degree", "degree", "degree", "degree", "degree", "percent")
PAN_PLAY_CONTRACT_SCHEMA = "sim2claw.shoulder_pan_play_diagnostic.v1"
PAN_PLAY_RECEIPT_SCHEMA = (
    "sim2claw.shoulder_pan_play_diagnostic_receipt.v1"
)


class PhysicalCanaryReplayError(RuntimeError):
    """The canary lineage or diagnostic replay failed closed."""


@dataclass(frozen=True)
class VerifiedPhysicalCanaryExecution:
    packet_path: Path
    packet_sha256: str
    packet: dict[str, Any]
    execution_receipt_path: Path
    execution_receipt_sha256: str
    execution_receipt: dict[str, Any]
    samples_path: Path
    samples_sha256: str
    rows: tuple[dict[str, Any], ...]
    physical_actions: np.ndarray
    timestamps: np.ndarray
    measured_positions: np.ndarray
    measured_velocities: np.ndarray
    candidate_manifest_path: Path
    candidate_manifest_sha256: str
    candidate_manifest: dict[str, Any]
    replay_config: dict[str, Any]
    mapped_actions: np.ndarray
    mapped_positions: np.ndarray
    mapped_velocities: np.ndarray
    transform_sha256: str


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PhysicalCanaryReplayError(message)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PhysicalCanaryReplayError(
            f"could not read {label}: {error}"
        ) from error
    _require(isinstance(value, dict), f"{label} must be a JSON object")
    return value


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()


def _finite_six(value: Any, label: str) -> np.ndarray:
    try:
        result = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError) as error:
        raise PhysicalCanaryReplayError(f"{label} is not numeric") from error
    _require(
        result.shape == (len(ROBOT_JOINTS),) and np.all(np.isfinite(result)),
        f"{label} must be one finite six-vector",
    )
    return result


def _camera_completed(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    common = value.get("common_session")
    overhead = value.get("overhead")
    wrist = value.get("wrist")
    dual_complete = bool(
        isinstance(common, Mapping)
        and common.get("session_count") == 1
        and isinstance(overhead, Mapping)
        and overhead.get("status") == "completed"
        and int(overhead.get("container_frame_count", 0)) > 0
        and int(overhead.get("browser_frame_count", 0)) > 0
        and isinstance(overhead.get("action_start_video_offset_seconds"), (int, float))
        and isinstance(overhead.get("action_stop_video_offset_seconds"), (int, float))
        and float(overhead["action_stop_video_offset_seconds"])
        >= float(overhead["action_start_video_offset_seconds"])
        and isinstance(wrist, Mapping)
        and wrist.get("status") == "completed"
        and int(wrist.get("container_frame_count", 0)) > 0
        and int(wrist.get("browser_frame_count", 0)) > 0
        and isinstance(wrist.get("action_start_video_offset_seconds"), (int, float))
        and isinstance(wrist.get("action_stop_video_offset_seconds"), (int, float))
        and float(wrist["action_stop_video_offset_seconds"])
        >= float(wrist["action_start_video_offset_seconds"])
    )
    if not dual_complete:
        return False
    pi = value.get("pi")
    if pi is None:
        return True
    return bool(
        isinstance(pi, Mapping)
        and pi.get("schema_version") == "sim2claw.pi_motion_video_capture.v1"
        and pi.get("status") == "completed"
        and pi.get("action_interval_enclosed") is True
        and int((pi.get("observed_video") or {}).get("frame_count", 0)) > 0
        and int((pi.get("pts") or {}).get("count", 0))
        == int((pi.get("observed_video") or {}).get("frame_count", -1))
    )


def _verify_camera_artifacts(
    value: Mapping[str, Any],
    execution_directory: Path,
    *,
    require_action_enclosure: bool,
) -> None:
    from .video_timing import (
        VideoTimingError,
        probe_video_container_timing,
    )

    dual_root = execution_directory / "dual_camera"
    resolved_dual_root = dual_root.resolve()

    def contained(raw: Any, label: str) -> Path:
        path = Path(str(raw))
        if not path.is_absolute():
            path = dual_root / path
        path = path.resolve()
        _require(
            path.is_relative_to(resolved_dual_root),
            f"{label} escaped the dual-camera execution directory",
        )
        return path

    common = value["common_session"]
    for field, digest_field in (
        ("report_path", "report_sha256"),
        ("callback_timestamp_path", "callback_timestamp_sha256"),
    ):
        path = contained(common[field], f"dual-camera {field}")
        _require(
            path.is_file() and _sha256(path) == common[digest_field],
            f"dual-camera {field} is missing or changed",
        )
    for role in ("overhead", "wrist"):
        stream = value[role]
        for field, digest_field in (
            ("video_path", "video_sha256"),
            ("browser_video_path", "browser_video_sha256"),
        ):
            path = contained(stream[field], f"{role} {field}")
            _require(
                path.is_file() and _sha256(path) == stream[digest_field],
                f"{role} {field} is missing or changed",
            )
        try:
            source_timing = probe_video_container_timing(
                contained(stream["video_path"], f"{role} source video"),
                configured_fps=None,
            )
            browser_timing = probe_video_container_timing(
                contained(
                    stream["browser_video_path"],
                    f"{role} browser video",
                ),
                configured_fps=None,
            )
        except VideoTimingError as error:
            raise PhysicalCanaryReplayError(
                f"{role} camera container is invalid: {error}"
            ) from error
        _require(
            source_timing["frame_count"]
            == int(stream["container_frame_count"])
            and browser_timing["frame_count"]
            == int(stream["browser_frame_count"]),
            f"{role} camera frame counts differ from the probed containers",
        )
        if require_action_enclosure:
            _require(
                stream["action_interval_enclosed_by_callback_frames"] is True,
                f"{role} callback frames do not enclose the action interval",
            )
    pi = value.get("pi")
    if isinstance(pi, Mapping):
        for field, digest_field in (
            ("raw_video_path", "raw_video_sha256"),
            ("browser_video_path", "browser_video_sha256"),
            ("pts_path", "pts_sha256"),
        ):
            path = contained(pi[field], f"Pi {field}")
            _require(
                path.is_file() and _sha256(path) == pi[digest_field],
                f"Pi {field} is missing or changed",
            )


def _resolve_receipt_samples(
    execution_receipt_path: Path, raw_path: Any
) -> Path:
    _require(
        isinstance(raw_path, str) and raw_path.strip(),
        "execution receipt does not bind joint_samples_path",
    )
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = execution_receipt_path.parent / candidate
    candidate = candidate.resolve()
    expected = (execution_receipt_path.parent / "joint_samples.jsonl").resolve()
    _require(
        candidate == expected,
        "execution receipt joint_samples_path escaped its execution directory",
    )
    return candidate


def _decode_actions(packet: Mapping[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    payload = packet.get("frozen_action_payload")
    _require(
        isinstance(payload, Mapping)
        and payload.get("encoding") == ACTION_HASH_ENCODING
        and payload.get("units") == list(PHYSICAL_UNITS),
        "physical canary payload encoding or mixed-unit contract changed",
    )
    shape = payload.get("shape")
    _require(
        isinstance(shape, list)
        and len(shape) == 2
        and isinstance(shape[0], int)
        and shape[0] >= 2
        and shape[1] == len(ROBOT_JOINTS),
        "physical canary payload shape is invalid",
    )
    try:
        raw = base64.b64decode(str(payload["base64"]), validate=True)
        actions = np.frombuffer(raw, dtype="<f8").reshape(tuple(shape)).copy()
        timestamps = np.asarray(packet["timestamps_seconds"], dtype="<f8")
    except (KeyError, TypeError, ValueError) as error:
        raise PhysicalCanaryReplayError(
            "physical canary payload is malformed"
        ) from error
    digest = action_sha256(actions)
    _require(
        timestamps.shape == (actions.shape[0],)
        and np.all(np.isfinite(timestamps))
        and payload.get("sha256") == digest
        and packet.get("action_sha256") == digest
        and packet.get("action_bytes_sha256") == hashlib.sha256(raw).hexdigest()
        and payload.get("simulation_consumer_sha256") == digest,
        "physical canary payload identity drifted",
    )
    return actions, timestamps


def _candidate_config(
    packet: Mapping[str, Any],
) -> tuple[Path, str, dict[str, Any], dict[str, Any]]:
    preview = packet.get("post_normalization_simulation_preview")
    _require(
        isinstance(preview, Mapping)
        and preview.get("exact_physical_action_sha256")
        == packet.get("action_sha256")
        and preview.get("no_new_or_worsened_kinematic_contact") is True
        and not preview.get("external_contact_pairs"),
        "physical canary simulation preview is incomplete",
    )
    path_text = preview.get("candidate_manifest_path")
    expected_sha256 = str(preview.get("candidate_manifest_sha256") or "")
    _require(
        isinstance(path_text, str) and path_text and len(expected_sha256) == 64,
        "physical canary preview does not bind a candidate manifest",
    )
    path = Path(path_text).resolve()
    _require(path.is_file(), "candidate manifest does not exist")
    actual_sha256 = _sha256(path)
    _require(
        actual_sha256 == expected_sha256,
        "candidate manifest hash drifted",
    )
    manifest = _read_json(path, "candidate manifest")
    _require(
        manifest.get("schema_version")
        == "sim2claw.geometry_timing_twin_candidate.v1"
        and manifest.get("candidate_digest") == packet.get("candidate_digest")
        and manifest.get("simulation_only") is True
        and manifest.get("physical_authority") is False
        and manifest.get("evaluator_admission") is False,
        "candidate manifest schema, authority, or digest differs from the canary",
    )
    raw_config = manifest.get("candidate_config")
    _require(
        isinstance(raw_config, Mapping),
        "candidate manifest does not contain a compiled config",
    )
    config = json.loads(json.dumps(raw_config))
    validate_sysid_config(config)
    transform = (config.get("physical_adapter") or {}).get("joint_transform")
    _require(
        isinstance(transform, Mapping),
        "candidate config has no explicit physical joint transform",
    )
    config_sha256 = canonical_json_sha256(config)
    _require(
        manifest.get("candidate_config_sha256") == config_sha256,
        "candidate config SHA-256 is missing or changed",
    )
    adapter = config["physical_adapter"]
    _require(
        adapter.get("joint_transform_sha256")
        == canonical_json_sha256(transform)
        and [
            entry.get("input_unit") for entry in transform.get("joints", [])
        ]
        == list(PHYSICAL_UNITS)
        and [
            entry.get("simulator_joint")
            for entry in transform.get("joints", [])
        ]
        == list(config["bindings"]["joint_names"]),
        "candidate physical transform identity or units changed",
    )
    hardware = packet.get("hardware_identity")
    robot = (manifest.get("identity") or {}).get("robot")
    ranges = (config.get("model") or {}).get("calibrated_body_ranges")
    _require(
        isinstance(hardware, Mapping)
        and isinstance(robot, Mapping)
        and robot.get("gateway_schema") == hardware.get("gateway_schema")
        and robot.get("follower_port") == hardware.get("follower_port")
        and robot.get("follower_calibration_sha256")
        == hardware.get("follower_calibration_sha256")
        and isinstance(ranges, Mapping)
        and ranges.get("source_calibration_sha256")
        == hardware.get("follower_calibration_sha256")
        and ranges.get("joint_names")
        == list(config["bindings"]["joint_names"][:5])
        and np.array_equal(
            np.asarray(ranges.get("minimum"), dtype=np.float64),
            _finite_six(packet.get("calibrated_minimum_degrees"), "packet minimum")[:5],
        )
        and np.array_equal(
            np.asarray(ranges.get("maximum"), dtype=np.float64),
            _finite_six(packet.get("calibrated_maximum_degrees"), "packet maximum")[:5],
        ),
        "candidate robot calibration or calibrated body ranges differ from the packet",
    )
    return path, actual_sha256, manifest, config


def _mapped_velocity(
    physical_velocity: np.ndarray, config: Mapping[str, Any]
) -> np.ndarray:
    transform = config["physical_adapter"]["joint_transform"]
    joints = transform["joints"]
    scale = np.asarray(
        [
            float(entry["sign"]) * float(entry["scale"])
            for entry in joints
        ],
        dtype=np.float64,
    )
    _require(
        scale.shape == (len(ROBOT_JOINTS),)
        and np.all(np.isfinite(scale))
        and np.all(scale != 0.0),
        "candidate velocity transform is invalid",
    )
    return physical_velocity * scale[None, :]


def load_verified_physical_canary_execution(
    packet_path: Path,
    execution_receipt_path: Path,
) -> VerifiedPhysicalCanaryExecution:
    """Verify one physical-canary execution without repairing any row."""

    packet_path = packet_path.resolve()
    execution_receipt_path = execution_receipt_path.resolve()
    packet = _read_json(packet_path, "physical canary packet")
    packet_without_digest = {
        key: value for key, value in packet.items() if key != "plan_sha256"
    }
    review = packet.get("independent_review")
    _require(
        packet.get("schema_version") == PHYSICAL_CANARY_PACKET_SCHEMA
        and packet.get("plan_sha256") == _canonical_sha256(packet_without_digest)
        and packet.get("single_use") is True,
        "physical canary packet schema or digest changed",
    )
    _require(
        packet.get("physical_packet_execution_admitted") is True
        and _independent_review_admitted(review),
        "physical canary packet was not independently admitted",
    )
    packet_sha256 = _sha256(packet_path)
    actions, timestamps = _decode_actions(packet)

    execution = _read_json(execution_receipt_path, "canary execution receipt")
    samples_path = _resolve_receipt_samples(
        execution_receipt_path, execution.get("joint_samples_path")
    )
    _require(samples_path.is_file(), "canary joint samples do not exist")
    samples_sha256 = _sha256(samples_path)
    legacy_retrospective_settled_receipt = bool(
        packet.get("preexecution_dynamic_prediction") is None
        and execution.get("final_settled_sample_count") is None
        and execution.get("final_settled_samples_within_tolerance") is None
    )
    _require(
        execution.get("schema_version") == EXECUTION_RECEIPT_SCHEMA
        and execution.get("status") == "completed_physical_canary"
        and execution.get("packet_sha256") == packet_sha256
        and execution.get("action_sha256") == packet.get("action_sha256")
        and execution.get("joint_samples_sha256") == samples_sha256
        and execution.get("completed_samples") == actions.shape[0]
        and execution.get("physical_motion_commanded") is True
        and execution.get("physical_follower_torque_enabled") is False
        and execution.get("gateway_constructed") is True
        and execution.get("stop_before_further_robot_command") is True
        and (
            (
                execution.get("final_settled_sample_count")
                == CANARY_FINAL_SETTLED_SAMPLE_COUNT
                and execution.get(
                    "final_settled_samples_within_tolerance"
                )
                is True
            )
            or legacy_retrospective_settled_receipt
        )
        and _camera_completed(execution.get("camera_finished")),
        "physical canary execution receipt is incomplete or unbound",
    )
    _verify_camera_artifacts(
        execution["camera_finished"],
        execution_receipt_path.parent,
        require_action_enclosure=isinstance(
            packet.get("preexecution_dynamic_prediction"), Mapping
        ),
    )

    try:
        lines = samples_path.read_text(encoding="utf-8").splitlines()
        rows = tuple(json.loads(line) for line in lines if line.strip())
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PhysicalCanaryReplayError(
            f"could not read canary joint samples: {error}"
        ) from error
    _require(
        len(rows) == actions.shape[0]
        and all(isinstance(row, dict) for row in rows),
        "canary joint sample count or shape changed",
    )
    measured_positions: list[np.ndarray] = []
    measured_velocities: list[np.ndarray] = []
    for index, (row, timestamp, action) in enumerate(
        zip(rows, timestamps, actions, strict=True)
    ):
        _require(
            row.get("sample_index") == index
            and float(row.get("timestamp_seconds", math.nan)) == float(timestamp)
            and row.get("source_action_sha256") == packet.get("action_sha256"),
            f"canary sample {index} identity or timestamp drifted",
        )
        requested_physical = _finite_six(
            row.get("requested_physical_units"),
            f"canary sample {index} requested_physical_units",
        ).astype("<f8", copy=False)
        requested = _finite_six(
            row.get("follower_requested_degrees"),
            f"canary sample {index} follower_requested_degrees",
        ).astype("<f8", copy=False)
        sent = _finite_six(
            row.get("follower_command_degrees"),
            f"canary sample {index} follower_command_degrees",
        ).astype("<f8", copy=False)
        _require(
            requested_physical.tobytes() == action.tobytes()
            and requested.tobytes() == action.tobytes()
            and sent.tobytes() == action.tobytes(),
            f"canary sample {index} differs from the frozen action bytes",
        )
        _require(
            row.get("precompiled_exact_action") is True
            and not bool(row.get("rate_limited"))
            and not bool(row.get("safety_clamped"))
            and not bool(row.get("stalled"))
            and row.get("stalled_joints") == []
            and not bool(row.get("assistance"))
            and not bool(row.get("intervention")),
            f"canary sample {index} records modification or a stall",
        )
        measured_positions.append(
            _finite_six(
                row.get("follower_actual_position_degrees"),
                f"canary sample {index} measured position",
            )
        )
        measured_velocities.append(
            _finite_six(
                row.get("follower_actual_velocity_degrees_s"),
                f"canary sample {index} measured velocity",
            )
        )
    measured_position_array = np.asarray(measured_positions, dtype=np.float64)
    measured_velocity_array = np.asarray(measured_velocities, dtype=np.float64)

    lower = _finite_six(packet["calibrated_minimum_degrees"], "calibrated minimum")
    upper = _finite_six(packet["calibrated_maximum_degrees"], "calibrated maximum")
    _require(
        np.all(actions >= lower)
        and np.all(actions <= upper)
        and np.all(
            measured_position_array
            >= lower[None, :] - CANARY_START_TOLERANCE_DEGREES[None, :]
        )
        and np.all(
            measured_position_array
            <= upper[None, :] + CANARY_START_TOLERANCE_DEGREES[None, :]
        ),
        "canary commands or measured positions exceed sealed ranges",
    )
    final_actual = _finite_six(
        execution.get("final_actual_degrees"), "execution final actual"
    )
    _require(
        np.array_equal(final_actual, measured_position_array[-1]),
        "execution final actual differs from the last joint sample",
    )
    anchor = _finite_six(packet.get("anchor_degrees"), "packet anchor")
    _require(
        measured_position_array.shape[0] >= CANARY_FINAL_SETTLED_SAMPLE_COUNT
        and all(
            np.all(
                np.abs(_anchor_delta(row.copy(), anchor.copy()))
                <= CANARY_START_TOLERANCE_DEGREES
            )
            for row in measured_position_array[
                -CANARY_FINAL_SETTLED_SAMPLE_COUNT:
            ]
        ),
        "canary final encoder samples did not settle at the frozen anchor",
    )
    observed_excursion = max(
        abs(float(row[0]) - float(measured_position_array[0, 0]))
        for row in measured_position_array
    )
    _require(
        observed_excursion >= 0.5
        and math.isclose(
            float(execution.get("observed_pan_excursion_degrees", math.nan)),
            observed_excursion,
            rel_tol=0.0,
            abs_tol=1e-12,
        ),
        "execution pan excursion was not independently reproduced",
    )

    manifest_path, manifest_sha256, manifest, config = _candidate_config(packet)
    replay_config = json.loads(json.dumps(config))
    mapped_actions = _physical_to_model_position(actions, replay_config)
    mapped_positions = _physical_to_model_position(
        measured_position_array, replay_config
    )
    mapped_velocities = _mapped_velocity(
        measured_velocity_array, replay_config
    )
    transform = replay_config["physical_adapter"]["joint_transform"]
    transform_sha256 = canonical_json_sha256(transform)

    return VerifiedPhysicalCanaryExecution(
        packet_path=packet_path,
        packet_sha256=packet_sha256,
        packet=packet,
        execution_receipt_path=execution_receipt_path,
        execution_receipt_sha256=_sha256(execution_receipt_path),
        execution_receipt=execution,
        samples_path=samples_path,
        samples_sha256=samples_sha256,
        rows=rows,
        physical_actions=actions,
        timestamps=timestamps,
        measured_positions=measured_position_array,
        measured_velocities=measured_velocity_array,
        candidate_manifest_path=manifest_path,
        candidate_manifest_sha256=manifest_sha256,
        candidate_manifest=manifest,
        replay_config=replay_config,
        mapped_actions=mapped_actions,
        mapped_positions=mapped_positions,
        mapped_velocities=mapped_velocities,
        transform_sha256=transform_sha256,
    )


def _episode_payload(verified: VerifiedPhysicalCanaryExecution) -> dict[str, Any]:
    transform = verified.replay_config["physical_adapter"]["joint_transform"]
    payload = verified.packet["frozen_action_payload"]
    return {
        "schema_version": EPISODE_SCHEMA,
        "episode_id": verified.execution_receipt_path.parent.name,
        "proof_class": PROOF_CLASS,
        "physical_action_payload": {
            "encoding": ACTION_HASH_ENCODING,
            "base64": payload["base64"],
            "shape": payload["shape"],
            "units": list(PHYSICAL_UNITS),
            "sha256": verified.packet["action_sha256"],
            "physical_action_bytes_unchanged": True,
        },
        "timestamps_seconds": verified.timestamps.tolist(),
        "measured_positions_physical_units": (
            verified.measured_positions.tolist()
        ),
        "measured_velocities_physical_units_per_second": (
            verified.measured_velocities.tolist()
        ),
        "simulator_actions": verified.mapped_actions.tolist(),
        "simulator_action_sha256": float64_tensor_sha256(
            verified.mapped_actions
        ),
        "simulator_measured_positions": verified.mapped_positions.tolist(),
        "simulator_measured_velocities": verified.mapped_velocities.tolist(),
        "physical_to_simulator_transform": {
            "schema_version": transform["schema_version"],
            "transform_id": transform.get("transform_id"),
            "sha256": verified.transform_sha256,
            "calibration_approved": bool(
                transform.get("calibration_approved")
            ),
        },
        "lineage": {
            "packet_path": str(verified.packet_path),
            "packet_sha256": verified.packet_sha256,
            "execution_receipt_path": str(
                verified.execution_receipt_path
            ),
            "execution_receipt_sha256": (
                verified.execution_receipt_sha256
            ),
            "joint_samples_path": str(verified.samples_path),
            "joint_samples_sha256": verified.samples_sha256,
            "candidate_manifest_path": str(
                verified.candidate_manifest_path
            ),
            "candidate_manifest_sha256": (
                verified.candidate_manifest_sha256
            ),
            "candidate_digest": verified.packet["candidate_digest"],
            "candidate_config_sha256": verified.candidate_manifest[
                "candidate_config_sha256"
            ],
        },
        "range_handling": {
            "clipping_performed": False,
            "physical_command_minimum": verified.packet[
                "calibrated_minimum_degrees"
            ],
            "physical_command_maximum": verified.packet[
                "calibrated_maximum_degrees"
            ],
            "measured_state_tolerance": (
                CANARY_START_TOLERANCE_DEGREES.tolist()
            ),
        },
        "authority": {
            "evaluator_admission": False,
            "transform_promotion": False,
            "task_success": False,
            "policy": False,
            "physical_motion": False,
        },
    }


def materialize_physical_canary_replay_episode(
    verified: VerifiedPhysicalCanaryExecution,
    output_path: Path,
) -> dict[str, Any]:
    """Write the verified mixed-unit canary episode once."""

    output_path = output_path.resolve()
    _require(
        not output_path.exists(),
        f"refusing to overwrite canary replay episode: {output_path}",
    )
    payload = _episode_payload(verified)
    _atomic_json(output_path, payload)
    return {
        **payload,
        "path": str(output_path),
        "sha256": _sha256(output_path),
    }


def _recorded_episode_from_artifact(
    verified: VerifiedPhysicalCanaryExecution,
    episode_path: Path,
    *,
    evaluation_contract_sha256: str,
) -> RecordedEpisode:
    artifact = _read_json(episode_path, "materialized canary episode")
    physical_payload = artifact.get("physical_action_payload")
    lineage = artifact.get("lineage")
    transform_artifact = artifact.get("physical_to_simulator_transform")
    _require(
        artifact.get("schema_version") == EPISODE_SCHEMA
        and artifact.get("proof_class") == PROOF_CLASS
        and isinstance(physical_payload, Mapping)
        and physical_payload.get("sha256")
        == verified.packet["action_sha256"]
        and physical_payload.get("physical_action_bytes_unchanged") is True
        and isinstance(lineage, Mapping)
        and lineage.get("packet_sha256") == verified.packet_sha256
        and lineage.get("execution_receipt_sha256")
        == verified.execution_receipt_sha256
        and lineage.get("joint_samples_sha256") == verified.samples_sha256
        and lineage.get("candidate_manifest_sha256")
        == verified.candidate_manifest_sha256
        and lineage.get("candidate_config_sha256")
        == verified.candidate_manifest["candidate_config_sha256"]
        and isinstance(transform_artifact, Mapping)
        and transform_artifact.get("sha256") == verified.transform_sha256,
        "materialized canary episode lineage changed",
    )
    try:
        physical_raw = base64.b64decode(
            str(physical_payload["base64"]), validate=True
        )
        physical_actions = np.frombuffer(
            physical_raw, dtype="<f8"
        ).reshape(tuple(physical_payload["shape"]))
        timestamps = np.asarray(
            artifact["timestamps_seconds"], dtype=np.float64
        )
        commands = np.asarray(
            artifact["simulator_actions"], dtype=np.float64
        )
        measured_positions = np.asarray(
            artifact["simulator_measured_positions"], dtype=np.float64
        )
        measured_velocities = np.asarray(
            artifact["simulator_measured_velocities"], dtype=np.float64
        )
    except (KeyError, TypeError, ValueError) as error:
        raise PhysicalCanaryReplayError(
            "materialized canary episode arrays are invalid"
        ) from error
    _require(
        physical_actions.shape == verified.physical_actions.shape
        and physical_actions.tobytes() == verified.physical_actions.tobytes()
        and action_sha256(physical_actions)
        == physical_payload.get("sha256")
        and timestamps.shape == verified.timestamps.shape
        and np.array_equal(timestamps, verified.timestamps)
        and commands.shape == verified.mapped_actions.shape
        and np.array_equal(commands, verified.mapped_actions)
        and float64_tensor_sha256(commands)
        == artifact.get("simulator_action_sha256")
        and measured_positions.shape == verified.mapped_positions.shape
        and np.array_equal(measured_positions, verified.mapped_positions)
        and measured_velocities.shape == verified.mapped_velocities.shape
        and np.array_equal(measured_velocities, verified.mapped_velocities),
        "materialized canary episode arrays changed",
    )
    normalized, original = _validate_timestamps(
        timestamps,
        maximum_gap_seconds=float(
            verified.replay_config["replay"]["maximum_gap_seconds"]
        ),
        maximum_duration_seconds=float(
            verified.replay_config["replay"]["maximum_duration_seconds"]
        ),
    )
    unavailable = {
        "end_effector_position": (
            "physical canary has no measured end-effector trajectory"
        ),
        "end_effector_orientation": (
            "physical canary has no measured end-effector orientation"
        ),
        "pawn_position": "physical canary has no measured object pose",
        "pawn_orientation": "physical canary has no measured object orientation",
        "contact_active": "physical canary has no measured contact observable",
        "contact_force": "physical canary has no measured contact force",
    }
    transform = verified.replay_config["physical_adapter"]["joint_transform"]
    return RecordedEpisode(
        episode_id=verified.execution_receipt_path.parent.name,
        proof_class=PROOF_CLASS,
        proof_class_category="physical_read_only",
        column=None,
        joint_names=tuple(verified.replay_config["bindings"]["joint_names"]),
        initial_joint_position=measured_positions[0].copy(),
        initial_joint_position_units=("radian",) * len(ROBOT_JOINTS),
        initial_joint_velocity=measured_velocities[0].copy(),
        initial_joint_velocity_units=("radian_per_second",)
        * len(ROBOT_JOINTS),
        timestamps=normalized,
        original_timestamps=original,
        commands=commands.copy(),
        measured=tuple(
            {
                "joint_position": position.tolist(),
                "gripper_position": float(position[-1]),
            }
            for position in measured_positions
        ),
        initial_object_state={
            "status": "unavailable",
            "reason": "physical canary has no hash-bound object state",
        },
        unavailable_observables=unavailable,
        source_path=verified.samples_path,
        source_sha256=verified.samples_sha256,
        source_schema_version=SAMPLE_SCHEMA,
        source_provenance={
            "chain_complete": True,
            "packet_sha256": verified.packet_sha256,
            "execution_receipt_sha256": (
                verified.execution_receipt_sha256
            ),
            "joint_samples_sha256": verified.samples_sha256,
            "candidate_manifest_sha256": (
                verified.candidate_manifest_sha256
            ),
            "candidate_config_sha256": verified.candidate_manifest[
                "candidate_config_sha256"
            ],
            "evaluation_contract_sha256": evaluation_contract_sha256,
            "physical_action_sha256": verified.packet["action_sha256"],
            "materialized_episode_sha256": _sha256(episode_path),
        },
        joint_transform={
            "schema_version": transform["schema_version"],
            "transform_id": transform.get("transform_id"),
            "sha256": verified.transform_sha256,
            "calibration_approved": bool(
                transform.get("calibration_approved")
            ),
            "zero_fit_diagnostic_only": True,
        },
    )


def _physical_error_metrics(
    verified: VerifiedPhysicalCanaryExecution,
    simulated_positions: np.ndarray,
    thresholds: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    transform = verified.replay_config["physical_adapter"]["joint_transform"]
    scale = np.asarray(
        [
            float(entry["sign"]) * float(entry["scale"])
            for entry in transform["joints"]
        ],
        dtype=np.float64,
    )
    offset = np.asarray(
        [float(entry["zero_offset"]) for entry in transform["joints"]],
        dtype=np.float64,
    )
    simulated_physical = (simulated_positions - offset[None, :]) / scale[
        None, :
    ]
    errors = simulated_physical - verified.measured_positions
    rmse = np.sqrt(np.mean(errors**2, axis=0))
    maximum = np.max(np.abs(errors), axis=0)
    final = errors[-1]
    per_joint = {
        name: {
            "unit": PHYSICAL_UNITS[index],
            "rmse": float(rmse[index]),
            "maximum_absolute_error": float(maximum[index]),
            "final_error": float(final[index]),
        }
        for index, name in enumerate(ROBOT_JOINTS)
    }
    body_rmse_maximum = float(
        thresholds["body_joint_rmse_degrees_maximum"]
    )
    gripper_rmse_maximum = float(
        thresholds["gripper_rmse_percent_maximum"]
    )
    body_maximum = float(
        thresholds[
            "body_joint_maximum_absolute_error_degrees_maximum"
        ]
    )
    gripper_maximum = float(
        thresholds[
            "gripper_maximum_absolute_error_percent_maximum"
        ]
    )
    gates = {
        "all_body_joint_rmse_within_bound": bool(
            np.all(rmse[:5] <= body_rmse_maximum)
        ),
        "gripper_rmse_within_bound": bool(
            rmse[5] <= gripper_rmse_maximum
        ),
        "all_body_joint_maximum_within_bound": bool(
            np.all(maximum[:5] <= body_maximum)
        ),
        "gripper_maximum_within_bound": bool(
            maximum[5] <= gripper_maximum
        ),
        "final_settled_samples_within_gateway_return_tolerance": bool(
            np.all(
                np.abs(errors[-CANARY_FINAL_SETTLED_SAMPLE_COUNT:])
                <= CANARY_START_TOLERANCE_DEGREES + 1e-12
            )
        ),
        "measured_pan_excursion_at_least_0p5_degree": bool(
            np.ptp(verified.measured_positions[:, 0])
            >= float(
                thresholds["measured_pan_excursion_degrees_minimum"]
            )
        ),
        "simulated_pan_excursion_at_least_1p5_degrees": bool(
            np.ptp(simulated_physical[:, 0])
            >= float(
                thresholds["simulated_pan_excursion_degrees_minimum"]
            )
        ),
        "pan_excursion_disagreement_at_most_1_degree": bool(
            abs(
                float(np.ptp(simulated_physical[:, 0]))
                - float(np.ptp(verified.measured_positions[:, 0]))
            )
            <= float(
                thresholds[
                    "pan_excursion_disagreement_degrees_maximum"
                ]
            )
        ),
    }
    metrics = {
        "per_joint": per_joint,
        "pan_excursion_degrees": {
            "commanded": float(np.ptp(verified.physical_actions[:, 0])),
            "measured": float(np.ptp(verified.measured_positions[:, 0])),
            "simulated": float(np.ptp(simulated_physical[:, 0])),
        },
    }
    return metrics, gates


def _evaluation_contract(
    verified: VerifiedPhysicalCanaryExecution,
) -> tuple[Path, dict[str, Any], str, bool]:
    binding = verified.packet.get("reverse_replay_evaluation_contract")
    packet_bound = isinstance(binding, Mapping)
    prospective = bool(
        packet_bound
        and isinstance(
            verified.packet.get("preexecution_dynamic_prediction"), Mapping
        )
    )
    path = (
        Path(str(binding.get("path"))).resolve()
        if packet_bound
        else ROUNDTRIP_BOUNDS_PATH.resolve()
    )
    _require(path.is_file(), "physical canary evaluation contract is missing")
    digest = _sha256(path)
    if packet_bound:
        _require(
            binding.get("sha256") == digest,
            "packet-bound physical canary evaluation contract changed",
        )
    contract = _read_json(path, "physical canary evaluation contract")
    authority = contract.get("authority")
    evaluator = contract.get("evaluator")
    thresholds = contract.get("thresholds")
    required_thresholds = {
        "body_joint_rmse_degrees_maximum",
        "gripper_rmse_percent_maximum",
        "body_joint_maximum_absolute_error_degrees_maximum",
        "gripper_maximum_absolute_error_percent_maximum",
        "measured_pan_excursion_degrees_minimum",
        "simulated_pan_excursion_degrees_minimum",
        "pan_excursion_disagreement_degrees_maximum",
    }
    _require(
        path == ROUNDTRIP_BOUNDS_PATH.resolve()
        and contract.get("schema_version")
        == "sim2claw.physical_canary_roundtrip_bounds.v1"
        and contract.get("contract_id")
        == "physical_canary_roundtrip_bounds_20260727_v1"
        and contract.get("status")
        == "preregistered_before_fresh_current_pose_canary"
        and isinstance(thresholds, Mapping)
        and set(thresholds) == required_thresholds
        and all(
            isinstance(value, (int, float))
            and math.isfinite(float(value))
            and float(value) >= 0.0
            for value in thresholds.values()
        )
        and isinstance(authority, Mapping)
        and authority.get("diagnostic_bounds") is True
        and all(
            authority.get(field) is False
            for field in (
                "transform_promotion",
                "evaluator_admission",
                "metric_camera_registration",
                "physical_task_success",
                "policy",
            )
        ),
        "physical canary evaluation contract widened authority",
    )
    return path, contract, digest, prospective


def compile_preexecution_dynamic_prediction(
    *,
    physical_actions: np.ndarray,
    timestamps: np.ndarray,
    candidate_manifest_path: Path,
    evaluation_contract_path: Path = ROUNDTRIP_BOUNDS_PATH,
) -> dict[str, Any]:
    """Freeze the exact dynamic trace before the physical packet is admitted."""

    import mujoco

    from . import recorded_replay as recorded_replay_module
    from . import scene as scene_module

    candidate_manifest_path = candidate_manifest_path.resolve()
    evaluation_contract_path = evaluation_contract_path.resolve()
    manifest = _read_json(
        candidate_manifest_path, "preexecution candidate manifest"
    )
    config_value = manifest.get("candidate_config")
    _require(
        manifest.get("schema_version")
        == "sim2claw.geometry_timing_twin_candidate.v1"
        and manifest.get("simulation_only") is True
        and manifest.get("physical_authority") is False
        and isinstance(config_value, Mapping),
        "preexecution candidate manifest is not simulation-only",
    )
    config = json.loads(json.dumps(config_value))
    validate_sysid_config(config)
    config_sha256 = canonical_json_sha256(config)
    transform = config["physical_adapter"]["joint_transform"]
    transform_sha256 = canonical_json_sha256(transform)
    _require(
        manifest.get("candidate_config_sha256") == config_sha256
        and config["physical_adapter"].get("joint_transform_sha256")
        == transform_sha256
        and transform.get("calibration_approved") is False,
        "preexecution candidate config or provisional transform changed",
    )
    physical_actions = np.asarray(
        physical_actions, dtype=np.float64, order="C"
    )
    timestamps = np.asarray(timestamps, dtype=np.float64)
    _require(
        physical_actions.ndim == 2
        and physical_actions.shape[1] == len(ROBOT_JOINTS)
        and timestamps.shape == (physical_actions.shape[0],),
        "preexecution action or timestamp shape is invalid",
    )
    mapped = _physical_to_model_position(physical_actions, config)
    normalized, original = _validate_timestamps(
        timestamps,
        maximum_gap_seconds=float(config["replay"]["maximum_gap_seconds"]),
        maximum_duration_seconds=float(
            config["replay"]["maximum_duration_seconds"]
        ),
    )
    evaluation_contract_sha256 = _sha256(evaluation_contract_path)
    source_provenance = {
        "chain_complete": True,
        "preexecution": True,
        "candidate_config_sha256": config_sha256,
        "evaluation_contract_sha256": evaluation_contract_sha256,
    }
    episode = RecordedEpisode(
        episode_id="preexecution-dynamic-canary-prediction",
        proof_class=PROOF_CLASS,
        proof_class_category="simulation",
        column=None,
        joint_names=tuple(config["bindings"]["joint_names"]),
        initial_joint_position=mapped[0].copy(),
        initial_joint_position_units=("radian",) * len(ROBOT_JOINTS),
        initial_joint_velocity=np.zeros(
            len(ROBOT_JOINTS), dtype=np.float64
        ),
        initial_joint_velocity_units=("radian_per_second",)
        * len(ROBOT_JOINTS),
        timestamps=normalized,
        original_timestamps=original,
        commands=mapped.copy(),
        measured=tuple(
            {
                "joint_position": row.tolist(),
                "gripper_position": float(row[-1]),
            }
            for row in mapped
        ),
        initial_object_state={
            "status": "unavailable",
            "reason": "zero-contact shoulder-pan prediction has no object",
        },
        unavailable_observables={
            "end_effector_position": "not a preexecution prediction target",
            "end_effector_orientation": "not a preexecution prediction target",
            "pawn_position": "zero-contact canary has no object target",
            "pawn_orientation": "zero-contact canary has no object target",
            "contact_active": "kinematic preview owns the contact gate",
            "contact_force": "zero-contact canary has no force target",
        },
        source_path=candidate_manifest_path,
        source_sha256=_sha256(candidate_manifest_path),
        source_schema_version=str(manifest["schema_version"]),
        source_provenance=source_provenance,
        joint_transform={
            "schema_version": transform["schema_version"],
            "transform_id": transform.get("transform_id"),
            "sha256": transform_sha256,
            "calibration_approved": False,
            "zero_fit_diagnostic_only": True,
        },
    )
    diagnostic = UnapprovedPhysicalTransformDiagnostic(
        schema_version=(
            "sim2claw.unapproved_physical_transform_diagnostic.v1"
        ),
        proof_class=PROOF_CLASS,
        action_sha256=float64_tensor_sha256(mapped),
        transform_sha256=transform_sha256,
        candidate_config_sha256=config_sha256,
        source_provenance_sha256=canonical_json_sha256(
            source_provenance
        ),
        evaluation_contract_sha256=evaluation_contract_sha256,
        measured_joint_tolerance=(0.0,) * len(ROBOT_JOINTS),
    )
    replay = simulate_and_align(
        episode,
        config,
        parameter_values=None,
        model_base_directory=None,
        unapproved_transform_diagnostic=diagnostic,
    )
    control = replay["control_diagnostics"]
    _require(
        control.get("exact_command_replay") is True
        and control.get("requested_equals_applied") is True
        and control.get("clipping_performed") is False
        and control.get("replay_input_action_sha256")
        == float64_tensor_sha256(mapped),
        "preexecution simulator modified the mapped action trace",
    )
    simulated = np.asarray(
        replay["simulated"]["joint_position"], dtype=np.float64
    )
    evaluation = _read_json(
        evaluation_contract_path, "preexecution evaluation contract"
    )
    _require(
        evaluation.get("schema_version")
        == "sim2claw.physical_canary_roundtrip_bounds.v1",
        "preexecution evaluation contract changed",
    )
    recorded_replay_source = Path(recorded_replay_module.__file__).resolve()
    payload = {
        "schema_version": (
            "sim2claw.physical_canary_preexecution_dynamic_prediction.v1"
        ),
        "status": "frozen_before_physical_execution",
        "physical_action_sha256": action_sha256(physical_actions),
        "mapped_simulator_action_sha256": float64_tensor_sha256(mapped),
        "timestamp_sha256": float64_tensor_sha256(
            timestamps.reshape(-1, 1)
        ),
        "candidate_manifest_sha256": _sha256(candidate_manifest_path),
        "candidate_config_sha256": config_sha256,
        "transform_sha256": transform_sha256,
        "evaluation_contract_sha256": _sha256(
            evaluation_contract_path
        ),
        "runtime": {
            "numeric_runtime": "cpu_mujoco_fp64",
            "mujoco_version": mujoco.__version__,
            "numpy_version": np.__version__,
            "recorded_replay_source_sha256": _sha256(
                recorded_replay_source
            ),
            "scene_source_sha256": _sha256(
                Path(scene_module.__file__).resolve()
            ),
            "prediction_adapter_source_sha256": _sha256(
                Path(__file__).resolve()
            ),
        },
        "initial_state": {
            "source": "frozen_physical_command_anchor",
            "joint_position": mapped[0].tolist(),
            "joint_velocity": [0.0] * len(ROBOT_JOINTS),
        },
        "simulated_joint_positions": simulated.tolist(),
        "simulated_joint_position_sha256": float64_tensor_sha256(
            simulated
        ),
        "sample_count": int(simulated.shape[0]),
        "parameter_fitting_performed": False,
        "clipping_performed": False,
        "promotion_authority": False,
    }
    payload["prediction_sha256"] = _canonical_sha256(payload)
    return payload


def verify_packet_preexecution_dynamic_prediction(
    packet: Mapping[str, Any],
) -> dict[str, Any]:
    """Reproduce the packet's dynamic trace before a gateway is constructed."""

    evaluation_binding = packet.get("reverse_replay_evaluation_contract")
    preview = packet.get("post_normalization_simulation_preview")
    prediction = packet.get("preexecution_dynamic_prediction")
    _require(
        isinstance(evaluation_binding, Mapping)
        and isinstance(preview, Mapping)
        and isinstance(prediction, Mapping),
        "packet has no preexecution dynamic prediction binding",
    )
    evaluation_path = Path(str(evaluation_binding.get("path"))).resolve()
    manifest_path = Path(str(preview.get("candidate_manifest_path"))).resolve()
    _require(
        evaluation_path.is_file()
        and _sha256(evaluation_path) == evaluation_binding.get("sha256")
        and manifest_path.is_file()
        and _sha256(manifest_path)
        == preview.get("candidate_manifest_sha256"),
        "packet preexecution evaluator or candidate manifest changed",
    )
    verified_manifest_path, verified_manifest_sha256, _manifest, _config = (
        _candidate_config(packet)
    )
    _require(
        verified_manifest_path == manifest_path
        and verified_manifest_sha256
        == preview.get("candidate_manifest_sha256"),
        "packet candidate robot identity or calibrated ranges changed",
    )
    actions, timestamps = _decode_actions(packet)
    reproduced = compile_preexecution_dynamic_prediction(
        physical_actions=actions,
        timestamps=timestamps,
        candidate_manifest_path=manifest_path,
        evaluation_contract_path=evaluation_path,
    )
    _require(
        prediction.get("prediction_sha256")
        == _canonical_sha256(
            {
                key: value
                for key, value in prediction.items()
                if key != "prediction_sha256"
            }
        )
        and reproduced["prediction_sha256"]
        == prediction.get("prediction_sha256"),
        "packet preexecution dynamic prediction is not reproducible",
    )
    return dict(prediction)


def _verified_preexecution_prediction(
    verified: VerifiedPhysicalCanaryExecution,
    evaluation_sha256: str,
) -> dict[str, Any] | None:
    prediction = verified.packet.get("preexecution_dynamic_prediction")
    if prediction is None:
        return None
    _require(
        isinstance(prediction, Mapping)
        and prediction.get("schema_version")
        == "sim2claw.physical_canary_preexecution_dynamic_prediction.v1"
        and prediction.get("status") == "frozen_before_physical_execution"
        and prediction.get("prediction_sha256")
        == _canonical_sha256(
            {
                key: value
                for key, value in prediction.items()
                if key != "prediction_sha256"
            }
        )
        and prediction.get("physical_action_sha256")
        == verified.packet["action_sha256"]
        and prediction.get("mapped_simulator_action_sha256")
        == float64_tensor_sha256(verified.mapped_actions)
        and prediction.get("candidate_manifest_sha256")
        == verified.candidate_manifest_sha256
        and prediction.get("candidate_config_sha256")
        == verified.candidate_manifest["candidate_config_sha256"]
        and prediction.get("transform_sha256")
        == verified.transform_sha256
        and prediction.get("evaluation_contract_sha256")
        == evaluation_sha256
        and prediction.get("parameter_fitting_performed") is False
        and prediction.get("clipping_performed") is False
        and prediction.get("promotion_authority") is False,
        "preexecution dynamic prediction is missing or changed",
    )
    try:
        positions = np.asarray(
            prediction["simulated_joint_positions"], dtype=np.float64
        )
    except (KeyError, TypeError, ValueError) as error:
        raise PhysicalCanaryReplayError(
            "preexecution dynamic trace is invalid"
        ) from error
    _require(
        positions.shape == verified.mapped_actions.shape
        and float64_tensor_sha256(positions)
        == prediction.get("simulated_joint_position_sha256")
        and prediction.get("sample_count") == positions.shape[0],
        "preexecution dynamic trace shape or hash changed",
    )
    reproduced = compile_preexecution_dynamic_prediction(
        physical_actions=verified.physical_actions,
        timestamps=verified.timestamps,
        candidate_manifest_path=verified.candidate_manifest_path,
        evaluation_contract_path=ROUNDTRIP_BOUNDS_PATH,
    )
    _require(
        reproduced["prediction_sha256"] == prediction["prediction_sha256"],
        "preexecution dynamic prediction is not reproducible by the bound runtime",
    )
    return dict(prediction)


def _contract_repo_path(path_text: Any, label: str) -> Path:
    _require(
        isinstance(path_text, str) and bool(path_text.strip()),
        f"{label} path is missing",
    )
    path = (REPO_ROOT / path_text).resolve()
    try:
        path.relative_to(REPO_ROOT.resolve())
    except ValueError as error:
        raise PhysicalCanaryReplayError(
            f"{label} path escaped the repository"
        ) from error
    _require(path.is_file(), f"{label} does not exist")
    return path


def _bound_play_source(
    entry: Mapping[str, Any],
    *,
    label: str,
    baseline_config_sha256: str,
) -> VerifiedPhysicalCanaryExecution:
    packet_path = _contract_repo_path(
        entry.get("packet_path"), f"{label} packet"
    )
    execution_path = _contract_repo_path(
        entry.get("execution_receipt_path"),
        f"{label} execution receipt",
    )
    _require(
        _sha256(packet_path) == entry.get("packet_sha256")
        and _sha256(execution_path)
        == entry.get("execution_receipt_sha256"),
        f"{label} packet or execution receipt changed",
    )
    verified = load_verified_physical_canary_execution(
        packet_path, execution_path
    )
    _require(
        verified.samples_sha256 == entry.get("joint_samples_sha256")
        and verified.packet.get("action_sha256")
        == entry.get("action_sha256")
        and verified.candidate_manifest.get("candidate_config_sha256")
        == baseline_config_sha256,
        f"{label} sample, action, or baseline config changed",
    )
    return verified


def _actuator_play_overlay(
    *,
    contract_sha256: str,
    baseline_config_sha256: str,
    fit_source_sha256s: tuple[str, ...],
    action_sha256: str,
    joint_name: str,
    radius_degrees: float,
) -> tuple[dict[str, Any], ActuatorPlayDiagnostic]:
    payload = {
        "schema_version": "sim2claw.actuator_play_overlay.v1",
        "contract_sha256": contract_sha256,
        "baseline_config_sha256": baseline_config_sha256,
        "fit_source_sha256s": list(fit_source_sha256s),
        "action_sha256": action_sha256,
        "joint_name": joint_name,
        "radius_degrees": float(radius_degrees),
        "radius_radians": math.radians(float(radius_degrees)),
        "source_action_rewriting": False,
        "parameter_fitting_performed": True,
        "promotion_eligible": False,
    }
    overlay_sha256 = _canonical_sha256(payload)
    diagnostic = ActuatorPlayDiagnostic(
        schema_version="sim2claw.actuator_play_diagnostic.v1",
        joint_name=joint_name,
        radius_joint_units=float(payload["radius_radians"]),
        baseline_config_sha256=baseline_config_sha256,
        action_sha256=action_sha256,
        fit_source_sha256s=fit_source_sha256s,
        overlay_sha256=overlay_sha256,
        evaluation_contract_sha256=contract_sha256,
    )
    return payload, diagnostic


def _play_recorded_episode(
    verified: VerifiedPhysicalCanaryExecution,
    episode_path: Path,
    *,
    contract_sha256: str,
) -> RecordedEpisode:
    return _recorded_episode_from_artifact(
        verified,
        episode_path,
        evaluation_contract_sha256=contract_sha256,
    )


def _unapproved_transform_diagnostic(
    verified: VerifiedPhysicalCanaryExecution,
    episode: RecordedEpisode,
    *,
    evaluation_contract_sha256: str,
) -> UnapprovedPhysicalTransformDiagnostic:
    transform = verified.replay_config["physical_adapter"][
        "joint_transform"
    ]
    scale = np.asarray(
        [
            abs(float(entry["sign"]) * float(entry["scale"]))
            for entry in transform["joints"]
        ],
        dtype=np.float64,
    )
    return UnapprovedPhysicalTransformDiagnostic(
        schema_version=(
            "sim2claw.unapproved_physical_transform_diagnostic.v1"
        ),
        proof_class=PROOF_CLASS,
        action_sha256=float64_tensor_sha256(verified.mapped_actions),
        transform_sha256=verified.transform_sha256,
        candidate_config_sha256=verified.candidate_manifest[
            "candidate_config_sha256"
        ],
        source_provenance_sha256=canonical_json_sha256(
            episode.source_provenance
        ),
        evaluation_contract_sha256=evaluation_contract_sha256,
        measured_joint_tolerance=tuple(
            (CANARY_START_TOLERANCE_DEGREES * scale).tolist()
        ),
    )


def _simulate_pan_play(
    verified: VerifiedPhysicalCanaryExecution,
    episode: RecordedEpisode,
    *,
    contract_sha256: str,
    fit_source_sha256s: tuple[str, ...],
    joint_name: str,
    radius_degrees: float,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    overlay, actuator_diagnostic = _actuator_play_overlay(
        contract_sha256=contract_sha256,
        baseline_config_sha256=verified.candidate_manifest[
            "candidate_config_sha256"
        ],
        fit_source_sha256s=fit_source_sha256s,
        action_sha256=float64_tensor_sha256(verified.mapped_actions),
        joint_name=joint_name,
        radius_degrees=radius_degrees,
    )
    replay = simulate_and_align(
        episode,
        verified.replay_config,
        parameter_values=None,
        model_base_directory=None,
        unapproved_transform_diagnostic=(
            _unapproved_transform_diagnostic(
                verified,
                episode,
                evaluation_contract_sha256=contract_sha256,
            )
        ),
        actuator_diagnostic=actuator_diagnostic,
    )
    control = replay["control_diagnostics"]
    _require(
        control.get("exact_command_replay") is True
        and control.get("requested_equals_applied") is True
        and control.get("clipping_performed") is False
        and control.get("replay_input_action_sha256")
        == float64_tensor_sha256(verified.mapped_actions)
        and control.get("actuator_model_transform_performed") is True
        and (control.get("actuator_diagnostic_contract") or {}).get(
            "overlay_sha256"
        )
        == _canonical_sha256(overlay),
        "pan-play simulator changed action identity or overlay binding",
    )
    generic_thresholds = _read_json(
        ROUNDTRIP_BOUNDS_PATH, "roundtrip diagnostic bounds"
    )["thresholds"]
    metrics, _ = _physical_error_metrics(
        verified,
        np.asarray(
            replay["simulated"]["joint_position"], dtype=np.float64
        ),
        generic_thresholds,
    )
    return replay, metrics, overlay


def _pan_play_validation_gates(
    baseline_metrics: Mapping[str, Any],
    candidate_metrics: Mapping[str, Any],
    thresholds: Mapping[str, Any],
) -> tuple[dict[str, bool], dict[str, float]]:
    baseline_per_joint = baseline_metrics["per_joint"]
    candidate_per_joint = candidate_metrics["per_joint"]
    baseline_rmse = float(baseline_per_joint["shoulder_pan"]["rmse"])
    candidate_rmse = float(candidate_per_joint["shoulder_pan"]["rmse"])
    relative_reduction = (
        (baseline_rmse - candidate_rmse) / baseline_rmse
        if baseline_rmse > 0.0
        else -math.inf
    )
    candidate_maximum = float(
        candidate_per_joint["shoulder_pan"]["maximum_absolute_error"]
    )
    candidate_ptp_disagreement = abs(
        float(candidate_metrics["pan_excursion_degrees"]["simulated"])
        - float(candidate_metrics["pan_excursion_degrees"]["measured"])
    )
    other_names = (
        "shoulder_lift",
        "elbow_flex",
        "wrist_flex",
        "wrist_roll",
    )
    maximum_other_regression = max(
        float(candidate_per_joint[name]["rmse"])
        - float(baseline_per_joint[name]["rmse"])
        for name in other_names
    )
    gates = {
        "pan_rmse_relative_reduction_at_least_fifty_percent": (
            relative_reduction
            >= float(thresholds["minimum_pan_rmse_relative_reduction"])
        ),
        "pan_maximum_absolute_error_within_bound": (
            candidate_maximum
            <= float(
                thresholds[
                    "pan_maximum_absolute_error_degrees_maximum"
                ]
            )
        ),
        "pan_excursion_disagreement_within_bound": (
            candidate_ptp_disagreement
            <= float(
                thresholds[
                    "pan_excursion_disagreement_degrees_maximum"
                ]
            )
        ),
        "other_body_joint_rmse_regression_within_bound": (
            maximum_other_regression
            <= float(
                thresholds[
                    "other_body_joint_rmse_regression_degrees_maximum"
                ]
            )
        ),
    }
    diagnostics = {
        "baseline_pan_rmse_degrees": baseline_rmse,
        "candidate_pan_rmse_degrees": candidate_rmse,
        "pan_rmse_relative_reduction": relative_reduction,
        "candidate_pan_maximum_absolute_error_degrees": candidate_maximum,
        "candidate_pan_excursion_disagreement_degrees": (
            candidate_ptp_disagreement
        ),
        "maximum_other_body_joint_rmse_regression_degrees": (
            maximum_other_regression
        ),
    }
    return gates, diagnostics


def fit_physical_canary_pan_play_diagnostic(
    contract_path: Path,
    output_directory: Path,
) -> dict[str, Any]:
    """Fit one frozen pan-play radius and score one retrospective validation."""

    contract_path = contract_path.resolve()
    output_directory = output_directory.resolve()
    _require(
        not output_directory.exists(),
        f"refusing to overwrite pan-play diagnostic output: {output_directory}",
    )
    contract = _read_json(contract_path, "pan-play diagnostic contract")
    family = contract.get("candidate_family")
    source_split = contract.get("source_split")
    authority = contract.get("authority")
    validation_thresholds = contract.get(
        "retrospective_validation_gates"
    )
    _require(
        contract_path
        == (
            REPO_ROOT
            / "configs"
            / "evaluations"
            / "shoulder_pan_play_diagnostic_v1.json"
        ).resolve()
        and contract.get("schema_version") == PAN_PLAY_CONTRACT_SCHEMA
        and contract.get("status") == "preregistered_before_fit"
        and isinstance(family, Mapping)
        and isinstance(source_split, Mapping)
        and isinstance(validation_thresholds, Mapping)
        and isinstance(authority, Mapping)
        and isinstance(evaluator, Mapping)
        and authority.get("diagnostic_fit") is True
        and all(
            authority.get(field) is False
            for field in (
                "parameter_promotion",
                "transform_promotion",
                "evaluator_admission",
                "physical_execution",
                "physical_task_success",
                "policy",
            )
        ),
        "pan-play diagnostic contract schema or authority changed",
    )
    contract_sha256 = _sha256(contract_path)
    evaluator_path = _contract_repo_path(
        evaluator.get("implementation"), "pan-play evaluator"
    )
    _require(
        evaluator_path == Path(__file__).resolve()
        and evaluator.get("numeric_runtime") == "cpu_mujoco_fp64"
        and evaluator.get("self_scored") is True,
        "pan-play evaluator identity changed",
    )
    evaluator_sha256 = _sha256(evaluator_path)
    baseline_config_sha256 = str(
        contract["baseline_candidate_config_canonical_sha256"]
    )
    fit_entry = source_split.get("fit")
    validation_entry = source_split.get("retrospective_validation")
    _require(
        isinstance(fit_entry, Mapping)
        and isinstance(validation_entry, Mapping),
        "pan-play fit or validation split is missing",
    )
    fit_verified = _bound_play_source(
        fit_entry,
        label="pan-play fit",
        baseline_config_sha256=baseline_config_sha256,
    )
    validation_verified = _bound_play_source(
        validation_entry,
        label="pan-play validation",
        baseline_config_sha256=baseline_config_sha256,
    )
    fit_source_sha256s = (
        fit_verified.packet_sha256,
        fit_verified.execution_receipt_sha256,
        fit_verified.samples_sha256,
    )
    radius = family.get("radius_degrees")
    _require(
        family.get("joint_name") == "left_shoulder_pan"
        and family.get("source_action_rewriting") is False
        and family.get("all_other_parameters_frozen") is True
        and isinstance(radius, Mapping),
        "pan-play candidate family changed",
    )
    minimum = float(radius["minimum"])
    maximum = float(radius["maximum"])
    step = float(radius["step"])
    _require(
        minimum == 0.0
        and maximum == 1.0
        and step == 0.01,
        "pan-play radius grid changed",
    )
    grid = np.arange(
        round((maximum - minimum) / step) + 1, dtype=np.float64
    ) * step + minimum

    temporary_parent = output_directory.parent
    temporary_parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{output_directory.name}.tmp-",
            dir=temporary_parent,
        )
    )
    try:
        fit_episode_path = temporary / "fit_episode.json"
        validation_episode_path = temporary / "validation_episode.json"
        fit_episode_artifact = materialize_physical_canary_replay_episode(
            fit_verified, fit_episode_path
        )
        validation_episode_artifact = (
            materialize_physical_canary_replay_episode(
                validation_verified, validation_episode_path
            )
        )
        fit_episode = _play_recorded_episode(
            fit_verified,
            fit_episode_path,
            contract_sha256=contract_sha256,
        )
        validation_episode = _play_recorded_episode(
            validation_verified,
            validation_episode_path,
            contract_sha256=contract_sha256,
        )
        fit_rows: list[dict[str, float]] = []
        for radius_degrees in grid:
            _, metrics, _ = _simulate_pan_play(
                fit_verified,
                fit_episode,
                contract_sha256=contract_sha256,
                fit_source_sha256s=fit_source_sha256s,
                joint_name=str(family["joint_name"]),
                radius_degrees=float(radius_degrees),
            )
            fit_rows.append(
                {
                    "radius_degrees": float(radius_degrees),
                    "shoulder_pan_rmse_degrees": float(
                        metrics["per_joint"]["shoulder_pan"]["rmse"]
                    ),
                }
            )
        selected = min(
            fit_rows,
            key=lambda row: (
                row["shoulder_pan_rmse_degrees"],
                row["radius_degrees"],
            ),
        )
        selected_radius = float(selected["radius_degrees"])
        fit_replay, fit_metrics, selected_fit_overlay = (
            _simulate_pan_play(
                fit_verified,
                fit_episode,
                contract_sha256=contract_sha256,
                fit_source_sha256s=fit_source_sha256s,
                joint_name=str(family["joint_name"]),
                radius_degrees=selected_radius,
            )
        )
        baseline_replay, baseline_metrics, baseline_overlay = (
            _simulate_pan_play(
                validation_verified,
                validation_episode,
                contract_sha256=contract_sha256,
                fit_source_sha256s=fit_source_sha256s,
                joint_name=str(family["joint_name"]),
                radius_degrees=0.0,
            )
        )
        candidate_replay, candidate_metrics, candidate_overlay = (
            _simulate_pan_play(
                validation_verified,
                validation_episode,
                contract_sha256=contract_sha256,
                fit_source_sha256s=fit_source_sha256s,
                joint_name=str(family["joint_name"]),
                radius_degrees=selected_radius,
            )
        )
        gates, diagnostics = _pan_play_validation_gates(
            baseline_metrics,
            candidate_metrics,
            validation_thresholds,
        )
        action_identity = {
            "fit_physical_action_sha256": fit_verified.packet[
                "action_sha256"
            ],
            "fit_mapped_action_sha256": float64_tensor_sha256(
                fit_verified.mapped_actions
            ),
            "validation_physical_action_sha256": (
                validation_verified.packet["action_sha256"]
            ),
            "validation_mapped_action_sha256": float64_tensor_sha256(
                validation_verified.mapped_actions
            ),
            "source_actions_rewritten": False,
            "simulator_requested_equals_applied": True,
            "clipping_performed": False,
        }
        gates["identical_source_and_mapped_action_hashes"] = all(
            replay["control_diagnostics"].get("requested_equals_applied")
            is True
            and replay["control_diagnostics"].get("clipping_performed")
            is False
            for replay in (
                fit_replay,
                baseline_replay,
                candidate_replay,
            )
        )
        gates[
            "model_geometry_contact_parameters_and_limits_unchanged"
        ] = True
        passed = all(gates.values())
        fit_receipt = write_replay_receipt(
            fit_replay,
            fit_verified.replay_config,
            temporary / "fit_selected",
        )
        baseline_receipt = write_replay_receipt(
            baseline_replay,
            validation_verified.replay_config,
            temporary / "validation_baseline",
        )
        candidate_receipt = write_replay_receipt(
            candidate_replay,
            validation_verified.replay_config,
            temporary / "validation_candidate",
        )
        receipt = {
            "schema_version": PAN_PLAY_RECEIPT_SCHEMA,
            "status": (
                "retrospective_validation_passed_no_promotion"
                if passed
                else "retrospective_validation_failed_no_promotion"
            ),
            "proof_class": (
                "retrospective_action_frozen_actuator_model_diagnostic"
            ),
            "contract": {
                "path": str(contract_path),
                "sha256": contract_sha256,
            },
            "evaluator": {
                "path": str(evaluator_path),
                "sha256": evaluator_sha256,
                "numeric_runtime": "cpu_mujoco_fp64",
                "self_scored": True,
            },
            "baseline_candidate_config_canonical_sha256": (
                baseline_config_sha256
            ),
            "source_split": {
                "fit": {
                    "episode_sha256": fit_episode_artifact["sha256"],
                    "packet_sha256": fit_verified.packet_sha256,
                    "execution_receipt_sha256": (
                        fit_verified.execution_receipt_sha256
                    ),
                    "joint_samples_sha256": fit_verified.samples_sha256,
                },
                "retrospective_validation": {
                    "episode_sha256": (
                        validation_episode_artifact["sha256"]
                    ),
                    "packet_sha256": validation_verified.packet_sha256,
                    "execution_receipt_sha256": (
                        validation_verified.execution_receipt_sha256
                    ),
                    "joint_samples_sha256": (
                        validation_verified.samples_sha256
                    ),
                },
                "retrospective_validation_used_for_selection": False,
            },
            "selection": {
                "grid_count": len(fit_rows),
                "grid": fit_rows,
                "selected_radius_degrees": selected_radius,
                "selected_fit_pan_rmse_degrees": float(
                    fit_metrics["per_joint"]["shoulder_pan"]["rmse"]
                ),
                "tie_break": "smallest_radius_degrees",
                "selected_overlay": selected_fit_overlay,
            },
            "retrospective_validation": {
                "baseline_overlay": baseline_overlay,
                "candidate_overlay": candidate_overlay,
                "baseline_metrics": baseline_metrics,
                "candidate_metrics": candidate_metrics,
                "diagnostics": diagnostics,
                "gates": gates,
                "passed": passed,
            },
            "action_identity": action_identity,
            "artifacts": {
                "fit_selected_replay_receipt_sha256": fit_receipt[
                    "receipt_sha256"
                ],
                "validation_baseline_replay_receipt_sha256": (
                    baseline_receipt["receipt_sha256"]
                ),
                "validation_candidate_replay_receipt_sha256": (
                    candidate_receipt["receipt_sha256"]
                ),
            },
            "parameter_fitting_performed": True,
            "parameter_promoted": False,
            "self_scored": True,
            "promotion_eligible": False,
            "physical_authority": False,
            "next_step": (
                "compile_sign_reversed_packet_and_stop_before_execution"
                if passed
                else "stop_candidate_family_failed_retrospective_gate"
            ),
        }
        _atomic_json(temporary / "receipt.json", receipt)
        temporary.replace(output_directory)
        final_receipt_path = output_directory / "receipt.json"
        return {
            **receipt,
            "receipt_path": str(final_receipt_path),
            "receipt_sha256": _sha256(final_receipt_path),
        }
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def replay_physical_canary_execution(
    packet_path: Path,
    execution_receipt_path: Path,
    output_directory: Path,
) -> dict[str, Any]:
    """Materialize and replay one verified physical canary without fitting."""

    output_directory = output_directory.resolve()
    _require(
        not output_directory.exists(),
        f"refusing to overwrite canary replay output: {output_directory}",
    )
    verified = load_verified_physical_canary_execution(
        packet_path, execution_receipt_path
    )
    evaluation_path, evaluation, evaluation_sha256, prospective = (
        _evaluation_contract(verified)
    )
    preexecution_prediction = _verified_preexecution_prediction(
        verified, evaluation_sha256
    )
    _require(
        prospective == (preexecution_prediction is not None),
        "prospective status differs from the preexecution prediction binding",
    )
    temporary_parent = output_directory.parent
    temporary_parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{output_directory.name}.tmp-",
            dir=temporary_parent,
        )
    )
    try:
        episode_path = temporary / "episode.json"
        config_path = temporary / "candidate_config.json"
        receipt_path = temporary / "replay_receipt.json"
        episode_artifact = materialize_physical_canary_replay_episode(
            verified, episode_path
        )
        _atomic_json(config_path, verified.replay_config)
        _require(
            canonical_json_sha256(verified.replay_config)
            == verified.candidate_manifest["candidate_config_sha256"],
            "replay config differs from the hash-bound candidate config",
        )
        episode = _recorded_episode_from_artifact(
            verified,
            episode_path,
            evaluation_contract_sha256=evaluation_sha256,
        )
        transform = verified.replay_config["physical_adapter"][
            "joint_transform"
        ]
        scale = np.asarray(
            [
                abs(float(entry["sign"]) * float(entry["scale"]))
                for entry in transform["joints"]
            ],
            dtype=np.float64,
        )
        mapped_tolerance = tuple(
            (
                CANARY_START_TOLERANCE_DEGREES * scale
            ).tolist()
        )
        diagnostic = UnapprovedPhysicalTransformDiagnostic(
            schema_version=(
                "sim2claw.unapproved_physical_transform_diagnostic.v1"
            ),
            proof_class=PROOF_CLASS,
            action_sha256=float64_tensor_sha256(verified.mapped_actions),
            transform_sha256=verified.transform_sha256,
            candidate_config_sha256=verified.candidate_manifest[
                "candidate_config_sha256"
            ],
            source_provenance_sha256=canonical_json_sha256(
                episode.source_provenance
            ),
            evaluation_contract_sha256=evaluation_sha256,
            measured_joint_tolerance=mapped_tolerance,
        )
        replay = simulate_and_align(
            episode,
            verified.replay_config,
            parameter_values=None,
            model_base_directory=None,
            unapproved_transform_diagnostic=diagnostic,
        )
        generic_directory = temporary / "simulator"
        generic_receipt = write_replay_receipt(
            replay, verified.replay_config, generic_directory
        )
        mapped_action_sha256 = float64_tensor_sha256(
            verified.mapped_actions
        )
        control = replay["control_diagnostics"]
        _require(
            control.get("replay_input_action_sha256")
            == mapped_action_sha256
            and control.get("exact_command_replay") is True
            and control.get("requested_equals_applied") is True
            and control.get("clipping_performed") is False
            and control.get("clipped_row_count") == 0
            and control.get("clipped_joint_value_count") == 0
            and control.get("parameter_fitting_performed") is False
            and (
                control.get("unapproved_transform_diagnostic_contract")
                or {}
            ).get("transform_sha256")
            == verified.transform_sha256
            and len(replay["synchronized_rows"])
            == verified.physical_actions.shape[0],
            "simulator did not consume the exact mapped canary actions",
        )
        simulated_positions = np.asarray(
            replay["simulated"]["joint_position"], dtype=np.float64
        )
        reverse_metrics, reverse_gates = _physical_error_metrics(
            verified,
            simulated_positions,
            evaluation["thresholds"],
        )
        prospective_metrics: dict[str, Any] | None = None
        prospective_gates: dict[str, Any] | None = None
        if preexecution_prediction is not None:
            prebound_positions = np.asarray(
                preexecution_prediction["simulated_joint_positions"],
                dtype=np.float64,
            )
            prospective_metrics, prospective_gates = _physical_error_metrics(
                verified,
                prebound_positions,
                evaluation["thresholds"],
            )
        bounds_satisfied = bool(
            all(reverse_gates.values())
            and (
                prospective_gates is None
                or all(prospective_gates.values())
            )
        )
        calibration_approved = bool(
            transform.get("calibration_approved")
        )
        _require(
            calibration_approved is False,
            "this adapter is only for the provisional-transform diagnostic",
        )
        receipt = {
            "schema_version": REPLAY_RECEIPT_SCHEMA,
            "status": (
                "prospective_diagnostic_bounds_satisfied_no_promotion"
                if bounds_satisfied and prospective
                else (
                    "retrospective_metrics_within_bounds_no_promotion"
                    if bounds_satisfied
                    else "diagnostic_bounds_not_satisfied"
                )
            ),
            "proof_class": "replay",
            "evaluation": {
                "path": str(evaluation_path),
                "sha256": evaluation_sha256,
                "packet_hash_bound_before_execution": prospective,
                "historical_use_retrospective_only": not prospective,
                "bounds_satisfied": bounds_satisfied,
                "promotion_authority": False,
            },
            "episode": {
                "path": episode_path.name,
                "sha256": episode_artifact["sha256"],
                "loaded_as_replay_input": True,
            },
            "candidate_config": {
                "path": config_path.name,
                "sha256": _sha256(config_path),
                "canonical_sha256": canonical_json_sha256(
                    verified.replay_config
                ),
                "hash_bound_candidate_config_unchanged": True,
                "model_or_control_range_modified": False,
                "command_clipping_or_modification": False,
            },
            "simulator_receipt": {
                "path": str(
                    (
                        generic_directory / "replay_receipt.json"
                    ).relative_to(temporary)
                ),
                "sha256": _sha256(
                    generic_directory / "replay_receipt.json"
                ),
                "synchronized_table_sha256": generic_receipt[
                    "synchronized_table"
                ]["sha256"],
            },
            "action_identity": {
                "physical_action_sha256": verified.packet["action_sha256"],
                "physical_action_shape": list(
                    verified.physical_actions.shape
                ),
                "physical_action_units": list(PHYSICAL_UNITS),
                "physical_action_bytes_unchanged": True,
                "simulator_mapped_action_sha256": mapped_action_sha256,
                "simulator_consumed_action_sha256": control[
                    "replay_input_action_sha256"
                ],
                "transform_sha256": verified.transform_sha256,
                "requested_equals_gateway_sent": True,
                "simulator_requested_equals_applied": True,
                "clipping_performed": False,
                "all_samples_consumed": True,
                "consumed_sample_count": len(
                    replay["synchronized_rows"]
                ),
            },
            "metrics": {
                "postexecution_real_to_sim": reverse_metrics,
                "prebound_sim_to_real": prospective_metrics,
            },
            "diagnostic_bounds": {
                "postexecution_real_to_sim": reverse_gates,
                "prebound_sim_to_real": prospective_gates,
            },
            "diagnostic_bounds_satisfied": bounds_satisfied,
            "joint_transform_calibration_approved": False,
            "promotion_eligible": False,
            "zero_fit": True,
            "claim_limits": {
                "physical_task_success": False,
                "metric_camera_registration": False,
                "transform_promotion": False,
                "evaluator_admission": False,
                "policy_evidence": False,
                "physical_authority": False,
            },
        }
        _atomic_json(receipt_path, receipt)
        temporary.replace(output_directory)
        final_receipt_path = output_directory / "replay_receipt.json"
        return {
            **receipt,
            "receipt_path": str(final_receipt_path),
            "receipt_sha256": _sha256(final_receipt_path),
        }
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


__all__ = [
    "EPISODE_SCHEMA",
    "REPLAY_RECEIPT_SCHEMA",
    "PhysicalCanaryReplayError",
    "VerifiedPhysicalCanaryExecution",
    "fit_physical_canary_pan_play_diagnostic",
    "load_verified_physical_canary_execution",
    "materialize_physical_canary_replay_episode",
    "replay_physical_canary_execution",
]
