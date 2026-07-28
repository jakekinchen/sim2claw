from __future__ import annotations

import json
from pathlib import Path

import pytest

from sim2claw.metric_registration_readiness import (
    MetricRegistrationReadinessError,
)
from sim2claw.metric_registration_readiness_control import (
    EXPECTED_GUARD,
    GUARD_PATH,
    load_exhaustion_guard,
    run_authorized_evaluation,
)


def test_guard_matches_exact_terminal_missing_result() -> None:
    assert load_exhaustion_guard() == EXPECTED_GUARD
    assert EXPECTED_GUARD["verdict"] == "measurement_prerequisites_missing"
    assert len(EXPECTED_GUARD["missing_prerequisites"]) == 10
    assert EXPECTED_GUARD["invalid_input_count"] == 0
    assert EXPECTED_GUARD["readiness_evaluations_used"] == 1
    assert EXPECTED_GUARD["readiness_evaluations_maximum"] == 1
    assert EXPECTED_GUARD["camera_sessions_used"] == 0
    assert EXPECTED_GUARD["robot_motions_used"] == 0
    assert EXPECTED_GUARD["simulator_replays_used"] == 0
    assert EXPECTED_GUARD["retry_authorized"] is False


def test_control_refuses_before_evaluator_delegation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def forbidden_evaluator(*_: object, **__: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(
        "sim2claw.metric_registration_readiness.materialize",
        forbidden_evaluator,
    )
    with pytest.raises(MetricRegistrationReadinessError, match="exhausted"):
        run_authorized_evaluation(output_root=Path("/tmp/arbitrary"))
    assert called is False


@pytest.mark.parametrize(
    "mutation",
    ["retry", "evaluation_count", "receipt", "verdict", "missing"],
)
def test_control_fails_closed_on_guard_mutation(
    tmp_path: Path,
    mutation: str,
) -> None:
    payload = dict(EXPECTED_GUARD)
    if mutation == "retry":
        payload["retry_authorized"] = True
    elif mutation == "evaluation_count":
        payload["readiness_evaluations_used"] = 0
    elif mutation == "receipt":
        payload["receipt_sha256"] = "0" * 64
    elif mutation == "verdict":
        payload["verdict"] = "ready_for_separately_owned_metric_fit"
    else:
        payload["missing_prerequisites"] = []
    path = tmp_path / GUARD_PATH.name
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(MetricRegistrationReadinessError, match="changed"):
        load_exhaustion_guard(path)
