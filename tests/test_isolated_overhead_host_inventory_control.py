from __future__ import annotations

import json
from pathlib import Path

import pytest

from sim2claw.avfoundation_format_inventory import (
    AVFoundationFormatInventoryError,
)
from sim2claw.isolated_overhead_host_inventory_control import (
    EXPECTED_GUARD,
    GUARD_PATH,
    load_exhaustion_guard,
    run_authorized_observation,
)


def test_guard_matches_exact_attachment_required_result() -> None:
    assert load_exhaustion_guard() == EXPECTED_GUARD
    assert EXPECTED_GUARD["remote_inventory_observations_used"] == 1
    assert EXPECTED_GUARD["ssh_connection_attempts_used"] == 1
    assert EXPECTED_GUARD["capture_sessions_used"] == 0
    assert EXPECTED_GUARD["camera_frames_used"] == 0
    assert EXPECTED_GUARD["remote_files_written"] == 0
    assert EXPECTED_GUARD["retries_used"] == 0
    assert EXPECTED_GUARD["retry_authorized"] is False


def test_control_refuses_before_any_process_delegation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def forbidden_observation(*_: object, **__: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(
        "sim2claw.isolated_overhead_host_inventory_v1.run_observation",
        forbidden_observation,
    )
    with pytest.raises(AVFoundationFormatInventoryError, match="exhausted"):
        run_authorized_observation(output_root=Path("/tmp/arbitrary"))
    assert called is False


@pytest.mark.parametrize(
    "mutation",
    ["retry", "connection", "session", "receipt", "verdict"],
)
def test_control_fails_closed_on_guard_mutation(
    tmp_path: Path,
    mutation: str,
) -> None:
    payload = dict(EXPECTED_GUARD)
    if mutation == "retry":
        payload["retry_authorized"] = True
    elif mutation == "connection":
        payload["ssh_connection_attempts_used"] = 0
    elif mutation == "session":
        payload["capture_sessions_used"] = 1
    elif mutation == "receipt":
        payload["receipt_sha256"] = "0" * 64
    else:
        payload["verdict"] = "isolated_overhead_host_ready"
    path = tmp_path / GUARD_PATH.name
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(AVFoundationFormatInventoryError, match="changed"):
        load_exhaustion_guard(path)
