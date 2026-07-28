from __future__ import annotations

import xml.etree.ElementTree as ET

import numpy as np
import pytest

from sim2claw import bidirectional_pawn_push_v2_current_task_static_v1
from sim2claw import bidirectional_pawn_push_v2_low_planar_open_jaw_static_v1
from sim2claw import bidirectional_pawn_push_v2_orientation_funnel_static_v1
from sim2claw import bidirectional_pawn_push_v2_temporal_static
from sim2claw.bidirectional_pawn_push_v2_scene_labels import (
    CANONICAL_FRAME_ID,
    POSITION_TOLERANCE_M,
    RAW_GRID_TRANSFORM,
    CurrentTaskSceneLabelError,
    candidate_geometry,
    current_task_square_center,
    load_scene_label_contract,
    validate_modeled_source_position,
)
from sim2claw.scene import (
    CURRENT_TASK_PIECE_LAYOUT,
    board_square_center,
    build_scene_xml,
)


def test_current_task_scene_label_contract_is_exact_and_non_authorizing() -> None:
    contract = load_scene_label_contract()
    assert contract["semantic_frame"]["id"] == CANONICAL_FRAME_ID
    assert contract["raw_grid_placement"] == {
        "transform": RAW_GRID_TRANSFORM,
        "apply_exactly_once": True,
        "scope": "current-task sparse reset-layout body placement only",
    }
    assert contract["structural_invariant"]["xy_tolerance_m"] == (
        POSITION_TOLERANCE_M
    )
    assert all(value is False for value in contract["authority"].values())


def test_every_current_task_body_matches_its_canonical_semantic_square() -> None:
    xml = build_scene_xml(
        piece_layout=CURRENT_TASK_PIECE_LAYOUT,
        piece_square_transform=RAW_GRID_TRANSFORM,
        include_visual_props=False,
    )
    root = ET.fromstring(xml)
    bodies = [
        body
        for body in root.findall(".//body")
        if "_pawn_" in body.attrib.get("name", "")
    ]
    assert len(bodies) == 16
    for body in bodies:
        body_name = body.attrib["name"]
        square = body_name.rsplit("_", 1)[-1]
        modeled_xyz = np.asarray(
            [float(value) for value in body.attrib["pos"].split()],
            dtype=np.float64,
        )
        validate_modeled_source_position(
            selected_piece_id=body_name,
            source_square=square,
            modeled_source_xyz=modeled_xyz,
        )


def test_missing_or_double_remap_fails_before_action_compilation() -> None:
    canonical = current_task_square_center("b1")
    source, destination, direction = candidate_geometry(
        selected_piece_id="brown_pawn_b1",
        source_square="b1",
        destination_square="b2",
        modeled_source_xyz=canonical,
    )
    np.testing.assert_allclose(source, canonical, rtol=0.0, atol=1e-12)
    np.testing.assert_allclose(
        destination,
        current_task_square_center("b2"),
        rtol=0.0,
        atol=1e-12,
    )
    assert abs(float(np.linalg.norm(direction[:2])) - 1.0) <= 1e-12

    legacy_identity_or_double_remap = np.asarray(board_square_center("b1"))
    with pytest.raises(CurrentTaskSceneLabelError, match="invariant failed"):
        candidate_geometry(
            selected_piece_id="brown_pawn_b1",
            source_square="b1",
            destination_square="b2",
            modeled_source_xyz=legacy_identity_or_double_remap,
        )


def test_versioned_adapters_target_only_exact_v05_current_task_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    calls = []

    def capture(**kwargs):
        calls.append(kwargs)
        return {"adapter_only_test": True}

    monkeypatch.setattr(
        bidirectional_pawn_push_v2_current_task_static_v1,
        "_execute_with_current_task_wiring",
        capture,
    )
    contract = tmp_path / "contract.json"
    output = tmp_path / "output"
    bidirectional_pawn_push_v2_current_task_static_v1.enumerate_temporal_and_freeze(
        contract,
        output,
    )
    bidirectional_pawn_push_v2_current_task_static_v1.enumerate_low_planar_and_freeze(
        contract,
        output,
    )
    assert calls[0]["enumerator"] is (
        bidirectional_pawn_push_v2_temporal_static.enumerate_and_freeze
    )
    assert calls[0]["target_module"] is bidirectional_pawn_push_v2_temporal_static
    assert calls[1]["enumerator"] is (
        bidirectional_pawn_push_v2_low_planar_open_jaw_static_v1.enumerate_and_freeze
    )
    assert calls[1]["target_module"] is (
        bidirectional_pawn_push_v2_orientation_funnel_static_v1
    )
