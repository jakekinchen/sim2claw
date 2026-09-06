"""Synthetic files test integrity rejection, never physical capture admission."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from sim2claw.d405_rgbd_integrity import main, validate_capture
from sim2claw import d405_rgbd_integrity


@pytest.fixture
def capture(tmp_path: Path) -> Path:
    root = tmp_path / "capture"
    root.mkdir()
    intrinsics = {"width": 848, "height": 480, "fx": 425., "fy": 426., "ppx": 424., "ppy": 240.,
                  "distortion_model": 0, "coeffs": [0.] * 5}
    manifest = {"schema_version": "sim2claw.d405_rgbd_capture.v1", "status": "complete",
                "proof_class": "synthetic_fixture", "experiment_id": "fixture", "device_serial": "fixture-device",
                "device_name": "Intel RealSense D405", "sdk_version": "synthetic", "frame_count": 3,
                "width": 848, "height": 480, "fps": 30, "depth_format": "Z16", "color_format": "RGB8",
                "depth_scale_meters": .0001, "pairing": "sdk_frameset", "exposure_synchronization_verified": False,
                "host_clock": "std_chrono_steady_clock_nanoseconds", "depth_intrinsics": intrinsics,
                "color_intrinsics": copy.deepcopy(intrinsics),
                "depth_to_color": {"rotation_column_major": [1,0,0,0,1,0,0,0,1], "translation_m": [0,0,0]}}
    (root / "manifest.json").write_text(json.dumps(manifest))
    rows = []
    for index in range(3):
        row = {"schema_version": "sim2claw.d405_rgbd_frame.v1", "index": index,
               "host_arrival_steady_ns": 1000000000 + index * 33333333}
        for stream, channels in (("depth", 2), ("color", 3)):
            size = 848 * 480 * channels
            row[stream] = {"frame_number": 50 + index, "device_timestamp_ms": 100 + index * 33.333,
                           "timestamp_domain": "Hardware Clock", "width": 848, "height": 480,
                           "stride_bytes": 848 * channels, "bits_per_pixel": channels * 8,
                           "offset_bytes": index * size, "bytes": size,
                           "frame_counter": index, "actual_exposure_us": 1000, "gain_level": None,
                           "actual_fps_x1000": 30000}
        rows.append(row)
    write_rows(root, rows)
    for name, channels in (("depth.z16", 2), ("color.rgb8", 3)):
        with (root / name).open("wb") as f:
            f.truncate(3 * 848 * 480 * channels)
    return root


def read_rows(root: Path) -> list[dict]:
    return [json.loads(line) for line in (root / "frames.jsonl").read_text().splitlines()]


def write_rows(root: Path, rows: list[dict]) -> None:
    (root / "frames.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))


def check(root: Path) -> dict:
    return validate_capture(root, expected_serial="fixture-device", expected_experiment="fixture")


def test_complete_files_remain_synthetic_and_unadmitted(capture: Path) -> None:
    report = check(capture)
    assert report == check(capture)
    assert report["status"] == "STRUCTURALLY_VALID_UNREVIEWED"
    assert report["source_proof_class"] == "synthetic_fixture"
    assert not any(report[key] for key in ("physical_capture_verified", "jaw_geometry_verified", "calibration_admitted",
                                          "exposure_synchronization_verified", "fit_performed", "hardware_access_performed"))
    assert report["optional_metadata_available_frames"]["color"]["gain_level"] == 0
    assert report["frame_number_gaps"] == {"depth": 0, "color": 0}
    assert len(report["artifacts"]) == 4


@pytest.mark.parametrize("name", ["depth.z16", "color.rgb8", "frames.jsonl", "manifest.json"])
def test_missing_file_rejected(capture: Path, name: str) -> None:
    (capture / name).unlink()
    with pytest.raises(ValueError, match="artifact"):
        check(capture)


@pytest.mark.parametrize("name", ["depth.z16", "color.rgb8"])
def test_raw_truncation_or_extra_bytes_rejected(capture: Path, name: str) -> None:
    with (capture / name).open("ab") as f:
        f.write(b"x")
    with pytest.raises(ValueError, match="raw size"):
        check(capture)


@pytest.mark.parametrize(("key", "value"), [
    ("frame_number", 50), ("device_timestamp_ms", 100), ("timestamp_domain", "changed"),
    ("stride_bytes", 0), ("offset_bytes", 0), ("bytes", 1), ("bits_per_pixel", 8),
    ("frame_counter", 0), ("actual_exposure_us", -1), ("device_timestamp_ms", float("nan")),
])
@pytest.mark.parametrize("stream", ["depth", "color"])
def test_corrupt_frame_metadata_rejected(capture: Path, key: str, value: object, stream: str) -> None:
    rows = read_rows(capture)
    rows[1][stream][key] = value
    write_rows(capture, rows)
    with pytest.raises(ValueError):
        check(capture)


@pytest.mark.parametrize(("key", "value"), [
    ("device_serial", "wrong"), ("experiment_id", "wrong"), ("status", "partial"),
    ("frame_count", True), ("frame_count", 4), ("frame_count", 901), ("width", 424),
    ("depth_scale_meters", 0), ("depth_scale_meters", float("nan")), ("color_format", "BGR8"),
    ("exposure_synchronization_verified", True), ("proof_class", "physical_success"),
])
def test_manifest_drift_or_claim_escalation_rejected(capture: Path, key: str, value: object) -> None:
    path = capture / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest[key] = value
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        check(capture)


@pytest.mark.parametrize("field", ["color_intrinsics", "depth_intrinsics", "depth_to_color"])
def test_both_calibrations_and_extrinsics_required(capture: Path, field: str) -> None:
    path = capture / "manifest.json"
    manifest = json.loads(path.read_text())
    del manifest[field]
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        check(capture)


def test_reflected_rotation_rejected(capture: Path) -> None:
    path = capture / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["depth_to_color"]["rotation_column_major"][0] = -1
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="right-handed"):
        check(capture)


def test_stream_clock_difference_is_explicit_not_synchronized(capture: Path) -> None:
    rows = read_rows(capture)
    for row in rows:
        row["color"]["timestamp_domain"] = "System Time"
    write_rows(capture, rows)
    report = check(capture)
    assert report["comparable_pair_timestamps"] == 0
    assert report["maximum_absolute_pair_timestamp_delta_ms"] is None
    assert report["exposure_synchronization_verified"] is False


def test_missing_optional_support_differs_from_missing_declaration(capture: Path) -> None:
    rows = read_rows(capture)
    rows[1]["depth"].pop("gain_level")
    write_rows(capture, rows)
    with pytest.raises(ValueError, match="declaration"):
        check(capture)


def test_duplicate_keys_and_host_reordering_rejected(capture: Path) -> None:
    rows = read_rows(capture)
    rows[1]["host_arrival_steady_ns"] = rows[0]["host_arrival_steady_ns"]
    write_rows(capture, rows)
    with pytest.raises(ValueError, match="host timestamps"):
        check(capture)
    path = capture / "manifest.json"
    path.write_text(path.read_text().replace('"status": "complete"', '"status": "complete", "status": "complete"'))
    with pytest.raises(ValueError, match="duplicate JSON key"):
        check(capture)


def test_symlink_artifact_rejected(capture: Path, tmp_path: Path) -> None:
    target = tmp_path / "saved"
    (capture / "depth.z16").rename(target)
    (capture / "depth.z16").symlink_to(target)
    with pytest.raises(ValueError, match="symlink"):
        check(capture)


def test_cli_no_simulator_or_sdk_import(capture: Path) -> None:
    code = """
import sys
from pathlib import Path
from sim2claw.d405_rgbd_integrity import validate_capture
validate_capture(Path(sys.argv[1]), expected_serial='fixture-device', expected_experiment='fixture')
assert not {'mujoco', 'numpy', 'torch', 'pyrealsense2'} & sys.modules.keys()
"""
    subprocess.run([sys.executable, "-c", code, str(capture)], check=True, capture_output=True)


def test_cli_returns_failure_json_for_partial_capture(capture: Path, capsys: pytest.CaptureFixture) -> None:
    (capture / "manifest.json").unlink()
    assert main([str(capture), "--expected-serial", "fixture-device", "--expected-experiment", "fixture"]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "INVALID"


def test_same_stat_metadata_change_during_validation_rejected(capture: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original = d405_rgbd_integrity.digest
    def mutate_before_hash(path: Path) -> str:
        if path.name == "manifest.json":
            stat = path.stat()
            path.write_text(path.read_text().replace('"sdk_version": "synthetic"', '"sdk_version": "tampered!"'))
            os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        return original(path)
    monkeypatch.setattr(d405_rgbd_integrity, "digest", mutate_before_hash)
    with pytest.raises(ValueError, match="metadata changed"):
        check(capture)
