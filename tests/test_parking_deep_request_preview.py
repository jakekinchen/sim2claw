from __future__ import annotations

from sim2claw.parking_deep_request_preview import (
    _contact_envelope_passes,
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
    assert not _contact_envelope_passes(
        angle_degrees=103.5,
        contacts={
            ("left_lower_arm", "left_shoulder"): -0.0093,
        },
        live_anchor_contacts=BASELINE,
        contact_free_maximum_degrees=99.6,
        maximum_additional_penetration_m=0.0005,
    )
