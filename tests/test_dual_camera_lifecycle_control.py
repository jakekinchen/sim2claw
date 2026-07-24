from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from sim2claw import dual_camera_lifecycle_control as control


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT
    / "configs/evaluations/dual_camera_lifecycle_qualification_v1.json"
)
GUARD = (
    ROOT
    / "configs/evaluations/dual_camera_lifecycle_qualification_v1_exhausted.json"
)


def test_tracked_guard_is_exact_and_terminal() -> None:
    guard = control.load_exhaustion_guard(GUARD)

    assert guard == control.EXPECTED_GUARD
    assert guard["attempts_used"] == guard["attempts_maximum"] == 1
    assert guard["retries_used"] == 0
    assert guard["retry_authorized"] is False


def test_guard_blocks_any_output_root_before_runner_or_device_access(
    tmp_path: Path,
) -> None:
    called = False

    def runner(**_kwargs: Any) -> dict[str, Any]:
        nonlocal called
        called = True
        return {}

    with pytest.raises(control.DualCameraLifecycleControlError, match="exhausted"):
        control.run_once(
            contract_path=CONTRACT,
            output_root=tmp_path / "fresh-arbitrary-root",
            guard_path=GUARD,
            canonical_raw_root=tmp_path / "canonical",
            runner=runner,
        )
    assert called is False


def test_malformed_guard_fails_closed_before_runner(
    tmp_path: Path,
) -> None:
    guard = tmp_path / "guard.json"
    guard.write_text('{"status":"open"}\n', encoding="utf-8")
    called = False

    def runner(**_kwargs: Any) -> dict[str, Any]:
        nonlocal called
        called = True
        return {}

    with pytest.raises(
        control.DualCameraLifecycleControlError,
        match="identity or budget changed",
    ):
        control.run_once(
            contract_path=CONTRACT,
            output_root=tmp_path / "canonical",
            guard_path=guard,
            canonical_raw_root=tmp_path / "canonical",
            runner=runner,
        )
    assert called is False


def test_preterminal_control_requires_canonical_root_before_runner(
    tmp_path: Path,
) -> None:
    called = False

    def runner(**_kwargs: Any) -> dict[str, Any]:
        nonlocal called
        called = True
        return {}

    with pytest.raises(control.DualCameraLifecycleControlError, match="canonical"):
        control.run_once(
            contract_path=CONTRACT,
            output_root=tmp_path / "wrong",
            guard_path=tmp_path / "missing-guard.json",
            canonical_raw_root=tmp_path / "canonical",
            runner=runner,
        )
    assert called is False


def test_preterminal_control_delegates_once_at_canonical_root(
    tmp_path: Path,
) -> None:
    calls: list[dict[str, Any]] = []

    def runner(**kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {"status": "fixture"}

    canonical = tmp_path / "canonical"
    result = control.run_once(
        contract_path=CONTRACT,
        output_root=canonical,
        guard_path=tmp_path / "missing-guard.json",
        canonical_raw_root=canonical,
        runner=runner,
    )

    assert result == {"status": "fixture"}
    assert calls == [{"contract_path": CONTRACT, "output_root": canonical}]


def test_guard_json_matches_expected_bytes() -> None:
    assert json.loads(GUARD.read_text(encoding="utf-8")) == control.EXPECTED_GUARD

