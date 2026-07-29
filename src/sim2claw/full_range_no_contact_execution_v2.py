"""Reachable-pan adapter for the reviewed RP04C execution engine."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from . import full_range_no_contact_execution as _v1


def _load_packet(packet_path: Path) -> tuple[dict[str, Any], np.ndarray]:
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    _v1._require(
        packet.get("schema_version")
        == "sim2claw.full_range_no_contact_execution_packet.v2",
        "unexpected reachable-pan RP04C packet schema",
    )
    for entry in packet["inputs"].values():
        _v1._bound(entry)
    static = json.loads(
        _v1._bound(packet["inputs"]["static_receipt"]).read_text(
            encoding="utf-8"
        )
    )
    _v1._require(
        static["status"]
        == "full_range_no_contact_identification_static_pass"
        and static["passed"] is True
        and static["route_transform"]["shoulder_pan_target_degrees"] == -60.0
        and static["physical_task_attempts"] == 0
        and static["mapping_approved"] is False,
        "reachable-pan static route is not admitted",
    )
    route_entry: Mapping[str, Any] = packet["physical_route"]
    shape = tuple(int(value) for value in route_entry["shape"])
    route = np.fromfile(_v1._bound(route_entry), dtype="<f8")
    _v1._require(
        route.size == int(np.prod(shape)), "reachable-pan route shape changed"
    )
    route = np.asarray(route.reshape(shape), dtype="<f8", order="C")
    _v1._require(shape == (1105, 6), "reachable-pan denominator changed")
    _v1._require(
        route_entry["sha256"] == static["physical_route"]["sha256"],
        "reachable-pan route differs from static pass",
    )
    boundaries = [
        int(value) for value in packet["execution"]["segment_boundaries"]
    ]
    _v1._require(
        boundaries == [0, 33, 67, 500, 1104],
        "reachable-pan boundaries changed",
    )
    _v1._require(
        np.array_equal(
            route[0],
            np.asarray(packet["execution"]["expected_row_zero"], dtype="<f8"),
        ),
        "reachable-pan row zero changed",
    )
    _v1._require(
        packet["maximum_executions"] == 1
        and packet["physical_task_attempt"] is False
        and packet["pawn_contact"] is False
        and packet["mapping_approval"] is False,
        "reachable-pan packet widened authority",
    )
    return packet, route


def execute(**kwargs: Any) -> dict[str, Any]:
    """Run the V2 packet through the unchanged reviewed execution loop."""

    original = _v1._load_packet
    _v1._load_packet = _load_packet
    try:
        return _v1.execute(**kwargs)
    finally:
        _v1._load_packet = original


__all__ = ["_load_packet", "execute"]
