from __future__ import annotations

from sim2claw.observable_registration_footage_enclosure_audit import (
    load_footage_enclosure_audit_contract,
    run_footage_enclosure_audit_once,
)


def test_contract_freezes_footage_only_no_refit_boundary() -> None:
    contract = load_footage_enclosure_audit_contract()

    assert contract["footage_policy"][
        "physical_definite_carry_interval_samples_inclusive"
    ] == [260, 390]
    assert contract["footage_policy"]["annotation_pass_fields"] == [
        "pass_a_xy",
        "pass_b_xy",
    ]
    assert contract["footage_policy"]["reannotation_allowed"] is False
    assert contract["closed_command_hold"][
        "stability_threshold_or_parameter_fit_allowed"
    ] is False
    assert not any(contract["claim_limits"].values())
    assert not any(contract["authority"].values())
    assert contract["execution"] == {
        "new_annotations_allowed": 0,
        "simulator_replays_allowed": 0,
        "new_candidates_allowed": 0,
        "parameter_changes_allowed": 0,
        "hardware_actions_allowed": 0,
        "heldout_open_allowed": False,
    }


def test_footage_establishes_persistent_enclosure_proxy(tmp_path) -> None:
    receipt = run_footage_enclosure_audit_once(
        output_directory=tmp_path / "or52"
    )

    assert receipt["status"] == (
        "PASS_FOOTAGE_ONLY_PERSISTENT_ENCLOSURE_PROXY_SIMULATOR_"
        "BILATERAL_CONTACT_ABSENT"
    )
    audit = receipt["physical_footage_audit"]
    assert audit["coaccepted_carry_row_count"] == 10
    assert audit["coaccepted_carry_sample_span"] == 100
    assert audit["closed_command_hold_interval_samples_inclusive"] == [241, 327]
    assert audit["closed_command_hold_sample_indices"] == [290, 300, 310, 320]
    assert all(audit["gates"].values())
    assert audit["persistent_image_plane_enclosure_proxy"] is True
    assert audit["bilateral_physical_contact_proven"] is False
    assert audit["metric_aperture_proven"] is False

    for pass_name in ("pass_a", "pass_b"):
        carry = audit["carry_pass_summaries"][pass_name]
        assert carry["between_jaw_tip_count"] == 10
        assert carry["all_crown_projections_between_jaw_tips"] is True
        hold = audit["closed_command_hold_pass_summaries"][pass_name]
        assert hold["between_jaw_tip_count"] == 4
        assert hold["all_crown_projections_between_jaw_tips"] is True

    comparison = receipt["simulator_comparison"]
    assert comparison["first_named_jaw_contact_sample"] == 229
    assert comparison["first_bilateral_jaw_contact_sample"] is None
    assert comparison["observed_named_jaw_bodies"] == [
        "left_moving_jaw_so101_v1"
    ]
    assert comparison["both_named_jaw_surfaces_contact"] is False
    assert comparison[
        "footage_proxy_and_simulator_named_contact_are_same_proof_class"
    ] is False
    assert receipt["new_execution"] == {
        "new_annotations": 0,
        "simulator_replays": 0,
        "new_candidates": 0,
        "parameter_changes": 0,
        "hardware_actions": 0,
        "heldout_opened": False,
    }
