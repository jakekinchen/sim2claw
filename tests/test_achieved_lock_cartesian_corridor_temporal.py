from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from sim2claw.achieved_lock_cartesian_corridor_temporal import (
    CartesianCorridorTemporalError,
    replay,
)
from sim2claw.paths import REPO_ROOT


CONTRACT = (
    REPO_ROOT
    / "configs/evaluations/"
    "achieved_lock_cartesian_corridor_temporal_v1.json"
)


def test_rp03c_temporal_contract_freezes_twenty_episodes() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    base = json.loads(
        (
            REPO_ROOT / contract["base_temporal_contract"]["path"]
        ).read_text(encoding="utf-8")
    )
    assert len(contract["cases"]) == 2
    assert {case["direction"] for case in contract["cases"]} == {
        "REAL_TO_SIM",
        "SIM_TO_REAL",
    }
    assert (
        len(contract["cases"])
        * len(base["plant_paths"])
        * len(base["robustness_variants"])
        == 20
    )
    assert all(contract["unchanged"].values())
    implementation = REPO_ROOT / contract["implementation"]["path"]
    assert hashlib.sha256(implementation.read_bytes()).hexdigest() == (
        contract["implementation"]["sha256"]
    )


def test_rp03c_temporal_refuses_output_overwrite(
    tmp_path: Path,
) -> None:
    output = tmp_path / "existing"
    output.mkdir()
    with pytest.raises(
        CartesianCorridorTemporalError,
        match="immutable RP03C temporal output already exists",
    ):
        replay(CONTRACT, output)
