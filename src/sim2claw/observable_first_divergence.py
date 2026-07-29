"""Localize physical/simulator divergence on an immutable source time base."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
    sha256_file,
)
from .paths import REPO_ROOT


SCHEMA = "sim2claw.observable_first_contact_divergence_contract.v1"
RECEIPT_SCHEMA = "sim2claw.observable_first_contact_divergence_receipt.v1"
CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "observable_first_contact_divergence_v1.json"
)
OUTPUT_PATH = (
    REPO_ROOT
    / "outputs"
    / "observable_first_contact_divergence_v1"
    / "receipt.json"
)
JOINT_NAMES = [
    "shoulder_pan",
    "shoulder_lift",
    "elbow_flex",
    "wrist_flex",
    "wrist_roll",
    "gripper",
]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def _bound_path(
    binding: dict[str, Any], *, root: Path, label: str
) -> Path:
    path = root / str(binding.get("path", ""))
    expected = str(binding.get("sha256", ""))
    _require(path.is_file(), f"{label} source is missing")
    _require(
        len(expected) == 64 and sha256_file(path) == expected,
        f"{label} hash drifted",
    )
    return path


def _bound_json(
    binding: dict[str, Any], *, root: Path, label: str
) -> dict[str, Any]:
    return load_json_object(
        _bound_path(binding, root=root, label=label), label=label
    )


def _load_jsonl(path: Path, *, label: str) -> list[dict[str, Any]]:
    try:
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as error:
        raise FactoryArtifactError(f"cannot read {label}: {error}") from error
    _require(rows and all(isinstance(row, dict) for row in rows), f"{label} is empty")
    return rows


def load_divergence_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="observable first divergence")
    _require(contract.get("schema_version") == SCHEMA, "unsupported divergence schema")
    sources = contract.get("sources")
    _require(isinstance(sources, dict) and sources, "divergence sources are missing")
    for source_id, binding in sources.items():
        _require(isinstance(binding, dict), f"invalid divergence source: {source_id}")
        _bound_path(binding, root=root, label=source_id)
    causal = contract.get("causal_policy")
    _require(
        isinstance(causal, dict)
        and causal.get("ordered_channels")
        == [
            "action_identity",
            "actuator_state",
            "jaw_projection_and_aperture",
            "selected_jaw_contact",
            "object_motion",
            "outcome",
        ]
        and causal.get("contact_material_may_be_primary_without_simulator_contact")
        is False
        and causal.get("actuator_timing_may_be_primary_when_enclosure_joint_gate_passes")
        is False
        and causal.get("mechanism_parameters_may_be_fit_in_or4") is False
        and causal.get("simulator_may_run_in_or4") is False,
        "divergence causal policy widened",
    )
    boundaries = contract.get("proof_boundaries")
    authority = contract.get("authority")
    _require(
        isinstance(boundaries, dict) and boundaries and not any(boundaries.values()),
        "divergence proof boundary widened",
    )
    _require(
        isinstance(authority, dict) and authority and not any(authority.values()),
        "divergence authority widened",
    )
    return contract


def joint_residual(
    physical_measured_degrees: list[float],
    simulator_applied_physical_degrees: list[float],
) -> dict[str, Any]:
    physical = np.asarray(physical_measured_degrees, dtype=np.float64)
    simulator = np.asarray(simulator_applied_physical_degrees, dtype=np.float64)
    _require(
        physical.shape == simulator.shape == (6,),
        "joint residual shape changed",
    )
    delta = simulator - physical
    return {
        "simulator_minus_physical_degrees": {
            name: float(value) for name, value in zip(JOINT_NAMES, delta, strict=True)
        },
        "all_joint_rms_degrees": float(np.sqrt(np.mean(delta**2))),
        "gripper_absolute_error_degrees": float(abs(delta[-1])),
    }


def evaluate_divergence(
    contract: dict[str, Any], *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    sources = contract["sources"]
    physical = _bound_json(
        sources["or3_receipt"], root=root, label="OR3 receipt"
    )
    c6 = _bound_json(sources["c6_receipt"], root=root, label="C6 receipt")
    trace = _bound_json(sources["c6_trace"], root=root, label="C6 trace")
    or2 = _bound_json(sources["or2_receipt"], root=root, label="OR2 receipt")
    or0 = _bound_json(sources["or0_receipt"], root=root, label="OR0 receipt")
    samples = _load_jsonl(
        _bound_path(
            sources["physical_samples"], root=root, label="physical samples"
        ),
        label="physical samples",
    )
    expected = contract["expected"]
    count = int(expected["row_count"])
    trace_rows = trace["rows"]
    _require(
        len(samples) == len(trace_rows) == count
        and [int(row["sample_index"]) for row in samples] == list(range(count))
        and [int(row["sample_index"]) for row in trace_rows] == list(range(count)),
        "physical/simulator row identity changed",
    )
    timestamp_errors = np.asarray(
        [
            abs(
                float(sample["timestamp_monotonic_seconds"])
                - float(simulator["source_timestamp_seconds"])
            )
            for sample, simulator in zip(samples, trace_rows, strict=True)
        ],
        dtype=np.float64,
    )
    max_timestamp_error = float(np.max(timestamp_errors))
    action_identity = {
        "requested": (
            or0["sealed_episode"]["requested_float32_sha256"]
            == c6["source_identity"]["requested_sha256"]
        ),
        "gateway_sent": (
            or0["sealed_episode"]["gateway_sent_float32_sha256"]
            == c6["source_identity"]["gateway_sent_sha256"]
        ),
        "timestamps": (
            or0["sealed_episode"]["timestamps_float64_sha256"]
            == c6["source_identity"]["timestamps_sha256"]
        ),
        "row_order": c6["source_identity"]["row_order_preserved"] is True,
    }
    event_samples = sorted(
        {
            int(expected["physical_last_separate_sample"]),
            *[
                int(value)
                for value in expected[
                    "physical_candidate_contact_interval_samples"
                ]
            ],
            int(expected["physical_first_definite_enclosure_sample"]),
            int(expected["physical_first_definite_carried_motion_sample"]),
            int(expected["physical_last_definite_carried_motion_sample"]),
            *[
                int(value)
                for value in expected[
                    "physical_candidate_release_interval_samples"
                ]
            ],
        }
    )
    initial_pawn = np.asarray(
        trace_rows[0]["selected_pawn_position_m"], dtype=np.float64
    )
    aligned_rows = []
    for sample_index in event_samples:
        sample = samples[sample_index]
        simulator = trace_rows[sample_index]
        pawn = np.asarray(
            simulator["selected_pawn_position_m"], dtype=np.float64
        )
        aligned_rows.append(
            {
                "sample_index": sample_index,
                "timestamp_seconds": float(
                    sample["timestamp_monotonic_seconds"]
                ),
                "joint_residual": joint_residual(
                    sample["follower_actual_position_degrees"],
                    simulator["plant_applied_physical"],
                ),
                "simulator_selected_jaw_contact_count": int(
                    simulator["selected_jaw_contact_count"]
                ),
                "simulator_pawn_planar_displacement_m": float(
                    np.linalg.norm((pawn - initial_pawn)[:2])
                ),
                "simulator_pawn_height_delta_m": float(
                    pawn[2] - initial_pawn[2]
                ),
                "physical_event_labels": [
                    key
                    for key, row in physical["events"].items()
                    if sample_index in row["sample_indices"]
                ],
            }
        )
    by_sample = {row["sample_index"]: row for row in aligned_rows}
    enclosure_sample = int(
        expected["physical_first_definite_enclosure_sample"]
    )
    carry_sample = int(
        expected["physical_first_definite_carried_motion_sample"]
    )
    enclosure = by_sample[enclosure_sample]
    carry = by_sample[carry_sample]
    or2_closeout = _bound_json(
        sources["or2_closeout"], root=root, label="OR2 closeout"
    )
    aperture_underprediction = float(
        or2_closeout["residual_localization"][
            "mean_separation_underprediction_px"
        ]
    )
    gates = contract["gates"]
    checks = {
        "physical_observation_accepted": physical["accepted"] is True,
        "c6_is_immutable_negative": (
            c6["numeric_task_success"] is False
            and c6["promotable_mission_success"] is False
        ),
        "action_identity": bool(all(action_identity.values())),
        "timestamp_identity": max_timestamp_error
        <= float(gates["maximum_timestamp_absolute_error_seconds"]),
        "enclosure_joint_rms": enclosure["joint_residual"][
            "all_joint_rms_degrees"
        ]
        <= float(
            gates[
                "maximum_all_joint_rms_error_degrees_at_definite_enclosure"
            ]
        ),
        "enclosure_gripper_alignment": enclosure["joint_residual"][
            "gripper_absolute_error_degrees"
        ]
        <= float(
            gates[
                "maximum_gripper_absolute_error_degrees_at_definite_enclosure"
            ]
        ),
        "simulator_contact_absent_at_physical_enclosure": enclosure[
            "simulator_selected_jaw_contact_count"
        ]
        == 0,
        "simulator_object_static_at_physical_carry_start": carry[
            "simulator_pawn_planar_displacement_m"
        ]
        <= float(
            gates[
                "maximum_simulator_pawn_planar_displacement_m_at_physical_carry_start"
            ]
        ),
        "or2_aperture_mismatch": aperture_underprediction
        >= float(gates["minimum_or2_jaw_separation_underprediction_px"]),
        "c6_selected_contact_steps_zero": int(
            c6["outcome"]["selected_piece_contact_steps"]
        )
        == int(expected["c6_selected_jaw_contact_steps"]),
    }
    contact_interval = physical["events"]["candidate_contact_interval_samples"]
    definite_time = float(
        physical["events"]["first_definite_enclosure_sample"]["time_seconds"][0]
    )
    sim_motion_sample = int(
        expected["c6_first_planar_motion_over_1mm_sample"]
    )
    sim_motion_time = float(
        trace_rows[sim_motion_sample]["source_timestamp_seconds"]
    )
    causal = {
        "earliest_divergence_channel": "selected_jaw_contact",
        "physical_candidate_interval_samples": contact_interval[
            "sample_indices"
        ],
        "physical_candidate_interval_seconds": contact_interval[
            "time_seconds"
        ],
        "definite_by_sample": enclosure_sample,
        "definite_by_seconds": definite_time,
        "simulator_selected_jaw_contact_count_at_definite_enclosure": enclosure[
            "simulator_selected_jaw_contact_count"
        ],
        "definite_object_consequence_divergence_sample": carry_sample,
        "definite_object_consequence_divergence_seconds": float(
            trace_rows[carry_sample]["source_timestamp_seconds"]
        ),
        "simulator_first_planar_motion_over_1mm_sample": sim_motion_sample,
        "simulator_first_planar_motion_over_1mm_seconds": sim_motion_time,
        "physical_enclosure_to_simulator_motion_gap_samples": (
            sim_motion_sample - enclosure_sample
        ),
        "physical_enclosure_to_simulator_motion_gap_seconds": (
            sim_motion_time - definite_time
        ),
        "selected_mechanism_family_for_or5": (
            "jaw_aperture_and_gripper_geometry_mapping"
        ),
        "mechanism_evidence": {
            "enclosure_all_joint_rms_degrees": enclosure[
                "joint_residual"
            ]["all_joint_rms_degrees"],
            "enclosure_gripper_absolute_error_degrees": enclosure[
                "joint_residual"
            ]["gripper_absolute_error_degrees"],
            "or2_mean_jaw_separation_underprediction_px": aperture_underprediction,
            "simulator_selected_jaw_contact_steps": int(
                c6["outcome"]["selected_piece_contact_steps"]
            ),
        },
        "remaining_alternatives": [
            "global_articulated_wrist_mapping_unapproved",
            "full_3d_jaw_pad_geometry_unmeasured",
            "contact_material_unidentifiable_until_geometric_contact_exists",
        ],
        "contact_material_selected": False,
        "actuator_timing_selected": False,
        "parameters_fit": False,
    }
    accepted = bool(all(checks.values()))
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "contract_sha256": sha256_file(CONTRACT_PATH),
        "action_identity": action_identity,
        "maximum_timestamp_absolute_error_seconds": max_timestamp_error,
        "aligned_event_rows": aligned_rows,
        "jaw_aperture_underprediction_px": aperture_underprediction,
        "checks": checks,
        "causal_localization": causal,
        "accepted": accepted,
        "result": (
            "FIRST_DIVERGENCE_LOCALIZED_TO_MISSING_SELECTED_JAW_ENCLOSURE"
            if accepted
            else "FIRST_DIVERGENCE_NOT_LOCALIZED"
        ),
        "proof_boundaries": contract["proof_boundaries"],
        "authority": contract["authority"],
    }
    return {**unsigned, "artifact_sha256": canonical_digest(unsigned)}


def build_divergence_receipt(
    contract_path: Path = CONTRACT_PATH,
    output_path: Path = OUTPUT_PATH,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    contract = load_divergence_contract(contract_path, root=root)
    receipt = evaluate_divergence(contract, root=root)
    atomic_write_json(output_path, receipt)
    return receipt


__all__ = [
    "CONTRACT_PATH",
    "OUTPUT_PATH",
    "build_divergence_receipt",
    "evaluate_divergence",
    "joint_residual",
    "load_divergence_contract",
]
