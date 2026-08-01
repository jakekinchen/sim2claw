from pathlib import Path

from sim2claw.observable_registration_external_metric_pad_surface_packet import (
    CONTRACT_PATH,
    compile_external_metric_manifest,
    load_external_metric_pad_surface_packet_contract,
    run_external_metric_pad_surface_packet_once,
    static_sensor_preflight,
)


def test_contract_reuses_exact_actions_and_denies_execution() -> None:
    contract = load_external_metric_pad_surface_packet_contract()
    assert contract["motion_packet"]["reuse_or43_requested_action_bytes_exactly"] is True
    assert contract["motion_packet"]["physical_execution_allowed_by_this_card"] is False
    assert contract["selected_sensor_route"]["or45_retry"] is False
    assert not any(contract["authority"].values())
    assert not any(contract["claim_limits"].values())


def test_manifest_has_frozen_fit_validation_and_stress_cycles() -> None:
    contract = load_external_metric_pad_surface_packet_contract()
    manifest = compile_external_metric_manifest(contract)
    assert manifest["action_identity"]["row_count"] == 442
    assert manifest["action_identity"]["requested_float64_sha256"] == "3ab970c0bcb5310e9a3939accce09eb281c9daac939e989749655b91ca8f3aa0"
    assert manifest["action_identity"]["action_bytes_changed"] is False
    fit = set(manifest["partition"]["fit_row_indices"])
    validation = set(manifest["partition"]["untouched_validation_row_indices"])
    stress = set(manifest["partition"]["stress_row_indices"])
    assert fit and validation and stress
    assert not (fit & validation or fit & stress or validation & stress)
    assert manifest["partition"]["validation_refit_allowed"] is False


def test_static_preflight_is_fail_closed_without_device_access() -> None:
    contract = load_external_metric_pad_surface_packet_contract()
    preflight = static_sensor_preflight(contract)
    assert preflight["status"] == "BLOCKED_EXTERNAL_METRIC_SENSOR_AND_JAW_MARKERS"
    assert preflight["hardware_access_performed"] is False
    assert preflight["device_enumeration_invoked"] is False
    assert preflight["or45_retry_attempted"] is False
    assert preflight["physical_packet_admitted"] is False
    assert "new_packet_d405_device_presence" in preflight["missing_capabilities"]
    assert "two_jaw_marker_identity_and_metric_geometry_receipt" in preflight["missing_capabilities"]


def test_live_compile_produces_no_motion_or_replay(tmp_path: Path) -> None:
    receipt = run_external_metric_pad_surface_packet_once(
        CONTRACT_PATH, tmp_path / "or48"
    )
    assert receipt["status"] == "PASS_PACKET_COMPILED_BLOCKED_EXTERNAL_METRIC_SENSOR_AND_JAW_MARKERS"
    assert receipt["requested_action_bytes_changed"] is False
    assert receipt["physical_packet_admitted"] is False
    assert receipt["camera_opened"] is False
    assert receipt["serial_opened"] is False
    assert receipt["torque_enabled"] is False
    assert receipt["robot_motion_performed"] is False
    assert receipt["physical_calibration_executed"] is False
    assert receipt["physical_task_attempt"] is False
    assert receipt["simulator_replays_run"] == 0
    assert receipt["global_mapping_approved"] is False
    assert receipt["transfer_claim"] is False
