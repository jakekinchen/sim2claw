from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = Path(
    "configs/evaluations/canonical_wrist_path_two_lane_static_v6.json"
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_two_lane_successor_is_uniform_and_bounded() -> None:
    contract = json.loads((ROOT / CONTRACT).read_text(encoding="utf-8"))
    assert contract["two_lane_override"] == {
        "lateral_offsets_m": [-0.003, 0.003],
        "stroke_m": 0.066,
        "return_to_live_seed_between_lanes": True,
        "derivation": (
            "the two endpoints of the frozen plus/minus 0.003 m "
            "lateral reset envelope"
        ),
        "only_outcome_relevant_change": True,
    }
    assert all(contract["unchanged_from_stroke_v5"].values())
    for key in (
        "base_contract",
        "base_static_receipt",
        "predecessor_closeout",
        "implementation",
    ):
        binding = contract[key]
        assert _sha(ROOT / binding["path"]) == binding["sha256"]


def test_two_lane_successor_source_has_no_hardware_surface() -> None:
    source = (
        ROOT / "src/sim2claw/canonical_wrist_path_two_lane_static.py"
    ).read_text(encoding="utf-8")
    assert "serial" not in source.lower()
    assert "dynamixel" not in source.lower()
