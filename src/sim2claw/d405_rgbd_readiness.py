"""Inventory the local D405/librealsense metric-depth readiness boundary.

This lane is intentionally camera-readiness only.  It does not start a stream,
open the robot gateway, infer calibration from nominal geometry, or promote a
metric-registration claim.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence


RECEIPT_SCHEMA = "sim2claw.d405_rgbd_readiness_receipt.v1"
MACOS_INSTALLATION_GUIDE = (
    "https://dev.realsenseai.com/installation/"
    "macos-installation-for-realsense-sdk/"
)
EXPECTED_PRODUCT_NAME = "Intel(R) RealSense(TM) Depth Camera 405"


class D405RGBDReadinessError(RuntimeError):
    """The bounded readiness inventory could not be completed."""


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("utf-8")


def _write_bytes(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(value)
    temporary.replace(path)


def _run(command: Sequence[str], *, timeout_seconds: float = 10.0) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            list(command),
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return {
            "command": list(command),
            "returncode": None,
            "stdout": b"",
            "stderr": str(error).encode("utf-8", errors="replace"),
        }
    return {
        "command": list(command),
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _match_int(text: str, name: str) -> int | None:
    match = re.search(rf'"{re.escape(name)}"\s*=\s*(\d+)', text)
    return int(match.group(1)) if match else None


def _match_string(text: str, name: str) -> str | None:
    match = re.search(rf'"{re.escape(name)}"\s*=\s*"([^"]+)"', text)
    return match.group(1) if match else None


def _d405_usb_identity(ioreg_text: str) -> dict[str, Any] | None:
    marker = ioreg_text.find(EXPECTED_PRODUCT_NAME)
    if marker < 0:
        return None
    window = ioreg_text[marker : marker + 4_096]
    return {
        "product_name": _match_string(window, "USB Product Name")
        or EXPECTED_PRODUCT_NAME,
        "serial_number": _match_string(window, "USB Serial Number"),
        "vendor_id_decimal": _match_int(window, "idVendor"),
        "product_id_decimal": _match_int(window, "idProduct"),
        "usb_speed_code": _match_int(window, "USBSpeed"),
    }


def _artifact(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.resolve()),
        "sha256": _sha256_file(path),
        "bytes": path.stat().st_size,
    }


def inventory_d405_rgbd_readiness(
    *,
    output_path: Path,
    enumeration_file: Path | None = None,
) -> dict[str, Any]:
    """Write a provenance-bound readiness receipt without starting a stream."""

    output_path = output_path.resolve()
    enumerator = shutil.which("rs-enumerate-devices")
    recorder = shutil.which("rs-record")
    converter = shutil.which("rs-convert")
    ioreg = shutil.which("ioreg")
    if ioreg is None:
        raise D405RGBDReadinessError("macOS ioreg is unavailable")

    usb_result = _run([ioreg, "-p", "IOUSB", "-l", "-w", "0"])
    usb_text = usb_result["stdout"].decode("utf-8", errors="replace")
    usb_identity = _d405_usb_identity(usb_text)

    version_result = (
        _run([enumerator, "--version"]) if enumerator is not None else None
    )
    if enumeration_file is not None:
        enumeration_file = enumeration_file.resolve()
        if not enumeration_file.is_file():
            raise D405RGBDReadinessError(
                f"enumeration transcript does not exist: {enumeration_file}"
            )
        enumeration_stdout = enumeration_file.read_bytes()
        enumeration_stderr = b""
        enumeration_returncode = 0
        enumeration_command = [
            "sudo",
            enumerator or "/opt/homebrew/bin/rs-enumerate-devices",
            "-c",
        ]
        enumeration_source = "operator_provided_privileged_transcript"
    elif enumerator is not None:
        enumeration_result = _run([enumerator, "-c"])
        enumeration_stdout = enumeration_result["stdout"]
        enumeration_stderr = enumeration_result["stderr"]
        enumeration_returncode = enumeration_result["returncode"]
        enumeration_command = enumeration_result["command"]
        enumeration_source = "live_unprivileged_probe"
    else:
        enumeration_stdout = b""
        enumeration_stderr = b"rs-enumerate-devices is unavailable"
        enumeration_returncode = None
        enumeration_command = []
        enumeration_source = "missing_sdk"

    evidence_stem = output_path.with_suffix("")
    stdout_path = evidence_stem.with_name(evidence_stem.name + ".enumeration.stdout.txt")
    stderr_path = evidence_stem.with_name(evidence_stem.name + ".enumeration.stderr.txt")
    _write_bytes(stdout_path, enumeration_stdout)
    _write_bytes(stderr_path, enumeration_stderr)

    combined = (enumeration_stdout + b"\n" + enumeration_stderr).decode(
        "utf-8", errors="replace"
    )
    lowered = combined.lower()
    access_denied = (
        "rs2_usb_status_access" in lowered
        or "failed to claim usb interface" in lowered
        or "failed to set power state" in lowered
    )
    device_opened = enumeration_returncode == 0 and (
        "realsense" in lowered or "stereo module" in lowered
    )
    intrinsics_observed = device_opened and "intrinsic" in lowered
    extrinsics_observed = device_opened and "extrinsic" in lowered
    metric_depth_capability_observed = device_opened and (
        "depth" in lowered or "z16" in lowered
    )

    if enumerator is None:
        status = "librealsense_tools_unavailable"
    elif usb_identity is None:
        status = "d405_not_present_on_usb"
    elif access_denied:
        status = "elevated_libusb_access_required"
    elif not device_opened:
        status = "sdk_device_enumeration_failed"
    elif not (intrinsics_observed and metric_depth_capability_observed):
        status = "sdk_enumerated_without_metric_calibration_evidence"
    else:
        status = "metric_depth_calibration_enumerated"

    executable_evidence: dict[str, Any] = {}
    for name, value in (
        ("rs_enumerate_devices", enumerator),
        ("rs_record", recorder),
        ("rs_convert", converter),
    ):
        if value is not None:
            path = Path(value).resolve()
            executable_evidence[name] = {
                "path": str(path),
                "sha256": _sha256_file(path),
            }

    version_text = ""
    if version_result is not None:
        version_text = (
            version_result["stdout"] + version_result["stderr"]
        ).decode("utf-8", errors="replace").strip()

    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "created_at": datetime.now(UTC).isoformat(),
        "status": status,
        "proof_class": "physical_camera_metric_depth_readiness_only",
        "host": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "uid": os.getuid(),
            "effective_uid": os.geteuid(),
        },
        "usb": {
            "d405_present": usb_identity is not None,
            "identity": usb_identity,
            "ioreg_command": usb_result["command"],
            "ioreg_returncode": usb_result["returncode"],
            "ioreg_stdout_sha256": _sha256_bytes(usb_result["stdout"]),
        },
        "librealsense": {
            "version_output": version_text,
            "executables": executable_evidence,
            "official_macos_access_guidance": MACOS_INSTALLATION_GUIDE,
        },
        "calibration_enumeration": {
            "source": enumeration_source,
            "command": enumeration_command,
            "returncode": enumeration_returncode,
            "stdout": _artifact(stdout_path),
            "stderr": _artifact(stderr_path),
            "device_opened": device_opened,
            "metric_depth_capability_observed": metric_depth_capability_observed,
            "intrinsics_observed": intrinsics_observed,
            "extrinsics_observed": extrinsics_observed,
            "macos_libusb_access_denied": access_denied,
        },
        "readiness": {
            "synchronized_rgbd_capture_ready": False,
            "metric_depth_scale_observed": False,
            "chessboard_plane_registration_ready": False,
            "uncertainty_status": (
                "not_estimable_until_metric_depth_frames_and_calibration_are_captured"
            ),
        },
        "next_action": {
            "command": (
                "sudo /opt/homebrew/bin/rs-enumerate-devices -c"
                if status == "elevated_libusb_access_required"
                else None
            ),
            "purpose": (
                "enumerate D405 depth calibration through the officially "
                "documented macOS elevated libusb route"
                if status == "elevated_libusb_access_required"
                else None
            ),
        },
        "authority": {
            "camera_stream_started": False,
            "robot_gateway_opened": False,
            "robot_motion": False,
            "metric_registration": False,
            "policy_transfer": False,
            "promotion": False,
        },
    }
    receipt["receipt_digest"] = _sha256_bytes(_canonical_bytes(receipt))
    _write_bytes(output_path, _canonical_bytes(receipt))
    return receipt
