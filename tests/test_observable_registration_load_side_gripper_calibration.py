from pathlib import Path

from sim2claw.observable_registration_load_side_gripper_calibration import (
    CONTRACT_PATH,
    compile_calibration_packet,
    load_load_side_gripper_calibration_contract,
    run_load_side_gripper_calibration_preflight_once,
    static_capability_preflight,
)


def test_contract_requires_independent_metric_observation_and_no_motion() -> None:
    contract = load_load_side_gripper_calibration_contract()
    assert contract["packet"]["object_present"] is False
    assert contract["packet"]["task_interval_repetitions"] == 3
    assert (
        contract["observation"][
            "independent_load_side_metric_observation_required"
        ]
        is True
    )
    assert contract["observation"]["rgb_only_claims_metric_aperture"] is False
    assert contract["static_preflight"]["may_open_camera"] is False
    assert contract["static_preflight"]["may_open_serial"] is False
    assert contract["static_preflight"]["may_move_robot"] is False
    assert not any(contract["authority"].values())


def test_packet_is_deterministic_bounded_and_unexecuted() -> None:
    contract = load_load_side_gripper_calibration_contract()
    first = compile_calibration_packet(contract)
    second = compile_calibration_packet(contract)
    assert first == second
    assert first["execution_status"] == "NOT_EXECUTED_STATIC_COMPILE_ONLY"
    assert first["requested_sent_measured_schema_complete"] is True
    assert first["maximum_compiled_slew_degrees_per_second"] <= 15.0
    assert first["row_count"] > 0
    phases = {row["phase"] for row in first["rows"]}
    assert "task_cycle_3_opening" in phases
    assert "task_cycle_3_closing" in phases
    assert "wide_cycle_1_opening" in phases
    assert all(row["sent_gripper_degrees"] is None for row in first["rows"])
    assert all(row["measured_gripper_degrees"] is None for row in first["rows"])


def test_capability_preflight_never_touches_hardware() -> None:
    contract = load_load_side_gripper_calibration_contract()
    report = static_capability_preflight(contract)
    assert report["hardware_access_performed"] is False
    assert report["camera_opened"] is False
    assert report["serial_opened"] is False
    assert report["torque_enabled"] is False
    assert report["robot_motion_performed"] is False
    assert report["realsense_device_enumeration_invoked"] is False
    assert report["physical_packet_admitted"] is False
    assert (
        report["status"]
        == "BLOCKED_INDEPENDENT_METRIC_LOAD_SIDE_OBSERVATION"
    )


def test_synthetic_metric_depth_capability_can_pass_static_gate() -> None:
    contract = load_load_side_gripper_calibration_contract()
    report = static_capability_preflight(
        contract,
        capability_override={
            "native_dual_camera_retains_metric_depth": True,
            "native_dual_camera_retains_device_timestamp": True,
            "native_dual_camera_retains_exposure_metadata": True,
            "native_dual_camera_retains_frame_counter": True,
        },
    )
    assert report["d405_metric_lane_ready"] is True
    assert report["physical_packet_admitted"] is True
    assert report["status"] == "PASS_STATIC_CAPABILITY_PREFLIGHT"
    assert report["hardware_access_performed"] is False


def test_live_preflight_compiles_packet_but_keeps_authority_false(
    tmp_path: Path,
) -> None:
    receipt = run_load_side_gripper_calibration_preflight_once(
        CONTRACT_PATH,
        tmp_path / "or43",
    )
    assert (
        receipt["status"]
        == "PASS_PACKET_COMPILED_BLOCKED_METRIC_LOAD_SIDE_SENSOR"
    )
    assert receipt["packet"]["execution_status"] == (
        "NOT_EXECUTED_STATIC_COMPILE_ONLY"
    )
    assert receipt["physical_packet_admitted"] is False
    assert receipt["physical_authority"] is False
    assert receipt["camera_opened"] is False
    assert receipt["robot_motion_performed"] is False
    assert receipt["physical_task_attempts"] == 0
    assert receipt["simulator_replays"] == 0
