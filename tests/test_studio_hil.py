from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import patch

from sim2claw.studio_catalog import _hil_identifiability_episodes


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _packet(
    root: Path,
    packet_id: str,
    *,
    admitted: bool,
    wrist_complete: bool,
) -> dict[str, object]:
    session = root / "runs/hil" / packet_id
    session.mkdir(parents=True)
    overhead = session / "overhead_c922.mp4"
    overhead.write_bytes(f"{packet_id}-overhead".encode())
    artifacts = {"overhead_c922.mp4": _sha(overhead)}
    if wrist_complete:
        wrist = session / "wrist_d405.browser.mp4"
        wrist.write_bytes(f"{packet_id}-wrist".encode())
        raw_wrist = session / "wrist_d405.mkv"
        raw_wrist.write_bytes(f"{packet_id}-raw-wrist".encode())
        artifacts.update(
            {
                "wrist_d405.browser.mp4": _sha(wrist),
                "wrist_d405.mkv": _sha(raw_wrist),
            }
        )
    failures = [] if admitted else ["wrist_video_not_completed"]
    return {
        "packet_id": packet_id,
        "session_relative": f"runs/hil/{packet_id}",
        "event": {"evaluation_sha256": "e" * 64},
        "raw": {
            "created_at": "2026-07-24T00:00:00+00:00",
            "action_tensor_sha256": "a" * 64,
            "artifact_sha256": artifacts,
        },
        "evaluation": {
            "admitted": admitted,
            "verdict": (
                "admit_unloaded_joint_measurement" if admitted else "reject_packet"
            ),
            "failures": failures,
        },
        "summary": {
            "actual_span_degrees": 20.0,
            "duration_seconds": 10.0,
            "tracking": {
                "requested_to_actual_best_lag": {
                    "lag_seconds": 0.15,
                    "lag_aligned_rmse": 0.6,
                }
            },
            "current_raw": {"p95_absolute": 2.0},
            "cameras": {
                "overhead": {
                    "status": "completed",
                    "duration_seconds": 10.0,
                    "frames": 300,
                },
                "wrist": {
                    "status": "completed" if wrist_complete else "failed",
                    "duration_seconds": 10.0 if wrist_complete else 0.0,
                },
            },
        },
    }


def test_hil_catalog_keeps_rejected_and_missing_camera_states_explicit(
    tmp_path: Path,
) -> None:
    packets = [
        _packet(tmp_path, "HIL-GRIPPER-05", admitted=True, wrist_complete=True),
        _packet(
            tmp_path,
            "HIL-WRIST-FLEX-30",
            admitted=False,
            wrist_complete=False,
        ),
    ]
    bundle = {
        "publication": {
            "physical": {
                "evidence_root": "outputs/evidence",
                "receipt_sha256": "r" * 64,
            }
        },
        "evidence_receipt": {"receipt_digest": "d" * 64},
        "packets": packets,
    }
    with patch(
        "sim2claw.studio_catalog.verify_hil_publication",
        return_value=bundle,
    ):
        episodes = _hil_identifiability_episodes(tmp_path)
    assert [row["status"] for row in episodes] == ["passed", "failed"]
    assert [len(row["recording_feeds"]) for row in episodes] == [2, 1]
    assert episodes[1]["camera"] == "overhead_only_wrist_evidence_unavailable"
    assert "wrist_video_not_completed" in episodes[1]["missing_evidence"]
    assert all(row["physical_task_success_verified"] is False for row in episodes)
    assert all(row["promotion_authority"] is False for row in episodes)


def test_hil_catalog_fails_closed_when_publication_is_invalid(tmp_path: Path) -> None:
    with patch(
        "sim2claw.studio_catalog.verify_hil_publication",
        side_effect=ValueError("summary hash changed"),
    ):
        assert _hil_identifiability_episodes(tmp_path) == []
