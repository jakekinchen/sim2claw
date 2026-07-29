from __future__ import annotations

import hashlib
import json

from sim2claw.paths import REPO_ROOT


def _sha(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_closeout_binds_the_immutable_passing_receipt() -> None:
    decision = json.loads(
        (
            REPO_ROOT
            / "configs/decisions/canonical_task_plane_registration_closeout_v1.json"
        ).read_text(encoding="utf-8")
    )
    receipt_path = REPO_ROOT / decision["receipt"]["path"]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert _sha(receipt_path) == decision["receipt"]["sha256"]
    assert receipt["passed"] is True
    assert all(receipt["checks"].values())
    assert receipt["aggregate"] == {
        "reprojection_max_px": 6.471232275449458,
        "reprojection_rms_px": 4.684082912224784,
        "task_plane_max_mm": 7.104332681776422,
        "task_plane_rms_mm": 4.741722953437291,
    }
    assert decision["result"]["registration_prerequisite_satisfied"] is True
    assert decision["authority"]["physical_packet_authorized"] is False
    assert decision["authority"]["physical_motion_authorized"] is False
