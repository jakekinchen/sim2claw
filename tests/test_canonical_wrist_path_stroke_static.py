from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = Path(
    "configs/evaluations/canonical_wrist_path_stroke_static_v5.json"
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_stroke_successor_is_one_bounded_cell_per_family() -> None:
    contract = json.loads((ROOT / CONTRACT).read_text(encoding="utf-8"))
    assert contract["stroke_override"] == {
        "from_m": 0.06,
        "to_m": 0.066,
        "derivation": (
            "existing 0.060 m stroke plus the full 0.006 m span of the "
            "frozen plus/minus 0.003 m reset uncertainty"
        ),
        "only_outcome_relevant_change": True,
    }
    assert len(contract["cases"]) == 4
    assert len({row["case_id"] for row in contract["cases"]}) == 4
    assert sum(
        row["direction"] == "REAL_TO_SIM" for row in contract["cases"]
    ) == 2
    assert sum(
        row["direction"] == "SIM_TO_REAL" for row in contract["cases"]
    ) == 2
    assert {row["contact_height_index"] for row in contract["cases"]} == {0}
    assert all(contract["unchanged_from_v4"].values())
    for key in ("base_contract", "predecessor_closeout", "implementation"):
        binding = contract[key]
        assert _sha(ROOT / binding["path"]) == binding["sha256"]


def test_stroke_successor_source_has_no_hardware_surface() -> None:
    source = (
        ROOT / "src/sim2claw/canonical_wrist_path_stroke_static.py"
    ).read_text(encoding="utf-8")
    assert "serial" not in source.lower()
    assert "dynamixel" not in source.lower()
