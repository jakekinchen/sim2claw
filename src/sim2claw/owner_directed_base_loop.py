"""Deterministic owner-directed replay of one base/inverse/base pawn cycle.

This runner deliberately does not promote the source recordings into learned
skills or reinterpret an overhead JPEG as a registered task verdict.  It keeps
the existing physical replay guards, releases torque after every move, and
retains an overhead checkpoint and aggregate receipt for the attempt.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .physical_trace_replay import (
    PhysicalTraceReplayError,
    load_physical_trace_source,
    run_physical_trace_replay,
)
from .teleop_recording import physical_gateway_preflight


OWNER_DIRECTED_LOOP_SCHEMA = "sim2claw.owner_directed_base_loop_attempt.v1"
DEFAULT_DURATION_SECONDS = 300.0


@dataclass(frozen=True)
class LoopMove:
    phase: str
    source_square: str
    destination_square: str
    recording_directory_name: str
    reverse: bool = False

    @property
    def move_id(self) -> str:
        return f"{self.source_square}_to_{self.destination_square}"


LOOP_MOVES = (
    LoopMove("base_to_inverse", "b1", "b2", "b1-to-b2__20260719T030059Z-a26f8400"),
    # The separately captured C forward trace produced no visible square
    # change.  Reverse the visually demonstrated C inverse trace instead.
    LoopMove(
        "base_to_inverse",
        "c2",
        "c1",
        "c1-to-c2__20260719T032400Z-052d5137",
        True,
    ),
    LoopMove("base_to_inverse", "d1", "d2", "d1-to-d2__20260719T031518Z-34bff0dd"),
    # Likewise, the demonstrated E motion is the inverse trace; reverse its
    # exact samples for the base-to-inverse direction.
    LoopMove(
        "base_to_inverse",
        "e2",
        "e1",
        "e1-to-e2__20260719T032531Z-06be393c",
        True,
    ),
    LoopMove("base_to_inverse", "f1", "f2", "f1-to-f2__20260719T031715Z-61ebb199"),
    LoopMove("base_to_inverse", "g2", "g1", "g2-to-g1__20260719T031813Z-b147b429"),
    LoopMove("inverse_to_base", "b2", "b1", "b1-to-b2__20260719T030059Z-a26f8400", True),
    LoopMove("inverse_to_base", "c1", "c2", "c1-to-c2__20260719T032400Z-052d5137"),
    LoopMove("inverse_to_base", "d2", "d1", "d1-to-d2__20260719T031518Z-34bff0dd", True),
    LoopMove("inverse_to_base", "e1", "e2", "e1-to-e2__20260719T032531Z-06be393c"),
    LoopMove("inverse_to_base", "f2", "f1", "f1-to-f2__20260719T031715Z-61ebb199", True),
    LoopMove("inverse_to_base", "g1", "g2", "g2-to-g1__20260719T031813Z-b147b429", True),
)


class OwnerDirectedLoopError(RuntimeError):
    """The deterministic loop was rejected or stopped fail-closed."""

    def __init__(self, message: str, *, attempt_directory: Path | None = None):
        super().__init__(message)
        self.attempt_directory = attempt_directory


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def build_loop_plan(
    repo_root: Path,
    *,
    duration_seconds: float = DEFAULT_DURATION_SECONDS,
    moves: Sequence[LoopMove] = LOOP_MOVES,
) -> dict[str, Any]:
    """Hash-validate all fixed sources before any physical gateway is opened."""

    if duration_seconds <= 0:
        raise OwnerDirectedLoopError("Loop duration must be positive.")
    repo_root = repo_root.resolve()
    source_root = (repo_root / "datasets" / "manipulation_source_recordings").resolve()
    plan_rows: list[dict[str, Any]] = []
    recorded_duration = 0.0
    if not moves:
        raise OwnerDirectedLoopError("The fixed move sequence is empty.")
    for index, move in enumerate(moves, start=1):
        recording = source_root / move.recording_directory_name
        try:
            source = load_physical_trace_source(recording, allowed_root=source_root)
        except PhysicalTraceReplayError as error:
            raise OwnerDirectedLoopError(
                f"Loop source {move.move_id} was rejected: {error}"
            ) from error
        source_duration = float(source.elapsed_seconds[-1])
        recorded_duration += source_duration
        plan_rows.append(
            {
                "sequence": index,
                "phase": move.phase,
                "move_id": move.move_id,
                "source_square": move.source_square,
                "destination_square": move.destination_square,
                "recording_directory": str(recording),
                "recording_id": str(source.receipt["recording_id"]),
                "reverse": move.reverse,
                "source_sample_count": len(source.rows),
                "recorded_duration_seconds": round(source_duration, 6),
                "source_samples_sha256": str(source.receipt["samples_sha256"]),
            }
        )
    if recorded_duration > duration_seconds:
        raise OwnerDirectedLoopError(
            "The fixed cycle's recorded motion exceeds the requested duration: "
            f"{recorded_duration:.1f}s > {duration_seconds:.1f}s."
        )
    return {
        "schema_version": "sim2claw.owner_directed_base_loop_plan.v1",
        "mapping_authority": "owner_directed_recording_folder_labels",
        "proof_class": "unqualified_physical_command_replay",
        "duration_horizon_seconds": float(duration_seconds),
        "recorded_motion_seconds": round(recorded_duration, 6),
        "move_count": len(plan_rows),
        "moves": plan_rows,
        "physical_task_success_verified": False,
    }


class StudioCheckpointClient:
    """Capture receipt-only overhead checkpoints through loopback Studio."""

    def __init__(self, base_url: str = "http://127.0.0.1:4173") -> None:
        self.base_url = base_url.rstrip("/")

    def _json(self, path: str, *, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        data = None
        method = "GET"
        headers: dict[str, str] = {}
        if payload is not None:
            data = json.dumps(dict(payload)).encode("utf-8")
            method = "POST"
            headers["Content-Type"] = "application/json"
        request = Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=15) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
            raise OwnerDirectedLoopError(f"Studio checkpoint request failed: {error}") from error
        if not isinstance(result, dict) or result.get("ok") is False:
            raise OwnerDirectedLoopError(
                f"Studio checkpoint was rejected: {result.get('error') if isinstance(result, dict) else result}"
            )
        return result

    def capture(self, destination: Path) -> dict[str, Any]:
        state = self._json("/api/orchestrator")
        endpoint = (
            "/api/orchestrator/preview"
            if state.get("state") == "STOPPED"
            else "/api/orchestrator/refresh"
        )
        refreshed = self._json(endpoint, payload={})
        orchestrator = refreshed.get("orchestrator") or refreshed
        source = orchestrator.get("source") or {}
        digest = source.get("latest_accepted_sha256") or source.get("latest_preview_sha256")
        if not digest:
            raise OwnerDirectedLoopError("Studio did not return an overhead frame hash.")
        request = Request(
            f"{self.base_url}/api/orchestrator/frame?sha={digest}",
            method="GET",
        )
        try:
            with urlopen(request, timeout=15) as response:
                body = response.read()
                content_type = str(response.headers.get("Content-Type") or "")
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            raise OwnerDirectedLoopError(f"Studio frame download failed: {error}") from error
        if not body or not content_type.startswith("image/"):
            raise OwnerDirectedLoopError("Studio checkpoint was not an image.")
        if _sha256_bytes(body) != digest:
            raise OwnerDirectedLoopError("Studio checkpoint hash did not match its source receipt.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(body)
        return {
            "frame_sha256": digest,
            "relative_path": str(destination.name),
            "camera_id": source.get("camera_id"),
            "registration_state": source.get("registration_state"),
            "captured_at": source.get("latest_captured_at"),
            "task_success_verified": False,
        }


ReplayRunner = Callable[..., dict[str, Any]]
PreflightRunner = Callable[[], dict[str, Any]]
CheckpointRunner = Callable[[Path], dict[str, Any]]
ProgressCallback = Callable[[dict[str, Any]], None]


def run_owner_directed_base_loop(
    repo_root: Path,
    *,
    operator_acknowledged: bool,
    owner_directed_unqualified_labels: bool,
    duration_seconds: float = DEFAULT_DURATION_SECONDS,
    output_root: Path | None = None,
    checkpoint: CheckpointRunner | None = None,
    replay_runner: ReplayRunner = run_physical_trace_replay,
    preflight_runner: PreflightRunner = physical_gateway_preflight,
    clock: Callable[[], float] = time.monotonic,
    should_stop: Callable[[], bool] = lambda: False,
    progress: ProgressCallback | None = None,
    moves: Sequence[LoopMove] = LOOP_MOVES,
    checkpoint_mode: str = "all",
) -> dict[str, Any]:
    """Run exactly one deterministic 12-move cycle within a duration horizon."""

    if not operator_acknowledged:
        raise OwnerDirectedLoopError(
            "The powered workcell must be explicitly acknowledged clear with --yes."
        )
    if not owner_directed_unqualified_labels:
        raise OwnerDirectedLoopError(
            "Owner-directed unqualified folder labels require the explicit mapping flag."
        )
    if checkpoint_mode not in {"all", "final_only", "none"}:
        raise OwnerDirectedLoopError("Unknown overhead checkpoint mode.")
    repo_root = repo_root.resolve()
    plan = build_loop_plan(
        repo_root,
        duration_seconds=duration_seconds,
        moves=moves,
    )
    destination_root = (
        output_root or repo_root / "runs" / "task_orchestrator" / "owner_directed_base_loop"
    ).resolve()
    attempt_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    attempt_directory = destination_root / attempt_id
    attempt_directory.mkdir(parents=True, exist_ok=False)
    frames_directory = attempt_directory / "frames"
    receipt_path = attempt_directory / "attempt_receipt.json"
    checkpoint_runner = checkpoint or StudioCheckpointClient().capture
    started_at = datetime.now(UTC).isoformat()
    started = clock()
    receipt: dict[str, Any] = {
        "schema_version": OWNER_DIRECTED_LOOP_SCHEMA,
        "attempt_id": attempt_id,
        "started_at": started_at,
        "completed_at": None,
        "status": "starting",
        "mapping_authority": plan["mapping_authority"],
        "proof_class": (
            "unqualified_physical_command_replay_with_unregistered_overhead_checkpoints"
        ),
        "duration_horizon_seconds": plan["duration_horizon_seconds"],
        "recorded_motion_seconds": plan["recorded_motion_seconds"],
        "plan": plan["moves"],
        "preflight": None,
        "checkpoints": [],
        "replays": [],
        "failure": None,
        "physical_task_success_verified": False,
        "torque_enabled_after": None,
    }

    def emit(event: str, **values: Any) -> None:
        if progress is not None:
            progress({"event": event, **values})

    def save() -> None:
        _atomic_json(receipt_path, receipt)

    save()
    try:
        preflight = preflight_runner()
        receipt["preflight"] = preflight
        if not preflight.get("passed"):
            raise OwnerDirectedLoopError("Physical gateway preflight did not pass.")
        if preflight.get("physical_follower_torque_enabled"):
            raise OwnerDirectedLoopError("Preflight did not leave follower torque off.")
        if checkpoint_mode == "all":
            initial = checkpoint_runner(frames_directory / "000-preflight.jpg")
            receipt["checkpoints"].append(
                {"sequence": 0, "phase": "preflight", **initial}
            )
        receipt["status"] = "running"
        save()
        source_root = (repo_root / "datasets" / "manipulation_source_recordings").resolve()
        for move in plan["moves"]:
            if should_stop():
                raise OwnerDirectedLoopError(
                    "Demo loop stop requested; stopped between guarded moves."
                )
            elapsed = clock() - started
            if elapsed >= duration_seconds:
                raise OwnerDirectedLoopError(
                    "Five-minute horizon elapsed before the full cycle completed."
                )
            emit(
                "move_started",
                sequence=move["sequence"],
                move_id=move["move_id"],
                phase=move["phase"],
            )
            replay = replay_runner(
                Path(move["recording_directory"]),
                operator_acknowledged=True,
                reverse=bool(move["reverse"]),
                allowed_source_root=source_root,
                progress=lambda row, current=move: emit(
                    "replay_progress",
                    sequence=current["sequence"],
                    move_id=current["move_id"],
                    replay=row,
                ),
            )
            replay_summary = {
                "sequence": move["sequence"],
                "phase": move["phase"],
                "move_id": move["move_id"],
                "run_id": replay.get("run_id"),
                "run_directory": replay.get("run_directory"),
                "status": replay.get("status"),
                "completed_sample_count": replay.get("completed_sample_count"),
                "source_sample_count": replay.get("source_sample_count"),
                "safety_clamped_sample_count": replay.get("safety_clamped_sample_count"),
                "torque_enabled_after": replay.get("physical_follower_torque_enabled"),
                "task_success_verified": False,
            }
            receipt["replays"].append(replay_summary)
            if replay.get("status") != "completed":
                raise OwnerDirectedLoopError(
                    f"Replay {move['move_id']} did not complete."
                )
            if replay.get("physical_follower_torque_enabled"):
                raise OwnerDirectedLoopError(
                    f"Replay {move['move_id']} did not release follower torque."
                )
            capture_after_move = checkpoint_mode == "all" or (
                checkpoint_mode == "final_only"
                and int(move["sequence"]) == len(plan["moves"])
            )
            if capture_after_move:
                checkpoint_row = checkpoint_runner(
                    frames_directory
                    / f"{int(move['sequence']):03d}-{move['move_id']}.jpg"
                )
                receipt["checkpoints"].append(
                    {
                        "sequence": move["sequence"],
                        "phase": move["phase"],
                        "move_id": move["move_id"],
                        **checkpoint_row,
                    }
                )
            save()
            emit("move_completed", sequence=move["sequence"], move_id=move["move_id"])
        receipt["status"] = "completed_command_cycle_unverified_task_outcome"
    except Exception as error:
        receipt["status"] = "failed"
        receipt["failure"] = {"type": type(error).__name__, "message": str(error)}
        raise OwnerDirectedLoopError(str(error), attempt_directory=attempt_directory) from error
    finally:
        try:
            final_preflight = preflight_runner()
            receipt["final_preflight"] = final_preflight
            receipt["torque_enabled_after"] = bool(
                final_preflight.get("physical_follower_torque_enabled")
            )
        except Exception as error:
            receipt["final_preflight"] = {
                "passed": False,
                "error": f"{type(error).__name__}: {error}",
            }
            receipt["torque_enabled_after"] = None
            if receipt["failure"] is None:
                receipt["status"] = "failed"
                receipt["failure"] = {
                    "type": type(error).__name__,
                    "message": f"Final torque-off preflight failed: {error}",
                }
        receipt["completed_at"] = datetime.now(UTC).isoformat()
        receipt["wall_duration_seconds"] = round(clock() - started, 6)
        save()
    if receipt["torque_enabled_after"] is not False:
        raise OwnerDirectedLoopError(
            "Final torque-off state was not verified.", attempt_directory=attempt_directory
        )
    emit("loop_completed", attempt_directory=str(attempt_directory))
    return {**receipt, "attempt_directory": str(attempt_directory)}
