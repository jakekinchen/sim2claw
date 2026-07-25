from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from sim2claw import c922_calibration_acquisition as acquisition
from sim2claw.c922_calibration_acquisition import (
    DEFAULT_PLAN_PATH,
    preflight_acquisition,
)
from sim2claw.c922_exact_mode_calibration import load_contract


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
