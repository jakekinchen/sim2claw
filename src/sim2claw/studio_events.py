"""Small, file-backed progress records consumed by the browser studio.

The records live under ignored ``runs/`` storage.  They are observability only:
writing one never grants execution, evaluator, gateway, or physical authority.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .paths import REPO_ROOT


DEFAULT_STUDIO_RUN_ROOT = REPO_ROOT / "runs" / "studio" / "processes"


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class StudioActivity:
    """Publish one process heartbeat using atomic JSON replacements."""

    kind: str
    title: str
    task_id: str | None = None
    run_root: Path = DEFAULT_STUDIO_RUN_ROOT
    activity_id: str = field(
        default_factory=lambda: f"{int(time.time())}-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    )
    _payload: dict[str, Any] = field(init=False, repr=False)
    _path: Path = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.run_root.mkdir(parents=True, exist_ok=True)
        self._path = self.run_root / f"{self.activity_id}.json"
        self._payload = {
            "schema_version": "sim2claw.studio_activity.v1",
            "id": self.activity_id,
            "kind": self.kind,
            "title": self.title,
            "task_id": self.task_id,
            "status": "running",
            "phase": "Starting",
            "current": None,
            "total": None,
            "progress": None,
            "pid": os.getpid(),
            "started_at": _now(),
            "updated_at": _now(),
            "ended_at": None,
            "detail": None,
            "metrics": {},
            "episode_id": None,
            "physical_authority": False,
        }
        self._write()

    @property
    def id(self) -> str:
        return self.activity_id

    def update(
        self,
        *,
        phase: str | None = None,
        current: int | float | None = None,
        total: int | float | None = None,
        detail: str | None = None,
        metrics: dict[str, Any] | None = None,
        episode_id: str | None = None,
    ) -> None:
        if phase is not None:
            self._payload["phase"] = phase
        if current is not None:
            self._payload["current"] = current
        if total is not None:
            self._payload["total"] = total
        if current is not None and total not in (None, 0):
            self._payload["progress"] = max(0.0, min(1.0, float(current) / float(total)))
        if detail is not None:
            self._payload["detail"] = detail
        if metrics:
            self._payload["metrics"].update(metrics)
        if episode_id is not None:
            self._payload["episode_id"] = episode_id
        self._payload["updated_at"] = _now()
        self._write()

    def complete(
        self,
        *,
        detail: str | None = None,
        metrics: dict[str, Any] | None = None,
        episode_id: str | None = None,
    ) -> None:
        self.update(detail=detail, metrics=metrics, episode_id=episode_id)
        self._payload.update(
            {
                "status": "completed",
                "phase": "Complete",
                "progress": 1.0,
                "ended_at": _now(),
                "updated_at": _now(),
            }
        )
        self._write()

    def fail(self, error: BaseException | str) -> None:
        self._payload.update(
            {
                "status": "failed",
                "phase": "Stopped",
                "detail": str(error),
                "ended_at": _now(),
                "updated_at": _now(),
            }
        )
        self._write()

    def __enter__(self) -> StudioActivity:
        return self

    def __exit__(self, exc_type: object, exc: BaseException | None, traceback: object) -> bool:
        if exc is not None:
            self.fail(exc)
        elif self._payload["status"] == "running":
            self.complete()
        return False

    def _write(self) -> None:
        temporary = self._path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(self._payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self._path)
