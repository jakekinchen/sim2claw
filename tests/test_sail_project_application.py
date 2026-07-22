from __future__ import annotations

import json
from pathlib import Path

from sim2claw.learning_factory_artifacts import sha256_file
from sim2claw.paths import REPO_ROOT
from sim2claw.sail.project_application import _candidate_status, _failure_flags


def test_failure_flags_preserve_transport_metric_blind_spot() -> None:
    row = {
        "bilateral_contact_observed": True,
        "qualified_bilateral_contact_observed": True,
        "piece_lifted": True,
        "lift_and_transport": False,
        "whole_base_inside_destination": False,
        "original_gate_results": {
            "upright": True,
            "settled": True,
            "released": True,
            "no_wrong_piece_contact": True,
            "collateral_within_limit": True,
        },
        "post_first_lift_task_diagnostic": {"destination_entry": {"source_index": 5}},
    }

    assert _failure_flags(row) == [
        "no_transport_while_above_lift_gate",
        "terminal_destination_containment_failure",
        "destination_entry_hidden_below_instantaneous_lift_gate",
    ]


def test_candidate_status_rejects_consequence_and_trace_regressions() -> None:
    baseline = {"strict_successes": 0, "lift_and_transport": 1, "lifted": 3}
    candidate = {
        "strict_successes": 0,
        "lift_and_transport": 0,
        "lifted": 2,
        "trace_metrics": {"overall_joint_rms_degrees": 1.3, "ee_rms_m": 0.02},
    }
    config = {
        "frozen_metrics": {
            "trace_guardrails": {
                "maximum_joint_rms_degrees": 1.2,
                "maximum_ee_rms_m": 0.01,
            }
        }
    }

    status, reasons = _candidate_status(
        name="candidate", summary=candidate, baseline=baseline, config=config
    )

    assert status == "rejected"
    assert reasons == [
        "lift_and_transport_regression",
        "lift_regression",
        "joint_trace_guard_failure",
        "ee_trace_guard_failure",
    ]


def test_static_studio_project_application_is_receipt_bound() -> None:
    publication = (
        REPO_ROOT
        / "src"
        / "sim2claw"
        / "studio_web"
        / "publication"
        / "sail_project_application_v1"
    )
    receipt = json.loads((publication / "receipt.json").read_text())
    manifest = json.loads((publication / "manifest.json").read_text())

    assert receipt["route"] == "/project-application.html"
    assert manifest["authority"]["read_only"]
    assert not manifest["authority"]["physical_authority"]
    for relative, expected in receipt["files"].items():
        assert sha256_file(REPO_ROOT / relative) == expected

    html = (REPO_ROOT / "src/sim2claw/studio_web/project-application.html").read_text()
    script = (REPO_ROOT / "src/sim2claw/studio_web/project-application.js").read_text()
    assert "Grasp-retention verdict" in html
    assert "/publication/sail_project_application_v1/manifest.json" in script
