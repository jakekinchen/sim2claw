"""Compile OR48 without opening a camera, serial bus, or robot gateway."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
)
from .observable_registration_belief_recalculation import REPO_ROOT, _bound_path


SCHEMA = "sim2claw.observable_registration_external_metric_pad_surface_packet_contract.v1"
RECEIPT_SCHEMA = "sim2claw.observable_registration_external_metric_pad_surface_packet_receipt.v1"
MANIFEST_SCHEMA = "sim2claw.or48_external_metric_pad_surface_manifest.v1"
CONTRACT_PATH = (
    REPO_ROOT
    / "configs/evaluations/observable_registration_external_metric_pad_surface_packet_v1.json"
)
OUTPUT_DIRECTORY = (
    REPO_ROOT / "outputs/observable_registration_external_metric_pad_surface_packet_v1"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def load_external_metric_pad_surface_packet_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="OR48 external metric pad packet")
    _require(contract.get("schema_version") == SCHEMA, "unsupported OR48 contract")
    for source_id, binding in contract["sources"].items():
        _bound_path(binding, root=root, label=source_id)
    motion = contract["motion_packet"]
    _require(
        motion["reuse_or43_requested_action_bytes_exactly"] is True
        and motion["row_count"] == 442
        and motion["requested_float64_sha256"]
        == "3ab970c0bcb5310e9a3939accce09eb281c9daac939e989749655b91ca8f3aa0"
        and motion["object_or_pawn_present"] is False
        and motion["zero_non_gripper_joint_motion_required"] is True
        and motion["physical_execution_allowed_by_this_card"] is False,
        "OR48 motion boundary widened",
    )
    route = contract["selected_sensor_route"]
    _require(
        route["route_id"] == "new_d405_rgbd_two_jaw_metric_landmarks"
        and route["new_experiment_id_and_new_lease_required"] is True
        and route["or45_retry"] is False
        and route["raw_depth_preservation_required"] is True
        and route["jaw_marker_identity_and_metric_geometry_receipt_required"] is True,
        "OR48 sensor route changed",
    )
    preflight = contract["static_preflight"]
    _require(
        preflight["may_read_bound_sources"] is True
        and preflight["may_compile_manifest"] is True
        and not any(
            preflight[name]
            for name in (
                "may_enumerate_device",
                "may_open_camera",
                "may_open_serial",
                "may_enable_torque",
                "may_move_robot",
                "may_run_simulator",
            )
        ),
        "OR48 static preflight boundary widened",
    )
    _require(
        not any(contract["claim_limits"].values())
        and not any(contract["authority"].values()),
        "OR48 claim or authority boundary widened",
    )
    return contract


def compile_external_metric_manifest(
    contract: dict[str, Any], *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    packet = load_json_object(
        _bound_path(contract["sources"]["or43_packet"], root=root, label="OR43 packet"),
        label="OR43 packet",
    )
    motion = contract["motion_packet"]
    _require(
        packet["row_count"] == motion["row_count"]
        and packet["duration_seconds"] == motion["duration_seconds"]
        and packet["sample_hz"] == motion["sample_hz"]
        and packet["requested_float64_sha256"] == motion["requested_float64_sha256"],
        "OR43 action identity changed",
    )
    phase_counts = Counter(row["phase"] for row in packet["rows"])
    fit_rows = [
        row
        for row in packet["rows"]
        if row["phase"].startswith(("task_cycle_1_", "task_cycle_2_"))
    ]
    validation_rows = [
        row for row in packet["rows"] if row["phase"].startswith("task_cycle_3_")
    ]
    stress_rows = [
        row for row in packet["rows"] if row["phase"].startswith("wide_cycle_1_")
    ]
    _require(
        fit_rows and validation_rows and stress_rows,
        "OR48 prospective cycle partition is empty",
    )
    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "execution_status": "NOT_EXECUTED_STATIC_COMPILE_ONLY",
        "action_identity": {
            "source_experiment_id": packet["experiment_id"],
            "row_count": packet["row_count"],
            "duration_seconds": packet["duration_seconds"],
            "sample_hz": packet["sample_hz"],
            "requested_float64_sha256": packet["requested_float64_sha256"],
            "action_bytes_changed": False,
        },
        "partition": {
            "fit_row_indices": [row["row_index"] for row in fit_rows],
            "untouched_validation_row_indices": [
                row["row_index"] for row in validation_rows
            ],
            "stress_row_indices": [row["row_index"] for row in stress_rows],
            "validation_refit_allowed": False,
        },
        "phase_counts": dict(sorted(phase_counts.items())),
        "sensor_route": contract["selected_sensor_route"],
        "fit_and_admission_gates": contract["fit_and_admission_gates"],
        "pawn_or_task_outcome_available": False,
    }
    manifest["artifact_sha256"] = canonical_digest(manifest)
    return manifest


def static_sensor_preflight(contract: dict[str, Any]) -> dict[str, Any]:
    facts = contract["current_preflight_facts"]
    route_ready = all(
        (
            facts["d405_matching_device_found_at_or45"],
            facts["d405_stream_started_at_or45"],
            facts["metric_frames_currently_available_for_new_packet"] > 0,
            facts["jaw_marker_identity_and_metric_geometry_receipt_present"],
            facts["both_load_side_surfaces_currently_verified_visible"],
        )
    )
    missing = []
    if not facts["d405_matching_device_found_at_or45"]:
        missing.append("new_packet_d405_device_presence")
    if not facts["d405_stream_started_at_or45"]:
        missing.append("new_packet_synchronized_rgbd_stream")
    if facts["metric_frames_currently_available_for_new_packet"] <= 0:
        missing.append("new_packet_metric_frames")
    if not facts["jaw_marker_identity_and_metric_geometry_receipt_present"]:
        missing.append("two_jaw_marker_identity_and_metric_geometry_receipt")
    if not facts["both_load_side_surfaces_currently_verified_visible"]:
        missing.append("both_load_side_surfaces_visible_in_all_partitions")
    return {
        "schema_version": "sim2claw.or48_static_sensor_preflight.v1",
        "hardware_access_performed": False,
        "device_enumeration_invoked": False,
        "camera_opened": False,
        "serial_opened": False,
        "torque_enabled": False,
        "robot_motion_performed": False,
        "simulator_run": False,
        "or45_retry_attempted": False,
        "new_sensor_route_ready": route_ready,
        "physical_packet_admitted": False,
        "missing_capabilities": missing,
        "status": (
            "PASS_STATIC_SENSOR_PREFLIGHT"
            if route_ready
            else "BLOCKED_EXTERNAL_METRIC_SENSOR_AND_JAW_MARKERS"
        ),
    }


def run_external_metric_pad_surface_packet_once(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
) -> dict[str, Any]:
    contract = load_external_metric_pad_surface_packet_contract(contract_path)
    output_directory.mkdir(parents=True, exist_ok=False)
    manifest = compile_external_metric_manifest(contract)
    manifest_path = output_directory / "packet_manifest.json"
    atomic_write_json(manifest_path, manifest)
    preflight = static_sensor_preflight(contract)
    preflight_path = output_directory / "sensor_preflight.json"
    atomic_write_json(preflight_path, preflight)
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "proof_class": contract["proof_class"],
        "status": (
            "PASS_PACKET_COMPILED_READY_FOR_SEPARATE_CAPABILITY_REVIEW"
            if preflight["new_sensor_route_ready"]
            else "PASS_PACKET_COMPILED_BLOCKED_EXTERNAL_METRIC_SENSOR_AND_JAW_MARKERS"
        ),
        "source_bindings": contract["sources"],
        "packet_manifest": {
            "path": manifest_path.name,
            "artifact_sha256": manifest["artifact_sha256"],
        },
        "sensor_preflight": {"path": preflight_path.name, **preflight},
        "requested_action_bytes_changed": False,
        "physical_packet_admitted": False,
        "camera_opened": False,
        "serial_opened": False,
        "torque_enabled": False,
        "robot_motion_performed": False,
        "physical_calibration_executed": False,
        "physical_task_attempt": False,
        "simulator_replays_run": 0,
        "global_mapping_approved": False,
        "simulator_promoted": False,
        "transfer_claim": False,
        "authority": contract["authority"],
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(output_directory / "receipt.json", receipt)
    return receipt


def main() -> int:
    run_external_metric_pad_surface_packet_once()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
