from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sim2claw.bidirectional_pawn_push_v2_temporal_static import (
    enumerate_empty_orthogonal_neighbors,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / (
    "configs/evaluations/"
    "bidirectional_pawn_push_v2_temporal_static_v1.json"
)
SQUARES = (
    "a2",
    "b1",
    "c2",
    "d1",
    "e2",
    "f1",
    "g2",
    "h1",
    "a8",
    "b7",
    "c8",
    "d7",
    "e8",
    "f7",
    "g8",
    "h7",
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_static_contract_is_bound_and_has_no_dynamic_or_physical_authority() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    for field in ("temporal_plan", "rehearsal_contract", "implementation"):
        binding = contract[field]
        assert _sha(ROOT / binding["path"]) == binding["sha256"]
    gateway = contract["gateway_semantics"]
    assert _sha(ROOT / gateway["path"]) == gateway["sha256"]
    assert gateway["gateway_opened"] is False
    assert gateway["serial_opened"] is False
    assert contract["enumeration"]["v05_dynamic_outcomes_available_to_selection"] is False
    assert not any(contract["authority"].values())


def test_reset_layout_neighbor_universe_is_complete_bounded_and_deterministic() -> None:
    pieces = {square: f"pawn_{square}" for square in SQUARES}
    first = enumerate_empty_orthogonal_neighbors(
        pieces, excluded_squares=["c2"]
    )
    second = enumerate_empty_orthogonal_neighbors(
        dict(reversed(tuple(pieces.items()))),
        excluded_squares=["c2"],
    )
    assert first == second
    assert len(first) == 48
    assert len(first) <= 64
    assert not any(row["source_square"] == "c2" for row in first)
    assert first[0] == {
        "source_square": "b1",
        "destination_square": "a1",
        "selected_piece_id": "pawn_b1",
    }
    occupied = set(SQUARES)
    assert all(row["destination_square"] not in occupied for row in first)
