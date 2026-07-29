from __future__ import annotations

import json
from pathlib import Path

from sim2claw.full_range_no_contact_execution_v2 import _load_packet


ROOT = Path(__file__).resolve().parents[1]
PACKET = (
    ROOT
    / "configs/hardware/full_range_no_contact_execution_v3_post_cable.json"
)


def test_post_cable_packet_reuses_exact_static_qualified_route() -> None:
    packet, route = _load_packet(PACKET)
    assert route.shape == (1105, 6)
    assert packet["physical_route"]["sha256"] == (
        "94381e4260cd638351e7eace26997826189e8952b2d297bcb199c0abe8cdbd92"
    )
    assert packet["hardware"]["configuration_token"] == (
        "owner-reported-wrist-camera-cable-relief-v1"
    )
    assert packet["acceptance"]["camera_cable_slack_review_required"] is True
    assert packet["maximum_executions"] == 1
    assert packet["physical_task_attempt"] is False
    assert packet["pawn_contact"] is False
    assert packet["mapping_approval"] is False
