from __future__ import annotations

import inspect
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from sim2claw.canonical_seeded_action_temporal import (
    CanonicalSeededActionTemporalError,
    _zoh_delay,
    replay,
)
from sim2claw.paths import REPO_ROOT


CONTRACT = (
    REPO_ROOT
    / "configs/evaluations/canonical_wrist_path_reset_temporal_v2.json"
)


def test_temporal_contract_preserves_strict_proof_gates() -> None:
    successor = json.loads(CONTRACT.read_text(encoding="utf-8"))
    base_binding = successor["base_temporal_contract"]
    base_path = REPO_ROOT / base_binding["path"]
    assert hashlib.sha256(base_path.read_bytes()).hexdigest() == (
        base_binding["sha256"]
    )
    contract = json.loads(base_path.read_text(encoding="utf-8"))
    assert contract["gates"]["minimum_signed_progress_mm"] == 36.025
    assert contract["acceptance"]["minimum_cases_per_direction"] == 2
    assert contract["plant_paths"][1] == {
        "path_id": "diagnostic_zoh_0p11s",
        "kind": "zero_order_hold_command_delay",
        "delay_seconds": 0.11,
        "diagnostic_only": True,
        "calibrated_physical_latency": False,
    }
    assert contract["authority"]["physical_motion"] is False
    assert successor["status"] == (
        "frozen_after_two_action_completion_before_isolated_reset_dynamic_replay"
    )
    assert all(successor["unchanged_from_base"].values())
    assert successor["reset_layout"]["mode"] == (
        "isolated_selected_pawn_offboard_parking"
    )
    assert (
        successor["temporal_implementation"]["sha256"]
        == hashlib.sha256(
            (
                REPO_ROOT
                / successor["temporal_implementation"]["path"]
            ).read_bytes()
        ).hexdigest()
    )


def test_zoh_delay_preserves_shape_and_requested_bytes() -> None:
    requested = np.arange(48, dtype="<f8").reshape(8, 6)
    before = requested.tobytes(order="C")
    applied, indices = _zoh_delay(
        requested, sample_hz=40.0, delay_seconds=0.11
    )
    assert requested.tobytes(order="C") == before
    assert applied.shape == requested.shape
    assert indices.tolist() == [0, 0, 0, 0, 0, 0, 1, 2]


def test_temporal_v1_dry_validation_is_quarantined() -> None:
    closeout = json.loads(
        (
            REPO_ROOT
            / "configs/decisions/"
            "canonical_seeded_action_temporal_v1_dry_validation_closeout.json"
        ).read_text(encoding="utf-8")
    )
    assert closeout["status"] == (
        "closed_nonadmissible_prefreeze_implementation_validation"
    )
    assert closeout["disclosure"]["official_attempt_count"] == 0
    assert closeout["disclosure"]["temporary_outputs_are_authoritative"] is False
    assert not any(closeout["authority"].values())


def test_temporal_replay_refuses_output_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "existing"
    output.mkdir()
    with pytest.raises(
        CanonicalSeededActionTemporalError,
        match="immutable temporal output directory already exists",
    ):
        replay(CONTRACT, output)


def test_temporal_replay_has_no_hardware_dependencies() -> None:
    source = inspect.getsource(
        __import__(
            "sim2claw.canonical_seeded_action_temporal",
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
