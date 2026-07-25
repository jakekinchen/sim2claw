"""Bind one native D405 recording to a live-anchored terminal hold.

Importing this module accesses no hardware. The default runtime starts
``rs-record`` itself; tests inject recorder and route fixtures. Only depth
frames whose clock-uncertainty intervals lie wholly inside the route receipt's
monotonic hold interval are admitted.
"""

from __future__ import annotations

import json
import math
import shutil
import signal
import struct
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np

from .d405_chessboard_surface_plane import (
    CONTRACT_PATH as CHESSBOARD_PLANE_CONTRACT_PATH,
    admit_chessboard_surface_planes,
    load_contract as load_chessboard_plane_contract,
)
from .d405_metric_surface_plane import fit_metric_surface_plane
from .d405_stationary_rgbd_capture import (
    _open_database_read_only,
    _parse_enumeration_device,
    _semicolon_fields,
    _single_topic_string,
    _topic_inventory,
)
from .learning_factory_artifacts import atomic_write_json, sha256_file
from .live_anchored_camera_reposition import execute_live_anchored_camera_reposition
from .paths import REPO_ROOT

CONTRACT_PATH = REPO_ROOT / "configs/evaluations/d405_pose_plane_capture_v1.json"
CONTRACT_SCHEMA = "sim2claw.d405_pose_plane_capture_contract.v1"
RECEIPT_SCHEMA = "sim2claw.d405_pose_plane_capture_receipt.v1"
NATIVE_RECORD_DURATION_SECONDS = 75


class D405PosePlaneCaptureError(RuntimeError):
    """The capture, clock binding, route, or evidence failed closed."""


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != CONTRACT_SCHEMA:
        raise D405PosePlaneCaptureError("unexpected pose-plane capture contract")
    if not value.get("authority") or any(value["authority"].values()):
        raise D405PosePlaneCaptureError("pose-plane capture authority widened")
    return value


class _NativeRsRecord:
    """Start rs-record and bound readiness by native depth-topic appearance."""

    def __init__(self, database_path: Path) -> None:
        executable = shutil.which("rs-record")
        if executable is None:
            raise D405PosePlaneCaptureError("rs-record is unavailable")
        self.command = [
            executable,
            "-t",
            str(NATIVE_RECORD_DURATION_SECONDS),
            "-f",
            str(database_path),
        ]
        self.database_path = database_path
        self.process: subprocess.Popen[str] | None = None

    def start(self) -> dict[str, Any]:
        process_start_lower = time.monotonic()
        self.process = subprocess.Popen(
            self.command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        process_start_upper = time.monotonic()
        deadline, ready = time.monotonic() + 5.0, False
        last_empty_poll_completed = process_start_lower
        clock_origin_bounds: list[float] | None = None
        while time.monotonic() < deadline and self.process.poll() is None:
            poll_started = time.monotonic()
            try:
                with _open_database_read_only(self.database_path) as connection:
                    row = connection.execute(
                        "SELECT MAX(messages.timestamp) FROM messages "
                        "JOIN topics ON messages.topic_id=topics.id "
                        "WHERE topics.name=?",
                        ("/device_0/sensor_0/Depth_0/image/data",),
                    ).fetchone()
                    bag_timestamp_ns = row[0] if row is not None else None
                    ready = bag_timestamp_ns is not None
            except Exception:
                ready = False
                bag_timestamp_ns = None
            poll_completed = time.monotonic()
            if ready:
                bag_timestamp_seconds = float(bag_timestamp_ns) / 1e9
                clock_origin_bounds = [
                    last_empty_poll_completed - bag_timestamp_seconds,
                    poll_completed - bag_timestamp_seconds,
                ]
                break
            last_empty_poll_completed = max(last_empty_poll_completed, poll_completed)
            time.sleep(0.02)
        if not ready:
            if self.process.poll() is None:
                self.process.send_signal(signal.SIGINT)
                try:
                    self.process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.communicate()
            raise D405PosePlaneCaptureError(
                "rs-record did not expose the depth topic within 5 seconds"
            )
        return {
            "command": self.command,
            "readiness": "first_depth_message_observed",
            "process_start_monotonic_bounds": [
                process_start_lower,
                process_start_upper,
            ],
            "clock_origin_monotonic_bounds": clock_origin_bounds,
            "clock_origin_method": (
                "last_empty_database_poll_to_first_observed_depth_message"
            ),
        }

    def finish(self) -> dict[str, Any]:
        if self.process is None:
            raise D405PosePlaneCaptureError("rs-record was not started")
        stop_signal_lower = time.monotonic()
        self.process.send_signal(signal.SIGINT)
        stop_signal_upper = time.monotonic()
        try:
            stdout, stderr = self.process.communicate(timeout=15)
        except subprocess.TimeoutExpired as error:
            self.process.kill()
            self.process.communicate()
            raise D405PosePlaneCaptureError("rs-record did not stop after SIGINT") from error
        accepted_returncodes = {0, -signal.SIGINT, 128 + signal.SIGINT}
        if self.process.returncode not in accepted_returncodes:
            raise D405PosePlaneCaptureError(
                f"rs-record exited {self.process.returncode}: {stderr.strip()}"
            )
        return {
            "returncode": self.process.returncode,
            "stdout_tail": stdout[-512:],
            "stop_signal_monotonic_bounds": [
                stop_signal_lower,
                stop_signal_upper,
            ],
        }


def _native_camera_identity() -> dict[str, str]:
    executable = shutil.which("rs-enumerate-devices")
    if executable is None:
        raise D405PosePlaneCaptureError("rs-enumerate-devices is unavailable")
    result = subprocess.run(
        [executable], check=True, capture_output=True, text=True, timeout=15
    )
    identity = _parse_enumeration_device(result.stdout)
    if not identity.get("sdk_serial_number") or not identity.get("asic_serial_number"):
        raise D405PosePlaneCaptureError("D405 identity enumeration is incomplete")
    return identity


def _decode_depth_image(blob: bytes) -> tuple[int, np.ndarray]:
    if blob[:4] != b"\x00\x01\x00\x00":
        raise D405PosePlaneCaptureError("unsupported ROS2 CDR encapsulation")
    offset = 4

    def unpack(code: str, size: int) -> Any:
        nonlocal offset
        offset = (offset + size - 1) // size * size
        value = struct.unpack_from("<" + code, blob, offset)[0]
        offset += size
        return value

    def string() -> str:
        nonlocal offset
        length = unpack("I", 4)
        value = blob[offset : offset + length]
        offset += length
        return value[:-1].decode()

    sec, nanosec = unpack("i", 4), unpack("I", 4)
    string()
    height, width, encoding = unpack("I", 4), unpack("I", 4), string()
    big_endian, step, length = unpack("B", 1), unpack("I", 4), unpack("I", 4)
    raw = blob[offset : offset + length]
    if (height, width, encoding, big_endian, step, len(raw)) != (
        480, 848, "mono16", 0, 1696, 814080
    ):
        raise D405PosePlaneCaptureError("unexpected D405 depth image layout")
    return sec * 1_000_000_000 + nanosec, np.frombuffer(raw, "<u2").reshape(480, 848)


def _route_hold(
    receipt: dict[str, Any], contract: dict[str, Any]
) -> tuple[float, float, dict[str, Any]]:
    if (
        receipt.get("status") != "completed_live_anchored_camera_reposition"
        or receipt.get("shutdown_torque_off_confirmed") is not True
        or receipt.get("physical_follower_torque_enabled") is not False
    ):
        raise D405PosePlaneCaptureError("route or final torque-off proof failed")
    interval = receipt.get("terminal_hold_monotonic_interval", {})
    start, end = interval.get("start"), interval.get("end")
    if not all(
        isinstance(value, (float, int)) and math.isfinite(value)
        for value in (start, end)
    ):
        raise D405PosePlaneCaptureError("terminal hold bounds are unavailable")
    if end - start < float(contract["minimum_terminal_hold_seconds"]):
        raise D405PosePlaneCaptureError("terminal hold interval is too short")
    telemetry = Path(receipt["telemetry"]["path"])
    decoded = [
        json.loads(line)
        for line in telemetry.read_text(encoding="utf-8").splitlines()
    ]
    poses = np.asarray(
        [
            row["follower_actual_position_degrees"]
            for row in decoded
            if row.get("setup_phase") == "target_hold"
        ]
    )
    if poses.ndim != 2 or poses.shape[1] != 6 or not np.all(np.isfinite(poses)):
        raise D405PosePlaneCaptureError("terminal hold has no finite joint poses")
    joint_range = np.ptp(poses, axis=0)
    if max(joint_range) > float(contract["maximum_terminal_joint_range_degrees"]):
        raise D405PosePlaneCaptureError("terminal hold joint pose was not stationary")
    pose = {
        "sample_count": len(poses),
        "mean_degrees": np.mean(poses, axis=0).tolist(),
        "standard_deviation_degrees": np.std(poses, axis=0).tolist(),
        "range_degrees": joint_range.tolist(),
        "exact_terminal_command_sha256": interval.get(
            "exact_terminal_command_sha256"
        ),
        "telemetry_sha256": sha256_file(telemetry),
    }
    return float(start), float(end), pose


def _ingest(
    database: Path,
    window_s: tuple[float, float],
    accepted_intrinsics: dict[str, Any],
    accepted_units: float,
    plane_contract: dict[str, Any],
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    with _open_database_read_only(database) as connection:
        _, ids = _topic_inventory(connection)
        depth_topic = "/device_0/sensor_0/Depth_0/image/data"
        required = (depth_topic, "/device_0/info")
        if not all(name in ids for name in required):
            raise D405PosePlaneCaptureError("recorded D405 topics are incomplete")
        ending = lambda suffix: next(
            (value for name, value in ids.items() if name.endswith(suffix)), None
        )
        camera_id, units_id = ending("Depth_0/camera_info"), ending("Depth_Units/value")
        if camera_id is None or units_id is None:
            raise D405PosePlaneCaptureError("metric calibration topics are incomplete")
        device = _semicolon_fields(
            _single_topic_string(connection, ids["/device_0/info"])
        )
        camera = _semicolon_fields(_single_topic_string(connection, camera_id))
        units = float(_single_topic_string(connection, units_id))
        rows = connection.execute(
            "SELECT timestamp,data FROM messages WHERE topic_id=? AND "
            "timestamp>=? AND timestamp<=? ORDER BY timestamp,id",
            (ids[depth_topic], int(window_s[0] * 1e9), int(window_s[1] * 1e9)),
        ).fetchall()
    observed = {
        "width": int(camera["width"]),
        "height": int(camera["height"]),
        "focal_length_px": [float(camera["fx"]), float(camera["fy"])],
        "principal_point_px": [float(camera["ppx"]), float(camera["ppy"])],
        "distortion_model": camera["model"],
        "distortion_coefficients": [
            float(value) for value in camera["coeffs"].split(",")
        ],
    }
    scalar_equal = all(
        observed[key] == accepted_intrinsics[key]
        for key in ("width", "height", "distortion_model")
    )
    numeric_equal = all(
        np.allclose(observed[key], accepted_intrinsics[key], rtol=0, atol=1e-6)
        for key in (
            "focal_length_px",
            "principal_point_px",
            "distortion_coefficients",
        )
    )
    if not scalar_equal or not numeric_equal or not math.isclose(
        units, accepted_units, rel_tol=0, abs_tol=1e-12
    ):
        raise D405PosePlaneCaptureError("recorded D405 calibration changed")
    observations = []
    for timestamp, blob in rows:
        header_timestamp, raw = _decode_depth_image(bytes(blob))
        if header_timestamp != timestamp:
            raise D405PosePlaneCaptureError("bag and depth timestamps differ")
        plane = fit_metric_surface_plane(
            raw.astype(np.float64) * units, observed, plane_contract
        )
        observations.append({"bag_timestamp_ns": timestamp, "plane": plane})
    return device, observations


def orchestrate_d405_pose_plane_capture(
    *,
    route_path: Path,
    candidate_manifest_path: Path,
    accepted_capture_receipt_path: Path,
    output_root: Path,
    operator_acknowledged: bool,
    route_executor: Callable[..., dict[str, Any]] = execute_live_anchored_camera_reposition,
    recorder_factory: Callable[[Path], Any] = _NativeRsRecord,
    identity_fn: Callable[[], dict[str, str]] = _native_camera_identity,
    clock_fn: Callable[[], float] = time.monotonic,
    contract_path: Path = CONTRACT_PATH,
    plane_contract_path: Path = CHESSBOARD_PLANE_CONTRACT_PATH,
) -> dict[str, Any]:
    """Record one setup route and admit only its stationary hold depth."""
    if not operator_acknowledged:
        raise D405PosePlaneCaptureError("physical capture requires acknowledgement")
    output_root, accepted_path = output_root.resolve(), accepted_capture_receipt_path.resolve()
    if output_root.exists():
        raise D405PosePlaneCaptureError(f"refusing to overwrite {output_root}")
    accepted = json.loads(accepted_path.read_text(encoding="utf-8"))
    if (
        accepted.get("schema_version")
        != "sim2claw.d405_stationary_rgbd_capture_receipt.v1"
        or accepted.get("verdict", {}).get("passed") is not True
    ):
        raise D405PosePlaneCaptureError("accepted D405 calibration lineage failed")
    contract = load_contract(contract_path)
    plane_contract = load_chessboard_plane_contract(plane_contract_path)
    intrinsics = accepted["calibration"]["intrinsics"]["depth"]
    units = float(accepted["streams"]["depth"]["depth_units_m_per_z16_unit"])
    expected_identity = accepted["device_identity"]["enumeration"]
    before_identity = identity_fn()
    if before_identity != expected_identity:
        raise D405PosePlaneCaptureError("live D405 identity differs from calibration")
    output_root.mkdir(parents=True)
    database, recorder = output_root / "pose-plane.db3", None
    recorder = recorder_factory(database)
    start_lower = clock_fn()
    start_report = recorder.start()
    start_upper = clock_fn()
    origin_bounds = start_report.get("clock_origin_monotonic_bounds")
    if (
        isinstance(origin_bounds, list)
        and len(origin_bounds) == 2
        and all(
            isinstance(value, (float, int)) and math.isfinite(value)
            for value in origin_bounds
        )
    ):
        start_lower, start_upper = map(float, origin_bounds)
    route_receipt, route_error = None, None
    try:
        route_receipt = route_executor(
            route_path=route_path,
            candidate_manifest_path=candidate_manifest_path,
            output_root=output_root / "route",
            operator_acknowledged=True,
        )
    except Exception as error:
        route_error = error
    end_lower = clock_fn()
    finish_report = recorder.finish()
    end_upper = clock_fn()
    stop_bounds = finish_report.get("stop_signal_monotonic_bounds")
    if (
        isinstance(stop_bounds, list)
        and len(stop_bounds) == 2
        and all(
            isinstance(value, (float, int)) and math.isfinite(value)
            for value in stop_bounds
        )
    ):
        end_lower, end_upper = map(float, stop_bounds)
    after_identity = identity_fn()
    if route_error is not None or route_receipt is None:
        raise D405PosePlaneCaptureError(f"route failed: {route_error}")
    stored_route_path = output_root / "route" / "execution_receipt.json"
    if not stored_route_path.is_file() or json.loads(
        stored_route_path.read_text(encoding="utf-8")
    ) != route_receipt:
        raise D405PosePlaneCaptureError("route receipt artifact is missing or changed")
    if before_identity != after_identity:
        raise D405PosePlaneCaptureError("D405 identity changed across capture")
    if (
        start_upper - start_lower
        > float(contract["maximum_record_start_bound_width_seconds"])
        or end_upper - end_lower
        > float(contract["maximum_record_end_bound_width_seconds"])
    ):
        raise D405PosePlaneCaptureError("recorder monotonic bounds are too wide")
    hold_start, hold_end, joint_pose = _route_hold(route_receipt, contract)
    window = (hold_start - start_lower, hold_end - start_upper)
    if window[1] <= window[0]:
        raise D405PosePlaneCaptureError("clock uncertainty consumes hold window")
    device, observations = _ingest(
        database, window, intrinsics, units, plane_contract
    )
    database_identity = {
        "sdk_serial_number": device.get("Serial Number"),
        "asic_serial_number": device.get("Asic Serial Number"),
        "firmware_update_id": device.get("Firmware Update Id"),
        "usb_product_id_hex": device.get("Product Id"),
        "physical_port": device.get("Physical Port"),
    }
    if any(before_identity.get(key) != value for key, value in database_identity.items()):
        raise D405PosePlaneCaptureError("database identity differs from live D405")
    if len(observations) < int(contract["minimum_hold_depth_frames"]):
        raise D405PosePlaneCaptureError("no sufficient stationary hold depth frames")
    admission = admit_chessboard_surface_planes(
        observations, contract_path=plane_contract_path
    )
    for item in admission["accepted_observations"]:
        item["joint_pose"] = joint_pose
    passed = admission["passed"]
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "proof_class": contract["proof_class"],
        "authority": contract["authority"],
        "recording": {
            "database_path": str(database),
            "database_sha256": sha256_file(database),
            "start_monotonic_bounds": [start_lower, start_upper],
            "end_monotonic_bounds": [end_lower, end_upper],
            "start_report": start_report,
            "finish_report": finish_report,
        },
        "calibration_lineage": {
            "accepted_capture_receipt_path": str(accepted_path),
            "accepted_capture_receipt_sha256": sha256_file(accepted_path),
            "depth_intrinsics": intrinsics,
            "depth_units_m_per_z16_unit": units,
        },
        "identity": {
            "before": before_identity,
            "after": after_identity,
            "database": database_identity,
        },
        "terminal_hold": {
            "monotonic_interval": [hold_start, hold_end],
            "joint_pose": joint_pose,
            "route_receipt_path": str(stored_route_path),
            "route_receipt_sha256": sha256_file(stored_route_path),
        },
        "conservative_hold_bag_window_seconds": list(window),
        "plane_admission": {
            key: value
            for key, value in admission.items()
            if key not in ("accepted_observations", "rejected_observations")
        },
        "observations": admission["accepted_observations"],
        "rejected_observations": admission["rejected_observations"],
        "verdict": {
            "passed": passed,
            "classification": (
                "bounded_joint_pose_chessboard_plane_observations_captured"
                if passed
                else "insufficient_stable_chessboard_plane_frames_rejected"
            ),
            "camera_to_robot_extrinsic_fitted": False,
            "policy_or_task_authority": False,
        },
    }
    atomic_write_json(output_root / "receipt.json", receipt)
    return receipt
