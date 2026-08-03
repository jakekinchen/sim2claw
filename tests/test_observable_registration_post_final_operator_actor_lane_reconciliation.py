from sim2claw.observable_registration_post_final_operator_actor_lane_reconciliation import (
    _select,
    load_post_final_operator_actor_lane_reconciliation_contract,
)


def test_contract_is_receipt_only_and_fail_closed() -> None:
    contract = load_post_final_operator_actor_lane_reconciliation_contract()
    resources = contract["resource_boundary"]
    assert resources["pixel_reads_allowed"] == 0
    assert resources["renders_allowed"] == 0
    assert resources["fits_or_candidate_searches_allowed"] == 0
    assert contract["claim_limits"]["same_video_semantic_match"] is False


def test_decision_tree_closes_failed_actor_and_selects_dominant_static_gap() -> None:
    tree = load_post_final_operator_actor_lane_reconciliation_contract()["decision_tree"]
    selection, _, _ = _select(actor_passed=False, static_gap=0.32, dynamic_gap=0.03, maximum_static_primitive_gain=0.007, tree=tree)
    assert selection == "CLOSE_ACTOR_LANE_SELECT_PERSISTENT_STATIC_ENCLOSURE_BOUNDARY_LINES"
    assert _select(actor_passed=True, static_gap=0.32, dynamic_gap=0.03, maximum_static_primitive_gain=0.007, tree=tree)[0] == "CONTINUE_TESTED_ACTOR_LANE"
