from __future__ import annotations

import json
from pathlib import Path

import pytest

from sim2claw.c922_exact_mode_calibration import C922CalibrationError
from sim2claw.c922_exact_mode_calibration_control import (
    EXPECTED_GUARD,
    GUARD_PATH,
    load_exhaustion_guard,
    run_authorized_evaluation,
)


def test_guard_matches_exact_terminal_not_ready_result() -> None:
    assert load_exhaustion_guard() == EXPECTED_GUARD
    assert EXPECTED_GUARD["verdict"] == "calibration_dataset_not_ready"
    assert len(EXPECTED_GUARD["missing_prerequisites"]) == 10
    assert EXPECTED_GUARD["declared_frame_count"] == 0
    assert EXPECTED_GUARD["accepted_frame_count"] == 0
    assert EXPECTED_GUARD["rejected_frame_count"] == 0
    assert EXPECTED_GUARD["model_fits_used"] == 0
    assert EXPECTED_GUARD["dataset_evaluations_used"] == 1
    assert EXPECTED_GUARD["dataset_evaluations_maximum"] == 1
    assert EXPECTED_GUARD["camera_sessions_used"] == 0
    assert EXPECTED_GUARD["new_camera_frames_used"] == 0
    assert EXPECTED_GUARD["robot_motions_used"] == 0
    assert EXPECTED_GUARD["simulator_replays_used"] == 0
    assert EXPECTED_GUARD["calibration_receipt_emitted"] is False
    assert EXPECTED_GUARD["retry_authorized"] is False


def test_control_refuses_before_evaluator_delegation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def forbidden_evaluator(*_: object, **__: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(
        "sim2claw.c922_exact_mode_calibration.materialize",
        forbidden_evaluator,
    )
    with pytest.raises(C922CalibrationError, match="exhausted"):
        run_authorized_evaluation(output_root=Path("/tmp/arbitrary"))
    assert called is False


@pytest.mark.parametrize(
    "mutation",
    [
        "retry",
        "evaluation_count",
        "evaluation_hash",
        "verdict",
        "missing",
        "receipt",
    ],
)
def test_control_fails_closed_on_guard_mutation(
    tmp_path: Path,
    mutation: str,
) -> None:
    payload = dict(EXPECTED_GUARD)
    if mutation == "retry":
        payload["retry_authorized"] = True
    elif mutation == "evaluation_count":
        payload["dataset_evaluations_used"] = 0
    elif mutation == "evaluation_hash":
        payload["evaluation_sha256"] = "0" * 64
    elif mutation == "verdict":
        payload["verdict"] = "exact_mode_intrinsics_and_distortion_verified"
    elif mutation == "missing":
        payload["missing_prerequisites"] = []
    else:
        payload["calibration_receipt_emitted"] = True
    path = tmp_path / GUARD_PATH.name
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(C922CalibrationError, match="changed"):
        load_exhaustion_guard(path)
