"""Compile OR43 without opening a camera, serial bus, or robot gateway."""

from __future__ import annotations

import hashlib
import importlib.util
import shutil
from pathlib import Path
from typing import Any

import numpy as np

from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
)
from .observable_registration_belief_recalculation import (
    REPO_ROOT,
    _bound_path,
)


SCHEMA = (
    "sim2claw."
    "observable_registration_load_side_gripper_calibration_contract.v1"
)
RECEIPT_SCHEMA = (
    "sim2claw."
    "observable_registration_load_side_gripper_calibration_receipt.v1"
)
CONTRACT_PATH = (
    REPO_ROOT
    / "configs/evaluations/"
    "observable_registration_load_side_gripper_calibration_v1.json"
)
OUTPUT_DIRECTORY = (
    REPO_ROOT
    / "outputs/observable_registration_load_side_gripper_calibration_v1"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def load_load_side_gripper_calibration_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="OR43 load-side calibration")
    _require(contract.get("schema_version") == SCHEMA, "unsupported contract")
    for source_id, binding in contract["sources"].items():
        _bound_path(binding, root=root, label=source_id)
    packet = contract["packet"]
    _require(
        packet["robot_role"] == "follower"
        and packet["joint"] == "gripper"
        and packet["object_present"] is False
        and packet["task_interval_repetitions"] >= 3
        and packet["requested_sent_measured_traces_required"] is True
        and packet["host_timestamps_required"] is True
        and packet["actuator_ack_timestamp_claim_allowed"] is False
        and packet["zero_other_joint_motion_required"] is True,
        "OR43 packet boundary widened",
    )
    observation = contract["observation"]
    _require(
        observation["independent_load_side_metric_observation_required"]
        is True
        and observation["d405_device_timestamp_required"] is True
        and observation["d405_exposure_metadata_required"] is True
        and observation["d405_frame_counter_required"] is True
        and observation["rgb_only_claims_metric_aperture"] is False
        and observation[
            "servo_encoder_is_independent_load_side_observation"
        ]
        is False,
        "OR43 observation boundary widened",
    )
    preflight = contract["static_preflight"]
    _require(
        preflight["may_check_executable_presence"] is True
        and preflight["may_check_python_module_presence"] is True
        and preflight["may_read_bound_source_capabilities"] is True
        and not any(
            preflight[name]
            for name in (
                "may_invoke_realsense_device_enumeration",
                "may_open_camera",
                "may_open_serial",
                "may_enable_torque",
                "may_move_robot",
                "may_run_simulator_replay",
            )
        ),
        "OR43 static preflight boundary widened",
    )
    _require(
        not any(contract["claim_limits"].values()),
        "OR43 claim boundary widened",
    )
    _require(
        not any(contract["authority"].values()),
        "OR43 authority boundary widened",
    )
    return contract


def _dwell(
    value: float,
    *,
    seconds: float,
    sample_hz: float,
    phase: str,
) -> list[dict[str, Any]]:
    count = int(round(seconds * sample_hz))
    return [
        {"requested_gripper_degrees": value, "phase": phase}
        for _ in range(count)
    ]


def _ramp(
    start: float,
    stop: float,
    *,
    sample_hz: float,
    maximum_slew: float,
    phase: str,
) -> list[dict[str, Any]]:
    duration = abs(stop - start) / maximum_slew
    step_count = max(1, int(np.ceil(duration * sample_hz)))
    values = np.linspace(start, stop, step_count + 1, dtype=np.float64)[1:]
    return [
        {
            "requested_gripper_degrees": float(value),
            "phase": phase,
        }
        for value in values
    ]


def compile_calibration_packet(
    contract: dict[str, Any],
) -> dict[str, Any]:
    spec = contract["packet"]
    sample_hz = float(spec["sample_hz"])
    maximum_slew = float(spec["maximum_slew_degrees_per_second"])
    dwell_seconds = float(spec["dwell_seconds_at_reversal"])
    task_low, task_high = [
        float(value) for value in spec["task_interval_degrees"]
    ]
    wide_low, wide_high = [
        float(value) for value in spec["wide_diagnostic_interval_degrees"]
    ]
    rows: list[dict[str, Any]] = []
    rows.extend(
        _dwell(
            task_low,
            seconds=dwell_seconds,
            sample_hz=sample_hz,
            phase="initial_low_dwell",
        )
    )
    for cycle in range(int(spec["task_interval_repetitions"])):
        rows.extend(
            _ramp(
                task_low,
                task_high,
                sample_hz=sample_hz,
                maximum_slew=maximum_slew,
                phase=f"task_cycle_{cycle + 1}_opening",
            )
        )
        rows.extend(
            _dwell(
                task_high,
                seconds=dwell_seconds,
                sample_hz=sample_hz,
                phase=f"task_cycle_{cycle + 1}_high_dwell",
            )
        )
        rows.extend(
            _ramp(
                task_high,
                task_low,
                sample_hz=sample_hz,
                maximum_slew=maximum_slew,
                phase=f"task_cycle_{cycle + 1}_closing",
            )
        )
        rows.extend(
            _dwell(
                task_low,
                seconds=dwell_seconds,
                sample_hz=sample_hz,
                phase=f"task_cycle_{cycle + 1}_low_dwell",
            )
        )
    for cycle in range(int(spec["wide_diagnostic_repetitions"])):
        rows.extend(
            _ramp(
                wide_low,
                wide_high,
                sample_hz=sample_hz,
                maximum_slew=maximum_slew,
                phase=f"wide_cycle_{cycle + 1}_opening",
            )
        )
        rows.extend(
            _dwell(
                wide_high,
                seconds=dwell_seconds,
                sample_hz=sample_hz,
                phase=f"wide_cycle_{cycle + 1}_high_dwell",
            )
        )
        rows.extend(
            _ramp(
                wide_high,
                wide_low,
                sample_hz=sample_hz,
                maximum_slew=maximum_slew,
                phase=f"wide_cycle_{cycle + 1}_closing",
            )
        )
        rows.extend(
            _dwell(
                wide_low,
                seconds=dwell_seconds,
                sample_hz=sample_hz,
                phase=f"wide_cycle_{cycle + 1}_final_dwell",
            )
        )
    values = np.asarray(
        [float(row["requested_gripper_degrees"]) for row in rows],
        dtype="<f8",
    )
    timestamps = np.arange(len(rows), dtype=np.float64) / sample_hz
    for index, row in enumerate(rows):
        row["row_index"] = index
        row["relative_time_seconds"] = float(timestamps[index])
        row["sent_gripper_degrees"] = None
        row["measured_gripper_degrees"] = None
        row["host_send_started_monotonic_seconds"] = None
        row["host_send_completed_monotonic_seconds"] = None
        row["host_measurement_monotonic_seconds"] = None
    increments = np.abs(np.diff(values))
    maximum_observed_slew = (
        float(np.max(increments) * sample_hz) if len(increments) else 0.0
    )
    return {
        "schema_version": "sim2claw.or43_gripper_calibration_packet.v1",
        "experiment_id": contract["experiment_id"],
        "execution_status": "NOT_EXECUTED_STATIC_COMPILE_ONLY",
        "sample_hz": sample_hz,
        "row_count": len(rows),
        "duration_seconds": float(len(rows) / sample_hz),
        "requested_float64_sha256": hashlib.sha256(
            values.tobytes(order="C")
        ).hexdigest(),
        "maximum_compiled_slew_degrees_per_second": maximum_observed_slew,
        "zero_other_joint_motion_required": True,
        "requested_sent_measured_schema_complete": all(
            {
                "sent_gripper_degrees",
                "measured_gripper_degrees",
                "host_send_started_monotonic_seconds",
                "host_send_completed_monotonic_seconds",
                "host_measurement_monotonic_seconds",
            }.issubset(row)
            for row in rows
        ),
        "rows": rows,
    }


def static_capability_preflight(
    contract: dict[str, Any],
    *,
    capability_override: dict[str, bool] | None = None,
) -> dict[str, Any]:
    facts = contract["current_capture_stack_facts"]
    observed = {
        "rs_enumerate_devices_executable_present": bool(
            shutil.which("rs-enumerate-devices")
        ),
        "pyrealsense2_module_present": (
            importlib.util.find_spec("pyrealsense2") is not None
        ),
        "native_dual_camera_retains_rgb": bool(
            facts["native_dual_camera_retains_rgb"]
        ),
        "native_dual_camera_retains_metric_depth": bool(
            facts["native_dual_camera_retains_metric_depth"]
        ),
        "native_dual_camera_retains_device_timestamp": bool(
            facts["native_dual_camera_retains_device_timestamp"]
        ),
        "native_dual_camera_retains_exposure_metadata": bool(
            facts["native_dual_camera_retains_exposure_metadata"]
        ),
        "native_dual_camera_retains_frame_counter": bool(
            facts["native_dual_camera_retains_frame_counter"]
        ),
        "configured_metric_fiducial_lane": bool(
            facts["configured_metric_fiducial_lane"]
        ),
        "configured_secondary_encoder_lane": bool(
            facts["configured_secondary_encoder_lane"]
        ),
    }
    if capability_override is not None:
        _require(
            set(capability_override).issubset(observed),
            "unknown OR43 capability override",
        )
        observed.update(capability_override)
    depth_lane = all(
        observed[name]
        for name in (
            "native_dual_camera_retains_metric_depth",
            "native_dual_camera_retains_device_timestamp",
            "native_dual_camera_retains_exposure_metadata",
            "native_dual_camera_retains_frame_counter",
        )
    )
    fiducial_lane = observed["configured_metric_fiducial_lane"]
    encoder_lane = observed["configured_secondary_encoder_lane"]
    independent_metric_lane = depth_lane or fiducial_lane or encoder_lane
    missing = []
    if not depth_lane:
        missing.append(
            "integrated_d405_metric_depth_with_device_timestamp_exposure_and_"
            "frame_counter"
        )
    if not fiducial_lane:
        missing.append("configured_two_jaw_metric_fiducial_lane")
    if not encoder_lane:
        missing.append("configured_secondary_load_side_displacement_lane")
    return {
        "schema_version": "sim2claw.or43_static_capability_preflight.v1",
        "hardware_access_performed": False,
        "camera_opened": False,
        "serial_opened": False,
        "torque_enabled": False,
        "robot_motion_performed": False,
        "realsense_device_enumeration_invoked": False,
        "observed_capabilities": observed,
        "d405_metric_lane_ready": depth_lane,
        "fiducial_metric_lane_ready": fiducial_lane,
        "secondary_encoder_lane_ready": encoder_lane,
        "independent_metric_load_side_observation_ready": (
            independent_metric_lane
        ),
        "missing_capabilities": missing,
        "physical_packet_admitted": independent_metric_lane,
        "status": (
            "PASS_STATIC_CAPABILITY_PREFLIGHT"
            if independent_metric_lane
            else "BLOCKED_INDEPENDENT_METRIC_LOAD_SIDE_OBSERVATION"
        ),
    }


def run_load_side_gripper_calibration_preflight_once(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    _require(not receipt_path.exists(), "OR43 one-run receipt already exists")
    contract = load_load_side_gripper_calibration_contract(
        contract_path, root=root
    )
    packet = compile_calibration_packet(contract)
    _require(
        packet["maximum_compiled_slew_degrees_per_second"]
        <= float(contract["packet"]["maximum_slew_degrees_per_second"])
        + 1e-12,
        "OR43 packet exceeds its slew bound",
    )
    capability = static_capability_preflight(contract)
    output_directory.mkdir(parents=True, exist_ok=False)
    packet_path = output_directory / "packet.json"
    capability_path = output_directory / "capability_preflight.json"
    atomic_write_json(packet_path, packet)
    atomic_write_json(capability_path, capability)
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "proof_class": contract["proof_class"],
        "status": (
            "PASS_PACKET_COMPILED_PHYSICAL_AUTHORITY_FALSE"
            if capability["physical_packet_admitted"]
            else "PASS_PACKET_COMPILED_BLOCKED_METRIC_LOAD_SIDE_SENSOR"
        ),
        "source_bindings": contract["sources"],
        "packet": {
            "path": packet_path.name,
            "row_count": packet["row_count"],
            "duration_seconds": packet["duration_seconds"],
            "requested_float64_sha256": packet[
                "requested_float64_sha256"
            ],
            "maximum_compiled_slew_degrees_per_second": packet[
                "maximum_compiled_slew_degrees_per_second"
            ],
            "execution_status": packet["execution_status"],
        },
        "capability_preflight": {
            "path": capability_path.name,
            **capability,
        },
        "physical_packet_admitted": False,
        "physical_authority": False,
        "camera_opened": False,
        "serial_opened": False,
        "torque_enabled": False,
        "robot_motion_performed": False,
        "physical_task_attempts": 0,
        "simulator_replays": 0,
        "metric_gripper_mapping_acquired": False,
        "global_mapping_approved": False,
        "transfer_claim": False,
        "authority": contract["authority"],
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


def main() -> int:
    run_load_side_gripper_calibration_preflight_once()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
