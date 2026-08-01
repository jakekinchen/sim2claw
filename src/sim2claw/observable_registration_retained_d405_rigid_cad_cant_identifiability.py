"""Fail-closed retained-RGB rigid-jaw cant identifiability screen."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
)
from .observable_registration_belief_recalculation import REPO_ROOT, _bound_path
from .observable_registration_retained_video_jaw_surface_mapping import (
    _direction,
    _load_jsonl,
)


SCHEMA = (
    "sim2claw.observable_registration_retained_d405_"
    "rigid_cad_cant_identifiability_contract.v1"
)
RECEIPT_SCHEMA = (
    "sim2claw.observable_registration_retained_d405_"
    "rigid_cad_cant_identifiability_receipt.v1"
)
PARTITION_SCHEMA = "sim2claw.or46_derived_observable_partition.v1"
CONTRACT_PATH = (
    REPO_ROOT
    / "configs/evaluations/"
    "observable_registration_retained_d405_rigid_cad_cant_identifiability_v1.json"
)
OUTPUT_DIRECTORY = (
    REPO_ROOT
    / "outputs/"
    "observable_registration_retained_d405_rigid_cad_cant_identifiability_v1"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def load_retained_d405_rigid_cad_cant_identifiability_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="OR46 retained RGB CAD screen")
    _require(contract.get("schema_version") == SCHEMA, "unsupported OR46 contract")
    for source_id, binding in contract["sources"].items():
        _bound_path(binding, root=root, label=source_id)
    corpus = contract["retained_corpus"]
    _require(
        corpus["accepted_frame_indices_inclusive"] == [64, 88]
        and corpus["accepted_frame_count"] == 25
        and corpus["contact_holdout_sample_range_inclusive"] == [228, 260]
        and corpus["terminal_sample_range_inclusive"] == [261, 530]
        and corpus[
            "contact_terminal_pawn_outcome_or_or36s_dynamic_result_allowed"
        ]
        is False,
        "OR46 retained-corpus boundary widened",
    )
    split = contract["derived_observable_split"]
    _require(
        split["gripper_value_equal_population_bins"] == 5
        and split["fit_and_jacobian_folds"] == [0, 1, 2]
        and split["no_refit_validation_fold"] == 3
        and split["derived_observable_stress_fold"] == 4
        and split["or41_role"] == "external_reject_only_never_fit_or_select",
        "OR46 split changed",
    )
    observables = contract["positive_observables"]
    _require(
        observables["red_mask_may_be_positive_cad_target"] is False
        and observables["pca_component_angle_allowed"] is False,
        "OR46 positive target widened to the unmodeled red boot",
    )
    model = contract["diagnostic_model"]
    _require(
        model["target"] == "one_axis_moving_rigid_jaw_body_cant_degrees"
        and model["target_bounds_degrees"] == [-15.0, 15.0]
        and model["candidate_parameter_emission_allowed"] is False
        and model["contact_surface_cant_claim_allowed"] is False,
        "OR46 diagnostic target or output widened",
    )
    _require(
        not any(contract["claim_limits"].values())
        and not any(contract["authority"].values()),
        "OR46 claim or authority boundary widened",
    )
    return contract


def _equal_population_bins(values: np.ndarray, count: int) -> np.ndarray:
    _require(values.ndim == 1 and len(values) >= count, "invalid OR46 bin input")
    order = np.argsort(values, kind="stable")
    result = np.empty(len(values), dtype=np.int64)
    for rank, observation_index in enumerate(order):
        result[observation_index] = min(count - 1, rank * count // len(values))
    return result


def derive_observable_partition(
    contract: dict[str, Any], *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    observations_payload = load_json_object(
        _bound_path(
            contract["sources"]["or40_preterminal_observations"],
            root=root,
            label="OR40 preterminal observations",
        ),
        label="OR40 preterminal observations",
    )
    observations = observations_payload.get("observations")
    _require(isinstance(observations, list), "OR40 observations missing")
    expected_first, expected_last = contract["retained_corpus"][
        "accepted_frame_indices_inclusive"
    ]
    frame_indices = [int(row["frame_index"]) for row in observations]
    _require(
        frame_indices == list(range(expected_first, expected_last + 1))
        and len(observations)
        == int(contract["retained_corpus"]["accepted_frame_count"]),
        "OR46 accepted retained frame identity changed",
    )
    samples = _load_jsonl(
        _bound_path(
            contract["sources"]["raw_samples"], root=root, label="raw samples"
        ),
        label="OR46 raw samples",
    )
    sample_times = np.asarray(
        [row["timestamp_monotonic_seconds"] for row in samples], dtype=np.float64
    )
    gripper_trace = np.asarray(
        [row["follower_actual_position_degrees"][5] for row in samples],
        dtype=np.float64,
    )
    split = contract["derived_observable_split"]
    directions = [
        _direction(
            float(row["sample_time_seconds"]),
            sample_times,
            gripper_trace,
            window=float(split["direction_window_seconds"]),
            epsilon=float(split["direction_epsilon_raw_degrees"]),
        )
        for row in observations
    ]
    values = np.asarray(
        [row["raw_gripper_degrees"] for row in observations], dtype=np.float64
    )
    bins = _equal_population_bins(
        values, int(split["gripper_value_equal_population_bins"])
    )
    strata: dict[tuple[str, int], list[int]] = defaultdict(list)
    for observation_index, (direction, value_bin) in enumerate(
        zip(directions, bins, strict=True)
    ):
        strata[(direction, int(value_bin))].append(observation_index)
    folds = [-1] * len(observations)
    for indices in strata.values():
        for within_stratum_index, observation_index in enumerate(
            sorted(indices, key=lambda index: frame_indices[index])
        ):
            folds[observation_index] = within_stratum_index % 5
    rows = [
        {
            "frame_index": frame_indices[index],
            "sample_index": int(observation["sample_index"]),
            "raw_gripper_degrees": float(values[index]),
            "direction": directions[index],
            "gripper_value_bin": int(bins[index]),
            "fold": int(folds[index]),
        }
        for index, observation in enumerate(observations)
    ]
    fold_reports: dict[str, Any] = {}
    for fold in range(5):
        fold_rows = [row for row in rows if row["fold"] == fold]
        fold_reports[str(fold)] = {
            "frame_count": len(fold_rows),
            "frame_indices": [row["frame_index"] for row in fold_rows],
            "direction_counts": dict(
                sorted(Counter(row["direction"] for row in fold_rows).items())
            ),
            "distinct_raw_gripper_values": len(
                {row["raw_gripper_degrees"] for row in fold_rows}
            ),
        }
    partition = {
        "schema_version": PARTITION_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "rule": contract["derived_observable_split"],
        "rows": rows,
        "fold_reports": fold_reports,
        "direction_counts": dict(sorted(Counter(directions).items())),
        "stratum_counts": {
            f"{direction}:bin_{value_bin}": len(indices)
            for (direction, value_bin), indices in sorted(strata.items())
        },
        "source_outcomes_used": False,
    }
    partition["artifact_sha256"] = canonical_digest(partition)
    return partition


def _prerender_gate_report(
    contract: dict[str, Any], partition: dict[str, Any]
) -> dict[str, bool]:
    gates = contract["prerender_gates"]
    reports = partition["fold_reports"]
    fit_count = sum(reports[str(fold)]["frame_count"] for fold in (0, 1, 2))
    validation_counts = reports["3"]["direction_counts"]
    stress_counts = reports["4"]["direction_counts"]
    validation_stress_rows = [
        row for row in partition["rows"] if row["fold"] in (3, 4)
    ]
    return {
        "minimum_fit_frames": fit_count >= int(gates["minimum_fit_frames"]),
        "validation_has_opening": validation_counts.get("opening", 0) >= 1,
        "validation_has_closing": validation_counts.get("closing", 0) >= 1,
        "stress_has_opening": stress_counts.get("opening", 0) >= 1,
        "stress_has_closing": stress_counts.get("closing", 0) >= 1,
        "joint_validation_stress_distinct_gripper_values": len(
            {row["raw_gripper_degrees"] for row in validation_stress_rows}
        )
        >= int(gates["minimum_joint_validation_stress_distinct_gripper_values"]),
    }


def run_retained_d405_rigid_cad_cant_identifiability_once(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
) -> dict[str, Any]:
    contract = load_retained_d405_rigid_cad_cant_identifiability_contract(
        contract_path
    )
    output_directory.mkdir(parents=True, exist_ok=False)
    partition = derive_observable_partition(contract)
    partition_path = output_directory / "derived_observable_partition.json"
    atomic_write_json(partition_path, partition)
    gate_report = _prerender_gate_report(contract, partition)
    prerender_pass = all(gate_report.values())
    _require(
        not prerender_pass,
        "OR46 preregistered prerender gates unexpectedly passed; CAD rendering "
        "must be implemented and separately reviewed before optimization",
    )
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "proof_class": contract["proof_class"],
        "status": contract["verdicts"]["prerender_split_failure"],
        "source_bindings": contract["sources"],
        "derived_observable_partition": {
            "path": partition_path.name,
            "artifact_sha256": partition["artifact_sha256"],
        },
        "prerender_gate_report": gate_report,
        "prerender_gates_passed": False,
        "failed_before_cad_render": True,
        "failed_before_optimization": True,
        "cad_renders_run": 0,
        "optimizer_runs": 0,
        "candidate_parameter_emitted": False,
        "simulator_replays_run": 0,
        "simulator_replay_permitted": False,
        "contact_surface_cant_identified": False,
        "raw_measured_values_order_or_timestamps_changed": False,
        "contact_terminal_pawn_outcome_or_or36s_dynamic_result_used": False,
        "global_mapping_approved": False,
        "simulator_promoted": False,
        "physical_task_attempt": False,
        "transfer_claim": False,
        "next_boundary": "TERMINAL_EXTERNAL_METRIC_PAD_OBSERVATION_REQUIRED",
        "authority": contract["authority"],
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(output_directory / "receipt.json", receipt)
    return receipt


def main() -> int:
    run_retained_d405_rigid_cad_cant_identifiability_once()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
