from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from sim2claw.paths import REPO_ROOT
from sim2claw.replay_eligibility import (
    audit_and_write_exact_replay_manifest,
    audit_exact_replay_manifest,
)


FIXTURE = REPO_ROOT / "configs/replay/exact_replay_synthetic_fixture.json"


def _payload() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _write(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_synthetic_exact_replay_manifest_is_eligible(tmp_path: Path) -> None:
    output = tmp_path / "report.json"

    report = audit_and_write_exact_replay_manifest(FIXTURE, output)

    assert report["status"] == "admit"
    assert report["exact_replay_eligible"] is True
    assert report["requested_action_sha256"] == report["applied_action_sha256"]
    assert all(report["checks"].values())
    assert report["rejection_reasons"] == []
    assert report["proof_class"] == "synthetic_contract_fixture"
    assert report["evaluator_admission"] is False
    assert report["physical_authority"] is False
    assert json.loads(output.read_text(encoding="utf-8")) == report


@pytest.mark.parametrize(
    ("mutate", "code"),
    (
        (
            lambda payload: payload.__setitem__(
                "joint_order", list(reversed(payload["joint_order"]))
            ),
            "joint_order_mismatch",
        ),
        (
            lambda payload: payload["units"].__setitem__("action", "degree"),
            "units_mismatch",
        ),
        (
            lambda payload: payload["joint_transform"]["scale"].__setitem__(0, 1.01),
            "joint_transform_not_identity",
        ),
        (
            lambda payload: payload["initial_state"].pop("joint_velocity"),
            "initial_velocity_missing",
        ),
        (
            lambda payload: payload["timestamps_seconds"].__setitem__(2, 0.04),
            "timestamps_not_monotonic",
        ),
        (
            lambda payload: payload["applied_actions"][1].__setitem__(0, 0.03),
            "requested_applied_mismatch",
        ),
        (
            lambda payload: payload["modifications"].__setitem__("clipping", True),
            "action_modification_present",
        ),
        (
            lambda payload: payload.__setitem__(
                "requested_action_sha256", "0" * 64
            ),
            "requested_action_hash_mismatch",
        ),
    ),
)
def test_exact_replay_manifest_fails_closed(
    tmp_path: Path,
    mutate: object,
    code: str,
) -> None:
    payload = copy.deepcopy(_payload())
    mutate(payload)

    report = audit_exact_replay_manifest(_write(tmp_path, payload))

    assert report["status"] == "reject"
    assert report["exact_replay_eligible"] is False
    assert code in {reason["code"] for reason in report["rejection_reasons"]}
    assert report["evaluator_admission"] is False
    assert report["physical_authority"] is False
