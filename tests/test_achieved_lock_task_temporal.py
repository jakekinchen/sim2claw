from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from sim2claw.achieved_lock_task_temporal import (
    AchievedLockTaskTemporalError,
    replay,
)
from sim2claw.paths import REPO_ROOT


CONTRACT = (
    REPO_ROOT
    / "configs/evaluations/achieved_lock_task_temporal_v1.json"
)


def test_achieved_lock_temporal_contract_is_two_case_dynamic_only() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["schema_version"] == (
        "sim2claw.achieved_lock_task_temporal.v1"
    )
    assert len(contract["cases"]) == 2
    assert {case["direction"] for case in contract["cases"]} == {
        "REAL_TO_SIM",
        "SIM_TO_REAL",
    }
    assert all(contract["unchanged_from_base"].values())
    assert contract["live_seed"]["follower_position_degrees"][2] == (
        92.43956043956044
    )
    implementation = REPO_ROOT / contract["temporal_implementation"]["path"]
    assert hashlib.sha256(implementation.read_bytes()).hexdigest() == (
        contract["temporal_implementation"]["sha256"]
    )


def test_achieved_lock_temporal_refuses_output_overwrite(
    tmp_path: Path,
) -> None:
    output = tmp_path / "existing"
    output.mkdir()
    with pytest.raises(
        AchievedLockTaskTemporalError,
        match="immutable achieved-lock temporal output already exists",
    ):
        replay(CONTRACT, output)
