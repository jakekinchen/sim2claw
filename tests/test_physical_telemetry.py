from __future__ import annotations

import json
from pathlib import Path

import pytest

from sim2claw.learning_factory_artifacts import load_json_object
from sim2claw.physical_telemetry import (
    AVAILABLE_OBSERVATIONS,
    CLAIM_BOUNDARY,
    DEFAULT_CONTRACT_PATH,
    UNAVAILABLE_OBSERVATIONS,
    PhysicalTelemetryError,
    PhysicalTelemetrySession,
    load_physical_telemetry_contract,
    materialize_physical_telemetry,
)


def test_physical_telemetry_contract_and_comparison_are_deterministic(
    tmp_path: Path,
) -> None:
    contract = load_physical_telemetry_contract()
    assert contract["authority"]["physical_authority"] is False
    first = materialize_physical_telemetry(tmp_path / "first", render_plots=False)
    second = materialize_physical_telemetry(tmp_path / "second", render_plots=False)
    assert first["corpus_comparison_sha256"] == second["corpus_comparison_sha256"]
    assert first["episode_count"] == 18
    assert first["sample_count"] == 7741
    assert first["endpoint_frame_count"] == 36
    assert first["episode_outcome_counts"] == {"success": 18}
    assert first["comparison_scope"]["physical_command_vs_measured"] is True
    assert first["comparison_scope"]["real_vs_sim"] is False
    assert first["available_observations"] == list(AVAILABLE_OBSERVATIONS)
    assert set(first["unavailable_observations"]) == set(UNAVAILABLE_OBSERVATIONS)
    shoulder = first["aggregate_joint_comparisons"][0]
    assert shoulder["joint_name"] == "shoulder_pan"
    assert shoulder["measured_minus_commanded"]["count"] == 7741
    assert shoulder["measured_minus_commanded"]["rmse"] == pytest.approx(
        1.40569889141487
    )


def test_episode_session_exposes_recorded_values_and_fails_closed_on_missing_ones(
    tmp_path: Path,
) -> None:
    root = tmp_path / "telemetry"
    corpus = materialize_physical_telemetry(root, render_plots=False)
    episode = corpus["episodes"][0]
    session = PhysicalTelemetrySession(
        episode,
        root / "state" / episode["recording_id"],
        artifact_root=root,
        reset=True,
    )
    recording_id = episode["recording_id"]
    status = session.telemetry_status(recording_id)
    assert status["remaining_budgets"]["physical_actions"] == 0
    trace = session.read_joint_trace(recording_id, 0, 3)
    assert len(trace["rows"]) == 3
    assert len(trace["rows"][0]["commanded_joint_position"]) == 6
    assert "cached_between_nominal_5hz_reads" in trace["motor_current_semantics"]
    object_track = session.read_object_trajectory(recording_id)
    assert object_track == {
        "available": False,
        "non_null_selected_piece_pose_count": 0,
        "non_null_target_pose_count": 0,
        "reason": "metric_object_pose_fields_are_null",
    }
    timing = session.read_execution_timing(recording_id)
    assert timing["command_to_actuation_latency"]["available"] is False
    contact = session.read_contact_and_grasp_outcomes(recording_id)
    assert contact["physical_contact_state_available"] is False
    assert contact["episode_receipt_outcome"]["learned_policy_execution"] is False
    metadata, frame_path = session.read_camera_frame(recording_id, "initial")
    assert frame_path.is_file()
    assert metadata["measurement_semantics"] == "qualitative_endpoint_frame_not_metric_pose"

    receipt = session.submit_telemetry_audit(
        recording_id,
        {
            "available_observations": list(AVAILABLE_OBSERVATIONS),
            "unavailable_observations": list(UNAVAILABLE_OBSERVATIONS),
            "trace_comparison_sha256": status["trace_comparison_sha256"],
        },
        CLAIM_BOUNDARY,
    )
    assert receipt["audit_complete"] is True
    assert receipt["physical_actions"] == 0
    assert receipt["authority"]["physical_transfer_proof"] is False


def test_telemetry_contract_and_session_reject_authority_or_path_widening(
    tmp_path: Path,
) -> None:
    contract = load_json_object(DEFAULT_CONTRACT_PATH)
    contract["authority"]["physical_authority"] = True
    widened = tmp_path / "widened.json"
    widened.write_text(json.dumps(contract), encoding="utf-8")
    with pytest.raises(PhysicalTelemetryError, match="authority widened"):
        load_physical_telemetry_contract(widened)

    root = tmp_path / "telemetry"
    corpus = materialize_physical_telemetry(root, render_plots=False)
    episode = dict(corpus["episodes"][0])
    episode["trace_path"] = "../outside.json"
    with pytest.raises(PhysicalTelemetryError, match="escaped"):
        PhysicalTelemetrySession(
            episode,
            root / "state" / episode["recording_id"],
            artifact_root=root,
        )
