from __future__ import annotations

import json
import sqlite3
import struct
from pathlib import Path

import numpy as np
import pytest

import sim2claw.d405_pose_plane_capture as pose_plane_capture
from sim2claw.d405_pose_plane_capture import (
    D405PosePlaneCaptureError,
    orchestrate_d405_pose_plane_capture,
)


IDENTITY = {
    "name": "RealSense D405",
    "sdk_serial_number": "130322273474",
    "firmware_version": "5.17.0.10",
    "physical_port": "0-2-1",
    "usb_product_id_hex": "0B5B",
    "usb_type_descriptor": "3.2",
    "asic_serial_number": "133323070214",
    "firmware_update_id": "133323070214",
}
INTRINSICS = {
    "width": 848,
    "height": 480,
    "focal_length_px": [422.038055419922, 422.038055419922],
    "principal_point_px": [422.791778564453, 236.049667358398],
    "distortion_model": "Brown Conrady",
    "distortion_coefficients": [0.0] * 5,
}


def _cdr_string(value: str) -> bytes:
    encoded = value.encode() + b"\0"
    return b"\x00\x01\x00\x00" + struct.pack("<I", len(encoded)) + encoded


def _cdr_depth(timestamp_ns: int, raw: np.ndarray) -> bytes:
    frame_id = b"Depth\0"
    encoding = b"mono16\0"
    value = bytearray(b"\x00\x01\x00\x00")
    value += struct.pack("<iI", timestamp_ns // 1_000_000_000, timestamp_ns % 1_000_000_000)
    value += struct.pack("<I", len(frame_id)) + frame_id
    while len(value) % 4:
        value += b"\0"
    value += struct.pack("<II", 480, 848)
    value += struct.pack("<I", len(encoding)) + encoding + b"\0"
    while len(value) % 4:
        value += b"\0"
    payload = raw.astype("<u2").tobytes()
    value += struct.pack("<II", 1696, len(payload)) + payload
    return bytes(value)


def _write_database(path: Path, timestamps_s: list[float]) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE topics(
          id INTEGER PRIMARY KEY,name TEXT,type TEXT,serialization_format TEXT,
          offered_qos_profiles TEXT);
        CREATE TABLE messages(
          id INTEGER PRIMARY KEY,topic_id INTEGER,timestamp INTEGER,data BLOB);
        """
    )
    topics = [
        (1, "/device_0/info"),
        (2, "/device_0/sensor_0/Depth_0/camera_info"),
        (3, "/device_0/sensor_0/option/Depth_Units/value"),
        (4, "/device_0/sensor_0/Depth_0/image/data"),
    ]
    connection.executemany(
        "INSERT INTO topics VALUES(?,?,'std_msgs/msg/String','cdr','')", topics
    )
    device = (
        "Name=RealSense D405;Serial Number=130322273474;"
        "Asic Serial Number=133323070214;Firmware Update Id=133323070214;"
        "Product Id=0B5B;Physical Port=0-2-1"
    )
    camera = (
        "width=848;height=480;fx=422.038055419922;ppx=422.791778564453;"
        "fy=422.038055419922;ppy=236.049667358398;model=Brown Conrady;"
        "coeffs=0,0,0,0,0"
    )
    connection.executemany(
        "INSERT INTO messages(topic_id,timestamp,data) VALUES(?,?,?)",
        [(1, 0, _cdr_string(device)), (2, 0, _cdr_string(camera)), (3, 0, _cdr_string("0.000100"))],
    )
    raw = np.full((480, 848), 1000, dtype=np.uint16)
    for timestamp_s in timestamps_s:
        timestamp_ns = int(timestamp_s * 1e9)
        connection.execute(
            "INSERT INTO messages(topic_id,timestamp,data) VALUES(4,?,?)",
            (timestamp_ns, _cdr_depth(timestamp_ns, raw)),
        )
    connection.commit()
    connection.close()


def _accepted(path: Path) -> Path:
    receipt = path / "accepted.json"
    receipt.write_text(
        json.dumps(
            {
                "schema_version": "sim2claw.d405_stationary_rgbd_capture_receipt.v1",
                "verdict": {"passed": True},
                "calibration": {"intrinsics": {"depth": INTRINSICS}},
                "streams": {"depth": {"depth_units_m_per_z16_unit": 0.0001}},
                "device_identity": {"enumeration": IDENTITY},
            }
        )
    )
    return receipt


def _fixture(
    tmp_path: Path,
    *,
    timestamps_s: list[float] = [0.8, 1.3, 1.7, 2.0, 2.6],
    torque_off: bool = True,
    identities: list[dict] | None = None,
    clocks: list[float] = [100.0, 100.1, 103.0, 103.1],
) -> dict:
    telemetry = tmp_path / "telemetry.jsonl"
    telemetry.write_text(
        "\n".join(
            json.dumps(
                {
                    "setup_phase": "target_hold",
                    "follower_actual_position_degrees": [
                        10.0,
                        -56.5,
                        89.8 + index * 0.02,
                        0.2,
                        -75.1,
                        3.1,
                    ],
                }
            )
            for index in range(3)
        )
    )

    class Recorder:
        def __init__(self, database_path: Path) -> None:
            self.database_path = database_path

        def start(self) -> dict:
            return {"status": "fixture_started"}

        def finish(self) -> dict:
            _write_database(self.database_path, timestamps_s)
            return {"returncode": 0}

    def route_executor(**route_kwargs: object) -> dict:
        receipt = {
            "status": "completed_live_anchored_camera_reposition",
            "shutdown_torque_off_confirmed": torque_off,
            "physical_follower_torque_enabled": False if torque_off else None,
            "terminal_hold_monotonic_interval": {
                "start": 101.2,
                "end": 102.5,
                "exact_terminal_command_sha256": "a" * 64,
            },
            "telemetry": {"path": str(telemetry)},
        }
        route_output = Path(route_kwargs["output_root"])
        route_output.mkdir(parents=True)
        (route_output / "execution_receipt.json").write_text(json.dumps(receipt))
        return receipt

    identity_values = iter(identities or [IDENTITY.copy(), IDENTITY.copy()])
    clock_values = iter(clocks)
    return {
        "route_path": tmp_path / "route.json",
        "candidate_manifest_path": tmp_path / "manifest.json",
        "accepted_capture_receipt_path": _accepted(tmp_path),
        "output_root": tmp_path / "output",
        "operator_acknowledged": True,
        "route_executor": route_executor,
        "recorder_factory": Recorder,
        "identity_fn": lambda: next(identity_values),
        "clock_fn": lambda: next(clock_values),
    }


def test_capture_admits_only_frames_wholly_inside_terminal_hold(tmp_path: Path) -> None:
    receipt = orchestrate_d405_pose_plane_capture(**_fixture(tmp_path))

    assert receipt["verdict"]["passed"] is True
    assert receipt["conservative_hold_bag_window_seconds"] == pytest.approx(
        [1.2, 2.4]
    )
    assert [item["bag_timestamp_ns"] for item in receipt["observations"]] == [
        1_300_000_000,
        1_700_000_000,
        2_000_000_000,
    ]
    assert receipt["plane_admission"]["accepted_frame_count"] == 3
    assert receipt["rejected_observations"] == []
    assert receipt["terminal_hold"]["joint_pose"]["sample_count"] == 3
    assert all(item["plane"]["residuals_m"]["rms"] < 1e-9 for item in receipt["observations"])
    assert all(value is False for value in receipt["authority"].values())


@pytest.mark.parametrize("failure", ["identity", "torque_off", "clock", "frames"])
def test_capture_prerequisites_fail_closed(tmp_path: Path, failure: str) -> None:
    kwargs = {}
    match = ""
    if failure == "identity":
        changed = IDENTITY.copy()
        changed["sdk_serial_number"] = "different"
        kwargs["identities"] = [IDENTITY.copy(), changed]
        match = "identity changed"
    elif failure == "torque_off":
        kwargs["torque_off"] = False
        match = "torque-off proof failed"
    elif failure == "clock":
        kwargs["clocks"] = [100.0, 100.8, 103.0, 103.1]
        match = "bounds are too wide"
    else:
        kwargs["timestamps_s"] = [0.1, 2.9]
        match = "no sufficient stationary hold"

    with pytest.raises(D405PosePlaneCaptureError, match=match):
        orchestrate_d405_pose_plane_capture(**_fixture(tmp_path, **kwargs))


def test_native_recorder_readiness_failure_releases_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Process:
        returncode = None
        signaled = False

        def poll(self) -> None:
            return None

        def send_signal(self, _signal: int) -> None:
            self.signaled = True

        def communicate(self, timeout: int | None = None) -> tuple[str, str]:
            self.returncode = -2
            return "", ""

    process = Process()
    monkeypatch.setattr(pose_plane_capture.subprocess, "Popen", lambda *_a, **_k: process)
    clock = iter([0.0, 0.0, 0.0, 6.0, 7.0, 7.0])
    monkeypatch.setattr(pose_plane_capture.time, "monotonic", lambda: next(clock))
    recorder = pose_plane_capture._NativeRsRecord.__new__(
        pose_plane_capture._NativeRsRecord
    )
    recorder.command = ["rs-record", "-f", str(tmp_path / "capture.db3")]
    recorder.database_path = tmp_path / "capture.db3"
    recorder.process = None

    with pytest.raises(D405PosePlaneCaptureError, match="did not expose"):
        recorder.start()

    assert process.signaled is True
    process.returncode = None
    recorder.process = process
    assert recorder.finish()["returncode"] == -2


def test_native_recorder_uses_explicit_bounded_duration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        pose_plane_capture.shutil, "which", lambda name: f"/fixture/{name}"
    )

    recorder = pose_plane_capture._NativeRsRecord(tmp_path / "capture.db3")

    assert recorder.command == [
        "/fixture/rs-record",
        "-t",
        "30",
        "-f",
        str(tmp_path / "capture.db3"),
    ]
