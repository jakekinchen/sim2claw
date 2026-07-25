from __future__ import annotations

import struct
from pathlib import Path

import pytest

from sim2claw.d405_stationary_rgbd_capture import (
    _decode_cdr_string,
    _pair_statistics,
    _reconcile_serials,
    evaluate_d405_stationary_rgbd_capture,
)
from sim2claw.paths import REPO_ROOT


def _identity_inputs() -> tuple[dict, dict, dict, dict]:
    expected = {
        "sdk_serial_number": "130322273474",
        "asic_serial_number": "133323070214",
        "firmware_update_id": "133323070214",
        "usb_product_id_hex": "0B5B",
        "physical_port": "0-2-1",
    }
    database = {
        "Serial Number": "130322273474",
        "Asic Serial Number": "133323070214",
        "Firmware Update Id": "133323070214",
        "Product Id": "0B5B",
        "Physical Port": "0-2-1",
    }
    enumeration = {
        "sdk_serial_number": "130322273474",
        "asic_serial_number": "133323070214",
        "firmware_update_id": "133323070214",
        "usb_product_id_hex": "0B5B",
        "physical_port": "0-2-1",
    }
    usb = {"serial_number": "133323070214"}
    return expected, database, enumeration, usb


def test_decodes_ros2_cdr_string() -> None:
    value = b"encoding=Z16;fps=30"
    blob = b"\x00\x01\x00\x00" + struct.pack("<I", len(value) + 1) + value + b"\x00"
    assert _decode_cdr_string(blob) == value.decode()


def test_serials_reconcile_as_distinct_identity_fields() -> None:
    expected, database, enumeration, usb = _identity_inputs()
    result = _reconcile_serials(
        expected=expected,
        database_device=database,
        enumeration_device=enumeration,
        usb_identity=usb,
    )
    assert result["reconciled"] is True
    assert result["identifiers_are_equal"] is False
    assert result["classification"].startswith("reconciled_distinct")


def test_serial_reconciliation_fails_closed_when_usb_chain_breaks() -> None:
    expected, database, enumeration, usb = _identity_inputs()
    usb["serial_number"] = "different-device"
    result = _reconcile_serials(
        expected=expected,
        database_device=database,
        enumeration_device=enumeration,
        usb_identity=usb,
    )
    assert result["reconciled"] is False
    assert result["checks"]["ioreg_usb_serial_matches_asic"] is False
    assert result["classification"] == "unreconciled_device_identity_fail_closed"


def test_pair_statistics_are_signed_color_minus_depth() -> None:
    result = _pair_statistics([0, 10_000_000], [250_000, 10_300_000])
    assert result["pair_count"] == 2
    assert result["signed_color_minus_depth_ms"]["minimum"] == pytest.approx(0.25)
    assert result["absolute_delta_ms"]["maximum"] == pytest.approx(0.3)


def test_existing_stationary_capture_passes_only_bounded_proof_when_present() -> None:
    capture = REPO_ROOT / "runs" / "d405-rgbd-capture" / "20260725-stationary-v2"
    readiness = (
        REPO_ROOT
        / "runs"
        / "d405-rgbd-readiness"
        / "20260725-elevated-inventory"
    )
    if not capture.is_dir() or not readiness.is_dir():
        pytest.skip("ignored local D405 stationary RGBD evidence is not present")

    receipt = evaluate_d405_stationary_rgbd_capture(capture, readiness)

    assert receipt["verdict"]["passed"] is True
    assert receipt["proof_class"] == "physical_stationary_rgbd_capture_only"
    assert receipt["rosbag"]["depth_image_frame_count"] == 135
    assert receipt["rosbag"]["color_image_frame_count"] == 135
    assert receipt["rosbag"]["rgb_depth_pairing"]["absolute_delta_ms"]["maximum"] < 2
    assert receipt["streams"]["depth"]["depth_units_m_per_z16_unit"] == pytest.approx(
        0.0001
    )
    assert receipt["device_identity"]["reconciliation"]["reconciled"] is True
    assert all(value is False for value in receipt["authority"].values())
    assert receipt["verdict"]["board_registration_authority"] is False
    assert receipt["verdict"]["task_authority"] is False
