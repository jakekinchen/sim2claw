"""Setup-only camera reposition anchored after torque-on settling.

Unlike action-frozen evidence paths, this executor does not know its action
bytes until the follower is torque-on and stable.  The resulting trajectory is
therefore eligible only for physical camera setup, never sim-gap evaluation.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from pathlib import Path
from typing import Any, Callable, Mapping

import numpy as np

from .physical_canary import (
    _default_gateway,
    _default_preflight,
    _gateway_identity,
)
from .overhead_video import WristVideoRecorder
from .physical_gateway import (
    BODY_REGISTRATION_OFFSET_LIMIT_DEG,
    BODY_TRACKING_ERROR_LIMIT_DEG,
    SETUP_OBSERVED_POSE_ELBOW_TRACKING_ERROR_LIMIT_DEG,
    SETUP_ONLY_ELBOW_TRACKING_ERROR_LIMIT_DEG,
)
from .replay_eligibility import action_sha256
from .wrist_view_reposition import (
    FINAL_TOLERANCE_DEGREES,
    MAX_STAGE_EXCURSION_DEGREES,
    MAX_SLEW_DEGREES_S,
    SAMPLE_HZ,
    WRIST_VIEW_ROUTE_SCHEMA,
    preview_wrist_view_actions,
)


RECEIPT_SCHEMA = "sim2claw.live_anchored_camera_reposition.v1"
MAX_SETUP_TARGET_HOLD_SECONDS = 2.0
MAX_STATIONARY_CAPTURE_SECONDS = 4.0


class LiveAnchoredCameraRepositionError(RuntimeError):
    """A live-anchored setup action failed closed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise LiveAnchoredCameraRepositionError(message)


def _read_json(path: Path, label: str) -> dict[str, Any]:
    def reject_duplicate_keys(
        pairs: list[tuple[str, Any]],
    ) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise LiveAnchoredCameraRepositionError(
                    f"{label} contains duplicate key: {key}"
                )
            value[key] = item
        return value

    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicate_keys,
        )
    except (OSError, json.JSONDecodeError) as error:
        raise LiveAnchoredCameraRepositionError(
            f"could not load {label}: {error}"
        ) from error
    _require(isinstance(value, dict), f"{label} must be an object")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_target(
    route_path: Path,
) -> tuple[
    dict[str, Any],
    np.ndarray,
    float,
    float,
    float,
    float,
    float | None,
]:
    route = _read_json(route_path, "camera-reposition route")
    _require(
        route.get("schema_version") == WRIST_VIEW_ROUTE_SCHEMA
        and isinstance(route.get("route_id"), str)
        and bool(route["route_id"]),
        "camera-reposition route identity changed",
    )
    targets = np.asarray(route.get("stage_targets_degrees"), dtype=np.float64)
    _require(
        targets.shape == (1, 6) and np.all(np.isfinite(targets)),
        "live-anchored setup requires exactly one finite six-joint target",
    )
    configured_slew = route.get(
        "setup_maximum_slew_degrees_s",
        MAX_SLEW_DEGREES_S,
    )
    _require(
        not isinstance(configured_slew, bool)
        and isinstance(configured_slew, (int, float))
        and math.isfinite(float(configured_slew))
        and 0.0 < float(configured_slew) <= MAX_SLEW_DEGREES_S,
        "setup route slew must be positive and no greater than 10 degrees/s",
    )
    setup_elbow_limit = route.get(
        "setup_elbow_tracking_error_limit_degrees",
        BODY_TRACKING_ERROR_LIMIT_DEG,
    )
    _require(
        not isinstance(setup_elbow_limit, bool)
        and isinstance(setup_elbow_limit, (int, float))
        and float(setup_elbow_limit)
        in {
            BODY_TRACKING_ERROR_LIMIT_DEG,
            7.0,
            BODY_REGISTRATION_OFFSET_LIMIT_DEG,
            SETUP_ONLY_ELBOW_TRACKING_ERROR_LIMIT_DEG,
            SETUP_OBSERVED_POSE_ELBOW_TRACKING_ERROR_LIMIT_DEG,
        },
        "setup elbow tracking limit must be exactly 6.0, 7.0, 12.0, 15.0, or 20.0 degrees",
    )
    observed_elbow_target = route.get(
        "setup_observed_elbow_target_degrees"
    )
    _require(
        observed_elbow_target is None
        or (
            not isinstance(observed_elbow_target, bool)
            and isinstance(observed_elbow_target, (int, float))
            and math.isfinite(float(observed_elbow_target))
        ),
        "setup observed elbow target must be finite when configured",
    )
    hold_seconds = route.get("setup_target_hold_seconds", 0.0)
    capture_seconds = route.get("stationary_capture_seconds", 0.0)
    for value, label, maximum in (
        (
            hold_seconds,
            "setup target hold",
            MAX_SETUP_TARGET_HOLD_SECONDS,
        ),
        (
            capture_seconds,
            "stationary capture",
            MAX_STATIONARY_CAPTURE_SECONDS,
        ),
    ):
        _require(
            not isinstance(value, bool)
            and isinstance(value, (int, float))
            and math.isfinite(float(value))
            and float(value) >= 0.0,
            f"{label} seconds must be finite and non-negative",
        )
        _require(
            float(value) <= maximum,
            f"{label} seconds cannot exceed {maximum:.1f}",
        )
    return (
        route,
        targets[0],
        float(configured_slew),
        float(setup_elbow_limit),
        float(hold_seconds),
        float(capture_seconds),
        (
            float(observed_elbow_target)
            if observed_elbow_target is not None
            else None
        ),
    )


def _camera_artifacts(output_root: Path) -> dict[str, dict[str, Any]]:
    candidates = {
        "lossless_video": output_root / "wrist_d405.mkv",
        "ffmpeg_log": output_root / "wrist_d405.ffmpeg.log",
        "browser_video": output_root / "wrist_d405.browser.mp4",
    }
    return {
        name: {
            "path": str(path),
            "sha256": _sha256(path),
            "size_bytes": path.stat().st_size,
        }
        for name, path in candidates.items()
        if path.is_file()
    }


def _preflight_identity_and_limits(
    preflight: Mapping[str, Any],
) -> tuple[dict[str, Any], np.ndarray, np.ndarray]:
    _require(
        preflight.get("passed") is True
        and preflight.get("control_source")
        == "frozen_precompiled_follower_actions"
        and preflight.get("real_leader_opened") is False
        and preflight.get("physical_follower_torque_enabled") is False,
        "fresh follower-only torque-off preflight did not pass",
    )
    identity = {
        "gateway_schema": preflight.get("schema_version"),
        "follower_port": preflight.get("follower_port"),
        "follower_calibration_sha256": preflight.get(
            "follower_calibration_sha256"
        ),
    }
    _require(
        isinstance(identity["follower_port"], str)
        and bool(identity["follower_port"])
        and isinstance(identity["follower_calibration_sha256"], str)
        and len(identity["follower_calibration_sha256"]) == 64,
        "follower hardware identity is incomplete",
    )
    lower = np.asarray(preflight.get("follower_calibrated_minimum"), dtype=np.float64)
    upper = np.asarray(preflight.get("follower_calibrated_maximum"), dtype=np.float64)
    _require(
        lower.shape == (6,)
        and upper.shape == (6,)
        and np.all(np.isfinite(lower))
        and np.all(np.isfinite(upper))
        and np.all(lower < upper),
        "fresh calibrated follower limits are invalid",
    )
    return identity, lower, upper


def _live_interpolation(
    anchor: np.ndarray,
    target: np.ndarray,
    *,
    maximum_slew_degrees_s: float = MAX_SLEW_DEGREES_S,
) -> tuple[np.ndarray, np.ndarray]:
    delta = target - anchor
    delta[4] = (float(target[4]) - float(anchor[4]) + 180.0) % 360.0 - 180.0
    _require(
        float(np.max(np.abs(delta))) <= MAX_STAGE_EXCURSION_DEGREES,
        "live-anchored target exceeds the 90 degree setup envelope",
    )
    interval_count = max(
        1,
        int(
            math.ceil(
                float(np.max(np.abs(delta)))
                / maximum_slew_degrees_s
                * SAMPLE_HZ
            )
        ),
    )
    actions = np.linspace(
        anchor,
        anchor + delta,
        interval_count + 1,
        dtype=np.float64,
    ).astype("<f8", copy=False)
    timestamps = np.arange(actions.shape[0], dtype="<f8") / SAMPLE_HZ
    rates = np.abs(np.diff(actions, axis=0) * SAMPLE_HZ)
    _require(
        float(np.max(rates)) <= maximum_slew_degrees_s + 1e-9,
        "live-anchored interpolation exceeds its route-bound setup slew",
    )
    return actions, timestamps


def execute_live_anchored_camera_reposition(
    *,
    route_path: Path,
    candidate_manifest_path: Path,
    output_root: Path,
    operator_acknowledged: bool,
    preflight_fn: Callable[[], dict[str, Any]] = _default_preflight,
    gateway_factory: Callable[[Any], Any] = _default_gateway,
    preview_fn: Callable[[list[np.ndarray], Path], dict[str, Any]] = (
        preview_wrist_view_actions
    ),
    recorder_factory: Callable[[Path], Any] = WristVideoRecorder,
    clock_fn: Callable[[], float] = time.monotonic,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Preview and execute one trajectory from a live torque-on anchor."""

    _require(operator_acknowledged, "physical setup execution requires --yes")
    route_path = route_path.resolve()
    candidate_manifest_path = candidate_manifest_path.resolve()
    output_root = output_root.resolve()
    _require(route_path.is_file(), f"route does not exist: {route_path}")
    _require(
        candidate_manifest_path.is_file(),
        f"candidate manifest does not exist: {candidate_manifest_path}",
    )
    _require(not output_root.exists(), f"refusing to overwrite output: {output_root}")
    (
        route,
        target,
        maximum_slew_degrees_s,
        setup_elbow_tracking_limit_degrees,
        target_hold_seconds,
        stationary_capture_seconds,
        observed_elbow_target_degrees,
    ) = _load_target(route_path)
    preflight = preflight_fn()
    identity, lower, upper = _preflight_identity_and_limits(preflight)
    _require(
        np.all(target >= lower) and np.all(target <= upper),
        "configured live-anchored target exceeds fresh calibrated limits",
    )

    output_root.mkdir(parents=True)
    telemetry_path = output_root / "telemetry.jsonl"
    action_path = output_root / "actions.float64le"
    executed_action_path = output_root / "executed_actions.float64le"
    receipt_path = output_root / "execution_receipt.json"
    gateway = gateway_factory(_gateway_identity(identity))
    opened: dict[str, Any] | None = None
    preview: dict[str, Any] | None = None
    actions: np.ndarray | None = None
    timestamps: np.ndarray | None = None
    completed_samples = 0
    attempted_samples = 0
    final_actual: list[float] | None = None
    failure: str | None = None
    shutdown_error: str | None = None
    started_monotonic: float | None = None
    movement_sample_count = 0
    hold_sample_count = int(math.ceil(target_hold_seconds * SAMPLE_HZ))
    capture_sample_count = int(math.ceil(stationary_capture_seconds * SAMPLE_HZ))
    capture_start_report: dict[str, Any] | None = None
    capture_report: dict[str, Any] | None = None
    capture_failure: str | None = None
    recorder: Any | None = None
    recorder_started = False
    executed_actions: list[np.ndarray] = []
    executed_movement_samples = 0
    observed_pose_stop: dict[str, Any] | None = None
    terminal_hold_started_monotonic: float | None = None
    terminal_hold_ended_monotonic: float | None = None

    try:
        opened = gateway.open_live_anchored_setup()
        raw_anchor = np.asarray(
            opened.get("settled_torque_on_anchor_degrees"),
            dtype=np.float64,
        )
        anchor = np.asarray(
            opened.get(
                "setup_command_anchor_degrees",
                opened.get("settled_torque_on_anchor_degrees"),
            ),
            dtype=np.float64,
        )
        live_lower = np.asarray(
            opened.get("follower_calibrated_minimum"), dtype=np.float64
        )
        live_upper = np.asarray(
            opened.get("follower_calibrated_maximum"), dtype=np.float64
        )
        _require(
            raw_anchor.shape == (6,)
            and np.all(np.isfinite(raw_anchor))
            and anchor.shape == (6,)
            and np.all(np.isfinite(anchor))
            and np.array_equal(lower, live_lower)
            and np.array_equal(upper, live_upper),
            "live gateway anchor or calibrated limits changed after preflight",
        )
        movement_actions, _ = _live_interpolation(
            anchor,
            target,
            maximum_slew_degrees_s=maximum_slew_degrees_s,
        )
        movement_sample_count = int(movement_actions.shape[0])
        stationary_actions = np.repeat(
            target[None, :],
            hold_sample_count + capture_sample_count,
            axis=0,
        )
        actions = np.concatenate((movement_actions, stationary_actions), axis=0)
        actions = actions.astype("<f8", copy=False)
        timestamps = np.arange(actions.shape[0], dtype="<f8") / SAMPLE_HZ
        _require(
            np.all(actions >= lower[None, :])
            and np.all(actions <= upper[None, :]),
            "live-anchored interpolation exceeds calibrated limits",
        )
        preview = preview_fn([actions], candidate_manifest_path)
        _require(
            preview.get("no_new_or_worsened_kinematic_contact") is True
            and not preview.get("external_contact_pairs"),
            "CPU preview rejected the live-anchored setup trajectory",
        )
        stages = preview.get("stages")
        _require(
            isinstance(stages, list)
            and len(stages) == 1
            and stages[0].get("exact_physical_action_sha256")
            == action_sha256(actions),
            "CPU preview did not consume the exact live trajectory",
        )
        action_path.write_bytes(actions.tobytes(order="C"))
        started_monotonic = clock_fn()

        def send_sample(
            action: np.ndarray,
            *,
            phase: str,
            phase_started: float,
            phase_index: int,
            planned_sample_index: int | None,
        ) -> dict[str, Any]:
            nonlocal attempted_samples, completed_samples, final_actual
            assert actions is not None
            delay = phase_started + float(phase_index) / SAMPLE_HZ - clock_fn()
            if delay > 0.0:
                sleep_fn(delay)
            attempted_samples += 1
            sample = gateway.sample(
                float(completed_samples) / SAMPLE_HZ,
                exact_requested_degrees=action,
                setup_elbow_tracking_error_limit_degrees=(
                    setup_elbow_tracking_limit_degrees
                    if setup_elbow_tracking_limit_degrees
                    in {
                        7.0,
                        BODY_REGISTRATION_OFFSET_LIMIT_DEG,
                        SETUP_ONLY_ELBOW_TRACKING_ERROR_LIMIT_DEG,
                        SETUP_OBSERVED_POSE_ELBOW_TRACKING_ERROR_LIMIT_DEG,
                    }
                    else None
                ),
            )
            _require(
                sample.get("physical_follower_torque_enabled") is True
                and sample.get("precompiled_exact_action") is True
                and sample.get("safety_clamped") is False
                and sample.get("rate_limited") is False,
                "gateway modified or rejected a live-anchored setup sample",
            )
            row = {
                "sample_index": completed_samples,
                "planned_sample_index": planned_sample_index,
                "setup_phase": phase,
                "planned_full_action_sha256": action_sha256(actions),
                **sample,
            }
            executed_actions.append(action.copy())
            completed_samples += 1
            final_actual = sample.get("follower_actual_position_degrees")
            telemetry.write(json.dumps(row, sort_keys=True) + "\n")
            telemetry.flush()
            return sample

        with telemetry_path.open("x", encoding="utf-8") as telemetry:
            for sample_index in range(movement_sample_count):
                sample = send_sample(
                    actions[sample_index],
                    phase="motion",
                    phase_started=started_monotonic,
                    phase_index=sample_index,
                    planned_sample_index=sample_index,
                )
                executed_movement_samples += 1
                actual = np.asarray(
                    sample.get("follower_actual_position_degrees"),
                    dtype=np.float64,
                )
                if (
                    observed_elbow_target_degrees is not None
                    and actual.shape == (6,)
                    and float(actual[2]) <= observed_elbow_target_degrees
                ):
                    stop_command = actions[sample_index].copy()
                    observed_pose_stop = {
                        "configured_observed_elbow_target_degrees": (
                            observed_elbow_target_degrees
                        ),
                        "planned_sample_index": sample_index,
                        "executed_sample_index": completed_samples - 1,
                        "observed_degrees": actual.tolist(),
                        "exact_command_degrees": stop_command.tolist(),
                        "exact_command_sha256": action_sha256(
                            stop_command[None, :]
                        ),
                        "planned_motion_prefix_sha256": action_sha256(
                            actions[: sample_index + 1]
                        ),
                    }
                    break
        _require(
            final_actual is not None,
            "live-anchored setup produced no final follower observation",
        )
        if observed_elbow_target_degrees is not None:
            _require(
                observed_pose_stop is not None,
                "observed elbow target was not reached before the full safe command path ended",
            )
        else:
            residual = target - np.asarray(final_actual, dtype=np.float64)
            residual[4] = (
                float(target[4]) - float(final_actual[4]) + 180.0
            ) % 360.0 - 180.0
            _require(
                np.all(np.abs(residual) <= FINAL_TOLERANCE_DEGREES),
                "follower did not reach the live-anchored camera target",
            )
        hold_command = executed_actions[-1].copy()
        with telemetry_path.open("a", encoding="utf-8") as telemetry:
            hold_started = clock_fn()
            terminal_hold_started_monotonic = hold_started
            for phase_index in range(hold_sample_count):
                send_sample(
                    hold_command,
                    phase="target_hold",
                    phase_started=hold_started,
                    phase_index=phase_index,
                    planned_sample_index=None,
                )
            if target_hold_seconds > 0.0:
                delay = hold_started + target_hold_seconds - clock_fn()
                if delay > 0.0:
                    sleep_fn(delay)
            terminal_hold_ended_monotonic = clock_fn()
            if stationary_capture_seconds > 0.0:
                recorder = recorder_factory(output_root / "wrist_d405.mkv")
                capture_start_report = recorder.start()
                recorder_started = True
                capture_started = clock_fn()
                for phase_index in range(capture_sample_count):
                    send_sample(
                        hold_command,
                        phase="stationary_capture",
                        phase_started=capture_started,
                        phase_index=phase_index,
                        planned_sample_index=None,
                    )
                delay = (
                    capture_started + stationary_capture_seconds - clock_fn()
                )
                if delay > 0.0:
                    sleep_fn(delay)
                capture_stopped = clock_fn()
                capture_report = recorder.finish(
                    action_started_monotonic=capture_started,
                    action_stopped_monotonic=capture_stopped,
                    post_roll_seconds=0.0,
                )
                recorder_started = False
                _require(
                    capture_report.get("status") == "completed",
                    "stationary D405 capture did not complete",
                )
        executed_array = np.asarray(executed_actions, dtype="<f8")
        executed_action_path.write_bytes(executed_array.tobytes(order="C"))
    except Exception as error:
        failure = f"{type(error).__name__}: {error}"
    finally:
        if recorder_started and recorder is not None:
            try:
                capture_report = recorder.finish(
                    action_started_monotonic=None,
                    action_stopped_monotonic=clock_fn(),
                    post_roll_seconds=0.0,
                )
            except Exception as error:
                capture_failure = f"{type(error).__name__}: {error}"
            recorder_started = False
        try:
            gateway.close()
        except Exception as error:
            shutdown_error = f"{type(error).__name__}: {error}"

    if executed_actions:
        executed_array = np.asarray(executed_actions, dtype="<f8")
        executed_action_path.write_bytes(executed_array.tobytes(order="C"))
    expected_executed_samples = (
        executed_movement_samples + hold_sample_count + capture_sample_count
    )
    completed = (
        failure is None
        and shutdown_error is None
        and actions is not None
        and completed_samples == expected_executed_samples
        and (
            observed_elbow_target_degrees is None
            or observed_pose_stop is not None
        )
    )
    planned_samples = int(actions.shape[0]) if actions is not None else 0
    partial_motion = (
        failure is not None
        and 0 < executed_movement_samples < movement_sample_count
    )
    setup_motion_completed = (
        executed_movement_samples > 0
        and (
            observed_pose_stop is not None
            or executed_movement_samples == movement_sample_count
        )
    )
    sent_motion_samples = executed_movement_samples
    sent_hold_samples = min(
        max(completed_samples - executed_movement_samples, 0),
        hold_sample_count,
    )
    sent_capture_samples = min(
        max(
            completed_samples - executed_movement_samples - hold_sample_count,
            0,
        ),
        capture_sample_count,
    )
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "status": (
            "completed_live_anchored_camera_reposition"
            if completed
            else (
                "stopped_safely_after_partial_setup_motion"
                if partial_motion
                else (
                    "stopped_safely_after_completed_setup_motion"
                    if setup_motion_completed
                    else "stopped_safely_before_setup_motion"
                )
            )
        ),
        "proof_class": "physical_camera_setup_only",
        "route": {
            "route_id": route["route_id"],
            "path": str(route_path),
            "sha256": _sha256(route_path),
            "target_degrees": target.tolist(),
        },
        "candidate_manifest": {
            "path": str(candidate_manifest_path),
            "sha256": _sha256(candidate_manifest_path),
        },
        "hardware_identity": identity,
        "gateway_open": opened,
        "live_anchor_degrees": (
            opened.get("settled_torque_on_anchor_degrees")
            if opened is not None
            else None
        ),
        "setup_command_anchor": (
            {
                "raw_observed_degrees": opened.get(
                    "settled_torque_on_anchor_degrees"
                ),
                "command_anchor_degrees": opened.get(
                    "setup_command_anchor_degrees",
                    opened.get("settled_torque_on_anchor_degrees"),
                ),
                "snap_delta_degrees": opened.get(
                    "setup_anchor_snap_delta_degrees",
                    [0.0] * 6,
                ),
                "snap_limit_degrees": opened.get(
                    "setup_anchor_snap_limit_degrees",
                    3.0,
                ),
                "elbow_only": True,
                "calibrated_limits_widened": False,
            }
            if opened is not None
            else None
        ),
        "trajectory": (
            {
                "sample_hz": SAMPLE_HZ,
                "sample_count": int(actions.shape[0]),
                "maximum_slew_degrees_s": maximum_slew_degrees_s,
                "default_maximum_slew_degrees_s": MAX_SLEW_DEGREES_S,
                "route_overrides_default_slew": (
                    maximum_slew_degrees_s != MAX_SLEW_DEGREES_S
                ),
                "setup_elbow_tracking_error_limit_degrees": (
                    setup_elbow_tracking_limit_degrees
                ),
                "global_body_tracking_error_limit_degrees": (
                    BODY_TRACKING_ERROR_LIMIT_DEG
                ),
                "setup_tracking_override_applied": (
                    setup_elbow_tracking_limit_degrees
                    != BODY_TRACKING_ERROR_LIMIT_DEG
                ),
                "movement_sample_count": movement_sample_count,
                "planned_full_movement_sample_count": movement_sample_count,
                "executed_movement_prefix_sample_count": (
                    executed_movement_samples
                ),
                "target_hold_seconds": target_hold_seconds,
                "target_hold_effective_command_seconds": (
                    hold_sample_count / SAMPLE_HZ
                ),
                "target_hold_maximum_seconds": (
                    MAX_SETUP_TARGET_HOLD_SECONDS
                ),
                "target_hold_sample_count": hold_sample_count,
                "stationary_capture_seconds": stationary_capture_seconds,
                "stationary_capture_effective_command_seconds": (
                    capture_sample_count / SAMPLE_HZ
                ),
                "stationary_capture_maximum_seconds": (
                    MAX_STATIONARY_CAPTURE_SECONDS
                ),
                "stationary_capture_sample_count": capture_sample_count,
                "maximum_excursion_degrees": float(
                    np.max(np.abs(actions[-1] - actions[0]))
                ),
                "action_sha256": action_sha256(actions),
                "action_bytes_path": str(action_path),
                "action_bytes_sha256": _sha256(action_path),
                "executed_action_sha256": (
                    action_sha256(
                        np.asarray(executed_actions, dtype="<f8")
                    )
                    if executed_actions
                    else None
                ),
                "executed_action_bytes_path": str(executed_action_path),
                "executed_action_bytes_sha256": (
                    _sha256(executed_action_path)
                    if executed_action_path.is_file()
                    else None
                ),
                "timestamps_seconds": timestamps.tolist(),
            }
            if actions is not None and action_path.is_file()
            else None
        ),
        "cpu_preview": preview,
        "observed_pose_termination": {
            "configured": observed_elbow_target_degrees is not None,
            "target_elbow_degrees": observed_elbow_target_degrees,
            "reached": observed_pose_stop is not None,
            "stop": observed_pose_stop,
            "planned_full_path_was_cpu_previewed": True,
            "executed_path_is_safe_prefix_plus_exact_terminal_hold": True,
            "sim_gap_evidence": False,
            "evaluator_admission": False,
        },
        "terminal_hold_monotonic_interval": {
            "start": terminal_hold_started_monotonic,
            "end": terminal_hold_ended_monotonic,
            "duration_seconds": (
                terminal_hold_ended_monotonic
                - terminal_hold_started_monotonic
                if terminal_hold_started_monotonic is not None
                and terminal_hold_ended_monotonic is not None
                else None
            ),
            "clock": "time.monotonic",
            "exact_terminal_command_sha256": (
                observed_pose_stop["exact_command_sha256"]
                if observed_pose_stop is not None
                else (
                    action_sha256(executed_actions[-1][None, :])
                    if executed_actions
                    else None
                )
            ),
        },
        "stationary_d405_capture": {
            "requested": stationary_capture_seconds > 0.0,
            "start_report": capture_start_report,
            "completion_report": capture_report,
            "failure": capture_failure,
            "completed_before_gateway_close": (
                capture_report is not None
                and capture_report.get("status") == "completed"
            ),
            "artifacts": _camera_artifacts(output_root),
        },
        "telemetry": {
            "path": str(telemetry_path),
            "sha256": _sha256(telemetry_path) if telemetry_path.is_file() else None,
            "planned_sample_count": planned_samples,
            "attempted_sample_count": attempted_samples,
            "sent_sample_count": completed_samples,
            "partial_setup_motion_commanded": partial_motion,
            "setup_motion_completed": setup_motion_completed,
            "phase_sample_counts": {
                "motion": {
                    "planned": movement_sample_count,
                    "sent": sent_motion_samples,
                },
                "target_hold": {
                    "planned": hold_sample_count,
                    "sent": sent_hold_samples,
                },
                "stationary_capture": {
                    "planned": capture_sample_count,
                    "sent": sent_capture_samples,
                },
            },
            "last_sent_sample_index": (
                completed_samples - 1 if completed_samples else None
            ),
            "first_unsent_sample_index": (
                completed_samples
                if failure is not None and completed_samples < planned_samples
                else None
            ),
            "first_unexecuted_planned_motion_sample_index": (
                executed_movement_samples
                if executed_movement_samples < movement_sample_count
                else None
            ),
            "final_actual_degrees": final_actual,
        },
        "failure": failure,
        "shutdown_error": shutdown_error,
        "physical_follower_torque_enabled": (
            False if shutdown_error is None else None
        ),
        "shutdown_torque_off_confirmed": shutdown_error is None,
        "evidence_limits": {
            "setup_only": True,
            "action_frozen_before_torque_on": False,
            "sim_gap_evidence": False,
            "policy_evidence": False,
            "evaluator_admission": False,
            "training_admission": False,
            "promotion": False,
        },
    }
    _write_json(receipt_path, receipt)
    if not completed:
        raise LiveAnchoredCameraRepositionError(
            failure or shutdown_error or "live-anchored setup stopped"
        )
    return receipt
