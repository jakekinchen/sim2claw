from sim2claw.pawn_bg_f2_outcome_footprint_screen_verify import adjudicate


def test_or144_adjudication_rejects_failed_producer_selection() -> None:
    receipt = adjudicate()

    assert receipt["candidate_count"] == 16
    assert receipt["recomputed_continuous_upright_pass_count"] == 0
    assert receipt["eligible_for_strict_successor"] == []
    assert receipt["producer_selection_bug_confirmed"] is True
    assert receipt["simulator_replays_used"] == 0


def test_or144_isolated_cell_is_collision_assisted_non_lift() -> None:
    cell = adjudicate()["isolated_40mm_x_20mm_cell"]

    assert cell["piece_lifted"] is False
    assert cell["transported_after_lift"] is False
    assert cell["wrong_piece_names"] == ["brown_pawn_e2", "brown_pawn_g2"]
    assert cell["local_basin_supported"] is False
