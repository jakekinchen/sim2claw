from __future__ import annotations

import json
import hashlib
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / "configs/hardware/post_cable_safe_return_v1.json"


def test_safe_return_packet_binds_exact_static_route_and_no_task_authority() -> None:
    packet = json.loads(PACKET.read_text(encoding="utf-8"))
    for entry in packet["inputs"].values():
        path = ROOT / entry["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]
    route_entry = packet["physical_route"]
    route = np.fromfile(ROOT / route_entry["path"], dtype="<f8").reshape(
        route_entry["shape"]
    )
    assert (
        hashlib.sha256((ROOT / route_entry["path"]).read_bytes()).hexdigest()
        == route_entry["sha256"]
    )
    assert route.shape == (270, 6)
    assert packet["execution"]["stage_boundary_row"] == 135
    assert packet["execution"]["sample_hz"] == 20.0
    assert packet["maximum_executions"] == 1
    assert packet["physical_task_attempt"] is False
    assert packet["pawn_contact"] is False
    assert packet["mapping_approval"] is False
