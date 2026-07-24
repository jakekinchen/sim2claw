from __future__ import annotations

import json
from pathlib import Path

import pytest

from sim2claw import d405_capture_reliability as reliability


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "configs/evaluations/d405_capture_reliability_v1.json"


def _timing(*, fps: float, frame_count: int) -> dict[str, object]:
    interval = 1.0 / fps
    return {
        "schema_version": "sim2claw.video_container_timing.v1",
        "status": "observed_container_timing",
        "configured_fps": fps,
        "frame_count": frame_count,
        "first_pts_seconds": 0.0,
        "last_pts_seconds": (frame_count - 1) * interval,
        "nominal_interval_seconds": interval,
        "interval_seconds": {
            "minimum": interval,
            "median": interval,
            "p95": interval,
            "maximum": interval,
        },
        "non_monotonic_interval_count": 0,
        "duplicate_pts_count": 0,
        "large_gap_count": 0,
        "inferred_missing_frame_intervals": 0,
        "repeat_picture_count": 0,
        "semantics": {
            "camera_exposure_timestamps": False,
            "device_synchronized": False,
        },
    }


def _materialize_campaign(root: Path) -> None:
    contract = reliability.load_d405_reliability_contract(CONTRACT)
    events = []
    for index in range(1, 7):
        trial_id = f"trial-{index:02d}"
        trial = root / trial_id
        trial.mkdir(parents=True)
        (trial / "overhead_c922.mp4").write_bytes(f"overhead-{index}".encode())
        (trial / "wrist_d405.mkv").write_bytes(f"wrist-{index}".encode())
        artifact_sha256 = {
            filename: reliability._sha256_file(trial / filename)
            for filename in ("overhead_c922.mp4", "wrist_d405.mkv")
        }
        event = {
            "trial_id": trial_id,
            "attempt_index": index,
            "replacement": False,
            "robot_motion": False,
            "capture_error": None,
            "artifact_sha256": artifact_sha256,
            "reports": {
                "overhead": {
                    "status": "completed",
                    "failure_kind": None,
                },
                "wrist": {
                    "status": "completed",
                    "failure_kind": None,
                    "source_stall_detected": False,
                    "source_progress_status": "progressing",
                },
            },
        }
        reliability._write_json(trial / "capture_event.json", event)
        events.append(
            {
                "trial_id": trial_id,
                "attempt_index": index,
                "capture_event_sha256": reliability._sha256_file(
                    trial / "capture_event.json"
                ),
            }
        )
    campaign = {
        "schema_version": reliability.CAMPAIGN_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": reliability._sha256_file(CONTRACT),
        "runtime_identity": reliability.verify_d405_runtime_identity(contract),
        "proof_class": "camera_only_stationary_dual_stream_transport_health",
        "budget": {
            "required_consecutive_trials": 6,
            "used_trials": 6,
            "replacement_trials_allowed": 0,
            "replacement_trials_used": 0,
            "robot_motion_trials": 0,
            "provider_calls": 0,
        },
        "events": events,
        "authority": {
            "metric_depth": False,
            "motion_capture_reliability": False,
            "robot_motion": False,
            "simulator_replay": False,
            "training": False,
            "promotion": False,
            "task_score_change": False,
        },
    }
    reliability._write_json(root / "campaign.json", campaign)


def _fake_probe(path: Path, *, configured_fps: float) -> dict[str, object]:
    frame_count = 1200 if path.name == "overhead_c922.mp4" else 200
    return _timing(fps=configured_fps, frame_count=frame_count)


def test_contract_freezes_camera_only_budget_and_closed_authority() -> None:
    contract = reliability.load_d405_reliability_contract(CONTRACT)

    assert contract["qualification"]["required_consecutive_trials"] == 6
    assert contract["qualification"]["trial_duration_seconds"] == 40.0
    assert contract["qualification"]["replacement_trials"] == 0
    assert contract["qualification"]["motion_capture_reliability_claim"] is False
    assert not any(contract["authority"].values())


def test_evaluator_reprobes_raw_videos_and_is_byte_identical(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign = tmp_path / "campaign"
    _materialize_campaign(campaign)
    monkeypatch.setattr(reliability, "probe_video_container_timing", _fake_probe)

    evaluation_a, receipt_a = reliability.evaluate_d405_camera_only_qualification(
        contract_path=CONTRACT,
        campaign_root=campaign,
        output_root=tmp_path / "evaluation-a",
    )
    evaluation_b, receipt_b = reliability.evaluate_d405_camera_only_qualification(
        contract_path=CONTRACT,
        campaign_root=campaign,
        output_root=tmp_path / "evaluation-b",
    )

    assert evaluation_a == evaluation_b
    assert receipt_a == receipt_b
    assert (
        (tmp_path / "evaluation-a/evaluation.json").read_bytes()
        == (tmp_path / "evaluation-b/evaluation.json").read_bytes()
    )
    assert (
        (tmp_path / "evaluation-a/receipt.json").read_bytes()
        == (tmp_path / "evaluation-b/receipt.json").read_bytes()
    )
    assert evaluation_a["verdict"] == "pass_stationary_dual_camera_transport_health_only"
    assert evaluation_a["passed_trial_count"] == 6
    assert evaluation_a["claim_limits"] == {
        "stationary_camera_transport_health": True,
        "motion_capture_reliability": False,
        "metric_depth": False,
        "camera_exposure_timestamps": False,
        "device_synchronized": False,
        "robot_behavior": False,
        "simulator_calibration": False,
        "task_success": False,
    }
    assert len(receipt_a["raw_artifact_sha256"]) == 18
    assert receipt_a["receipt_digest"] == reliability._canonical_digest(
        {key: value for key, value in receipt_a.items() if key != "receipt_digest"}
    )


def test_evaluator_rejects_reported_source_stall_even_with_readable_video(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign = tmp_path / "campaign"
    _materialize_campaign(campaign)
    event_path = campaign / "trial-03/capture_event.json"
    event = json.loads(event_path.read_text(encoding="utf-8"))
    event["reports"]["wrist"]["source_stall_detected"] = True
    event["reports"]["wrist"]["source_progress_status"] = "stalled"
    reliability._write_json(event_path, event)
    manifest_path = campaign / "campaign.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["events"][2]["capture_event_sha256"] = reliability._sha256_file(
        event_path
    )
    reliability._write_json(manifest_path, manifest)
    monkeypatch.setattr(reliability, "probe_video_container_timing", _fake_probe)

    evaluation, _ = reliability.evaluate_d405_camera_only_qualification(
        contract_path=CONTRACT,
        campaign_root=campaign,
        output_root=tmp_path / "evaluation",
    )

    assert evaluation["verdict"] == "reject_stationary_capture_reliability"
    assert evaluation["passed_trial_count"] == 5
    assert evaluation["source_stall_count"] == 1
    assert evaluation["trials"][2]["failures"] == [
        "wrist_source_progress_failed"
    ]


@pytest.mark.parametrize(
    ("mutation", "match"),
    [
        ("replacement", "budget"),
        ("authority", "authority"),
        ("duplicate", "order or identity"),
    ],
)
def test_evaluator_rejects_budget_authority_and_replay_mutation(
    tmp_path: Path,
    mutation: str,
    match: str,
) -> None:
    campaign = tmp_path / "campaign"
    _materialize_campaign(campaign)
    manifest_path = campaign / "campaign.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if mutation == "replacement":
        manifest["budget"]["replacement_trials_used"] = 1
    elif mutation == "authority":
        manifest["authority"]["robot_motion"] = True
    else:
        manifest["events"][5]["trial_id"] = "trial-05"
    reliability._write_json(manifest_path, manifest)

    with pytest.raises(reliability.D405ReliabilityError, match=match):
        reliability.evaluate_d405_camera_only_qualification(
            contract_path=CONTRACT,
            campaign_root=campaign,
            output_root=tmp_path / "evaluation",
        )


def test_runner_refuses_existing_output_before_opening_cameras(
    tmp_path: Path,
) -> None:
    output = tmp_path / "existing"
    output.mkdir()

    with pytest.raises(reliability.D405ReliabilityError, match="already exists"):
        reliability.run_d405_camera_only_qualification(
            contract_path=CONTRACT,
            output_root=output,
        )
