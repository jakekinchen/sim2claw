"""Guarded staged follower reposition for a D405 AprilTag view.

The compiler freezes three direct physical-space interpolations from one fresh
torque-off follower read.  Every stage is previewed in the current MuJoCo
scene, executed separately through the reviewed follower-only gateway, and
closed with torque off before the next stage can be considered.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

import mujoco
import numpy as np

from .physical_canary import (
    EXCITATION_CONTROL_SOURCE,
    GATEWAY_SCHEMA,
    _default_gateway,
    _default_preflight,
    _gateway_identity,
    _physical_to_model_position,
)
from .recorded_replay import _compile_model
from .replay_eligibility import ACTION_HASH_ENCODING, action_sha256
from .scene import ROBOT_JOINTS


WRIST_VIEW_PACKET_SCHEMA = "sim2claw.wrist_view_reposition_packet.v2"
WRIST_VIEW_REVIEW_SCHEMA = "sim2claw.wrist_view_reposition_review.v2"
WRIST_VIEW_EXECUTION_SCHEMA = "sim2claw.wrist_view_reposition_execution.v2"
WRIST_VIEW_ROUTE_SCHEMA = "sim2claw.wrist_view_reposition_route.v1"
FRAME_JOINT_ALIGNMENT_SCHEMA = "sim2claw.wrist_view_frame_joint_alignment.v1"
SAMPLE_HZ = 40
SAMPLES_PER_STAGE = 361
CAPTURE_HOLD_SECONDS = 2.0
CAPTURE_HOLD_SAMPLES = int(SAMPLE_HZ * CAPTURE_HOLD_SECONDS)
MAX_STAGE_EXCURSION_DEGREES = 90.0
MAX_SLEW_DEGREES_S = 10.0
COMPILE_ANCHOR_TOLERANCE_DEGREES = np.asarray(
    [0.5, 0.5, 0.5, 0.5, 0.5, 0.1], dtype=np.float64
)
COMPILE_COMMAND_ANCHOR_CLIP_TOLERANCE_DEGREES = np.asarray(
    [0.5, 0.5, 3.0, 0.5, 0.5, 0.1], dtype=np.float64
)
STAGE_ANCHOR_TOLERANCE_DEGREES = np.asarray(
    [3.0, 3.0, 3.0, 3.0, 3.0, 0.5], dtype=np.float64
)
HOLD_ENTRY_TOLERANCE_DEGREES = np.asarray(
    [3.0, 3.0, 6.0, 3.0, 3.0, 5.0], dtype=np.float64
)
FINAL_TOLERANCE_DEGREES = np.asarray(
    [3.0, 3.0, 5.0, 3.0, 3.0, 5.0], dtype=np.float64
)
BASELINE_SELF_CONTACT_PAIRS = {
    tuple(sorted(("left_shoulder", "left_lower_arm"))),
    tuple(sorted(("left_shoulder", "left_wrist"))),
}


class CameraCapture(Protocol):
    def start(self) -> dict[str, Any]: ...

    def finish(
        self,
        *,
        action_started_monotonic: float | None,
        action_stopped_monotonic: float | None,
        post_roll_seconds: float,
    ) -> dict[str, Any]: ...


def _default_capture(path: Path) -> CameraCapture:
    from .native_dual_camera import NativeDualCameraRecorder

    return NativeDualCameraRecorder(path)


class WristViewRepositionError(RuntimeError):
    """A staged reposition contract or safety check failed closed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise WristViewRepositionError(message)


def _canonical(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise WristViewRepositionError(f"could not load {label}: {error}") from error
    _require(isinstance(value, dict), f"{label} must be an object")
    return value


def _write_once(path: Path, value: Mapping[str, Any]) -> None:
    _require(not path.exists(), f"refusing to overwrite existing output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _identity_and_limits(
    preflight: Mapping[str, Any],
) -> tuple[dict[str, Any], np.ndarray, np.ndarray, np.ndarray]:
    _require(
        preflight.get("passed") is True
        and preflight.get("schema_version") == GATEWAY_SCHEMA
        and preflight.get("control_source") == EXCITATION_CONTROL_SOURCE
        and preflight.get("real_leader_opened") is False
        and preflight.get("physical_follower_torque_enabled") is False
        and preflight.get("device_configuration_rewritten") is False,
        "fresh follower-only torque-off preflight did not pass",
    )
    port = str(preflight.get("follower_port") or "")
    calibration = str(preflight.get("follower_calibration_sha256") or "")
    _require(port and len(calibration) == 64, "follower hardware identity is incomplete")
    values = [
        np.asarray(preflight.get(field), dtype=np.float64)
        for field in (
            "follower_start_degrees",
            "follower_calibrated_minimum",
            "follower_calibrated_maximum",
        )
    ]
    _require(
        all(value.shape == (6,) and np.all(np.isfinite(value)) for value in values),
        "follower preflight vectors must be finite six-vectors",
    )
    current, lower, upper = values
    _require(np.all(lower < upper), "follower calibrated limits are unordered")
    return (
        {
            "gateway_schema": GATEWAY_SCHEMA,
            "follower_port": port,
            "follower_calibration_sha256": calibration,
        },
        current,
        lower,
        upper,
    )


def _joint_delta(current: np.ndarray, expected: np.ndarray) -> np.ndarray:
    delta = current - expected
    delta[4] = (float(current[4]) - float(expected[4]) + 180.0) % 360.0 - 180.0
    return delta


def _load_route(route_path: Path) -> tuple[dict[str, Any], np.ndarray, np.ndarray]:
    route = _read_json(route_path.resolve(), "wrist-view route")
    _require(
        route.get("schema_version") == WRIST_VIEW_ROUTE_SCHEMA
        and isinstance(route.get("route_id"), str)
        and bool(route["route_id"]),
        "wrist-view route identity changed",
    )
    anchor = np.asarray(route.get("reviewed_anchor_degrees"), dtype=np.float64)
    targets = np.asarray(route.get("stage_targets_degrees"), dtype=np.float64)
    _require(
        anchor.shape == (6,)
        and np.all(np.isfinite(anchor))
        and targets.ndim == 2
        and targets.shape[1] == 6
        and 1 <= targets.shape[0] <= 4
        and np.all(np.isfinite(targets)),
        "wrist-view route must contain one anchor and one to four six-joint targets",
    )
    return route, anchor, targets


def _contact_pair(model: mujoco.MjModel, contact: Any) -> tuple[str, str]:
    body_ids = [
        int(model.geom_bodyid[int(contact.geom1)]),
        int(model.geom_bodyid[int(contact.geom2)]),
    ]
    names = [
        mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, body_id)
        or f"body#{body_id}"
        for body_id in body_ids
    ]
    return tuple(sorted((names[0], names[1])))


def preview_wrist_view_actions(
    stages: list[np.ndarray],
    candidate_manifest_path: Path,
) -> dict[str, Any]:
    """Preview exact staged float64 actions without dynamics or action repair."""

    candidate_manifest_path = candidate_manifest_path.resolve()
    manifest = _read_json(candidate_manifest_path, "candidate manifest")
    candidate_config = manifest.get("candidate_config")
    _require(
        isinstance(candidate_config, Mapping),
        "candidate manifest lacks its compiled config",
    )
    _require(
        (candidate_config.get("model") or {}).get("kind") == "current_chess_scene",
        "wrist-view preview requires the current chess scene",
    )
    model, _ = _compile_model(dict(candidate_config), base_directory=None)
    data = mujoco.MjData(model)
    joint_names = list((candidate_config.get("bindings") or {}).get("joint_names") or [])
    transform_joints = (
        ((candidate_config.get("physical_adapter") or {}).get("joint_transform") or {})
        .get("joints")
    )
    _require(
        len(joint_names) == len(ROBOT_JOINTS)
        and isinstance(transform_joints, list)
        and [joint.get("source_joint") for joint in transform_joints]
        == list(ROBOT_JOINTS)
        and [joint.get("simulator_joint") for joint in transform_joints]
        == joint_names,
        "candidate physical/simulator joint order changed",
    )
    joint_ids = [
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        for name in joint_names
    ]
    _require(all(joint_id >= 0 for joint_id in joint_ids), "candidate joint is missing")

    model_stages = [
        _physical_to_model_position(actions, candidate_config) for actions in stages
    ]
    initial_pairs: set[tuple[str, str]] | None = None
    initial_minimum: float | None = None
    final_pairs: set[tuple[str, str]] = set()
    global_minimum: float | None = None
    stage_reports: list[dict[str, Any]] = []
    for stage_index, (physical_actions, model_actions) in enumerate(
        zip(stages, model_stages, strict=True), start=1
    ):
        stage_pairs: set[tuple[str, str]] = set()
        stage_minimum: float | None = None
        for row_index, row in enumerate(model_actions):
            for joint_index, joint_id in enumerate(joint_ids):
                data.qpos[int(model.jnt_qposadr[joint_id])] = float(row[joint_index])
            data.qvel[:] = 0.0
            mujoco.mj_forward(model, data)
            row_pairs: set[tuple[str, str]] = set()
            row_distances: list[float] = []
            for contact_index in range(data.ncon):
                contact = data.contact[contact_index]
                row_pairs.add(_contact_pair(model, contact))
                row_distances.append(float(contact.dist))
            if stage_index == 1 and row_index == 0:
                initial_pairs = row_pairs
                initial_minimum = min(row_distances) if row_distances else None
            _require(initial_pairs is not None, "preview initial contact was not observed")
            _require(
                row_pairs.issubset(initial_pairs),
                "staged reposition creates a new model contact pair",
            )
            stage_pairs.update(row_pairs)
            if row_distances:
                row_minimum = min(row_distances)
                stage_minimum = (
                    row_minimum
                    if stage_minimum is None
                    else min(stage_minimum, row_minimum)
                )
                global_minimum = (
                    row_minimum
                    if global_minimum is None
                    else min(global_minimum, row_minimum)
                )
            final_pairs = row_pairs
        if initial_minimum is not None and stage_minimum is not None:
            _require(
                stage_minimum >= initial_minimum - 1e-9,
                "staged reposition worsens baseline model penetration",
            )
        stage_reports.append(
            {
                "stage_index": stage_index,
                "exact_physical_action_sha256": action_sha256(physical_actions),
                "sample_count": int(physical_actions.shape[0]),
                "observed_contact_pairs": [list(pair) for pair in sorted(stage_pairs)],
                "minimum_distance_m": stage_minimum,
                "external_contact_pairs": [],
                "no_new_or_worsened_kinematic_contact": True,
            }
        )
    _require(
        final_pairs.issubset(BASELINE_SELF_CONTACT_PAIRS),
        "staged reposition does not clear its pre-existing external model contact",
    )
    initial_unexpected_pairs = (initial_pairs or set()) - BASELINE_SELF_CONTACT_PAIRS
    return {
        "runtime": "cpu_mujoco_mj_forward",
        "candidate_manifest_path": str(candidate_manifest_path),
        "candidate_manifest_sha256": _sha256(candidate_manifest_path),
        "candidate_digest": manifest.get("candidate_digest"),
        "baseline_contact_pairs": [list(pair) for pair in sorted(initial_pairs or set())],
        "initial_preexisting_contact_pairs": [
            list(pair) for pair in sorted(initial_unexpected_pairs)
        ],
        "final_contact_pairs": [list(pair) for pair in sorted(final_pairs)],
        "baseline_minimum_distance_m": initial_minimum,
        "minimum_distance_m": global_minimum,
        "contact_pairs_unchanged_or_removed_only": True,
        "external_contact_pairs": [],
        "no_new_or_worsened_kinematic_contact": True,
        "stages": stage_reports,
    }


def _decode_stage(stage: Mapping[str, Any]) -> tuple[np.ndarray, np.ndarray, bytes]:
    payload = stage.get("frozen_action_payload") or {}
    _require(payload.get("encoding") == ACTION_HASH_ENCODING, "stage encoding changed")
    try:
        raw = base64.b64decode(str(payload["base64"]), validate=True)
        actions = np.frombuffer(raw, dtype="<f8").reshape(tuple(payload["shape"]))
        timestamps = np.asarray(stage["timestamps_seconds"], dtype="<f8")
    except (KeyError, TypeError, ValueError) as error:
        raise WristViewRepositionError("stage payload is malformed") from error
    _require(
        actions.shape == (SAMPLES_PER_STAGE, 6)
        and timestamps.shape == (SAMPLES_PER_STAGE,)
        and np.all(np.isfinite(actions))
        and np.all(np.isfinite(timestamps)),
        "stage arrays changed shape or contain non-finite values",
    )
    _require(
        action_sha256(actions) == stage.get("action_sha256")
        == payload.get("sha256")
        == payload.get("simulation_consumer_sha256")
        and hashlib.sha256(raw).hexdigest() == stage.get("action_bytes_sha256"),
        "stage exact action bytes drifted",
    )
    return actions, timestamps, raw


def _decode_capture_hold(
    stage: Mapping[str, Any],
) -> tuple[np.ndarray, np.ndarray, bytes]:
    payload = stage.get("frozen_capture_hold_payload") or {}
    _require(payload.get("encoding") == ACTION_HASH_ENCODING, "hold encoding changed")
    try:
        raw = base64.b64decode(str(payload["base64"]), validate=True)
        actions = np.frombuffer(raw, dtype="<f8").reshape(tuple(payload["shape"]))
        timestamps = np.asarray(stage["capture_hold_timestamps_seconds"], dtype="<f8")
    except (KeyError, TypeError, ValueError) as error:
        raise WristViewRepositionError("capture-hold payload is malformed") from error
    _require(
        actions.shape == (CAPTURE_HOLD_SAMPLES, 6)
        and timestamps.shape == (CAPTURE_HOLD_SAMPLES,)
        and np.all(np.isfinite(actions))
        and np.all(np.isfinite(timestamps)),
        "capture-hold arrays changed shape or contain non-finite values",
    )
    _require(
        action_sha256(actions) == stage.get("capture_hold_action_sha256")
        == payload.get("sha256")
        == payload.get("simulation_consumer_sha256")
        and hashlib.sha256(raw).hexdigest()
        == stage.get("capture_hold_action_bytes_sha256"),
        "capture-hold exact action bytes drifted",
    )
    target = np.asarray(stage["target_degrees"], dtype="<f8")
    _require(
        np.all(actions == target[None, :]),
        "capture-hold payload is not an exact final-target hold",
    )
    return actions, timestamps, raw


def _validate_packet(packet_path: Path) -> dict[str, Any]:
    packet = _read_json(packet_path.resolve(), "wrist-view packet")
    _require(
        packet.get("schema_version") == WRIST_VIEW_PACKET_SCHEMA
        and packet.get("plan_sha256")
        == _canonical({key: value for key, value in packet.items() if key != "plan_sha256"}),
        "wrist-view packet digest changed",
    )
    route = packet.get("route") or {}
    _require(
        isinstance(route.get("path"), str)
        and len(str(route.get("sha256") or "")) == 64
        and _sha256(Path(route["path"]).resolve()) == route["sha256"],
        "reviewed wrist-view route drifted",
    )
    assistance = packet.get("action_assistance") or {}
    _require(
        assistance
        == {
            "inverse_kinematics": False,
            "clipping": False,
            "offsets": False,
            "suffix_or_corrective_action": False,
        },
        "wrist-view action assistance changed",
    )
    stages = packet.get("stages")
    _require(
        isinstance(stages, list) and 1 <= len(stages) <= 4,
        "packet must contain one to four stages",
    )
    previous = np.asarray(packet["command_anchor_degrees"], dtype=np.float64)
    for stage_index, stage in enumerate(stages, start=1):
        _require(stage.get("stage_index") == stage_index, "stage order changed")
        actions, timestamps, _ = _decode_stage(stage)
        hold_actions, hold_timestamps, _ = _decode_capture_hold(stage)
        target = np.asarray(stage["target_degrees"], dtype=np.float64)
        _require(
            actions[0].tobytes() == previous.astype("<f8").tobytes()
            and actions[-1].tobytes() == target.astype("<f8").tobytes(),
            "stage endpoints drifted",
        )
        _require(
            np.array_equal(
                timestamps,
                (np.arange(SAMPLES_PER_STAGE, dtype="<f8") + 1.0) / SAMPLE_HZ,
            ),
            "stage timestamps changed",
        )
        _require(
            np.array_equal(
                hold_timestamps,
                (np.arange(CAPTURE_HOLD_SAMPLES, dtype="<f8") + 1.0) / SAMPLE_HZ,
            )
            and np.all(hold_actions == target[None, :]),
            "capture-hold timing or target changed",
        )
        _require(
            stage.get("capture_hold_reuses_previewed_target") is True,
            "capture hold is not bound to the previewed target",
        )
        _require(
            float(np.max(np.abs(target - previous)))
            <= MAX_STAGE_EXCURSION_DEGREES + 1e-9,
            "stage excursion exceeds 90 degrees",
        )
        preview = stage.get("simulation_preview") or {}
        _require(
            preview.get("exact_physical_action_sha256") == stage["action_sha256"]
            and preview.get("no_new_or_worsened_kinematic_contact") is True
            and not preview.get("external_contact_pairs"),
            "stage simulation preview is not admitted",
        )
        previous = target
    return packet


def compile_wrist_view_reposition_packet(
    packet_path: Path,
    *,
    candidate_manifest_path: Path,
    route_path: Path,
    preflight_fn: Callable[[], dict[str, Any]] | None = None,
    preview_fn: Callable[[list[np.ndarray], Path], dict[str, Any]] = (
        preview_wrist_view_actions
    ),
) -> dict[str, Any]:
    """Freeze supplied reviewed direct-interpolation stages from a fresh anchor."""

    preflight = (preflight_fn or _default_preflight)()
    identity, anchor, lower, upper = _identity_and_limits(preflight)
    route, reviewed_anchor, targets = _load_route(route_path)
    _require(
        np.all(
            np.abs(_joint_delta(anchor, reviewed_anchor))
            <= COMPILE_ANCHOR_TOLERANCE_DEGREES
        ),
        "fresh follower pose no longer matches the reviewed live torque-off pose",
    )
    _require(
        np.all(targets >= lower[None, :]) and np.all(targets <= upper[None, :]),
        "reviewed wrist-view target exceeds fresh calibrated limits",
    )
    command_anchor = np.clip(anchor, lower, upper).astype("<f8")
    _require(
        np.all(
            np.abs(_joint_delta(command_anchor, anchor))
            <= COMPILE_COMMAND_ANCHOR_CLIP_TOLERANCE_DEGREES
        ),
        "fresh torque-off pose is too far outside calibrated limits",
    )
    timestamps = (np.arange(SAMPLES_PER_STAGE, dtype="<f8") + 1.0) / SAMPLE_HZ
    hold_timestamps = (
        np.arange(CAPTURE_HOLD_SAMPLES, dtype="<f8") + 1.0
    ) / SAMPLE_HZ
    action_stages: list[np.ndarray] = []
    previous = command_anchor
    for target in targets:
        delta = target - previous
        _require(
            float(np.max(np.abs(delta))) <= MAX_STAGE_EXCURSION_DEGREES + 1e-9,
            "reviewed wrist-view stage exceeds 90 degrees",
        )
        actions = np.linspace(
            previous, target.astype("<f8"), SAMPLES_PER_STAGE, dtype=np.float64
        ).astype("<f8", copy=False)
        rates = np.abs(np.diff(actions, axis=0) / np.diff(timestamps)[:, None])
        _require(
            float(np.max(rates)) <= MAX_SLEW_DEGREES_S + 1e-9,
            "reviewed wrist-view stage exceeds 10 degrees/s",
        )
        _require(
            np.all(actions >= lower[None, :]) and np.all(actions <= upper[None, :]),
            "frozen wrist-view action exceeds calibrated limits",
        )
        action_stages.append(actions)
        previous = target.astype("<f8")
    preview = preview_fn(action_stages, candidate_manifest_path)
    _require(
        preview.get("no_new_or_worsened_kinematic_contact") is True
        and not preview.get("external_contact_pairs"),
        "simulation preview rejected the staged reposition",
    )
    preview_stages = preview.get("stages")
    _require(
        isinstance(preview_stages, list) and len(preview_stages) == len(action_stages),
        "simulation preview stage count changed",
    )
    stages: list[dict[str, Any]] = []
    previous = anchor.astype("<f8")
    action_previous = command_anchor
    for stage_index, (target, actions, stage_preview) in enumerate(
        zip(targets, action_stages, preview_stages, strict=True), start=1
    ):
        raw = actions.tobytes(order="C")
        digest = action_sha256(actions)
        hold_actions = np.repeat(
            target.astype("<f8")[None, :], CAPTURE_HOLD_SAMPLES, axis=0
        )
        hold_raw = hold_actions.tobytes(order="C")
        hold_digest = action_sha256(hold_actions)
        _require(
            stage_preview.get("exact_physical_action_sha256") == digest,
            "simulation preview did not consume the exact stage bytes",
        )
        stages.append(
            {
                "stage_index": stage_index,
                "expected_anchor_degrees": previous.tolist(),
                "command_anchor_degrees": action_previous.tolist(),
                "target_degrees": target.tolist(),
                "maximum_joint_excursion_degrees": float(
                    np.max(np.abs(target - previous))
                ),
                "timestamps_seconds": timestamps.tolist(),
                "frozen_action_payload": {
                    "encoding": ACTION_HASH_ENCODING,
                    "shape": list(actions.shape),
                    "base64": base64.b64encode(raw).decode("ascii"),
                    "sha256": digest,
                    "simulation_consumer_sha256": digest,
                    "hardware_consumer_must_use_same_bytes": True,
                    "units": ["degree"] * 5 + ["percent"],
                },
                "action_sha256": digest,
                "action_bytes_sha256": hashlib.sha256(raw).hexdigest(),
                "capture_hold_timestamps_seconds": hold_timestamps.tolist(),
                "frozen_capture_hold_payload": {
                    "encoding": ACTION_HASH_ENCODING,
                    "shape": list(hold_actions.shape),
                    "base64": base64.b64encode(hold_raw).decode("ascii"),
                    "sha256": hold_digest,
                    "simulation_consumer_sha256": hold_digest,
                    "hardware_consumer_must_use_same_bytes": True,
                    "units": ["degree"] * 5 + ["percent"],
                },
                "capture_hold_action_sha256": hold_digest,
                "capture_hold_action_bytes_sha256": hashlib.sha256(
                    hold_raw
                ).hexdigest(),
                "capture_hold_seconds": CAPTURE_HOLD_SECONDS,
                "simulation_preview": stage_preview,
                "capture_hold_reuses_previewed_target": True,
                "inspect_wrist_camera_before_next_stage": stage_index < len(targets),
            }
        )
        previous = target.astype("<f8")
        action_previous = target.astype("<f8")
    packet = {
        "schema_version": WRIST_VIEW_PACKET_SCHEMA,
        "kind": "follower_only_staged_d405_tag_view_reposition",
        "single_use_per_stage": True,
        "hardware_identity": identity,
        "compile_anchor_source": "fresh_torque_off_follower_read",
        "compile_anchor_degrees": anchor.tolist(),
        "command_anchor_degrees": command_anchor.tolist(),
        "reviewed_live_anchor_degrees": reviewed_anchor.tolist(),
        "route": {
            "route_id": route["route_id"],
            "path": str(route_path.resolve()),
            "sha256": _sha256(route_path.resolve()),
        },
        "calibrated_minimum_degrees": lower.tolist(),
        "calibrated_maximum_degrees": upper.tolist(),
        "sample_hz": SAMPLE_HZ,
        "samples_per_stage": SAMPLES_PER_STAGE,
        "capture_hold_samples": CAPTURE_HOLD_SAMPLES,
        "capture_hold_seconds": CAPTURE_HOLD_SECONDS,
        "capture_during_motion": bool(route.get("capture_during_motion", False)),
        "maximum_stage_excursion_degrees": MAX_STAGE_EXCURSION_DEGREES,
        "maximum_slew_degrees_s": MAX_SLEW_DEGREES_S,
        "stage_anchor_tolerance_degrees": STAGE_ANCHOR_TOLERANCE_DEGREES.tolist(),
        "hold_entry_tolerance_degrees": HOLD_ENTRY_TOLERANCE_DEGREES.tolist(),
        "final_tolerance_degrees": FINAL_TOLERANCE_DEGREES.tolist(),
        "stages": stages,
        "simulation_preview": {
            key: value for key, value in preview.items() if key != "stages"
        },
        "candidate_manifest": {
            "path": str(candidate_manifest_path.resolve()),
            "sha256": _sha256(candidate_manifest_path.resolve()),
            "candidate_digest": preview.get("candidate_digest"),
        },
        "action_assistance": {
            "inverse_kinematics": False,
            "clipping": False,
            "offsets": False,
            "suffix_or_corrective_action": False,
        },
        "execution_contract": {
            "one_stage_per_invocation": True,
            "fresh_preflight_each_stage": True,
            "prior_stage_receipt_required_after_stage_1": True,
            "torque_off_on_every_close": True,
            "native_dual_camera_final_hold_capture": True,
            "camera_capture_finishes_before_gateway_close": True,
            "frame_joint_alignment_clock": "host_continuous_monotonic_nanoseconds",
        },
        "physical_motion_commanded": False,
        "physical_follower_torque_enabled": False,
        "physical_authority": False,
    }
    packet["plan_sha256"] = _canonical(packet)
    _write_once(packet_path, packet)
    return packet


def review_wrist_view_reposition_packet(
    packet_path: Path,
    output_path: Path,
    *,
    reviewer: str,
    decision_id: str,
) -> dict[str, Any]:
    """Seal an independent review receipt without changing the packet."""

    packet_path = packet_path.resolve()
    packet = _validate_packet(packet_path)
    reviewer = reviewer.strip()
    decision_id = decision_id.strip()
    _require(reviewer and decision_id, "reviewer and decision identity are required")
    receipt = {
        "schema_version": WRIST_VIEW_REVIEW_SCHEMA,
        "status": "admitted_for_one_execution_per_stage",
        "packet_path": str(packet_path),
        "packet_sha256": _sha256(packet_path),
        "plan_sha256": packet["plan_sha256"],
        "reviewer": reviewer,
        "decision_id": decision_id,
        "frozen_float64_actions_reviewed": True,
        "stage_excursions_reviewed": True,
        "bounded_slew_reviewed": True,
        "simulation_contact_preview_reviewed": True,
        "fresh_anchor_and_identity_checks_reviewed": True,
        "torque_off_close_reviewed": True,
        "final_hold_capture_reviewed": True,
        "clear_workcell_acknowledged": True,
        "camera_inspection_between_stages_acknowledged": True,
        "physical_authority": False,
    }
    _write_once(output_path, receipt)
    return receipt


def _validate_review(
    review_path: Path, packet_path: Path, packet: Mapping[str, Any]
) -> dict[str, Any]:
    review = _read_json(review_path.resolve(), "wrist-view review")
    _require(
        review.get("schema_version") == WRIST_VIEW_REVIEW_SCHEMA
        and review.get("status") == "admitted_for_one_execution_per_stage"
        and review.get("packet_sha256") == _sha256(packet_path)
        and review.get("plan_sha256") == packet.get("plan_sha256"),
        "wrist-view review is not bound to this packet",
    )
    fields = (
        "reviewer",
        "decision_id",
        "frozen_float64_actions_reviewed",
        "stage_excursions_reviewed",
        "bounded_slew_reviewed",
        "simulation_contact_preview_reviewed",
        "fresh_anchor_and_identity_checks_reviewed",
        "torque_off_close_reviewed",
        "final_hold_capture_reviewed",
        "clear_workcell_acknowledged",
        "camera_inspection_between_stages_acknowledged",
    )
    _require(all(review.get(field) for field in fields), "review receipt is incomplete")
    return review


def _capture_artifacts(
    capture_root: Path, camera_finished: Mapping[str, Any]
) -> list[dict[str, Any]]:
    common = camera_finished.get("common_session") or {}
    rows: list[tuple[str, str, str]] = [
        (
            "native_report",
            str(common.get("report_path") or ""),
            str(common.get("report_sha256") or ""),
        ),
        (
            "callback_ledger",
            str(common.get("callback_timestamp_path") or ""),
            str(common.get("callback_timestamp_sha256") or ""),
        ),
    ]
    for role in ("overhead", "wrist"):
        stream = camera_finished.get(role) or {}
        rows.extend(
            [
                (
                    f"{role}_source_video",
                    str(stream.get("video_path") or ""),
                    str(stream.get("video_sha256") or ""),
                ),
                (
                    f"{role}_browser_video",
                    str(stream.get("browser_video_path") or ""),
                    str(stream.get("browser_video_sha256") or ""),
                ),
            ]
        )
    artifacts: list[dict[str, Any]] = []
    for kind, relative, expected_sha256 in rows:
        path = capture_root / relative
        _require(relative and len(expected_sha256) == 64, f"{kind} receipt is incomplete")
        _require(
            path.is_file() and _sha256(path) == expected_sha256,
            f"{kind} artifact hash changed",
        )
        artifacts.append(
            {
                "kind": kind,
                "path": str(path),
                "sha256": expected_sha256,
                "bytes": path.stat().st_size,
            }
        )
    return artifacts


def _align_d405_frames_to_hold_samples(
    capture_root: Path,
    camera_finished: Mapping[str, Any],
    hold_samples: list[dict[str, Any]],
    output_path: Path,
) -> dict[str, Any]:
    _require(len(hold_samples) == CAPTURE_HOLD_SAMPLES, "capture hold is incomplete")
    common = camera_finished.get("common_session") or {}
    ledger_path = capture_root / str(common.get("callback_timestamp_path") or "")
    _require(ledger_path.is_file(), "native callback ledger is missing")
    first_ns = int(hold_samples[0]["host_continuous_ns"])
    last_ns = int(hold_samples[-1]["host_continuous_ns"])
    frames: list[dict[str, Any]] = []
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        host_ns = event.get("host_continuous_ns")
        if (
            event.get("role") == "d405"
            and event.get("kind") == "output"
            and event.get("appended_to_writer") is True
            and isinstance(host_ns, int)
            and first_ns <= host_ns <= last_ns
        ):
            frames.append(event)
    _require(len(frames) >= 2, "fewer than two D405 frames overlap the torque-on hold")
    rows: list[dict[str, Any]] = []
    maximum_delta_ns = 0
    for frame in frames:
        host_ns = int(frame["host_continuous_ns"])
        nearest = min(
            hold_samples,
            key=lambda sample: abs(int(sample["host_continuous_ns"]) - host_ns),
        )
        delta_ns = abs(int(nearest["host_continuous_ns"]) - host_ns)
        maximum_delta_ns = max(maximum_delta_ns, delta_ns)
        rows.append(
            {
                "schema_version": FRAME_JOINT_ALIGNMENT_SCHEMA,
                "camera_role": "d405",
                "frame_sequence": frame.get("sequence"),
                "frame_pts_seconds": frame.get("pts_seconds"),
                "frame_host_continuous_ns": host_ns,
                "nearest_joint_sample_index": nearest["sample_index"],
                "joint_sample_host_continuous_ns": nearest["host_continuous_ns"],
                "absolute_time_delta_ns": delta_ns,
                "requested_physical_units": nearest["requested_physical_units"],
                "actual_physical_units": nearest["actual_physical_units"],
                "source_action_sha256": nearest["source_action_sha256"],
            }
        )
    _require(
        maximum_delta_ns <= 100_000_000,
        "D405 frame-to-joint nearest-neighbor delta exceeds 100 ms",
    )
    _require(not output_path.exists(), f"refusing to overwrite alignment: {output_path}")
    with output_path.open("x", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    return {
        "schema_version": FRAME_JOINT_ALIGNMENT_SCHEMA,
        "status": "host_clock_nearest_joint_sample_alignment",
        "camera_role": "d405",
        "aligned_frame_count": len(rows),
        "hold_joint_sample_count": len(hold_samples),
        "maximum_absolute_time_delta_ns": maximum_delta_ns,
        "maximum_allowed_time_delta_ns": 100_000_000,
        "path": str(output_path),
        "sha256": _sha256(output_path),
        "timestamp_semantics": {
            "clock": "host_continuous_monotonic_nanoseconds",
            "nearest_neighbor_only": True,
            "camera_exposure_synchronized": False,
        },
    }


def execute_wrist_view_reposition_stage(
    packet_path: Path,
    review_path: Path,
    output_directory: Path,
    *,
    stage_index: int,
    prior_receipt_path: Path | None = None,
    operator_acknowledged: bool = False,
    preflight_fn: Callable[[], dict[str, Any]] | None = None,
    gateway_factory: Callable[[Any], Any] | None = None,
    capture_factory: Callable[[Path], CameraCapture] | None = None,
    clock_fn: Callable[[], float] = time.monotonic,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Execute exactly one reviewed stage, then close the follower torque-off."""

    packet_path = packet_path.resolve()
    packet = _validate_packet(packet_path)
    _validate_review(review_path, packet_path, packet)
    _require(operator_acknowledged, "fresh operator acknowledgement is required")
    _require(
        1 <= stage_index <= len(packet["stages"]),
        "stage index is outside this route",
    )
    if stage_index == 1:
        _require(prior_receipt_path is None, "stage 1 does not accept a prior receipt")
    else:
        _require(prior_receipt_path is not None, "later stages require the prior receipt")
        prior = _read_json(prior_receipt_path.resolve(), "prior execution receipt")
        _require(
            prior.get("schema_version") == WRIST_VIEW_EXECUTION_SCHEMA
            and prior.get("status") == "completed_wrist_view_reposition_stage"
            and prior.get("packet_sha256") == _sha256(packet_path)
            and prior.get("stage_index") == stage_index - 1
            and prior.get("physical_follower_torque_enabled") is False,
            "prior execution receipt does not admit this stage",
        )

    manifest = packet["candidate_manifest"]
    manifest_path = Path(manifest["path"]).resolve()
    _require(
        _sha256(manifest_path) == manifest["sha256"],
        "candidate manifest drifted after packet compilation",
    )
    route = packet["route"]
    _require(
        _sha256(Path(route["path"]).resolve()) == route["sha256"],
        "reviewed wrist-view route drifted after packet compilation",
    )
    stage = packet["stages"][stage_index - 1]
    actions, timestamps, _ = _decode_stage(stage)
    hold_actions, hold_timestamps, _ = _decode_capture_hold(stage)
    fresh_preview = preview_wrist_view_actions(
        [np.asarray(item, dtype="<f8") for item in [actions]],
        manifest_path,
    )
    _require(
        fresh_preview.get("no_new_or_worsened_kinematic_contact") is True
        and not fresh_preview.get("external_contact_pairs"),
        "fresh simulation preview rejected the stage",
    )

    preflight = (preflight_fn or _default_preflight)()
    identity, current, lower, upper = _identity_and_limits(preflight)
    _require(identity == packet["hardware_identity"], "follower identity drifted")
    expected_anchor = np.asarray(stage["expected_anchor_degrees"], dtype=np.float64)
    anchor_tolerance = np.asarray(
        packet["stage_anchor_tolerance_degrees"], dtype=np.float64
    )
    _require(
        np.all(np.abs(_joint_delta(current, expected_anchor)) <= anchor_tolerance),
        "fresh follower pose does not match this stage anchor",
    )
    _require(
        np.all(actions >= lower[None, :])
        and np.all(actions <= upper[None, :])
        and np.all(hold_actions >= lower[None, :])
        and np.all(hold_actions <= upper[None, :]),
        "frozen actions exceed fresh calibrated limits",
    )

    output_directory = output_directory.resolve()
    receipt_path = output_directory / "execution_receipt.json"
    samples_path = output_directory / "joint_samples.jsonl"
    alignment_path = output_directory / "d405_frame_joint_alignment.jsonl"
    _require(
        not receipt_path.exists()
        and not samples_path.exists()
        and not alignment_path.exists(),
        "refusing to overwrite wrist-view execution output",
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    samples_path.open("x").close()
    gateway = (
        gateway_factory or _default_gateway
    )(_gateway_identity(identity) if gateway_factory is None else identity)
    completed_motion = 0
    completed_hold = 0
    actual = current.copy()
    started = clock_fn()
    capture_root = output_directory / "final_hold_camera"
    capture: CameraCapture | None = None
    camera_started: dict[str, Any] | None = None
    camera_finished: dict[str, Any] | None = None
    hold_started: float | None = None
    hold_stopped: float | None = None
    hold_sample_records: list[dict[str, Any]] = []
    error: Exception | None = None
    try:
        opened = gateway.open(enable_motion=True, paired_pose_confirmed=True)
        opened_start = np.asarray(opened["follower_start_degrees"], dtype=np.float64)
        _require(
            np.all(
                np.abs(_joint_delta(opened_start, expected_anchor))
                <= anchor_tolerance
            ),
            "follower anchor drifted before the stage hold",
        )
        if packet.get("capture_during_motion") is True:
            capture = (capture_factory or _default_capture)(capture_root)
            camera_started = capture.start()
        motion_started = clock_fn()
        with samples_path.open("a", encoding="utf-8") as handle:
            for sample_index, (timestamp, target) in enumerate(
                zip(timestamps, actions, strict=True)
            ):
                delay = motion_started + float(timestamp) - clock_fn()
                if delay > 0.0:
                    sleep_fn(delay)
                ensure_running = (
                    getattr(capture, "ensure_running", None)
                    if capture is not None
                    else None
                )
                if callable(ensure_running):
                    ensure_running()
                sample = gateway.sample(
                    float(timestamp), exact_requested_degrees=target
                )
                requested = np.asarray(
                    sample.get("follower_requested_degrees"), dtype="<f8"
                )
                sent = np.asarray(
                    sample.get("follower_command_degrees"), dtype="<f8"
                )
                _require(
                    requested.tobytes() == target.tobytes()
                    and sent.tobytes() == target.tobytes()
                    and not sample.get("rate_limited")
                    and not sample.get("safety_clamped"),
                    "gateway modified, clipped, or rate-limited a frozen action",
                )
                actual = np.asarray(
                    sample["follower_actual_position_degrees"], dtype=np.float64
                )
                handle.write(
                    json.dumps(
                        {
                            "sample_index": sample_index,
                            "phase": "motion",
                            "host_continuous_ns": int(round(clock_fn() * 1e9)),
                            "timestamp_seconds": float(timestamp),
                            "source_action_sha256": stage["action_sha256"],
                            "requested_physical_units": target.tolist(),
                            **sample,
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )
                completed_motion += 1
        target = np.asarray(stage["target_degrees"], dtype=np.float64)
        residual = _joint_delta(actual, target)
        _require(
            np.all(
                np.abs(residual)
                <= np.asarray(
                    packet["hold_entry_tolerance_degrees"], dtype=np.float64
                )
            ),
            "follower did not reach the staged target",
        )
        if capture is None:
            capture = (capture_factory or _default_capture)(capture_root)
            camera_started = capture.start()
        hold_started = clock_fn()
        with samples_path.open("a", encoding="utf-8") as handle:
            for hold_index, (timestamp, target) in enumerate(
                zip(hold_timestamps, hold_actions, strict=True)
            ):
                delay = hold_started + float(timestamp) - clock_fn()
                if delay > 0.0:
                    sleep_fn(delay)
                ensure_running = getattr(capture, "ensure_running", None)
                if callable(ensure_running):
                    ensure_running()
                sample = gateway.sample(
                    float(timestamps[-1] + timestamp),
                    exact_requested_degrees=target,
                )
                requested = np.asarray(
                    sample.get("follower_requested_degrees"), dtype="<f8"
                )
                sent = np.asarray(
                    sample.get("follower_command_degrees"), dtype="<f8"
                )
                _require(
                    requested.tobytes() == target.tobytes()
                    and sent.tobytes() == target.tobytes()
                    and not sample.get("rate_limited")
                    and not sample.get("safety_clamped"),
                    "gateway modified, clipped, or rate-limited a frozen hold action",
                )
                actual = np.asarray(
                    sample["follower_actual_position_degrees"], dtype=np.float64
                )
                host_ns = int(round(clock_fn() * 1e9))
                record = {
                    "sample_index": completed_motion + hold_index,
                    "phase": "capture_hold",
                    "host_continuous_ns": host_ns,
                    "timestamp_seconds": float(timestamps[-1] + timestamp),
                    "capture_hold_timestamp_seconds": float(timestamp),
                    "source_action_sha256": stage["capture_hold_action_sha256"],
                    "requested_physical_units": target.tolist(),
                    "actual_physical_units": actual.tolist(),
                    **sample,
                }
                hold_sample_records.append(record)
                handle.write(json.dumps(record, sort_keys=True) + "\n")
                completed_hold += 1
        hold_stopped = clock_fn()
        residual = _joint_delta(
            actual, np.asarray(stage["target_degrees"], dtype=np.float64)
        )
        _require(
            np.all(
                np.abs(residual)
                <= np.asarray(packet["final_tolerance_degrees"], dtype=np.float64)
            ),
            "follower left the staged target during camera hold",
        )
        camera_finished = capture.finish(
            action_started_monotonic=hold_started,
            action_stopped_monotonic=hold_stopped,
            post_roll_seconds=0.0,
        )
    except Exception as caught:
        error = caught
    finally:
        if capture is not None and camera_started is not None and camera_finished is None:
            try:
                camera_finished = capture.finish(
                    action_started_monotonic=hold_started,
                    action_stopped_monotonic=hold_stopped or clock_fn(),
                    post_roll_seconds=0.0,
                )
            except Exception as caught:
                error = error or caught
        try:
            gateway.close()
        except Exception as caught:
            error = error or caught

    capture_artifacts: list[dict[str, Any]] | None = None
    frame_joint_alignment: dict[str, Any] | None = None
    if error is None:
        try:
            _require(camera_finished is not None, "final hold camera did not finish")
            capture_artifacts = _capture_artifacts(capture_root, camera_finished)
            frame_joint_alignment = _align_d405_frames_to_hold_samples(
                capture_root,
                camera_finished,
                hold_sample_records,
                alignment_path,
            )
        except Exception as caught:
            error = caught

    residual = _joint_delta(
        actual, np.asarray(stage["target_degrees"], dtype=np.float64)
    )
    receipt = {
        "schema_version": WRIST_VIEW_EXECUTION_SCHEMA,
        "status": (
            "completed_wrist_view_reposition_stage"
            if error is None
            else "stopped_safely"
        ),
        "packet_sha256": _sha256(packet_path),
        "review_sha256": _sha256(review_path.resolve()),
        "stage_index": stage_index,
        "action_sha256": stage["action_sha256"],
        "capture_hold_action_sha256": stage["capture_hold_action_sha256"],
        "completed_samples": completed_motion + completed_hold,
        "completed_motion_samples": completed_motion,
        "completed_capture_hold_samples": completed_hold,
        "joint_samples_path": str(samples_path),
        "joint_samples_sha256": _sha256(samples_path),
        "camera_started": camera_started,
        "camera_finished": camera_finished,
        "capture_artifacts": capture_artifacts,
        "frame_joint_alignment": frame_joint_alignment,
        "fresh_preflight_anchor_degrees": current.tolist(),
        "expected_anchor_degrees": expected_anchor.tolist(),
        "target_degrees": stage["target_degrees"],
        "final_actual_degrees": actual.tolist(),
        "final_residual_degrees": residual.tolist(),
        "error": str(error) if error is not None else None,
        "physical_motion_commanded": (completed_motion + completed_hold) > 0,
        "physical_follower_torque_enabled": False,
        "physical_authority": False,
        "camera_opened": camera_started is not None,
        "camera_capture_completed_before_torque_off": camera_finished is not None,
        "inspect_wrist_camera_before_next_stage": stage_index < len(packet["stages"]),
        "stop_before_further_robot_command": True,
        "wall_duration_seconds": max(0.0, clock_fn() - started),
    }
    _write_once(receipt_path, receipt)
    if error is not None:
        raise WristViewRepositionError(
            f"wrist-view stage stopped safely with torque off: {error}"
        ) from error
    return receipt
