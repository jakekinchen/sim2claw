from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from inspect_robots import read_eval_log

from sim2claw.inspect_robots_adapter import (
    DEFAULT_FIXTURE_PATH,
    PROOF_CLASS,
    InspectRobotsIntegrationError,
    run_offline_slice,
)


def _fixture() -> dict[str, object]:
    return json.loads(DEFAULT_FIXTURE_PATH.read_text(encoding="utf-8"))


def _write_fixture(tmp_path: Path, payload: dict[str, object]) -> Path:
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_offline_eval_log_preserves_actions_cameras_and_closed_authority(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "logs"

    report = run_offline_slice(output_dir=output_dir)
    log = read_eval_log(report["eval_log_path"])
    provenance = log.samples[0].trial_metadata[0]["sim2claw"]

    assert report["status"] == "pass"
    assert report["proof_class"] == PROOF_CLASS
    assert report["evaluator_admission"] is False
    assert report["physical_authority"] is False
    assert report["gateway_invoked"] is False
    assert report["requested_applied_sequence_exact"] is True
    assert report["task_success_claimed"] is False
    assert set(report["camera_roles"]) == {"top", "wrist"}
    assert provenance["requested_action_sequence_sha256"] == provenance[
        "applied_action_sequence_sha256"
    ]
    assert all(
        transition["requested_action_sha256"]
        == transition["applied_action_sha256"]
        for transition in provenance["transitions"]
    )
    assert all(
        set(transition["camera_refs"]) == {"top", "wrist"}
        for transition in provenance["transitions"]
    )


def test_requested_applied_divergence_survives_the_eval_log(tmp_path: Path) -> None:
    payload = copy.deepcopy(_fixture())
    payload["actions"][1]["applied_action_rad"][0] = 0.041
    fixture_path = _write_fixture(tmp_path, payload)

    report = run_offline_slice(
        fixture_path=fixture_path,
        output_dir=tmp_path / "logs",
    )
    log = read_eval_log(report["eval_log_path"])
    provenance = log.samples[0].trial_metadata[0]["sim2claw"]

    assert report["requested_applied_sequence_exact"] is False
    assert provenance["transitions"][0]["requested_applied_exact"] is True
    assert provenance["transitions"][1]["requested_applied_exact"] is False
    assert provenance["transitions"][1]["requested_action_sha256"] != provenance[
        "transitions"
    ][1]["applied_action_sha256"]
    assert provenance["transitions"][2]["requested_applied_exact"] is True


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("physical_authority", True, "cannot grant physical authority"),
        ("evaluator_admission", True, "cannot grant evaluator admission"),
    ),
)
def test_offline_fixture_rejects_promoted_authority_or_admission(
    tmp_path: Path,
    field: str,
    value: bool,
    message: str,
) -> None:
    payload = _fixture()
    payload[field] = value
    fixture_path = _write_fixture(tmp_path, payload)
    output_dir = tmp_path / "logs"

    with pytest.raises(InspectRobotsIntegrationError, match=message):
        run_offline_slice(fixture_path=fixture_path, output_dir=output_dir)

    assert not output_dir.exists()
