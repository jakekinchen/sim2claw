"""Bounded dual-camera HIL packets for current-workcell identifiability.

The runner owns acquisition only. A separate pure evaluator reads the frozen
raw artifacts and applies the preregistered admission thresholds. Unloaded HIL
packets never grant task, training, promotion, or physical-transfer authority.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

import numpy as np

from .overhead_video import (
    OverheadVideoRecorder,
    WristVideoRecorder,
    list_avfoundation_cameras,
)
from .paths import REPO_ROOT
from .physical_gateway import GatewayIdentity, shortest_delta_degrees
from .physical_trace_replay import (
    PhysicalTraceReplayError,
    physical_replay_gateway,
    run_physical_trace_replay,
    validate_replay_envelope,
)
from .scene import ROBOT_JOINTS
from .teleop_recording import RECEIPT_SCHEMA, physical_gateway_preflight


CONTRACT_SCHEMA = "sim2claw.current_100mm_hil_identifiability.v1"
CONTRACT_SCHEMA_V2 = "sim2claw.current_100mm_hil_identifiability.v2"
RAW_RECEIPT_SCHEMA = "sim2claw.current_100mm_hil_raw_packet.v1"
EVALUATION_SCHEMA = "sim2claw.current_100mm_hil_packet_evaluation.v1"
CAMPAIGN_SCHEMA = "sim2claw.current_100mm_hil_campaign.v1"
PROOF_CLASS = "physical_hil_unloaded_joint_observation"
EVALUATION_PROOF_CLASS = "derived_hil_joint_identifiability_evaluation"
DEFAULT_CONTRACT = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "current_100mm_hil_identifiability_v1.json"
)


class HILIdentifiabilityError(RuntimeError):
    """Expected fail-closed HIL acquisition or evaluation error."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def load_hil_contract(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HILIdentifiabilityError(f"HIL contract is unreadable: {error}") from error
    schema = contract.get("schema_version")
    if schema not in {CONTRACT_SCHEMA, CONTRACT_SCHEMA_V2}:
        raise HILIdentifiabilityError("HIL contract schema is unsupported.")
    packets = contract.get("packets")
    expected_packets = 4 if schema == CONTRACT_SCHEMA else 6
    if not isinstance(packets, list) or len(packets) != expected_packets:
        raise HILIdentifiabilityError(
            f"HIL {schema} contract requires exactly {expected_packets} packets."
        )
    packet_ids = [row.get("packet_id") for row in packets]
    if len(set(packet_ids)) != expected_packets or any(not value for value in packet_ids):
        raise HILIdentifiabilityError("HIL packet identifiers must be unique.")
    if int(contract["budget"]["physical_packet_attempts"]) != expected_packets:
        raise HILIdentifiabilityError(
            "HIL physical attempt budget must equal the packet inventory."
        )
    if int(contract["budget"]["adaptive_retries"]) != 0:
        raise HILIdentifiabilityError("HIL adaptive retries must remain zero.")
    if int(contract["action_materialization"]["sample_hz"]) != 20:
        raise HILIdentifiabilityError("HIL action materialization is frozen at 20 Hz.")
    if contract["action_materialization"]["joint_order"] != list(ROBOT_JOINTS):
        raise HILIdentifiabilityError("HIL joint order does not match the gateway.")
    if schema == CONTRACT_SCHEMA_V2:
        target_joints = [row.get("target_joint") for row in packets]
        if target_joints != list(ROBOT_JOINTS):
            raise HILIdentifiabilityError(
                "HIL v2 must preregister one ordered packet per gateway joint."
            )
        for packet in packets:
            segments = packet.get("segments")
            if (
                not isinstance(segments, list)
                or len(segments) < 2
                or float(segments[-1].get("target_offset", math.nan)) != 0.0
            ):
                raise HILIdentifiabilityError(
                    "HIL v2 segments must be non-empty and return to zero."
                )
            for segment in segments:
                values = (
                    segment.get("target_offset"),
                    segment.get("ramp_seconds"),
                    segment.get("hold_seconds"),
                )
                if not all(
                    isinstance(value, (int, float)) and math.isfinite(float(value))
                    for value in values
                ):
                    raise HILIdentifiabilityError(
                        "HIL v2 segment values must be finite."
                    )
                if (
                    float(segment["ramp_seconds"]) <= 0.0
                    or float(segment["hold_seconds"]) <= 0.0
                ):
                    raise HILIdentifiabilityError(
                        "HIL v2 segment durations must be positive."
                    )
    return contract


def _packet(contract: dict[str, Any], packet_id: str) -> dict[str, Any]:
    try:
        return next(
            row for row in contract["packets"] if row["packet_id"] == packet_id
        )
    except StopIteration as error:
        raise HILIdentifiabilityError(f"Unknown HIL packet: {packet_id}") from error


def materialize_packet_actions(
    contract: dict[str, Any],
    packet_id: str,
    start_degrees: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Create the frozen 20 Hz absolute command tensor from one live start."""

    start = np.asarray(start_degrees, dtype=np.float64)
    if start.shape != (6,) or not np.all(np.isfinite(start)):
        raise HILIdentifiabilityError("HIL start pose requires six finite values.")
    packet = _packet(contract, packet_id)
    try:
        target_index = list(ROBOT_JOINTS).index(packet["target_joint"])
    except ValueError as error:
        raise HILIdentifiabilityError("HIL target joint is unsupported.") from error
    sample_hz = int(contract["action_materialization"]["sample_hz"])
    pre_hold = round(
        float(contract["action_materialization"]["pre_hold_seconds"]) * sample_hz
    )
    post_hold = round(
        float(contract["action_materialization"]["post_return_hold_seconds"])
        * sample_hz
    )
    if min(pre_hold, post_hold) < 1:
        raise HILIdentifiabilityError("HIL segment duration is too short.")

    actions: list[np.ndarray] = [start.copy() for _ in range(pre_hold + 1)]
    if contract["schema_version"] == CONTRACT_SCHEMA:
        offsets = np.asarray(packet["offset_sequence"], dtype=np.float64)
        if (
            offsets.ndim != 1
            or offsets.size < 2
            or not np.all(np.isfinite(offsets))
            or abs(float(offsets[0])) > 1e-12
            or abs(float(offsets[-1])) > 1e-12
        ):
            raise HILIdentifiabilityError(
                "HIL offset sequence must be finite and start/end at zero."
            )
        segment_rows = [
            {
                "source_offset": float(source_offset),
                "target_offset": float(target_offset),
                "ramp_seconds": float(packet["ramp_seconds"]),
                "hold_seconds": float(packet["hold_seconds"]),
            }
            for source_offset, target_offset in zip(
                offsets[:-1], offsets[1:], strict=True
            )
        ]
    else:
        segment_rows = []
        source_offset = 0.0
        for segment in packet["segments"]:
            target_offset = float(segment["target_offset"])
            segment_rows.append(
                {
                    "source_offset": source_offset,
                    "target_offset": target_offset,
                    "ramp_seconds": float(segment["ramp_seconds"]),
                    "hold_seconds": float(segment["hold_seconds"]),
                }
            )
            source_offset = target_offset

    for segment in segment_rows:
        source_offset = float(segment["source_offset"])
        target_offset = float(segment["target_offset"])
        ramp_steps = round(float(segment["ramp_seconds"]) * sample_hz)
        hold_steps = round(float(segment["hold_seconds"]) * sample_hz)
        if min(ramp_steps, hold_steps) < 1:
            raise HILIdentifiabilityError("HIL segment duration is too short.")
        for index in range(1, ramp_steps + 1):
            fraction = index / ramp_steps
            smooth = fraction * fraction * (3.0 - 2.0 * fraction)
            action = start.copy()
            action[target_index] += float(
                source_offset + smooth * (target_offset - source_offset)
            )
            actions.append(action)
        for _ in range(hold_steps):
            action = start.copy()
            action[target_index] += float(target_offset)
            actions.append(action)
    actions.extend(start.copy() for _ in range(post_hold))
    tensor = np.ascontiguousarray(np.asarray(actions, dtype="<f8"))
    timestamps = np.arange(tensor.shape[0], dtype=np.float64) / sample_hz
    if not np.array_equal(tensor[0], tensor[-1]):
        raise HILIdentifiabilityError("HIL packet must return exactly to its start.")
    return timestamps, tensor


def action_tensor_sha256(actions: np.ndarray) -> str:
    tensor = np.ascontiguousarray(np.asarray(actions, dtype="<f8"))
    if tensor.ndim != 2 or tensor.shape[1:] != (6,):
        raise HILIdentifiabilityError("HIL action tensor must have shape [N, 6].")
    return hashlib.sha256(tensor.tobytes(order="C")).hexdigest()


def _materialize_source(
    directory: Path,
    *,
    contract: dict[str, Any],
    packet: dict[str, Any],
    timestamps: np.ndarray,
    actions: np.ndarray,
) -> dict[str, Any]:
    directory.mkdir(parents=True, exist_ok=False)
    samples_path = directory / "samples.jsonl"
    with samples_path.open("w", encoding="utf-8") as handle:
        for index, (timestamp, action) in enumerate(
            zip(timestamps, actions, strict=True)
        ):
            row = {
                "sample_index": index,
                "timestamp_monotonic_seconds": float(timestamp),
                "follower_command_degrees": action.tolist(),
                "action_owner": "preregistered_hil_contract",
                "assistance": 0,
                "intervention": 0,
            }
            handle.write(
                json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n"
            )
    action_path = directory / "action_tensor.npy"
    np.save(action_path, np.ascontiguousarray(actions, dtype="<f8"), allow_pickle=False)
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "recording_id": packet["packet_id"],
        "mode": "physical_follower",
        "label": f"{packet['packet_id']} preregistered unloaded HIL packet",
        "sample_count": int(actions.shape[0]),
        "samples_sha256": _sha256(samples_path),
        "action_tensor_path": action_path.name,
        "action_tensor_file_sha256": _sha256(action_path),
        "action_tensor_sha256": action_tensor_sha256(actions),
        "contract_id": contract["contract_id"],
        "proof_class": "preregistered_physical_hil_action_packet",
        "task_claim": False,
        "training_admission": False,
    }
    _atomic_json(directory / "recording_receipt.json", receipt)
    return receipt


def _video_counts(report: dict[str, Any]) -> tuple[int, float]:
    observed = report.get("observed_video") or {}
    streams = observed.get("streams") or []
    stream = streams[0] if streams else {}
    format_row = observed.get("format") or {}
    try:
        frames = int(stream.get("nb_frames") or 0)
    except (TypeError, ValueError):
        frames = 0
    try:
        duration = float(format_row.get("duration") or 0.0)
    except (TypeError, ValueError):
        duration = 0.0
    if frames == 0 and report.get("browser_video_path"):
        browser = report.get("browser_observed_video") or {}
        browser_streams = browser.get("streams") or []
        browser_stream = browser_streams[0] if browser_streams else {}
        browser_format = browser.get("format") or {}
        try:
            frames = int(browser_stream.get("nb_frames") or 0)
        except (TypeError, ValueError):
            frames = 0
        if duration <= 0.0:
            try:
                duration = float(browser_format.get("duration") or 0.0)
            except (TypeError, ValueError):
                duration = 0.0
    return frames, duration


def _video_container_timing(
    report: dict[str, Any],
    *,
    prefer_browser_derivative: bool,
) -> dict[str, Any]:
    if prefer_browser_derivative and report.get("browser_video_path"):
        browser = report.get("browser_observed_video") or {}
        timing = browser.get("container_timing")
        if isinstance(timing, dict):
            return timing
    observed = report.get("observed_video") or {}
    timing = observed.get("container_timing")
    return timing if isinstance(timing, dict) else {}


def _relative_artifacts(session: Path, paths: list[Path]) -> dict[str, str]:
    return {
        str(path.relative_to(session)): _sha256(path)
        for path in paths
        if path.is_file()
    }


def evaluate_hil_packet(raw_receipt_path: Path, contract_path: Path) -> dict[str, Any]:
    """Independently validate raw bytes and apply evaluator-owned gates."""

    contract = load_hil_contract(contract_path)
    try:
        raw = json.loads(raw_receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HILIdentifiabilityError(f"HIL raw receipt is unreadable: {error}") from error
    if raw.get("schema_version") != RAW_RECEIPT_SCHEMA:
        raise HILIdentifiabilityError("HIL raw receipt schema is unsupported.")
    session = raw_receipt_path.parent
    failures: list[str] = []
    for relative, expected in raw.get("artifact_sha256", {}).items():
        path = (session / relative).resolve()
        if not path.is_relative_to(session.resolve()) or not path.is_file():
            failures.append(f"artifact_missing:{relative}")
        elif _sha256(path) != expected:
            failures.append(f"artifact_hash_mismatch:{relative}")

    source = session / "source"
    action_path = source / "action_tensor.npy"
    replay_receipt_path = Path(raw["replay_receipt_path"]).resolve()
    if not replay_receipt_path.is_relative_to(session.resolve()):
        raise HILIdentifiabilityError(
            "HIL replay receipt must remain inside its packet directory."
        )
    replay_samples_path = replay_receipt_path.parent / "replay_samples.jsonl"
    try:
        actions = np.load(action_path, allow_pickle=False)
        replay = json.loads(replay_receipt_path.read_text(encoding="utf-8"))
        rows = [
            json.loads(line)
            for line in replay_samples_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise HILIdentifiabilityError(
            f"HIL evaluator could not load raw packet bytes: {error}"
        ) from error
    source_rows = [
        row for row in rows if row.get("replay_phase", "source_trace") == "source_trace"
    ]
    if action_tensor_sha256(actions) != raw.get("action_tensor_sha256"):
        failures.append("action_tensor_digest_mismatch")
    if len(source_rows) != int(actions.shape[0]):
        failures.append("source_row_count_mismatch")
    else:
        requested = np.asarray(
            [row["requested_source_command_degrees"] for row in source_rows],
            dtype="<f8",
        )
        if not np.array_equal(requested, actions):
            failures.append("requested_action_bytes_changed")

    packet = _packet(contract, str(raw["packet_id"]))
    joint_index = list(ROBOT_JOINTS).index(packet["target_joint"])
    actual = np.asarray(
        [row["follower_actual_position_degrees"] for row in source_rows],
        dtype=np.float64,
    )
    actual_span = (
        0.0
        if actual.size == 0
        else float(np.max(actual[:, joint_index]) - np.min(actual[:, joint_index]))
    )
    if actual_span < float(packet["required_position_span"]):
        failures.append("required_position_span_not_observed")

    final_residual = np.full(6, np.inf, dtype=np.float64)
    if actual.size:
        final_residual = actions[0] - actual[-1]
        final_residual[4] = shortest_delta_degrees(
            float(actions[0, 4]), float(actual[-1, 4])
        )
    thresholds = contract["packet_admission"]
    if float(np.max(np.abs(final_residual[:5]))) > float(
        thresholds["body_final_residual_degrees_maximum"]
    ):
        failures.append("body_return_residual_exceeded")
    if abs(float(final_residual[5])) > float(
        thresholds["gripper_final_residual_maximum"]
    ):
        failures.append("gripper_return_residual_exceeded")

    refresh_times = {
        round(float(row["current_telemetry_elapsed_seconds"]), 6)
        for row in source_rows
        if row.get("available_motor_current_raw") is not None
        and row.get("current_telemetry_elapsed_seconds") is not None
        and not row.get("current_telemetry_stale", True)
    }
    duration = float((actions.shape[0] - 1) / 20.0)
    expected_refreshes = max(1, math.floor(duration * 5.0) + 1)
    current_coverage = min(1.0, len(refresh_times) / expected_refreshes)
    if current_coverage < float(
        thresholds["current_refresh_coverage_fraction_minimum"]
    ):
        failures.append("current_refresh_coverage_failed")

    maximum_bus_retries = max(
        (int(row.get("bus_read_retries_total") or 0) for row in source_rows),
        default=0,
    )
    if maximum_bus_retries > int(thresholds["bus_retry_count_maximum"]):
        failures.append("bus_retry_budget_exceeded")
    if any(bool(row.get("stalled")) for row in source_rows):
        failures.append("stall_observed")
    if replay.get("status") != "completed":
        failures.append("physical_replay_not_completed")

    camera_metrics: dict[str, Any] = {}
    for role, report_name, configured_fps, threshold_name in (
        (
            "overhead",
            "overhead_video.json",
            30.0,
            "overhead_frame_coverage_fraction_minimum",
        ),
        ("wrist", "wrist_video.json", 5.0, "wrist_frame_coverage_fraction_minimum"),
    ):
        try:
            report = json.loads((session / report_name).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            report = {}
        frames, video_duration = _video_counts(report)
        frame_coverage = min(
            1.0,
            frames / max(1.0, duration * configured_fps),
        )
        camera_metrics[role] = {
            "status": report.get("status"),
            "frames": frames,
            "duration_seconds": video_duration,
            "frame_coverage_fraction": frame_coverage,
        }
        if thresholds.get("container_timing_required") is True:
            timing = _video_container_timing(
                report,
                prefer_browser_derivative=role == "wrist",
            )
            inferred_missing = timing.get("inferred_missing_frame_intervals")
            try:
                inferred_missing_count = int(inferred_missing)
            except (TypeError, ValueError):
                inferred_missing_count = -1
            denominator = frames + max(0, inferred_missing_count)
            inferred_missing_fraction = (
                None
                if inferred_missing_count < 0
                else inferred_missing_count / max(1, denominator)
            )
            camera_metrics[role]["container_timing"] = timing
            camera_metrics[role][
                "inferred_missing_frame_interval_fraction"
            ] = inferred_missing_fraction
            if timing.get("status") != "observed_container_timing":
                failures.append(f"{role}_container_timing_unavailable")
            maximum_name = (
                f"{role}_inferred_missing_frame_interval_fraction_maximum"
            )
            if (
                inferred_missing_fraction is None
                or inferred_missing_fraction > float(thresholds[maximum_name])
            ):
                failures.append(f"{role}_container_timing_gap_fraction_failed")
        if report.get("status") != "completed":
            failures.append(f"{role}_video_not_completed")
        if frame_coverage < float(thresholds[threshold_name]):
            failures.append(f"{role}_frame_coverage_failed")

    admitted = not failures
    evaluation = {
        "schema_version": EVALUATION_SCHEMA,
        "contract_id": contract["contract_id"],
        "packet_id": raw["packet_id"],
        "proof_class": EVALUATION_PROOF_CLASS,
        "verdict": "admit_unloaded_joint_measurement" if admitted else "reject_packet",
        "admitted": admitted,
        "failures": failures,
        "action_tensor_sha256": raw.get("action_tensor_sha256"),
        "source_sample_count": int(actions.shape[0]),
        "target_joint": packet["target_joint"],
        "actual_position_span": actual_span,
        "required_position_span": float(packet["required_position_span"]),
        "final_residual_degrees": final_residual.tolist(),
        "current_refresh_count": len(refresh_times),
        "expected_current_refresh_count": expected_refreshes,
        "current_refresh_coverage_fraction": current_coverage,
        "maximum_bus_retries": maximum_bus_retries,
        "camera_metrics": camera_metrics,
        "unknown_observables": [
            "force",
            "deformation",
            "metric_wrist_depth",
            "contact_state",
            "camera_to_gripper_extrinsics",
        ],
        "authority": {
            "unloaded_joint_measurement": admitted,
            "task_success": False,
            "training": False,
            "promotion": False,
            "physical_transfer": False,
        },
    }
    evaluation["evaluation_digest"] = _canonical_digest(evaluation)
    return evaluation


def _identity_from_report(report: dict[str, Any]) -> GatewayIdentity:
    return GatewayIdentity(
        leader_port=str(report["leader_port"]),
        follower_port=str(report["follower_port"]),
        leader_calibration_sha256=str(report["leader_calibration_sha256"]),
        follower_calibration_sha256=str(report["follower_calibration_sha256"]),
    )


def _verify_preflight(
    contract: dict[str, Any],
    gateway_report: dict[str, Any],
    camera_report: dict[str, Any],
) -> None:
    expected = contract["hardware_identity"]
    for field in (
        "leader_port",
        "follower_port",
        "leader_calibration_sha256",
        "follower_calibration_sha256",
    ):
        if gateway_report.get(field) != expected[field]:
            raise HILIdentifiabilityError(f"HIL hardware identity mismatch: {field}")
    if gateway_report.get("physical_follower_torque_enabled") is not False:
        raise HILIdentifiabilityError("Follower torque must be off before HIL packet.")
    detected = {row["name"] for row in camera_report.get("cameras", [])}
    for field in ("overhead_name", "wrist_name"):
        if contract["camera_identity"][field] not in detected:
            raise HILIdentifiabilityError(f"Required HIL camera missing: {field}")


def execute_hil_packet(
    contract_path: Path,
    packet_id: str,
    output_root: Path,
    *,
    operator_acknowledged: bool,
    gateway_preflight: Callable[[], dict[str, Any]] = physical_gateway_preflight,
    camera_inventory: Callable[[], dict[str, Any]] = list_avfoundation_cameras,
    replay_runner: Callable[..., dict[str, Any]] = run_physical_trace_replay,
    overhead_factory: Callable[[Path], Any] = OverheadVideoRecorder,
    wrist_factory: Callable[[Path], Any] = WristVideoRecorder,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Execute one preregistered packet exactly once."""

    if not operator_acknowledged:
        raise HILIdentifiabilityError("HIL physical safety acknowledgement is required.")
    contract = load_hil_contract(contract_path)
    packet = _packet(contract, packet_id)
    session = output_root.resolve() / packet_id
    if session.exists():
        raise HILIdentifiabilityError(
            f"HIL packet output already exists and cannot be replayed: {packet_id}"
        )
    gateway_report = gateway_preflight()
    camera_report = camera_inventory()
    _verify_preflight(contract, gateway_report, camera_report)
    start = np.asarray(gateway_report["follower_start_degrees"], dtype=np.float64)
    timestamps, actions = materialize_packet_actions(contract, packet_id, start)
    validate_replay_envelope(
        actions,
        start,
        lower_limits=np.asarray(
            gateway_report["follower_calibrated_minimum"], dtype=np.float64
        ),
        upper_limits=np.asarray(
            gateway_report["follower_calibrated_maximum"], dtype=np.float64
        ),
    )

    session.mkdir(parents=True, exist_ok=False)
    source = session / "source"
    source_receipt = _materialize_source(
        source,
        contract=contract,
        packet=packet,
        timestamps=timestamps,
        actions=actions,
    )
    overhead = overhead_factory(session / "overhead_c922.mp4")
    wrist = wrist_factory(session / "wrist_d405.mkv")
    overhead_start: dict[str, Any] | None = None
    wrist_start: dict[str, Any] | None = None
    overhead_report: dict[str, Any] = {"status": "not_started"}
    wrist_report: dict[str, Any] = {"status": "not_started"}
    action_started: float | None = None
    action_stopped: float | None = None
    replay: dict[str, Any] | None = None
    replay_error: PhysicalTraceReplayError | None = None
    identity = _identity_from_report(gateway_report)
    try:
        overhead_start = overhead.start()
        wrist_start = wrist.start()

        def progress(_row: dict[str, Any]) -> None:
            overhead.ensure_running()
            wrist.ensure_running()

        action_started = clock()
        try:
            replay = replay_runner(
                source,
                operator_acknowledged=True,
                output_root=session / "replay",
                identity=identity,
                gateway_factory=lambda gateway_identity: physical_replay_gateway(
                    gateway_identity,
                    current_telemetry_hz=5.0,
                ),
                progress=progress,
                allowed_source_root=source,
                controlled_return_on_failure=True,
                controlled_return_hold_seconds=3.0,
            )
        except PhysicalTraceReplayError as error:
            replay_error = error
            if error.run_directory is not None:
                receipt_path = error.run_directory / "replay_receipt.json"
                if receipt_path.is_file():
                    replay = json.loads(receipt_path.read_text(encoding="utf-8"))
                    replay["run_directory"] = str(error.run_directory)
        action_stopped = clock()
    finally:
        if action_started is not None and action_stopped is None:
            action_stopped = clock()
        if overhead_start is not None:
            overhead_report = overhead.finish(
                action_started_monotonic=action_started,
                action_stopped_monotonic=action_stopped,
                post_roll_seconds=1.0,
            )
        if wrist_start is not None:
            wrist_report = wrist.finish(
                action_started_monotonic=action_started,
                action_stopped_monotonic=action_stopped,
                post_roll_seconds=1.0,
            )
        _atomic_json(session / "overhead_video.json", overhead_report)
        _atomic_json(session / "wrist_video.json", wrist_report)

    if replay is None:
        raise HILIdentifiabilityError(
            f"HIL replay produced no receipt: {replay_error or 'unknown failure'}"
        )
    replay_directory = Path(str(replay["run_directory"])).resolve()
    replay_receipt_path = replay_directory / "replay_receipt.json"
    paths = [
        source / "samples.jsonl",
        source / "recording_receipt.json",
        source / "action_tensor.npy",
        session / "overhead_video.json",
        session / "wrist_video.json",
        session / "overhead_c922.mp4",
        session / "overhead_c922.ffmpeg.log",
        session / "wrist_d405.mkv",
        session / "wrist_d405.browser.mp4",
        session / "wrist_d405.ffmpeg.log",
        replay_receipt_path,
        replay_directory / "replay_samples.jsonl",
    ]
    raw = {
        "schema_version": RAW_RECEIPT_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_file_sha256": _sha256(contract_path),
        "packet_id": packet_id,
        "proof_class": PROOF_CLASS,
        "captured_start_degrees": start.tolist(),
        "action_tensor_sha256": source_receipt["action_tensor_sha256"],
        "action_sample_count": int(actions.shape[0]),
        "action_duration_seconds": float(timestamps[-1]),
        "hardware_preflight": gateway_report,
        "camera_inventory": camera_report,
        "overhead_video_start": overhead_start,
        "wrist_video_start": wrist_start,
        "replay_receipt_path": str(replay_receipt_path),
        "physical_attempt_consumed": True,
        "physical_replay_status": replay.get("status"),
        "physical_replay_failure": (
            None
            if replay_error is None
            else {
                "type": type(replay_error).__name__,
                "message": str(replay_error),
            }
        ),
        "artifact_sha256": _relative_artifacts(session, paths),
        "task_success_verified": False,
        "training_admission": False,
        "promotion_authority": False,
        "physical_follower_torque_enabled_after": False,
        "created_at": datetime.now(UTC).isoformat(),
    }
    raw["raw_receipt_digest"] = _canonical_digest(raw)
    raw_path = session / "raw_receipt.json"
    _atomic_json(raw_path, raw)
    evaluation = evaluate_hil_packet(raw_path, contract_path)
    evaluation_path = session / "evaluation.json"
    _atomic_json(evaluation_path, evaluation)
    return {
        "packet_id": packet_id,
        "session_directory": str(session),
        "raw_receipt_path": str(raw_path),
        "raw_receipt_sha256": _sha256(raw_path),
        "evaluation_path": str(evaluation_path),
        "evaluation_sha256": _sha256(evaluation_path),
        "action_tensor_sha256": raw["action_tensor_sha256"],
        "physical_attempt_consumed": True,
        "replay_status": replay.get("status"),
        "verdict": evaluation["verdict"],
        "admitted": evaluation["admitted"],
    }


def run_hil_campaign(
    contract_path: Path,
    output_root: Path,
    *,
    operator_acknowledged: bool,
    packet_id: str | None = None,
    **packet_kwargs: Any,
) -> dict[str, Any]:
    """Run selected preregistered packets without retries."""

    contract = load_hil_contract(contract_path)
    maximum_attempts = int(contract["budget"]["physical_packet_attempts"])
    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    state_path = output_root / "campaign_state.json"
    if state_path.is_file():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state.get("schema_version") != CAMPAIGN_SCHEMA:
            raise HILIdentifiabilityError("Existing HIL campaign state is invalid.")
        if state.get("contract_id") != contract["contract_id"]:
            raise HILIdentifiabilityError(
                "Existing HIL campaign is bound to another contract."
            )
        if (
            int(state.get("budget", {}).get("maximum_physical_packet_attempts", -1))
            != maximum_attempts
        ):
            raise HILIdentifiabilityError(
                "Existing HIL campaign attempt budget does not match the contract."
            )
    else:
        state = {
            "schema_version": CAMPAIGN_SCHEMA,
            "contract_id": contract["contract_id"],
            "contract_file_sha256": _sha256(contract_path),
            "events": [],
            "budget": {
                "maximum_physical_packet_attempts": maximum_attempts,
                "used_physical_packet_attempts": 0,
                "adaptive_retries": 0,
                "provider_calls": 0,
            },
            "authority": {
                "task_success": False,
                "training": False,
                "promotion": False,
                "physical_transfer": False,
            },
        }
        _atomic_json(state_path, state)
    executed = {event["packet_id"] for event in state["events"]}
    requested_ids = (
        [packet_id] if packet_id is not None else [row["packet_id"] for row in contract["packets"]]
    )
    for current_id in requested_ids:
        if current_id in executed:
            raise HILIdentifiabilityError(
                f"HIL packet already consumed and cannot be retried: {current_id}"
            )
        if int(state["budget"]["used_physical_packet_attempts"]) >= maximum_attempts:
            raise HILIdentifiabilityError("HIL physical attempt budget is exhausted.")
        event = execute_hil_packet(
            contract_path,
            current_id,
            output_root,
            operator_acknowledged=operator_acknowledged,
            **packet_kwargs,
        )
        state["events"].append(event)
        state["budget"]["used_physical_packet_attempts"] += int(
            event["physical_attempt_consumed"]
        )
        _atomic_json(state_path, state)
        executed.add(current_id)
        if event["replay_status"] != "completed":
            break
    return {
        **state,
        "campaign_state_path": str(state_path),
        "campaign_state_sha256": _sha256(state_path),
    }
