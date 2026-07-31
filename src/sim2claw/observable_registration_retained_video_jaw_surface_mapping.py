"""Fail-closed retained-video identification of gripper directional play."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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


SCHEMA = (
    "sim2claw."
    "observable_registration_retained_video_jaw_surface_mapping_contract.v1"
)
RECEIPT_SCHEMA = (
    "sim2claw."
    "observable_registration_retained_video_jaw_surface_mapping_receipt.v1"
)
CONTRACT_PATH = (
    REPO_ROOT
    / "configs/evaluations/"
    "observable_registration_retained_video_jaw_surface_mapping_v1.json"
)
OUTPUT_DIRECTORY = (
    REPO_ROOT
    / "outputs/observable_registration_retained_video_jaw_surface_mapping_v1"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def _load_jsonl(path: Path, *, label: str) -> list[dict[str, Any]]:
    try:
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as error:
        raise FactoryArtifactError(f"cannot read {label}: {error}") from error
    _require(
        bool(rows) and all(isinstance(row, dict) for row in rows),
        f"{label} is empty",
    )
    return rows


def load_retained_video_jaw_surface_mapping_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="OR40 retained-video mapping")
    _require(contract.get("schema_version") == SCHEMA, "unsupported contract")
    for source_id, binding in contract["sources"].items():
        _bound_path(binding, root=root, label=source_id)
    estimand = contract["estimand"]
    _require(
        estimand["mechanism"]
        == (
            "rate_independent_directional_play_between_raw_gripper_encoder_"
            "and_moving_contact_surface"
        )
        and not any(
            estimand[name]
            for name in (
                "metric_aperture_claim_allowed",
                "camera_calibration_claim_allowed",
                "force_stiffness_or_compliance_claim_allowed",
                "gearbox_backlash_claim_allowed",
            )
        ),
        "OR40 estimand or proof boundary widened",
    )
    trajectory = contract["trajectory"]
    _require(
        trajectory["row_count"] == 531
        and trajectory["raw_channel"]
        == "follower_actual_position_degrees[5]"
        and trajectory["timestamp_channel"] == "timestamp_monotonic_seconds"
        and trajectory["source_values_order_and_timestamps_immutable"] is True,
        "OR40 raw trajectory boundary widened",
    )
    partition = contract["partition"]
    _require(
        partition["mapping_sample_range_inclusive"] == [110, 224]
        and partition["contact_holdout_sample_range_inclusive"] == [228, 260]
        and partition["terminal_sample_range_inclusive"] == [261, 530]
        and partition["contact_and_terminal_samples_available_to_fit_or_selection"]
        is False
        and partition["validation_refit_allowed"] is False,
        "OR40 partition changed",
    )
    replay = contract["replay"]
    _require(
        replay["permitted_only_if_mapping_gate_passes"] is True
        and replay["maximum_dynamic_replays"] == 1
        and replay["base_topology"]
        == "OR36S_MEASURED_STATE_SINGLE_SURFACE_V1"
        and replay["raw_rows_values_order_and_timestamps_immutable"] is True
        and replay["object_pose_injection_allowed"] is False
        and replay["latch_or_grasp_mode_allowed"] is False
        and replay["terminal_refit_allowed"] is False,
        "OR40 replay boundary widened",
    )
    _require(
        not any(contract["claim_limits"].values()),
        "OR40 claim boundary widened",
    )
    return contract


def _decode_video(path: Path) -> list[np.ndarray]:
    capture = cv2.VideoCapture(str(path))
    _require(capture.isOpened(), "cannot open OR40 wrist video")
    frames: list[np.ndarray] = []
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        frames.append(frame)
    capture.release()
    _require(bool(frames), "OR40 wrist video is empty")
    return frames


def _best_frame_bindings(
    schedule: dict[str, Any], *, first_frame: int, last_frame: int
) -> dict[int, dict[str, Any]]:
    result: dict[int, dict[str, Any]] = {}
    for row in schedule["sample_frame_bindings"]:
        frame_index = int(row["d405"]["frame_index"])
        if not first_frame <= frame_index <= last_frame:
            continue
        previous = result.get(frame_index)
        if previous is None or float(
            row["d405"]["association_error_ms"]
        ) < float(previous["d405"]["association_error_ms"]):
            result[frame_index] = row
    return result


def _red_pad_observation(
    frame: np.ndarray, extraction: dict[str, Any]
) -> dict[str, Any] | None:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    hue = hsv[:, :, 0]
    mask = (
        (
            (hue < int(extraction["hue_low_max"]))
            | (hue > int(extraction["hue_high_min"]))
        )
        & (hsv[:, :, 1] > int(extraction["minimum_saturation"]))
        & (hsv[:, :, 2] > int(extraction["minimum_value"]))
    ).astype(np.uint8)
    mask[: int(extraction["minimum_y"]), :] = 0
    count, _, stats, centroids = cv2.connectedComponentsWithStats(mask)
    x_min, x_max = [
        float(value) for value in extraction["centroid_x_range"]
    ]
    candidates: list[dict[str, Any]] = []
    for component_id in range(1, count):
        area = int(stats[component_id, cv2.CC_STAT_AREA])
        centroid_x = float(centroids[component_id, 0])
        centroid_y = float(centroids[component_id, 1])
        if (
            area >= int(extraction["minimum_component_area_px"])
            and x_min <= centroid_x <= x_max
            and centroid_y >= float(extraction["minimum_centroid_y"])
        ):
            candidates.append(
                {
                    "area_px": area,
                    "centroid_xy": [centroid_x, centroid_y],
                }
            )
    if len(candidates) < 2:
        return None
    selected = sorted(
        sorted(
            candidates,
            key=lambda row: int(row["area_px"]),
            reverse=True,
        )[:2],
        key=lambda row: float(row["centroid_xy"][0]),
    )
    fixed, moving = selected
    aperture_px = float(moving["centroid_xy"][0]) - float(
        fixed["centroid_xy"][0]
    )
    if aperture_px <= 0.0:
        return None
    return {
        "fixed_pad": fixed,
        "moving_pad": moving,
        "moving_minus_fixed_centroid_x_px": aperture_px,
    }


def extract_preterminal_observations(
    contract: dict[str, Any], *, root: Path = REPO_ROOT
) -> tuple[list[dict[str, Any]], list[int]]:
    sources = contract["sources"]
    video_path = _bound_path(
        sources["wrist_video"], root=root, label="wrist video"
    )
    schedule = load_json_object(
        _bound_path(
            sources["schedule_receipt"],
            root=root,
            label="schedule receipt",
        ),
        label="OR40 schedule receipt",
    )
    samples = _load_jsonl(
        _bound_path(
            sources["raw_samples"], root=root, label="raw samples"
        ),
        label="OR40 raw samples",
    )
    frames = _decode_video(video_path)
    first_frame, last_frame = [
        int(value) for value in contract["extraction"]["frame_range_inclusive"]
    ]
    _require(last_frame < len(frames), "OR40 frame range exceeds video")
    bindings = _best_frame_bindings(
        schedule, first_frame=first_frame, last_frame=last_frame
    )
    sample_first, sample_last = [
        int(value)
        for value in contract["partition"][
            "mapping_sample_range_inclusive"
        ]
    ]
    observations: list[dict[str, Any]] = []
    abstained: list[int] = []
    for frame_index in range(first_frame, last_frame + 1):
        binding = bindings.get(frame_index)
        observation = _red_pad_observation(
            frames[frame_index], contract["extraction"]
        )
        if binding is None or observation is None:
            abstained.append(frame_index)
            continue
        sample_index = int(binding["sample_index"])
        if not sample_first <= sample_index <= sample_last:
            abstained.append(frame_index)
            continue
        sample = samples[sample_index]
        _require(
            int(sample["sample_index"]) == sample_index,
            "OR40 raw sample order changed",
        )
        observations.append(
            {
                "frame_index": frame_index,
                "sample_index": sample_index,
                "sample_time_seconds": float(
                    sample["timestamp_monotonic_seconds"]
                ),
                "association_error_ms": float(
                    binding["d405"]["association_error_ms"]
                ),
                "raw_gripper_degrees": float(
                    sample["follower_actual_position_degrees"][5]
                ),
                "split": (
                    "fit"
                    if (frame_index // 2) % 2 == 0
                    else "validation"
                ),
                **observation,
            }
        )
    return observations, abstained


def directional_play(raw: np.ndarray, half_width: float) -> np.ndarray:
    _require(raw.ndim == 1 and len(raw) > 0, "invalid play input")
    _require(half_width >= 0.0, "invalid play half width")
    surface = np.empty_like(raw, dtype=np.float64)
    surface[0] = float(raw[0])
    for index in range(1, len(raw)):
        value = float(raw[index])
        surface[index] = np.clip(
            surface[index - 1],
            value - half_width,
            value + half_width,
        )
    return surface


def _direction(
    query_time: float,
    times: np.ndarray,
    raw: np.ndarray,
    *,
    window: float,
    epsilon: float,
) -> str:
    before = float(np.interp(query_time - window, times, raw))
    after = float(np.interp(query_time + window, times, raw))
    delta = after - before
    if delta > epsilon:
        return "opening"
    if delta < -epsilon:
        return "closing"
    return "hold"


def _candidate_rows(
    observations: list[dict[str, Any]],
    *,
    times: np.ndarray,
    raw: np.ndarray,
    mapped: np.ndarray,
    lag_seconds: float,
    fit: dict[str, Any],
) -> list[dict[str, Any]]:
    result = []
    for row in observations:
        query_time = float(row["sample_time_seconds"]) + lag_seconds
        result.append(
            {
                **row,
                "query_time_seconds": query_time,
                "mapped_surface_raw_degrees": float(
                    np.interp(query_time, times, mapped)
                ),
                "direction": _direction(
                    query_time,
                    times,
                    raw,
                    window=float(fit["direction_window_seconds"]),
                    epsilon=float(fit["direction_epsilon_raw_degrees"]),
                ),
            }
        )
    return result


def _linear_fit(rows: list[dict[str, Any]]) -> dict[str, Any]:
    _require(len(rows) >= 2, "insufficient OR40 fit rows")
    design = np.asarray(
        [
            [1.0, float(row["mapped_surface_raw_degrees"])]
            for row in rows
        ],
        dtype=np.float64,
    )
    observed = np.asarray(
        [float(row["moving_minus_fixed_centroid_x_px"]) for row in rows],
        dtype=np.float64,
    )
    coefficients, _, rank, singular_values = np.linalg.lstsq(
        design, observed, rcond=None
    )
    predicted = design @ coefficients
    rms = float(np.sqrt(np.mean(np.square(observed - predicted))))
    return {
        "intercept_px": float(coefficients[0]),
        "scale_px_per_raw_degree": float(coefficients[1]),
        "rms_px": rms,
        "rank": int(rank),
        "singular_values": singular_values.tolist(),
    }


def _evaluate_rows(
    rows: list[dict[str, Any]], model: dict[str, Any]
) -> float:
    observed = np.asarray(
        [float(row["moving_minus_fixed_centroid_x_px"]) for row in rows],
        dtype=np.float64,
    )
    predicted = np.asarray(
        [
            float(model["intercept_px"])
            + float(model["scale_px_per_raw_degree"])
            * float(row["mapped_surface_raw_degrees"])
            for row in rows
        ],
        dtype=np.float64,
    )
    return float(np.sqrt(np.mean(np.square(observed - predicted))))


def _direction_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        name: sum(row["direction"] == name for row in rows)
        for name in ("opening", "closing", "hold")
    }


def _fit_candidate(
    contract: dict[str, Any],
    observations: list[dict[str, Any]],
    samples: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    times = np.asarray(
        [float(row["timestamp_monotonic_seconds"]) for row in samples],
        dtype=np.float64,
    )
    raw = np.asarray(
        [float(row["follower_actual_position_degrees"][5]) for row in samples],
        dtype=np.float64,
    )
    _require(
        len(raw) == int(contract["trajectory"]["row_count"])
        and np.all(np.diff(times) > 0.0),
        "OR40 raw trajectory shape or time ordering changed",
    )
    fit_config = contract["fit"]
    beta_min, beta_max = [
        float(value)
        for value in fit_config["play_half_width_bounds_raw_degrees"]
    ]
    lag_min, lag_max = [
        float(value) for value in fit_config["camera_lag_seconds_bounds"]
    ]
    profile: list[dict[str, Any]] = []
    best: dict[str, Any] | None = None
    fit_observations = [
        row for row in observations if row["split"] == "fit"
    ]
    for half_width in np.linspace(
        beta_min,
        beta_max,
        int(fit_config["play_half_width_grid_count"]),
    ):
        mapped = directional_play(raw, float(half_width))
        beta_best: dict[str, Any] | None = None
        for lag in np.linspace(
            lag_min,
            lag_max,
            int(fit_config["camera_lag_grid_count"]),
        ):
            rows = _candidate_rows(
                fit_observations,
                times=times,
                raw=raw,
                mapped=mapped,
                lag_seconds=float(lag),
                fit=fit_config,
            )
            model = _linear_fit(rows)
            candidate = {
                "play_half_width_raw_degrees": float(half_width),
                "camera_lag_seconds": float(lag),
                "model": model,
                "fit_direction_counts": _direction_counts(rows),
            }
            if beta_best is None or float(model["rms_px"]) < float(
                beta_best["model"]["rms_px"]
            ):
                beta_best = candidate
            if best is None or float(model["rms_px"]) < float(
                best["model"]["rms_px"]
            ):
                best = candidate
        _require(beta_best is not None, "OR40 beta profile is empty")
        profile.append(beta_best)
    _require(best is not None, "OR40 candidate search is empty")
    return best, profile


def _validation_report(
    contract: dict[str, Any],
    observations: list[dict[str, Any]],
    samples: list[dict[str, Any]],
    candidate: dict[str, Any],
    profile: list[dict[str, Any]],
) -> dict[str, Any]:
    times = np.asarray(
        [float(row["timestamp_monotonic_seconds"]) for row in samples],
        dtype=np.float64,
    )
    raw = np.asarray(
        [float(row["follower_actual_position_degrees"][5]) for row in samples],
        dtype=np.float64,
    )
    fit_config = contract["fit"]
    validation = [
        row for row in observations if row["split"] == "validation"
    ]
    candidate_rows = _candidate_rows(
        validation,
        times=times,
        raw=raw,
        mapped=directional_play(
            raw, float(candidate["play_half_width_raw_degrees"])
        ),
        lag_seconds=float(candidate["camera_lag_seconds"]),
        fit=fit_config,
    )
    candidate_rms = _evaluate_rows(candidate_rows, candidate["model"])
    null_profile = [
        row
        for row in profile
        if float(row["play_half_width_raw_degrees"]) == 0.0
    ]
    _require(len(null_profile) == 1, "OR40 zero-play profile missing")
    null = null_profile[0]
    null_rows = _candidate_rows(
        validation,
        times=times,
        raw=raw,
        mapped=directional_play(raw, 0.0),
        lag_seconds=float(null["camera_lag_seconds"]),
        fit=fit_config,
    )
    null_rms = _evaluate_rows(null_rows, null["model"])
    improvement = (
        1.0 - candidate_rms / null_rms if null_rms > 0.0 else float("-inf")
    )
    near = [
        row
        for row in profile
        if float(row["model"]["rms_px"])
        <= float(candidate["model"]["rms_px"]) * 1.05
    ]
    if len(near) >= 3:
        correlation = float(
            np.corrcoef(
                [
                    float(row["play_half_width_raw_degrees"])
                    for row in near
                ],
                [float(row["camera_lag_seconds"]) for row in near],
            )[0, 1]
        )
        if not np.isfinite(correlation):
            correlation = 1.0
    else:
        correlation = 1.0
    return {
        "candidate_validation_rms_px": candidate_rms,
        "zero_play_validation_rms_px": null_rms,
        "validation_improvement_over_zero_play_fraction": improvement,
        "validation_direction_counts": _direction_counts(candidate_rows),
        "play_lag_near_optimum_correlation": correlation,
        "candidate_rows": candidate_rows,
        "zero_play_candidate": null,
    }


def run_retained_video_jaw_surface_mapping_once(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    _require(not receipt_path.exists(), "OR40 one-run receipt already exists")
    contract = load_retained_video_jaw_surface_mapping_contract(
        contract_path, root=root
    )
    observations, abstained = extract_preterminal_observations(
        contract, root=root
    )
    samples = _load_jsonl(
        _bound_path(
            contract["sources"]["raw_samples"],
            root=root,
            label="raw samples",
        ),
        label="OR40 raw samples",
    )
    candidate, profile = _fit_candidate(contract, observations, samples)
    output_directory.mkdir(parents=True, exist_ok=False)
    extraction_path = output_directory / "preterminal_observations.json"
    atomic_write_json(
        extraction_path,
        {
            "observations": observations,
            "abstained_frame_indices": abstained,
        },
    )
    manifest = {
        "schema_version": "sim2claw.or40_candidate_manifest.v1",
        "experiment_id": contract["experiment_id"],
        "source_bindings": contract["sources"],
        "partition": contract["partition"],
        "extraction": contract["extraction"],
        "fit": contract["fit"],
        "candidate": candidate,
        "fit_frame_indices": [
            row["frame_index"]
            for row in observations
            if row["split"] == "fit"
        ],
        "validation_frame_indices_sealed": [
            row["frame_index"]
            for row in observations
            if row["split"] == "validation"
        ],
        "contact_holdout_samples_sealed": contract["partition"][
            "contact_holdout_sample_range_inclusive"
        ],
        "terminal_samples_sealed": contract["partition"][
            "terminal_sample_range_inclusive"
        ],
        "terminal_outcome_used_for_selection": False,
    }
    manifest["artifact_sha256"] = canonical_digest(manifest)
    manifest_path = output_directory / "candidate_manifest.json"
    atomic_write_json(manifest_path, manifest)

    validation = _validation_report(
        contract, observations, samples, candidate, profile
    )
    gates = contract["mapping_gates"]
    fit_counts = candidate["fit_direction_counts"]
    validation_counts = validation["validation_direction_counts"]
    beta_max = float(
        contract["fit"]["play_half_width_bounds_raw_degrees"][1]
    )
    beta = float(candidate["play_half_width_raw_degrees"])
    gate_report = {
        "minimum_extracted_frames": (
            len(observations) >= int(gates["minimum_extracted_frames"])
        ),
        "minimum_fit_opening_frames": (
            fit_counts["opening"]
            >= int(gates["minimum_fit_frames_per_direction"])
        ),
        "minimum_fit_closing_frames": (
            fit_counts["closing"]
            >= int(gates["minimum_fit_frames_per_direction"])
        ),
        "minimum_validation_opening_frames": (
            validation_counts["opening"]
            >= int(gates["minimum_validation_frames_per_direction"])
        ),
        "minimum_validation_closing_frames": (
            validation_counts["closing"]
            >= int(gates["minimum_validation_frames_per_direction"])
        ),
        "maximum_validation_rms": (
            validation["candidate_validation_rms_px"]
            <= float(gates["maximum_validation_rms_px"])
        ),
        "minimum_validation_improvement_over_zero_play": (
            validation["validation_improvement_over_zero_play_fraction"]
            >= float(
                gates[
                    "minimum_validation_improvement_over_zero_play_fraction"
                ]
            )
        ),
        "maximum_play_lag_correlation": (
            abs(validation["play_lag_near_optimum_correlation"])
            <= float(gates["maximum_play_lag_correlation"])
        ),
        "minimum_upper_bound_margin": (
            beta
            <= beta_max
            * (1.0 - float(gates["minimum_upper_bound_margin_fraction"]))
        ),
    }
    mapping_pass = all(gate_report.values())
    visual_pass = gate_report["minimum_extracted_frames"]
    direction_pass = all(
        gate_report[name]
        for name in (
            "minimum_fit_opening_frames",
            "minimum_fit_closing_frames",
            "minimum_validation_opening_frames",
            "minimum_validation_closing_frames",
        )
    )
    if not visual_pass:
        status = contract["verdicts"]["insufficient_visual_observability"]
    elif not direction_pass:
        status = contract["verdicts"][
            "directional_excitation_or_rank_failure"
        ]
    elif not gate_report["maximum_play_lag_correlation"]:
        status = contract["verdicts"]["timing_confound"]
    elif not mapping_pass:
        status = contract["verdicts"]["validation_or_bound_failure"]
    else:
        raise FactoryArtifactError(
            "OR40 mapping unexpectedly passed; the separately frozen single "
            "dynamic replay seam must be compiled before opening validation"
        )
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "proof_class": contract["proof_class"],
        "status": status,
        "source_bindings": contract["sources"],
        "candidate_manifest": {
            "path": manifest_path.name,
            "artifact_sha256": manifest["artifact_sha256"],
        },
        "preterminal_observations": {
            "path": extraction_path.name,
            "accepted_frame_count": len(observations),
            "accepted_frame_indices": [
                row["frame_index"] for row in observations
            ],
            "abstained_frame_indices": abstained,
        },
        "candidate": candidate,
        "profile": profile,
        "validation": validation,
        "mapping_gate_report": gate_report,
        "mapping_gate_passed": mapping_pass,
        "dynamic_replays_run": 0,
        "dynamic_replay_permitted": False,
        "raw_measured_row_count": len(samples),
        "raw_measured_values_order_or_timestamps_changed": False,
        "contact_or_terminal_samples_used_for_fit_or_selection": False,
        "metric_aperture_claim": False,
        "camera_calibration_claim": False,
        "force_stiffness_or_compliance_claim": False,
        "global_mapping_approved": False,
        "simulator_promoted": False,
        "transfer_claim": False,
        "authority": contract["authority"],
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


def main() -> int:
    run_retained_video_jaw_surface_mapping_once()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
