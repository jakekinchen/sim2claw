from __future__ import annotations

import copy
import hashlib
import json
import shutil
import tempfile
import threading
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import cv2

from sim2claw.orchestrator_frames import (
    FrameSourceError,
    LocalOverheadSnapshotAdapter,
    SiliconOverheadSnapshotAdapter,
    SnapshotFrame,
    SnapshotResponse,
    load_snapshot_contract,
    normalized_luminance_ssim,
    prepare_registered_roi,
)
from sim2claw.orchestrator_model import (
    JSONResponse,
    OpenAIOrchestratorModel,
    OrchestratorModelError,
    SYSTEM_PROMPT,
    load_decision_schema,
    validate_decision,
)
from sim2claw.orchestrator_perception import (
    RegisteredSquareOccupancyClassifier,
    load_base_case_contract,
)
from sim2claw.orchestrator_skills import (
    OneAtATimeSkillDispatcher,
    SkillRegistry,
    SkillRegistryError,
)
from sim2claw.studio_server import create_server
from sim2claw.task_orchestrator import TaskOrchestratorService


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "orchestrator"
CONFIG_PATH = ROOT / "configs" / "orchestrator" / "studio_task_orchestrator_v1.json"


def _fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _frame(name: str, sequence: int) -> SnapshotFrame:
    payload = _fixture_bytes(name)
    image = cv2.imdecode(
        __import__("numpy").frombuffer(payload, dtype=__import__("numpy").uint8),
        cv2.IMREAD_COLOR,
    )
    digest = hashlib.sha256(payload).hexdigest()
    return SnapshotFrame(
        payload,
        image,
        {
            "schema_version": "sim2claw.orchestrator_frame_record.v1",
            "source_host": "silicon.local.net",
            "camera_role": "overhead_workspace",
            "capture_timestamp": (datetime.now(UTC) + timedelta(microseconds=sequence)).isoformat(),
            "studio_receipt_timestamp": datetime.now(UTC).isoformat(),
            "width": 512,
            "height": 512,
            "encoding": "png",
            "byte_count": len(payload),
            "sha256": digest,
            "freshness": {"maximum_age_seconds": 10, "age_seconds": 0, "passed": True},
            "roi_contract_id": "silicon_registered_board_100mm_v1",
            "workspace_pose_id": "workspace_board_fiducial_robotward_100mm_20260718_v3",
            "board_pose_id": "board_robotward_100mm_20260718_v3",
            "registration_error_pixels": 0.0,
            "fetch_duration_ms": 0.2,
            "error": None,
            "physical_authority": False,
        },
    )


class FixtureFrameAdapter:
    def __init__(self, names: list[str]) -> None:
        self.names = names
        self.index = 0
        self.closed = False

    def fetch(self) -> SnapshotFrame:
        if self.closed:
            raise FrameSourceError("closed", "fixture adapter closed")
        index = min(self.index, len(self.names) - 1)
        self.index += 1
        return _frame(self.names[index], self.index)

    def close(self) -> None:
        self.closed = True


class FaultFrameAdapter(FixtureFrameAdapter):
    def __init__(self, code: str = "source_unavailable") -> None:
        super().__init__([])
        self.code = code

    def fetch(self) -> SnapshotFrame:
        raise FrameSourceError(self.code, f"fixture frame fault: {self.code}")


class OneFrameThenFaultAdapter(FixtureFrameAdapter):
    def fetch(self) -> SnapshotFrame:
        if self.index > 0:
            raise FrameSourceError("stale_frame", "fixture stale frame")
        return super().fetch()


class BlockingFrameAdapter(FixtureFrameAdapter):
    def __init__(self, name: str = "b_mismatch.png") -> None:
        super().__init__([name])
        self.started = threading.Event()
        self.release = threading.Event()

    def fetch(self) -> SnapshotFrame:
        self.started.set()
        self.release.wait(2.0)
        return super().fetch()

    def close(self) -> None:
        self.release.set()
        super().close()


def _decision(kind: str = "observe", **values: Any) -> dict[str, Any]:
    return {
        "decision": kind,
        "reason": values.get("reason", "bounded fixture decision"),
        "skill_id": values.get("skill_id"),
        "arguments": values.get("arguments", {}),
        "expected_postcondition": values.get("expected_postcondition", {}),
        "confidence": values.get("confidence", 0.9),
    }


class FixtureModel:
    def __init__(self, *, restore: bool = False) -> None:
        self.restore = restore
        self.calls = 0
        self.closed = False

    def decide(self, *, context: Mapping[str, Any], **_kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        if self.restore:
            move = context["base_case_state"]["suggested_moves"][0]
            decision = _decision(
                "run_skill",
                skill_id=move["skill_id"],
                arguments={
                    "source_square": move["source_square"],
                    "destination_square": move["destination_square"],
                },
                expected_postcondition=move["expected_postcondition"],
            )
        else:
            decision = _decision()
        return {
            "schema_version": "sim2claw.orchestrator_model_turn.v1",
            "request_id": f"fixture-{self.calls}",
            "model": "gpt-5.6-luna",
            "decision": decision,
            "validation": {"valid": True},
            "usage": {},
            "cost": {"amount": None},
            "physical_authority": False,
        }

    def close(self) -> None:
        self.closed = True


class FaultModel(FixtureModel):
    def decide(self, **_kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        raise OrchestratorModelError(
            "invalid_model_output", "Fixture model returned malformed output."
        )


class CompleteClaimModel(FixtureModel):
    def decide(self, **_kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        return {
            "schema_version": "sim2claw.orchestrator_model_turn.v1",
            "request_id": f"fixture-{self.calls}",
            "model": "gpt-5.6-luna",
            "decision": _decision("complete", reason="Fixture model claimed completion."),
            "validation": {"valid": True},
            "usage": {},
            "cost": {"amount": None},
            "physical_authority": False,
        }


class CrossFileProposalModel(FixtureModel):
    def decide(self, **_kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        return {
            "schema_version": "sim2claw.orchestrator_model_turn.v1",
            "request_id": f"fixture-{self.calls}",
            "model": "gpt-5.6-luna",
            "decision": _decision(
                "run_skill",
                skill_id="pawn_b2_to_b1",
                arguments={"source_square": "b2", "destination_square": "c1"},
                expected_postcondition={"occupied": ["c1"], "empty": ["b2"]},
            ),
            "validation": {"valid": True},
            "usage": {},
            "cost": {"amount": None},
            "physical_authority": False,
        }


class BlockingModel(FixtureModel):
    def __init__(self) -> None:
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()

    def decide(self, **_kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        self.started.set()
        self.release.wait(2.0)
        return {
            "schema_version": "sim2claw.orchestrator_model_turn.v1",
            "request_id": f"fixture-{self.calls}",
            "model": "gpt-5.6-luna",
            "decision": _decision("observe"),
            "validation": {"valid": True},
            "usage": {},
            "cost": {"amount": None},
            "physical_authority": False,
        }

    def close(self) -> None:
        self.release.set()
        super().close()


class FixtureSkillAdapter:
    def __init__(self, counter: dict[str, int]) -> None:
        self.counter = counter

    def execute(
        self, request: Mapping[str, Any], stop_event: threading.Event
    ) -> Mapping[str, Any]:
        self.counter["active"] += 1
        self.counter["max_active"] = max(self.counter["max_active"], self.counter["active"])
        self.counter["calls"] += 1
        try:
            if stop_event.is_set():
                raise RuntimeError("fixture stopped")
            return {"trace_id": f"fixture-trace-{self.counter['calls']}", "request": dict(request)}
        finally:
            self.counter["active"] -= 1

    def safe_stop(self) -> Mapping[str, Any]:
        return {"requested": True, "fixture_stopped": True}


class TimeoutSkillAdapter:
    def execute(
        self, _request: Mapping[str, Any], stop_event: threading.Event
    ) -> Mapping[str, Any]:
        stop_event.wait(1.0)
        return {"stopped": stop_event.is_set()}

    def safe_stop(self) -> Mapping[str, Any]:
        return {"requested": True, "fixture_stopped": True}


class FailingSkillAdapter:
    def execute(
        self, _request: Mapping[str, Any], _stop_event: threading.Event
    ) -> Mapping[str, Any]:
        raise RuntimeError("fixture skill failure")

    def safe_stop(self) -> Mapping[str, Any]:
        return {"requested": True, "fixture_stopped": True}


class BlockingSkillAdapter:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.release = threading.Event()

    def execute(
        self, _request: Mapping[str, Any], stop_event: threading.Event
    ) -> Mapping[str, Any]:
        self.started.set()
        self.release.wait(2.0)
        if stop_event.is_set():
            raise RuntimeError("fixture stopped while active")
        return {"completed": True}

    def safe_stop(self) -> Mapping[str, Any]:
        self.release.set()
        return {"requested": True, "fixture_stopped": True}


class UnstoppableSkillAdapter:
    def __init__(self) -> None:
        self.release = threading.Event()

    def execute(
        self, _request: Mapping[str, Any], _stop_event: threading.Event
    ) -> Mapping[str, Any]:
        self.release.wait(2.0)
        return {"released": True}

    def safe_stop(self) -> Mapping[str, Any]:
        raise RuntimeError("fixture safe-stop failure")


class FakeClock:
    def __init__(self) -> None:
        self.value = 1000.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def _copy_runtime_configs(destination: Path) -> Path:
    shutil.copytree(ROOT / "configs", destination / "configs")
    return destination / "configs" / "orchestrator" / "studio_task_orchestrator_v1.json"


def _ready_dispatcher(
    config_root: Path, *, execution_modes: list[str] | None = None
) -> tuple[OneAtATimeSkillDispatcher, dict[str, int]]:
    path = config_root / "configs" / "orchestrator" / "studio_task_orchestrator_skills_v1.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    for index, skill in enumerate(payload["skills"]):
        skill.update(
            {
                "checkpoint_sha256": f"{index + 1:064x}",
                "evaluator_receipt_sha256": f"{index + 101:064x}",
                "promotion_receipt_sha256": f"{index + 201:064x}",
                "execution_modes": execution_modes or ["simulation"],
                "readiness": "promoted_fixture_only",
                "callable": True,
            }
        )
    registry = SkillRegistry(payload)
    counter = {"active": 0, "max_active": 0, "calls": 0}
    adapters = {
        skill_id: FixtureSkillAdapter(counter) for skill_id in registry.entries
    }
    return OneAtATimeSkillDispatcher(registry, adapters), counter


class ContractAndPerceptionTests(unittest.TestCase):
    def test_base_case_contract_is_exact_and_partitioned(self) -> None:
        contract = load_base_case_contract(
            ROOT / "configs" / "orchestrator" / "pawn_bg_diagonal_base_case_v1.json"
        )
        self.assertEqual(contract.managed_files, tuple("bcdefg"))
        self.assertEqual(contract.managed_ranks, (1, 2))
        self.assertEqual(
            contract.required_occupied,
            frozenset({"b1", "c2", "d1", "e2", "f1", "g2"}),
        )
        self.assertEqual(len(contract.managed_squares), 12)

    def test_fixture_result_and_physical_canary_contracts_are_frozen_closed(self) -> None:
        fixture_manifest = json.loads(
            (
                ROOT
                / "configs"
                / "orchestrator"
                / "fixtures"
                / "fixture_manifest_v1.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            fixture_manifest["schema_version"],
            "sim2claw.orchestrator_fixture_manifest.v1",
        )
        negative_ids = {row["case_id"] for row in fixture_manifest["negative_cases"]}
        self.assertTrue(
            {
                "stale_frame",
                "camera_registration_drift",
                "missing_pawn",
                "two_pawns_in_file",
                "malformed_model_output",
                "unavailable_skill",
                "skill_timeout",
            }.issubset(negative_ids)
        )
        for group in ("positive_cases", "restoration_cases", "negative_cases"):
            for case in fixture_manifest[group]:
                for relative_path in case.get("frames", []):
                    self.assertTrue((ROOT / relative_path).is_file(), relative_path)
        self.assertFalse(fixture_manifest["authority"]["physical_authority"])

        gate = json.loads(
            (
                ROOT / "configs" / "orchestrator" / "physical_canary_gate_v1.json"
            ).read_text(encoding="utf-8")
        )
        self.assertFalse(gate["physical_authority"])
        self.assertFalse(gate["shadow_protocol"]["issues_hardware_command"])
        self.assertFalse(gate["canary"]["enabled"])
        self.assertTrue(gate["operator_approval"]["required_per_action"])
        self.assertEqual(
            gate["required_new_physical_evaluator"]["status"],
            "contract_frozen_implementation_not_enabled",
        )

        physical_evaluator = json.loads(
            (
                ROOT
                / "configs"
                / "orchestrator"
                / "physical_pawn_bg_canary_evaluator_v1.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            physical_evaluator["schema_version"],
            "sim2claw.orchestrator_physical_evaluator.v1",
        )
        self.assertFalse(physical_evaluator["physical_authority"])
        self.assertFalse(physical_evaluator["enablement"]["enabled"])
        self.assertTrue(
            physical_evaluator["operator_approval_schema"]["single_use"]
        )
        self.assertEqual(physical_evaluator["runtime_gates"]["maximum_actions"], 1)
        self.assertTrue(
            physical_evaluator["post_action_gates"]["torque_off_receipt_required"]
        )

        result_schema = json.loads(
            (
                ROOT
                / "configs"
                / "orchestrator"
                / "schemas"
                / "orchestrator_result_v1.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(result_schema["$id"], "sim2claw.orchestrator_result.v1")
        self.assertEqual(
            result_schema["properties"]["physical_authority"]["const"], False
        )

    def test_square_classifier_separates_similarity_from_base_case(self) -> None:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        contract = load_base_case_contract(
            ROOT / "configs" / "orchestrator" / "pawn_bg_diagonal_base_case_v1.json"
        )
        classifier = RegisteredSquareOccupancyClassifier(contract, config["perception"])
        base = cv2.imread(str(FIXTURES / "base_case.png"))
        exposure = cv2.imread(str(FIXTURES / "base_case_exposure.png"))
        mismatch = cv2.imread(str(FIXTURES / "b_mismatch.png"))
        exposure_similarity = normalized_luminance_ssim(
            prepare_registered_roi(base), prepare_registered_roi(exposure)
        )
        similarity = normalized_luminance_ssim(
            prepare_registered_roi(base), prepare_registered_roi(mismatch)
        )
        self.assertGreaterEqual(exposure_similarity, 0.97)
        self.assertGreaterEqual(similarity, 0.97)
        base_state = classifier.classify(base, evidence_frame_sha256="base")
        exposure_state = classifier.classify(
            exposure, evidence_frame_sha256="exposure"
        )
        mismatch_state = classifier.classify(mismatch, evidence_frame_sha256="mismatch")
        self.assertTrue(base_state["deterministic_complete"])
        self.assertTrue(exposure_state["deterministic_complete"])
        self.assertFalse(mismatch_state["deterministic_complete"])
        self.assertEqual(mismatch_state["mismatched_files"], ["b"])
        self.assertEqual(mismatch_state["suggested_moves"][0]["skill_id"], "pawn_b2_to_b1")

    def test_negative_occupancy_fixtures_fail_closed(self) -> None:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        contract = load_base_case_contract(
            ROOT / "configs" / "orchestrator" / "pawn_bg_diagonal_base_case_v1.json"
        )
        classifier = RegisteredSquareOccupancyClassifier(contract, config["perception"])
        expected = {
            "missing_d.png": "missing_pawn",
            "two_f.png": "two_pawns_in_file",
            "obstruction_g.png": "obstruction",
        }
        for name, blocker in expected.items():
            with self.subTest(name=name):
                state = classifier.classify(
                    cv2.imread(str(FIXTURES / name)), evidence_frame_sha256=name
                )
                self.assertEqual(state["state"], "blocked")
                self.assertIn(blocker, {row["kind"] for row in state["blockers"]})


class SnapshotAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = load_snapshot_contract(
            ROOT / "configs" / "orchestrator" / "silicon_overhead_snapshot_v1.json"
        )
        self.now = datetime(2026, 7, 19, 17, 0, tzinfo=UTC)

    def response(self, **overrides: Any) -> SnapshotResponse:
        headers = {
            "Content-Type": "image/png",
            "X-Sim2Claw-Captured-At": self.now.isoformat(),
            "X-Sim2Claw-Camera-Role": "overhead_workspace",
            "X-Sim2Claw-ROI-Contract": "silicon_registered_board_100mm_v1",
            "X-Sim2Claw-Workspace-Pose": "workspace_board_fiducial_robotward_100mm_20260718_v3",
            "X-Sim2Claw-Registration-Error-Px": "0.25",
        }
        headers.update(overrides.pop("headers", {}))
        return SnapshotResponse(
            status=overrides.pop("status", 200),
            headers=headers,
            body=overrides.pop("body", _fixture_bytes("base_case.png")),
            final_url=overrides.pop(
                "final_url", self.contract["endpoint"]["url"]
            ),
        )

    def adapter(self, response: SnapshotResponse) -> SiliconOverheadSnapshotAdapter:
        return SiliconOverheadSnapshotAdapter(
            self.contract,
            token="fixture-secret-token",
            requester=lambda *_args: response,
            now=lambda: self.now,
        )

    def test_valid_snapshot_records_identity_without_secret_or_url(self) -> None:
        frame = self.adapter(self.response()).fetch()
        self.assertEqual(frame.record["source_host"], "silicon.local.net")
        self.assertEqual(frame.record["registration_error_pixels"], 0.25)
        self.assertTrue(frame.record["freshness"]["passed"])
        serialized = json.dumps(frame.record)
        self.assertNotIn("fixture-secret-token", serialized)
        self.assertNotIn("/api/v1/", serialized)

    def test_local_overhead_snapshot_is_live_preview_without_registration_authority(self) -> None:
        image = cv2.imdecode(
            __import__("numpy").frombuffer(
                _fixture_bytes("base_case.png"), dtype=__import__("numpy").uint8
            ),
            cv2.IMREAD_COLOR,
        )
        encoded, jpeg = cv2.imencode(".jpg", image)
        self.assertTrue(encoded)
        adapter = LocalOverheadSnapshotAdapter(
            lambda camera_id: {
                "camera_id": camera_id,
                "device_name": "C922 Pro Stream Webcam",
                "device_index": 1,
                "captured_at": self.now.isoformat(),
                "fetch_duration_ms": 12.5,
                "body": jpeg.tobytes(),
            },
            status=lambda _camera_id: {
                "ready": True,
                "available": True,
                "device_name": "C922 Pro Stream Webcam",
            },
        )
        frame = adapter.fetch()
        self.assertEqual(frame.record["camera_id"], "logitech-overhead")
        self.assertEqual(frame.record["camera_role"], "overhead_workspace")
        self.assertFalse(frame.record["perception_ready"])
        self.assertEqual(
            frame.record["registration_state"], "operator_registration_required"
        )
        self.assertFalse(frame.record["physical_authority"])

    def test_stale_malformed_oversized_redirected_and_drift_frames_are_rejected(self) -> None:
        cases: list[tuple[str, dict[str, Any], str, dict[str, Any] | None]] = [
            (
                "stale",
                {"headers": {"X-Sim2Claw-Captured-At": (self.now - timedelta(seconds=11)).isoformat()}},
                "stale_frame",
                None,
            ),
            ("malformed", {"body": b"not-an-image"}, "malformed_frame", None),
            (
                "redirect",
                {"final_url": "https://unapproved.example/snapshot"},
                "redirect_rejected",
                None,
            ),
            (
                "same_host_redirect",
                {"final_url": "https://silicon.local.net/api/v1/cameras/overhead/other"},
                "redirect_rejected",
                None,
            ),
            (
                "drift",
                {"headers": {"X-Sim2Claw-Registration-Error-Px": "9"}},
                "camera_registration_drift",
                None,
            ),
            (
                "oversized",
                {"body": _fixture_bytes("base_case.png")},
                "oversized_frame",
                {"maximum": 100},
            ),
        ]
        for name, response_values, code, contract_change in cases:
            with self.subTest(name=name):
                contract = copy.deepcopy(self.contract)
                if contract_change:
                    contract["endpoint"]["maximum_bytes"] = contract_change["maximum"]
                adapter = SiliconOverheadSnapshotAdapter(
                    contract,
                    token="fixture",
                    requester=lambda *_args, values=response_values: self.response(**values),
                    now=lambda: self.now,
                )
                with self.assertRaises(FrameSourceError) as raised:
                    adapter.fetch()
                self.assertEqual(raised.exception.code, code)


class ModelAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        self.model_config = config["model"]
        self.schema = load_decision_schema(
            ROOT / "configs" / "orchestrator" / "schemas" / "orchestrator_decision_v1.json"
        )

    def test_exact_model_medium_reasoning_structured_turn(self) -> None:
        captured: dict[str, Any] = {}

        def transport(
            method: str,
            _url: str,
            _headers: Mapping[str, str],
            payload: Mapping[str, Any] | None,
            _timeout: float,
        ) -> JSONResponse:
            if method == "GET":
                return JSONResponse(200, {"id": "gpt-5.6-luna"})
            captured["payload"] = payload
            decision = _decision("ask_user", reason="Square G2 is obstructed.")
            return JSONResponse(
                200,
                {
                    "id": "resp_fixture",
                    "model": "gpt-5.6-luna",
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {"type": "output_text", "text": json.dumps(decision)}
                            ],
                        }
                    ],
                    "usage": {
                        "input_tokens": 100,
                        "output_tokens": 20,
                        "total_tokens": 120,
                        "output_tokens_details": {"reasoning_tokens": 8},
                    },
                },
            )

        model = OpenAIOrchestratorModel(
            self.model_config,
            self.schema,
            api_key="fixture-openai-secret",
            transport=transport,
        )
        turn = model.decide(
            context={"bounded": True},
            accepted_frame_bytes=_fixture_bytes("b_mismatch.png"),
            accepted_frame_encoding="png",
            reference_frame_bytes=_fixture_bytes("base_case.png"),
        )
        request = captured["payload"]
        self.assertEqual(request["model"], "gpt-5.6-luna")
        self.assertEqual(request["reasoning"], {"effort": "medium"})
        self.assertEqual(request["instructions"], SYSTEM_PROMPT)
        self.assertIn("B1, C2, D1, E2, F1, and G2", request["instructions"])
        self.assertIn(
            "B2, C1, D2, E1, F2, and G1 are occupied",
            request["instructions"],
        )
        self.assertIn(
            "B1->B2, C2->C1, D1->D2, E2->E1, F1->F2, and G2->G1",
            request["instructions"],
        )
        self.assertIn("planning-only", request["instructions"])
        self.assertIn(
            "occupied contains only the destination square",
            request["instructions"],
        )
        self.assertIn(
            'The named command "loop the base case" means',
            request["instructions"],
        )
        self.assertIn(
            "A requested loop duration is a planning horizon",
            request["instructions"],
        )
        self.assertIn("exactly one allowlisted skill", request["instructions"])
        self.assertIn("only the deterministic state checker", request["instructions"])
        self.assertIn("cannot train or promote", request["instructions"])
        self.assertFalse(request["store"])
        self.assertEqual(request["text"]["format"]["type"], "json_schema")
        self.assertTrue(request["text"]["format"]["strict"])
        self.assertEqual(turn["decision"]["decision"], "ask_user")
        self.assertEqual(turn["usage"]["reasoning_tokens"], 8)
        self.assertNotIn("fixture-openai-secret", json.dumps(request))
        self.assertNotIn("fixture-openai-secret", json.dumps(turn))

    def test_identity_mismatch_and_malformed_outputs_fail_closed(self) -> None:
        mismatch = OpenAIOrchestratorModel(
            self.model_config,
            self.schema,
            api_key="fixture",
            transport=lambda *_args: JSONResponse(200, {"id": "gpt-5.5"}),
        )
        self.assertFalse(mismatch.preflight()["ready"])
        with self.assertRaises(OrchestratorModelError):
            validate_decision({"decision": "run_skill"})

        redirected_config = copy.deepcopy(self.model_config)
        redirected_config["endpoint"] = "https://unapproved.example/v1/responses"
        with self.assertRaises(ValueError):
            OpenAIOrchestratorModel(
                redirected_config,
                self.schema,
                api_key="fixture",
            )


class SkillRegistryTests(unittest.TestCase):
    def test_production_registry_exposes_twelve_unavailable_act_skills(self) -> None:
        registry = SkillRegistry.load(
            ROOT / "configs" / "orchestrator" / "studio_task_orchestrator_skills_v1.json"
        )
        rows = registry.public_rows()
        self.assertEqual(len(rows), 12)
        self.assertTrue(all(row["architecture"] == "ACT" for row in rows))
        self.assertTrue(all(not row["callable"] for row in rows))
        self.assertTrue(all(row["observation_schema"] for row in rows))
        self.assertTrue(all(row["action_schema"] for row in rows))
        self.assertTrue(all(row["preconditions"] for row in rows))
        self.assertTrue(all(row["postconditions"] for row in rows))
        self.assertTrue(all(row["timeout_seconds"] == 30 for row in rows))
        self.assertEqual(registry.capability_summary()["callable"], 0)
        self.assertNotIn("chess_rook_lift_v1", registry.entries)
        execution_contract = registry.payload["execution_contract"]
        self.assertEqual(
            execution_contract["supported_scene_id"],
            "operator_updated_chess_workcell_v3",
        )
        self.assertIn("supported_workcell_id", execution_contract)
        self.assertIn("supported_calibration_id", execution_contract)

    def test_published_registry_fails_closed_when_any_receipt_is_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = json.loads(
                (
                    ROOT
                    / "configs/orchestrator/studio_task_orchestrator_skills_v1.json"
                ).read_text(encoding="utf-8")
            )
            artifacts = {
                "checkpoint.pt": b"checkpoint",
                "evaluation.json": b"evaluation",
                "promotion.json": b"promotion",
            }
            for name, value in artifacts.items():
                (root / name).write_bytes(value)
            source["artifact_verification_required"] = True
            for skill in source["skills"]:
                skill.update(
                    {
                        "checkpoint_path": "checkpoint.pt",
                        "checkpoint_sha256": hashlib.sha256(
                            artifacts["checkpoint.pt"]
                        ).hexdigest(),
                        "evaluator_receipt_path": "evaluation.json",
                        "evaluator_receipt_sha256": hashlib.sha256(
                            artifacts["evaluation.json"]
                        ).hexdigest(),
                        "promotion_receipt_path": "promotion.json",
                        "promotion_receipt_sha256": hashlib.sha256(
                            artifacts["promotion.json"]
                        ).hexdigest(),
                        "execution_modes": ["simulation"],
                        "readiness": "promoted_simulation_only",
                        "callable": True,
                    }
                )
            path = root / "registry.json"
            path.write_text(json.dumps(source), encoding="utf-8")
            assert SkillRegistry.load(path).capability_summary()["callable"] == 12
            (root / "promotion.json").unlink()
            assert SkillRegistry.load(path).capability_summary()["callable"] == 0

    def test_runtime_counterexample_return_is_identity_bound(self) -> None:
        dispatcher, _ = _ready_dispatcher(ROOT)
        registry = dispatcher.registry
        entry = registry.entry("pawn_b1_to_b2")
        payload = {
            "schema_version": "sim2claw.runtime_counterexample_return.v1",
            "skill_id": entry.skill_id,
            "checkpoint_sha256": entry.payload["checkpoint_sha256"],
            "evaluator_receipt_sha256": entry.payload["evaluator_receipt_sha256"],
            "promotion_receipt_sha256": entry.payload["promotion_receipt_sha256"],
            "failure_code": "bad_placement",
            "action_trace_sha256": "a" * 64,
            "initial_state_sha256": "b" * 64,
            "terminal_state_sha256": "c" * 64,
        }
        routed = registry.validate_counterexample_return(payload)
        self.assertEqual(routed["route"], "LF-12")
        self.assertEqual(routed["training_rows_authorized"], 0)
        payload["checkpoint_sha256"] = "d" * 64
        with self.assertRaisesRegex(SkillRegistryError, "checkpoint_sha256"):
            registry.validate_counterexample_return(payload)

    def test_skill_timeout_safe_stops_and_returns_terminal_failure(self) -> None:
        payload = json.loads(
            (ROOT / "configs" / "orchestrator" / "studio_task_orchestrator_skills_v1.json").read_text(
                encoding="utf-8"
            )
        )
        skill = next(row for row in payload["skills"] if row["skill_id"] == "pawn_b1_to_b2")
        skill.update(
            {
                "checkpoint_sha256": "1" * 64,
                "evaluator_receipt_sha256": "2" * 64,
                "promotion_receipt_sha256": "3" * 64,
                "execution_modes": ["simulation"],
                "readiness": "promoted_fixture_only",
                "callable": True,
                "timeout_seconds": 0.01,
            }
        )
        registry = SkillRegistry(payload)
        dispatcher = OneAtATimeSkillDispatcher(
            registry, {"pawn_b1_to_b2": TimeoutSkillAdapter()}
        )
        result = dispatcher.dispatch(
            "pawn_b1_to_b2",
            {"source_square": "b1", "destination_square": "b2"},
            mode="simulation",
            latest_state={"observed_occupied": ["b1"], "observed_empty": ["b2"]},
        )
        self.assertEqual(result["status"], "timeout")
        self.assertTrue(result["safe_stop"]["fixture_stopped"])
        self.assertFalse(dispatcher.snapshot()["busy"])

    def test_unstoppable_timeout_latches_dispatcher_against_second_skill(self) -> None:
        payload = json.loads(
            (
                ROOT
                / "configs"
                / "orchestrator"
                / "studio_task_orchestrator_skills_v1.json"
            ).read_text(encoding="utf-8")
        )
        skill = next(row for row in payload["skills"] if row["skill_id"] == "pawn_b1_to_b2")
        skill.update(
            {
                "checkpoint_sha256": "1" * 64,
                "evaluator_receipt_sha256": "2" * 64,
                "promotion_receipt_sha256": "3" * 64,
                "execution_modes": ["simulation"],
                "readiness": "promoted_fixture_only",
                "callable": True,
                "timeout_seconds": 0.01,
            }
        )
        registry = SkillRegistry(payload)
        adapter = UnstoppableSkillAdapter()
        dispatcher = OneAtATimeSkillDispatcher(
            registry,
            {"pawn_b1_to_b2": adapter},
            safe_stop_grace_seconds=0.01,
        )
        try:
            result = dispatcher.dispatch(
                "pawn_b1_to_b2",
                {"source_square": "b1", "destination_square": "b2"},
                mode="simulation",
                latest_state={"observed_occupied": ["b1"], "observed_empty": ["b2"]},
            )
            self.assertEqual(result["status"], "timeout")
            self.assertIn("error", result["safe_stop"])
            self.assertIsNotNone(dispatcher.snapshot()["terminal_fault_latched"])
            with self.assertRaises(SkillRegistryError):
                dispatcher.dispatch(
                    "pawn_b1_to_b2",
                    {"source_square": "b1", "destination_square": "b2"},
                    mode="simulation",
                    latest_state={
                        "observed_occupied": ["b1"],
                        "observed_empty": ["b2"],
                    },
                )
        finally:
            adapter.release.set()


class ServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.config_path = _copy_runtime_configs(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def service(
        self,
        source: FixtureFrameAdapter,
        model: FixtureModel,
        *,
        dispatcher: OneAtATimeSkillDispatcher | None = None,
        clock: FakeClock | None = None,
    ) -> TaskOrchestratorService:
        return TaskOrchestratorService(
            repo_root=self.root,
            config_path=self.config_path,
            frame_adapter_factory=lambda: source,
            model_adapter_factory=lambda: model,
            dispatcher=dispatcher,
            monotonic=clock or __import__("time").monotonic,
            start_worker=False,
        )

    def local_source_service(self) -> tuple[TaskOrchestratorService, FixtureModel]:
        image = cv2.imdecode(
            __import__("numpy").frombuffer(
                _fixture_bytes("b_mismatch.png"), dtype=__import__("numpy").uint8
            ),
            cv2.IMREAD_COLOR,
        )
        encoded, jpeg = cv2.imencode(".jpg", image)
        self.assertTrue(encoded)

        def adapter() -> LocalOverheadSnapshotAdapter:
            return LocalOverheadSnapshotAdapter(
                lambda camera_id: {
                    "camera_id": camera_id,
                    "device_name": "C922 Pro Stream Webcam",
                    "device_index": 1,
                    "captured_at": datetime.now(UTC).isoformat(),
                    "body": jpeg.tobytes(),
                },
                status=lambda _camera_id: {
                    "ready": True,
                    "available": True,
                    "device_name": "C922 Pro Stream Webcam",
                },
            )

        model = FixtureModel()
        service = TaskOrchestratorService(
            repo_root=self.root,
            config_path=self.config_path,
            frame_adapter_factory=adapter,
            frame_source_metadata={
                "adapter_id": "local_logitech_overhead_snapshot_v1",
                "label": "Logitech overhead",
                "host": "local-avfoundation",
                "camera_id": "logitech-overhead",
                "camera_role": "overhead_workspace",
                "roi_contract_id": "local_overhead_unregistered_v1",
                "registration_state": "operator_registration_required",
            },
            frame_source_status=lambda: {
                "ready": True,
                "available": True,
                "device_name": "C922 Pro Stream Webcam",
            },
            workcell_status=lambda: {
                "arms": [{"role": "leader", "connected": True}],
                "cameras": [
                    {
                        "id": "logitech-overhead",
                        "available": True,
                        "primary_for_orchestrator": True,
                    }
                ],
                "physical_authority": False,
            },
            model_adapter_factory=lambda: model,
            start_worker=False,
        )
        return service, model

    def test_local_overhead_preview_works_while_stopped_without_model_turn(self) -> None:
        service, model = self.local_source_service()
        state = service.preview_source()
        self.assertEqual(state["state"], "STOPPED")
        self.assertEqual(state["source"]["health"], "healthy")
        self.assertTrue(state["source"]["latest_preview_sha256"])
        self.assertEqual(state["source"]["device_name"], "C922 Pro Stream Webcam")
        self.assertIsNone(state["base_case"])
        self.assertEqual(model.calls, 0)
        self.assertTrue(state["workcell"]["cameras"][0]["primary_for_orchestrator"])
        service.shutdown()

    def test_unregistered_local_overhead_reaches_model_without_action_authority(self) -> None:
        service, model = self.local_source_service()
        service.start({"mode": "observe_only"})
        self.assertTrue(service.process_pending_once())
        state = service.snapshot()
        self.assertEqual(state["state"], "OBSERVING")
        self.assertEqual(state["base_case"]["state"], "observation_limited")
        self.assertEqual(
            state["base_case"]["blockers"][0]["kind"],
            "camera_registration_required",
        )
        self.assertEqual(model.calls, 1)
        self.assertEqual(state["conversation"][-1]["role"], "assistant")
        self.assertEqual(state["action_queue"]["verification"], "not_started")
        self.assertFalse(state["physical_authority"])
        service.stop()
        service.shutdown()

    def test_demo_visual_feedback_does_not_show_registration_blocker(self) -> None:
        service, _model = self.local_source_service()
        service.frame_adapter_factory = lambda: LocalOverheadSnapshotAdapter(
            lambda camera_id: {
                "camera_id": camera_id,
                "device_name": "C922 Pro Stream Webcam",
                "captured_at": datetime.now(UTC).isoformat(),
                "body": _fixture_bytes("b_mismatch.png"),
            },
            status=lambda _camera_id: {"ready": True, "available": True},
            demo_visual_feedback=True,
        )
        service.source_metadata["registration_state"] = "demo_visual_feedback"
        service.start({"mode": "observe_only"})
        self.assertTrue(service.process_pending_once())
        state = service.snapshot()
        self.assertEqual(state["base_case"]["state"], "demo_visual_feedback")
        self.assertEqual(state["base_case"]["blockers"], [])
        self.assertEqual(
            state["base_case"]["comparison_authority"],
            "demo_visual_feedback_without_square_level_registration",
        )
        service.stop()
        service.shutdown()

    def test_exact_loop_chat_bypasses_model_and_starts_fixed_demo_controller(self) -> None:
        source = FixtureFrameAdapter(["b_mismatch.png"])
        model = FixtureModel()
        controller = {
            "enabled": True,
            "status": "ready",
            "completed_moves": 0,
            "total_moves": 12,
        }
        starts: list[str] = []

        def start_demo() -> dict[str, Any]:
            starts.append("started")
            controller["status"] = "running"
            return dict(controller)

        service = TaskOrchestratorService(
            repo_root=self.root,
            config_path=self.config_path,
            frame_adapter_factory=lambda: source,
            model_adapter_factory=lambda: model,
            frame_source_status=lambda: {"ready": True, "available": True},
            workcell_status=lambda: {
                "arms": [{"id": "so101-follower", "role": "follower", "connected": True}],
                "cameras": [{"id": "logitech-overhead", "available": True}],
            },
            demo_loop_start=start_demo,
            demo_loop_status=lambda: dict(controller),
            demo_loop_stop=lambda: dict(controller),
            start_worker=False,
        )
        started = service.start({"mode": "demo_physical"})
        self.assertEqual(started["state"], "OBSERVING")
        self.assertEqual(model.calls, 0)
        self.assertFalse(service.process_pending_once())
        state = service.chat("Loop it.")
        self.assertEqual(starts, ["started"])
        self.assertEqual(model.calls, 0)
        self.assertEqual(
            state["action_queue"]["current_action"]["skill_id"],
            "five_minute_base_loop_script",
        )
        self.assertEqual(state["conversation"][-1]["decision"], "run_demo_script")
        self.assertTrue(state["physical_authority"])
        service.stop()
        service.shutdown()

    def test_base_case_completion_is_checker_owned_and_stops_resources(self) -> None:
        source = FixtureFrameAdapter(["base_case.png"])
        model = FixtureModel()
        service = self.service(source, model)
        service.start({"mode": "observe_only"})
        self.assertTrue(service.process_pending_once())
        state = service.snapshot()
        self.assertEqual(state["state"], "STOPPED")
        self.assertEqual(state["main_status"], "verified")
        self.assertEqual(state["task_outcome"], "complete")
        self.assertEqual(model.calls, 0)
        self.assertTrue(source.closed)
        self.assertTrue(model.closed)
        events = [row["event"] for row in state["ledger"]]
        self.assertIn("deterministic_base_case_complete", events)
        self.assertIn("session_stopped", events)
        self.assertTrue((service.session_directory / "final.json").is_file())
        final_result = json.loads(
            (service.session_directory / "final.json").read_text(encoding="utf-8")
        )
        result_schema = service.result_schema
        self.assertEqual(set(final_result), set(result_schema["required"]))
        self.assertEqual(final_result["state"], "STOPPED")
        self.assertFalse(final_result["physical_authority"])
        self.assertEqual(
            final_result["torque_off"], "not_applicable_no_physical_adapter"
        )
        manifest = json.loads(
            (service.session_directory / "session.json").read_text(encoding="utf-8")
        )
        contract_paths = set(manifest["contracts"])
        self.assertIn(
            "configs/orchestrator/fixtures/fixture_manifest_v1.json", contract_paths
        )
        self.assertIn(
            "configs/orchestrator/physical_canary_gate_v1.json", contract_paths
        )
        self.assertIn(
            "configs/orchestrator/physical_pawn_bg_canary_evaluator_v1.json",
            contract_paths,
        )
        self.assertIn(
            "configs/orchestrator/schemas/orchestrator_result_v1.json", contract_paths
        )

    def test_dedup_ignores_poll_but_chat_forces_model_turn(self) -> None:
        source = FixtureFrameAdapter(["b_mismatch.png"] * 3)
        model = FixtureModel()
        service = self.service(source, model)
        service.start({"mode": "observe_only"})
        service.process_pending_once()
        self.assertEqual(model.calls, 1)
        service.process_pending_once()
        state = service.snapshot()
        self.assertEqual(model.calls, 1)
        self.assertEqual(state["comparison"]["suppression_count"], 1)
        service.chat("The pawn position was checked by the operator.")
        service.process_pending_once()
        state = service.snapshot()
        self.assertEqual(model.calls, 2)
        self.assertEqual(state["comparison"]["accepted_count"], 2)
        ignored = [row for row in state["ledger"] if row["event"] == "frame_ignored"]
        self.assertFalse(ignored[0]["payload"]["inactivity_timers_reset"])
        service.configure({"polling_interval_seconds": 27})
        self.assertEqual(service.snapshot()["settings"]["polling_interval_seconds"], 27)
        service.stop()

    def test_pause_resume_and_refresh_preserve_ledger_and_force_duplicates(self) -> None:
        source = FixtureFrameAdapter(["b_mismatch.png"] * 3)
        model = FixtureModel()
        service = self.service(source, model)
        service.start({"mode": "observe_only"})
        service.process_pending_once()
        self.assertEqual(model.calls, 1)

        service.pause()
        paused = service.snapshot()
        paused_event_count = len(paused["ledger"])
        self.assertEqual(paused["state"], "PAUSED")
        self.assertFalse(service.process_pending_once())
        self.assertEqual(len(service.snapshot()["ledger"]), paused_event_count)
        self.assertEqual(model.calls, 1)

        service.resume()
        service.process_pending_once()
        resumed = service.snapshot()
        self.assertEqual(resumed["comparison"]["accepted_count"], 2)
        self.assertEqual(model.calls, 2)
        self.assertTrue(
            any(
                row["event"] == "frame_accepted"
                and row["payload"]["forced_accept_reason"] == "resume"
                for row in resumed["ledger"]
            )
        )

        service.refresh()
        service.process_pending_once()
        refreshed = service.snapshot()
        self.assertEqual(refreshed["comparison"]["accepted_count"], 3)
        self.assertEqual(model.calls, 3)
        self.assertTrue(
            any(
                row["event"] == "frame_accepted"
                and row["payload"]["forced_accept_reason"] == "user_refresh"
                for row in refreshed["ledger"]
            )
        )
        service.stop()

    def test_source_fault_does_not_reuse_last_frame_for_model_reasoning(self) -> None:
        source = OneFrameThenFaultAdapter(["b_mismatch.png"])
        model = FixtureModel()
        service = self.service(source, model)
        service.start({"mode": "observe_only"})
        service.process_pending_once()
        self.assertEqual(model.calls, 1)
        service.process_pending_once()
        state = service.snapshot()
        self.assertEqual(state["state"], "PAUSED")
        self.assertEqual(state["fault"]["category"], "frame_source")
        self.assertEqual(state["source"]["latest_error"]["code"], "stale_frame")
        self.assertEqual(state["comparison"]["accepted_count"], 1)
        self.assertEqual(model.calls, 1)
        self.assertTrue(source.closed)
        self.assertTrue(model.closed)
        service.stop()

    def test_source_fault_resume_reacquires_and_forces_recovery_observation(self) -> None:
        first_source = FaultFrameAdapter()
        recovered_source = FixtureFrameAdapter(["b_mismatch.png"])
        first_model = FixtureModel()
        recovered_model = FixtureModel()
        sources = iter([first_source, recovered_source])
        models = iter([first_model, recovered_model])
        service = TaskOrchestratorService(
            repo_root=self.root,
            config_path=self.config_path,
            frame_adapter_factory=lambda: next(sources),
            model_adapter_factory=lambda: next(models),
            start_worker=False,
        )
        service.start({"mode": "observe_only"})
        service.process_pending_once()
        faulted = service.snapshot()
        self.assertEqual(faulted["state"], "PAUSED")
        self.assertTrue(first_source.closed)
        self.assertTrue(first_model.closed)

        service.resume()
        service.process_pending_once()
        recovered = service.snapshot()
        self.assertEqual(recovered["state"], "OBSERVING")
        self.assertTrue(recovered["source"]["live_connectivity_verified"])
        self.assertEqual(recovered_model.calls, 1)
        recovery_frames = [
            row
            for row in recovered["ledger"]
            if row["event"] == "frame_accepted"
            and row["payload"]["forced_accept_reason"] == "source_health_recovery"
        ]
        self.assertEqual(len(recovery_frames), 1)
        service.stop()

    def test_invalid_model_output_is_recorded_and_pauses_failed(self) -> None:
        source = FixtureFrameAdapter(["b_mismatch.png"])
        model = FaultModel()
        service = self.service(source, model)
        service.start({"mode": "observe_only"})
        service.process_pending_once()
        state = service.snapshot()
        self.assertEqual(state["state"], "PAUSED")
        self.assertEqual(state["main_status"], "failed")
        self.assertEqual(state["fault"]["category"], "model")
        self.assertIn("model_turn_rejected", [row["event"] for row in state["ledger"]])
        self.assertIn("fault_resources_released", [row["event"] for row in state["ledger"]])
        self.assertTrue(source.closed)
        self.assertTrue(model.closed)
        service.stop()

    def test_ambiguous_or_obstructed_managed_state_requires_user_without_model(self) -> None:
        cases = {
            "missing_d.png": "missing_pawn",
            "two_f.png": "two_pawns_in_file",
            "obstruction_g.png": "obstruction",
        }
        for fixture, blocker in cases.items():
            with self.subTest(fixture=fixture):
                source = FixtureFrameAdapter([fixture])
                model = FixtureModel(restore=True)
                service = self.service(source, model)
                service.start({"mode": "observe_only"})
                service.process_pending_once()
                state = service.snapshot()
                self.assertEqual(state["state"], "PAUSED")
                self.assertEqual(state["main_status"], "proposed")
                self.assertEqual(
                    state["pause_reason"], "deterministic_base_state_blocked"
                )
                self.assertEqual(
                    state["action_queue"]["verification"],
                    "user_intervention_required",
                )
                self.assertEqual(model.calls, 0)
                self.assertIn(
                    blocker,
                    state["action_queue"]["proposed_plan"][0]["reason"],
                )
                help_events = [
                    row for row in state["ledger"] if row["event"] == "user_help_requested"
                ]
                self.assertEqual(
                    help_events[0]["payload"]["owner"],
                    "deterministic_managed_region_checker",
                )
                service.stop()

    def test_observe_only_records_unavailable_proposal_without_dispatch(self) -> None:
        source = FixtureFrameAdapter(["b_mismatch.png"])
        model = FixtureModel(restore=True)
        service = self.service(source, model)
        service.start({"mode": "observe_only"})
        service.process_pending_once()
        state = service.snapshot()
        self.assertEqual(state["main_status"], "proposed")
        self.assertEqual(state["action_queue"]["verification"], "unavailable")
        self.assertIn(
            "skill_rejected_unavailable", [row["event"] for row in state["ledger"]]
        )
        self.assertEqual(service.dispatcher.snapshot()["busy"], False)
        service.stop()

    def test_physical_shadow_records_supervised_operator_choice_without_command(self) -> None:
        dispatcher, counter = _ready_dispatcher(
            self.root, execution_modes=["physical_shadow"]
        )
        source = FixtureFrameAdapter(["b_mismatch.png"])
        model = FixtureModel(restore=True)
        service = self.service(source, model, dispatcher=dispatcher)
        service.start({"mode": "physical_shadow"})
        service.process_pending_once()
        proposed = service.snapshot()
        self.assertEqual(proposed["state"], "PAUSED")
        self.assertEqual(
            proposed["pause_reason"], "awaiting_operator_shadow_choice"
        )
        self.assertEqual(
            proposed["action_queue"]["verification"],
            "awaiting_operator_shadow_choice",
        )
        self.assertEqual(counter["calls"], 0)
        self.assertFalse(proposed["physical_shadow"]["hardware_command_issued"])

        reviewed = service.shadow_choice(
            skill_id="pawn_b2_to_b1",
            operator_identity="fixture-operator",
            note="supervised fixture comparison",
        )
        self.assertEqual(
            reviewed["action_queue"]["verification"], "shadow_exact_match"
        )
        comparison = reviewed["physical_shadow"]["latest_comparison"]
        self.assertTrue(comparison["exact_choice_match"])
        self.assertEqual(comparison["operator_identity"], "fixture-operator")
        self.assertEqual(
            comparison["accepted_frame_sha256"],
            reviewed["source"]["latest_accepted_sha256"],
        )
        self.assertFalse(comparison["hardware_command_issued"])
        self.assertFalse(comparison["physical_authority"])
        shadow_summary = reviewed["physical_shadow"]["by_proposed_skill"][
            "pawn_b2_to_b1"
        ]
        self.assertEqual(shadow_summary["trials"], 1)
        self.assertEqual(shadow_summary["exact_match_rate"], 1.0)
        self.assertFalse(shadow_summary["protocol_passed"])
        self.assertEqual(counter["calls"], 0)
        self.assertIn(
            "shadow_operator_choice_recorded",
            [row["event"] for row in reviewed["ledger"]],
        )
        service.stop()

    def test_model_cannot_claim_completion_before_deterministic_checker(self) -> None:
        source = FixtureFrameAdapter(["b_mismatch.png"])
        model = CompleteClaimModel()
        service = self.service(source, model)
        service.start({"mode": "observe_only"})
        service.process_pending_once()
        state = service.snapshot()
        self.assertEqual(state["state"], "PAUSED")
        self.assertEqual(state["main_status"], "failed")
        self.assertIsNone(state["task_outcome"])
        self.assertEqual(state["fault"]["category"], "model_policy")
        self.assertEqual(state["fault"]["code"], "model_cannot_own_completion")
        self.assertTrue(source.closed)
        self.assertTrue(model.closed)
        service.stop()

    def test_cross_file_model_proposal_is_rejected_before_dispatch(self) -> None:
        source = FixtureFrameAdapter(["b_mismatch.png"])
        model = CrossFileProposalModel()
        service = self.service(source, model)
        service.start({"mode": "observe_only"})
        service.process_pending_once()
        state = service.snapshot()
        self.assertEqual(state["state"], "PAUSED")
        self.assertEqual(state["fault"]["category"], "model_policy")
        self.assertEqual(state["fault"]["code"], "skill_proposal_rejected")
        self.assertEqual(service.dispatcher.snapshot()["busy"], False)
        self.assertTrue(source.closed)
        self.assertTrue(model.closed)
        service.stop()

    def test_skill_failure_forces_fresh_observation_before_fault_pause(self) -> None:
        dispatcher, _counter = _ready_dispatcher(self.root)
        dispatcher.adapters["pawn_b2_to_b1"] = FailingSkillAdapter()
        source = FixtureFrameAdapter(["b_mismatch.png", "b_mismatch.png"])
        model = FixtureModel(restore=True)
        service = self.service(source, model, dispatcher=dispatcher)
        service.start({"mode": "simulation"})
        service.process_pending_once()
        interim = service.snapshot()
        self.assertEqual(
            interim["action_queue"]["verification"],
            "awaiting_forced_failure_observation",
        )
        service.process_pending_once()
        state = service.snapshot()
        self.assertEqual(state["state"], "PAUSED")
        self.assertEqual(state["main_status"], "failed")
        self.assertEqual(state["comparison"]["accepted_count"], 2)
        forced_failure_frames = [
            row
            for row in state["ledger"]
            if row["event"] == "frame_accepted"
            and row["payload"]["forced_accept_reason"] == "skill_failure"
        ]
        self.assertEqual(len(forced_failure_frames), 1)
        self.assertEqual(state["fault"]["category"], "execution")
        self.assertTrue(source.closed)
        self.assertTrue(model.closed)
        service.stop()

    def test_pause_during_skill_safe_stops_then_verifies_failure_after_resume(self) -> None:
        dispatcher, _counter = _ready_dispatcher(self.root)
        adapter = BlockingSkillAdapter()
        dispatcher.adapters["pawn_b2_to_b1"] = adapter
        source = FixtureFrameAdapter(["b_mismatch.png", "b_mismatch.png"])
        model = FixtureModel(restore=True)
        service = self.service(source, model, dispatcher=dispatcher)
        service.start({"mode": "simulation"})
        worker = threading.Thread(target=service.process_pending_once)
        worker.start()
        self.assertTrue(adapter.started.wait(1.0))
        service.pause("user_pause_during_skill")
        worker.join(timeout=2.0)
        self.assertFalse(worker.is_alive())
        paused = service.snapshot()
        self.assertEqual(paused["state"], "PAUSED")
        self.assertEqual(
            paused["action_queue"]["verification"],
            "awaiting_forced_failure_observation",
        )
        self.assertIn("skill_failure", service.pending_reasons)

        service.resume()
        service.process_pending_once()
        terminal = service.snapshot()
        self.assertEqual(terminal["state"], "PAUSED")
        self.assertEqual(terminal["main_status"], "failed")
        self.assertEqual(terminal["fault"]["category"], "execution")
        self.assertTrue(
            any(
                row["event"] == "frame_accepted"
                and row["payload"]["forced_accept_reason"] == "skill_failure"
                for row in terminal["ledger"]
            )
        )
        service.stop()

    def test_stop_during_skill_does_not_reopen_terminal_session(self) -> None:
        dispatcher, _counter = _ready_dispatcher(self.root)
        adapter = BlockingSkillAdapter()
        dispatcher.adapters["pawn_b2_to_b1"] = adapter
        source = FixtureFrameAdapter(["b_mismatch.png"])
        model = FixtureModel(restore=True)
        service = self.service(source, model, dispatcher=dispatcher)
        service.start({"mode": "simulation"})
        worker = threading.Thread(target=service.process_pending_once)
        worker.start()
        self.assertTrue(adapter.started.wait(1.0))
        service.stop("user_stop_during_skill")
        worker.join(timeout=2.0)
        self.assertFalse(worker.is_alive())
        terminal = service.snapshot()
        self.assertEqual(terminal["state"], "STOPPED")
        self.assertEqual(terminal["ledger"][-1]["event"], "session_stopped")
        self.assertEqual(service.pending_reasons, [])
        self.assertFalse(dispatcher.snapshot()["busy"])
        final_result = json.loads(
            (service.session_directory / "final.json").read_text(encoding="utf-8")
        )
        self.assertEqual(final_result["reason"], "user_stop_during_skill")

    def test_stop_during_frame_fetch_does_not_append_after_terminal_receipt(self) -> None:
        source = BlockingFrameAdapter()
        model = FixtureModel()
        service = self.service(source, model)
        service.start({"mode": "observe_only"})
        worker = threading.Thread(target=service.process_pending_once)
        worker.start()
        self.assertTrue(source.started.wait(1.0))
        service.stop("user_stop_during_frame")
        worker.join(timeout=2.0)
        self.assertFalse(worker.is_alive())
        terminal = service.snapshot()
        self.assertEqual(terminal["state"], "STOPPED")
        self.assertEqual(terminal["ledger"][-1]["event"], "session_stopped")
        self.assertEqual(terminal["comparison"]["captured_count"], 0)
        self.assertEqual(model.calls, 0)

    def test_stop_during_model_turn_does_not_append_after_terminal_receipt(self) -> None:
        source = FixtureFrameAdapter(["b_mismatch.png"])
        model = BlockingModel()
        service = self.service(source, model)
        service.start({"mode": "observe_only"})
        worker = threading.Thread(target=service.process_pending_once)
        worker.start()
        self.assertTrue(model.started.wait(1.0))
        service.stop("user_stop_during_model")
        worker.join(timeout=2.0)
        self.assertFalse(worker.is_alive())
        terminal = service.snapshot()
        self.assertEqual(terminal["state"], "STOPPED")
        self.assertEqual(terminal["ledger"][-1]["event"], "session_stopped")
        self.assertFalse(terminal["model"]["active"])
        self.assertTrue(source.closed)
        self.assertTrue(model.closed)

    def test_either_inactivity_timer_auto_pauses(self) -> None:
        for timer_name in ("user", "world"):
            with self.subTest(timer=timer_name):
                clock = FakeClock()
                source = FixtureFrameAdapter(["b_mismatch.png"])
                model = FixtureModel()
                service = self.service(source, model, clock=clock)
                service.start({"mode": "observe_only"})
                if timer_name == "user":
                    service.last_world_activity_monotonic = clock() + 250
                else:
                    service.last_user_activity_monotonic = clock() + 250
                clock.advance(301)
                service.process_pending_once()
                state = service.snapshot()
                self.assertEqual(state["state"], "PAUSED")
                self.assertEqual(state["pause_reason"], f"{timer_name}_inactivity_timeout" if timer_name == "user" else "world_action_inactivity_timeout")
                service.stop()

    def test_simulation_restores_multiple_files_one_verified_move_at_a_time(self) -> None:
        cases = [
            ["b_c_e_mismatch.png", "c_e_mismatch.png", "e_mismatch.png", "base_case.png"],
            ["d_f_g_mismatch.png", "f_g_mismatch.png", "g_mismatch.png", "base_case.png"],
        ]
        for index, names in enumerate(cases):
            with self.subTest(combination=index):
                dispatcher, counter = _ready_dispatcher(self.root)
                source = FixtureFrameAdapter(names)
                model = FixtureModel(restore=True)
                service = self.service(source, model, dispatcher=dispatcher)
                service.start({"mode": "simulation"})
                for _ in range(4):
                    service.process_pending_once()
                state = service.snapshot()
                self.assertEqual(state["state"], "STOPPED")
                self.assertEqual(state["task_outcome"], "complete")
                self.assertEqual(counter["calls"], 3)
                self.assertEqual(counter["max_active"], 1)
                verified = [
                    row
                    for row in state["ledger"]
                    if row["event"] == "skill_postcondition_verified"
                ]
                self.assertEqual(len(verified), 3)
                self.assertTrue(all(row["payload"]["passed"] for row in verified))

    def test_simulation_restores_every_single_file_mismatch(self) -> None:
        for file_name in "bcdefg":
            with self.subTest(file=file_name):
                dispatcher, counter = _ready_dispatcher(self.root)
                source = FixtureFrameAdapter([f"{file_name}_mismatch.png", "base_case.png"])
                model = FixtureModel(restore=True)
                service = self.service(source, model, dispatcher=dispatcher)
                service.start({"mode": "simulation"})
                service.process_pending_once()
                service.process_pending_once()
                state = service.snapshot()
                self.assertEqual(state["task_outcome"], "complete")
                self.assertEqual(counter["calls"], 1)


class StudioHTTPTests(unittest.TestCase):
    def test_loopback_and_read_only_orchestrator_surfaces(self) -> None:
        server = create_server("127.0.0.1", 0, repo_root=ROOT)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with urlopen(f"{base}/api/orchestrator", timeout=3) as response:
                payload = json.loads(response.read())
            self.assertTrue(payload["available"])
            self.assertNotIn("demo_physical", payload["modes"])
            self.assertFalse(payload["physical_authority"])
            self.assertEqual(payload["model"]["label"], "5.6 luna")
            self.assertEqual(
                payload["physical_authority"],
                payload["demo_loop"]["physical_authority"],
            )
            self.assertEqual(payload["demo_loop"]["authority_scope"], "none")
            self.assertEqual(payload["skills"]["callable"], 0)
            self.assertFalse(payload["modes"]["physical_gated"]["selectable"])
            self.assertEqual(
                payload["physical_canary_gate"]["status"],
                "disabled_pending_separate_authorization",
            )
            self.assertFalse(payload["physical_canary_gate"]["enabled"])
            with urlopen(f"{base}/", timeout=3) as response:
                html = response.read().decode("utf-8")
            self.assertIn('data-route="orchestrator">Task Orchestrator', html)
            self.assertIn('id="orchestrator-main-status"', html)
            self.assertIn('id="orchestrator-shadow-review"', html)
            self.assertIn('id="orchestrator-shadow-choice"', html)
            request = Request(
                f"{base}/api/orchestrator/session",
                data=json.dumps({"action": "start", "mode": "physical_gated"}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with self.assertRaises(HTTPError) as raised:
                urlopen(request, timeout=3)
            self.assertEqual(raised.exception.code, 400)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

        enabled = create_server(
            "127.0.0.1",
            0,
            repo_root=ROOT,
            enable_physical_demo=True,
        )
        thread = threading.Thread(target=enabled.serve_forever, daemon=True)
        thread.start()
        try:
            with urlopen(
                f"http://127.0.0.1:{enabled.server_address[1]}/api/orchestrator",
                timeout=3,
            ) as response:
                payload = json.loads(response.read())
            self.assertIn("demo_physical", payload["modes"])
            self.assertEqual(
                payload["demo_loop"]["authority_scope"],
                "fixed_owner_directed_base_inverse_base_script_only",
            )
            self.assertFalse(
                payload["demo_loop"]["registration_required_for_demo_script"]
            )
        finally:
            enabled.shutdown()
            enabled.server_close()
            thread.join(timeout=3)

        with self.assertRaisesRegex(ValueError, "interactive loopback"):
            create_server(
                "0.0.0.0",
                0,
                repo_root=ROOT,
                enable_physical_demo=True,
            )
        with self.assertRaisesRegex(ValueError, "interactive loopback"):
            create_server(
                "127.0.0.1",
                0,
                repo_root=ROOT,
                read_only=True,
                enable_physical_demo=True,
            )

        read_only = create_server("127.0.0.1", 0, repo_root=ROOT, read_only=True)
        thread = threading.Thread(target=read_only.serve_forever, daemon=True)
        thread.start()
        try:
            with urlopen(
                f"http://127.0.0.1:{read_only.server_address[1]}/api/orchestrator",
                timeout=3,
            ) as response:
                payload = json.loads(response.read())
            self.assertFalse(payload["available"])
            self.assertFalse(payload["physical_authority"])
            request = Request(
                f"http://127.0.0.1:{read_only.server_address[1]}/api/orchestrator/session",
                data=json.dumps({"action": "start", "mode": "observe_only"}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with self.assertRaises(HTTPError) as raised:
                urlopen(request, timeout=3)
            self.assertEqual(raised.exception.code, 403)
        finally:
            read_only.shutdown()
            read_only.server_close()
            thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
