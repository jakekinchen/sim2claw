"""Typed execution, immutable artifact, and lease contracts for the factory."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import tempfile
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Protocol


ARTIFACT_REFERENCE_SCHEMA = "sim2claw.factory_artifact_reference.v1"
ATTEMPT_SCHEMA = "sim2claw.learning_factory_attempt.v1"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@dataclass(frozen=True)
class AdapterDescriptor:
    """Static declaration of one stage adapter's authority and dependencies."""

    stage_id: str
    dependencies: tuple[str, ...]
    output_contract: str
    verdict_owner: str
    component_modules: tuple[str, ...] = ()
    external_tools: tuple[str, ...] = ()
    cleanup_required: bool = False


@dataclass(frozen=True)
class StageOutcome:
    """Only terminal value an adapter may return to the controller."""

    status: str
    summary: str
    output: dict[str, Any] | None
    proof_class: str
    blockers: tuple[str, ...] = ()
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "StageOutcome":
        output = payload.get("output")
        if output is not None and not isinstance(output, dict):
            raise TypeError("stage adapter output must be an object or null")
        blockers = payload.get("blockers", [])
        if not isinstance(blockers, list) or any(
            not isinstance(item, str) for item in blockers
        ):
            raise TypeError("stage adapter blockers must be a list of strings")
        diagnostics = payload.get("diagnostics", {})
        if not isinstance(diagnostics, dict):
            raise TypeError("stage adapter diagnostics must be an object")
        return cls(
            status=str(payload.get("status", "")),
            summary=str(payload.get("summary", "")),
            output=output,
            proof_class=str(payload.get("proof_class", "")),
            blockers=tuple(blockers),
            diagnostics=dict(diagnostics),
        )

    def as_payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "summary": self.summary,
            "output": self.output,
            "proof_class": self.proof_class,
            "blockers": list(self.blockers),
            "diagnostics": dict(self.diagnostics),
        }


class StageAdapter(Protocol):
    """A deterministic stage boundary with a declared evidence owner."""

    descriptor: AdapterDescriptor

    def run(self, attempt_dir: Path) -> StageOutcome: ...


@dataclass(frozen=True)
class FunctionStageAdapter:
    """Typed wrapper used while component-specific adapters stay lightweight."""

    descriptor: AdapterDescriptor
    function: Callable[[Path], dict[str, Any] | StageOutcome]

    def run(self, attempt_dir: Path) -> StageOutcome:
        result = self.function(attempt_dir)
        return result if isinstance(result, StageOutcome) else StageOutcome.from_payload(result)


class ContentAddressedArtifactStore:
    """Write immutable JSON objects at paths derived from their byte digest."""

    def __init__(self, root: Path, *, path_root: Path):
        self.root = root.resolve()
        self.path_root = path_root.resolve()

    def put_json(self, value: dict[str, Any]) -> dict[str, Any]:
        encoded = _canonical_json_bytes(value)
        digest = _sha256_bytes(encoded)
        path = self.root / "sha256" / digest[:2] / f"{digest}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{digest}.", suffix=".tmp", dir=path.parent
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError:
                if path.read_bytes() != encoded:
                    raise RuntimeError(
                        f"content-addressed artifact collision or corruption: {digest}"
                    )
        finally:
            temporary.unlink(missing_ok=True)
        return {
            "schema_version": ARTIFACT_REFERENCE_SCHEMA,
            "algorithm": "sha256",
            "sha256": digest,
            "size_bytes": len(encoded),
            "media_type": "application/json",
            "path": path.relative_to(self.path_root).as_posix(),
            "immutable": True,
        }

    def verify(self, reference: dict[str, Any]) -> Path:
        if reference.get("schema_version") != ARTIFACT_REFERENCE_SCHEMA:
            raise ValueError("unsupported factory artifact reference")
        digest = str(reference.get("sha256", ""))
        if len(digest) != 64 or reference.get("algorithm") != "sha256":
            raise ValueError("factory artifact reference has an invalid digest")
        declared = Path(str(reference.get("path", "")))
        if declared.is_absolute() or ".." in declared.parts:
            raise ValueError("factory artifact reference escapes its path root")
        path = (self.path_root / declared).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("factory artifact reference is outside the artifact store")
        if not path.is_file():
            raise ValueError(f"factory artifact is missing: {declared}")
        encoded = path.read_bytes()
        if _sha256_bytes(encoded) != digest or len(encoded) != int(
            reference.get("size_bytes", -1)
        ):
            raise ValueError("factory artifact bytes do not match their reference")
        return path


class StageLease:
    """Exclusive stage lease with heartbeat and conservative stale recovery."""

    def __init__(
        self,
        path: Path,
        *,
        stage_id: str,
        attempt_id: str,
        timeout_seconds: float = 300.0,
    ):
        if timeout_seconds <= 0:
            raise ValueError("lease timeout must be positive")
        self.path = path
        self.stage_id = stage_id
        self.attempt_id = attempt_id
        self.timeout_seconds = float(timeout_seconds)
        self.hostname = socket.gethostname()
        self.pid = os.getpid()
        self._started_at = _utc_now()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _payload(self) -> dict[str, Any]:
        return {
            "schema_version": "sim2claw.learning_factory_lease.v1",
            "stage_id": self.stage_id,
            "attempt_id": self.attempt_id,
            "hostname": self.hostname,
            "pid": self.pid,
            "started_at": self._started_at,
            "heartbeat_at": _utc_now(),
            "timeout_seconds": self.timeout_seconds,
        }

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    def _observed(self) -> tuple[dict[str, Any] | None, float]:
        try:
            stat = self.path.stat()
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return (value if isinstance(value, dict) else None), stat.st_mtime
        except (OSError, json.JSONDecodeError):
            try:
                return None, self.path.stat().st_mtime
            except OSError:
                return None, 0.0

    def _stale(self, observed: dict[str, Any] | None, mtime: float) -> bool:
        if observed is not None and observed.get("hostname") == self.hostname:
            try:
                return not self._pid_alive(int(observed.get("pid", -1)))
            except (TypeError, ValueError):
                pass
        heartbeat = None if observed is None else observed.get("heartbeat_at")
        try:
            stamp = datetime.fromisoformat(str(heartbeat)).timestamp()
        except (TypeError, ValueError):
            stamp = mtime
        return datetime.now(UTC).timestamp() - stamp > self.timeout_seconds

    def _recover_if_stale(self) -> bool:
        observed, mtime = self._observed()
        if not self._stale(observed, mtime):
            return False
        expected_attempt = None if observed is None else observed.get("attempt_id")
        current, _ = self._observed()
        current_attempt = None if current is None else current.get("attempt_id")
        if current_attempt != expected_attempt:
            return False
        self.path.unlink(missing_ok=True)
        return True

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            payload = json.dumps(self._payload(), sort_keys=True).encode("utf-8")
            try:
                descriptor = os.open(
                    self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
                )
            except FileExistsError:
                if self._recover_if_stale():
                    continue
                raise RuntimeError(
                    f"stage {self.stage_id} already has an active lease at {self.path}"
                )
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            self._thread = threading.Thread(
                target=self._heartbeat_loop,
                name=f"factory-lease-{self.stage_id}",
                daemon=True,
            )
            self._thread.start()
            return
        raise RuntimeError(f"could not safely acquire stage lease: {self.path}")

    def _heartbeat_loop(self) -> None:
        interval = max(0.05, min(5.0, self.timeout_seconds / 3.0))
        while not self._stop.wait(interval):
            observed, _ = self._observed()
            if observed is None or observed.get("attempt_id") != self.attempt_id:
                return
            _atomic_write_json(self.path, self._payload())

    def release(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        observed, _ = self._observed()
        if observed is not None and observed.get("attempt_id") == self.attempt_id:
            self.path.unlink(missing_ok=True)

    def __enter__(self) -> "StageLease":
        self.acquire()
        return self

    def __exit__(self, *_: object) -> None:
        self.release()
