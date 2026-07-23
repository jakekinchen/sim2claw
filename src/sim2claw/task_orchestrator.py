"""Background, receipt-producing Studio Task Orchestrator state machine."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from .orchestrator_frames import (
    FrameAdapter,
    FrameSourceError,
    SiliconOverheadSnapshotAdapter,
    SnapshotFrame,
    load_snapshot_contract,
    normalized_luminance_ssim,
    prepare_registered_roi,
)
from .orchestrator_model import (
    OpenAIOrchestratorModel,
    OrchestratorModelError,
    load_decision_schema,
)
from .orchestrator_perception import (
    RegisteredSquareOccupancyClassifier,
    load_base_case_contract,
    verify_expected_postcondition,
)
from .orchestrator_skills import (
    OneAtATimeSkillDispatcher,
    SkillRegistry,
    SkillRegistryError,
)
from .paths import REPO_ROOT


ORCHESTRATOR_STATE_SCHEMA = "sim2claw.task_orchestrator_state.v1"
ORCHESTRATOR_EVENT_SCHEMA = "sim2claw.orchestrator_event.v1"
BOARD_FILES = "bcdefg"
BIT_PATTERN_RE = re.compile(r"(?<![01])([01]{6})(?![01])")
DEFAULT_CONFIG_PATH = REPO_ROOT / "configs" / "orchestrator" / "studio_task_orchestrator_v1.json"
ACTIVE_STATES = {
    "STARTING",
    "OBSERVING",
    "AWAITING_MODEL",
    "PROPOSED_ACTION",
    "EXECUTING_SKILL",
    "VERIFYING",
}
STATE_TRANSITIONS = {
    "STOPPED": {"STARTING"},
    "STARTING": {"OBSERVING", "PAUSING", "STOPPING", "FAULTED"},
    "OBSERVING": {"AWAITING_MODEL", "PAUSING", "STOPPING", "FAULTED"},
    "AWAITING_MODEL": {"PROPOSED_ACTION", "OBSERVING", "PAUSING", "STOPPING", "FAULTED"},
    "PROPOSED_ACTION": {"EXECUTING_SKILL", "OBSERVING", "PAUSING", "STOPPING", "FAULTED"},
    "EXECUTING_SKILL": {"VERIFYING", "PAUSING", "STOPPING", "FAULTED"},
    "VERIFYING": {"OBSERVING", "AWAITING_MODEL", "PAUSING", "STOPPING", "FAULTED"},
    "PAUSING": {"PAUSED", "STOPPING", "FAULTED"},
    "PAUSED": {"STARTING", "STOPPING"},
    "FAULTED": {"PAUSING", "STOPPING"},
    "STOPPING": {"STOPPED"},
}


class TaskOrchestratorError(RuntimeError):
    """Stable operator-facing orchestrator control error."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_dotenv_value(path: Path, key: str) -> str | None:
    """Read one simple dotenv value without mutating process environment."""

    if not path.is_file():
        return None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip().removeprefix("export ").strip() != key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        return value or None
    return None


def _secret(repo_root: Path, key: str) -> str | None:
    return os.environ.get(key) or _read_dotenv_value(repo_root / ".env", key)


def interpret_objective(message: str) -> dict[str, Any]:
    """Preserve an intent while limiting execution to the twelve B-G moves."""
    patterns = BIT_PATTERN_RE.findall(message)
    target_pattern = patterns[-1] if patterns else None
    source_pattern = patterns[-2] if len(patterns) > 1 else None
    objective: dict[str, Any] = {
        "request": message,
        "status": "active",
        "kind": "pattern" if target_pattern is not None else "free_form",
        "execution_vocabulary": "twelve_b_through_g_moves_only",
    }
    if target_pattern is None:
        return objective
    occupied: list[str] = []
    empty: list[str] = []
    moves: list[str] = []
    for file_name, bit in zip(BOARD_FILES, target_pattern, strict=True):
        destination_rank = "2" if bit == "1" else "1"
        source_rank = "1" if bit == "1" else "2"
        occupied.append(file_name + destination_rank)
        empty.append(file_name + source_rank)
        moves.append(f"pawn_{file_name}{source_rank}_to_{file_name}{destination_rank}")
    objective["pattern"] = {
        "files": list(BOARD_FILES),
        "bit_meaning": {"0": "rank_1", "1": "rank_2"},
        "source_if_supplied": source_pattern,
        "target": target_pattern,
        "occupied": occupied,
        "empty": empty,
        "candidate_moves": moves,
    }
    return objective


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


class TaskOrchestratorService:
    """Own one user-controlled task session and its serialized background work."""

    def __init__(
        self,
        *,
        repo_root: Path = REPO_ROOT,
        config_path: Path = DEFAULT_CONFIG_PATH,
        frame_adapter_factory: Callable[[], FrameAdapter] | None = None,
        frame_source_metadata: Mapping[str, Any] | None = None,
        frame_source_status: Callable[[], Mapping[str, Any]] | None = None,
        workcell_status: Callable[[], Mapping[str, Any]] | None = None,
        demo_loop_start: Callable[[], Mapping[str, Any]] | None = None,
        demo_action_start: Callable[[str], Mapping[str, Any]] | None = None,
        demo_loop_status: Callable[[], Mapping[str, Any]] | None = None,
        demo_loop_stop: Callable[[], Mapping[str, Any]] | None = None,
        model_adapter_factory: Callable[[], OpenAIOrchestratorModel] | None = None,
        dispatcher: OneAtATimeSkillDispatcher | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        utc_now: Callable[[], datetime] = _utc_now,
        start_worker: bool = True,
    ) -> None:
        self.repo_root = repo_root.resolve()
        self.config_path = config_path.resolve()
        self.authority_root = self.config_path.parents[2]
        self.config = json.loads(self.config_path.read_text(encoding="utf-8"))
        if self.config.get("schema_version") != "sim2claw.task_orchestrator_config.v1":
            raise ValueError("unexpected Task Orchestrator config schema")
        self.monotonic = monotonic
        self.utc_now = utc_now
        self.lock = threading.RLock()
        self.wake_event = threading.Event()
        self.shutdown_event = threading.Event()
        self.pending_reasons: list[str] = []
        self.worker: threading.Thread | None = None

        task_config = self.config["task"]
        self.base_case_path = self.authority_root / task_config["base_case_contract"]
        self.snapshot_contract_path = self.authority_root / task_config["snapshot_contract"]
        self.registry_path = self.authority_root / task_config["skill_registry"]
        self.fixture_manifest_path = self.authority_root / task_config["fixture_manifest"]
        self.physical_canary_gate_path = (
            self.authority_root / task_config["physical_canary_gate"]
        )
        self.physical_evaluator_path = self.authority_root / task_config[
            "physical_evaluator"
        ]
        self.event_schema_path = self.authority_root / task_config["event_schema"]
        self.result_schema_path = self.authority_root / task_config["result_schema"]
        self.decision_schema_path = (
            self.authority_root
            / "configs"
            / "orchestrator"
            / "schemas"
            / "orchestrator_decision_v1.json"
        )
        self.reference_image_path = (
            self.authority_root / self.config["perception"]["reference_image"]
        )
        self.base_contract = load_base_case_contract(self.base_case_path)
        self.snapshot_contract = load_snapshot_contract(self.snapshot_contract_path)
        loaded_registry = SkillRegistry.load(self.registry_path)
        self.registry = dispatcher.registry if dispatcher is not None else loaded_registry
        self.decision_schema = load_decision_schema(self.decision_schema_path)
        self.fixture_manifest = json.loads(
            self.fixture_manifest_path.read_text(encoding="utf-8")
        )
        if self.fixture_manifest.get("schema_version") != (
            "sim2claw.orchestrator_fixture_manifest.v1"
        ):
            raise ValueError("unexpected orchestrator fixture manifest schema")
        self.physical_canary_gate = json.loads(
            self.physical_canary_gate_path.read_text(encoding="utf-8")
        )
        if self.physical_canary_gate.get("schema_version") != (
            "sim2claw.orchestrator_physical_canary_gate.v1"
        ):
            raise ValueError("unexpected physical canary gate schema")
        if self.physical_canary_gate.get("physical_authority") is not False:
            raise ValueError("physical canary gate must not grant physical authority")
        self.physical_evaluator = json.loads(
            self.physical_evaluator_path.read_text(encoding="utf-8")
        )
        if self.physical_evaluator.get("schema_version") != (
            "sim2claw.orchestrator_physical_evaluator.v1"
        ):
            raise ValueError("unexpected physical evaluator schema")
        if self.physical_evaluator.get("physical_authority") is not False:
            raise ValueError("physical evaluator contract must not grant physical authority")
        expected_evaluator_reference = str(
            self.physical_evaluator_path.relative_to(self.authority_root)
        )
        if self.physical_canary_gate.get("physical_evaluator_contract") != (
            expected_evaluator_reference
        ):
            raise ValueError("physical canary gate evaluator binding changed")
        self.event_schema = json.loads(self.event_schema_path.read_text(encoding="utf-8"))
        if self.event_schema.get("$id") != "sim2claw.orchestrator_event.v1":
            raise ValueError("unexpected orchestrator event schema")
        self.result_schema = json.loads(self.result_schema_path.read_text(encoding="utf-8"))
        if self.result_schema.get("$id") != "sim2claw.orchestrator_result.v1":
            raise ValueError("unexpected orchestrator result schema")
        self.classifier = RegisteredSquareOccupancyClassifier(
            self.base_contract, self.config["perception"]
        )
        self.dispatcher = dispatcher or OneAtATimeSkillDispatcher(self.registry)

        snapshot_token_name = self.snapshot_contract["endpoint"]["authentication"][
            "environment_variable"
        ]
        model_key_name = self.config["model"]["api_key_environment_variable"]
        self.frame_credential_configured = bool(_secret(self.repo_root, snapshot_token_name))
        self.model_credential_configured = bool(_secret(self.repo_root, model_key_name))
        self.frame_adapter_factory = frame_adapter_factory or (
            lambda: SiliconOverheadSnapshotAdapter(
                self.snapshot_contract,
                token=_secret(self.repo_root, snapshot_token_name),
            )
        )
        self.model_adapter_factory = model_adapter_factory or (
            lambda: OpenAIOrchestratorModel(
                self.config["model"],
                self.decision_schema,
                api_key=_secret(self.repo_root, model_key_name),
            )
        )
        if frame_adapter_factory is not None:
            self.frame_credential_configured = True
        if model_adapter_factory is not None:
            self.model_credential_configured = True

        self.source_metadata = {
            "adapter_id": self.snapshot_contract["adapter_id"],
            "label": "Silicon registered board",
            "host": self.snapshot_contract["endpoint"]["allowed_host"],
            "camera_id": "silicon-overhead",
            "camera_role": self.snapshot_contract["image_contract"]["camera_role"],
            "roi_contract_id": self.snapshot_contract["image_contract"]["roi_contract_id"],
            "registration_state": "registered",
            **dict(frame_source_metadata or {}),
        }
        self.frame_source_status = frame_source_status
        self.workcell_status = workcell_status
        self.demo_loop_start = demo_loop_start
        self.demo_action_start = demo_action_start
        self.demo_loop_status = demo_loop_status
        self.demo_loop_stop = demo_loop_stop
        self.demo_loop_last_status: str | None = None

        self.frame_adapter: FrameAdapter | None = None
        self.model_adapter: OpenAIOrchestratorModel | None = None
        self.session_directory: Path | None = None
        self.ledger_path: Path | None = None
        self.event_sequence = 0
        self.latest_frame: SnapshotFrame | None = None
        self.latest_frame_bytes: bytes | None = None
        self.latest_frame_content_type: str | None = None
        self.last_accepted_roi: Any = None
        self.last_base_state: dict[str, Any] | None = None
        self.pending_postcondition: dict[str, Any] | None = None
        self.last_skill_results: dict[str, Any] = {}
        self.recent_conversation: list[dict[str, Any]] = []
        self.ledger_tail: list[dict[str, Any]] = []
        self.next_poll_monotonic: float | None = None
        self.last_user_activity_monotonic: float | None = None
        self.last_world_activity_monotonic: float | None = None
        self.active_objective: dict[str, Any] | None = None
        self.state = self._initial_state()
        if start_worker:
            self.worker = threading.Thread(
                target=self._worker_loop,
                name="sim2claw-task-orchestrator",
                daemon=True,
            )
            self.worker.start()

    def _initial_state(self) -> dict[str, Any]:
        polling = self.config["polling"]
        inactivity = self.config["inactivity"]
        return {
            "schema_version": ORCHESTRATOR_STATE_SCHEMA,
            "session_id": None,
            "state": "STOPPED",
            "main_status": "stopped",
            "task_outcome": None,
            "mode": self.config["execution"]["default_mode"],
            "started_at": None,
            "updated_at": self.utc_now().isoformat(),
            "pause_reason": None,
            "fault": None,
            "settings": {
                "polling_interval_seconds": polling["default_interval_seconds"],
                "polling_minimum_seconds": polling["minimum_interval_seconds"],
                "polling_maximum_seconds": polling["maximum_interval_seconds"],
                "deduplication_threshold": self.config["deduplication"]["threshold"],
                "user_inactivity_seconds": inactivity["user_seconds"],
                "world_action_inactivity_seconds": inactivity["world_action_seconds"],
            },
            "source": {
                **json.loads(json.dumps(self.source_metadata)),
                "health": "not_started",
                "connected": False,
                "latest_captured_at": None,
                "latest_accepted_sha256": None,
                "latest_preview_sha256": None,
                "latest_error": None,
                "live_connectivity_verified": False,
            },
            "comparison": {
                "metric": self.config["deduplication"]["metric"],
                "similarity": None,
                "suppression_count": 0,
                "accepted_count": 0,
                "captured_count": 0,
            },
            "base_case": None,
            "model": {
                "adapter_id": self.config["model"]["adapter_id"],
                "label": self.config["model"]["user_facing_label"],
                "provider_model_id": self.config["model"]["provider_model_id"],
                "reasoning_effort": self.config["model"]["reasoning_effort"],
                "credential_configured": self.model_credential_configured,
                "identity_verified": False,
                "active": False,
                "last_turn": None,
            },
            "skills": self.registry.capability_summary(),
            "action_queue": {
                "proposed_plan": [],
                "current_action": None,
                "expected_postcondition": None,
                "verification": "not_started",
            },
            "physical_shadow": {
                "comparison_count": 0,
                "latest_comparison": None,
                "by_proposed_skill": {},
                "hardware_command_issued": False,
                "physical_authority": False,
            },
            "timers": {
                "user_remaining_seconds": inactivity["user_seconds"],
                "world_action_remaining_seconds": inactivity["world_action_seconds"],
            },
            "physical_authority": False,
            "torque_off": "not_applicable_no_physical_adapter",
        }

    def _mode_capabilities(self) -> dict[str, dict[str, Any]]:
        source_preflight = self._source_preflight()
        source_ready = bool(source_preflight.get("ready"))
        model_ready = self.model_credential_configured
        skills = self.registry.capability_summary()
        dispatcher_state = self.dispatcher.snapshot()
        dispatcher_ready = dispatcher_state["terminal_fault_latched"] is None
        common = source_ready and model_ready
        missing_common: list[str] = []
        if not source_ready:
            missing_common.append(
                str(source_preflight.get("reason") or "selected overhead source")
            )
        if not model_ready:
            missing_common.append("exact-model credential")
        common_reason = (
            None
            if not missing_common
            else " and ".join(missing_common).capitalize()
            + (" is required." if len(missing_common) == 1 else " are required.")
        )
        capabilities = {
            "observe_only": {
                "selectable": common,
                "reason": (
                    None if common else common_reason
                ),
                "physical_authority": False,
            },
            "simulation": {
                "selectable": common and skills["simulation_ready"] and dispatcher_ready,
                "reason": (
                    None
                    if common and skills["simulation_ready"] and dispatcher_ready
                    else (
                        "Skill dispatcher has a latched terminal fault."
                        if not dispatcher_ready
                        else skills["absence_reason"]
                        or "Observation/model preflight is unavailable."
                    )
                ),
                "physical_authority": False,
            },
            "physical_shadow": {
                "selectable": common and skills["physical_shadow_ready"] and dispatcher_ready,
                "reason": (
                    None
                    if common and skills["physical_shadow_ready"] and dispatcher_ready
                    else (
                        "Skill dispatcher has a latched terminal fault."
                        if not dispatcher_ready
                        else skills["absence_reason"] or "Shadow preflight is unavailable."
                    )
                ),
                "issues_hardware_command": False,
                "physical_authority": False,
            },
            "physical_gated": {
                "selectable": False,
                "reason": "Physical gated execution is outside this brief and remains disabled.",
                "physical_authority": False,
            },
        }
        if self.demo_loop_start is not None and self.demo_loop_status is not None:
            demo = self._demo_loop_snapshot()
            capabilities["demo_physical"] = {
                "selectable": bool(demo["ready"]),
                "reason": demo.get("reason"),
                "physical_authority": bool(demo["physical_authority"]),
                "authority_scope": demo["authority_scope"],
            }
        return capabilities

    def _demo_loop_snapshot(
        self,
        workcell: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.demo_loop_status is None:
            return {
                "enabled": False,
                "status": "unavailable",
                "ready": False,
                "reason": "The fixed demo loop controller is unavailable.",
                "authority_scope": "none",
                "physical_authority": False,
            }
        try:
            controller = dict(self.demo_loop_status())
        except Exception as error:
            controller = {
                "enabled": True,
                "status": "failed",
                "error": f"{type(error).__name__}: {error}",
            }
        source = self._source_preflight()
        if workcell is None:
            try:
                workcell = dict(self.workcell_status()) if self.workcell_status else {}
            except Exception as error:
                workcell = {"error": f"{type(error).__name__}: {error}"}
        follower_connected = any(
            bool(row.get("connected"))
            for row in (workcell.get("arms") or [])
            if row.get("id") == "so101-follower" or row.get("role") == "follower"
        )
        camera_ready = bool(source.get("ready"))
        running = controller.get("status") in {"running", "stopping"}
        ready = bool(
            controller.get("enabled", True)
            and camera_ready
            and follower_connected
        )
        missing: list[str] = []
        if not camera_ready:
            missing.append("visible overhead camera")
        if not follower_connected:
            missing.append("connected follower")
        return {
            **controller,
            "enabled": True,
            "ready": ready or running,
            "camera_ready": camera_ready,
            "follower_connected": follower_connected,
            "reason": None if ready or running else " and ".join(missing) + " required.",
            "authority_scope": "fixed_owner_directed_base_inverse_base_script_only",
            "physical_authority": bool(ready or running),
            "registration_required_for_demo_script": False,
        }

    @staticmethod
    def _is_demo_loop_command(message: str) -> bool:
        normalized = " ".join(
            "".join(character if character.isalnum() else " " for character in message.casefold()).split()
        )
        return normalized in {
            "loop it",
            "run the loop",
            "start the loop",
            "loop the base case",
            "run the base case loop",
        }

    def _sync_demo_loop_locked(self) -> dict[str, Any]:
        demo = self._demo_loop_snapshot()
        status = str(demo.get("status") or "unavailable")
        prior = self.demo_loop_last_status
        self.state["demo_loop"] = demo
        self.state["physical_authority"] = bool(demo.get("physical_authority"))
        if status in {"running", "stopping"}:
            self.state["main_status"] = "executing"
            action = str(demo.get("action") or "loop")
            self.state["action_queue"]["current_action"] = {
                "decision": "run_demo_script",
                "skill_id": "five_minute_base_loop_script",
                "arguments": {"duration_seconds": 300, "action": action},
            }
            self.state["action_queue"]["verification"] = status
        elif prior in {"running", "stopping"} and status in {"completed", "failed", "stopped"}:
            self.state["action_queue"]["current_action"] = None
            self.state["action_queue"]["verification"] = (
                "command_cycle_completed_task_unverified"
                if status == "completed"
                else status
            )
            self.state["main_status"] = (
                "command_cycle_complete" if status == "completed" else "failed"
            )
            action_label = str(demo.get("action") or "loop").replace("_", " ")
            message = (
                f"The fixed {action_label} command sequence completed. "
                "Overhead checkpoints and the aggregate receipt were saved."
                if status == "completed"
                else f"The fixed demo loop {status}: {demo.get('error') or 'see its receipt.'}"
            )
            self.recent_conversation.append(
                {
                    "role": "assistant",
                    "message": message,
                    "decision": "demo_loop_status",
                    "recorded_at": self.utc_now().isoformat(),
                }
            )
            maximum = int(self.config["model"]["maximum_recent_messages"])
            self.recent_conversation = self.recent_conversation[-maximum:]
            self._event_locked("demo_loop_finished", demo)
        self.demo_loop_last_status = status
        return demo

    def _source_preflight(self) -> dict[str, Any]:
        if self.frame_source_status is None:
            return {
                "ready": self.frame_credential_configured,
                "reason": (
                    None
                    if self.frame_credential_configured
                    else "server-side Silicon snapshot credential"
                ),
                **self.source_metadata,
                "physical_authority": False,
            }
        try:
            dynamic = dict(self.frame_source_status())
        except Exception as error:
            dynamic = {
                "ready": False,
                "reason": f"Source preflight failed: {type(error).__name__}: {error}",
            }
        return {
            **self.source_metadata,
            **dynamic,
            "physical_authority": False,
        }

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            self._update_timer_snapshot_locked()
            self._sync_demo_loop_locked()
            payload = json.loads(json.dumps(self.state))
            source_preflight = self._source_preflight()
            payload["source"].update(
                {
                    "ready": bool(source_preflight.get("ready")),
                    "available": bool(source_preflight.get("available", source_preflight.get("ready"))),
                    "device_name": source_preflight.get("device_name"),
                    "device_index": source_preflight.get("device_index"),
                    "busy": bool(source_preflight.get("busy", False)),
                    "preflight_reason": source_preflight.get("reason"),
                }
            )
            payload["modes"] = self._mode_capabilities()
            payload["allowed_skills"] = self.registry.public_rows(self.last_skill_results)
            payload["dispatcher"] = self.dispatcher.snapshot()
            payload["physical_canary_gate"] = {
                "gate_id": self.physical_canary_gate["gate_id"],
                "status": self.physical_canary_gate["status"],
                "enabled": self.physical_canary_gate["canary"]["enabled"],
                "evaluator_id": self.physical_evaluator["evaluator_id"],
                "evaluator_status": self.physical_evaluator["status"],
                "physical_authority": False,
            }
            payload["ledger"] = json.loads(json.dumps(self.ledger_tail))
            payload["conversation"] = json.loads(json.dumps(self.recent_conversation))
            payload["objective"] = json.loads(json.dumps(self.active_objective))
            if self.workcell_status is not None:
                try:
                    payload["workcell"] = json.loads(json.dumps(self.workcell_status()))
                except Exception as error:
                    payload["workcell"] = {
                        "schema_version": "sim2claw.orchestrator_workcell_inventory.v1",
                        "arms": [],
                        "cameras": [],
                        "error": f"{type(error).__name__}: {error}",
                        "physical_authority": False,
                    }
            demo = self._demo_loop_snapshot(payload.get("workcell") or {})
            payload["demo_loop"] = demo
            payload["physical_authority"] = bool(demo.get("physical_authority"))
            payload["torque_off"] = (
                "guarded_replay_releases_between_moves"
                if demo.get("physical_authority")
                else payload.get("torque_off")
            )
            payload["receipt_directory"] = (
                str(self.session_directory.relative_to(self.repo_root))
                if self.session_directory is not None
                else None
            )
            return payload

    def frame_payload(self) -> tuple[bytes, str, str] | None:
        with self.lock:
            if self.latest_frame_bytes is None or self.latest_frame_content_type is None:
                return None
            digest = hashlib.sha256(self.latest_frame_bytes).hexdigest()
            return self.latest_frame_bytes, self.latest_frame_content_type, digest

    def preview_source(self) -> dict[str, Any]:
        """Capture one operator preview without starting a model/session ledger."""

        with self.lock:
            if self.state["state"] != "STOPPED":
                raise TaskOrchestratorError(
                    "Use Refresh frame while a task session is active."
                )
            if not self._source_preflight().get("ready"):
                raise TaskOrchestratorError(
                    str(
                        self._source_preflight().get("reason")
                        or "The selected overhead source is unavailable."
                    )
                )
        adapter = self.frame_adapter_factory()
        try:
            frame = adapter.fetch()
        except FrameSourceError as error:
            with self.lock:
                self.state["source"]["health"] = "fault"
                self.state["source"]["connected"] = False
                self.state["source"]["latest_error"] = error.receipt()
            raise TaskOrchestratorError(str(error)) from error
        finally:
            adapter.close()
        with self.lock:
            self.latest_frame = frame
            self.latest_frame_bytes = frame.image_bytes
            self.latest_frame_content_type = f"image/{frame.record['encoding']}"
            self.state["source"].update(
                {
                    "health": "healthy",
                    "connected": True,
                    "latest_captured_at": frame.record["capture_timestamp"],
                    "latest_preview_sha256": frame.sha256,
                    "latest_error": None,
                    "live_connectivity_verified": True,
                    "registration_state": frame.record.get("registration_state")
                    or self.source_metadata.get("registration_state"),
                }
            )
            return self.snapshot()

    def _transition_locked(self, new_state: str, *, main_status: str | None = None) -> None:
        current = str(self.state["state"])
        if new_state == current:
            if main_status is not None:
                self.state["main_status"] = main_status
            return
        if new_state not in STATE_TRANSITIONS.get(current, set()):
            raise TaskOrchestratorError(f"Invalid orchestrator transition {current}->{new_state}")
        self.state["state"] = new_state
        if main_status is not None:
            self.state["main_status"] = main_status
        self.state["updated_at"] = self.utc_now().isoformat()

    def _event_locked(self, event: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        session_id = self.state.get("session_id")
        if not session_id:
            return {}
        row = {
            "schema_version": ORCHESTRATOR_EVENT_SCHEMA,
            "sequence": self.event_sequence,
            "session_id": session_id,
            "event": event,
            "recorded_at": self.utc_now().isoformat(),
            "payload": json.loads(json.dumps(payload)),
            "physical_authority": False,
        }
        self.event_sequence += 1
        self.ledger_tail.append(row)
        limit = int(self.config["receipts"]["ledger_tail_api_limit"])
        self.ledger_tail = self.ledger_tail[-limit:]
        if self.ledger_path is not None:
            self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
            with self.ledger_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
        return row

    def _session_manifest(self) -> dict[str, Any]:
        contracts = {
            str(path.relative_to(self.authority_root)): _sha256(path)
            for path in (
                self.config_path,
                self.base_case_path,
                self.snapshot_contract_path,
                self.registry_path,
                self.decision_schema_path,
                self.fixture_manifest_path,
                self.physical_canary_gate_path,
                self.physical_evaluator_path,
                self.event_schema_path,
                self.result_schema_path,
                self.reference_image_path,
            )
        }
        return {
            "schema_version": "sim2claw.task_orchestrator_session.v1",
            "session_id": self.state["session_id"],
            "task_id": self.config["task"]["task_id"],
            "mode": self.state["mode"],
            "started_at": self.state["started_at"],
            "contracts": contracts,
            "source": {
                "adapter_id": self.source_metadata["adapter_id"],
                "host": self.source_metadata["host"],
                "camera_role": self.source_metadata["camera_role"],
                "roi_contract_id": self.source_metadata["roi_contract_id"],
                "registration_state": self.source_metadata.get("registration_state"),
            },
            "model": {
                "adapter_id": self.config["model"]["adapter_id"],
                "provider_model_id": self.config["model"]["provider_model_id"],
                "user_facing_label": self.config["model"]["user_facing_label"],
                "reasoning_effort": self.config["model"]["reasoning_effort"],
                "substitution_allowed": False,
            },
            "settings": self.state["settings"],
            "credentials_recorded": False,
            "raw_remote_url_recorded": False,
            "physical_authority": False,
            "torque_off": "not_applicable_no_physical_adapter",
        }

    def start(self, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        settings = dict(payload or {})
        with self.lock:
            if self.state["state"] != "STOPPED":
                raise TaskOrchestratorError("A new session can start only from STOPPED.")
            mode = str(settings.get("mode") or self.config["execution"]["default_mode"])
            capability = self._mode_capabilities().get(mode)
            if capability is None:
                raise TaskOrchestratorError("Unknown orchestrator mode.")
            if not capability["selectable"]:
                raise TaskOrchestratorError(str(capability["reason"]))
            self.state = self._initial_state()
            self.state["mode"] = mode
            self._apply_settings_locked(settings)
            now = self.utc_now()
            session_id = now.strftime("%Y%m%dT%H%M%S.%fZ-") + secrets.token_hex(4)
            self.state["session_id"] = session_id
            self.state["started_at"] = now.isoformat()
            self.state["pause_reason"] = None
            self.state["fault"] = None
            self.state["task_outcome"] = None
            self.event_sequence = 0
            self.ledger_tail = []
            self.recent_conversation = []
            self.latest_frame = None
            self.latest_frame_bytes = None
            self.latest_frame_content_type = None
            self.last_accepted_roi = None
            self.last_base_state = None
            self.pending_postcondition = None
            self.last_skill_results = {}
            self.active_objective = None
            self.frame_adapter = self.frame_adapter_factory()
            self.model_adapter = self.model_adapter_factory()
            receipt_root = self.repo_root / self.config["receipts"]["root"]
            self.session_directory = receipt_root / session_id
            self.ledger_path = self.session_directory / "ledger.jsonl"
            self.session_directory.mkdir(parents=True, exist_ok=False)
            _atomic_json(self.session_directory / "session.json", self._session_manifest())
            now_mono = self.monotonic()
            self.last_user_activity_monotonic = now_mono
            self.last_world_activity_monotonic = now_mono
            self.next_poll_monotonic = now_mono
            self._transition_locked("STARTING", main_status="observing")
            self._event_locked(
                "session_started",
                {"mode": mode, "forced_accept_reason": "start", "settings": self.state["settings"]},
            )
            if mode == "demo_physical":
                # The demo lane is command-driven. Starting its chat session
                # must not produce an unsolicited planning turn before the
                # operator types the exact loop command.
                self.next_poll_monotonic = None
                self._transition_locked("OBSERVING", main_status="ready")
            else:
                self.pending_reasons.append("start")
                self.wake_event.set()
            return self.snapshot()

    def _apply_settings_locked(self, payload: Mapping[str, Any]) -> None:
        if "polling_interval_seconds" in payload:
            value = float(payload["polling_interval_seconds"])
            minimum = float(self.config["polling"]["minimum_interval_seconds"])
            maximum = float(self.config["polling"]["maximum_interval_seconds"])
            if not minimum <= value <= maximum:
                raise TaskOrchestratorError(
                    f"Polling interval must be between {minimum:g} and {maximum:g} seconds."
                )
            self.state["settings"]["polling_interval_seconds"] = value
        for request_name, state_name in (
            ("user_inactivity_seconds", "user_inactivity_seconds"),
            ("world_action_inactivity_seconds", "world_action_inactivity_seconds"),
        ):
            if request_name in payload:
                value = float(payload[request_name])
                if not 30 <= value <= 3600:
                    raise TaskOrchestratorError("Inactivity timers must be between 30 and 3600 seconds.")
                self.state["settings"][state_name] = value

    def configure(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        with self.lock:
            self._apply_settings_locked(payload)
            self._event_locked("settings_changed", {"settings": self.state["settings"]})
            self.wake_event.set()
            return self.snapshot()

    def chat(self, message: str) -> dict[str, Any]:
        message = message.strip()
        if not message or len(message) > 2000:
            raise TaskOrchestratorError("Chat message must contain 1 to 2000 characters.")
        with self.lock:
            if self.state["state"] not in ACTIVE_STATES:
                raise TaskOrchestratorError("Chat can wake only an active session.")
            row = {"role": "user", "message": message, "recorded_at": self.utc_now().isoformat()}
            self.recent_conversation.append(row)
            maximum = int(self.config["model"]["maximum_recent_messages"])
            self.recent_conversation = self.recent_conversation[-maximum:]
            self.last_user_activity_monotonic = self.monotonic()
            self._event_locked("user_chat", row)
            if self._is_demo_loop_command(message) and self.demo_loop_start is not None:
                demo = self._demo_loop_snapshot()
                if not demo.get("ready"):
                    raise TaskOrchestratorError(
                        str(demo.get("reason") or "The fixed demo loop is unavailable.")
                    )
                started = dict(self.demo_loop_start())
                self.demo_loop_last_status = str(started.get("status") or "running")
                self.state["demo_loop"] = started
                self.state["physical_authority"] = True
                self.state["main_status"] = "executing"
                self.state["action_queue"] = {
                    "proposed_plan": [
                        {
                            "decision": "run_demo_script",
                            "reason": "Exact demo chat command routed directly to the fixed loopback script.",
                            "skill_id": "five_minute_base_loop_script",
                            "arguments": {"duration_seconds": 300},
                            "expected_postcondition": {},
                            "confidence": 1.0,
                        }
                    ],
                    "current_action": {
                        "decision": "run_demo_script",
                        "skill_id": "five_minute_base_loop_script",
                        "arguments": {"duration_seconds": 300},
                    },
                    "expected_postcondition": None,
                    "verification": "running",
                }
                assistant = {
                    "role": "assistant",
                    "message": (
                        "Starting the fixed five-minute base → inverse → base demo loop now. "
                        "The LLM planner was bypassed; the guarded Python runner owns execution."
                    ),
                    "decision": "run_demo_script",
                    "recorded_at": self.utc_now().isoformat(),
                }
                self.recent_conversation.append(assistant)
                self.recent_conversation = self.recent_conversation[-maximum:]
                self._event_locked("demo_loop_started", started)
                self.pending_reasons.clear()
                self.next_poll_monotonic = None
                self.last_world_activity_monotonic = self.monotonic()
                return self.snapshot()
            self.active_objective = interpret_objective(message)
            self.active_objective["created_at"] = self.utc_now().isoformat()
            self._event_locked("objective_accepted", self.active_objective)
            self.pending_reasons.append("user_chat")
            self.wake_event.set()
            return self.snapshot()

    def refresh(self) -> dict[str, Any]:
        with self.lock:
            if self.state["state"] not in ACTIVE_STATES:
                raise TaskOrchestratorError("Refresh requires an active session.")
            self.last_user_activity_monotonic = self.monotonic()
            self._event_locked("user_refresh_requested", {})
            self.pending_reasons.append("user_refresh")
            self.wake_event.set()
            return self.snapshot()

    def acknowledge(self, message: str = "operator acknowledgement") -> dict[str, Any]:
        with self.lock:
            if self.state["state"] not in ACTIVE_STATES:
                raise TaskOrchestratorError("Acknowledgement requires an active session.")
            self.last_user_activity_monotonic = self.monotonic()
            self._event_locked("user_acknowledgement", {"message": message[:500]})
            return self.snapshot()

    def shadow_choice(
        self,
        *,
        skill_id: str | None,
        operator_identity: str,
        note: str = "",
    ) -> dict[str, Any]:
        operator_identity = operator_identity.strip()
        note = note.strip()
        if not 1 <= len(operator_identity) <= 128:
            raise TaskOrchestratorError(
                "Shadow comparison requires an operator identity of 1 to 128 characters."
            )
        if len(note) > 500:
            raise TaskOrchestratorError("Shadow comparison note is limited to 500 characters.")
        normalized_choice = (skill_id or "").strip() or None
        with self.lock:
            if self.state["state"] != "PAUSED" or self.state["mode"] != "physical_shadow":
                raise TaskOrchestratorError(
                    "A shadow choice requires a paused physical-shadow proposal."
                )
            if self.state["action_queue"]["verification"] != (
                "awaiting_operator_shadow_choice"
            ):
                raise TaskOrchestratorError("No physical-shadow proposal is awaiting review.")
            proposals = self.state["action_queue"].get("proposed_plan") or []
            if len(proposals) != 1 or proposals[0].get("decision") != "run_skill":
                raise TaskOrchestratorError("The pending shadow proposal is malformed.")
            proposal = proposals[0]
            proposed_skill_id = str(proposal["skill_id"])
            proposed_entry = self.registry.entry(proposed_skill_id)

            operator_choice: dict[str, Any] | None = None
            if normalized_choice is not None:
                choice_entry = self.registry.entry(normalized_choice)
                readiness = self.registry.readiness(normalized_choice, "physical_shadow")
                if not readiness["ready"]:
                    raise TaskOrchestratorError(
                        "The operator choice is not a promoted physical-shadow skill."
                    )
                operator_choice = {
                    "skill_id": normalized_choice,
                    "checkpoint_sha256": choice_entry.payload["checkpoint_sha256"],
                    "evaluator_receipt_sha256": choice_entry.payload[
                        "evaluator_receipt_sha256"
                    ],
                    "promotion_receipt_sha256": choice_entry.payload[
                        "promotion_receipt_sha256"
                    ],
                }

            comparison = {
                "schema_version": "sim2claw.orchestrator_shadow_comparison.v1",
                "recorded_at": self.utc_now().isoformat(),
                "session_id": self.state["session_id"],
                "operator_identity": operator_identity,
                "operator_note": note or None,
                "accepted_frame_sha256": self.state["source"][
                    "latest_accepted_sha256"
                ],
                "managed_region_state": json.loads(json.dumps(self.state["base_case"])),
                "model_proposal": json.loads(json.dumps(proposal)),
                "proposed_skill_identity": {
                    "skill_id": proposed_skill_id,
                    "checkpoint_sha256": proposed_entry.payload["checkpoint_sha256"],
                    "evaluator_receipt_sha256": proposed_entry.payload[
                        "evaluator_receipt_sha256"
                    ],
                    "promotion_receipt_sha256": proposed_entry.payload[
                        "promotion_receipt_sha256"
                    ],
                },
                "operator_choice": operator_choice,
                "exact_choice_match": normalized_choice == proposed_skill_id,
                "hardware_command_issued": False,
                "physical_authority": False,
            }
            self.state["physical_shadow"]["comparison_count"] += 1
            self.state["physical_shadow"]["latest_comparison"] = comparison
            by_skill = self.state["physical_shadow"]["by_proposed_skill"]
            prior_summary = by_skill.get(proposed_skill_id) or {
                "trials": 0,
                "exact_matches": 0,
            }
            trials = int(prior_summary["trials"]) + 1
            exact_matches = int(prior_summary["exact_matches"]) + int(
                comparison["exact_choice_match"]
            )
            required_trials = int(
                self.physical_canary_gate["shadow_protocol"][
                    "minimum_supervised_trials_per_skill"
                ]
            )
            required_match_rate = float(
                self.physical_canary_gate["shadow_protocol"][
                    "required_exact_operator_choice_match_rate"
                ]
            )
            exact_match_rate = exact_matches / trials
            by_skill[proposed_skill_id] = {
                "trials": trials,
                "exact_matches": exact_matches,
                "exact_match_rate": round(exact_match_rate, 6),
                "minimum_supervised_trials": required_trials,
                "required_exact_match_rate": required_match_rate,
                "protocol_passed": (
                    trials >= required_trials
                    and exact_match_rate >= required_match_rate
                ),
                "physical_authority": False,
            }
            self.state["action_queue"]["verification"] = (
                "shadow_exact_match"
                if comparison["exact_choice_match"]
                else "shadow_choice_mismatch"
            )
            self.state["pause_reason"] = "shadow_choice_recorded_requires_resume"
            self.last_user_activity_monotonic = self.monotonic()
            self._event_locked("shadow_operator_choice_recorded", comparison)
            return self.snapshot()

    def pause(self, reason: str = "user_pause") -> dict[str, Any]:
        with self.lock:
            self._pause_locked(reason)
            return self.snapshot()

    def _pause_locked(self, reason: str) -> None:
        if self.state["state"] == "PAUSED":
            return
        if self.state["state"] not in ACTIVE_STATES | {"FAULTED"}:
            raise TaskOrchestratorError("Only an active or faulted session can pause.")
        self._transition_locked("PAUSING", main_status=("failed" if reason.startswith("fault:") else self.state["main_status"]))
        safe_stop = self.dispatcher.safe_stop()
        self.state["pause_reason"] = reason
        self.next_poll_monotonic = None
        self.pending_reasons.clear()
        self._event_locked("session_pausing", {"reason": reason, "safe_stop": safe_stop})
        self._transition_locked("PAUSED")
        self._event_locked("session_paused", {"reason": reason, "safe_stop": safe_stop})

    def _release_adapters_locked(self) -> dict[str, Any]:
        safe_stop = self.dispatcher.safe_stop()
        close_errors: dict[str, str] = {}
        for name, adapter in (
            ("frame", self.frame_adapter),
            ("model", self.model_adapter),
        ):
            if adapter is None:
                continue
            try:
                adapter.close()
            except Exception as error:  # retain release failures without reopening authority
                close_errors[name] = f"{type(error).__name__}: {error}"
        self.frame_adapter = None
        self.model_adapter = None
        return {
            "safe_stop": safe_stop,
            "frame_released": "frame" not in close_errors,
            "model_released": "model" not in close_errors,
            "close_errors": close_errors,
            "physical_authority": False,
        }

    def resume(self) -> dict[str, Any]:
        with self.lock:
            if self.state["state"] != "PAUSED":
                raise TaskOrchestratorError("Resume requires PAUSED state.")
            prior_fault = self.state.get("fault")
            if self.frame_adapter is None or self.model_adapter is None:
                frame_adapter: FrameAdapter | None = None
                model_adapter: OpenAIOrchestratorModel | None = None
                try:
                    frame_adapter = self.frame_adapter_factory()
                    model_adapter = self.model_adapter_factory()
                except Exception as error:
                    for adapter in (frame_adapter, model_adapter):
                        if adapter is not None:
                            try:
                                adapter.close()
                            except Exception:
                                pass
                    raise TaskOrchestratorError(
                        f"Session resources could not be reacquired: {type(error).__name__}: {error}"
                    ) from error
                self.frame_adapter = frame_adapter
                self.model_adapter = model_adapter
            self.state["pause_reason"] = None
            self.state["fault"] = None
            now = self.monotonic()
            self.last_user_activity_monotonic = now
            self.last_world_activity_monotonic = now
            self.next_poll_monotonic = now
            self._transition_locked("STARTING", main_status="observing")
            reason = (
                "source_health_recovery"
                if prior_fault and prior_fault.get("category") == "frame_source"
                else "resume"
            )
            self._event_locked("session_resumed", {"forced_accept_reason": reason})
            self.pending_reasons.append(reason)
            self.wake_event.set()
            return self.snapshot()

    def stop(self, reason: str = "user_stop", *, task_outcome: str | None = None) -> dict[str, Any]:
        with self.lock:
            if self.demo_loop_stop is not None:
                demo = self._demo_loop_snapshot()
                if demo.get("status") in {"running", "stopping"}:
                    self.demo_loop_stop()
            if self.state["state"] == "STOPPED":
                return self.snapshot()
            if self.state["state"] not in ACTIVE_STATES | {"PAUSED", "FAULTED", "PAUSING"}:
                raise TaskOrchestratorError("Session cannot stop from its current state.")
            self._transition_locked("STOPPING", main_status=("verified" if task_outcome == "complete" else self.state["main_status"]))
            release = self._release_adapters_locked()
            self.pending_reasons.clear()
            self.next_poll_monotonic = None
            if task_outcome is not None:
                self.state["task_outcome"] = task_outcome
            self._event_locked("session_stopping", {"reason": reason, "release": release})
            self._transition_locked("STOPPED")
            self._event_locked(
                "session_stopped",
                {
                    "reason": reason,
                    "task_outcome": self.state["task_outcome"],
                    "release": release,
                    "physical_authority": False,
                    "torque_off": "not_applicable_no_physical_adapter",
                },
            )
            if self.session_directory is not None:
                _atomic_json(
                    self.session_directory / "final.json",
                    {
                        "schema_version": "sim2claw.task_orchestrator_final.v1",
                        "session_id": self.state["session_id"],
                        "stopped_at": self.utc_now().isoformat(),
                        "reason": reason,
                        "state": self.state["state"],
                        "main_status": self.state["main_status"],
                        "task_outcome": self.state["task_outcome"],
                        "base_case": self.state["base_case"],
                        "frame_counts": self.state["comparison"],
                        "physical_authority": False,
                        "torque_off": "not_applicable_no_physical_adapter",
                    },
                )
            return self.snapshot()

    def _fault(self, category: str, detail: Mapping[str, Any]) -> None:
        with self.lock:
            if self.state["state"] not in ACTIVE_STATES:
                return
            self._transition_locked("FAULTED", main_status="failed")
            self.state["fault"] = {"category": category, **json.loads(json.dumps(detail))}
            self._event_locked("fault", self.state["fault"])
            self._pause_locked(f"fault:{category}")
            release = self._release_adapters_locked()
            self._event_locked("fault_resources_released", release)

    def _update_timer_snapshot_locked(self) -> None:
        if self.state["state"] not in ACTIVE_STATES:
            return
        now = self.monotonic()
        user_elapsed = (
            now - self.last_user_activity_monotonic
            if self.last_user_activity_monotonic is not None
            else 0.0
        )
        world_elapsed = (
            now - self.last_world_activity_monotonic
            if self.last_world_activity_monotonic is not None
            else 0.0
        )
        self.state["timers"] = {
            "user_remaining_seconds": round(
                max(0.0, float(self.state["settings"]["user_inactivity_seconds"]) - user_elapsed),
                3,
            ),
            "world_action_remaining_seconds": round(
                max(
                    0.0,
                    float(self.state["settings"]["world_action_inactivity_seconds"])
                    - world_elapsed,
                ),
                3,
            ),
        }

    def _check_inactivity(self) -> bool:
        with self.lock:
            if self.state["state"] not in ACTIVE_STATES:
                return False
            demo = self._sync_demo_loop_locked()
            if demo.get("status") in {"running", "stopping"}:
                now = self.monotonic()
                self.last_user_activity_monotonic = now
                self.last_world_activity_monotonic = now
                self._update_timer_snapshot_locked()
                return False
            self._update_timer_snapshot_locked()
            timers = self.state["timers"]
            reason = None
            if timers["user_remaining_seconds"] <= 0:
                reason = "user_inactivity_timeout"
            elif timers["world_action_remaining_seconds"] <= 0:
                reason = "world_action_inactivity_timeout"
            if reason:
                self._event_locked("inactivity_expired", {"reason": reason, "timers": timers})
                self._pause_locked(reason)
                return True
            return False

    def _worker_loop(self) -> None:
        while not self.shutdown_event.is_set():
            if self._check_inactivity():
                continue
            reason: str | None = None
            wait_seconds = 1.0
            with self.lock:
                demo = self._sync_demo_loop_locked()
                if demo.get("status") in {"running", "stopping"}:
                    wait_seconds = 0.5
                    reason = None
                elif self.pending_reasons and self.state["state"] in ACTIVE_STATES:
                    reason = self.pending_reasons.pop(0)
                elif self.state["state"] in ACTIVE_STATES and self.next_poll_monotonic is not None:
                    remaining = self.next_poll_monotonic - self.monotonic()
                    if remaining <= 0:
                        reason = "poll"
                    else:
                        wait_seconds = min(1.0, max(0.02, remaining))
            if reason is None:
                self.wake_event.wait(wait_seconds)
                self.wake_event.clear()
                continue
            self._process_observation(reason)

    def process_pending_once(self) -> bool:
        """Deterministic test/CLI hook; production uses the background worker."""

        if self._check_inactivity():
            return True
        with self.lock:
            if (
                self.state.get("mode") == "demo_physical"
                and not self.pending_reasons
                and self.next_poll_monotonic is None
            ):
                return False
            if self.pending_reasons:
                reason = self.pending_reasons.pop(0)
            elif self.state["state"] in ACTIVE_STATES:
                reason = "poll"
            else:
                return False
        self._process_observation(reason)
        return True

    def _accept_reason(self, reason: str) -> bool:
        return reason in {
            "start",
            "resume",
            "source_health_recovery",
            "user_chat",
            "user_refresh",
            "skill_completion",
            "skill_failure",
        }

    def _store_accepted_frame(self, frame: SnapshotFrame) -> str | None:
        if self.session_directory is None or not self.config["receipts"][
            "retain_raw_accepted_frames"
        ]:
            return None
        extension = ".jpg" if frame.record["encoding"] == "jpeg" else ".png"
        relative = Path("frames") / "accepted" / (
            f"{self.state['comparison']['accepted_count']:04d}-{frame.sha256}{extension}"
        )
        destination = self.session_directory / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(frame.image_bytes)
        return str(relative)

    def _process_observation(self, reason: str) -> None:
        with self.lock:
            if self.state["state"] not in ACTIVE_STATES:
                return
            if self.state["state"] == "STARTING":
                self._transition_locked("OBSERVING", main_status="observing")
            self.next_poll_monotonic = self.monotonic() + float(
                self.state["settings"]["polling_interval_seconds"]
            )
            frame_adapter = self.frame_adapter
        if frame_adapter is None:
            self._fault("frame_source", {"code": "adapter_unavailable"})
            return
        try:
            frame = frame_adapter.fetch()
        except FrameSourceError as error:
            with self.lock:
                if self.state["state"] == "STOPPED":
                    return
                self.state["source"]["health"] = "fault"
                self.state["source"]["connected"] = False
                self.state["source"]["latest_error"] = error.receipt()
                self._event_locked("frame_capture_failed", error.receipt())
            self._fault("frame_source", error.receipt())
            return
        try:
            comparison_size = tuple(int(value) for value in self.config["deduplication"]["comparison_size"])
            roi = prepare_registered_roi(frame.image_bgr, comparison_size)  # type: ignore[arg-type]
            with self.lock:
                if self.state["state"] == "STOPPED":
                    return
                similarity = (
                    None
                    if self.last_accepted_roi is None
                    else round(normalized_luminance_ssim(self.last_accepted_roi, roi), 6)
                )
                forced = self._accept_reason(reason)
                suppressed = (
                    similarity is not None
                    and similarity >= float(self.state["settings"]["deduplication_threshold"])
                    and not forced
                )
                self.state["comparison"]["captured_count"] += 1
                self.state["comparison"]["similarity"] = similarity
                self.state["source"].update(
                    {
                        "health": "healthy",
                        "connected": True,
                        "latest_captured_at": frame.record["capture_timestamp"],
                        "latest_error": None,
                        "live_connectivity_verified": True,
                        "registration_state": frame.record.get("registration_state")
                        or self.source_metadata.get("registration_state"),
                    }
                )
                if suppressed:
                    self.state["comparison"]["suppression_count"] += 1
                    self._event_locked(
                        "frame_ignored",
                        {
                            "frame": frame.record,
                            "similarity": similarity,
                            "threshold": self.state["settings"]["deduplication_threshold"],
                            "reason": "deduplication_threshold",
                            "inactivity_timers_reset": False,
                        },
                    )
                    self._transition_locked("OBSERVING", main_status="observing")
                    return
                material_change = similarity is not None and similarity < float(
                    self.state["settings"]["deduplication_threshold"]
                )
                if material_change:
                    self.last_world_activity_monotonic = self.monotonic()
                self.last_accepted_roi = roi
                self.latest_frame = frame
                self.latest_frame_bytes = frame.image_bytes
                self.latest_frame_content_type = f"image/{frame.record['encoding']}"
                self.state["comparison"]["accepted_count"] += 1
                self.state["source"]["latest_accepted_sha256"] = frame.sha256
                retained_path = self._store_accepted_frame(frame)
                if frame.record.get("perception_ready", True):
                    base_state = self.classifier.classify(
                        frame.image_bgr, evidence_frame_sha256=frame.sha256
                    )
                else:
                    base_state = self._unregistered_base_state(frame)
                prior_base_state = self.last_base_state
                self.last_base_state = base_state
                self.state["base_case"] = base_state
                self._event_locked(
                    "frame_accepted",
                    {
                        "frame": frame.record,
                        "similarity": similarity,
                        "threshold": self.state["settings"]["deduplication_threshold"],
                        "forced_accept_reason": reason if forced else None,
                        "material_change": material_change,
                        "retained_path": retained_path,
                        "base_case": base_state,
                    },
                )
                pending = self.pending_postcondition
        except Exception as error:
            self._fault(
                "perception",
                {"code": "perception_failed", "message": f"{type(error).__name__}: {error}"},
            )
            return

        if pending is not None and reason in {"skill_completion", "skill_failure"}:
            with self.lock:
                if self.state["state"] == "EXECUTING_SKILL":
                    self._transition_locked("VERIFYING", main_status="observing")
                else:
                    # A user Pause may safely stop the adapter before its result
                    # reaches this worker. Resume returns through OBSERVING, where
                    # the forced evidence is still verified without inventing a
                    # state-machine edge.
                    self.state["main_status"] = "observing"
                    self.state["updated_at"] = self.utc_now().isoformat()
                verification = verify_expected_postcondition(
                    pending["before_state"], base_state, pending["expected_postcondition"]
                )
                self.state["action_queue"]["verification"] = (
                    "verified" if verification["passed"] else "failed"
                )
                self.state["action_queue"]["current_action"] = None
                self.last_skill_results[pending["skill_id"]] = {
                    **pending["skill_result"],
                    "postcondition_verification": verification,
                }
                self._event_locked("skill_postcondition_verified", verification)
                self.pending_postcondition = None
                if pending.get("terminal_skill_failure"):
                    self._fault(
                        "execution",
                        {
                            "code": "skill_failed",
                            "skill_id": pending["skill_id"],
                            "result": pending["skill_result"],
                            "post_failure_observation_sha256": frame.sha256,
                            "postcondition_verification": verification,
                        },
                    )
                    return
                if not verification["passed"]:
                    self._fault(
                        "postcondition",
                        {"code": "postcondition_failed", "verification": verification},
                    )
                    return
                self.state["main_status"] = "verified"

        if base_state["deterministic_complete"]:
            with self.lock:
                self.state["main_status"] = "verified"
                self.state["task_outcome"] = "complete"
                self._event_locked(
                    "deterministic_base_case_complete",
                    {
                        "contract_id": base_state["contract_id"],
                        "evidence_frame_sha256": base_state["evidence_frame_sha256"],
                        "completion_owner": "deterministic_managed_region_checker",
                    },
                )
            self.stop("deterministic_base_case_complete", task_outcome="complete")
            return

        if base_state["state"] == "blocked":
            blocker_summary = ", ".join(
                str(row.get("kind") or "unknown_blocker")
                + (
                    f" on {str(row.get('square') or row.get('file')).upper()}"
                    if row.get("square") or row.get("file")
                    else ""
                )
                for row in base_state["blockers"]
            )
            deterministic_request = {
                "decision": "ask_user",
                "reason": f"Managed-region intervention required: {blocker_summary}.",
                "skill_id": None,
                "arguments": {},
                "expected_postcondition": {},
                "confidence": float(base_state["confidence"]),
            }
            with self.lock:
                self.state["action_queue"] = {
                    "proposed_plan": [deterministic_request],
                    "current_action": None,
                    "expected_postcondition": None,
                    "verification": "user_intervention_required",
                }
                self.state["main_status"] = "proposed"
                self.state["updated_at"] = self.utc_now().isoformat()
                self._event_locked(
                    "user_help_requested",
                    {
                        "decision": deterministic_request,
                        "owner": "deterministic_managed_region_checker",
                        "blockers": base_state["blockers"],
                    },
                )
                self._pause_locked("deterministic_base_state_blocked")
            return

        self._run_model_turn(frame, base_state, reason, prior_base_state)

    def _unregistered_base_state(self, frame: SnapshotFrame) -> dict[str, Any]:
        demo_feedback = frame.record.get("registration_state") == "demo_visual_feedback"
        squares = {
            square: {
                "status": "unknown",
                "brown_ratio": None,
                "colored_non_brown_ratio": None,
                "confidence": 0.0,
            }
            for square in self.base_contract.managed_squares
        }
        return {
            "schema_version": "sim2claw.orchestrator_base_state.v1",
            "contract_id": self.base_contract.contract_id,
            "state": "demo_visual_feedback" if demo_feedback else "observation_limited",
            "deterministic_complete": False,
            "required_occupied": sorted(self.base_contract.required_occupied),
            "required_empty": sorted(self.base_contract.required_empty),
            "observed_occupied": [],
            "observed_empty": [],
            "mismatched_files": [],
            "confidence": 0.0,
            "minimum_confidence": self.classifier.minimum_confidence,
            "evidence_frame_sha256": frame.sha256,
            "squares": squares,
            "blockers": [] if demo_feedback else [
                {
                    "kind": "camera_registration_required",
                    "camera_id": frame.record.get("camera_id"),
                    "registration_state": frame.record.get("registration_state"),
                }
            ],
            "suggested_moves": [],
            "comparison_authority": (
                "demo_visual_feedback_without_square_level_registration"
                if demo_feedback
                else "raw_frame_model_context_without_square_level_authority"
            ),
            "physical_authority": False,
        }

    def _model_context(
        self,
        base_state: Mapping[str, Any],
        reason: str,
        prior_base_state: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        return {
            "task_id": self.config["task"]["task_id"],
            "wake_reason": reason,
            "session_state": self.state["state"],
            "mode": self.state["mode"],
            "base_case_contract": self.base_contract.payload,
            "named_layouts": {
                "base_case": {
                    "occupied": ["b1", "c2", "d1", "e2", "f1", "g2"],
                    "empty": ["b2", "c1", "d2", "e1", "f2", "g1"],
                },
                "inverse_base_case": {
                    "occupied": ["b2", "c1", "d2", "e1", "f2", "g1"],
                    "empty": ["b1", "c2", "d1", "e2", "f1", "g2"],
                    "from_base_case_moves": [
                        "pawn_b1_to_b2",
                        "pawn_c2_to_c1",
                        "pawn_d1_to_d2",
                        "pawn_e2_to_e1",
                        "pawn_f1_to_f2",
                        "pawn_g2_to_g1",
                    ],
                },
            },
            "named_loops": {
                "loop_base_case": {
                    "normalize_to": "base_case",
                    "repeat_phases": ["inverse_base_case", "base_case"],
                    "base_to_inverse_moves": [
                        "pawn_b1_to_b2",
                        "pawn_c2_to_c1",
                        "pawn_d1_to_d2",
                        "pawn_e2_to_e1",
                        "pawn_f1_to_f2",
                        "pawn_g2_to_g1",
                    ],
                    "inverse_to_base_moves": [
                        "pawn_b2_to_b1",
                        "pawn_c1_to_c2",
                        "pawn_d2_to_d1",
                        "pawn_e1_to_e2",
                        "pawn_f2_to_f1",
                        "pawn_g1_to_g2",
                    ],
                    "one_move_then_registered_reobservation": True,
                    "duration_is_planning_horizon_not_execution_authority": True,
                }
            },
            "base_case_state": base_state,
            "prior_base_case_state": prior_base_state,
            "newest_user_message": (
                self.recent_conversation[-1]["message"] if self.recent_conversation else None
            ),
            "recent_conversation": self.recent_conversation,
            "recent_action_results": list(self.last_skill_results.values())[-4:],
            "allowlisted_skills": self.registry.public_rows(self.last_skill_results),
            "authority_limits": {
                "managed_region": "B--G ranks 1--2 only",
                "one_skill_per_decision": True,
                "executor_validation_required": True,
                "completion_owner": "deterministic_managed_region_checker",
                "training_or_promotion_allowed": False,
                "raw_joint_or_arbitrary_command_allowed": False,
                "named_layout_assertion_is_planning_only": True,
                "loop_duration_grants_execution_authority": False,
                "physical_authority": False,
            },
        }

    def _run_model_turn(
        self,
        frame: SnapshotFrame,
        base_state: Mapping[str, Any],
        reason: str,
        prior_base_state: Mapping[str, Any] | None,
    ) -> None:
        with self.lock:
            if self.state["state"] not in ACTIVE_STATES:
                return
            self._transition_locked("AWAITING_MODEL", main_status="observing")
            self.state["model"]["active"] = True
            model = self.model_adapter
            context = self._model_context(base_state, reason, prior_base_state)
        if model is None:
            self._fault("model", {"code": "adapter_unavailable"})
            return
        try:
            turn = model.decide(
                context=context,
                accepted_frame_bytes=frame.image_bytes,
                accepted_frame_encoding=frame.record["encoding"],
                reference_frame_bytes=self.reference_image_path.read_bytes(),
            )
        except OrchestratorModelError as error:
            with self.lock:
                if self.state["state"] == "STOPPED":
                    return
                self.state["model"]["active"] = False
                self.state["model"]["last_turn"] = {
                    "validation": {"valid": False},
                    "error": error.receipt(),
                }
                self._event_locked("model_turn_rejected", error.receipt())
            self._fault("model", error.receipt())
            return
        with self.lock:
            self.state["model"]["active"] = False
            if self.state["state"] == "STOPPED":
                return
            if self.state["state"] != "AWAITING_MODEL":
                self._event_locked(
                    "model_turn_discarded",
                    {"reason": "session state changed while model was active", "request_id": turn.get("request_id")},
                )
                return
            self.state["model"]["identity_verified"] = True
            self.state["model"]["last_turn"] = turn
            self.recent_conversation.append(
                {
                    "role": "assistant",
                    "message": str(turn["decision"]["reason"]),
                    "decision": str(turn["decision"]["decision"]),
                    "recorded_at": self.utc_now().isoformat(),
                }
            )
            maximum = int(self.config["model"]["maximum_recent_messages"])
            self.recent_conversation = self.recent_conversation[-maximum:]
            self._event_locked("model_decision", turn)
        self._handle_decision(turn["decision"], base_state)

    def _handle_decision(
        self, decision: Mapping[str, Any], base_state: Mapping[str, Any]
    ) -> None:
        kind = decision["decision"]
        if kind == "observe":
            with self.lock:
                self._transition_locked("OBSERVING", main_status="observing")
            return
        if kind == "ask_user":
            with self.lock:
                self.state["action_queue"]["proposed_plan"] = [dict(decision)]
                self.state["action_queue"]["verification"] = "awaiting_user_message"
                self._transition_locked("PROPOSED_ACTION", main_status="proposed")
                self._event_locked("user_help_requested", {"decision": decision})
                if self.state["mode"] == "observe_only":
                    self._transition_locked("OBSERVING", main_status="proposed")
                else:
                    self._pause_locked("model_requested_user_help")
            return
        if kind == "pause":
            with self.lock:
                self._pause_locked("model_requested_pause")
            return
        if kind == "complete":
            self._fault(
                "model_policy",
                {
                    "code": "model_cannot_own_completion",
                    "message": "Model declared completion before the deterministic checker passed.",
                },
            )
            return
        if kind != "run_skill":
            self._fault("model_policy", {"code": "unknown_decision"})
            return
        skill_id = str(decision["skill_id"])
        try:
            entry = self.registry.entry(skill_id)
            expected_arguments = {
                "source_square": entry.payload["source_square"],
                "destination_square": entry.payload["destination_square"],
            }
            if dict(decision["arguments"]) != expected_arguments:
                raise SkillRegistryError("Model arguments do not match the immutable skill entry.")
            if dict(decision["expected_postcondition"]) != {
                "occupied": [entry.payload["destination_square"]],
                "empty": [entry.payload["source_square"]],
            }:
                raise SkillRegistryError("Model postcondition does not match the immutable skill entry.")
        except SkillRegistryError as error:
            self._fault(
                "model_policy",
                {"code": "skill_proposal_rejected", "message": str(error), "skill_id": skill_id},
            )
            return
        with self.lock:
            self.state["action_queue"] = {
                "proposed_plan": [dict(decision)],
                "current_action": None,
                "expected_postcondition": dict(decision["expected_postcondition"]),
                "verification": "proposed",
            }
            self._transition_locked("PROPOSED_ACTION", main_status="proposed")
            self._event_locked("skill_proposed", {"decision": decision})
            mode = self.state["mode"]
        if mode == "observe_only":
            readiness = self.registry.readiness(skill_id, mode)
            with self.lock:
                if not readiness["promotion_ready"]:
                    verification = "unavailable"
                else:
                    verification = "dry_run_only"
                self.state["action_queue"]["verification"] = verification
                self._event_locked(
                    (
                        "skill_rejected_unavailable"
                        if verification == "unavailable"
                        else "skill_not_dispatched"
                    ),
                    {
                        "skill_id": skill_id,
                        "mode": mode,
                        "reason": verification,
                        "readiness": readiness,
                        "physical_command_issued": False,
                    },
                )
                self._transition_locked("OBSERVING", main_status="proposed")
            return
        if mode == "physical_shadow":
            readiness = self.registry.readiness(skill_id, mode)
            if not readiness["ready"]:
                with self.lock:
                    self.state["action_queue"]["verification"] = "unavailable"
                    self._event_locked(
                        "skill_rejected_unavailable",
                        {
                            "skill_id": skill_id,
                            "mode": mode,
                            "readiness": readiness,
                            "physical_command_issued": False,
                        },
                    )
                    self._pause_locked("unavailable_promoted_skill")
                return
            with self.lock:
                self.state["action_queue"]["verification"] = (
                    "awaiting_operator_shadow_choice"
                )
                self._event_locked(
                    "shadow_action_proposed",
                    {
                        "skill_id": skill_id,
                        "decision": decision,
                        "readiness": readiness,
                        "physical_command_issued": False,
                        "physical_authority": False,
                    },
                )
                self._pause_locked("awaiting_operator_shadow_choice")
            return
        if mode != "simulation":
            self._fault("authority", {"code": "physical_gated_disabled"})
            return
        readiness = self.registry.readiness(skill_id, mode)
        if not readiness["ready"]:
            with self.lock:
                self.state["action_queue"]["verification"] = "unavailable"
                self._event_locked(
                    "skill_rejected_unavailable", {"skill_id": skill_id, "readiness": readiness}
                )
                self._pause_locked("unavailable_promoted_skill")
            return
        with self.lock:
            executed_count = sum(
                1 for row in self.ledger_tail if row.get("event") == "skill_execution_finished"
            )
            if executed_count >= int(self.config["execution"]["maximum_actions_per_session"]):
                self._fault("execution", {"code": "maximum_actions_exceeded"})
                return
            self._transition_locked("EXECUTING_SKILL", main_status="executing")
            self.state["action_queue"]["current_action"] = dict(decision)
            self.state["action_queue"]["verification"] = "executing"
            self.last_world_activity_monotonic = self.monotonic()
            self._event_locked(
                "skill_execution_started",
                {"skill_id": skill_id, "mode": mode, "arguments": decision["arguments"]},
            )
        try:
            result = self.dispatcher.dispatch(
                skill_id,
                decision["arguments"],
                mode=mode,
                latest_state=base_state,
            )
        except SkillRegistryError as error:
            self._fault(
                "execution", {"code": "dispatch_rejected", "message": str(error), "skill_id": skill_id}
            )
            return
        with self.lock:
            if self.state["state"] == "STOPPED":
                # Stop already recorded the terminal receipt and released every
                # adapter. A late simulation result cannot reopen the session or
                # append work after session_stopped.
                return
            self.last_world_activity_monotonic = self.monotonic()
            self._event_locked("skill_execution_finished", result)
            if result["status"] != "completed":
                self.pending_postcondition = {
                    "skill_id": skill_id,
                    "before_state": json.loads(json.dumps(base_state)),
                    "expected_postcondition": dict(decision["expected_postcondition"]),
                    "skill_result": result,
                    "terminal_skill_failure": True,
                }
                self.state["action_queue"]["verification"] = (
                    "awaiting_forced_failure_observation"
                )
                self.pending_reasons.insert(0, "skill_failure")
                self.wake_event.set()
                return
            self.pending_postcondition = {
                "skill_id": skill_id,
                "before_state": json.loads(json.dumps(base_state)),
                "expected_postcondition": dict(decision["expected_postcondition"]),
                "skill_result": result,
            }
            self.state["action_queue"]["verification"] = "awaiting_forced_observation"
            self.pending_reasons.insert(0, "skill_completion")
            self.wake_event.set()

    def shutdown(self) -> None:
        try:
            self.stop("studio_shutdown")
        except TaskOrchestratorError:
            pass
        self.shutdown_event.set()
        self.wake_event.set()
        if self.worker is not None:
            self.worker.join(timeout=3.0)
