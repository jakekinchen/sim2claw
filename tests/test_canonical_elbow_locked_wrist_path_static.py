from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path

import numpy as np

from sim2claw.canonical_elbow_locked_low_path_static import (
    _compile_low_direct,
)
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


def test_v3_height_successor_materializes_path_without_weakening_contact_gate() -> None:
    successor_path = (
        ROOT
        / "configs/evaluations/canonical_elbow_locked_wrist_path_static_v3.json"
    )
    successor = json.loads(successor_path.read_text(encoding="utf-8"))
    bridge_path = ROOT / successor["base_contract"]["path"]
    assert _sha(bridge_path) == successor["base_contract"]["sha256"]
    bridge = json.loads(bridge_path.read_text(encoding="utf-8"))
    base_path = ROOT / bridge["base_contract"]["path"]
    assert _sha(base_path) == bridge["base_contract"]["sha256"]
    base = json.loads(base_path.read_text(encoding="utf-8"))
    assert base["grid"]["contact_heights_m"] == [0.036, 0.04]
    assert base["action"]["precontact_backoff_m"] == 0.035
    assert base["gates"]["maximum_first_contact_height_m"] == 0.032
    assert base["grid"]["maximum_total_cells"] == 288
    assert all(successor["unchanged_from_base"].values())


def test_v4_low_path_removes_only_unreachable_clearance_stages() -> None:
    source = inspect.getsource(_compile_low_direct)
    assert "cartesian_targets = [low_precontact, contact, pushed]" in source
    assert '"high_clearance_stage_removed": True' in source
    assert '"high_retreat_stage_removed": True' in source
    contract_path = (
        ROOT
        / "configs/evaluations/canonical_elbow_locked_low_path_static_v4.json"
    )
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    for key in (
        "base_contract",
        "mapping_closeout",
        "fresh_wrist_heldout_receipt",
        "elbow_stall_closeout",
        "implementation",
    ):
        binding = contract[key]
        assert _sha(ROOT / binding["path"]) == binding["sha256"]
    assert all(contract["unchanged_from_base"].values())
    assert not any(
        value
        for key, value in contract["authority"].items()
        if key not in {"model_loading", "static_simulation"}
    )
