from __future__ import annotations

import json
from pathlib import Path

from sim2claw import d405_rgbd_readiness as readiness


IOREG_D405 = b"""
+-o Intel(R) RealSense(TM) Depth Camera 405@00200000
  {
    "USBSpeed" = 4
    "idProduct" = 2907
    "USB Product Name" = "Intel(R) RealSense(TM) Depth Camera 405"
    "idVendor" = 32902
    "USB Serial Number" = "fixture-serial"
  }
"""


def _result(
    command: list[str],
    *,
    returncode: int = 0,
    stdout: bytes = b"",
    stderr: bytes = b"",
) -> dict[str, object]:
    return {
        "command": command,
        "returncode": returncode,
        "stdout": stdout,
        "stderr": stderr,
    }


def _install_fake_runtime(
    tmp_path: Path,
    monkeypatch,
    *,
    enumeration_result: dict[str, object],
) -> None:
    for name in ("rs-enumerate-devices", "rs-record", "rs-convert"):
        path = tmp_path / name
        path.write_bytes(name.encode())

    def which(name: str) -> str | None:
        if name == "ioreg":
            return "/usr/sbin/ioreg"
        candidate = tmp_path / name
        return str(candidate) if candidate.exists() else None

    def run(command, *, timeout_seconds=10.0):
        del timeout_seconds
        if command[0] == "/usr/sbin/ioreg":
            return _result(list(command), stdout=IOREG_D405)
        if command[-1] == "--version":
            return _result(list(command), stdout=b"2.58.3\n")
        return enumeration_result

    monkeypatch.setattr(readiness.shutil, "which", which)
    monkeypatch.setattr(readiness, "_run", run)


def test_unprivileged_macos_access_failure_is_a_truthful_readiness_receipt(
    tmp_path: Path, monkeypatch
) -> None:
    enumeration = _result(
        [str(tmp_path / "rs-enumerate-devices"), "-c"],
        returncode=1,
        stderr=(
            b"failed to claim usb interface: 0, "
            b"error: RS2_USB_STATUS_ACCESS\nfailed to set power state\n"
        ),
    )
    _install_fake_runtime(
        tmp_path, monkeypatch, enumeration_result=enumeration
    )

    receipt = readiness.inventory_d405_rgbd_readiness(
        output_path=tmp_path / "receipt.json"
    )

    assert receipt["status"] == "elevated_libusb_access_required"
    assert receipt["usb"]["d405_present"] is True
    assert receipt["usb"]["identity"]["product_id_decimal"] == 2907
    assert receipt["calibration_enumeration"]["device_opened"] is False
    assert receipt["readiness"]["synchronized_rgbd_capture_ready"] is False
    assert receipt["next_action"]["command"] == (
        "sudo /opt/homebrew/bin/rs-enumerate-devices -c"
    )
    assert not any(receipt["authority"].values())


def test_privileged_transcript_can_establish_calibration_enumeration_only(
    tmp_path: Path, monkeypatch
) -> None:
    _install_fake_runtime(
        tmp_path,
        monkeypatch,
        enumeration_result=_result([], returncode=1),
    )
    transcript = tmp_path / "privileged-enumeration.txt"
    transcript.write_text(
        "Intel(R) RealSense(TM) Depth Camera 405\n"
        "Stereo Module\nDepth Z16\nDepth Intrinsic\nDepth Extrinsic\n",
        encoding="utf-8",
    )

    receipt = readiness.inventory_d405_rgbd_readiness(
        output_path=tmp_path / "receipt.json",
        enumeration_file=transcript,
    )

    assert receipt["status"] == "metric_depth_calibration_enumerated"
    assert receipt["calibration_enumeration"]["intrinsics_observed"] is True
    assert receipt["calibration_enumeration"]["extrinsics_observed"] is True
    assert receipt["readiness"]["synchronized_rgbd_capture_ready"] is False
    assert receipt["authority"]["metric_registration"] is False


def test_receipt_and_raw_enumeration_outputs_are_hash_bound(
    tmp_path: Path, monkeypatch
) -> None:
    enumeration = _result(
        [str(tmp_path / "rs-enumerate-devices"), "-c"],
        returncode=1,
        stdout=b"partial stdout\n",
        stderr=b"failed to set power state\n",
    )
    _install_fake_runtime(
        tmp_path, monkeypatch, enumeration_result=enumeration
    )
    output = tmp_path / "receipt.json"

    receipt = readiness.inventory_d405_rgbd_readiness(output_path=output)

    stored = json.loads(output.read_text(encoding="utf-8"))
    assert stored == receipt
    for stream in ("stdout", "stderr"):
        artifact = receipt["calibration_enumeration"][stream]
        path = Path(artifact["path"])
        assert path.is_file()
        assert readiness._sha256_file(path) == artifact["sha256"]
