from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from sim2claw import dual_camera_lifecycle as lifecycle


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = (
    ROOT
    / "configs"
    / "evaluations"
    / "dual_camera_lifecycle_qualification_v1.json"
)
RUNTIME = {
    "ffmpeg_path": "/fixture/ffmpeg",
    "ffmpeg_sha256": "a" * 64,
    "ffprobe_path": "/fixture/ffprobe",
    "ffprobe_sha256": "b" * 64,
}
IMPLEMENTATION = {
    path: str(index) * 64
    for index, path in enumerate(lifecycle.IMPLEMENTATION_PATHS, start=1)
}
REPOSITORY = {
    "head": "c" * 40,
    "tree": "d" * 40,
    "worktree_clean": True,
}


def _camera_identity() -> dict[str, Any]:
    contract = lifecycle.load_contract(CONTRACT)
    declared = contract["device_identity"]
    return {
        "avfoundation_names": [
            declared["c922_exact_name"],
            declared["d405_exact_name"],
        ],
        "d405_wrist": {
            "name": declared["d405_exact_name"],
            "unique_id": declared["d405_camera_unique_id"],
            "model_id": declared["d405_model_id"],
        },
        "c922_overhead": {
            "name": declared["c922_exact_name"],
            "unique_id": declared["c922_camera_unique_id"],
            "model_id": declared["c922_model_id"],
        },
    }


def _timing(*, fps: float, frames: int, missing: int = 0) -> dict[str, Any]:
    interval = 1.0 / fps
    return {
        "schema_version": "sim2claw.video_container_timing.v1",
        "status": "observed_container_timing",
        "frame_count": frames,
        "first_pts_seconds": 0.0,
        "last_pts_seconds": (frames - 1) * interval,
        "configured_fps": fps,
        "nominal_interval_seconds": interval,
        "interval_seconds": {
            "minimum": interval,
            "median": interval,
            "p95": interval,
            "maximum": interval,
        },
        "duplicate_pts_count": 0,
        "non_monotonic_interval_count": 0,
        "repeat_picture_count": 0,
        "large_gap_count": int(missing > 0),
        "inferred_missing_frame_intervals": missing,
        "semantics": {
            "camera_exposure_timestamps": False,
            "device_synchronized": False,
        },
    }


def _anchors() -> dict[str, float]:
    return {
        "d405_start_requested": 0.0,
        "d405_started": 1.0,
        "c922_start_requested": 1.0,
        "c922_started": 2.0,
        "common_window_started": 2.0,
        "common_window_stopped": 12.0,
        "c922_stop_requested": 12.0,
        "c922_stopped": 13.0,
        "d405_stop_requested": 13.0,
        "d405_stopped": 14.0,
    }


def _materialize_campaign(root: Path) -> None:
    contract = lifecycle.load_contract(CONTRACT)
    trial = root / "trial-01"
    trial.mkdir(parents=True)
    (trial / "overhead_c922.mp4").write_bytes(b"fixture-overhead")
    (trial / "wrist_d405.mkv").write_bytes(b"fixture-wrist")
    artifact_sha256 = {
        path.name: lifecycle._sha256_file(path)
        for path in sorted(trial.iterdir())
    }
    event = {
        "schema_version": lifecycle.EVENT_SCHEMA,
        "contract_id": contract["contract_id"],
        "attempt_index": 1,
        "replacement": False,
        "retry": False,
        "proof_class": lifecycle.PROOF_CLASS,
        "runtime_identity": RUNTIME,
        "implementation_identity": IMPLEMENTATION,
        "repository_identity": REPOSITORY,
        "camera_identity": _camera_identity(),
        "lifecycle_anchors_monotonic_seconds": _anchors(),
        "capture_error": None,
        "start_reports": {
            "d405_wrist": {
                "status": "recording",
                "camera_name": contract["device_identity"]["d405_exact_name"],
                "configured_width": 424,
                "configured_height": 240,
                "configured_fps": 5,
            },
            "c922_overhead": {
                "status": "recording",
                "camera_name": contract["device_identity"]["c922_exact_name"],
                "configured_width": 640,
                "configured_height": 480,
                "configured_fps": 30,
            },
        },
        "reports": {
            "d405_wrist": {
                "status": "completed",
                "source_stall_detected": False,
                "source_progress_status": "progressing",
            },
            "c922_overhead": {"status": "completed"},
        },
        "artifact_sha256": artifact_sha256,
        "authority": {
            "robot_gateway": False,
            "robot_motion": False,
            "simulator_replay": False,
            "provider_calls": 0,
            "training": False,
            "promotion": False,
            "task_score_change": False,
        },
    }
    event_path = trial / "capture_event.json"
    lifecycle._write_json(event_path, event)
    campaign = {
        "schema_version": lifecycle.CAMPAIGN_SCHEMA,
        "contract_id": contract["contract_id"],
        "contract_sha256": lifecycle._sha256_file(CONTRACT),
        "proof_class": lifecycle.PROOF_CLASS,
        "runtime_identity": RUNTIME,
        "implementation_identity": IMPLEMENTATION,
        "repository_identity": REPOSITORY,
        "event": {
            "attempt_index": 1,
            "path": "trial-01/capture_event.json",
            "sha256": lifecycle._sha256_file(event_path),
        },
        "budget": {
            "attempts_used": 1,
            "attempts_maximum": 1,
            "replacement_attempts_used": 0,
            "retries_used": 0,
            "d405_capture_sessions_used": 1,
            "c922_capture_sessions_used": 1,
            "robot_motion_trials_used": 0,
            "simulator_replays_used": 0,
            "provider_calls_used": 0,
        },
        "authority": {
            "motion_capture_reliability": False,
            "metric_depth": False,
            "exposure_synchronization": False,
            "robot_behavior": False,
            "simulator_calibration": False,
            "task_success": False,
        },
    }
    lifecycle._write_json(root / "campaign.json", campaign)


def _refresh_event_hash(root: Path) -> None:
    campaign_path = root / "campaign.json"
    campaign = json.loads(campaign_path.read_text(encoding="utf-8"))
    campaign["event"]["sha256"] = lifecycle._sha256_file(
        root / "trial-01/capture_event.json"
    )
    lifecycle._write_json(campaign_path, campaign)


def _patch_probes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lifecycle, "verify_runtime_identity", lambda _contract: RUNTIME)
    monkeypatch.setattr(lifecycle, "implementation_identity", lambda: IMPLEMENTATION)
    monkeypatch.setattr(
        lifecycle,
        "_probe_stream",
        lambda path, **_kwargs: {
            "codec_name": "h264" if path.suffix == ".mp4" else "ffv1",
            "width": 640 if path.suffix == ".mp4" else 424,
            "height": 480 if path.suffix == ".mp4" else 240,
            "pix_fmt": "fixture",
        },
    )
    monkeypatch.setattr(
        lifecycle,
        "probe_video_container_timing",
        lambda path, *, configured_fps, **_kwargs: _timing(
            fps=configured_fps,
            frames=300 if path.suffix == ".mp4" else 50,
        ),
    )


def test_contract_freezes_one_nested_stationary_session() -> None:
    contract = lifecycle.load_contract(CONTRACT)

    assert contract["lifecycle"]["start_order"] == [
        "d405_wrist",
        "c922_overhead",
    ]
    assert contract["lifecycle"]["stop_order"] == [
        "c922_overhead",
        "d405_wrist",
    ]
    assert contract["operation_budget"]["attempts_maximum"] == 1
    assert contract["operation_budget"]["retries_maximum"] == 0
    assert contract["authority"]["robot_motion"] is False
    assert contract["authority"]["simulator_replay"] is False


def test_evaluator_is_byte_identical_and_keeps_claims_narrow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign = tmp_path / "campaign"
    _materialize_campaign(campaign)
    _patch_probes(monkeypatch)

    evaluation_a, receipt_a = lifecycle.evaluate_qualification(
        contract_path=CONTRACT,
        campaign_root=campaign,
        output_root=tmp_path / "evaluation-a",
    )
    evaluation_b, receipt_b = lifecycle.evaluate_qualification(
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
    assert evaluation_a["verdict"] == (
        "pass_stationary_nested_dual_camera_lifecycle_health_only"
    )
    assert evaluation_a["failures"] == []
    assert evaluation_a["claim_limits"] == {
        "stationary_nested_camera_lifecycle_health": True,
        "motion_capture_reliability": False,
        "metric_depth": False,
        "camera_exposure_timestamps": False,
        "cross_camera_synchronization": False,
        "robot_behavior": False,
        "simulator_calibration": False,
        "task_success": False,
    }
    assert receipt_a["receipt_digest"] == lifecycle._canonical_digest(
        {key: value for key, value in receipt_a.items() if key != "receipt_digest"}
    )


def test_evaluator_rejects_lifecycle_inversion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign = tmp_path / "campaign"
    _materialize_campaign(campaign)
    event_path = campaign / "trial-01/capture_event.json"
    event = json.loads(event_path.read_text(encoding="utf-8"))
    event["lifecycle_anchors_monotonic_seconds"]["c922_start_requested"] = 0.5
    lifecycle._write_json(event_path, event)
    _refresh_event_hash(campaign)
    _patch_probes(monkeypatch)

    evaluation, _ = lifecycle.evaluate_qualification(
        contract_path=CONTRACT,
        campaign_root=campaign,
        output_root=tmp_path / "evaluation",
    )

    assert evaluation["verdict"] == (
        "reject_stationary_nested_dual_camera_lifecycle"
    )
    assert "nested_lifecycle_order_failed" in evaluation["failures"]


def test_evaluator_rejects_source_stall_and_pts_gap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    campaign = tmp_path / "campaign"
    _materialize_campaign(campaign)
    event_path = campaign / "trial-01/capture_event.json"
    event = json.loads(event_path.read_text(encoding="utf-8"))
    event["reports"]["d405_wrist"]["source_stall_detected"] = True
    event["reports"]["d405_wrist"]["source_progress_status"] = "stalled"
    lifecycle._write_json(event_path, event)
    _refresh_event_hash(campaign)
    _patch_probes(monkeypatch)
    monkeypatch.setattr(
        lifecycle,
        "probe_video_container_timing",
        lambda path, *, configured_fps, **_kwargs: _timing(
            fps=configured_fps,
            frames=300 if path.suffix == ".mp4" else 50,
            missing=1 if path.suffix == ".mp4" else 0,
        ),
    )

    evaluation, _ = lifecycle.evaluate_qualification(
        contract_path=CONTRACT,
        campaign_root=campaign,
        output_root=tmp_path / "evaluation",
    )

    assert "d405_wrist:source_progress_failed" in evaluation["failures"]
    assert "c922_overhead:inferred_missing_intervals" in evaluation["failures"]


@pytest.mark.parametrize("mutation", ["budget", "authority", "artifact", "extra_trial"])
def test_evaluator_fails_closed_on_raw_evidence_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    campaign = tmp_path / "campaign"
    _materialize_campaign(campaign)
    _patch_probes(monkeypatch)
    if mutation in {"budget", "authority"}:
        path = campaign / "campaign.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        if mutation == "budget":
            value["budget"]["retries_used"] = 1
        else:
            value["authority"]["task_success"] = True
        lifecycle._write_json(path, value)
    elif mutation == "artifact":
        (campaign / "trial-01/wrist_d405.mkv").write_bytes(b"changed")
    else:
        (campaign / "trial-02").mkdir()

    with pytest.raises(lifecycle.DualCameraLifecycleError):
        lifecycle.evaluate_qualification(
            contract_path=CONTRACT,
            campaign_root=campaign,
            output_root=tmp_path / "evaluation",
        )


def test_runner_uses_nested_order_and_one_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    class Clock:
        now = 0.0

        def read(self) -> float:
            return self.now

        def sleep(self, duration: float) -> None:
            self.now += duration

    class Recorder:
        def __init__(self, path: Path, role: str):
            self.path = path
            self.role = role

        def start(self) -> dict[str, Any]:
            events.append(f"{self.role}_start")
            self.path.write_bytes(self.role.encode())
            return {"status": "recording"}

        def ensure_running(self) -> None:
            return

        def finish(self, **_kwargs: Any) -> dict[str, Any]:
            events.append(f"{self.role}_finish")
            return {
                "status": "completed",
                "source_stall_detected": False,
                "source_progress_status": "progressing",
            }

    clock = Clock()
    monkeypatch.setattr(lifecycle, "verify_runtime_identity", lambda _contract: RUNTIME)
    monkeypatch.setattr(lifecycle, "inspect_camera_identity", lambda _contract: _camera_identity())
    monkeypatch.setattr(lifecycle, "implementation_identity", lambda: IMPLEMENTATION)
    monkeypatch.setattr(lifecycle, "repository_identity", lambda: REPOSITORY)

    campaign = lifecycle.run_qualification(
        contract_path=CONTRACT,
        output_root=tmp_path / "campaign",
        clock=clock.read,
        sleep=clock.sleep,
        overhead_factory=lambda path: Recorder(path, "c922"),
        wrist_factory=lambda path: Recorder(path, "d405"),
    )

    assert events == ["d405_start", "c922_start", "c922_finish", "d405_finish"]
    assert campaign["budget"]["attempts_used"] == 1
    assert campaign["budget"]["retries_used"] == 0


def test_runner_refuses_existing_output_before_device_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = tmp_path / "existing"
    output.mkdir()
    touched = False

    def runtime(_contract: dict[str, Any]) -> dict[str, str]:
        nonlocal touched
        touched = True
        return RUNTIME

    monkeypatch.setattr(lifecycle, "verify_runtime_identity", runtime)
    with pytest.raises(lifecycle.DualCameraLifecycleError, match="already exists"):
        lifecycle.run_qualification(
            contract_path=CONTRACT,
            output_root=output,
        )
    assert touched is False
