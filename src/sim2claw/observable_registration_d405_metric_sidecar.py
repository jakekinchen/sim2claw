"""Build and inspect OR44 without enumerating or opening a camera."""

from __future__ import annotations

import hashlib
import shutil
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


SCHEMA = "sim2claw.observable_registration_d405_metric_sidecar_contract.v1"
RECEIPT_SCHEMA = (
    "sim2claw.observable_registration_d405_metric_sidecar_receipt.v1"
)
CONTRACT_PATH = (
    REPO_ROOT
    / "configs/evaluations/observable_registration_d405_metric_sidecar_v1.json"
)
OUTPUT_DIRECTORY = (
    REPO_ROOT / "outputs/observable_registration_d405_metric_sidecar_v1"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_d405_metric_sidecar_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="OR44 D405 metric sidecar")
    _require(contract.get("schema_version") == SCHEMA, "unsupported contract")
    for source_id, binding in contract["sources"].items():
        _bound_path(binding, root=root, label=source_id)
    source_path = root / contract["native_source"]
    _require(source_path.is_file(), "OR44 native source is missing")
    capture = contract["capture_contract"]
    _require(
        capture["device_family"] == "Intel RealSense D405"
        and capture["format"] == "Z16"
        and capture["depth_scale_required"] is True
        and capture["intrinsics_required"] is True
        and capture["sensor_timestamp_and_domain_required"] is True
        and capture["host_steady_arrival_required"] is True
        and capture["frame_number_required"] is True,
        "OR44 capture boundary widened",
    )
    _require(
        all(contract["forbidden_during_or44"].values()),
        "OR44 forbidden-operation boundary weakened",
    )
    _require(not any(contract["claim_limits"].values()), "OR44 claim widened")
    _require(not any(contract["authority"].values()), "OR44 authority widened")
    return contract


def _verify_help_precedes_hardware_access(source_text: str) -> None:
    help_index = source_text.find("if (options.help)")
    context_index = source_text.find("rs2::context context")
    pipeline_index = source_text.find("rs2::pipeline pipeline")
    _require(help_index >= 0, "OR44 help branch is missing")
    _require(context_index >= 0, "OR44 context boundary is missing")
    _require(pipeline_index >= 0, "OR44 pipeline boundary is missing")
    _require(
        help_index < context_index < pipeline_index,
        "OR44 help no longer precedes hardware access",
    )


def compile_and_smoke_test_sidecar(
    contract: dict[str, Any],
    output_directory: Path,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    build = contract["build"]
    compiler = shutil.which(build["compiler"])
    _require(compiler is not None, "OR44 compiler is unavailable")
    include_directory = Path(build["include_directory"])
    library_directory = Path(build["library_directory"])
    _require(
        (include_directory / "librealsense2/rs.hpp").is_file(),
        "OR44 librealsense headers are unavailable",
    )
    _require(
        (library_directory / "librealsense2.dylib").is_file(),
        "OR44 librealsense library is unavailable",
    )
    source_path = root / contract["native_source"]
    source_text = source_path.read_text(encoding="utf-8")
    _verify_help_precedes_hardware_access(source_text)
    output_directory.mkdir(parents=True, exist_ok=False)
    binary_path = output_directory / "RealSenseD405MetricRecorder"
    command = [
        compiler,
        f"-std={build['cpp_standard']}",
        "-O2",
        "-Wall",
        "-Wextra",
        str(source_path),
        f"-I{include_directory}",
        f"-L{library_directory}",
        f"-Wl,-rpath,{library_directory}",
        f"-l{build['library']}",
        "-o",
        str(binary_path),
    ]
    compile_result = subprocess.run(
        command, check=False, capture_output=True, text=True
    )
    _require(
        compile_result.returncode == 0,
        f"OR44 compile failed: {compile_result.stderr.strip()}",
    )
    help_result = subprocess.run(
        [str(binary_path), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    _require(
        help_result.returncode == contract["static_acceptance"]["help_exit_code"],
        "OR44 help smoke test failed",
    )
    missing_tokens = [
        token
        for token in contract["static_acceptance"][
            "help_schema_tokens_required"
        ]
        if token not in help_result.stdout
    ]
    _require(not missing_tokens, f"OR44 help is missing {missing_tokens}")
    help_path = output_directory / "help.txt"
    help_path.write_text(help_result.stdout, encoding="utf-8")
    return {
        "schema_version": "sim2claw.or44_d405_metric_sidecar_build.v1",
        "status": "PASS_COMPILED_AND_LINKED_HELP_ONLY",
        "compiler": compiler,
        "binary": binary_path.name,
        "binary_sha256": _sha256(binary_path),
        "native_source_sha256": _sha256(source_path),
        "help": help_path.name,
        "help_sha256": _sha256(help_path),
        "compile_exit_code": compile_result.returncode,
        "help_exit_code": help_result.returncode,
        "help_precedes_context_creation": True,
        "librealsense_header_present": True,
        "librealsense_library_present": True,
        "device_enumeration_performed": False,
        "camera_opened": False,
        "stream_started": False,
        "serial_opened": False,
        "torque_enabled": False,
        "robot_motion_performed": False,
        "physical_task_attempts": 0,
        "simulator_replays": 0,
    }


def run_d405_metric_sidecar_build_once(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    _require(not receipt_path.exists(), "OR44 one-run receipt already exists")
    contract = load_d405_metric_sidecar_contract(contract_path, root=root)
    build = compile_and_smoke_test_sidecar(
        contract, output_directory, root=root
    )
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "proof_class": contract["proof_class"],
        "status": "PASS_COMPILED_D405_METRIC_SIDECAR_NO_DEVICE_ACCESS",
        "source_bindings": contract["sources"],
        "build": build,
        "capture_schema": contract["capture_contract"],
        "hardware_used": False,
        "d405_device_presence_checked": False,
        "metric_depth_captured": False,
        "load_side_gripper_mapping_acquired": False,
        "physical_calibration_executed": False,
        "global_mapping_approved": False,
        "physical_task_attempts": 0,
        "simulator_replays": 0,
        "transfer_claim": False,
        "authority": contract["authority"],
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


def main() -> int:
    run_d405_metric_sidecar_build_once()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
