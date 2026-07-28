from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTHORIZATION = (
    ROOT
    / "configs"
    / "evaluations"
    / "bidirectional_pawn_push_v2_low_planar_post_fable_authorization_v2.json"
)
CONTRACT = (
    ROOT
    / "configs"
    / "evaluations"
    / "bidirectional_pawn_push_v2_low_planar_post_fable_static_v2.json"
)
PAUSED = (
    ROOT
    / "configs"
    / "evaluations"
    / "bidirectional_pawn_push_v2_low_planar_open_jaw_static_v1.json"
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_post_fable_v2_bindings_are_frozen_before_model_loading() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["status"] == "frozen_before_model_loading"
    for key in (
        "authorization",
        "post_fable_decision",
        "current_task_scene_labels",
        "supersedes_paused_v05_ug",
        "selection_source_static_receipt",
        "v05_uf_temporal_receipt",
        "orientation_static_contract",
        "seeded_static_contract",
        "ramped_static_contract",
        "open_jaw_static_contract",
        "legacy_compatibility_implementation",
        "current_task_adapter",
        "implementation",
    ):
        binding = contract[key]
        assert _sha(ROOT / binding["path"]) == binding["sha256"]
    for binding in contract["base_implementations"].values():
        assert _sha(ROOT / binding["path"]) == binding["sha256"]
    assert _sha(PAUSED) == (
        "bb04adf78b55fe16726b8bb20f18ed92795b6f9a58cad2ee7deb3f57b16a939d"
    )


def test_exact_six_family_108_cell_screen_has_no_substitution() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    design = contract["frozen_design"]
    expected = [
        "brown_pawn_d1__d1_c1",
        "tan_pawn_b7__b7_b8",
        "tan_pawn_b7__b7_a7",
        "tan_pawn_c8__c8_b8",
        "tan_pawn_c8__c8_c7",
        "tan_pawn_a8__a8_b8",
    ]
    assert design["priority_case_ids"] == expected
    assert design["evaluated_family_count"] == 6
    assert design["cells_per_family"] == 18
    assert design["maximum_total_cells"] == 108
    assert design["substitution_if_priority_family_is_ineligible"] is False
    assert design["direction_composition"]["REAL_TO_SIM"] == expected[::2]
    assert design["direction_composition"]["SIM_TO_REAL"] == expected[1::2]


def test_ranking_is_static_only_and_optional_hedge_is_prospectively_zero() -> None:
    authorization = json.loads(AUTHORIZATION.read_text(encoding="utf-8"))
    source = authorization["static_only_selection_source"]
    assert source["temporal_outcomes_opened_for_selection"] is False
    design = authorization["prospective_static_design"]
    assert design["dynamic_outcomes_available_to_ranking"] is False
    assert design["flat_closed_jaw_side_or_back_anti_wedge_hedge_count"] == 0
    assert design["flat_closed_jaw_side_or_back_anti_wedge_hedge_geometry"] is None
    assert "no fresh quarantine-clean" in design["zero_hedge_reason"]
    assert design["contact_height_m"] == 0.018
    assert design["contact_offset_m"] == 0.016
    assert design["stroke_m"] == 0.09
    assert design["vertical_rise_m"] == 0.0
    assert authorization["authority"]["static_simulation"] is True
    for key in (
        "dynamic_replay",
        "camera",
        "gateway",
        "serial",
        "physical_motion",
        "physical_task_attempt",
        "paid_compute",
        "promotion",
        "transfer_claim",
    ):
        assert authorization["authority"][key] is False
