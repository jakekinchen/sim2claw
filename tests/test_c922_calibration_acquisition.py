from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path

import numpy as np
import pytest

from sim2claw import c922_calibration_acquisition as acquisition
from sim2claw.c922_calibration_acquisition import (
    DEFAULT_PLAN_PATH,
    acquire_corpus,
    preflight_acquisition,
)
from sim2claw.c922_exact_mode_calibration import (
    evaluate_manifest,
    load_contract,
    load_inputs,
    sha256_file,
)


def _plan() -> dict[str, object]:
    return json.loads(DEFAULT_PLAN_PATH.read_text(encoding="utf-8"))


def _write(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_pending_plan_reports_only_real_physical_inputs() -> None:
    report = preflight_acquisition()

    assert report["status"] == "blocked_physical_inputs"
    assert report["capture_ready"] is False
    assert report["frame_plan_valid"] is True
    assert report["frame_plan"]["split_counts"] == {
        "fit": 12,
        "validation": 3,
        "held_out": 3,
    }
    assert report["missing_physical_inputs"] == [
        "fixed_observable_focus_setting",
        "owner_approved_capture",
        "printed_grid_measurement_receipt",
        "printed_target_mounted_flat",
    ]
    assert report["motion_qualification_blockers"] == [
        "d405_cable_connector_strain_relief_repair"
    ]
    assert report["target_nominal_dimensions_are_metric_authority"] is False
    assert report["required_measured_dimensions"] == [
        "square_pitch_x_mm",
        "square_pitch_y_mm",
        "total_width_x_mm",
        "total_height_y_mm",
    ]
    assert report["camera_opened"] is False
    assert report["physical_authority"] is False


def test_frame_plan_drift_fails_before_capture(tmp_path: Path) -> None:
    plan = copy.deepcopy(_plan())
    plan["frame_slots"][17]["split"] = "fit"

    report = preflight_acquisition(_write(tmp_path, plan))

    assert report["status"] == "invalid_plan"
    assert report["frame_plan_valid"] is False
    assert "split_counts" in report["invalid_plan_reasons"]
    assert report["camera_sessions_used"] == 0


def test_nominal_target_values_cannot_substitute_for_measurement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(acquisition, "REPO_ROOT", tmp_path)
    contract = load_contract()
    receipt = {
        "schema_version": "sim2claw.printed_grid_measurement_receipt.v1",
        "measurement_id": "synthetic-test",
        "target_asset_sha256": contract["target"]["asset_sha256"],
        "square_pitch_x_mm": 20.0,
        "square_pitch_y_mm": 20.0,
        "total_width_x_mm": 200.0,
        "total_height_y_mm": 140.0,
        "instrument": "fixture-caliper",
        "instrument_resolution_mm": 0.01,
        "measurement_uncertainty_mm": 0.02,
        "measurement_points_description": "fixture endpoints",
        "measured_by": "fixture",
        "measured_at": "2026-07-24T00:00:00Z",
        "measurement_basis": "nominal_design_values",
        "nominal_values_substituted": True,
    }
    receipt_path = tmp_path / "measurement.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    plan = _plan()
    plan["target"]["printed_and_mounted_flat"] = True
    plan["target"]["measurement_receipt_path"] = str(receipt_path)
    plan["target"]["measurement_receipt_sha256"] = __import__(
        "hashlib"
    ).sha256(receipt_path.read_bytes()).hexdigest()

    report = preflight_acquisition(_write(tmp_path, plan))

    assert report["target_measurement_ready"] is False
    assert "physical_post_print_measurement_basis" in report[
        "missing_physical_inputs"
    ]
    assert "nominal_values_must_not_be_substituted" in report[
        "missing_physical_inputs"
    ]


def _corners(
    _path: Path, _inner: tuple[int, int], _size: tuple[int, int]
) -> np.ndarray:
    return np.asarray(
        [[180.0 + column * 30.0, 150.0 + row * 30.0] for row in range(6) for column in range(9)],
        dtype=np.float32,
    )


def _corpus_root() -> tuple[tempfile.TemporaryDirectory[str], Path]:
    temporary = tempfile.TemporaryDirectory(dir=acquisition.REPO_ROOT / "outputs")
    return temporary, Path(temporary.name) / "corpus"


def test_dry_run_completes_frozen_slots_and_is_consumed_fail_closed() -> None:
    temporary, output = _corpus_root()
    with temporary:
        result = acquire_corpus(
            DEFAULT_PLAN_PATH,
            output,
            dry_run=True,
            output_fn=lambda _message: None,
        )
        contract = load_contract()
        manifest = load_inputs(output / "inputs.json", contract=contract)
        evaluation = evaluate_manifest(
            contract,
            manifest,
            input_sha256=sha256_file(output / "inputs.json"),
        )
        assert result["split_counts"] == {"fit": 12, "validation": 3, "held_out": 3}
        assert result["fitting_performed"] is False
        assert evaluation["verdict"] == "calibration_evaluator_reject"
        assert evaluation["model_budget"]["used"] == 0


def test_live_capture_requires_measurement_focus_and_owner_approval() -> None:
    temporary, output = _corpus_root()
    touched: list[bool] = []
    with temporary, pytest.raises(ValueError, match="Physical inputs are incomplete"):
        acquire_corpus(
            DEFAULT_PLAN_PATH,
            output,
            capture_fn=lambda *_args: touched.append(True),
        )
    assert touched == []


@pytest.mark.parametrize("failure", ["mode", "missing", "duplicate", "held_out"])
def test_acquisition_fail_closed_boundaries(failure: str) -> None:
    temporary, output = _corpus_root()

    def capture(slot, attempt, camera, synthetic):
        row = dict(acquisition._synthetic_capture(slot, attempt, camera, synthetic))
        if failure == "mode":
            row["camera"]["format_index"] = 99
        if failure == "missing":
            Path(row["image_path"]).unlink()
        if failure == "duplicate":
            Path(row["image_path"]).write_bytes(b"duplicate")
        if failure == "held_out" and slot["split"] == "held_out":
            row["used_for_fit_or_selection"] = True
        return row

    expected = {
        "mode": "exact mode",
        "missing": "did not produce",
        "duplicate": "Duplicate frame",
        "held_out": "fit or selection",
    }[failure]
    with temporary, pytest.raises(ValueError, match=expected):
        acquire_corpus(
            DEFAULT_PLAN_PATH,
            output,
            dry_run=True,
            capture_fn=capture,
            detector_fn=_corners,
            output_fn=lambda _message: None,
        )


def test_rejected_view_never_advances_or_emits_manifest() -> None:
    temporary, output = _corpus_root()
    with temporary:
        with pytest.raises(ValueError, match="failed quality checks"):
            acquire_corpus(
                DEFAULT_PLAN_PATH,
                output,
                dry_run=True,
                capture_fn=acquisition._synthetic_capture,
                detector_fn=lambda *_args: None,
                output_fn=lambda _message: None,
                maximum_attempts=1,
            )
        assert not (output / "inputs.json").exists()
