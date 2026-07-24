"""Post-terminal control plane for the exhausted common-session family."""

from __future__ import annotations

import json
from pathlib import Path
from typing import NoReturn

from sim2claw.avfoundation_format_inventory import (
    AVFoundationFormatInventoryError,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD_PATH = (
    REPO_ROOT
    / "configs/evaluations/"
    "avfoundation_dual_camera_common_session_v1_exhausted.json"
)
EXPECTED_GUARD = {
    "schema_version": (
        "sim2claw.avfoundation_dual_camera_common_session_exhaustion.v1"
    ),
    "contract_id": (
        "current-100mm-avfoundation-dual-camera-common-session-20260724-v1"
    ),
    "status": "terminal_callback_delivery_degraded_attempt_budget_exhausted",
    "contract_sha256": (
        "c2ad7c333e06affae037998318976931da638c5eec2806e769f9c2971f817af1"
    ),
    "observation_commit": "86d8005b5a97b2fc853be26db7db9b6788517525",
    "sealing_commit": "84dcdb1cbe853ced3e9cd41e63d6feb3b379abd2",
    "observation_attempts_used": 1,
    "observation_attempts_maximum": 1,
    "common_capture_sessions_used": 1,
    "retries_used": 0,
    "retry_authorized": False,
    "verdict": "common_session_callback_delivery_degraded",
    "failed_gates": [
        "after_stop:c922_format_index",
        "after_stop:d405_format_index",
    ],
    "prelaunch_sha256": (
        "c17f86dbc7dfa6b938c58b2355644d1a9fb25951923b2c8e77c946d513d1eb89"
    ),
    "attempt_sha256": (
        "e5c9e02e207f38c2c05b67d000928aeb41c51edf34fb3f3a4cf27a669b6968d5"
    ),
    "raw_observation_sha256": (
        "f78c363d3e45f4f6a191d8156f047e338d4ee786c9cb47fe10ab58af3b6a44d5"
    ),
    "evaluation_sha256": (
        "76cca950c1d696015ed31620dcbfd02f88aec65ba86c24b8e3f7051fc8aaea7b"
    ),
    "receipt_sha256": (
        "a33ada6551f297a5c1f95838716c1411b412d8fc4575a7c924f3b27889a4b53b"
    ),
    "receipt_digest": (
        "910f334722dbd56ccbc45bc610711e3c9c87b7c19936f1abe515a3e5cb9c2a4e"
    ),
}


def load_exhaustion_guard(path: Path = GUARD_PATH) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AVFoundationFormatInventoryError(
            f"Common-session exhaustion guard is unavailable: {error}"
        ) from error
    if payload != EXPECTED_GUARD:
        raise AVFoundationFormatInventoryError(
            "Common-session exhaustion guard changed."
        )
    return payload


def run_authorized_observation(*_: object, **__: object) -> NoReturn:
    """Refuse every post-terminal observation before device delegation."""

    load_exhaustion_guard()
    raise AVFoundationFormatInventoryError(
        "Dual-camera common-session family is exhausted; no retry is authorized."
    )
