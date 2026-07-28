from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sim2claw.real_to_sim_transfer import audit_source
from sim2claw.studio_catalog import _verified_phase_a_comparison


def _row(index: int) -> dict[str, object]:
    values = [float(index + offset) for offset in range(6)]
    return {
        "schema_version": "sim2claw.physical_teleoperation_sample.v1",
        "sample_index": index,
        "timestamp_monotonic_seconds": 0.05 * (index + 1),
        "follower_requested_degrees": values,
        "follower_command_degrees": values,
        "follower_actual_position_degrees": values,
        "precompiled_exact_action": False,
        "rate_limited": False,
        "safety_clamped": False,
        "observability_timestamps": {
            "actuator_application_or_ack_timestamp_available": False,
        },
    }


def test_source_audit_preserves_metadata_conflict_and_fails_exact_gate() -> None:
    receipt = {
        "mode": "physical_follower",
        "sample_count": 2,
        "label": "d1 to d2",
        "language_instruction": "Move b2 to b1",
        "source_square": "b2",
        "destination_square": "b1",
        "target_square_operator_metadata": "b1",
        "execution": {"action_dtype": "float32_replay_required"},
    }
    rows = [_row(0), _row(1)]
    rows[1]["follower_requested_degrees"] = [9.0] * 6
    rows[1]["rate_limited"] = True
    rows[1]["safety_clamped"] = True

    audit = audit_source(
        receipt,
        rows,
        visual_source_square="d1",
        visual_destination_square="d2",
    )

    assert audit["raw_metadata_conflict"] is True
    assert audit["raw_metadata"]["source_square"] == "b2"
    assert audit["requested_command_mismatch_count"] == 1
    assert audit["rate_limited_row_count"] == 1
    assert audit["safety_clamped_row_count"] == 1
    assert audit["exact_action_replay_eligible"] is False
    assert len(audit["exact_action_replay_blockers"]) >= 5
    assert len(audit["operator_requested_action"]["float32_little_endian_sha256"]) == 64
    assert len(audit["gateway_sent_action"]["float32_little_endian_sha256"]) == 64
    assert len(
        audit["observed_physical_joints"]["float64_little_endian_sha256"]
    ) == 64


def test_phase_a_catalog_admission_is_adjacent_and_hash_bound(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "datasets/manipulation_source_recordings/episode"
    directory.mkdir(parents=True)
    source_receipt_path = directory / "recording_receipt.json"
    source_receipt = {
        "recording_id": "fixture-recording",
        "samples_sha256": "a" * 64,
    }
    source_receipt_path.write_text(
        json.dumps(source_receipt, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    outputs = {}
    for name, content in (
        ("phase_a_comparison.mp4", b"video"),
        ("phase_a_comparison_poster.png", b"poster"),
        ("phase_a_kinematic_state_trace.json", b"trace"),
    ):
        (directory / name).write_bytes(content)
        outputs[name] = hashlib.sha256(content).hexdigest()
    comparison = {
        "schema_version": "sim2claw.studio_episode_comparison.v1",
        "phase": "A_real_to_sim",
        "selected_source": {
            "recording_id": "fixture-recording",
            "source_receipt_sha256": hashlib.sha256(
                source_receipt_path.read_bytes()
            ).hexdigest(),
            "samples_sha256": "a" * 64,
        },
        "visual_twin": {"available": True, "physics_authority": False},
        "physics_replay": {
            "available": False,
            "fail_closed": True,
            "simulator_applied_action_sha256": None,
        },
        "evaluator": {
            "phase_a_artifact_passed": True,
            "physics_lane_fail_closed": True,
            "physics_task_success": False,
        },
        "outputs": {
            "comparison_video_path": "phase_a_comparison.mp4",
            "comparison_video_sha256": outputs["phase_a_comparison.mp4"],
            "poster_path": "phase_a_comparison_poster.png",
            "poster_sha256": outputs["phase_a_comparison_poster.png"],
            "kinematic_state_trace_path": "phase_a_kinematic_state_trace.json",
            "kinematic_state_trace_sha256": outputs[
                "phase_a_kinematic_state_trace.json"
            ],
        },
    }
    comparison_path = directory / "phase_a_comparison_receipt.json"
    comparison_path.write_text(
        json.dumps(comparison, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    admitted = _verified_phase_a_comparison(
        source_receipt_path,
        source_receipt,
        "fixture-recording",
    )
    assert admitted["phase"] == "A_real_to_sim"

    (directory / "phase_a_comparison.mp4").write_bytes(b"tampered")
    assert (
        _verified_phase_a_comparison(
            source_receipt_path,
            source_receipt,
            "fixture-recording",
        )
        == {}
    )
