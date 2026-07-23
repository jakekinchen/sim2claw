from __future__ import annotations

import json
import threading
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen

from sim2claw.studio_server import create_server
from sim2claw.studio_twin_fidelity import (
    DOMAIN_ORDER,
    load_twin_fidelity_projection,
    project_twin_fidelity,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
ACTION_SHA256 = "4" * 64


def _episode() -> dict[str, object]:
    return {
        "id": "selected-replay",
        "title": "Selected replay",
        "subtitle": "Action-frozen C2 replay",
        "action_array_sha256": ACTION_SHA256,
        "proof_class": "simulation_partial",
    }


def _observatory() -> dict[str, object]:
    return {
        "episodes": [
            {
                "id": "sail-episode",
                "action_array_sha256": ACTION_SHA256,
                "proof_class": "retained_action_frozen_simulation_partial",
                "proof_label": "Retained simulation · partial",
                "metrics": {
                    "joint_rms_degrees": 1.25,
                    "ee_rms_m": 0.011,
                    "final_target_distance_m": 0.01,
                },
                "availability": [
                    {"id": "pawn", "detail": "Physical pawn motion unavailable."},
                    {"id": "target", "detail": "Physical target unavailable."},
                    {"id": "timing", "detail": "Timing is phase-aligned."},
                    {"id": "contact", "detail": "Simulation contact only."},
                    {"id": "consequence", "detail": "Simulation consequence only."},
                ],
                "residual_cells": [
                    {
                        "channel": "selected_event_timing:near_closed_crossing",
                        "rmse": 1.45,
                    },
                    {
                        "channel": "selected_event_timing:release_onset",
                        "rmse": 0.152,
                    },
                ],
            }
        ],
        "twin_worthiness": {
            "level": "TW-REPLAY",
            "allowed_capabilities": ["diagnostics"],
            "denied_capabilities": ["training", "physical_authority"],
        },
    }


def _live_projection() -> dict[str, object]:
    receipt = {
        "action_sha256": ACTION_SHA256,
        "verdict": "evaluator_reject",
        "selected_intervention": "trusted_action_frozen_c2_factorial",
        "action_bytes_unchanged": True,
        "receipt_digest": "d" * 64,
        "budget": {"used_anchor_replays": 4},
    }
    outputs = {
        "residual_evidence": {"residuals": [{}, {}]},
        "mechanism_status": {
            "mechanisms": [
                {
                    "mechanism_id": "flexural_contact",
                    "family": "flexural contact",
                    "missing_observables": [
                        "jaw_force",
                        "rubber_cap_deformation_profile",
                    ],
                },
                {
                    "mechanism_id": "actuator_load_path",
                    "family": "actuator load path",
                    "missing_observables": ["jaw_force"],
                },
            ]
        },
        "acquisition_ranking": {
            "rows": [
                {
                    "kind": "measurement_acquisition",
                    "availability": "missing",
                    "intervention_id": "measurement_synchronized_force_deformation_probe",
                }
            ]
        },
        "posterior": {
            "before": {"flexural_contact": 0.5, "actuator_load_path": 0.5},
            "after": {"flexural_contact": 0.5, "actuator_load_path": 0.5},
            "observed_information_gain_bits": 0.0,
        },
        "consequence": {
            "status": "rejected_no_joint_mechanism_and_strict_task_ee_evidence",
            "strict_task_and_ee_pass_count": 0,
            "candidate_count": 4,
            "admitted_evaluator_owned_evidence": 0,
            "posterior_movement_permitted": False,
        },
    }
    evaluation = {
        "candidate_results": [
            {
                "candidate_id": "baseline",
                "anchor_evaluation": {
                    "trace_metrics": {
                        "overall_joint_rms_degrees": 1.2,
                        "ee_rms_m": 0.011,
                    }
                },
            }
        ],
        "main_effects": {
            "flexural_contact": 0.118,
            "actuator_load_path": -0.089,
        },
        "effect_evidence": {
            "flexural_contact": True,
            "actuator_load_path": True,
        },
    }
    return project_twin_fidelity(
        _episode(),
        _observatory(),
        live_receipt=receipt,
        live_outputs=outputs,
        live_verification={
            "receipt_sha256": "a" * 64,
            "campaign_state_sha256": "b" * 64,
        },
        adapter_evaluation=evaluation,
        adapter_thresholds={
            "maximum_joint_rms_degrees": 2.0,
            "maximum_ee_rms_m": 0.02,
        },
    )


def test_projection_orders_domains_and_keeps_missing_distinct_from_failed() -> None:
    projection = _live_projection()
    assert projection["available"] is True
    assert projection["evidence_status"] == "terminal_negative"
    assert projection["summary"]["verdict"] == "evaluator_reject"
    assert [row["id"] for row in projection["domains"]] == [
        row[0] for row in DOMAIN_ORDER
    ]
    statuses = {row["id"]: row["status"] for row in projection["domains"]}
    assert statuses["geometry_scale"] == "missing"
    assert statuses["contact_compliance"] == "missing"
    assert statuses["task_ee_consequence"] == "failed"
    strict = projection["domains"][-1]["measurements"][0]
    assert strict["value"] == 0
    assert strict["observed"] is True
    assert "percentage" not in json.dumps(projection).lower()
    assert "score" not in projection


def test_terminal_negative_keeps_posterior_and_authority_closed() -> None:
    projection = _live_projection()
    assert "Posterior belief remained unchanged" in projection["summary"]["detail"]
    assert projection["evaluator"]["observed_information_gain_bits"] == 0.0
    assert {row["status"] for row in projection["hypotheses"]} == {"unchanged"}
    assert projection["next_evidence"]["status"] == "missing"
    assert projection["authority"] == {
        "read_only": True,
        "training_admitted": False,
        "simulator_promotion": False,
        "physical_capture": False,
        "physical_authority": False,
        "robot_motion": False,
    }


def test_action_mismatch_does_not_attach_terminal_campaign_claims() -> None:
    projection = _live_projection()
    mismatched = project_twin_fidelity(
        {**_episode(), "action_array_sha256": "5" * 64},
        {
            **_observatory(),
            "episodes": [
                {
                    **_observatory()["episodes"][0],
                    "action_array_sha256": "5" * 64,
                }
            ],
        },
        live_receipt={"action_sha256": ACTION_SHA256},
        live_outputs={"posterior": {"before": {}, "after": {}}},
        live_verification={"receipt_sha256": "a" * 64},
        adapter_evaluation={"candidate_results": []},
    )
    assert projection["episode"]["action_binding"] == "byte_identical_campaign_match"
    assert mismatched["evidence_status"] == "episode_evidence_only"
    assert mismatched["receipt"]["verification"] == "unavailable"
    assert mismatched["evaluator"]["verdict"] is None


def test_invalid_observatory_receipt_fails_projection_closed() -> None:
    with patch(
        "sim2claw.studio_twin_fidelity.load_studio_observatory",
        side_effect=ValueError("observatory receipt digest changed"),
    ):
        projection = load_twin_fidelity_projection(_episode(), repo_root=REPO_ROOT)
    assert projection["available"] is False
    assert projection["reason"] == "sail_observatory_unavailable"
    assert {row["status"] for row in projection["domains"]} == {"missing"}
    assert "summary" not in projection


def test_invalid_live_receipt_never_synthesizes_terminal_claims() -> None:
    with (
        patch(
            "sim2claw.studio_twin_fidelity.load_studio_observatory",
            return_value=_observatory(),
        ),
        patch(
            "sim2claw.studio_twin_fidelity._load_live_bundle",
            side_effect=ValueError("live receipt output changed"),
        ),
    ):
        projection = load_twin_fidelity_projection(_episode(), repo_root=REPO_ROOT)
    assert projection["available"] is True
    assert projection["evidence_status"] == "episode_evidence_only"
    assert projection["summary"]["verdict"] == "no_action_matched_terminal_campaign"
    assert "live receipt output changed" in projection["summary"]["detail"]
    assert projection["evaluator"]["verdict"] is None
    assert projection["hypotheses"] == []


def test_server_projects_selected_episode_through_read_only_endpoint(
    tmp_path: Path,
) -> None:
    expected = _live_projection()
    with (
        patch(
            "sim2claw.studio_server.build_catalog",
            return_value={"episodes": [_episode()]},
        ),
        patch(
            "sim2claw.studio_server.load_twin_fidelity_projection",
            return_value=expected,
        ) as loader,
    ):
        server = create_server("127.0.0.1", 0, repo_root=tmp_path, read_only=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with urlopen(
                f"{base}/api/twin-fidelity?episode_id=selected-replay"
            ) as response:
                observed = json.load(response)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
    assert observed == expected
    loader.assert_called_once()


def test_replay_owns_twin_fidelity_navigation_and_read_only_drawer() -> None:
    html = (REPO_ROOT / "src/sim2claw/studio_web/index.html").read_text()
    css = (REPO_ROOT / "src/sim2claw/studio_web/studio.css").read_text()
    js = (REPO_ROOT / "src/sim2claw/studio_web/studio.js").read_text()

    nav = html.split('<nav class="view-switch"', 1)[1].split("</nav>", 1)[0]
    drawer = html.split('id="twin-fidelity-drawer"', 1)[1].split("</aside>", 1)[0]
    assert "/learning-factory.html" not in nav
    assert (REPO_ROOT / "src/sim2claw/studio_web/learning-factory.html").is_file()
    assert 'id="twin-fidelity-trigger"' in html
    assert 'aria-controls="twin-fidelity-drawer"' in html
    assert 'id="twin-fidelity-content"' in html
    assert "<form" not in drawer
    assert "fetch(`/api/twin-fidelity?episode_id=" in js
    assert 'event.key === "Escape" && state.drawer' in js
    assert "trigger?.focus({ preventScroll: true })" in js
    assert "@media (max-width: 620px)" in css
    assert ".twin-domain.is-missing" in css
    assert ".twin-domain.is-failed" in css
