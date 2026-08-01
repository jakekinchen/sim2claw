import json
from pathlib import Path

import pytest

from sim2claw.learning_factory_artifacts import FactoryArtifactError
from sim2claw.observable_registration_d405_static_metric_capture import (
    CONTRACT_PATH,
    load_d405_static_metric_capture_contract,
    run_d405_static_metric_capture_once,
    validate_d405_static_metric_capture,
)


def _write_synthetic_capture(
    output_directory: Path,
    *,
    duplicate_frame_number: bool = False,
    truncate_raw: bool = False,
) -> tuple[Path, Path, Path]:
    output_directory.mkdir()
    prefix = output_directory / "capture"
    width = 424
    height = 240
    frame_count = 30
    raw_frame_bytes = width * height * 2
    raw_size = raw_frame_bytes * frame_count - int(truncate_raw)
    with prefix.with_suffix(".z16").open("wb") as raw_file:
        raw_file.truncate(raw_size)
    rows = []
    for index in range(frame_count):
        rows.append(
            {
                "schema_version": "sim2claw.d405_depth_frame.v1",
                "frame_index": index,
                "frame_number": 100 if duplicate_frame_number else 100 + index,
                "sensor_timestamp_ms": 1_000.0 + index * (1_000.0 / 30.0),
                "sensor_timestamp_domain": "Hardware Clock",
                "host_arrival_steady_ns": 5_000_000_000 + index * 33_333_333,
                "raw_offset_bytes": index * raw_frame_bytes,
                "width": width,
                "height": height,
                "stride_bytes": width * 2,
                "bits_per_pixel": 16,
                "frame_counter": 500 + index,
                "actual_exposure_us": 3_000,
                "gain_level": None,
                "actual_fps_x1000": 30_000,
            }
        )
    prefix.with_suffix(".metadata.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    prefix.with_suffix(".manifest.json").write_text(
        json.dumps(
            {
                "schema_version": (
                    "sim2claw.d405_metric_depth_capture_manifest.v1"
                ),
                "device_name": "Intel RealSense D405",
                "device_serial": "130322273474",
                "librealsense_api_version": 25803,
                "width": width,
                "height": height,
                "fps": 30,
                "frame_count": frame_count,
                "depth_scale_meters": 0.0001,
                "raw_frame_bytes": raw_frame_bytes,
                "intrinsics": {
                    "fx": 211.2,
                    "fy": 211.4,
                    "ppx": 212.0,
                    "ppy": 120.0,
                    "model": 4,
                    "coeffs": [0.0, 0.0, 0.0, 0.0, 0.0],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return (
        prefix.with_suffix(".manifest.json"),
        prefix.with_suffix(".metadata.jsonl"),
        prefix.with_suffix(".z16"),
    )


def test_contract_is_exact_zero_motion_one_packet() -> None:
    contract = load_d405_static_metric_capture_contract()
    packet = contract["packet"]
    assert packet["device_family"] == "Intel RealSense D405"
    assert (packet["frame_count"], packet["width"], packet["height"]) == (
        30,
        424,
        240,
    )
    assert packet["fps"] == 30
    assert packet["format"] == "Z16"
    assert contract["execution_boundary"]["packet_count"] == 1
    assert contract["execution_boundary"]["adaptive_retry_allowed"] is False
    assert not any(contract["authority"].values())


def test_validator_accepts_complete_capture_and_reports_optional_support(
    tmp_path: Path,
) -> None:
    contract = load_d405_static_metric_capture_contract()
    manifest, metadata, raw = _write_synthetic_capture(tmp_path / "capture")
    result = validate_d405_static_metric_capture(
        contract, manifest_path=manifest, metadata_path=metadata, raw_path=raw
    )
    assert result["status"] == "PASS_D405_STATIC_METRIC_CAPTURE"
    assert result["frame_count"] == 30
    assert result["raw_byte_count"] == 424 * 240 * 2 * 30
    assert result["optional_metadata_support"] == {
        "frame_counter": "complete",
        "actual_exposure_us": "complete",
        "gain_level": "missing",
        "actual_fps_x1000": "complete",
    }


@pytest.mark.parametrize(
    ("duplicate_frame_number", "truncate_raw", "match"),
    [
        (True, False, "frame numbers are not unique"),
        (False, True, "raw byte count does not match"),
    ],
)
def test_validator_fails_closed_on_capture_corruption(
    tmp_path: Path,
    duplicate_frame_number: bool,
    truncate_raw: bool,
    match: str,
) -> None:
    contract = load_d405_static_metric_capture_contract()
    manifest, metadata, raw = _write_synthetic_capture(
        tmp_path / "capture",
        duplicate_frame_number=duplicate_frame_number,
        truncate_raw=truncate_raw,
    )
    with pytest.raises(FactoryArtifactError, match=match):
        validate_d405_static_metric_capture(
            contract,
            manifest_path=manifest,
            metadata_path=metadata,
            raw_path=raw,
        )


def test_live_runner_refuses_current_false_camera_authority(
    tmp_path: Path,
) -> None:
    with pytest.raises(FactoryArtifactError, match="camera authority"):
        run_d405_static_metric_capture_once(
            CONTRACT_PATH,
            tmp_path / "or45",
            camera_authority=False,
        )
    assert not (tmp_path / "or45").exists()
