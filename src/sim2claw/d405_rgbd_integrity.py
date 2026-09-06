"""Offline native RGBD byte/metadata validation, never physical admission.

Uses only the standard library. No SDK, camera, robot, fit, or simulator imports.
The emitted hashes can be frozen by a future evaluator before annotations/fit.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

SCHEMA = "sim2claw.d405_rgbd_capture.v1"
OPTIONAL_METADATA = ("frame_counter", "actual_exposure_us", "gain_level", "actual_fps_x1000")
FILES = ("manifest.json", "frames.jsonl", "depth.z16", "color.rgb8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def integer(value: Any, minimum: int = 0) -> bool:
    return type(value) is int and value >= minimum


def finite(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def _json(text: str) -> dict:
    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict:
        result = {}
        for key, value in pairs:
            require(key not in result, f"duplicate JSON key: {key}")
            result[key] = value
        return result
    value = json.loads(text, object_pairs_hook=unique_pairs)
    require(isinstance(value, dict), "JSON record must be an object")
    return value


def _intrinsics(value: Any, width: int, height: int) -> None:
    require(isinstance(value, dict), "missing intrinsics")
    require(value.get("width") == width and value.get("height") == height, "intrinsics profile mismatch")
    require(all(finite(value.get(k)) for k in ("fx", "fy", "ppx", "ppy")), "nonfinite intrinsics")
    require(value["fx"] > 0 and value["fy"] > 0, "invalid focal lengths")
    require(integer(value.get("distortion_model")) and value["distortion_model"] <= 6, "invalid distortion model")
    coeffs = value.get("coeffs")
    require(isinstance(coeffs, list) and len(coeffs) == 5 and all(map(finite, coeffs)), "invalid distortion coefficients")


def _extrinsics(value: Any) -> None:
    require(isinstance(value, dict), "missing depth-to-color extrinsics")
    rotation, translation = value.get("rotation_column_major"), value.get("translation_m")
    require(isinstance(rotation, list) and len(rotation) == 9 and all(map(finite, rotation)), "invalid rotation")
    require(isinstance(translation, list) and len(translation) == 3 and all(map(finite, translation)), "invalid translation")
    columns = [rotation[i:i + 3] for i in (0, 3, 6)]
    for i in range(3):
        for j in range(3):
            dot = sum(a * b for a, b in zip(columns[i], columns[j]))
            require(abs(dot - int(i == j)) < 1e-4, "rotation is not orthonormal")
    a, b, c = columns
    det = a[0] * (b[1]*c[2] - b[2]*c[1]) - b[0] * (a[1]*c[2] - a[2]*c[1]) + c[0] * (a[1]*b[2] - a[2]*b[1])
    require(abs(det - 1) < 1e-4, "rotation is not right-handed")


def validate_capture(directory: Path, *, expected_serial: str, expected_experiment: str) -> dict[str, Any]:
    """Check saved data, preserving synthetic/unreviewed provenance separately.

    A valid record does not prove the camera was present, the measurements are
    independent, or either jaw is visible. No future physical gate is opened.
    """
    directory = Path(directory).absolute()
    require(not any(p.is_symlink() for p in (directory, *directory.parents)), "symlink capture directory")
    require(directory.is_dir(), "capture directory missing")
    paths = {name: directory / name for name in FILES}
    for name, path in paths.items():
        require(path.is_file() and not path.is_symlink(), f"missing or symlink artifact: {name}")
    before = {name: (p.stat().st_size, p.stat().st_mtime_ns) for name, p in paths.items()}
    require(paths["manifest.json"].stat().st_size <= 65536, "oversized manifest")
    require(paths["frames.jsonl"].stat().st_size <= 16 * 1024 * 1024, "oversized frame metadata")
    manifest_bytes = paths["manifest.json"].read_bytes()
    manifest = _json(manifest_bytes.decode("utf-8"))
    require(manifest.get("schema_version") == SCHEMA and manifest.get("status") == "complete", "capture is incomplete or has unsupported schema")
    require(manifest.get("proof_class") in {"synthetic_fixture", "unreviewed_native_rgbd_capture"}, "unsupported proof class")
    require(bool(expected_serial) and manifest.get("device_serial") == expected_serial, "device serial mismatch")
    require(bool(expected_experiment) and manifest.get("experiment_id") == expected_experiment, "experiment identity mismatch")
    require(manifest.get("device_name") == "Intel RealSense D405", "not a D405 capture")
    require(isinstance(manifest.get("sdk_version"), str) and bool(manifest["sdk_version"]), "missing SDK version")
    require((manifest.get("width"), manifest.get("height"), manifest.get("fps")) == (848, 480, 30), "exact profile mismatch")
    require(manifest.get("depth_format") == "Z16" and manifest.get("color_format") == "RGB8", "format mismatch")
    require(manifest.get("pairing") == "sdk_frameset", "unknown pairing method")
    require(manifest.get("exposure_synchronization_verified") is False, "unsupported synchronization claim")
    require(manifest.get("host_clock") == "std_chrono_steady_clock_nanoseconds", "unknown host clock")
    count = manifest.get("frame_count")
    require(integer(count, 1) and count <= 900, "invalid frame count")
    require(finite(manifest.get("depth_scale_meters")) and manifest["depth_scale_meters"] > 0, "invalid depth scale")
    for stream in ("depth", "color"):
        _intrinsics(manifest.get(stream + "_intrinsics"), 848, 480)
    _extrinsics(manifest.get("depth_to_color"))
    rows_bytes = paths["frames.jsonl"].read_bytes()
    lines = rows_bytes.decode("utf-8").splitlines()
    require(len(lines) == count, "frame metadata count mismatch")
    rows = [_json(line) for line in lines]
    offsets = {"depth": 0, "color": 0}
    previous = {"depth": None, "color": None}
    support = {stream: {key: 0 for key in OPTIONAL_METADATA} for stream in offsets}
    gaps = {stream: 0 for stream in offsets}
    domains: dict[str, str] = {}
    deltas: list[float] = []
    host_previous = -1
    for index, row in enumerate(rows):
        require(row.get("schema_version") == "sim2claw.d405_rgbd_frame.v1" and type(row.get("index")) is int and row["index"] == index, "frame row order/schema mismatch")
        host = row.get("host_arrival_steady_ns")
        require(integer(host) and host > host_previous, "host timestamps must increase")
        host_previous = host
        for stream, bpp in (("depth", 16), ("color", 24)):
            f = row.get(stream)
            require(isinstance(f, dict), f"missing {stream} frame")
            require((f.get("width"), f.get("height"), f.get("bits_per_pixel")) == (848, 480, bpp), "frame profile mismatch")
            stride = f.get("stride_bytes")
            require(integer(stride, 848 * (bpp // 8)) and stride <= 848 * (bpp // 8) + 4096, "invalid frame stride")
            require(integer(f.get("offset_bytes")) and f["offset_bytes"] == offsets[stream], "raw offset mismatch")
            require(integer(f.get("bytes")) and f["bytes"] == stride * 480, "frame byte count mismatch")
            offsets[stream] += f["bytes"]
            require(integer(f.get("frame_number")), "invalid frame number")
            require(finite(f.get("device_timestamp_ms")) and f["device_timestamp_ms"] >= 0, "invalid device timestamp")
            domain = f.get("timestamp_domain")
            require(isinstance(domain, str) and bool(domain), "missing clock domain")
            require(domain == domains.setdefault(stream, domain), "clock domain changed during capture")
            old = previous[stream]
            if old is not None:
                require(f["frame_number"] > old["frame_number"], "duplicate or reversed frame number")
                require(f["device_timestamp_ms"] > old["device_timestamp_ms"], "device timestamps must increase")
                gaps[stream] += f["frame_number"] - old["frame_number"] - 1
                if old["frame_counter"] is not None and f.get("frame_counter") is not None:
                    require(f["frame_counter"] > old["frame_counter"], "metadata frame counter must increase")
            for key in OPTIONAL_METADATA:
                require(key in f, f"missing optional-metadata declaration: {key}")
                value = f[key]
                require(value is None or (finite(value) and value >= 0), f"invalid optional metadata: {key}")
                if key == "frame_counter":
                    require(value is None or integer(value), "invalid metadata frame counter")
                support[stream][key] += int(value is not None)
            previous[stream] = f
        if domains["depth"] == domains["color"]:
            deltas.append(row["color"]["device_timestamp_ms"] - row["depth"]["device_timestamp_ms"])
    for stream, name in (("depth", "depth.z16"), ("color", "color.rgb8")):
        require(paths[name].stat().st_size == offsets[stream], f"{stream} raw size mismatch")
    hashes = {name: {"sha256": digest(p), "bytes": p.stat().st_size} for name, p in paths.items()}
    for name, parsed in (("manifest.json", manifest_bytes), ("frames.jsonl", rows_bytes)):
        require(hashes[name]["sha256"] == hashlib.sha256(parsed).hexdigest(), "metadata changed during validation")
    require(before == {name: (p.stat().st_size, p.stat().st_mtime_ns) for name, p in paths.items()}, "capture changed during validation")
    return {
        "schema_version": "sim2claw.d405_rgbd_integrity.v1",
        "status": "STRUCTURALLY_VALID_UNREVIEWED",
        "source_proof_class": manifest["proof_class"],
        "experiment_id": manifest["experiment_id"], "device_serial": manifest["device_serial"],
        "frame_count": count, "artifacts": hashes, "frame_number_gaps": gaps,
        "optional_metadata_available_frames": support, "device_clock_domains": domains,
        "comparable_pair_timestamps": len(deltas),
        "maximum_absolute_pair_timestamp_delta_ms": max(map(abs, deltas)) if deltas else None,
        "depth_scale_meters": manifest["depth_scale_meters"],
        "physical_capture_verified": False, "exposure_synchronization_verified": False,
        "jaw_geometry_verified": False, "calibration_admitted": False,
        "fit_performed": False, "hardware_access_performed": False,
        "missing_for_jaw_calibration": [
            "independent review of capture provenance and current experiment lease",
            "two rigid jaw landmarks with independently measured marker-to-contact-surface geometry",
            "jaw visibility and metric observation quality in fit, validation and stress partitions",
            "bound requested, sent and measured joints plus independent clock association",
            "frozen fit and untouched validation with evaluator-owned identifiability gates",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--expected-serial", required=True)
    parser.add_argument("--expected-experiment", required=True)
    args = parser.parse_args(argv)
    try:
        report = validate_capture(args.directory, expected_serial=args.expected_serial, expected_experiment=args.expected_experiment)
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(json.dumps({"status": "INVALID", "error": str(error)}, sort_keys=True))
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
