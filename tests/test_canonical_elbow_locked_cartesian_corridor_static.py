from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from sim2claw.canonical_elbow_locked_cartesian_corridor_static import (
    CartesianCorridorStaticError,
    MAXIMUM_CARTESIAN_CHORD_ERROR_M,
    MAXIMUM_POST_CONTACT_BACKTRACK_M,
    MAXIMUM_REFINEMENT_DEPTH,
    _point_to_segment_error,
    enumerate_and_freeze,
)
from sim2claw.paths import REPO_ROOT


CONTRACT = (
    REPO_ROOT
    / "configs/evaluations/"
    "parking_recovery_rp03c_cartesian_corridor_static_v1.json"
)


def test_rp03c_contract_freezes_one_geometric_intervention() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["intervention"] == {
        "maximum_cartesian_chord_error_m": (
            MAXIMUM_CARTESIAN_CHORD_ERROR_M
        ),
        "maximum_refinement_depth": MAXIMUM_REFINEMENT_DEPTH,
        "maximum_post_contact_backtrack_m": (
            MAXIMUM_POST_CONTACT_BACKTRACK_M
        ),
        "only_outcome_relevant_change": (
            "joint_interpolation_between_existing_cartesian_endpoints"
        ),
    }
    assert all(contract["unchanged"].values())
    assert contract["authority"]["physical_motion"] is False
    implementation = REPO_ROOT / contract["implementation"]["path"]
    assert hashlib.sha256(implementation.read_bytes()).hexdigest() == (
        contract["implementation"]["sha256"]
    )


def test_point_to_segment_error_detects_an_artificial_arc() -> None:
    error, closest = _point_to_segment_error(
        np.asarray([0.5, 0.002, 0.0]),
        np.asarray([0.0, 0.0, 0.0]),
        np.asarray([1.0, 0.0, 0.0]),
    )
    assert error == pytest.approx(0.002)
    assert closest.tolist() == pytest.approx([0.5, 0.0, 0.0])
    assert error > MAXIMUM_CARTESIAN_CHORD_ERROR_M


def test_rp03c_refuses_output_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "existing"
    output.mkdir()
    with pytest.raises(
        CartesianCorridorStaticError,
        match="immutable Cartesian-corridor output already exists",
    ):
        enumerate_and_freeze(CONTRACT, output)
