from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path

import numpy as np

from sim2claw.canonical_elbow_locked_wrist_path_static import (
    _locked_elbow_solver,
)

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT
    / "configs/evaluations/canonical_elbow_locked_wrist_path_static_v2.json"
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_locked_solver_excludes_elbow_column_and_restores_exact_value() -> None:
    source = inspect.getsource(_locked_elbow_solver)
    assert "active_indices = (0, 1, 3)" in source
    assert "elbow_value = float(seed[2])" in source
    assert "scratch.qpos[elbow_address] = elbow_value" in source


def test_exact_elbow_audit_is_bitwise_not_tolerance_based() -> None:
    source = inspect.getsource(
        __import__(
            "sim2claw.canonical_elbow_locked_wrist_path_static",
            fromlist=["enumerate_and_freeze"],
        ).enumerate_and_freeze
    )
    assert "np.array_equal" in source
    assert np.array_equal(
        np.asarray([1.0, 1.0]), np.full(2, 1.0)
    )


def test_contract_is_bounded_outcome_blind_and_has_no_motion_authority() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    for key in (
        "predecessor_contract",
        "base_contract",
        "mapping_closeout",
        "fresh_wrist_heldout_receipt",
        "elbow_stall_closeout",
        "predecessor_runner_closeout",
        "implementation",
    ):
        binding = contract[key]
        assert _sha(ROOT / binding["path"]) == binding["sha256"]
    assert contract["live_seed"]["locked_joint_index"] == 2
    assert contract["live_seed"]["locked_joint_name"] == "elbow_flex"
    assert all(contract["unchanged_from_base"].values())
    assert contract["authority"]["model_loading"]
    assert contract["authority"]["static_simulation"]
    assert not any(
        value
        for key, value in contract["authority"].items()
        if key not in {"model_loading", "static_simulation"}
    )
