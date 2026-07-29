from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = Path(
    "configs/evaluations/canonical_wrist_path_static_selector_v1.json"
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_selector_is_static_only_and_outcome_blind() -> None:
    contract = json.loads((ROOT / CONTRACT).read_text(encoding="utf-8"))
    assert contract["selection_rule"] == {
        "eligible_candidates": [
            "canonical_single_lane_stroke_v5",
            "two_lane_v6",
        ],
        "primary_key": (
            "minimum_absolute_first_contact_vertical_normal_component"
        ),
        "tie_break": "canonical_single_lane_stroke_v5",
        "dynamic_outcomes_used": False,
    }
    assert contract["authority"]["static_selection"]
    assert not any(
        value
        for name, value in contract["authority"].items()
        if name != "static_selection"
    )
    for key in (
        "canonical_static_receipt",
        "two_lane_static_receipt",
        "predecessor_closeout",
        "implementation",
    ):
        binding = contract[key]
        assert _sha(ROOT / binding["path"]) == binding["sha256"]


def test_selector_source_has_no_hardware_or_dynamic_surface() -> None:
    source = (
        ROOT / "src/sim2claw/canonical_wrist_path_static_selector.py"
    ).read_text(encoding="utf-8")
    for forbidden in ("import mujoco", "import serial", "dynamixel_sdk"):
        assert forbidden not in source.lower()
