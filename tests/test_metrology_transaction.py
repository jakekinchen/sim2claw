from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from sim2claw import c922_calibration_acquisition as c922_acquisition
from sim2claw.cli import build_parser
from sim2claw.metrology_transaction import (
    DEFAULT_TRANSACTION_PATH,
    REPO_ROOT,
    MetrologyTransactionError,
    preflight_and_write,
    preflight_transaction,
)


def _transaction() -> dict[str, object]:
    return json.loads(DEFAULT_TRANSACTION_PATH.read_text(encoding="utf-8"))


def _write_transaction(tmp_path: Path, value: dict[str, object]) -> Path:
    path = tmp_path / "transaction.json"
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    return path


def test_default_transaction_is_blocked_without_camera_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_camera_opens(*args: object, **kwargs: object) -> object:
        raise AssertionError("camera opened during readiness")

    monkeypatch.setattr(c922_acquisition, "_native_burst", fail_if_camera_opens)
    report = preflight_transaction(DEFAULT_TRANSACTION_PATH)

    assert report["status"] == "blocked_physical_inputs"
    assert report["invalid_transaction_reasons"] == []
    assert report["p8"]["preflight"]["frame_plan"]["slot_count"] == 18
    assert report["p8"]["split_counts"] == {
        "fit": 12,
        "validation": 3,
        "held_out": 3,
    }
    assert {
        "printed_target_mounted_flat",
        "fixed_observable_c922_focus_setting",
        "18_exact_mode_c922_frame_receipts",
        "stationary_fixed_board_capture",
        "direct_board_measurement_receipt",
        "a1_h1_a8_physical_survey",
        "two_independent_eight_point_annotations",
    }.issubset(set(report["remaining_physical_inputs"]))
    assert report["authority"] == {
        "camera_opened": False,
        "camera_sessions_used": 0,
        "new_frames_captured": 0,
        "robot_motion_used": 0,
        "simulator_replays_used": 0,
        "provider_calls": 0,
        "training_rows": 0,
        "metric_fit_authorized": False,
        "evaluator_admission": False,
        "physical_authority": False,
        "task_success_verified": False,
    }


def test_transaction_rejects_split_drift_before_existing_preflight(
    tmp_path: Path,
) -> None:
    value = copy.deepcopy(_transaction())
    value["physical_inputs"]["c922_capture"]["split_counts"]["fit"] = 11  # type: ignore[index]
    path = _write_transaction(tmp_path, value)

    report = preflight_transaction(path, repo_root=REPO_ROOT)

    assert report["status"] == "invalid_transaction"
    assert "physical_c922_split_counts" in report["invalid_transaction_reasons"]
    assert report["authority"]["camera_opened"] is False


def test_transaction_rejects_bound_contract_hash_drift(
    tmp_path: Path,
) -> None:
    value = copy.deepcopy(_transaction())
    value["bindings"]["c922_calibration_contract"]["sha256"] = "0" * 64  # type: ignore[index]
    path = _write_transaction(tmp_path, value)

    report = preflight_transaction(path, repo_root=REPO_ROOT)

    assert report["status"] == "invalid_transaction"
    assert "c922_calibration_contract_hash" in report["invalid_transaction_reasons"]


def test_preflight_write_is_content_addressed_and_non_replayable(tmp_path: Path) -> None:
    output = REPO_ROOT / "tmp" / f"metrology-readiness-{tmp_path.name}.json"
    try:
        report = preflight_and_write(
            DEFAULT_TRANSACTION_PATH,
            output,
            repo_root=REPO_ROOT,
        )

        assert output.is_file()
        persisted = json.loads(output.read_text(encoding="utf-8"))
        assert persisted["transaction_sha256"] == report["transaction_sha256"]
        with pytest.raises(MetrologyTransactionError, match="replay is forbidden"):
            preflight_and_write(DEFAULT_TRANSACTION_PATH, output, repo_root=REPO_ROOT)
    finally:
        output.unlink(missing_ok=True)


def test_cli_exposes_readiness_only_transaction() -> None:
    args = build_parser().parse_args(
        [
            "metrology-transaction-preflight",
            "--transaction",
            str(DEFAULT_TRANSACTION_PATH),
            "--output",
            "runs/metrology-readiness.json",
        ]
    )

    assert args.command == "metrology-transaction-preflight"
    assert args.transaction == DEFAULT_TRANSACTION_PATH
