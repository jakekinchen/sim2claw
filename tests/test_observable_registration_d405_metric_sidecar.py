from pathlib import Path

from sim2claw.observable_registration_d405_metric_sidecar import (
    CONTRACT_PATH,
    compile_and_smoke_test_sidecar,
    load_d405_metric_sidecar_contract,
    run_d405_metric_sidecar_build_once,
)


def test_contract_requires_metric_depth_metadata_and_zero_authority() -> None:
    contract = load_d405_metric_sidecar_contract()
    capture = contract["capture_contract"]
    assert capture["device_family"] == "Intel RealSense D405"
    assert capture["format"] == "Z16"
    assert capture["depth_scale_required"] is True
    assert capture["intrinsics_required"] is True
    assert capture["sensor_timestamp_and_domain_required"] is True
    assert capture["host_steady_arrival_required"] is True
    assert capture["frame_number_required"] is True
    assert all(contract["forbidden_during_or44"].values())
    assert not any(contract["authority"].values())


def test_native_help_branch_precedes_hardware_access() -> None:
    contract = load_d405_metric_sidecar_contract()
    source = Path(contract["native_source"]).read_text(encoding="utf-8")
    assert source.index("if (options.help)") < source.index(
        "rs2::context context"
    )
    assert source.index("rs2::context context") < source.index(
        "rs2::pipeline pipeline"
    )


def test_sidecar_compiles_links_and_help_never_opens_device(
    tmp_path: Path,
) -> None:
    contract = load_d405_metric_sidecar_contract()
    build = compile_and_smoke_test_sidecar(contract, tmp_path / "build")
    assert build["status"] == "PASS_COMPILED_AND_LINKED_HELP_ONLY"
    assert build["help_exit_code"] == 0
    assert build["help_precedes_context_creation"] is True
    assert build["device_enumeration_performed"] is False
    assert build["camera_opened"] is False
    assert build["stream_started"] is False
    assert build["robot_motion_performed"] is False


def test_live_build_receipt_remains_hardware_unopened(tmp_path: Path) -> None:
    receipt = run_d405_metric_sidecar_build_once(
        CONTRACT_PATH, tmp_path / "or44"
    )
    assert (
        receipt["status"]
        == "PASS_COMPILED_D405_METRIC_SIDECAR_NO_DEVICE_ACCESS"
    )
    assert receipt["hardware_used"] is False
    assert receipt["d405_device_presence_checked"] is False
    assert receipt["metric_depth_captured"] is False
    assert receipt["load_side_gripper_mapping_acquired"] is False
    assert receipt["physical_task_attempts"] == 0
    assert receipt["simulator_replays"] == 0
    assert receipt["transfer_claim"] is False
