#!/usr/bin/env python3
"""Build the new RGBD recorder and exercise only pre-camera argument paths."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="new, empty build directory")
    parser.add_argument("--sdk-prefix", type=Path, default=Path("/opt/homebrew/opt/librealsense"))
    args = parser.parse_args()
    compiler = shutil.which("clang++")
    if not compiler:
        parser.error("clang++ is unavailable")
    if not (args.sdk_prefix / "include/librealsense2/rs.hpp").is_file():
        parser.error("librealsense headers are unavailable")
    output = args.output.absolute()
    output.mkdir(parents=True, exist_ok=False)
    source = ROOT / "tools/macos/RealSenseD405RGBDRecorder.cpp"
    binary = output / "RealSenseD405RGBDRecorder"
    lib = args.sdk_prefix / "lib"
    command = [compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror", str(source),
               "-isystem", str(args.sdk_prefix / "include"), "-L" + str(lib),
               "-Wl,-rpath," + str(lib), "-lrealsense2", "-o", str(binary)]
    subprocess.run(command, check=True, timeout=90)
    common = ["--capture", "--serial", "software-test", "--experiment-id", "software-test"]
    # Every negative case must reject in parse(), before creating an SDK context.
    cases = [(["--help"], 0, "returns before device enumeration"),
             ([], 2, "capture is disabled"),
             (common, 2, "explicit experiment-id"),
             (common + ["--output-dir", str(output)], 2, "already exists"),
             (common + ["--output-dir", str(output / "never-created"), "--frames", "901"], 2, "between 1 and 900"),
             (common + ["--output-dir", str(output / "never-created"), "--frames", "1x"], 2, "invalid frame count")]
    results = []
    for arguments, expected, token in cases:
        result = subprocess.run([str(binary), *arguments], text=True, capture_output=True, timeout=10)
        if result.returncode != expected or token not in result.stdout + result.stderr:
            raise RuntimeError(f"pre-camera smoke check failed: {arguments}: {result}")
        results.append({"arguments": arguments, "returncode": result.returncode,
                        "stdout": result.stdout, "stderr": result.stderr})
    if (output / "never-created").exists():
        raise RuntimeError("negative option check unexpectedly created capture output")
    receipt = {"schema_version": "sim2claw.rgbd_recorder_build.v1", "status": "PASS_BUILD_AND_PRE_CAMERA_SMOKE",
               "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
               "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
               "command": command, "checks": results, "hardware_access_performed": False,
               "physical_capture_verified": False, "jaw_calibration_admitted": False}
    (output / "build-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"status": receipt["status"], "checks": len(results), "receipt": str(output / "build-receipt.json")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
