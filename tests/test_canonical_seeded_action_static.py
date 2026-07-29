from __future__ import annotations

import inspect
import json
from pathlib import Path

import numpy as np
import pytest

from sim2claw.canonical_seeded_action_static import (
    CanonicalSeededActionStaticError,
    enumerate_and_freeze,
)
from sim2claw.paths import REPO_ROOT


CONTRACT = (
    REPO_ROOT
    / "configs/evaluations/canonical_seeded_action_static_v1.json"
)


def test_contract_freezes_current_seed_and_false_physical_authority() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["live_seed"]["follower_position_degrees"] == [
        6.5054945054945055,
        -85.53846153846153,
        99.47252747252747,
        -20.087912087912088,
        -103.34065934065934,
        2.375296912114014,
    ]
    assert contract["gates"]["minimum_families_per_direction"] == 2
    assert contract["authority"]["physical_motion"] is False
    assert contract["authority"]["dynamic_simulation"] is False


def test_static_compiler_is_deterministic_and_row_zero_is_exact(
    tmp_path: Path,
) -> None:
    first = enumerate_and_freeze(CONTRACT, tmp_path / "first")
    second = enumerate_and_freeze(CONTRACT, tmp_path / "second")
    comparable_first = {
        key: value
        for key, value in first.items()
        if key not in {"selected"}
    }
    comparable_second = {
        key: value
        for key, value in second.items()
        if key not in {"selected"}
    }
    assert comparable_first == comparable_second
    assert [row["action_sha256"] for row in first["selected"]] == [
        row["action_sha256"] for row in second["selected"]
    ]
    seed = np.asarray(
        json.loads(CONTRACT.read_text())["live_seed"][
            "follower_position_degrees"
        ]
    )
    for row in first["selected"]:
        assert np.allclose(
            row["gateway"]["row_zero_physical"],
            seed,
            atol=1e-12,
            rtol=0.0,
        )
    assert first["dynamic_simulation_executed"] is False
    assert first["physical_motion"] is False


def test_static_compiler_refuses_output_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "existing"
    output.mkdir()
    with pytest.raises(
        CanonicalSeededActionStaticError,
        match="immutable output directory already exists",
    ):
        enumerate_and_freeze(CONTRACT, output)


def test_static_compiler_has_no_hardware_dependencies() -> None:
    source = inspect.getsource(
        __import__(
            "sim2claw.canonical_seeded_action_static",
            fromlist=["unused"],
        )
    )
    for forbidden in (
        "SO101PhysicalGateway",
        "serial",
        "camera.open",
        ".set_torque(",
        "write_goal",
    ):
        assert forbidden not in source
