from __future__ import annotations

import json
from pathlib import Path

from sim2claw.coordinated_unloading_shadow_probe import compile_probe


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT
    / "configs/evaluations/coordinated_unloading_shadow_probe_static_v1.json"
)


def test_frozen_shadow_probe_is_dual_scene_contact_impossible(
    tmp_path: Path,
) -> None:
    receipt = compile_probe(CONTRACT, tmp_path / "probe")
    assert receipt["passed"] is True
    assert receipt["case_id"] == "tan_pawn_f7__f7_e7"
    assert receipt["prefix_stop_row_inclusive"] == 490
    assert receipt["prefix_shape"] == [491, 6]
    assert receipt["registered_scene"]["new_robot_contact_pairs"] == []
    assert receipt["uncorrected_scene"]["new_robot_contact_pairs"] == []
    assert receipt["registered_scene"]["selected_pawn_contact_observed"] is False
    assert receipt["uncorrected_scene"]["selected_pawn_contact_observed"] is False
    assert receipt["checks"]["all_segments_within_excursion_limit"] is True
    assert receipt["physical_motion"] is False
    assert receipt["physical_task_attempts"] == 0


def test_frozen_contract_preserves_false_physical_authority() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["authority"] == {
        "model_loading": True,
        "static_simulation": True,
        "camera": False,
        "gateway": False,
        "serial": False,
        "physical_motion": False,
        "physical_task_attempt": False,
        "mapping_approval": False,
        "transfer_claim": False,
    }
    assert contract["gateway"]["segment_boundaries"] == [0, 433, 490]
    assert contract["gateway"]["segment_excursion_limit"] == 80.0
    assert contract["prefix"]["minimum_contact_margin_rows"] == 40
