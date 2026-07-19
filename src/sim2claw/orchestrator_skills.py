"""Fail-closed promoted-skill registry and one-at-a-time dispatch boundary."""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol


SKILL_RESULT_SCHEMA = "sim2claw.orchestrator_skill_result.v1"
DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class SkillRegistryError(RuntimeError):
    """A model proposal cannot cross the promoted-skill boundary."""


class SkillAdapter(Protocol):
    def execute(
        self,
        request: Mapping[str, Any],
        stop_event: threading.Event,
    ) -> Mapping[str, Any]: ...

    def safe_stop(self) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class SkillEntry:
    payload: dict[str, Any]

    @property
    def skill_id(self) -> str:
        return str(self.payload["skill_id"])

    @property
    def callable(self) -> bool:
        return bool(self.payload.get("callable"))

    @property
    def execution_modes(self) -> tuple[str, ...]:
        return tuple(str(value) for value in self.payload.get("execution_modes", []))


class SkillRegistry:
    def __init__(self, payload: Mapping[str, Any]) -> None:
        self.payload = json.loads(json.dumps(payload))
        if self.payload.get("schema_version") != "sim2claw.orchestrator_skill_registry.v1":
            raise ValueError("unexpected orchestrator skill-registry schema")
        defaults = dict(self.payload["unavailable_defaults"])
        common = dict(self.payload["execution_contract"])
        self.entries: dict[str, SkillEntry] = {}
        for raw in self.payload["skills"]:
            merged = {**common, **defaults, **dict(raw)}
            merged["artifact_verification_required"] = bool(
                self.payload.get("artifact_verification_required", False)
            )
            identifier = str(merged["skill_id"])
            if identifier in self.entries:
                raise ValueError(f"duplicate orchestrator skill: {identifier}")
            self.entries[identifier] = SkillEntry(merged)
        expected = {
            f"pawn_{file_name}{source}_to_{file_name}{destination}"
            for file_name in "bcdefg"
            for source, destination in ((1, 2), (2, 1))
        }
        if set(self.entries) != expected:
            raise ValueError("orchestrator skill registry is not the frozen 12-move B--G set")
        for forbidden in self.payload.get("forbidden_substitutions", []):
            if forbidden in self.entries:
                raise ValueError("forbidden policy substitution entered the registry")

    @classmethod
    def load(cls, path: Path) -> "SkillRegistry":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("artifact_verification_required") is True:
            base = path.resolve().parent
            for skill in payload.get("skills", []):
                verified = True
                for path_field, digest_field in (
                    ("checkpoint_path", "checkpoint_sha256"),
                    ("evaluator_receipt_path", "evaluator_receipt_sha256"),
                    ("promotion_receipt_path", "promotion_receipt_sha256"),
                ):
                    candidate = (base / str(skill.get(path_field) or "")).resolve()
                    expected = str(skill.get(digest_field) or "")
                    if not candidate.is_relative_to(base) or not candidate.is_file():
                        verified = False
                        break
                    digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
                    if digest != expected:
                        verified = False
                        break
                skill["artifacts_verified"] = verified
        return cls(payload)

    def entry(self, skill_id: str) -> SkillEntry:
        try:
            return self.entries[skill_id]
        except KeyError as error:
            raise SkillRegistryError(f"Skill is not allowlisted: {skill_id}") from error

    @staticmethod
    def _promotion_ready(entry: SkillEntry) -> bool:
        payload = entry.payload
        return (
            entry.callable
            and bool(entry.execution_modes)
            and payload.get("architecture") == "ACT"
            and all(
                isinstance(payload.get(field), str)
                and DIGEST_PATTERN.fullmatch(str(payload[field])) is not None
                for field in (
                    "checkpoint_sha256",
                    "evaluator_receipt_sha256",
                    "promotion_receipt_sha256",
                )
            )
            and (
                payload.get("artifacts_verified") is True
                if payload.get("artifact_verification_required") is True
                else True
            )
        )

    def validate_counterexample_return(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Authenticate a runtime failure before routing it back to LF-12."""

        if payload.get("schema_version") != "sim2claw.runtime_counterexample_return.v1":
            raise SkillRegistryError("Unsupported runtime counterexample schema.")
        skill_id = str(payload.get("skill_id") or "")
        entry = self.entry(skill_id)
        for field in (
            "checkpoint_sha256",
            "evaluator_receipt_sha256",
            "promotion_receipt_sha256",
        ):
            if payload.get(field) != entry.payload.get(field):
                raise SkillRegistryError(f"Runtime counterexample {field} mismatch.")
        for field in ("action_trace_sha256", "initial_state_sha256", "terminal_state_sha256"):
            if DIGEST_PATTERN.fullmatch(str(payload.get(field) or "")) is None:
                raise SkillRegistryError(f"Runtime counterexample lacks {field}.")
        failure_code = str(payload.get("failure_code") or "")
        if not failure_code:
            raise SkillRegistryError("Runtime counterexample lacks a failure code.")
        return {
            **dict(payload),
            "training_rows_authorized": 0,
            "route": "LF-12",
            "physical_authority": False,
        }

    def readiness(self, skill_id: str, mode: str) -> dict[str, Any]:
        entry = self.entry(skill_id)
        promotion_ready = self._promotion_ready(entry)
        mode_ready = mode in entry.execution_modes
        ready = promotion_ready and mode_ready
        return {
            "skill_id": skill_id,
            "ready": ready,
            "promotion_ready": promotion_ready,
            "mode_ready": mode_ready,
            "readiness": entry.payload.get("readiness"),
            "execution_modes": list(entry.execution_modes),
            "physical_authority": False,
        }

    def public_rows(self, last_results: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
        results = last_results or {}
        rows: list[dict[str, Any]] = []
        for identifier in sorted(self.entries):
            entry = self.entries[identifier]
            rows.append(
                {
                    "skill_id": identifier,
                    "version": entry.payload["version"],
                    "architecture": entry.payload["architecture"],
                    "source_square": entry.payload["source_square"],
                    "destination_square": entry.payload["destination_square"],
                    "observation_schema": entry.payload["observation_schema"],
                    "action_schema": entry.payload["action_schema"],
                    "supported_scene_id": entry.payload["supported_scene_id"],
                    "supported_workcell_id": entry.payload["supported_workcell_id"],
                    "supported_calibration_id": entry.payload[
                        "supported_calibration_id"
                    ],
                    "preconditions": list(entry.payload["preconditions"]),
                    "postconditions": list(entry.payload["postconditions"]),
                    "timeout_seconds": entry.payload["timeout_seconds"],
                    "safe_stop": entry.payload["safe_stop"],
                    "known_failure_regions": list(
                        entry.payload["known_failure_regions"]
                    ),
                    "recovery_restriction": entry.payload["recovery_restriction"],
                    "checkpoint_sha256": entry.payload.get("checkpoint_sha256"),
                    "evaluator_receipt_sha256": entry.payload.get(
                        "evaluator_receipt_sha256"
                    ),
                    "promotion_receipt_sha256": entry.payload.get(
                        "promotion_receipt_sha256"
                    ),
                    "execution_modes": list(entry.execution_modes),
                    "readiness": entry.payload.get("readiness"),
                    "callable": entry.callable and self._promotion_ready(entry),
                    "last_result": results.get(identifier),
                    "physical_authority": False,
                }
            )
        return rows

    def capability_summary(self) -> dict[str, Any]:
        callable_rows = [entry for entry in self.entries.values() if self._promotion_ready(entry)]
        return {
            "registered": len(self.entries),
            "callable": len(callable_rows),
            "simulation_ready": any("simulation" in entry.execution_modes for entry in callable_rows),
            "physical_shadow_ready": any(
                "physical_shadow" in entry.execution_modes for entry in callable_rows
            ),
            "physical_gated_ready": False,
            "absence_reason": (
                None
                if callable_rows
                else "No separately evaluated B--G ACT checkpoint is promoted."
            ),
            "physical_authority": False,
        }


class OneAtATimeSkillDispatcher:
    """Dispatch at most one already-promoted adapter and expose safe-stop state."""

    def __init__(
        self,
        registry: SkillRegistry,
        adapters: Mapping[str, SkillAdapter] | None = None,
        *,
        monotonic=time.monotonic,
        safe_stop_grace_seconds: float = 1.0,
    ) -> None:
        self.registry = registry
        self.adapters = dict(adapters or {})
        self.monotonic = monotonic
        self.safe_stop_grace_seconds = float(safe_stop_grace_seconds)
        if self.safe_stop_grace_seconds < 0:
            raise ValueError("safe-stop grace period cannot be negative")
        self.lock = threading.RLock()
        self.active_skill_id: str | None = None
        self.active_adapter: SkillAdapter | None = None
        self.active_stop_event: threading.Event | None = None
        self.terminal_fault_latched: str | None = None

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "active_skill_id": self.active_skill_id,
                "busy": self.active_skill_id is not None,
                "terminal_fault_latched": self.terminal_fault_latched,
                "physical_authority": False,
            }

    def safe_stop(self) -> dict[str, Any]:
        with self.lock:
            adapter = self.active_adapter
            stop_event = self.active_stop_event
            skill_id = self.active_skill_id
            if stop_event is not None:
                stop_event.set()
        result: Mapping[str, Any] = {"requested": adapter is not None}
        if adapter is not None:
            try:
                result = adapter.safe_stop()
            except Exception as error:  # fail closed and retain the exact stop failure
                result = {"requested": True, "error": f"{type(error).__name__}: {error}"}
                with self.lock:
                    self.terminal_fault_latched = (
                        f"safe_stop_failed:{type(error).__name__}"
                    )
        return {
            "skill_id": skill_id,
            "safe_stop": dict(result),
            "torque_off": None,
            "physical_authority": False,
        }

    def dispatch(
        self,
        skill_id: str,
        arguments: Mapping[str, Any],
        *,
        mode: str,
        latest_state: Mapping[str, Any],
    ) -> dict[str, Any]:
        entry = self.registry.entry(skill_id)
        readiness = self.registry.readiness(skill_id, mode)
        if not readiness["ready"]:
            raise SkillRegistryError(
                f"Skill is unavailable in {mode}: {readiness['readiness']}"
            )
        if mode != "simulation":
            raise SkillRegistryError("Only separately promoted simulation adapters are enabled.")
        expected_arguments = {
            "source_square": entry.payload["source_square"],
            "destination_square": entry.payload["destination_square"],
        }
        if dict(arguments) != expected_arguments:
            raise SkillRegistryError("Skill arguments do not match the immutable registry schema.")
        source = expected_arguments["source_square"]
        destination = expected_arguments["destination_square"]
        if source not in latest_state.get("observed_occupied", []) or destination not in latest_state.get(
            "observed_empty", []
        ):
            raise SkillRegistryError("Latest square-level state does not satisfy skill preconditions.")
        adapter = self.adapters.get(skill_id)
        if adapter is None:
            raise SkillRegistryError("Promoted registry entry has no bound runtime adapter.")
        with self.lock:
            if self.terminal_fault_latched is not None:
                raise SkillRegistryError(
                    "Dispatcher has a latched terminal fault and cannot start another skill."
                )
            if self.active_skill_id is not None:
                raise SkillRegistryError("A skill is already active.")
            self.active_skill_id = skill_id
            self.active_adapter = adapter
            self.active_stop_event = threading.Event()
            stop_event = self.active_stop_event
        started = self.monotonic()
        timeout = float(entry.payload["timeout_seconds"])
        executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix=f"orchestrator-{skill_id}",
        )
        future = executor.submit(adapter.execute, dict(arguments), stop_event)
        status = "completed"
        adapter_result: dict[str, Any]
        safe_stop_result: dict[str, Any] | None = None
        try:
            adapter_result = dict(future.result(timeout=timeout))
        except concurrent.futures.TimeoutError:
            status = "timeout"
            stop_event.set()
            try:
                safe_stop_result = dict(adapter.safe_stop())
            except Exception as stop_error:
                safe_stop_result = {
                    "error": f"{type(stop_error).__name__}: {stop_error}"
                }
                with self.lock:
                    self.terminal_fault_latched = (
                        f"timeout_safe_stop_failed:{type(stop_error).__name__}"
                    )
            try:
                future.result(timeout=self.safe_stop_grace_seconds)
            except concurrent.futures.TimeoutError:
                with self.lock:
                    self.terminal_fault_latched = "timeout_adapter_not_terminal"
            except Exception:
                # The adapter reached a terminal exception after cancellation.
                pass
            adapter_result = {"error": "skill timeout", "timeout_seconds": timeout}
        except Exception as error:
            status = "failed"
            stop_event.set()
            try:
                safe_stop_result = dict(adapter.safe_stop())
            except Exception as stop_error:
                safe_stop_result = {
                    "error": f"{type(stop_error).__name__}: {stop_error}"
                }
            adapter_result = {"error": f"{type(error).__name__}: {error}"}
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
            with self.lock:
                self.active_skill_id = None
                self.active_adapter = None
                self.active_stop_event = None
        return {
            "schema_version": SKILL_RESULT_SCHEMA,
            "skill_id": skill_id,
            "mode": mode,
            "status": status,
            "duration_seconds": round(self.monotonic() - started, 6),
            "checkpoint_sha256": entry.payload["checkpoint_sha256"],
            "evaluator_receipt_sha256": entry.payload["evaluator_receipt_sha256"],
            "promotion_receipt_sha256": entry.payload["promotion_receipt_sha256"],
            "arguments": dict(arguments),
            "adapter_result": adapter_result,
            "safe_stop": safe_stop_result,
            "physical_authority": False,
            "torque_off": None,
        }
