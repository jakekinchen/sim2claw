#!/usr/bin/env python3
"""Run one bounded real-provider smoke turn for the Task Orchestrator model."""

from __future__ import annotations

import atexit
import json
from pathlib import Path

import cv2

from sim2claw.orchestrator_model import (
    OpenAIOrchestratorModel,
    OrchestratorModelError,
    load_decision_schema,
)
from sim2claw.orchestrator_perception import (
    RegisteredSquareOccupancyClassifier,
    load_base_case_contract,
)
from sim2claw.orchestrator_skills import SkillRegistry
from sim2claw.task_orchestrator import _secret


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    config = json.loads(
        (ROOT / "configs" / "orchestrator" / "studio_task_orchestrator_v1.json").read_text(
            encoding="utf-8"
        )
    )
    decision_schema = load_decision_schema(
        ROOT / "configs" / "orchestrator" / "schemas" / "orchestrator_decision_v1.json"
    )
    model = OpenAIOrchestratorModel(
        config["model"],
        decision_schema,
        api_key=_secret(ROOT, config["model"]["api_key_environment_variable"]),
    )
    atexit.register(model.close)
    preflight = model.preflight(refresh=True)
    if not preflight["ready"]:
        print(
            json.dumps(
                {
                    "ok": False,
                    "stage": "exact_model_preflight",
                    "model": config["model"]["provider_model_id"],
                    "reasoning_effort": config["model"]["reasoning_effort"],
                    "error": preflight.get("error") or preflight.get("reason"),
                    "credential_printed": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 2

    contract = load_base_case_contract(
        ROOT / "configs" / "orchestrator" / "pawn_bg_diagonal_base_case_v1.json"
    )
    classifier = RegisteredSquareOccupancyClassifier(contract, config["perception"])
    frame_path = ROOT / "tests" / "fixtures" / "orchestrator" / "b_mismatch.png"
    frame_bytes = frame_path.read_bytes()
    frame = cv2.imread(str(frame_path))
    base_state = classifier.classify(
        frame,
        evidence_frame_sha256=__import__("hashlib").sha256(frame_bytes).hexdigest(),
    )
    registry = SkillRegistry.load(ROOT / config["task"]["skill_registry"])
    context = {
        "task_id": config["task"]["task_id"],
        "wake_reason": "real_provider_smoke_fixture",
        "session_state": "AWAITING_MODEL",
        "mode": "observe_only",
        "base_case_contract": contract.payload,
        "base_case_state": base_state,
        "newest_user_message": "Inspect the managed region and propose at most one bounded next step.",
        "recent_conversation": [],
        "recent_action_results": [],
        "allowlisted_skills": registry.public_rows(),
        "authority_limits": {
            "physical_authority": False,
            "executor_validation_required": True,
            "completion_owner": "deterministic_managed_region_checker",
        },
    }
    try:
        turn = model.decide(
            context=context,
            accepted_frame_bytes=frame_bytes,
            accepted_frame_encoding="png",
            reference_frame_bytes=(
                ROOT / config["perception"]["reference_image"]
            ).read_bytes(),
        )
    except OrchestratorModelError as error:
        print(
            json.dumps(
                {
                    "ok": False,
                    "stage": "structured_model_turn",
                    "model": config["model"]["provider_model_id"],
                    "error": error.receipt(),
                    "credential_printed": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 3
    print(
        json.dumps(
            {
                "ok": True,
                "model": turn["model"],
                "reasoning_effort": turn["reasoning_effort"],
                "request_id": turn["request_id"],
                "decision": turn["decision"],
                "validation": turn["validation"],
                "latency_ms": turn["latency_ms"],
                "usage": turn["usage"],
                "physical_authority": False,
                "credential_printed": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
