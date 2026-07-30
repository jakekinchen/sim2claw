from pathlib import Path

from sim2claw.retained_rgb_contact_consequence_proxies import (
    build_retained_rgb_contact_consequence_proxies,
    load_retained_rgb_contact_consequence_proxies_contract,
)


def test_contract_forbids_depth_force_and_reannotation() -> None:
    contract = load_retained_rgb_contact_consequence_proxies_contract()
    policy = contract["proxy_policy"]
    assert policy["pawn_axis_requires_distinct_accepted_crown_and_base_points"]
    assert not policy["metric_depth_restoration_allowed"]
    assert not policy["contact_force_inference_allowed"]
    assert not policy["cross_episode_merge_allowed"]
    assert not policy["reannotation_allowed"]


def test_proxy_builder_abstains_on_unobserved_pawn_axis(
    tmp_path: Path,
) -> None:
    receipt = build_retained_rgb_contact_consequence_proxies(
        output_directory=tmp_path
    )
    assert receipt["status"] == (
        "PASS_BOUNDED_JAW_CROWN_EVENT_PROXY_PAWN_AXIS_INSUFFICIENT"
    )
    assert receipt["proxy_summary"]["jaw_proxy_row_count"] == 23
    assert receipt["proxy_summary"]["accepted_crown_row_count"] == 10
    assert receipt["proxy_summary"]["pawn_axis_orientation_available"] is False
    assert receipt["proxy_summary"]["physical_first_contact_interval_samples"] == [
        228,
        232,
    ]
    assert receipt["global_mapping_approved"] is False
    assert receipt["transfer_claim"] is False
