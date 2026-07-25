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


class LiveAnchoredCameraRepositionError(RuntimeError):
    """A live-anchored setup action failed closed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise LiveAnchoredCameraRepositionError(message)


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
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


def _load_target(route_path: Path) -> tuple[dict[str, Any], np.ndarray]:
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
    return route, targets[0]


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
                / MAX_SLEW_DEGREES_S
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
        float(np.max(rates)) <= MAX_SLEW_DEGREES_S + 1e-9,
        "live-anchored interpolation exceeds 10 degrees/s",
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
    route, target = _load_target(route_path)
    preflight = preflight_fn()
    identity, lower, upper = _preflight_identity_and_limits(preflight)
    _require(
        np.all(target >= lower) and np.all(target <= upper),
        "configured live-anchored target exceeds fresh calibrated limits",
    )

    output_root.mkdir(parents=True)
    telemetry_path = output_root / "telemetry.jsonl"
    action_path = output_root / "actions.float64le"
    receipt_path = output_root / "execution_receipt.json"
    gateway = gateway_factory(_gateway_identity(identity))
    opened: dict[str, Any] | None = None
    preview: dict[str, Any] | None = None
    actions: np.ndarray | None = None
    timestamps: np.ndarray | None = None
    completed_samples = 0
    final_actual: list[float] | None = None
    failure: str | None = None
    shutdown_error: str | None = None
    started_monotonic: float | None = None

    try:
        opened = gateway.open_live_anchored_setup()
        anchor = np.asarray(
            opened.get("settled_torque_on_anchor_degrees"),
            dtype=np.float64,
        )
        live_lower = np.asarray(
            opened.get("follower_calibrated_minimum"), dtype=np.float64
        )
        live_upper = np.asarray(
            opened.get("follower_calibrated_maximum"), dtype=np.float64
        )
        _require(
            anchor.shape == (6,)
            and np.all(np.isfinite(anchor))
            and np.array_equal(lower, live_lower)
            and np.array_equal(upper, live_upper),
            "live gateway anchor or calibrated limits changed after preflight",
        )
        actions, timestamps = _live_interpolation(anchor, target)
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
        with telemetry_path.open("x", encoding="utf-8") as telemetry:
            for sample_index, (timestamp, action) in enumerate(
                zip(timestamps, actions, strict=True)
            ):
                delay = started_monotonic + float(timestamp) - clock_fn()
                if delay > 0.0:
                    sleep_fn(delay)
                sample = gateway.sample(
                    float(timestamp),
                    exact_requested_degrees=action,
                )
                _require(
                    sample.get("physical_follower_torque_enabled") is True
                    and sample.get("precompiled_exact_action") is True
                    and sample.get("safety_clamped") is False
                    and sample.get("rate_limited") is False,
                    "gateway modified or rejected a live-anchored setup sample",
                )
                row = {
                    "sample_index": sample_index,
                    "source_action_sha256": action_sha256(actions),
                    **sample,
                }
                telemetry.write(json.dumps(row, sort_keys=True) + "\n")
                telemetry.flush()
                completed_samples += 1
                final_actual = sample.get("follower_actual_position_degrees")
        _require(
            final_actual is not None,
            "live-anchored setup produced no final follower observation",
        )
        residual = target - np.asarray(final_actual, dtype=np.float64)
        residual[4] = (
            float(target[4]) - float(final_actual[4]) + 180.0
        ) % 360.0 - 180.0
        _require(
            np.all(np.abs(residual) <= FINAL_TOLERANCE_DEGREES),
            "follower did not reach the live-anchored camera target",
        )
    except Exception as error:
        failure = f"{type(error).__name__}: {error}"
    finally:
        try:
            gateway.close()
        except Exception as error:
            shutdown_error = f"{type(error).__name__}: {error}"

    completed = (
        failure is None
        and shutdown_error is None
        and actions is not None
        and completed_samples == actions.shape[0]
    )
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "status": (
            "completed_live_anchored_camera_reposition"
            if completed
            else "stopped_safely"
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
        "trajectory": (
            {
                "sample_hz": SAMPLE_HZ,
                "sample_count": int(actions.shape[0]),
                "maximum_slew_degrees_s": MAX_SLEW_DEGREES_S,
                "maximum_excursion_degrees": float(
                    np.max(np.abs(actions[-1] - actions[0]))
                ),
                "action_sha256": action_sha256(actions),
                "action_bytes_path": str(action_path),
                "action_bytes_sha256": _sha256(action_path),
                "timestamps_seconds": timestamps.tolist(),
            }
            if actions is not None and action_path.is_file()
            else None
        ),
        "cpu_preview": preview,
        "telemetry": {
            "path": str(telemetry_path),
            "sha256": _sha256(telemetry_path) if telemetry_path.is_file() else None,
            "completed_samples": completed_samples,
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
