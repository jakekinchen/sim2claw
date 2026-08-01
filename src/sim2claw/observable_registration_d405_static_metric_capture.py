"""Validate and, only with an external camera lease, execute OR45 once."""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
from pathlib import Path
from typing import Any

from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
)
from .observable_registration_belief_recalculation import REPO_ROOT, _bound_path


SCHEMA = "sim2claw.observable_registration_d405_static_metric_capture_contract.v1"
RECEIPT_SCHEMA = "sim2claw.observable_registration_d405_static_metric_capture_receipt.v1"
CONTRACT_PATH = (
    REPO_ROOT
    / "configs/evaluations/observable_registration_d405_static_metric_capture_v1.json"
)
OUTPUT_DIRECTORY = (
    REPO_ROOT / "outputs/observable_registration_d405_static_metric_capture_v1"
)
OR44_BINARY = (
    REPO_ROOT
    / "outputs/observable_registration_d405_metric_sidecar_v1"
    / "RealSenseD405MetricRecorder"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _finite_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def load_d405_static_metric_capture_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="OR45 D405 static metric capture")
    _require(contract.get("schema_version") == SCHEMA, "unsupported contract")
    for source_id, binding in contract["sources"].items():
        _bound_path(binding, root=root, label=source_id)
    packet = contract["packet"]
    _require(
        packet
        == {
            "device_family": "Intel RealSense D405",
            "frame_count": 30,
            "width": 424,
            "height": 240,
            "fps": 30,
            "stream": "depth",
            "format": "Z16",
            "robot_motion": False,
            "object_interaction": False,
            "serial_access": False,
            "torque_enable": False,
        },
        "OR45 packet identity drifted",
    )
    boundary = contract["execution_boundary"]
    _require(boundary["packet_count"] == 1, "OR45 packet count widened")
    _require(
        boundary["adaptive_retry_allowed"] is False,
        "OR45 adaptive retry boundary widened",
    )
    _require(not any(contract["authority"].values()), "OR45 authority widened")
    return contract


def _load_metadata(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise FactoryArtifactError(
                f"invalid metadata JSON on line {line_number}"
            ) from error
        _require(isinstance(row, dict), "metadata row is not an object")
        rows.append(row)
    return rows


def _strictly_increasing(values: list[float | int]) -> bool:
    return all(left < right for left, right in zip(values, values[1:]))


def validate_d405_static_metric_capture(
    contract: dict[str, Any],
    *,
    manifest_path: Path,
    metadata_path: Path,
    raw_path: Path,
) -> dict[str, Any]:
    """Validate captured bytes without altering or interpreting depth geometry."""

    _require(manifest_path.is_file(), "capture manifest is missing")
    _require(metadata_path.is_file(), "capture metadata is missing")
    _require(raw_path.is_file(), "capture raw depth is missing")
    manifest = load_json_object(manifest_path, label="OR45 capture manifest")
    packet = contract["packet"]
    acceptance = contract["acceptance"]
    _require(
        manifest.get("schema_version")
        == "sim2claw.d405_metric_depth_capture_manifest.v1",
        "capture manifest schema drifted",
    )
    _require(
        acceptance["device_name_must_contain"]
        in str(manifest.get("device_name", "")),
        "capture device is not the frozen D405 family",
    )
    _require(bool(manifest.get("device_serial")), "capture device serial is missing")
    for field in ("width", "height", "fps", "frame_count"):
        _require(
            manifest.get(field) == packet[field],
            f"capture manifest {field} drifted",
        )
    _require(
        _finite_number(manifest.get("depth_scale_meters"))
        and float(manifest["depth_scale_meters"]) > 0,
        "capture depth scale is not positive and finite",
    )
    intrinsics = manifest.get("intrinsics")
    _require(isinstance(intrinsics, dict), "capture intrinsics are missing")
    for field in ("fx", "fy", "ppx", "ppy"):
        _require(
            _finite_number(intrinsics.get(field)),
            f"capture intrinsic {field} is not finite",
        )
    _require(
        float(intrinsics["fx"]) > 0 and float(intrinsics["fy"]) > 0,
        "capture focal lengths are not positive",
    )
    coefficients = intrinsics.get("coeffs")
    _require(
        isinstance(coefficients, list)
        and len(coefficients) == 5
        and all(_finite_number(value) for value in coefficients),
        "capture distortion coefficients are invalid",
    )

    raw_frame_bytes = manifest.get("raw_frame_bytes")
    _require(
        isinstance(raw_frame_bytes, int) and raw_frame_bytes > 0,
        "capture raw frame byte count is invalid",
    )
    expected_raw_bytes = raw_frame_bytes * packet["frame_count"]
    actual_raw_bytes = raw_path.stat().st_size
    _require(
        actual_raw_bytes == expected_raw_bytes,
        "raw byte count does not match capture manifest",
    )

    rows = _load_metadata(metadata_path)
    _require(
        len(rows) == acceptance["complete_frame_record_count"],
        "capture metadata frame count is incomplete",
    )
    required_fields = {
        "schema_version",
        "frame_index",
        "frame_number",
        "sensor_timestamp_ms",
        "sensor_timestamp_domain",
        "host_arrival_steady_ns",
        "raw_offset_bytes",
        "width",
        "height",
        "stride_bytes",
        "bits_per_pixel",
        *acceptance["optional_metadata_support_must_be_reported"],
    }
    for index, row in enumerate(rows):
        _require(
            required_fields <= row.keys(),
            f"capture metadata row {index} is incomplete",
        )
        _require(
            row["schema_version"] == "sim2claw.d405_depth_frame.v1",
            "capture frame schema drifted",
        )
        _require(row["frame_index"] == index, "capture frame index drifted")
        _require(
            row["width"] == packet["width"]
            and row["height"] == packet["height"]
            and row["bits_per_pixel"] == 16,
            "capture frame dimensions or format drifted",
        )
        _require(
            row["stride_bytes"] * packet["height"] == raw_frame_bytes,
            "capture frame stride disagrees with manifest",
        )
        _require(
            row["raw_offset_bytes"] == index * raw_frame_bytes,
            "capture raw offset is not contiguous",
        )
        _require(
            _finite_number(row["sensor_timestamp_ms"])
            and _finite_number(row["host_arrival_steady_ns"]),
            "capture timestamps are not finite",
        )
        _require(
            isinstance(row["sensor_timestamp_domain"], str)
            and bool(row["sensor_timestamp_domain"]),
            "capture timestamp domain is missing",
        )

    sensor_timestamps = [float(row["sensor_timestamp_ms"]) for row in rows]
    host_timestamps = [int(row["host_arrival_steady_ns"]) for row in rows]
    frame_numbers = [int(row["frame_number"]) for row in rows]
    _require(
        _strictly_increasing(sensor_timestamps),
        "sensor timestamps are not strictly monotonic",
    )
    _require(
        _strictly_increasing(host_timestamps),
        "host arrival timestamps are not strictly monotonic",
    )
    _require(
        len(set(frame_numbers)) == len(frame_numbers),
        "frame numbers are not unique",
    )

    optional_support: dict[str, str] = {}
    for field in acceptance["optional_metadata_support_must_be_reported"]:
        present = sum(row[field] is not None for row in rows)
        optional_support[field] = (
            "missing"
            if present == 0
            else "complete"
            if present == len(rows)
            else "partial"
        )

    return {
        "status": "PASS_D405_STATIC_METRIC_CAPTURE",
        "device_name": manifest["device_name"],
        "device_serial": manifest["device_serial"],
        "frame_count": len(rows),
        "raw_byte_count": actual_raw_bytes,
        "depth_scale_meters": manifest["depth_scale_meters"],
        "intrinsics": intrinsics,
        "sensor_timestamp_domain": rows[0]["sensor_timestamp_domain"],
        "sensor_timestamps_strictly_monotonic": True,
        "host_timestamps_strictly_monotonic": True,
        "frame_numbers_unique": True,
        "optional_metadata_support": optional_support,
        "files": {
            "manifest_sha256": _sha256(manifest_path),
            "metadata_sha256": _sha256(metadata_path),
            "raw_sha256": _sha256(raw_path),
        },
    }


def _verified_or44_binary(root: Path) -> tuple[Path, str]:
    closeout = load_json_object(
        root
        / "configs/decisions/observable_registration_d405_metric_sidecar_v1_closeout.json",
        label="OR44 closeout",
    )
    binary_path = (
        root
        / "outputs/observable_registration_d405_metric_sidecar_v1"
        / "RealSenseD405MetricRecorder"
    )
    _require(binary_path.is_file(), "verified OR44 recorder binary is missing")
    expected = closeout["result"]["binary_sha256"]
    _require(_sha256(binary_path) == expected, "OR44 recorder binary drifted")
    return binary_path, expected


def run_d405_static_metric_capture_once(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
    camera_authority: bool = False,
    device_serial: str | None = None,
) -> dict[str, Any]:
    """Execute the frozen packet once after an external control plane admits it."""

    _require(camera_authority, "OR45 camera authority is false")
    _require(bool(device_serial), "OR45 exact D405 serial is required")
    _require(not output_directory.exists(), "OR45 output already exists")
    contract = load_d405_static_metric_capture_contract(contract_path, root=root)
    binary_path, binary_sha256 = _verified_or44_binary(root)
    packet = contract["packet"]
    output_directory.mkdir(parents=True, exist_ok=False)
    prefix = output_directory / "capture"
    command = [
        str(binary_path),
        "--output-prefix",
        str(prefix),
        "--serial",
        str(device_serial),
        "--frames",
        str(packet["frame_count"]),
        "--width",
        str(packet["width"]),
        "--height",
        str(packet["height"]),
        "--fps",
        str(packet["fps"]),
    ]
    result = subprocess.run(
        command, check=False, capture_output=True, text=True, timeout=20
    )
    command_record = {
        "binary_sha256": binary_sha256,
        "arguments": command[1:],
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
    if result.returncode != 0:
        receipt = {
            "schema_version": RECEIPT_SCHEMA,
            "experiment_id": contract["experiment_id"],
            "proof_class": contract["proof_class"],
            "status": "TERMINAL_D405_STATIC_METRIC_CAPTURE_FAILED_NO_RETRY",
            "command": command_record,
            "camera_open_authorized": True,
            "serial_opened": False,
            "torque_enabled": False,
            "robot_motion_performed": False,
            "physical_task_attempts": 0,
            "simulator_replays": 0,
            "transfer_claim": False,
        }
        receipt["artifact_sha256"] = canonical_digest(receipt)
        atomic_write_json(output_directory / "receipt.json", receipt)
        return receipt

    validation = validate_d405_static_metric_capture(
        contract,
        manifest_path=prefix.with_suffix(".manifest.json"),
        metadata_path=prefix.with_suffix(".metadata.jsonl"),
        raw_path=prefix.with_suffix(".z16"),
    )
    _require(
        validation["device_serial"] == device_serial,
        "captured D405 serial does not match lease",
    )
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "proof_class": "zero_motion_d405_static_metric_depth_capture",
        "status": "PASS_D405_STATIC_METRIC_CAPTURE",
        "command": command_record,
        "validation": validation,
        "camera_open_authorized": True,
        "camera_opened": True,
        "metric_depth_captured": True,
        "load_side_gripper_mapping_acquired": False,
        "physical_calibration_executed": False,
        "global_mapping_approved": False,
        "serial_opened": False,
        "torque_enabled": False,
        "robot_motion_performed": False,
        "physical_task_attempts": 0,
        "simulator_replays": 0,
        "transfer_claim": False,
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(output_directory / "receipt.json", receipt)
    return receipt


def main() -> int:
    raise SystemExit(
        "OR45 requires a separately validated one-shot camera capability lease"
    )


if __name__ == "__main__":
    main()
