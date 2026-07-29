from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from sim2claw.canonical_task_plane_registration import (
    CanonicalTaskPlaneRegistrationError,
    evaluate,
)
from sim2claw.paths import REPO_ROOT


CONTRACT = (
    REPO_ROOT
    / "configs/evaluations/canonical_task_plane_registration_v1.json"
)


def test_contract_is_motion_free_and_uses_strict_metric_gate() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["gates"]["maximum_task_plane_rms_mm_exclusive"] == 25.0
    assert contract["gates"]["maximum_task_plane_max_mm_exclusive"] == 25.0
    assert contract["authority"] == {
        "camera_open": False,
        "gateway": False,
        "serial": False,
        "physical_motion": False,
        "physical_recapture": False,
        "candidate_refit": False,
        "raw_heldout_image_reopen": False,
        "task_attempt": False,
        "physical_transfer": False,
    }


def test_evaluator_recomputes_v4_through_canonical_runtime(
    tmp_path: Path,
) -> None:
    output = tmp_path / "receipt.json"
    receipt = evaluate(CONTRACT, output)
    assert receipt["passed"] is True
    assert receipt["status"] == "canonical_task_plane_registration_pass"
    assert receipt["aggregate"]["task_plane_rms_mm"] == pytest.approx(
        4.741722953437291,
        abs=1e-9,
    )
    assert receipt["aggregate"]["task_plane_max_mm"] == pytest.approx(
        7.104332681776422,
        abs=1e-9,
    )
    assert receipt["corner_order"] == [
        "a8_outer",
        "h8_outer",
        "h1_outer",
        "a1_outer",
    ]
    assert receipt["piece_alignment_max_m"] <= 1e-9
    assert receipt["raw_heldout_images_reopened"] is False
    assert receipt["physical_recapture"] is False
    assert all(receipt["checks"].values())


def test_evaluator_refuses_to_overwrite_an_immutable_receipt(
    tmp_path: Path,
) -> None:
    output = tmp_path / "receipt.json"
    output.write_text("{}\n", encoding="utf-8")
    with pytest.raises(
        CanonicalTaskPlaneRegistrationError,
        match="immutable output already exists",
    ):
        evaluate(CONTRACT, output)


def test_evaluator_has_no_physical_control_dependencies() -> None:
    source = inspect.getsource(
        __import__(
            "sim2claw.canonical_task_plane_registration",
            fromlist=["unused"],
        )
    )
    for forbidden in (
        "SO101PhysicalGateway",
        "serial",
        "camera.open",
        "piece_square_transform",
        "board_orientation",
    ):
        assert forbidden not in source
