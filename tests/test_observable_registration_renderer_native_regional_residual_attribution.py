from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from sim2claw.observable_registration_native_rasterizer_byte_equivalence import (
    _compile_native,
)
from sim2claw.observable_registration_board_anchored_workcell_se2_static_development_fit import (
    _region_masks,
)
from sim2claw.observable_registration_renderer_native_regional_residual_attribution import (
    DEFAULT_CONTRACT,
    _compile_id_renderer,
    _dynamic_attribution,
    _exposure_audit,
    _occupancy_panels,
    _renderer_equivalence_probe,
    evaluate_once,
    load_regional_residual_attribution_contract,
)


def test_contract_is_frozen_diagnostic_only_and_closes_unopened_pixels() -> None:
    contract = load_regional_residual_attribution_contract()
    assert contract["status"] == "owner_admitted_frozen_not_executed"
    assert contract["development_partition"]["split_positions"] == list(range(1, 8))
    assert sum(row["frame_count"] for row in contract["development_partition"]["episodes"]) == 751
    assert contract["resource_boundary"]["positions_8_through_11_pixel_reads_allowed"] == 0
    assert contract["resource_boundary"]["sibling_pixel_reads_allowed"] == 0
    assert contract["resource_boundary"]["fits_allowed"] == 0
    assert contract["protocol_provenance"]["retrospective_and_outcome_informed"] is True
    assert contract["claim_limits"]["fidelity_improvement"] is False
    assert contract["claim_limits"]["physics_fidelity"] is False
    assert not any(contract["authority"].values())


def test_renderer_groups_include_every_scene_body_exactly_once() -> None:
    contract = load_regional_residual_attribution_contract()
    scene = json.loads(Path(contract["sources"]["scene_manifest"]["path"]).read_text())
    grouped = [
        int(body_id)
        for declaration in contract["renderer_group_ids"].values()
        for body_id in declaration.get("body_ids", [])
    ]
    assert len(grouped) == len(set(grouped))
    assert set(grouped) == {int(geom["body_id"]) for geom in scene["geoms"]}
    assert contract["renderer_group_ids"]["world_floor"]["body_ids"] == [0]


def test_instrumented_renderer_is_rgb_and_counter_equivalent(tmp_path: Path) -> None:
    contract = load_regional_residual_attribution_contract()
    original, _, _ = _compile_native(
        {
            "sources": {"native_source": contract["sources"]["or79_native_source"]},
            "compiler": {"executable": "clang"},
        },
        tmp_path,
    )
    instrumented, _, _ = _compile_id_renderer(tmp_path)
    result = _renderer_equivalence_probe(original, instrumented)
    assert result == {
        "synthetic_render_count": 2,
        "rgb_byte_equal": True,
        "depth_updates_equal": True,
        "occluded_fragments_equal": True,
        "visible_group_ids": [4, 9],
    }


def test_bound_occupancy_map_round_trips_four_frozen_panels() -> None:
    contract = load_regional_residual_attribution_contract()
    receipt = json.loads(Path(contract["sources"]["or132_receipt"]["path"]).read_text())
    panels = _occupancy_panels(receipt["rows"][0]["occupancy_map"])
    assert len(panels) == 4
    assert all(panel.shape == (240, 320) and panel.dtype == np.bool_ for panel in panels)
    or120 = json.loads(Path(contract["sources"]["or120_contract"]["path"]).read_text())
    _, outside = _region_masks(
        np.asarray(or120["regions"]["board_plus_margin"]["points_px"], dtype=np.float64),
        width=320,
        height=240,
        dilation_kernel_px=or120["regions"]["board_plus_margin"]["dilation_kernel_px_at_320x240"],
    )
    assert int((panels[0] & outside).sum()) == int(receipt["rows"][0]["persistent_outside_board"]["physical_pixels"])
    assert int((panels[2] & outside).sum()) == int(receipt["rows"][0]["dynamic_outside_board"]["physical_pixels"])


def test_dynamic_attribution_conserves_mass_on_synthetic_frames() -> None:
    physical = np.full((24, 32, 3), 100, np.uint8)
    candidate = physical.copy()
    cv2.line(physical, (0, 12), (31, 12), (0, 0, 0), 1)
    ids = np.zeros((24, 32), np.uint16)
    ids[5:19, 12:16] = 7
    persistent = np.zeros((24, 32), bool)
    persistent[2, :] = True
    dynamic = np.ones((24, 32), bool)
    outside = np.ones((24, 32), bool)
    result = _dynamic_attribution(
        [physical],
        [candidate],
        [ids],
        persistent,
        dynamic,
        outside,
        {7},
        {
            "edge_tolerance_kernel_px": 3,
            "camera": {"position": [0.0, -2.0, 2.0], "target": [0.0, 0.0, 0.0]},
            "nominal_light_direction": [0.3, -0.4, 0.85],
            "canny_low_threshold": 50,
            "canny_high_threshold": 150,
            "silhouette_deficit": {"distance_to_rendered_arm_silhouette_px_exclusive_max": 5.0},
            "shadow_like": {
                "distance_to_rendered_arm_silhouette_px_min": 5.0,
                "arm_centroid_offset_stability_px_max": 6.0,
            },
        },
        100.0,
    )
    assert result["physical_dynamic_unmatched_edge_pixels"] > 0
    assert sum(result["mass_pixels"].values()) == result["physical_dynamic_unmatched_edge_pixels"]
    assert result["mass_shares_sum"] == pytest.approx(1.0)


def test_exposure_audit_ledgers_all_eighteen_recordings_without_sibling_pixels() -> None:
    exposure = _exposure_audit(load_regional_residual_attribution_contract())
    assert exposure["complete"] is True
    assert exposure["recording_count"] == 18
    assert exposure["or131_recording_count"] == 11
    assert exposure["other_sibling_recording_count"] == 7
    assert exposure["derived_frame_artifact_count"] == 36
    sibling_rows = [row for row in exposure["recordings"] if not row["or131_corpus_member"]]
    assert all(row["pixels_read_by_or133a"] == 0 for row in sibling_rows)
    assert exposure["untouched_cohort_remaining"] is False


def test_evaluator_refuses_existing_receipt_without_reading_pixels(tmp_path: Path) -> None:
    (tmp_path / "receipt.json").write_text("{}")
    with pytest.raises(ValueError, match="one-run receipt already exists"):
        evaluate_once(DEFAULT_CONTRACT, tmp_path)
