from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from sim2claw.board_orientation import (
    all_square_mappings,
    canonical_body_grid_square,
    canonical_square_center,
    canonical_to_legacy_square,
    legacy_to_canonical_square,
    render_canonical_orientation_svg,
)
from sim2claw.paths import REPO_ROOT
from sim2claw.scene import (
    CURRENT_TASK_PIECE_LAYOUT,
    board_square_center,
    build_scene_xml,
)


CONTRACT_PATH = REPO_ROOT / "configs/scenes/chessboard_canonical_orientation_v1.json"
MIGRATION_PATH = (
    REPO_ROOT / "configs/migrations/chessboard_orientation_legacy_to_canonical_v1.json"
)
UG_CONTRACT_PATH = (
    REPO_ROOT
    / "configs/evaluations/bidirectional_pawn_push_v2_low_planar_open_jaw_static_v1.json"
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_rotate_180_mapping_is_complete_bijective_and_self_inverse() -> None:
    mapping = all_square_mappings()
    assert len(mapping) == 64
    assert len(set(mapping.values())) == 64
    assert mapping["a1"] == "h8"
    assert mapping["g8"] == "b1"
    assert mapping["f7"] == "c2"
    for raw_grid_square, canonical_square in mapping.items():
        assert canonical_to_legacy_square(canonical_square) == raw_grid_square
        assert legacy_to_canonical_square(raw_grid_square) == canonical_square


def test_semantic_body_name_is_preserved_while_raw_grid_position_rotates() -> None:
    xml = build_scene_xml(
        piece_layout=CURRENT_TASK_PIECE_LAYOUT,
        piece_square_transform="rotate_180",
        include_visual_props=False,
    )
    root = ET.fromstring(xml)
    body = root.find(".//body[@name='brown_pawn_b1']")
    assert body is not None
    modeled_position = tuple(float(value) for value in body.attrib["pos"].split())

    assert canonical_body_grid_square("b1") == "g8"
    assert modeled_position == pytest.approx(canonical_square_center("b1"), abs=1e-9)
    assert modeled_position == pytest.approx(board_square_center("g8"), abs=1e-9)
    assert modeled_position != pytest.approx(board_square_center("b1"), abs=1e-6)


def test_contract_preserves_semantic_layout_and_separates_historical_fit() -> None:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    layout = contract["sparse_reset_layout"]
    assert layout["canonical_semantic_body_labels"]["brown"] == [
        "a2",
        "b1",
        "c2",
        "d1",
        "e2",
        "f1",
        "g2",
        "h1",
    ]
    assert layout["canonical_semantic_body_labels"]["tan"] == [
        "a8",
        "b7",
        "c8",
        "d7",
        "e8",
        "f7",
        "g8",
        "h7",
    ]
    assert layout["example"]["canonical_body_id"] == "brown_pawn_b1"
    assert layout["example"]["raw_legacy_grid_square"] == "g8"
    adapter = contract["legacy_scene_adapter"]
    assert adapter["transform"] == "rotate_180"
    assert adapter["bijection_size"] == 64
    historical = contract["historical_frame_separation"]["v04_fit_only_candidate"]
    assert historical["transform"] == "reflect_ranks"
    assert historical["not_the_global_frame_transform"] is True
    for key in (
        "model_loading",
        "static_simulation",
        "dynamic_replay",
        "camera",
        "gateway",
        "serial",
        "physical_motion",
        "paid_compute",
        "simulator_promotion",
        "transfer_claim",
    ):
        assert contract["authority"][key] is False


def test_bound_orientation_sources_and_preserved_history_match_hashes() -> None:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    for binding in (
        contract["physical_landmark_binding"],
        contract["legacy_scene_adapter"]["implementation"],
        contract["legacy_scene_adapter"]["immutable_legacy_geometry"],
        contract["historical_frame_separation"]["owner_reviewed_orientation_diagnosis"],
        contract["historical_frame_separation"]["v04_fit_only_candidate"],
    ):
        assert _sha(REPO_ROOT / binding.get("path", binding.get("source"))) == binding[
            "source_sha256" if "source_sha256" in binding else "sha256"
        ]

    migration = json.loads(MIGRATION_PATH.read_text(encoding="utf-8"))
    assert migration["resume"] is False
    assert migration["orientation_contract"]["sha256"] == _sha(CONTRACT_PATH)
    for binding in migration["historical_preservation"]["preserved_without_edit"]:
        assert _sha(REPO_ROOT / binding["path"]) == binding["sha256"]


def test_orientation_svg_contains_every_label_once_with_near_far_cues(
    tmp_path: Path,
) -> None:
    svg_path = tmp_path / "canonical-orientation.svg"
    render_canonical_orientation_svg(svg_path)
    root = ET.parse(svg_path).getroot()
    labels = [
        element.attrib["data-square-label"]
        for element in root.iter()
        if "data-square-label" in element.attrib
    ]
    assert len(labels) == 64
    assert len(set(labels)) == 64
    text_content = " ".join("".join(root.itertext()).split())
    assert "FAR SIDE · RANK 8" in text_content
    assert "NEAR SIDE · RANK 1 · OPERATOR + LEFT ARM" in text_content


def test_studio_orientation_reference_is_explicit_and_responsive() -> None:
    html = (REPO_ROOT / "src/sim2claw/studio_web/index.html").read_text(
        encoding="utf-8"
    )
    javascript = (REPO_ROOT / "src/sim2claw/studio_web/studio.js").read_text(
        encoding="utf-8"
    )
    css = (REPO_ROOT / "src/sim2claw/studio_web/studio.css").read_text(
        encoding="utf-8"
    )
    assert 'id="canonical-orientation-board"' in html
    assert "Far side · rank 8" in html
    assert "Near side · rank 1 · operator + left arm" in html
    assert "function renderCanonicalOrientationBoard()" in javascript
    assert "for (const rank of [8, 7, 6, 5, 4, 3, 2, 1])" in javascript
    assert "data.canonicalSquare" not in javascript
    assert "cell.dataset.canonicalSquare = square" in javascript
    assert ".canonical-orientation-cell" in css
    assert "@media (max-width: 700px)" in css


def test_v05_ug_fails_closed_before_model_loading_or_enumeration() -> None:
    from sim2claw.bidirectional_pawn_push_v2_low_planar_open_jaw_static_v1 import (
        LowPlanarOpenJawStaticV1Error,
        enumerate_and_freeze,
    )

    with pytest.raises(LowPlanarOpenJawStaticV1Error, match="paused"):
        enumerate_and_freeze(
            UG_CONTRACT_PATH,
            REPO_ROOT / "runs/bidirectional-pawn-push-v2/never-created-paused-v05-ug",
        )
    assert not (
        REPO_ROOT / "runs/bidirectional-pawn-push-v2/never-created-paused-v05-ug"
    ).exists()
