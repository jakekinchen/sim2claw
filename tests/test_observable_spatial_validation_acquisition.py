from __future__ import annotations

from sim2claw.observable_spatial_validation_acquisition import (
    build_spatial_validation_acquisition_readiness,
    evaluate_spatial_validation_acquisition,
    load_spatial_validation_acquisition_contract,
)


def test_contract_freezes_four_new_validation_poses_without_authority() -> None:
    contract = load_spatial_validation_acquisition_contract()
    assert len(contract["pose_design"]["targets"]) == 4
    assert contract["pose_design"]["minimum_shoulder_pan_span_degrees"] == 10.0
    assert contract["pose_design"]["minimum_shoulder_lift_span_degrees"] == 3.0
    assert contract["camera_contract"]["d405_depth_required"] is False
    assert contract["role_separation"][
        "all_four_new_targets_are_validation_only"
    ] is True
    assert not any(contract["authority"].values())


def test_readiness_passes_design_and_fails_closed_on_external_inputs() -> None:
    receipt = evaluate_spatial_validation_acquisition(
        load_spatial_validation_acquisition_contract()
    )
    assert receipt["design_ready"] is True
    assert receipt["capture_ready"] is False
    assert receipt["pose_design"]["target_count"] == 4
    assert receipt["pose_design"]["shoulder_pan_span_degrees"] == 20.0
    assert receipt["pose_design"]["shoulder_lift_span_degrees"] == 3.0
    assert receipt["status"] == "BLOCKED_REQUIRED_EXTERNAL_INPUTS"
    assert set(receipt["missing_external_inputs"]) == {
        "follower_elbow_service_receipt",
        "fresh_torque_off_identity_and_limits_receipt",
        "fresh_current_physical_authority_receipt",
        "fresh_cpu_fp64_route_collision_camera_review",
    }
    assert receipt["actions_compiled"] is False
    assert receipt["physical_motion"] is False
    assert receipt["validation_images_opened"] is False


def test_readiness_receipt_is_deterministic(tmp_path) -> None:
    first = build_spatial_validation_acquisition_readiness(
        output_path=tmp_path / "first.json"
    )
    second = build_spatial_validation_acquisition_readiness(
        output_path=tmp_path / "second.json"
    )
    assert first == second
    assert first["artifact_sha256"] == second["artifact_sha256"]
