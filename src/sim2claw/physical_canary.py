"""Guarded execution of one frozen simulation canary on the follower.

This module is intentionally narrow: normalization is a separate, bounded
phase; compilation only binds a fresh follower anchor; execution consumes the
simulation bundle's frozen bytes and delegates rate, tracking, limit, and
stall guards to the reviewed follower-only gateway.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

import numpy as np

from .replay_eligibility import ACTION_HASH_ENCODING, MANIFEST_SCHEMA, action_sha256
from .scene import ROBOT_JOINTS


# These are stable reviewed contract values.  The hardware implementations
# are imported lazily so simulation/contact tooling cannot import a gateway or
# robot driver merely by loading this module.
GATEWAY_SCHEMA = "sim2claw.so101_physical_gateway.v2"
EXCITATION_CONTROL_SOURCE = "frozen_precompiled_follower_actions"
_EXCITATION_COMMAND_SOURCE_PORT = "in-process://frozen-precompiled-actions"
_EXCITATION_COMMAND_SOURCE_SHA256 = hashlib.sha256(
    EXCITATION_CONTROL_SOURCE.encode()
).hexdigest()


PHYSICAL_CANARY_PACKET_SCHEMA = "sim2claw.physical_canary_packet.v1"
NORMALIZATION_PACKET_SCHEMA = "sim2claw.physical_canary_normalization.v1"
EXECUTION_RECEIPT_SCHEMA = "sim2claw.physical_canary_execution_receipt.v1"
NORMALIZATION_RECEIPT_SCHEMA = "sim2claw.physical_canary_normalization_receipt.v1"
NORMALIZATION_SAMPLE_HZ = 20
NORMALIZATION_SLEW_DEGREES_S = 5.0
NORMALIZATION_TARGET_DEGREES = {1: -105.0, 3: -105.0}
CANARY_START_TOLERANCE_DEGREES = np.asarray(
    [0.5, 0.5, 0.5, 0.5, 0.5, 0.1], dtype=np.float64
)
CANARY_BODY_RATE_DEGREES_S = 60.0
CANARY_WRIST_ROLL_RATE_DEGREES_S = 90.0
CANARY_GRIPPER_RATE_S = 100.0
NORMALIZATION_MARGIN_DEGREES = 0.5
NORMALIZATION_MAX_DELTA_DEGREES = 5.0


class PhysicalCanaryError(RuntimeError):
    """A physical-canary input or safety gate failed closed."""


class CameraCapture(Protocol):
    def start(self) -> dict[str, Any]: ...

    def finish(
        self,
        *,
        action_started_monotonic: float | None,
        action_stopped_monotonic: float | None,
        post_roll_seconds: float,
    ) -> dict[str, Any]: ...


def _default_preflight() -> dict[str, Any]:
    from .teleop_recording import physical_excitation_follower_preflight

    return physical_excitation_follower_preflight()


def _default_gateway(identity: Any) -> Any:
    from .teleop_recording import _physical_excitation_gateway

    return _physical_excitation_gateway(identity)


def _default_capture(path: Path) -> CameraCapture:
    from .native_dual_camera import NativeDualCameraRecorder

    return NativeDualCameraRecorder(path)


def _gateway_identity(identity: Mapping[str, Any]) -> Any:
    from .physical_gateway import GatewayIdentity

    return GatewayIdentity(
        _EXCITATION_COMMAND_SOURCE_PORT,
        str(identity["follower_port"]),
        _EXCITATION_COMMAND_SOURCE_SHA256,
        str(identity["follower_calibration_sha256"]),
    )


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PhysicalCanaryError(message)


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PhysicalCanaryError(f"could not load {label}: {error}") from error
    _require(isinstance(value, dict), f"{label} must be an object")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _write_once(path: Path, value: Mapping[str, Any]) -> None:
    _require(not path.exists(), f"refusing to overwrite existing output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _decode_bundle(bundle_path: Path) -> tuple[dict[str, Any], np.ndarray, np.ndarray, bytes]:
    bundle = _read_json(bundle_path, "simulation canary bundle")
    _require(bundle.get("schema_version") == MANIFEST_SCHEMA, "canary bundle schema changed")
    _require(bundle.get("canary_schema_version") == "sim2claw.zero_contact_canary_bundle.v1", "canary schema changed")
    _require(bundle.get("simulation_only") is True, "physical canary requires a simulation-only bundle")
    _require(bundle.get("evaluator_admission") is False and bundle.get("physical_authority") is False, "canary authority widened")
    payload = bundle.get("frozen_action_payload")
    _require(isinstance(payload, Mapping) and payload.get("encoding") == ACTION_HASH_ENCODING, "frozen canary payload is missing")
    shape = payload.get("shape")
    _require(
        isinstance(shape, list)
        and len(shape) == 2
        and isinstance(shape[0], int)
        and shape[0] >= 2
        and shape[1] == len(ROBOT_JOINTS),
        "frozen canary shape is invalid",
    )
    try:
        raw = base64.b64decode(str(payload["base64"]), validate=True)
        actions = np.frombuffer(raw, dtype="<f8").reshape(tuple(shape))
        timestamps = np.asarray(bundle["timestamps_seconds"], dtype="<f8")
    except (KeyError, TypeError, ValueError) as error:
        raise PhysicalCanaryError("frozen canary payload is malformed") from error
    _require(actions.shape[0] >= 2 and timestamps.shape == (actions.shape[0],), "canary trajectory shape is invalid")
    _require(np.all(np.isfinite(actions)) and np.all(np.isfinite(timestamps)) and np.array_equal(timestamps, np.arange(actions.shape[0], dtype=np.float64) / 20.0), "canary timestamps are not the frozen 20 Hz sequence")
    digest = action_sha256(actions)
    _require(payload.get("sha256") == digest and payload.get("simulation_consumer_sha256") == digest, "frozen canary action hash drifted")
    for field in ("requested_actions", "applied_actions"):
        value = np.asarray(bundle.get(field), dtype="<f8", order="C")
        _require(value.shape == actions.shape and value.tobytes(order="C") == raw, f"canary {field} changed from frozen bytes")
    _require(bundle.get("requested_action_sha256") == digest and bundle.get("applied_action_sha256") == digest, "canary action lineage drifted")
    _require(actions[0].tobytes() == np.asarray(bundle["initial_state"]["joint_position"], dtype="<f8").tobytes(), "canary initial state drifted from frozen bytes")
    return bundle, actions, timestamps, raw


def _identity_from_preflight(preflight: Mapping[str, Any]) -> dict[str, Any]:
    _require(preflight.get("schema_version") == GATEWAY_SCHEMA, "follower gateway schema changed")
    _require(preflight.get("control_source") == EXCITATION_CONTROL_SOURCE and preflight.get("real_leader_opened") is False, "physical canary requires follower-only control")
    _require(preflight.get("physical_follower_torque_enabled") is False and preflight.get("device_configuration_rewritten") is False, "follower preflight is not torque-off and configuration-free")
    port = str(preflight.get("follower_port") or "")
    calibration = str(preflight.get("follower_calibration_sha256") or "")
    _require(port and len(calibration) == 64, "follower hardware identity is incomplete")
    return {"gateway_schema": GATEWAY_SCHEMA, "follower_port": port, "follower_calibration_sha256": calibration}


def _anchor_delta(current: np.ndarray, expected: np.ndarray) -> np.ndarray:
    delta = current - expected
    delta[4] = (float(current[4]) - float(expected[4]) + 180.0) % 360.0 - 180.0
    return delta


def _validate_limits(preflight: Mapping[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    current = np.asarray(preflight.get("follower_start_degrees"), dtype=np.float64)
    lower = np.asarray(preflight.get("follower_calibrated_minimum"), dtype=np.float64)
    upper = np.asarray(preflight.get("follower_calibrated_maximum"), dtype=np.float64)
    _require(all(value.shape == (6,) and np.all(np.isfinite(value)) for value in (current, lower, upper)), "follower preflight vectors must be finite six-vectors")
    _require(np.all(lower < upper), "follower calibrated limits are unordered")
    return current, lower, upper


def compile_physical_canary_normalization(
    packet_path: Path,
    *,
    preflight_fn: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compile a separate inward-only normalization packet from a fresh read."""

    preflight = (preflight_fn or _default_preflight)()
    identity = _identity_from_preflight(preflight)
    anchor, lower, upper = _validate_limits(preflight)
    target = anchor.copy()
    for index, requested in NORMALIZATION_TARGET_DEGREES.items():
        if anchor[index] < requested:
            target[index] = requested
    delta = target - anchor
    _require(np.all(np.abs(delta[[1, 3]]) <= NORMALIZATION_MAX_DELTA_DEGREES), "normalization exceeds its bounded inward move")
    _require(np.all(target >= lower) and np.all(target <= upper), "normalization target exceeds calibrated limits")
    for index in NORMALIZATION_TARGET_DEGREES:
        _require(min(target[index] - lower[index], upper[index] - target[index]) >= NORMALIZATION_MARGIN_DEGREES, "normalization target lacks conservative calibrated margin")
    first_command = anchor.copy()
    for index in NORMALIZATION_TARGET_DEGREES:
        if first_command[index] < lower[index]:
            first_command[index] = lower[index]
        elif first_command[index] > upper[index]:
            first_command[index] = upper[index]
    _require(np.all(first_command >= lower) and np.all(first_command <= upper), "normalization first command is outside calibrated limits")
    initial_steps = max(1, int(math.ceil(float(np.max(np.abs(first_command - anchor))) / NORMALIZATION_SLEW_DEGREES_S * NORMALIZATION_SAMPLE_HZ)))
    command_delta = target - first_command
    steps = max(1, int(math.ceil(float(np.max(np.abs(command_delta[[1, 3]]))) / NORMALIZATION_SLEW_DEGREES_S * NORMALIZATION_SAMPLE_HZ)))
    timestamps = (np.arange(steps + 1, dtype=np.float64) + initial_steps) / NORMALIZATION_SAMPLE_HZ
    actions = first_command[None, :] + (np.arange(steps + 1, dtype=np.float64) / steps)[:, None] * command_delta[None, :]
    _require(np.all(actions[:, [0, 2, 4, 5]] == anchor[[0, 2, 4, 5]][None, :]), "normalization changed an uncommanded joint")
    action_hash = action_sha256(actions)
    packet = {
        "schema_version": NORMALIZATION_PACKET_SCHEMA,
        "kind": "follower_only_inward_normalization",
        "single_use": True,
        "physical_packet_execution_admitted": False,
        "independent_review": {"reviewer": None, "reviewed_at": None, "decision_id": None, "bounded_normalization_reviewed": False, "clear_workspace_acknowledged": False},
        "hardware_identity": identity,
        "anchor_degrees": anchor.tolist(),
        "first_command_degrees": actions[0].tolist(),
        "target_degrees": target.tolist(),
        "changed_joint_indices": [1, 3],
        "unchanged_joint_indices": [0, 2, 4, 5],
        "sample_hz": NORMALIZATION_SAMPLE_HZ,
        "slew_degrees_s": NORMALIZATION_SLEW_DEGREES_S,
        "calibrated_minimum_degrees": lower.tolist(),
        "calibrated_maximum_degrees": upper.tolist(),
        "timestamps_seconds": timestamps.tolist(),
        "actions_degrees": actions.tolist(),
        "action_sha256": action_hash,
        "physical_motion_commanded": False,
        "physical_follower_torque_enabled": False,
        "physical_authority": False,
    }
    packet["plan_sha256"] = _canonical(packet)
    _write_once(packet_path, packet)
    return packet


def execute_physical_canary_normalization(
    packet_path: Path,
    output_path: Path,
    *,
    operator_acknowledged: bool = False,
    preflight_fn: Callable[[], dict[str, Any]] | None = None,
    gateway_factory: Callable[[Any], Any] | None = None,
    clock_fn: Callable[[], float] = time.monotonic,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    packet = _read_json(packet_path.resolve(), "normalization packet")
    _require(packet.get("schema_version") == NORMALIZATION_PACKET_SCHEMA and packet.get("plan_sha256") == _canonical({k: v for k, v in packet.items() if k != "plan_sha256"}), "normalization packet digest changed")
    _require(operator_acknowledged, "fresh operator acknowledgement is required")
    review = packet.get("independent_review") or {}
    _require(packet.get("physical_packet_execution_admitted") is True and all(review.get(field) for field in ("reviewer", "reviewed_at", "decision_id", "bounded_normalization_reviewed", "clear_workspace_acknowledged")), "normalization packet is not independently admitted")
    _require(not output_path.exists(), f"refusing to overwrite existing output: {output_path}")
    preflight = (preflight_fn or _default_preflight)()
    identity = _identity_from_preflight(preflight)
    _require(identity == packet["hardware_identity"], "normalization hardware identity drifted")
    current, _, _ = _validate_limits(preflight)
    anchor = np.asarray(packet["anchor_degrees"], dtype=np.float64)
    _require(np.all(np.abs(_anchor_delta(current, anchor)) <= CANARY_START_TOLERANCE_DEGREES), "fresh follower pose does not match normalization anchor")
    actions = np.asarray(packet["actions_degrees"], dtype="<f8")
    timestamps = np.asarray(packet["timestamps_seconds"], dtype="<f8")
    _require(np.all(actions[0] >= np.asarray(packet["calibrated_minimum_degrees"], dtype=np.float64)) and np.all(actions[0] <= np.asarray(packet["calibrated_maximum_degrees"], dtype=np.float64)), "normalization first command exceeds sealed limits")
    _require(packet.get("action_sha256") == action_sha256(actions), "normalization action hash drifted")
    gateway = (
        gateway_factory or _default_gateway
    )(_gateway_identity(identity) if gateway_factory is None else identity)
    actual = current.copy()
    completed = 0
    started = clock_fn()
    try:
        opened = gateway.open(enable_motion=True, paired_pose_confirmed=True)
        opened_actual = np.asarray(opened["follower_start_degrees"], dtype=np.float64)
        _require(np.all(np.abs(_anchor_delta(opened_actual, anchor)) <= CANARY_START_TOLERANCE_DEGREES), "follower anchor drifted before normalization hold")
        for timestamp, action in zip(timestamps, actions, strict=True):
            delay = started + float(timestamp) - clock_fn()
            if delay > 0.0:
                sleep_fn(delay)
            sample = gateway.sample(float(timestamp), exact_requested_degrees=action)
            requested = np.asarray(sample.get("follower_requested_degrees"), dtype="<f8")
            sent = np.asarray(sample.get("follower_command_degrees"), dtype="<f8")
            _require(requested.tobytes() == action.tobytes() and sent.tobytes() == action.tobytes() and not sample.get("rate_limited") and not sample.get("safety_clamped"), "normalization action was modified by the gateway")
            actual = np.asarray(sample["follower_actual_position_degrees"], dtype=np.float64)
            completed += 1
        target = np.asarray(packet["target_degrees"], dtype=np.float64)
        _require(np.all(np.abs(_anchor_delta(actual, target)) <= CANARY_START_TOLERANCE_DEGREES), "follower did not reach the normalization target")
    finally:
        gateway.close()
    result = {
        "schema_version": NORMALIZATION_RECEIPT_SCHEMA,
        "status": "completed_follower_normalization",
        "packet_sha256": _sha256(packet_path.resolve()),
        "hardware_identity": packet["hardware_identity"],
        "completed_samples": completed,
        "final_actual_degrees": actual.tolist(),
        "target_degrees": packet["target_degrees"],
        "physical_motion_commanded": True,
        "physical_follower_torque_enabled": False,
        "physical_authority": False,
    }
    _write_once(output_path, result)
    return result


def compile_physical_canary_packet(
    bundle_path: Path,
    packet_path: Path,
    *,
    contact_receipt_path: Path,
    normalization_receipt_path: Path,
    preflight_fn: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Bind the exact canary bytes to a fresh normalized follower anchor."""

    bundle_path = bundle_path.resolve()
    bundle, actions, timestamps, raw = _decode_bundle(bundle_path)
    contact = _read_json(contact_receipt_path.resolve(), "simulation contact receipt")
    _require(contact.get("candidate_digest") == bundle.get("candidate_digest") and contact.get("action_consumer_sha256") == bundle["frozen_action_payload"]["sha256"], "simulation contact receipt is not bound to this canary")
    _require(contact.get("status") == "rejected_forbidden_contact" and contact.get("simulation_no_contact_admitted") is False and contact.get("physical_authority") is False, "simulation contact result must remain a diagnostic mismatch")
    first = (contact.get("native_contact_audit") or {}).get("first_forbidden_contact") or {}
    _require({first.get("body_a"), first.get("body_b")} in ({"left_shoulder", "left_lower_arm"}, {"left_shoulder", "left_wrist"}), "simulation contact mismatch is not the verified baseline self-contact diagnostic")
    normalization = _read_json(normalization_receipt_path.resolve(), "normalization receipt")
    _require(normalization.get("schema_version") == NORMALIZATION_RECEIPT_SCHEMA and normalization.get("status") == "completed_follower_normalization" and normalization.get("physical_follower_torque_enabled") is False and normalization.get("physical_motion_commanded") is True, "bounded normalization receipt is not complete")
    preflight = (preflight_fn or _default_preflight)()
    identity = _identity_from_preflight(preflight)
    current, lower, upper = _validate_limits(preflight)
    _require(normalization.get("hardware_identity") == identity, "normalization/follower identity drifted")
    bundle_identity = (bundle.get("identity") or {}).get("robot") or {}
    _require(bundle_identity.get("follower_port") == identity["follower_port"] and bundle_identity.get("follower_calibration_sha256") == identity["follower_calibration_sha256"] and bundle_identity.get("gateway_schema") == identity["gateway_schema"], "canary/follower identity drifted")
    anchor = np.asarray(bundle["initial_state"]["joint_position"], dtype=np.float64)
    anchor_degrees = np.rad2deg(anchor)
    _require(np.all(np.abs(_anchor_delta(current, anchor_degrees)) <= CANARY_START_TOLERANCE_DEGREES), "fresh normalized follower pose does not match the frozen canary start")
    normalized_actual = np.asarray(normalization.get("final_actual_degrees"), dtype=np.float64)
    _require(normalized_actual.shape == (6,) and np.all(np.abs(_anchor_delta(normalized_actual, anchor_degrees)) <= CANARY_START_TOLERANCE_DEGREES), "canary bundle is not bound to the completed normalization anchor")
    actions_degrees = np.rad2deg(actions)
    # The first hardware probe is deliberately shoulder-pan-only.  The
    # normalized anchor has model-baseline self contact; the verified probe
    # changes no other joint and returns byte-identically to its start.
    _require(
        np.all(actions_degrees[:, 1:] == actions_degrees[0, 1:][None, :]),
        "physical canary must leave non-shoulder-pan joints byte-identical",
    )
    _require(
        float(np.max(np.abs(actions_degrees[:, 0] - actions_degrees[0, 0]))) <= 1.0 + 1e-9
        and np.array_equal(actions_degrees[-1], actions_degrees[0]),
        "physical canary must be a bounded shoulder-pan +/-1 degree return-to-start",
    )
    _require(np.all(actions_degrees >= lower) and np.all(actions_degrees <= upper), "frozen canary exceeds follower calibrated limits")
    rates = np.diff(actions_degrees, axis=0) / np.diff(timestamps)[:, None]
    _require(float(np.max(np.abs(rates[:, :4]))) <= CANARY_BODY_RATE_DEGREES_S + 1e-9 and float(np.max(np.abs(rates[:, 4]))) <= CANARY_WRIST_ROLL_RATE_DEGREES_S + 1e-9 and float(np.max(np.abs(rates[:, 5]))) <= CANARY_GRIPPER_RATE_S + 1e-9, "frozen canary exceeds gateway slew bounds")
    packet = {
        "schema_version": PHYSICAL_CANARY_PACKET_SCHEMA,
        "kind": "follower_only_frozen_simulation_canary",
        "single_use": True,
        "physical_packet_execution_admitted": False,
        "independent_review": {"reviewer": None, "reviewed_at": None, "decision_id": None, "frozen_action_reviewed": False, "hardware_clear_workspace_acknowledged": False, "hardware_readiness_acknowledged": False, "diagnostic_sim_model_mismatch_acknowledged": False},
        "bundle_path": str(bundle_path),
        "bundle_sha256": _sha256(bundle_path),
        "candidate_digest": bundle["candidate_digest"],
        "hardware_identity": identity,
        "anchor_degrees": current.tolist(),
        "calibrated_minimum_degrees": lower.tolist(),
        "calibrated_maximum_degrees": upper.tolist(),
        "timestamps_seconds": timestamps.tolist(),
        "frozen_action_payload": bundle["frozen_action_payload"],
        "action_sha256": action_sha256(actions),
        "action_bytes_sha256": hashlib.sha256(raw).hexdigest(),
        "source_contact_receipt": {"path": str(contact_receipt_path.resolve()), "sha256": _sha256(contact_receipt_path.resolve())},
        "source_normalization_receipt": {"path": str(normalization_receipt_path.resolve()), "sha256": _sha256(normalization_receipt_path.resolve())},
        "simulation_contact_classification": "diagnostic_sim_model_baseline_self_contact",
        "hardware_gate": "no_new_or_worsened_kinematic_contact_plus_clear_workspace_and_bounded_normalization",
        "physical_authority": False,
    }
    packet["plan_sha256"] = _canonical(packet)
    _write_once(packet_path, packet)
    return packet


def execute_physical_canary_packet(
    packet_path: Path,
    output_directory: Path,
    *,
    operator_acknowledged: bool = False,
    preflight_fn: Callable[[], dict[str, Any]] | None = None,
    gateway_factory: Callable[[Any], Any] | None = None,
    capture_factory: Callable[[Path], CameraCapture] | None = None,
    clock_fn: Callable[[], float] = time.monotonic,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    packet_path = packet_path.resolve()
    packet = _read_json(packet_path, "physical canary packet")
    _require(packet.get("schema_version") == PHYSICAL_CANARY_PACKET_SCHEMA and packet.get("plan_sha256") == _canonical({k: v for k, v in packet.items() if k != "plan_sha256"}), "physical canary packet digest changed")
    _require(operator_acknowledged, "fresh operator acknowledgement is required")
    review = packet.get("independent_review") or {}
    _require(packet.get("physical_packet_execution_admitted") is True and all(review.get(field) for field in ("reviewer", "reviewed_at", "decision_id", "frozen_action_reviewed", "hardware_clear_workspace_acknowledged", "hardware_readiness_acknowledged", "diagnostic_sim_model_mismatch_acknowledged")), "physical canary packet is not independently admitted")
    output_directory = output_directory.resolve()
    output_path = output_directory / "execution_receipt.json"
    samples_path = output_directory / "joint_samples.jsonl"
    _require(not output_path.exists() and not samples_path.exists(), "refusing to overwrite physical canary output")
    bundle_path = Path(packet["bundle_path"]).resolve()
    _require(_sha256(bundle_path) == packet["bundle_sha256"], "simulation canary bundle drifted")
    bundle, actions, timestamps, raw = _decode_bundle(bundle_path)
    _require(bundle["candidate_digest"] == packet["candidate_digest"] and action_sha256(actions) == packet["action_sha256"] and raw == base64.b64decode(packet["frozen_action_payload"]["base64"], validate=True), "physical canary frozen bytes drifted")
    preflight = (preflight_fn or _default_preflight)()
    identity = _identity_from_preflight(preflight)
    _require(identity == packet["hardware_identity"], "physical canary follower identity drifted")
    current, lower, upper = _validate_limits(preflight)
    anchor = np.asarray(packet["anchor_degrees"], dtype=np.float64)
    _require(np.all(np.abs(_anchor_delta(current, anchor)) <= CANARY_START_TOLERANCE_DEGREES), "fresh follower pose does not match the normalized canary anchor")
    actions_degrees = np.rad2deg(actions)
    _require(np.all(actions_degrees >= lower) and np.all(actions_degrees <= upper), "frozen canary exceeds fresh calibrated limits")
    gateway = (
        gateway_factory or _default_gateway
    )(_gateway_identity(identity) if gateway_factory is None else identity)
    capture: CameraCapture | None = None
    camera_started: dict[str, Any] | None = None
    camera_finished: dict[str, Any] | None = None
    completed = 0
    actual = current.copy()
    started = clock_fn()
    action_started: float | None = None
    action_stopped: float | None = None
    error: Exception | None = None
    try:
        output_directory.mkdir(parents=True, exist_ok=True)
        samples_path.open("x").close()
        capture = (capture_factory or _default_capture)(output_directory / "dual_camera")
        camera_started = capture.start()
        opened = gateway.open(enable_motion=True, paired_pose_confirmed=True)
        opened_start = np.asarray(opened["follower_start_degrees"], dtype=np.float64)
        _require(np.all(np.abs(_anchor_delta(opened_start, anchor)) <= CANARY_START_TOLERANCE_DEGREES), "follower anchor drifted before canary hold")
        action_started = clock_fn()
        with samples_path.open("a", encoding="utf-8") as handle:
            for index, (timestamp, action, target) in enumerate(zip(timestamps, actions, actions_degrees, strict=True)):
                delay = action_started + float(timestamp) - clock_fn()
                if delay > 0.0:
                    sleep_fn(delay)
                sample = gateway.sample(float(timestamp), exact_requested_degrees=target)
                requested = np.asarray(sample.get("follower_requested_degrees"), dtype="<f8")
                sent = np.asarray(sample.get("follower_command_degrees"), dtype="<f8")
                _require(requested.tobytes() == target.tobytes() and sent.tobytes() == target.tobytes() and not sample.get("rate_limited") and not sample.get("safety_clamped"), "gateway modified or clipped the frozen canary target")
                actual = np.asarray(sample["follower_actual_position_degrees"], dtype=np.float64)
                handle.write(json.dumps({"sample_index": index, "timestamp_seconds": float(timestamp), "source_action_sha256": packet["action_sha256"], "requested_radians": action.tolist(), "requested_degrees": target.tolist(), **sample}, sort_keys=True) + "\n")
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
                camera_finished = capture.finish(action_started_monotonic=action_started, action_stopped_monotonic=action_stopped, post_roll_seconds=0.5)
            except Exception as caught:
                error = error or caught
    if error is not None:
        raise PhysicalCanaryError(f"physical canary stopped safely with torque off: {error}") from error
    _require(
        np.all(np.abs(_anchor_delta(actual, anchor)) <= CANARY_START_TOLERANCE_DEGREES),
        "physical canary did not return to its exact normalized start",
    )
    receipt = {"schema_version": EXECUTION_RECEIPT_SCHEMA, "status": "completed_physical_canary", "packet_sha256": _sha256(packet_path), "action_sha256": packet["action_sha256"], "completed_samples": completed, "joint_samples_path": str(samples_path), "joint_samples_sha256": _sha256(samples_path), "camera_started": camera_started, "camera_finished": camera_finished, "final_actual_degrees": actual.tolist(), "physical_motion_commanded": True, "physical_follower_torque_enabled": False, "physical_authority": False, "gateway_constructed": True, "stop_before_further_robot_command": True}
    _write_once(output_path, receipt)
    return receipt
