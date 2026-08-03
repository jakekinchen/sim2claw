from __future__ import annotations

import numpy as np

from sim2claw.observable_registration_post_object_persistent_static_spatial_decomposition import (
    _classify_spatial_family,
    _extract_panel,
    _orientation_separation,
    load_spatial_decomposition_contract,
)


def test_or121_contract_binds_identity_and_zero_video_render_boundary() -> None:
    contract = load_spatial_decomposition_contract()

    assert set(contract["frozen_identities"]) == {"implementation", "test"}
    assert contract["consensus"]["minimum_episode_count"] == 9
    assert contract["line_extractor"]["vote_threshold"] == 12
    assert contract["resource_boundary"]["source_video_decodes_allowed"] == 0
    assert contract["resource_boundary"]["renders_allowed"] == 0
    assert contract["claim_limits"]["specific_object_identity"] is False


def test_or121_extracts_third_panel_and_wraps_orientation_separation() -> None:
    image = np.zeros((240, 320 * 8), dtype=np.uint8)
    image[:, 640:960] = 255

    panel = _extract_panel(image, 2, 320, 240)

    assert panel.shape == (240, 320)
    assert np.all(panel == 255)
    assert _orientation_separation(170, 10) == 20.0
    assert _orientation_separation(50, 140) == 90.0


def test_or121_classification_requires_clipped_orthogonal_rectilinear_support() -> None:
    contract = load_spatial_decomposition_contract()
    summary = {
        "consensus_pixel_count": 900,
        "minimum_episode_consensus_coverage": 0.98,
        "largest_component_dilated_share": 0.38,
        "primary_orientation_line_count": 5,
        "primary_orientation_total_length_px": 200.0,
        "secondary_orientation_line_count": 2,
        "secondary_orientation_total_length_px": 80.0,
        "orientation_family_separation_degrees": 90.0,
        "largest_component_touches_image_boundary": True,
        "largest_component_bbox_aspect_ratio": 1.6,
    }

    assert _classify_spatial_family(summary, contract["acceptance"]) == "clipped_image_space_rectilinear_planar_array"
    summary["secondary_orientation_total_length_px"] = 20.0
    assert _classify_spatial_family(summary, contract["acceptance"]) == "unresolved_multi_component_persistent_scene"
