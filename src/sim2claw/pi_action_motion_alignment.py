"""Fail-closed same-run Pi frame to action-interval alignment."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

import cv2
import numpy as np

from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
)
from .observable_registration_belief_recalculation import (
    REPO_ROOT,
    _bound_path,
)

SCHEMA = "sim2claw.pi_action_motion_alignment_contract.v1"
RECEIPT_SCHEMA = "sim2claw.pi_action_motion_alignment_receipt.v1"
CURVES_SCHEMA = "sim2claw.pi_action_motion_alignment_curves.v1"
ASSOCIATIONS_SCHEMA = (
    "sim2claw.pi_frame_action_interval_associations.v1"
)
CONTRACT_PATH = (
    REPO_ROOT
    / "configs/evaluations/pi_action_motion_alignment_v1.json"
)
OUTPUT_DIRECTORY = REPO_ROOT / "outputs/pi_action_motion_alignment_v1"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _smooth(values: np.ndarray, width: int = 3) -> np.ndarray:
    if len(values) < width:
        return values.astype(np.float64, copy=True)
    return np.convolve(
        values,
        np.ones(width, dtype=np.float64) / width,
        mode="same",
    )


def _standardize(values: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    deviation = float(np.std(values))
    if deviation <= 1e-12:
        return np.zeros_like(values)
    return (values - float(np.mean(values))) / deviation


def _video_motion(
    path: Path, *, width: int, height: int
) -> dict[str, Any]:
    capture = cv2.VideoCapture(str(path))
    _require(capture.isOpened(), f"video unavailable: {path}")
    energies: list[float] = []
    previous: np.ndarray | None = None
    frame_count = 0
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            gray = cv2.resize(
                cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY),
                (width, height),
                interpolation=cv2.INTER_AREA,
            )
            if previous is not None:
                energies.append(
                    float(np.mean(cv2.absdiff(gray, previous)))
                )
            previous = gray
            frame_count += 1
    finally:
        capture.release()
    _require(frame_count >= 2, f"video has too few frames: {path}")
    smoothed = _smooth(np.asarray(energies, dtype=np.float64))
    derivative = np.gradient(smoothed)
    return {
        "frame_count": frame_count,
        "motion_energy": smoothed,
        "motion_derivative": derivative,
    }


def _pi_pts_seconds(path: Path) -> np.ndarray:
    values = [
        float(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    result = np.asarray(values, dtype=np.float64) / 1000.0
    _require(
        len(result) >= 2 and bool(np.all(np.diff(result) > 0.0)),
        "Pi PTS are not strictly increasing",
    )
    return result


def _best_lag(
    *,
    pi_t: np.ndarray,
    pi_signal: np.ndarray,
    reference_t: np.ndarray,
    reference_signal: np.ndarray,
    lag_values: np.ndarray,
    fit_minimum: float,
    fit_maximum: float,
    exclusions: Iterable[tuple[float, float]] = (),
) -> dict[str, Any]:
    pi_signal = _standardize(pi_signal)
    reference_signal = _standardize(reference_signal)
    scores: list[float] = []
    for lag in lag_values:
        host_t = pi_t + float(lag)
        mask = (host_t >= fit_minimum) & (host_t <= fit_maximum)
        for low, high in exclusions:
            mask &= (host_t < low) | (host_t > high)
        if int(np.count_nonzero(mask)) < 20:
            scores.append(float("nan"))
            continue
        reference = np.interp(
            host_t[mask], reference_t, reference_signal
        )
        if float(np.std(reference)) <= 1e-12:
            scores.append(float("nan"))
            continue
        scores.append(
            float(np.corrcoef(pi_signal[mask], reference)[0, 1])
        )
    score_array = np.asarray(scores, dtype=np.float64)
    _require(
        bool(np.any(np.isfinite(score_array))),
        "lag search has no finite score",
    )
    best_index = int(np.nanargmax(score_array))
    return {
        "lag_seconds": float(lag_values[best_index]),
        "score": float(score_array[best_index]),
        "scores": score_array,
    }


def _transitions(
    host_t: np.ndarray,
    joint_energy: np.ndarray,
    *,
    threshold_fraction: float,
    minimum_separation_seconds: float,
) -> list[int]:
    peak = float(np.max(joint_energy))
    if peak <= 1e-12:
        return []
    moving = joint_energy > threshold_fraction * peak
    candidates = (
        np.flatnonzero(np.diff(moving.astype(np.int8)) != 0) + 1
    )
    selected: list[int] = []
    for index in candidates.tolist():
        if (
            not selected
            or float(host_t[index] - host_t[selected[-1]])
            >= minimum_separation_seconds
        ):
            selected.append(index)
    return selected


def _binding_paths(
    run: Mapping[str, Any], *, root: Path
) -> dict[str, Path]:
    return {
        name: _bound_path(binding, root=root, label=f"{run['run_id']} {name}")
        for name, binding in run.items()
        if isinstance(binding, Mapping)
        and set(binding) >= {"path", "sha256"}
    }


def load_pi_action_motion_alignment_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="Pi action motion alignment")
    _require(contract.get("schema_version") == SCHEMA, "unsupported contract")
    method = contract["method"]
    _require(
        method["fit_model"] == "one_constant_offset_per_run"
        and method["drift_fit_allowed"] is False
        and method["scale_fit_allowed"] is False
        and method["task_contact_or_outcome_fit_allowed"] is False
        and method["cross_episode_merge_allowed"] is False,
        "alignment fit boundary widened",
    )
    _require(
        method["minimum_independent_transitions"] >= 3
        and method["minimum_distinct_peak_margin_fraction"] >= 0.2
        and method["maximum_association_interval_seconds"] <= 0.1,
        "alignment acceptance weakened",
    )
    for run in contract["runs"]:
        paths = _binding_paths(run, root=root)
        _require(
            set(paths)
            == {
                "execution_receipt",
                "joint_samples",
                "pi_video",
                "pi_pts",
                "c922_video",
                "c922_callbacks",
            },
            f"{run['run_id']} bindings incomplete",
        )
    _require(
        not any(contract["authority"].values()),
        "alignment authority widened",
    )
    _require(
        contract["reporting"]["original_successful_d1_d2_pi_available"]
        is False
        and contract["reporting"]["transfer_claim_allowed"] is False,
        "alignment claim boundary widened",
    )
    return contract


def _evaluate_run(
    run: Mapping[str, Any],
    *,
    method: Mapping[str, Any],
    root: Path,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    paths = _binding_paths(run, root=root)
    execution = load_json_object(
        paths["execution_receipt"], label=f"{run['run_id']} execution"
    )
    pi_receipt = execution["camera_finished"]["pi"]
    _require(
        pi_receipt["timestamp_semantics"]["host_bounds_only"] is True
        and pi_receipt["timestamp_semantics"][
            "camera_exposure_synchronized"
        ]
        is False
        and pi_receipt["timestamp_semantics"][
            "cross_camera_exposure_synchronized"
        ]
        is False,
        f"{run['run_id']} Pi timestamp semantics changed",
    )
    pi_pts = _pi_pts_seconds(paths["pi_pts"])
    pi_motion = _video_motion(
        paths["pi_video"],
        width=int(method["resize_width"]),
        height=int(method["resize_height"]),
    )
    _require(
        pi_motion["frame_count"] == len(pi_pts),
        f"{run['run_id']} Pi frame/PTS count mismatch",
    )
    c922_motion = _video_motion(
        paths["c922_video"],
        width=int(method["resize_width"]),
        height=int(method["resize_height"]),
    )
    callback_rows = _jsonl(paths["c922_callbacks"])
    c922_host = np.asarray(
        [
            float(row["host_continuous_ns"]) / 1e9
            for row in callback_rows
            if row.get("role") == "c922"
            and row.get("appended_to_writer") is True
        ],
        dtype=np.float64,
    )
    _require(
        c922_motion["frame_count"] == len(c922_host),
        f"{run['run_id']} C922 frame/callback count mismatch",
    )
    joint_rows_all = _jsonl(paths["joint_samples"])
    allowed_phases = set(run["fit_phase_allowlist"])
    joint_rows = [
        row for row in joint_rows_all if row["phase"] in allowed_phases
    ]
    _require(
        len(joint_rows) >= 2,
        f"{run['run_id']} fit phase has too few joint rows",
    )
    joint_host = np.asarray(
        [float(row["host_continuous_ns"]) / 1e9 for row in joint_rows],
        dtype=np.float64,
    )
    joint_energy = _smooth(
        np.asarray(
            [
                sum(
                    abs(float(value))
                    for value in row[
                        "follower_actual_velocity_degrees_s"
                    ]
                )
                for row in joint_rows
            ],
            dtype=np.float64,
        )
    )
    transitions = _transitions(
        joint_host,
        joint_energy,
        threshold_fraction=float(
            method["joint_motion_threshold_fraction_of_peak"]
        ),
        minimum_separation_seconds=float(
            method["minimum_transition_separation_seconds"]
        ),
    )

    pi_host_base = (
        float(pi_receipt["host_monotonic_start"]) + pi_pts[1:]
    )
    lag_values = np.arange(
        float(method["lag_minimum_seconds"]),
        float(method["lag_maximum_seconds"])
        + 0.5 * float(method["lag_step_seconds"]),
        float(method["lag_step_seconds"]),
        dtype=np.float64,
    )
    visual = _best_lag(
        pi_t=pi_host_base,
        pi_signal=pi_motion["motion_derivative"],
        reference_t=c922_host[1:],
        reference_signal=c922_motion["motion_derivative"],
        lag_values=lag_values,
        fit_minimum=float(joint_host[0]),
        fit_maximum=float(joint_host[-1]),
    )
    frame_period = float(np.median(np.diff(pi_pts)))
    distinct = (
        np.abs(lag_values - float(visual["lag_seconds"]))
        >= int(method["distinct_peak_exclusion_pi_frames"])
        * frame_period
    )
    second_score = float(np.nanmax(visual["scores"][distinct]))
    peak_margin = (
        float(visual["score"]) - second_score
    ) / max(abs(float(visual["score"])), 1e-12)

    joint = _best_lag(
        pi_t=pi_host_base,
        pi_signal=pi_motion["motion_energy"],
        reference_t=joint_host,
        reference_signal=joint_energy,
        lag_values=lag_values,
        fit_minimum=float(joint_host[0]),
        fit_maximum=float(joint_host[-1]),
    )
    exclusion_radius = float(
        method["leave_one_transition_out_seconds"]
    )
    leave_one_lags: list[float] = []
    for transition_index in transitions:
        transition_time = float(joint_host[transition_index])
        result = _best_lag(
            pi_t=pi_host_base,
            pi_signal=pi_motion["motion_derivative"],
            reference_t=c922_host[1:],
            reference_signal=c922_motion["motion_derivative"],
            lag_values=lag_values,
            fit_minimum=float(joint_host[0]),
            fit_maximum=float(joint_host[-1]),
            exclusions=[
                (
                    transition_time - exclusion_radius,
                    transition_time + exclusion_radius,
                )
            ],
        )
        leave_one_lags.append(float(result["lag_seconds"]))
    lag_span = (
        max(leave_one_lags) - min(leave_one_lags)
        if leave_one_lags
        else float("inf")
    )
    if leave_one_lags:
        lag_low = min(
            [float(visual["lag_seconds"]), *leave_one_lags]
        ) - 0.5 * frame_period
        lag_high = max(
            [float(visual["lag_seconds"]), *leave_one_lags]
        ) + 0.5 * frame_period
    else:
        lag_low = float(visual["lag_seconds"]) - 0.5 * frame_period
        lag_high = float(visual["lag_seconds"]) + 0.5 * frame_period
    interval_width = lag_high - lag_low
    joint_delta = abs(
        float(visual["lag_seconds"]) - float(joint["lag_seconds"])
    )
    gates = {
        "minimum_c922_derivative_correlation": float(visual["score"])
        >= float(method["minimum_c922_derivative_correlation"]),
        "distinct_peak_margin": peak_margin
        >= float(method["minimum_distinct_peak_margin_fraction"]),
        "minimum_independent_transitions": len(transitions)
        >= int(method["minimum_independent_transitions"]),
        "leave_one_transition_out_lag_span": lag_span
        <= float(
            method[
                "maximum_leave_one_transition_out_lag_span_seconds"
            ]
        ),
        "joint_corroboration_lag_delta": joint_delta
        <= float(method["maximum_joint_corroboration_lag_delta_seconds"])
        + 1e-12,
        "association_interval_width": interval_width
        <= float(method["maximum_association_interval_seconds"]),
    }
    accepted = all(gates.values())
    result = {
        "run_id": run["run_id"],
        "role": run["role"],
        "status": (
            "PASS_PI_ACTION_INTERVAL_ASSOCIATION"
            if accepted
            else "PI_ACTION_ASSOCIATION_INSUFFICIENT"
        ),
        "fit_phase_allowlist": run["fit_phase_allowlist"],
        "pi_frame_count": pi_motion["frame_count"],
        "c922_frame_count": c922_motion["frame_count"],
        "joint_row_count": len(joint_rows),
        "transition_count": len(transitions),
        "visual_lag_seconds": float(visual["lag_seconds"]),
        "visual_correlation": float(visual["score"]),
        "distinct_second_score": second_score,
        "distinct_peak_margin_fraction": peak_margin,
        "joint_corroboration_lag_seconds": float(
            joint["lag_seconds"]
        ),
        "joint_corroboration_score": float(joint["score"]),
        "joint_corroboration_lag_delta_seconds": joint_delta,
        "leave_one_transition_out_lags_seconds": leave_one_lags,
        "leave_one_transition_out_lag_span_seconds": lag_span,
        "association_lag_interval_seconds": (
            [lag_low, lag_high] if accepted else None
        ),
        "association_interval_width_seconds": (
            interval_width if accepted else None
        ),
        "gates": gates,
        "task_contact_or_outcome_used_for_fit": False,
        "camera_exposure_synchronized": False,
        "cross_camera_exposure_synchronized": False,
    }
    curves = {
        "run_id": run["run_id"],
        "pi_pts_seconds": pi_pts[1:].tolist(),
        "pi_motion_energy": pi_motion["motion_energy"].tolist(),
        "pi_motion_derivative": pi_motion[
            "motion_derivative"
        ].tolist(),
        "c922_host_seconds": c922_host[1:].tolist(),
        "c922_motion_energy": c922_motion["motion_energy"].tolist(),
        "c922_motion_derivative": c922_motion[
            "motion_derivative"
        ].tolist(),
        "joint_host_seconds": joint_host.tolist(),
        "joint_motion_energy": joint_energy.tolist(),
        "lag_grid_seconds": lag_values.tolist(),
        "visual_lag_scores": visual["scores"].tolist(),
        "joint_lag_scores": joint["scores"].tolist(),
    }
    associations: list[dict[str, Any]] = []
    if accepted:
        all_joint_host = np.asarray(
            [
                float(row["host_continuous_ns"]) / 1e9
                for row in joint_rows_all
            ],
            dtype=np.float64,
        )
        for frame_index, pts in enumerate(pi_pts):
            host_low = float(pi_receipt["host_monotonic_start"]) + float(
                pts
            ) + lag_low
            host_high = float(pi_receipt["host_monotonic_start"]) + float(
                pts
            ) + lag_high
            low_index = int(
                np.clip(
                    np.searchsorted(all_joint_host, host_low, side="left"),
                    0,
                    len(all_joint_host) - 1,
                )
            )
            high_index = int(
                np.clip(
                    np.searchsorted(all_joint_host, host_high, side="right")
                    - 1,
                    0,
                    len(all_joint_host) - 1,
                )
            )
            associations.append(
                {
                    "pi_frame_index": frame_index,
                    "pi_pts_seconds": float(pts),
                    "host_interval_seconds": [host_low, host_high],
                    "joint_row_interval": [low_index, high_index],
                    "joint_sample_index_interval": [
                        int(joint_rows_all[low_index]["sample_index"]),
                        int(joint_rows_all[high_index]["sample_index"]),
                    ],
                }
            )
    return result, curves, associations


def build_pi_action_motion_alignment(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    _require(not receipt_path.exists(), "OR22A output already exists")
    contract = load_pi_action_motion_alignment_contract(
        contract_path, root=root
    )
    results: list[dict[str, Any]] = []
    curve_rows: list[dict[str, Any]] = []
    association_runs: list[dict[str, Any]] = []
    for run in contract["runs"]:
        result, curves, associations = _evaluate_run(
            run, method=contract["method"], root=root
        )
        results.append(result)
        curve_rows.append(curves)
        association_runs.append(
            {
                "run_id": run["run_id"],
                "status": result["status"],
                "rows": associations,
            }
        )
    contact_free = [
        result
        for result in results
        if result["role"] == "contact_free_method_validation"
    ]
    contact_free_passes = sum(
        result["status"] == "PASS_PI_ACTION_INTERVAL_ASSOCIATION"
        for result in contact_free
    )
    method_gate = contact_free_passes >= int(
        contract["reporting"]["minimum_contact_free_accepted_runs"]
    )
    curves_path = output_directory / "curves.json"
    associations_path = output_directory / "associations.json"
    atomic_write_json(
        curves_path,
        {"schema_version": CURVES_SCHEMA, "runs": curve_rows},
    )
    atomic_write_json(
        associations_path,
        {
            "schema_version": ASSOCIATIONS_SCHEMA,
            "timestamp_semantics": {
                "camera_exposure_synchronized": False,
                "cross_camera_exposure_synchronized": False,
                "association_is_interval_valued": True,
            },
            "runs": association_runs,
        },
    )
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "proof_class": contract["proof_class"],
        "status": (
            "PASS_BOUNDED_PI_ACTION_INTERVAL_ALIGNMENT"
            if method_gate
            else "PI_ACTION_ASSOCIATION_INSUFFICIENT"
        ),
        "method_gate_passed": method_gate,
        "contact_free_validation": {
            "accepted_runs": contact_free_passes,
            "total_runs": len(contact_free),
            "minimum_required": contract["reporting"][
                "minimum_contact_free_accepted_runs"
            ],
        },
        "runs": results,
        "curves_sha256": _sha256(curves_path),
        "associations_sha256": _sha256(associations_path),
        "original_successful_d1_d2_pi_available": False,
        "task_contact_or_outcome_used_for_fit": False,
        "global_mapping_approved": False,
        "task_success_claim": False,
        "transfer_claim": False,
        "authority": contract["authority"],
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


def main() -> int:
    build_pi_action_motion_alignment()
    return 0
