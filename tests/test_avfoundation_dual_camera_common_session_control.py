from __future__ import annotations

import json
from pathlib import Path

import pytest

from sim2claw.avfoundation_dual_camera_common_session_control import (
    EXPECTED_GUARD,
    GUARD_PATH,
    load_exhaustion_guard,
    run_authorized_observation,
)
from sim2claw.avfoundation_format_inventory import (
    AVFoundationFormatInventoryError,
)


def test_tracked_guard_matches_exact_terminal_accounting() -> None:
    assert load_exhaustion_guard() == EXPECTED_GUARD
    assert EXPECTED_GUARD["observation_attempts_used"] == 1
    assert EXPECTED_GUARD["observation_attempts_maximum"] == 1
    assert EXPECTED_GUARD["common_capture_sessions_used"] == 1
    assert EXPECTED_GUARD["retries_used"] == 0
    assert EXPECTED_GUARD["retry_authorized"] is False
    assert EXPECTED_GUARD["failed_gates"] == [
        "after_stop:c922_format_index",
        "after_stop:d405_format_index",
    ]


def test_control_refuses_before_any_device_delegation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def forbidden_runner(*_: object, **__: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(
        "sim2claw.avfoundation_dual_camera_common_session_v1.run_observation",
        forbidden_runner,
    )
    with pytest.raises(AVFoundationFormatInventoryError, match="exhausted"):
        run_authorized_observation(output_root=Path("/tmp/arbitrary"))
    assert called is False


@pytest.mark.parametrize(
    "mutation",
    ["retry", "attempt_count", "session_count", "receipt", "failed_gate"],
)
def test_control_fails_closed_on_guard_mutation(
    tmp_path: Path,
    mutation: str,
) -> None:
    payload = dict(EXPECTED_GUARD)
    if mutation == "retry":
        payload["retry_authorized"] = True
    elif mutation == "attempt_count":
        payload["observation_attempts_used"] = 0
    elif mutation == "session_count":
        payload["common_capture_sessions_used"] = 0
    elif mutation == "receipt":
        payload["receipt_sha256"] = "0" * 64
    else:
        payload["failed_gates"] = []
    path = tmp_path / GUARD_PATH.name
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(AVFoundationFormatInventoryError, match="changed"):
        load_exhaustion_guard(path)
