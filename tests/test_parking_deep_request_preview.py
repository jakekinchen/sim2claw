from __future__ import annotations

from sim2claw.parking_deep_request_preview import (
    _contact_envelope_passes,
    _validate,
)


BASELINE = {
    ("left_lower_arm", "left_shoulder"): -0.0087,
    ("left_shoulder", "left_wrist"): -0.0056,
}


def test_contact_free_segment_rejects_any_contact() -> None:
    assert _contact_envelope_passes(
        angle_degrees=99.6,
        contacts={},
        live_anchor_contacts=BASELINE,
        contact_free_maximum_degrees=99.6,
        maximum_additional_penetration_m=0.0005,
    )
    assert not _contact_envelope_passes(
        angle_degrees=99.6,
        contacts={("left_lower_arm", "left_shoulder"): -0.0001},
        live_anchor_contacts=BASELINE,
        contact_free_maximum_degrees=99.6,
        maximum_additional_penetration_m=0.0005,
    )


def test_live_anchor_segment_allows_only_bounded_baseline_pairs() -> None:
    assert _contact_envelope_passes(
        angle_degrees=103.5,
        contacts={
            ("left_lower_arm", "left_shoulder"): -0.0089,
            ("left_shoulder", "left_wrist"): -0.0057,
        },
        live_anchor_contacts=BASELINE,
        contact_free_maximum_degrees=99.6,
        maximum_additional_penetration_m=0.0005,
    )
    assert not _contact_envelope_passes(
        angle_degrees=103.5,
        contacts={("left_gripper", "left_shoulder"): -0.0001},
        live_anchor_contacts=BASELINE,
        contact_free_maximum_degrees=99.6,
        maximum_additional_penetration_m=0.0005,
    )


def test_v2_preview_stops_inside_calibrated_command_range() -> None:
    contract = {
        "schema_version": "sim2claw.parking_deep_request_preview.v2",
        "status": "frozen_for_one_motion_free_cpu_fp64_preview",
        "authority": {
            "model_loading": True,
            "static_simulation": True,
            "camera": False,
            "gateway": False,
            "serial": False,
            "torque": False,
            "physical_motion": False,
            "physical_task_attempt": False,
            "mapping_approval": False,
            "simulator_promotion": False,
            "transfer_claim": False,
        },
        "static_preview": {
            "engine": "mujoco",
            "numeric_mode": "cpu_float64",
            "elbow_interval_degrees": [80.0, 102.1],
            "sample_increment_degrees": 0.1,
            "expected_sample_count": 222,
            "strict_contact_free_maximum_degrees": 99.6,
            "live_anchor_contact_maximum_additional_penetration_m": 0.0005,
            "minimum_dynamic_clearance_m": 0.12,
        },
    }
    _validate(contract)
    assert not _contact_envelope_passes(
        angle_degrees=103.5,
        contacts={
            ("left_lower_arm", "left_shoulder"): -0.0093,
        },
        live_anchor_contacts=BASELINE,
        contact_free_maximum_degrees=99.6,
        maximum_additional_penetration_m=0.0005,
    )
