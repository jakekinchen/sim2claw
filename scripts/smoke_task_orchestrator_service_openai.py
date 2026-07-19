#!/usr/bin/env python3
"""Exercise the full orchestrator with a synthetic frame and the real model."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np

from sim2claw.orchestrator_frames import SnapshotFrame
from sim2claw.task_orchestrator import TaskOrchestratorService


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "orchestrator" / "b_mismatch.png"


class SyntheticRegisteredFrameAdapter:
    """One deterministic Silicon-contract-shaped frame; never opens hardware."""

    def __init__(self) -> None:
        self.closed = False

    def fetch(self) -> SnapshotFrame:
        if self.closed:
            raise RuntimeError("synthetic frame adapter is closed")
        image_bytes = FIXTURE_PATH.read_bytes()
        image = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise RuntimeError("synthetic fixture could not be decoded")
        now = datetime.now(UTC).isoformat()
        digest = hashlib.sha256(image_bytes).hexdigest()
        return SnapshotFrame(
            image_bytes=image_bytes,
            image_bgr=image,
            record={
                "schema_version": "sim2claw.orchestrator_frame_record.v1",
                "source_host": "silicon.local.net",
                "camera_role": "overhead_workspace",
                "capture_timestamp": now,
                "studio_receipt_timestamp": now,
                "width": 512,
                "height": 512,
                "encoding": "png",
                "byte_count": len(image_bytes),
                "sha256": digest,
                "freshness": {
                    "maximum_age_seconds": 10,
                    "age_seconds": 0.0,
                    "passed": True,
                },
                "roi_contract_id": "silicon_registered_board_100mm_v1",
                "workspace_pose_id": (
                    "workspace_board_fiducial_robotward_100mm_20260718_v3"
                ),
                "board_pose_id": "board_robotward_100mm_20260718_v3",
                "registration_error_pixels": 0.0,
                "fetch_duration_ms": 0.0,
                "error": None,
                "physical_authority": False,
            },
        )

    def close(self) -> None:
        self.closed = True


def main() -> int:
    source = SyntheticRegisteredFrameAdapter()
    service = TaskOrchestratorService(
        repo_root=ROOT,
        frame_adapter_factory=lambda: source,
        start_worker=False,
    )
    try:
        service.start({"mode": "observe_only"})
        service.process_pending_once()
        observed = service.snapshot()
        events = [row["event"] for row in observed["ledger"]]
        required_events = {"frame_accepted", "model_decision"}
        checks = {
            "exact_model_identity_verified": observed["model"]["identity_verified"]
            and observed["model"]["provider_model_id"] == "gpt-5.6-luna",
            "required_events_recorded": required_events <= set(events),
            "no_skill_execution": "skill_execution_started" not in events,
            "physical_authority_false": observed["physical_authority"] is False,
            "source_adapter_fixture_closed_after_stop": False,
        }
        turn = observed["model"].get("last_turn") or {}
        if observed["state"] != "STOPPED":
            service.stop("real_model_synthetic_frame_smoke_complete")
        terminal = service.snapshot()
        checks["source_adapter_fixture_closed_after_stop"] = source.closed
        checks["terminal_state_stopped"] = terminal["state"] == "STOPPED"
        checks["terminal_physical_authority_false"] = (
            terminal["physical_authority"] is False
        )
        ok = all(checks.values())
        print(
            json.dumps(
                {
                    "ok": ok,
                    "proof_class": "synthetic_registered_frame_with_live_openai_model",
                    "model": turn.get("model"),
                    "reasoning_effort": turn.get("reasoning_effort"),
                    "request_id": turn.get("request_id"),
                    "decision": (turn.get("decision") or {}).get("decision"),
                    "checks": checks,
                    "events": events,
                    "receipt_directory": observed["receipt_directory"],
                    "credential_printed": False,
                    "camera_live_verified": False,
                    "hardware_command_issued": False,
                    "physical_authority": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0 if ok else 4
    finally:
        service.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
