"""Loopback-only controller for the fixed owner-directed demo cycle."""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from .owner_directed_base_loop import (
    DEFAULT_DURATION_SECONDS,
    LOOP_MOVES,
    OwnerDirectedLoopError,
    build_loop_plan,
    run_owner_directed_base_loop,
)


CameraCapture = Callable[[str], Mapping[str, Any]]

DEMO_ACTION_MOVES = {
    "loop": LOOP_MOVES,
    "base_to_inverse": LOOP_MOVES[:6],
    "inverse_to_base": LOOP_MOVES[6:],
    **{f"pawn_{move.move_id}": (move,) for move in LOOP_MOVES},
}

DEMO_ACTION_RESULT_PATTERNS = {
    "loop": "010101",
    "base_to_inverse": "101010",
    "inverse_to_base": "010101",
}


class DemoLoopController:
    """Run one fixed physical demo in a background thread with bounded authority."""

    def __init__(
        self,
        repo_root: Path,
        *,
        camera_capture: CameraCapture,
        camera_id: str = "logitech-overhead",
    ) -> None:
        self.repo_root = repo_root.resolve()
        self.camera_capture = camera_capture
        self.camera_id = camera_id
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.state: dict[str, Any] = {
            "schema_version": "sim2claw.demo_loop_controller.v1",
            "enabled": True,
            "status": "ready",
            "action": None,
            "current_move": None,
            "completed_moves": 0,
            "total_moves": 12,
            "latest_event": None,
            "attempt_directory": None,
            "error": None,
            "started_at": None,
            "completed_at": None,
            "authority_scope": "fixed_owner_directed_base_inverse_base_script_only",
            "physical_authority": True,
            "task_success_verified": False,
        }

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return json.loads(json.dumps(self.state))

    def _checkpoint(self, destination: Path) -> dict[str, Any]:
        captured = dict(self.camera_capture(self.camera_id))
        body = captured.get("body")
        if not isinstance(body, bytes) or not body:
            raise OwnerDirectedLoopError("Demo overhead checkpoint was empty.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(body)
        return {
            "frame_sha256": hashlib.sha256(body).hexdigest(),
            "relative_path": str(destination.relative_to(destination.parents[1])),
            "camera_id": captured.get("camera_id") or self.camera_id,
            "registration_state": "demo_visual_feedback",
            "captured_at": captured.get("captured_at"),
            "task_success_verified": False,
        }

    def _progress(self, row: dict[str, Any]) -> None:
        with self.lock:
            self.state["latest_event"] = row
            if row.get("event") in {"move_started", "move_completed"}:
                self.state["current_move"] = row.get("move_id")
            if row.get("event") == "move_completed":
                self.state["completed_moves"] = int(row.get("sequence") or 0)

    def _run(self, action: str) -> None:
        try:
            report = run_owner_directed_base_loop(
                self.repo_root,
                operator_acknowledged=True,
                owner_directed_unqualified_labels=True,
                duration_seconds=DEFAULT_DURATION_SECONDS,
                checkpoint=self._checkpoint,
                should_stop=self.stop_event.is_set,
                progress=self._progress,
                moves=DEMO_ACTION_MOVES[action],
                # The C922 and follower controller share the local USB tree.
                # Keep the camera closed while motors are armed, then capture
                # one final torque-off proof frame after the sequence.
                checkpoint_mode="final_only",
            )
        except OwnerDirectedLoopError as error:
            with self.lock:
                self.state.update(
                    {
                        "status": "stopped" if self.stop_event.is_set() else "failed",
                        "attempt_directory": (
                            str(error.attempt_directory)
                            if error.attempt_directory is not None
                            else None
                        ),
                        "error": str(error),
                        "completed_at": datetime.now(UTC).isoformat(),
                        "current_move": None,
                        "physical_authority": True,
                    }
                )
            return
        except Exception as error:
            with self.lock:
                self.state.update(
                    {
                        "status": "failed",
                        "error": f"{type(error).__name__}: {error}",
                        "completed_at": datetime.now(UTC).isoformat(),
                        "current_move": None,
                        "physical_authority": True,
                    }
                )
            return
        with self.lock:
            self.state.update(
                {
                    "status": "completed",
                    "completed_moves": len(DEMO_ACTION_MOVES[action]),
                    "attempt_directory": report.get("attempt_directory"),
                    "error": None,
                    "completed_at": datetime.now(UTC).isoformat(),
                    "current_move": None,
                    "physical_authority": True,
                    "task_success_verified": False,
                }
            )

    def start_action(self, action: str) -> dict[str, Any]:
        if action not in DEMO_ACTION_MOVES:
            raise OwnerDirectedLoopError(f"Unknown fixed demo action: {action}")
        # Validate the fixed assets before reporting the demo lane as started.
        build_loop_plan(
            self.repo_root,
            duration_seconds=DEFAULT_DURATION_SECONDS,
            moves=DEMO_ACTION_MOVES[action],
        )
        with self.lock:
            if self.thread is not None and self.thread.is_alive():
                raise OwnerDirectedLoopError("A fixed demo sequence is already running.")
            self.stop_event.clear()
            self.state.update(
                {
                    "status": "running",
                    "action": action,
                    "current_move": None,
                    "completed_moves": 0,
                    "total_moves": len(DEMO_ACTION_MOVES[action]),
                    "latest_event": {"event": "loop_requested"},
                    "attempt_directory": None,
                    "error": None,
                    "started_at": datetime.now(UTC).isoformat(),
                    "completed_at": None,
                    "physical_authority": True,
                    "task_success_verified": False,
                }
            )
            self.thread = threading.Thread(
                target=self._run,
                args=(action,),
                name="sim2claw-demo-base-loop",
                daemon=True,
            )
            self.thread.start()
            return self.snapshot()

    def start(self) -> dict[str, Any]:
        return self.start_action("loop")

    def request_stop(self) -> dict[str, Any]:
        with self.lock:
            if self.thread is not None and self.thread.is_alive():
                self.stop_event.set()
                self.state["status"] = "stopping"
                self.state["latest_event"] = {
                    "event": "stop_requested",
                    "behavior": "finish_current_guarded_move_then_release_torque",
                }
            return self.snapshot()

    def shutdown(self) -> None:
        self.request_stop()
        thread = self.thread
        if thread is not None:
            thread.join(timeout=5.0)
