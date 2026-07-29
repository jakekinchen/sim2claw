from __future__ import annotations

import json
from pathlib import Path

from sim2claw.pawn_direction_family_static import (
    BEARINGS_DEGREES,
    NEAR_SIDE_SQUARES,
    _corridor_gate,
    _destination_name,
    _parse_destination,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT
    / "configs/evaluations/reachable_lock_80_low_contact_pawn_direction_static_v1.json"
)


def test_direction_grid_is_finite_and_preserves_carry() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert tuple(contract["grid"]["near_side_squares"]) == NEAR_SIDE_SQUARES
    assert tuple(contract["grid"]["bearings_degrees"]) == BEARINGS_DEGREES
    assert contract["grid"]["new_family_count"] == 63
    assert contract["grid"]["new_cell_count"] == 756
    assert contract["grid"]["carry_case_id"] == "brown_pawn_f1__f1_f2"
    assert len(contract["grid"]["historical_quarantine_case_ids"]) == 8
    assert all(contract["unchanged"].values())
    assert contract["authority"]["dynamic_simulation"] is False
    assert contract["authority"]["physical_motion"] is False


def test_synthetic_destination_round_trips() -> None:
    for square in NEAR_SIDE_SQUARES:
        for bearing in BEARINGS_DEGREES:
            assert _parse_destination(
                _destination_name(square, bearing)
            ) == (square, bearing)


def test_corridor_gate_rejects_carry_pawn_and_off_board_endpoint() -> None:
    common = {
        "stroke_m": 0.066,
        "square_side_m": 0.04445,
        "pawn_radius_m": 0.0138,
        "minimum_corridor_separation_m": 0.0336,
    }
    same_pawn = _corridor_gate(
        source_square="f1", bearing_degrees=0, **common
    )
    assert same_pawn["disjoint_pawn"] is False
    assert same_pawn["passed"] is False
    off_board = _corridor_gate(
        source_square="h1", bearing_degrees=0, **common
    )
    assert off_board["endpoint_inside_board"] is False
    assert off_board["passed"] is False
