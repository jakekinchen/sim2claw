from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from sim2claw.canonical_wrist_path_action_completion import (
    CanonicalWristPathActionCompletionError,
    freeze_actions,
)
from sim2claw.paths import REPO_ROOT


CONTRACT = (
    REPO_ROOT
    / "configs/evaluations/canonical_wrist_path_action_completion_v1.json"
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_action_completion_is_two_case_static_only_freeze() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert len(contract["cases"]) == 2
    assert all(
        case["dynamic_outcome_opened"] is False
        for case in contract["cases"]
    )
    for name in (
        "static_contract",
        "static_receipt",
        "temporal_closeout",
        "implementation",
    ):
        binding = contract[name]
        assert _sha(REPO_ROOT / binding["path"]) == binding["sha256"]
    assert contract["authority"]["static_simulation"]
    assert not contract["authority"]["dynamic_simulation"]
    assert not contract["authority"]["physical_motion"]


def test_action_completion_refuses_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "existing"
    output.mkdir()
    with pytest.raises(
        CanonicalWristPathActionCompletionError,
        match="immutable action completion output already exists",
    ):
        freeze_actions(CONTRACT, output)
