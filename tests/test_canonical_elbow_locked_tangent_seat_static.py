from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from sim2claw.canonical_elbow_locked_tangent_seat_static import (
    TANGENT_SEAT_DEPTH_M,
    TangentSeatStaticError,
    enumerate_and_freeze,
)
from sim2claw.paths import REPO_ROOT


CONTRACT = (
    REPO_ROOT
    / "configs/evaluations/"
    "parking_recovery_rp03d_tangent_seat_static_v1.json"
)


def test_rp03d_freezes_one_midrange_tangent_seat() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["intervention"] == {
        "tangent_seat_depth_m": TANGENT_SEAT_DEPTH_M,
        "derivation": "midpoint_of_prospectively_advised_1_to_2mm_range",
        "only_outcome_relevant_change": (
            "one_task_horizontal_seat_waypoint_after_contact"
        ),
    }
    assert all(contract["unchanged"].values())
    assert contract["authority"]["physical_motion"] is False
    implementation = REPO_ROOT / contract["implementation"]["path"]
    assert hashlib.sha256(implementation.read_bytes()).hexdigest() == (
        contract["implementation"]["sha256"]
    )


def test_rp03d_refuses_output_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "existing"
    output.mkdir()
    with pytest.raises(
        TangentSeatStaticError,
        match="immutable tangent-seat output already exists",
    ):
        enumerate_and_freeze(CONTRACT, output)
