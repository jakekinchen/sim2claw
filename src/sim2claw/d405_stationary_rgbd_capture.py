"""Read-only evaluator for an existing stationary D405 RGBD capture.

The evaluator opens no camera or robot. It consumes a rosbag2 SQLite database,
librealsense enumeration/readiness artifacts, and already-extracted frames. Its
only positive proof class is a physical stationary RGBD capture; it grants no
board-registration, camera-to-robot, motion, policy, or task authority.
"""

from __future__ import annotations

import json
import math
import re
import sqlite3
import struct
from pathlib import Path
from statistics import mean, median
from typing import Any
from urllib.parse import quote

import numpy as np

from .learning_factory_artifacts import atomic_write_json, sha256_file
from .paths import REPO_ROOT


CONTRACT_PATH = (
    REPO_ROOT / "configs" / "evaluations" / "d405_stationary_rgbd_capture_v1.json"
)
CONTRACT_SCHEMA = "sim2claw.d405_stationary_rgbd_capture_contract.v1"
RECEIPT_SCHEMA = "sim2claw.d405_stationary_rgbd_capture_receipt.v1"


class D405CaptureEvaluationError(RuntimeError):
    """The offline capture evidence is missing, malformed, or inconsistent."""


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise D405CaptureEvaluationError(f"cannot read contract {path}: {error}") from error
    if value.get("schema_version") != CONTRACT_SCHEMA:
        raise D405CaptureEvaluationError("unexpected D405 capture contract schema")
    authority = value.get("authority")
    if not isinstance(authority, dict) or not authority or any(authority.values()):
        raise D405CaptureEvaluationError("D405 capture authority widened")
    return value


def _decode_cdr_string(blob: bytes) -> str:
    if len(blob) < 9:
        raise D405CaptureEvaluationError("CDR string payload is truncated")
    little_endian = blob[1] == 1
    byte_order = "<" if little_endian else ">"
    length = struct.unpack(f"{byte_order}I", blob[4:8])[0]
    if length < 1 or 8 + length > len(blob):
        raise D405CaptureEvaluationError("CDR string length is invalid")
    payload = blob[8 : 8 + length]
    if payload[-1] != 0:
        raise D405CaptureEvaluationError("CDR string is not null terminated")
    return payload[:-1].decode("utf-8")


def _semicolon_fields(value: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for part in value.split(";"):
        if "=" in part:
            key, item = part.split("=", 1)
            fields[key.strip()] = item.strip()
    return fields


def _open_database_read_only(path: Path) -> sqlite3.Connection:
    uri = f"file:{quote(str(path.resolve()))}?mode=ro&immutable=1"
    return sqlite3.connect(uri, uri=True)


def _topic_inventory(
    connection: sqlite3.Connection,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    rows = connection.execute(
        """
        SELECT topics.id, topics.name, topics.type, topics.serialization_format,
               COUNT(messages.id), MIN(messages.timestamp), MAX(messages.timestamp)
        FROM topics LEFT JOIN messages ON messages.topic_id = topics.id
        GROUP BY topics.id ORDER BY topics.id
        """
    ).fetchall()
    inventory: list[dict[str, Any]] = []
    ids: dict[str, int] = {}
    for topic_id, name, type_name, serialization, count, first, last in rows:
        ids[str(name)] = int(topic_id)
        duration_ns = 0 if first is None or last is None else int(last) - int(first)
        inventory.append(
            {
                "id": int(topic_id),
                "name": str(name),
                "type": str(type_name),
                "serialization_format": str(serialization),
                "message_count": int(count),
                "first_timestamp_ns": None if first is None else int(first),
                "last_timestamp_ns": None if last is None else int(last),
                "duration_s": duration_ns / 1_000_000_000.0,
            }
        )
    return inventory, ids


def _topic_timestamps(
    connection: sqlite3.Connection, topic_id: int
) -> list[int]:
    return [
        int(row[0])
        for row in connection.execute(
            "SELECT timestamp FROM messages WHERE topic_id=? ORDER BY timestamp, id",
            (topic_id,),
        )
    ]


def _single_topic_string(
    connection: sqlite3.Connection, topic_id: int
) -> str:
    rows = connection.execute(
        "SELECT data FROM messages WHERE topic_id=? ORDER BY timestamp, id", (topic_id,)
    ).fetchall()
    if len(rows) != 1:
        raise D405CaptureEvaluationError(
            f"expected one string message on topic id {topic_id}, found {len(rows)}"
        )
    return _decode_cdr_string(bytes(rows[0][0]))


def _find_topic_id(ids: dict[str, int], suffix: str) -> int:
    matches = [topic_id for name, topic_id in ids.items() if name.endswith(suffix)]
    if len(matches) != 1:
        raise D405CaptureEvaluationError(
            f"expected exactly one topic ending {suffix!r}, found {len(matches)}"
        )
    return matches[0]


def _pair_statistics(depth: list[int], color: list[int]) -> dict[str, Any]:
    if not depth or len(depth) != len(color):
        raise D405CaptureEvaluationError(
            f"RGB/depth frame counts differ: depth={len(depth)} color={len(color)}"
        )
    signed_ms = [(c - d) / 1_000_000.0 for d, c in zip(depth, color)]
    absolute_ms = [abs(value) for value in signed_ms]
    return {
        "pairing_method": "same_order_by_rosbag_topic_timestamp",
        "pair_count": len(signed_ms),
        "signed_color_minus_depth_ms": {
            "minimum": min(signed_ms),
            "maximum": max(signed_ms),
            "mean": mean(signed_ms),
            "median": median(signed_ms),
        },
        "absolute_delta_ms": {
            "minimum": min(absolute_ms),
            "maximum": max(absolute_ms),
            "mean": mean(absolute_ms),
            "median": median(absolute_ms),
            "p95": float(np.percentile(absolute_ms, 95)),
        },
    }


def _parse_enumeration_device(text: str) -> dict[str, str]:
    labels = {
        "Name": "name",
        "Serial Number": "sdk_serial_number",
        "Firmware Version": "firmware_version",
        "Physical Port": "physical_port",
        "Product Id": "usb_product_id_hex",
        "Usb Type Descriptor": "usb_type_descriptor",
        "Asic Serial Number": "asic_serial_number",
        "Firmware Update Id": "firmware_update_id",
    }
    result: dict[str, str] = {}
    for label, key in labels.items():
        match = re.search(rf"(?m)^\s*{re.escape(label)}\s*:\s*(.+?)\s*$", text)
        if match:
            result[key] = match.group(1).strip()
    return result


def _parse_intrinsics(text: str, stream: str, encoding: str) -> dict[str, Any]:
    header = (
        rf'Intrinsic of "{re.escape(stream)}" / 848x480 / '
        rf"\{{[^}}\n]*{re.escape(encoding)}[^}}\n]*\}}"
    )
    match = re.search(
        header + r"(?P<body>.*?)(?=\n\s*\n|\nIntrinsic of|\nExtrinsic from)",
        text,
        re.S,
    )
    if not match:
        raise D405CaptureEvaluationError(f"missing {stream} {encoding} intrinsics")
    body = match.group("body")

    def number(label: str) -> float:
        found = re.search(rf"(?m)^\s*{re.escape(label)}\s*:\s*([-+0-9.eE]+)", body)
        if not found:
            raise D405CaptureEvaluationError(f"missing intrinsic field {label}")
        return float(found.group(1))

    model = re.search(r"(?m)^\s*Distortion(?: Model)?\s*:\s*(.+?)\s*$", body)
    coeffs = re.search(r"(?m)^\s*Coeff(?:icient)?s\s*:\s*(.+?)\s*$", body)
    if not model or not coeffs:
        raise D405CaptureEvaluationError("missing intrinsic distortion fields")
    return {
        "width": int(number("Width")),
        "height": int(number("Height")),
        "principal_point_px": [number("PPX"), number("PPY")],
        "focal_length_px": [number("Fx"), number("Fy")],
        "distortion_model": model.group(1).strip(),
        "distortion_coefficients": [
            float(value) for value in coeffs.group(1).strip().split()
        ],
    }


def _parse_depth_to_color_extrinsics(text: str) -> dict[str, Any]:
    match = re.search(
        r'Extrinsic from "Depth"\s+To\s+"Color"\s*:(?P<body>.*?)(?=\nExtrinsic from)',
        text,
        re.S,
    )
    if not match:
        raise D405CaptureEvaluationError("missing Depth-to-Color extrinsics")
    body = match.group("body")
    rotation = re.search(
        r"Rotation Matrix:\s*\n"
        r"\s*([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s*\n"
        r"\s*([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s*\n"
        r"\s*([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)",
        body,
    )
    translation = re.search(
        r"Translation Vector:\s*\[?\s*([-+0-9.eE]+)\s+"
        r"([-+0-9.eE]+)\s+([-+0-9.eE]+)\s*\]?",
        body,
    )
    if not rotation or not translation:
        raise D405CaptureEvaluationError("malformed Depth-to-Color extrinsics")
    values = [float(value) for value in rotation.groups()]
    return {
        "from": "Depth/848x480/Z16",
        "to": "Color/848x480/RGB8",
        "rotation_matrix_row_major": [values[0:3], values[3:6], values[6:9]],
        "translation_m": [float(value) for value in translation.groups()],
    }


def _usb_identity(receipt: dict[str, Any]) -> dict[str, Any]:
    usb = receipt.get("usb_identity")
    if isinstance(usb, dict):
        return usb
    # The readiness schema used by the evidence nests USB identity under inventory.
    inventory = receipt.get("inventory")
    if isinstance(inventory, dict) and isinstance(inventory.get("usb_identity"), dict):
        return inventory["usb_identity"]
    usb_section = receipt.get("usb")
    if isinstance(usb_section, dict) and isinstance(usb_section.get("identity"), dict):
        return usb_section["identity"]
    raise D405CaptureEvaluationError("readiness receipt has no USB identity")


def _reconcile_serials(
    *,
    expected: dict[str, str],
    database_device: dict[str, str],
    enumeration_device: dict[str, str],
    usb_identity: dict[str, Any],
) -> dict[str, Any]:
    usb_serial = str(
        usb_identity.get("serial_number")
        or usb_identity.get("serial")
        or usb_identity.get("USB Serial Number")
        or ""
    )
    checks = {
        "database_sdk_serial_matches_expected": (
            database_device.get("Serial Number") == expected["sdk_serial_number"]
        ),
        "enumeration_sdk_serial_matches_expected": (
            enumeration_device.get("sdk_serial_number")
            == expected["sdk_serial_number"]
        ),
        "database_asic_serial_matches_expected": (
            database_device.get("Asic Serial Number")
            == expected["asic_serial_number"]
        ),
        "enumeration_asic_serial_matches_expected": (
            enumeration_device.get("asic_serial_number")
            == expected["asic_serial_number"]
        ),
        "database_firmware_update_id_matches_asic": (
            database_device.get("Firmware Update Id")
            == expected["asic_serial_number"]
        ),
        "enumeration_firmware_update_id_matches_asic": (
            enumeration_device.get("firmware_update_id")
            == expected["asic_serial_number"]
        ),
        "ioreg_usb_serial_matches_asic": usb_serial == expected["asic_serial_number"],
        "sdk_and_asic_identifiers_are_distinct": (
            expected["sdk_serial_number"] != expected["asic_serial_number"]
        ),
        "database_product_id_matches": (
            database_device.get("Product Id", "").upper()
            == expected["usb_product_id_hex"].upper()
        ),
        "enumeration_product_id_matches": (
            enumeration_device.get("usb_product_id_hex", "").upper()
            == expected["usb_product_id_hex"].upper()
        ),
        "database_physical_port_matches": (
            database_device.get("Physical Port") == expected["physical_port"]
        ),
        "enumeration_physical_port_matches": (
            enumeration_device.get("physical_port") == expected["physical_port"]
        ),
    }
    reconciled = all(checks.values())
    return {
        "reconciled": reconciled,
        "classification": (
            "reconciled_distinct_sdk_and_asic_usb_identifiers_same_device_record"
            if reconciled
            else "unreconciled_device_identity_fail_closed"
        ),
        "sdk_logical_serial_number": expected["sdk_serial_number"],
        "asic_firmware_update_and_ioreg_usb_serial_number": expected[
            "asic_serial_number"
        ],
        "identifiers_are_equal": False,
        "checks": checks,
    }


def _parse_metadata(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if ": " in line:
            key, value = line.split(": ", 1)
            result[key.strip()] = value.strip()
    return result


def _extracted_evidence(capture_dir: Path) -> dict[str, Any]:
    depth_dir = capture_dir / "extracted" / "depth"
    color_dir = capture_dir / "extracted" / "color"
    depth_metadata = sorted(depth_dir.glob("*_metadata_*.txt"))
    color_metadata = sorted(color_dir.glob("*_metadata_*.txt"))
    depth_csvs = sorted(depth_dir.glob("*.csv"))
    if not depth_metadata or len(depth_metadata) != len(color_metadata):
        raise D405CaptureEvaluationError("extracted RGB/depth metadata pairing is incomplete")

    depth_by_counter = {
        _parse_metadata(path).get("Frame Counter"): (path, _parse_metadata(path))
        for path in depth_metadata
    }
    color_by_counter = {
        _parse_metadata(path).get("Frame Counter"): (path, _parse_metadata(path))
        for path in color_metadata
    }
    counters = sorted(set(depth_by_counter) & set(color_by_counter), key=int)
    if len(counters) != len(depth_metadata):
        raise D405CaptureEvaluationError("extracted metadata frame counters do not pair")
    pairs: list[dict[str, Any]] = []
    for counter in counters:
        depth_path, depth_values = depth_by_counter[counter]
        color_path, color_values = color_by_counter[counter]
        depth_file_timestamp = float(depth_path.stem.rsplit("_", 1)[1])
        color_file_timestamp = float(color_path.stem.rsplit("_", 1)[1])
        depth_frame_timestamp = float(depth_values["Frame Timestamp"])
        color_frame_timestamp = float(color_values["Frame Timestamp"])
        pairs.append(
            {
                "frame_counter": int(counter),
                "depth_metadata": str(depth_path.relative_to(capture_dir)),
                "color_metadata": str(color_path.relative_to(capture_dir)),
                "filename_color_minus_depth_ms": color_file_timestamp
                - depth_file_timestamp,
                "device_frame_timestamp_color_minus_depth_ms": (
                    color_frame_timestamp - depth_frame_timestamp
                )
                / 1000.0,
            }
        )

    csv_stats: list[dict[str, Any]] = []
    for path in depth_csvs:
        values = np.loadtxt(path, delimiter=",", dtype=np.float64)
        nonzero = values[values > 0.0]
        if nonzero.size == 0:
            raise D405CaptureEvaluationError(f"depth CSV has no nonzero samples: {path}")
        csv_stats.append(
            {
                "path": str(path.relative_to(capture_dir)),
                "shape": list(values.shape),
                "sample_count": int(values.size),
                "zero_count": int(np.count_nonzero(values == 0.0)),
                "nonzero_count": int(nonzero.size),
                "valid_fraction": float(nonzero.size / values.size),
                "nonzero_depth_m": {
                    "minimum": float(np.min(nonzero)),
                    "maximum": float(np.max(nonzero)),
                    "mean": float(np.mean(nonzero)),
                    "p01": float(np.percentile(nonzero, 1)),
                    "median": float(np.median(nonzero)),
                    "p99": float(np.percentile(nonzero, 99)),
                },
            }
        )
    return {
        "metadata_pairs": pairs,
        "metric_depth_csv_statistics": csv_stats,
        "depth_png_semantics": "false_color_preview_not_metric_depth_array",
    }


def _artifact_hashes(root: Path) -> list[dict[str, Any]]:
    artifacts = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        if "evaluation" in path.relative_to(root).parts:
            continue
        artifacts.append(
            {
                "path": str(path.relative_to(root)),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return artifacts


def evaluate_d405_stationary_rgbd_capture(
    capture_dir: Path,
    readiness_dir: Path,
    *,
    output_path: Path | None = None,
    contract_path: Path = CONTRACT_PATH,
) -> dict[str, Any]:
    """Evaluate existing D405 artifacts without accessing camera or robot hardware."""
    capture_dir = capture_dir.resolve()
    readiness_dir = readiness_dir.resolve()
    contract = load_contract(contract_path)
    database_path = capture_dir / contract["capture_database_name"]
    readiness_path = readiness_dir / "readiness-receipt.json"
    enum_path = readiness_dir / "readiness-receipt.enumeration.stdout.txt"
    for path in (database_path, readiness_path, enum_path):
        if not path.is_file():
            raise D405CaptureEvaluationError(f"required artifact does not exist: {path}")

    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    enumeration_text = enum_path.read_text(encoding="utf-8")
    with _open_database_read_only(database_path) as connection:
        topics, topic_ids = _topic_inventory(connection)
        expected_streams = contract["expected_streams"]
        depth_topic = expected_streams["depth"]["topic"]
        color_topic = expected_streams["color"]["topic"]
        if depth_topic not in topic_ids or color_topic not in topic_ids:
            raise D405CaptureEvaluationError("required RGBD image topics are absent")
        depth_timestamps = _topic_timestamps(connection, topic_ids[depth_topic])
        color_timestamps = _topic_timestamps(connection, topic_ids[color_topic])
        pairing = _pair_statistics(depth_timestamps, color_timestamps)

        depth_info = _semicolon_fields(
            _single_topic_string(connection, _find_topic_id(topic_ids, "Depth_0/info"))
        )
        color_info = _semicolon_fields(
            _single_topic_string(connection, _find_topic_id(topic_ids, "Color_0/info"))
        )
        depth_camera_info = _semicolon_fields(
            _single_topic_string(
                connection, _find_topic_id(topic_ids, "Depth_0/camera_info")
            )
        )
        color_camera_info = _semicolon_fields(
            _single_topic_string(
                connection, _find_topic_id(topic_ids, "Color_0/camera_info")
            )
        )
        device_info = _semicolon_fields(
            _single_topic_string(connection, topic_ids["/device_0/info"])
        )
        depth_units = float(
            _single_topic_string(
                connection, _find_topic_id(topic_ids, "Depth_Units/value")
            )
        )
        depth_to_color_tf = _semicolon_fields(
            _single_topic_string(
                connection, _find_topic_id(topic_ids, "Color_0/tf/ref_0")
            )
        )

    enumeration_device = _parse_enumeration_device(enumeration_text)
    identity = _reconcile_serials(
        expected=contract["expected_device"],
        database_device=device_info,
        enumeration_device=enumeration_device,
        usb_identity=_usb_identity(readiness),
    )
    intrinsics = {
        "depth": _parse_intrinsics(enumeration_text, "Depth", "Z16"),
        "color": _parse_intrinsics(enumeration_text, "Color", "RGB8"),
        "database_depth_camera_info": depth_camera_info,
        "database_color_camera_info": color_camera_info,
    }
    extrinsics = {
        "enumerated_depth_to_color": _parse_depth_to_color_extrinsics(enumeration_text),
        "database_color_tf_ref_0": depth_to_color_tf,
    }
    extracted = _extracted_evidence(capture_dir)

    stream_checks = {
        "depth_encoding": depth_info.get("encoding")
        == expected_streams["depth"]["encoding"],
        "color_encoding": color_info.get("encoding")
        == expected_streams["color"]["encoding"],
        "depth_fps": int(depth_info.get("fps", 0))
        == int(expected_streams["depth"]["fps"]),
        "color_fps": int(color_info.get("fps", 0))
        == int(expected_streams["color"]["fps"]),
        "depth_frame_count": len(depth_timestamps)
        >= int(contract["minimum_frames_per_stream"]),
        "color_frame_count": len(color_timestamps)
        >= int(contract["minimum_frames_per_stream"]),
        "pair_delta": pairing["absolute_delta_ms"]["maximum"]
        <= float(contract["maximum_absolute_rgb_depth_pair_delta_ms"]),
        "depth_units": math.isclose(
            depth_units,
            float(contract["expected_depth_units_m_per_z16_unit"]),
            rel_tol=0.0,
            abs_tol=1e-12,
        ),
    }
    passed = identity["reconciled"] and all(stream_checks.values())
    failure_reasons = [
        key for key, value in {**identity["checks"], **stream_checks}.items() if not value
    ]
    librealsense = readiness.get("librealsense", {})
    binary_hashes = {
        name: item
        for name, item in librealsense.get("executables", {}).items()
        if isinstance(item, dict)
    }
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "proof_class": contract["proof_class"],
        "camera_or_robot_accessed_by_evaluator": False,
        "database_open_mode": "sqlite_read_only_immutable",
        "authority": contract["authority"],
        "stationarity_scope": {
            "capture_designation": "stationary",
            "robot_stationarity_independently_measured": False,
        },
        "lineage": {
            "capture_directory": str(capture_dir),
            "readiness_directory": str(readiness_dir),
            "contract": {
                "path": str(contract_path.resolve()),
                "sha256": sha256_file(contract_path),
            },
            "capture_artifacts": _artifact_hashes(capture_dir),
            "readiness_artifacts": _artifact_hashes(readiness_dir),
            "reported_librealsense_version": librealsense.get("version_output"),
            "reported_binary_hashes": binary_hashes,
        },
        "device_identity": {
            "database": device_info,
            "enumeration": enumeration_device,
            "ioreg_usb": _usb_identity(readiness),
            "reconciliation": identity,
        },
        "rosbag": {
            "database": str(database_path),
            "database_sha256": sha256_file(database_path),
            "topic_count": len(topics),
            "topics": topics,
            "depth_image_frame_count": len(depth_timestamps),
            "color_image_frame_count": len(color_timestamps),
            "depth_image_duration_s": (
                depth_timestamps[-1] - depth_timestamps[0]
            )
            / 1_000_000_000.0,
            "color_image_duration_s": (
                color_timestamps[-1] - color_timestamps[0]
            )
            / 1_000_000_000.0,
            "rgb_depth_pairing": pairing,
        },
        "streams": {
            "depth": {
                "database_info": depth_info,
                "encoding": "Z16",
                "depth_units_m_per_z16_unit": depth_units,
                "raw_frame_size_bytes": 848 * 480 * 2,
            },
            "color": {"database_info": color_info, "encoding": "RGB8"},
            "checks": stream_checks,
        },
        "calibration": {
            "intrinsics": intrinsics,
            "extrinsics": extrinsics,
            "scope": "camera_internal_rgb_depth_calibration_only",
            "camera_to_robot_extrinsic_available": False,
        },
        "extracted": extracted,
        "verdict": {
            "passed": passed,
            "classification": (
                "physical_stationary_rgbd_capture_ingested_identity_reconciled"
                if passed
                else "physical_stationary_rgbd_capture_not_accepted_fail_closed"
            ),
            "failure_reasons": failure_reasons,
            "board_registration_authority": False,
            "task_authority": False,
        },
    }
    if output_path is not None:
        atomic_write_json(output_path, receipt)
    return receipt
