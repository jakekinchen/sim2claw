"""Cross-episode retained gripper-cycle mapping with no dynamic replay."""

from __future__ import annotations

from pathlib import Path
from typing import Any

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
from .observable_registration_retained_video_jaw_surface_mapping import (
    _decode_video,
    _direction,
    _evaluate_rows,
    _linear_fit,
    _load_jsonl,
    _red_pad_observation,
    directional_play,
)


SCHEMA = (
    "sim2claw."
    "observable_registration_retained_full_range_gripper_mapping_contract.v1"
)
RECEIPT_SCHEMA = (
    "sim2claw."
    "observable_registration_retained_full_range_gripper_mapping_receipt.v1"
)
CONTRACT_PATH = (
    REPO_ROOT
    / "configs/evaluations/"
    "observable_registration_retained_full_range_gripper_mapping_v1.json"
)
OUTPUT_DIRECTORY = (
    REPO_ROOT
    / "outputs/"
    "observable_registration_retained_full_range_gripper_mapping_v1"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def load_retained_full_range_gripper_mapping_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="OR41 retained gripper mapping")
    _require(contract.get("schema_version") == SCHEMA, "unsupported contract")
    for source_id, binding in contract["sources"].items():
        _bound_path(binding, root=root, label=source_id)
    audit = contract["source_audit"]
    _require(
        audit["raw_row_count"] == 2401
        and audit["wrist_frame_count"] == 642
        and audit["gripper_cycle_sample_range_inclusive"] == [430, 546]
        and audit["physical_object_contact_allowed_in_fit"] is False
        and audit["terminal_task_outcome_available_to_fit_or_selection"]
        is False,
        "OR41 source audit widened",
    )
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
        "OR41 estimand widened",
    )
    partition = contract["partition"]
    _require(
        partition["opening_and_closing_partitioned_separately"] is True
        and partition["hold_rows_abstain_from_fit_and_validation"] is True
        and partition["or40_task_clip_is_cross_episode_no_refit_validation"]
        is True
        and partition["candidate_manifest_written_before_any_validation"]
        is True
        and partition["validation_refit_allowed"] is False,
        "OR41 partition widened",
    )
    replay = contract["replay"]
    _require(
        replay["dynamic_replay_allowed"] is False
        and replay[
            "successful_mapping_requires_separate_prospective_replay_successor"
        ]
        is True
        and replay["object_pose_injection_allowed"] is False
        and replay["latch_or_grasp_mode_allowed"] is False
        and replay["terminal_refit_allowed"] is False,
        "OR41 replay boundary widened",
    )
    _require(
        not any(contract["claim_limits"].values()),
        "OR41 claim boundary widened",
    )
    _require(
        not any(contract["authority"].values()),
        "OR41 authority boundary widened",
    )
    return contract


def _d405_frame_callbacks(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    callbacks = [
        row
        for row in rows
        if row.get("role") == "d405"
        and row.get("appended_to_writer") is True
        and row.get("warmup_excluded") is False
    ]
    _require(bool(callbacks), "OR41 has no admitted D405 callbacks")
    return callbacks


def _nearest_sample(
    samples: list[dict[str, Any]], callback_seconds: float
) -> tuple[dict[str, Any], float]:
    differences = np.asarray(
        [
            abs(
                float(
                    row["observability_timestamps"][
                        "sample_started_monotonic_seconds"
                    ]
                )
                - callback_seconds
            )
            for row in samples
        ],
        dtype=np.float64,
    )
    index = int(np.argmin(differences))
    return samples[index], float(differences[index] * 1000.0)


def extract_full_range_gripper_observations(
    contract: dict[str, Any], *, root: Path = REPO_ROOT
) -> tuple[list[dict[str, Any]], list[int]]:
    sources = contract["sources"]
    samples = _load_jsonl(
        _bound_path(
            sources["full_range_samples"],
            root=root,
            label="full-range samples",
        ),
        label="OR41 full-range samples",
    )
    callbacks = _d405_frame_callbacks(
        _load_jsonl(
            _bound_path(
                sources["full_range_callback_timestamps"],
                root=root,
                label="full-range callbacks",
            ),
            label="OR41 callback timestamps",
        )
    )
    frames = _decode_video(
        _bound_path(
            sources["full_range_wrist_video"],
            root=root,
            label="full-range wrist video",
        )
    )
    _require(
        len(samples) == int(contract["source_audit"]["raw_row_count"])
        and len(frames) == int(contract["source_audit"]["wrist_frame_count"])
        and len(callbacks) == len(frames),
        "OR41 retained source counts changed",
    )
    first_frame, last_frame = [
        int(value)
        for value in contract["association"]["frame_range_inclusive"]
    ]
    first_sample, last_sample = [
        int(value)
        for value in contract["source_audit"][
            "gripper_cycle_sample_range_inclusive"
        ]
    ]
    maximum_error = float(
        contract["association"]["maximum_association_error_ms"]
    )
    partition = contract["partition"]
    observations: list[dict[str, Any]] = []
    abstained: list[int] = []
    for frame_index in range(first_frame, last_frame + 1):
        sample, association_error_ms = _nearest_sample(
            samples, float(callbacks[frame_index]["host_continuous_ns"]) / 1e9
        )
        sample_index = int(sample["sample_index"])
        pad = _red_pad_observation(
            frames[frame_index], contract["extraction"]
        )
        if (
            pad is None
            or association_error_ms > maximum_error
            or not first_sample <= sample_index <= last_sample
        ):
            abstained.append(frame_index)
            continue
        sample_time = float(sample["timestamp_monotonic_seconds"])
        raw = np.asarray(
            [
                float(row["follower_actual_position_degrees"][5])
                for row in samples
            ],
            dtype=np.float64,
        )
        times = np.asarray(
            [float(row["timestamp_monotonic_seconds"]) for row in samples],
            dtype=np.float64,
        )
        direction = _direction(
            sample_time,
            times,
            raw,
            window=float(partition["direction_label_window_seconds"]),
            epsilon=float(partition["direction_epsilon_raw_degrees"]),
        )
        observations.append(
            {
                "frame_index": frame_index,
                "sample_index": sample_index,
                "sample_time_seconds": sample_time,
                "association_error_ms": association_error_ms,
                "raw_gripper_degrees": float(
                    sample["follower_actual_position_degrees"][5]
                ),
                "direction": direction,
                **pad,
            }
        )
    for direction in ("opening", "closing"):
        members = [
            row for row in observations if row["direction"] == direction
        ]
        for direction_index, row in enumerate(members):
            row["direction_row_index"] = direction_index
            row["split"] = (
                "fit" if direction_index % 2 == 0 else "validation"
            )
    for row in observations:
        if row["direction"] == "hold":
            row["direction_row_index"] = None
            row["split"] = "abstain_hold"
    return observations, abstained


def _mapped_rows(
    observations: list[dict[str, Any]],
    *,
    times: np.ndarray,
    raw: np.ndarray,
    half_width: float,
    lag_seconds: float,
) -> list[dict[str, Any]]:
    mapped = directional_play(raw, half_width)
    return [
        {
            **row,
            "query_time_seconds": float(row["sample_time_seconds"])
            + lag_seconds,
            "mapped_surface_raw_degrees": float(
                np.interp(
                    float(row["sample_time_seconds"]) + lag_seconds,
                    times,
                    mapped,
                )
            ),
        }
        for row in observations
    ]


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
    fit_rows = [row for row in observations if row["split"] == "fit"]
    fit = contract["fit"]
    beta_min, beta_max = [
        float(value) for value in fit["play_half_width_bounds_raw_degrees"]
    ]
    lag_min, lag_max = [
        float(value) for value in fit["camera_lag_seconds_bounds"]
    ]
    best: dict[str, Any] | None = None
    profile: list[dict[str, Any]] = []
    for half_width in np.linspace(
        beta_min, beta_max, int(fit["play_half_width_grid_count"])
    ):
        beta_best: dict[str, Any] | None = None
        for lag in np.linspace(
            lag_min, lag_max, int(fit["camera_lag_grid_count"])
        ):
            rows = _mapped_rows(
                fit_rows,
                times=times,
                raw=raw,
                half_width=float(half_width),
                lag_seconds=float(lag),
            )
            model = _linear_fit(rows)
            candidate = {
                "play_half_width_raw_degrees": float(half_width),
                "camera_lag_seconds": float(lag),
                "model": model,
            }
            if beta_best is None or float(model["rms_px"]) < float(
                beta_best["model"]["rms_px"]
            ):
                beta_best = candidate
            if best is None or float(model["rms_px"]) < float(
                best["model"]["rms_px"]
            ):
                best = candidate
        _require(beta_best is not None, "OR41 beta profile is empty")
        profile.append(beta_best)
    _require(best is not None, "OR41 candidate profile is empty")
    return best, profile


def _direction_counts(
    rows: list[dict[str, Any]], *, split: str
) -> dict[str, int]:
    return {
        direction: sum(
            row["direction"] == direction and row["split"] == split
            for row in rows
        )
        for direction in ("opening", "closing")
    }


def _validation_metrics(
    observations: list[dict[str, Any]],
    samples: list[dict[str, Any]],
    *,
    candidate: dict[str, Any],
    null: dict[str, Any],
) -> dict[str, Any]:
    times = np.asarray(
        [float(row["timestamp_monotonic_seconds"]) for row in samples],
        dtype=np.float64,
    )
    raw = np.asarray(
        [float(row["follower_actual_position_degrees"][5]) for row in samples],
        dtype=np.float64,
    )
    validation = [
        row for row in observations if row["split"] == "validation"
    ]
    candidate_rows = _mapped_rows(
        validation,
        times=times,
        raw=raw,
        half_width=float(candidate["play_half_width_raw_degrees"]),
        lag_seconds=float(candidate["camera_lag_seconds"]),
    )
    null_rows = _mapped_rows(
        validation,
        times=times,
        raw=raw,
        half_width=0.0,
        lag_seconds=float(null["camera_lag_seconds"]),
    )
    candidate_rms = _evaluate_rows(candidate_rows, candidate["model"])
    null_rms = _evaluate_rows(null_rows, null["model"])
    return {
        "candidate_rms_px": candidate_rms,
        "zero_play_rms_px": null_rms,
        "improvement_over_zero_play_fraction": (
            1.0 - candidate_rms / null_rms
            if null_rms > 0.0
            else float("-inf")
        ),
        "candidate_rows": candidate_rows,
    }


def _or40_validation_metrics(
    contract: dict[str, Any],
    *,
    candidate: dict[str, Any],
    null: dict[str, Any],
    root: Path,
) -> dict[str, Any]:
    sources = contract["sources"]
    task_observations = load_json_object(
        _bound_path(
            sources["or40_preterminal_observations"],
            root=root,
            label="OR40 observations",
        ),
        label="OR40 observations",
    )["observations"]
    task_samples = _load_jsonl(
        _bound_path(
            sources["or40_raw_samples"],
            root=root,
            label="OR40 raw samples",
        ),
        label="OR40 raw samples",
    )
    times = np.asarray(
        [float(row["timestamp_monotonic_seconds"]) for row in task_samples],
        dtype=np.float64,
    )
    raw = np.asarray(
        [
            float(row["follower_actual_position_degrees"][5])
            for row in task_samples
        ],
        dtype=np.float64,
    )
    candidate_rows = _mapped_rows(
        task_observations,
        times=times,
        raw=raw,
        half_width=float(candidate["play_half_width_raw_degrees"]),
        lag_seconds=float(candidate["camera_lag_seconds"]),
    )
    null_rows = _mapped_rows(
        task_observations,
        times=times,
        raw=raw,
        half_width=0.0,
        lag_seconds=float(null["camera_lag_seconds"]),
    )
    candidate_rms = _evaluate_rows(candidate_rows, candidate["model"])
    null_rms = _evaluate_rows(null_rows, null["model"])
    return {
        "candidate_rms_px": candidate_rms,
        "zero_play_rms_px": null_rms,
        "improvement_over_zero_play_fraction": (
            1.0 - candidate_rms / null_rms
            if null_rms > 0.0
            else float("-inf")
        ),
        "frame_count": len(candidate_rows),
    }


def run_retained_full_range_gripper_mapping_once(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    _require(not receipt_path.exists(), "OR41 one-run receipt already exists")
    contract = load_retained_full_range_gripper_mapping_contract(
        contract_path, root=root
    )
    observations, abstained = extract_full_range_gripper_observations(
        contract, root=root
    )
    samples = _load_jsonl(
        _bound_path(
            contract["sources"]["full_range_samples"],
            root=root,
            label="full-range samples",
        ),
        label="OR41 full-range samples",
    )
    candidate, profile = _fit_candidate(contract, observations, samples)
    null_candidates = [
        row
        for row in profile
        if float(row["play_half_width_raw_degrees"]) == 0.0
    ]
    _require(len(null_candidates) == 1, "OR41 zero-play profile missing")
    null = null_candidates[0]
    output_directory.mkdir(parents=True, exist_ok=False)
    observations_path = output_directory / "observations.json"
    atomic_write_json(
        observations_path,
        {
            "observations": observations,
            "abstained_frame_indices": abstained,
        },
    )
    manifest = {
        "schema_version": "sim2claw.or41_candidate_manifest.v1",
        "experiment_id": contract["experiment_id"],
        "source_bindings": contract["sources"],
        "source_audit": contract["source_audit"],
        "association": contract["association"],
        "extraction": contract["extraction"],
        "partition": contract["partition"],
        "fit": contract["fit"],
        "candidate": candidate,
        "fit_frame_indices": [
            row["frame_index"]
            for row in observations
            if row["split"] == "fit"
        ],
        "internal_validation_frame_indices_sealed": [
            row["frame_index"]
            for row in observations
            if row["split"] == "validation"
        ],
        "or40_task_clip_validation_sealed": True,
        "terminal_task_outcome_used_for_selection": False,
    }
    manifest["artifact_sha256"] = canonical_digest(manifest)
    manifest_path = output_directory / "candidate_manifest.json"
    atomic_write_json(manifest_path, manifest)

    internal = _validation_metrics(
        observations, samples, candidate=candidate, null=null
    )
    task = _or40_validation_metrics(
        contract, candidate=candidate, null=null, root=root
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
    gates = contract["gates"]
    fit_counts = _direction_counts(observations, split="fit")
    validation_counts = _direction_counts(
        observations, split="validation"
    )
    beta = float(candidate["play_half_width_raw_degrees"])
    beta_max = float(
        contract["fit"]["play_half_width_bounds_raw_degrees"][1]
    )
    gate_report = {
        "minimum_fit_opening_frames": fit_counts["opening"]
        >= int(gates["minimum_fit_frames_per_direction"]),
        "minimum_fit_closing_frames": fit_counts["closing"]
        >= int(gates["minimum_fit_frames_per_direction"]),
        "minimum_validation_opening_frames": validation_counts["opening"]
        >= int(gates["minimum_internal_validation_frames_per_direction"]),
        "minimum_validation_closing_frames": validation_counts["closing"]
        >= int(gates["minimum_internal_validation_frames_per_direction"]),
        "maximum_internal_validation_rms": internal["candidate_rms_px"]
        <= float(gates["maximum_internal_validation_rms_px"]),
        "minimum_internal_validation_improvement": internal[
            "improvement_over_zero_play_fraction"
        ]
        >= float(
            gates[
                "minimum_internal_validation_improvement_over_zero_play_fraction"
            ]
        ),
        "maximum_play_lag_correlation": abs(correlation)
        <= float(gates["maximum_play_lag_correlation"]),
        "minimum_upper_bound_margin": beta
        <= beta_max
        * (1.0 - float(gates["minimum_upper_bound_margin_fraction"])),
        "maximum_or40_task_clip_validation_rms": task["candidate_rms_px"]
        <= float(gates["maximum_or40_task_clip_validation_rms_px"]),
        "minimum_or40_task_clip_improvement": task[
            "improvement_over_zero_play_fraction"
        ]
        >= float(
            gates[
                "minimum_or40_task_clip_improvement_over_zero_play_fraction"
            ]
        ),
    }
    mapping_pass = all(gate_report.values())
    status = (
        "PASS_RETAINED_CROSS_EPISODE_DIRECTIONAL_PLAY_MAPPING"
        if mapping_pass
        else "TERMINAL_NEGATIVE_RETAINED_CROSS_EPISODE_DIRECTIONAL_PLAY"
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
        "observations": {
            "path": observations_path.name,
            "accepted_frame_count": len(observations),
            "abstained_frame_indices": abstained,
            "fit_direction_counts": fit_counts,
            "validation_direction_counts": validation_counts,
        },
        "candidate": candidate,
        "profile": profile,
        "internal_validation": internal,
        "or40_task_clip_no_refit_validation": task,
        "play_lag_near_optimum_correlation": correlation,
        "mapping_gate_report": gate_report,
        "mapping_gate_passed": mapping_pass,
        "dynamic_replays_run": 0,
        "raw_measured_values_order_or_timestamps_changed": False,
        "terminal_task_outcome_used_for_fit_or_selection": False,
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
    run_retained_full_range_gripper_mapping_once()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
