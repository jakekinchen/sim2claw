from sim2claw.observable_registration_post_final_two_material_finite_object_full_timeline_propagation import load_post_final_two_material_finite_object_full_timeline_propagation_contract


def test_contract_freezes_full_timeline_and_honest_same_video_gates() -> None:
    contract = load_post_final_two_material_finite_object_full_timeline_propagation_contract()
    assert contract["gates"]["expected_total_frame_count"] == 1210
    assert contract["same_video_acceptance"]["minimum_pooled_mean_full_frame_linear_pixel_similarity"] == 0.80
    assert contract["same_video_acceptance"]["maximum_pooled_mean_full_frame_linear_pixel_similarity"] == 0.90
    assert contract["same_video_acceptance"]["minimum_pooled_mean_outside_board_edge_f1"] == 0.60
    assert contract["resource_boundary"]["fits_or_candidate_selections_allowed"] == 0


def test_frozen_object_has_two_real_materials_and_exact_triangles() -> None:
    contract = load_post_final_two_material_finite_object_full_timeline_propagation_contract()
    frozen = contract["frozen_object"]
    assert frozen["shaft_pre_response_bgr"] != frozen["terminal_pre_response_bgr"]
    assert frozen["total_triangle_count"] == 348
