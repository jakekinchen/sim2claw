"""Ordered first-divergence attribution for frozen realized-action evidence."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import numpy as np

from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
    sha256_file,
)
from .paths import REPO_ROOT
from .realized_action_sage_lite import _Kinematics, load_episodes


SCHEMA = "sim2claw.realized_action_first_divergence_contract.v1"
RECEIPT_SCHEMA = "sim2claw.realized_action_first_divergence_receipt.v1"
CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "realized_action_first_divergence_v1.json"
)
OUTPUT_PATH = (
    REPO_ROOT
    / "outputs"
    / "realized_action_first_divergence_v1"
    / "receipt.json"
)
ORDER = (
    "initial_geometry",
    "requested_to_sent_action",
    "sent_to_measured_joint_response",
    "provisional_end_effector_projection",
    "first_contact",
    "pawn_planar_motion",
    "lift_or_tip",
    "release_or_support",
    "final_consequence",
)


def _bound(
    root: Path, entry: Mapping[str, Any], label: str
) -> tuple[Path, dict[str, Any]]:
    path = root / str(entry["path"])
    if not path.is_file() or sha256_file(path) != entry.get("sha256"):
        raise FactoryArtifactError(f"{label} hash rejected: {path}")
    return path, load_json_object(path, label=label)


def load_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="first-divergence contract")
    if contract.get("schema_version") != SCHEMA:
        raise FactoryArtifactError("unsupported first-divergence contract")
    if tuple(contract.get("ordered_channels", [])) != ORDER:
        raise FactoryArtifactError("first-divergence channel order changed")
    for key, entry in contract.get("sources", {}).items():
        _bound(root, entry, key)
    if not all(contract.get("rules", {}).values()):
        raise FactoryArtifactError("first-divergence rule widened")
    authority = contract.get("authority")
    if not isinstance(authority, dict) or not authority or any(authority.values()):
        raise FactoryArtifactError("first-divergence authority widened")
    return contract


def _first_index(mask: np.ndarray) -> int | None:
    indices = np.flatnonzero(mask)
    return int(indices[0]) if len(indices) else None


def _event(
    *,
    channel: str,
    status: str,
    sample_index: int | None = None,
    timestamp_seconds: float | None = None,
    evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "channel": channel,
        "status": status,
        "sample_index": sample_index,
        "timestamp_seconds": timestamp_seconds,
        "evidence": dict(evidence or {}),
    }


def _episode_events(
    episode: Any,
    kinematics: _Kinematics,
    contract: Mapping[str, Any],
    *,
    sealed_sources: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    thresholds = contract["thresholds"]
    timestamps = episode.timestamps
    events: list[dict[str, Any]] = []
    if episode.cohort_role == "sealed":
        events.append(
            _event(
                channel="initial_geometry",
                status="observed_within_frozen_metric_gate",
                sample_index=0,
                timestamp_seconds=float(timestamps[0]),
                evidence={"physical_d1_error_mm": 3.100600525428267},
            )
        )
    else:
        events.append(
            _event(
                channel="initial_geometry",
                status="unobservable_metric_object_state",
                evidence={
                    "reason": "legacy episode has no evaluator-owned metric initial object observation"
                },
            )
        )
    requested_sent = np.any(episode.requested != episode.sent, axis=1)
    index = _first_index(requested_sent)
    events.append(
        _event(
            channel="requested_to_sent_action",
            status="diverged" if index is not None else "no_exact_difference_observed",
            sample_index=index,
            timestamp_seconds=float(timestamps[index]) if index is not None else None,
            evidence={
                "changed_row_count": int(np.sum(requested_sent)),
                "sample_count": int(len(timestamps)),
            },
        )
    )
    joint_error = np.abs(episode.sent - episode.measured)
    joint_mask = np.any(
        joint_error > float(thresholds["joint_response_absolute_degrees"]), axis=1
    )
    index = _first_index(joint_mask)
    evidence: dict[str, Any] = {
        "threshold_degrees": float(thresholds["joint_response_absolute_degrees"]),
        "maximum_absolute_degrees": float(np.max(joint_error)),
    }
    if index is not None:
        joint_index = int(np.argmax(joint_error[index]))
        evidence["first_joint"] = episode.joint_order[joint_index]
        evidence["first_joint_error_degrees"] = float(joint_error[index, joint_index])
    events.append(
        _event(
            channel="sent_to_measured_joint_response",
            status="diverged" if index is not None else "within_threshold",
            sample_index=index,
            timestamp_seconds=float(timestamps[index]) if index is not None else None,
            evidence=evidence,
        )
    )
    sent_ee = kinematics.positions(episode.sent)
    measured_ee = kinematics.positions(episode.measured)
    ee_error_mm = np.linalg.norm(sent_ee - measured_ee, axis=1) * 1000.0
    ee_mask = ee_error_mm > float(
        thresholds["provisional_end_effector_error_mm"]
    )
    index = _first_index(ee_mask)
    events.append(
        _event(
            channel="provisional_end_effector_projection",
            status="diverged_under_unapproved_mapping" if index is not None else "within_threshold_under_unapproved_mapping",
            sample_index=index,
            timestamp_seconds=float(timestamps[index]) if index is not None else None,
            evidence={
                "threshold_mm": float(
                    thresholds["provisional_end_effector_error_mm"]
                ),
                "maximum_error_mm": float(np.max(ee_error_mm)),
                "mapping_globally_approved": False,
            },
        )
    )
    if sealed_sources is None:
        for channel in ORDER[4:]:
            events.append(
                _event(
                    channel=channel,
                    status="unobservable",
                    evidence={
                        "reason": "episode has no per-sample metric object, contact, or evaluator consequence channel"
                    },
                )
            )
        return events

    trace_rows = sealed_sources["trace"]["rows"]
    grasp_active = np.asarray(
        [bool(row["grasp_mode_active"]) for row in trace_rows], dtype=bool
    )
    first_grasp = _first_index(grasp_active)
    events.append(
        _event(
            channel="first_contact",
            status="unobservable_observed_grasp_mode_only",
            sample_index=(
                int(trace_rows[first_grasp]["sample_index"])
                if first_grasp is not None
                else None
            ),
            timestamp_seconds=(
                float(trace_rows[first_grasp]["source_timestamp_seconds"])
                if first_grasp is not None
                else None
            ),
            evidence={
                "observed_grasp_mode_event_available": first_grasp is not None,
                "contact_witness_available": False,
            },
        )
    )
    pawn = np.asarray(
        [row["selected_pawn_position_m"] for row in trace_rows], dtype=np.float64
    )
    planar_mm = np.linalg.norm(pawn[:, :2] - pawn[0, :2], axis=1) * 1000.0
    index = _first_index(
        planar_mm > float(thresholds["simulated_pawn_planar_motion_mm"])
    )
    events.append(
        _event(
            channel="pawn_planar_motion",
            status="observed_in_observed_state_plus_mode_simulator" if index is not None else "not_observed_in_trace",
            sample_index=(
                int(trace_rows[index]["sample_index"]) if index is not None else None
            ),
            timestamp_seconds=(
                float(trace_rows[index]["source_timestamp_seconds"])
                if index is not None
                else None
            ),
            evidence={
                "threshold_mm": float(
                    thresholds["simulated_pawn_planar_motion_mm"]
                ),
                "maximum_planar_displacement_mm": float(np.max(planar_mm)),
                "physical_metric_path_available": False,
            },
        )
    )
    lift_mm = (pawn[:, 2] - pawn[0, 2]) * 1000.0
    index = _first_index(
        lift_mm > float(thresholds["simulated_pawn_lift_mm"])
    )
    events.append(
        _event(
            channel="lift_or_tip",
            status="simulated_lift_observed_physical_tip_path_unobservable"
            if index is not None
            else "unobservable",
            sample_index=(
                int(trace_rows[index]["sample_index"]) if index is not None else None
            ),
            timestamp_seconds=(
                float(trace_rows[index]["source_timestamp_seconds"])
                if index is not None
                else None
            ),
            evidence={
                "maximum_simulated_lift_mm": float(np.max(lift_mm)),
                "free_release_terminal_tilt_degrees": sealed_sources[
                    "rp04k"
                ]["drivers"]["observed_joint_state_upper_bound"]["outcome"][
                    "final_upright_tilt_degrees"
                ],
            },
        )
    )
    release_indices = np.flatnonzero(grasp_active[:-1] & ~grasp_active[1:])
    release = int(release_indices[0] + 1) if len(release_indices) else None
    events.append(
        _event(
            channel="release_or_support",
            status="observed_mode_release_then_free_support_failure",
            sample_index=(
                int(trace_rows[release]["sample_index"]) if release is not None else None
            ),
            timestamp_seconds=(
                float(trace_rows[release]["source_timestamp_seconds"])
                if release is not None
                else None
            ),
            evidence={
                "observed_mode_release": release is not None,
                "free_release_composable_success": False,
                "support_handoff_successes": 1,
                "support_handoff_attempts": 3,
                "support_projection_is_free_contact_prediction": False,
            },
        )
    )
    rp04k_outcome = sealed_sources["rp04k"]["drivers"][
        "observed_joint_state_upper_bound"
    ]["outcome"]
    events.append(
        _event(
            channel="final_consequence",
            status="physical_visual_success_but_free_release_simulator_failure",
            sample_index=int(trace_rows[-1]["sample_index"]),
            timestamp_seconds=float(trace_rows[-1]["source_timestamp_seconds"]),
            evidence={
                "physical_terminal_upright_reviewed": True,
                "simulator_composable_success": bool(
                    rp04k_outcome["composable_task_success"]
                ),
                "simulator_final_planar_center_error_mm": float(
                    rp04k_outcome["final_planar_center_error_m"] * 1000.0
                ),
                "simulator_final_height_error_mm": float(
                    rp04k_outcome["final_height_error_m"] * 1000.0
                ),
                "simulator_final_tilt_degrees": float(
                    rp04k_outcome["final_upright_tilt_degrees"]
                ),
            },
        )
    )
    return events


def _sensitivity_matrix(
    c2: Mapping[str, Any],
    c3: Mapping[str, Any],
    rp04k: Mapping[str, Any],
    rp04l: Mapping[str, Any],
) -> list[dict[str, Any]]:
    fit = c3["cohort_results"]["fit"]
    validation = c3["cohort_results"]["validation"]
    upper = rp04k["drivers"]["observed_joint_state_upper_bound"]["outcome"]
    return [
        {
            "channel": "geometry",
            "evidence": {
                "task_plane_rms_mm": c2["accepted"]["task_plane_rms_mm"],
                "initial_d1_error_mm": c2["accepted"][
                    "initial_d1_pawn_base_error_mm"
                ],
                "terminal_d2_error_mm": c2["accepted"][
                    "terminal_d2_pawn_base_error_mm"
                ],
                "global_mapping_approved": False,
            },
            "changes_observed_residual": True,
            "cross_episode_identified": False,
            "advance": "preserve_task_plane_only",
        },
        {
            "channel": "sample_timing",
            "evidence": {
                "fit_best_shift_samples": fit["sample_domain_alignment"][
                    "best_overall"
                ]["shift_samples"],
                "validation_best_shift_samples": validation[
                    "sample_domain_alignment"
                ]["best_overall"]["shift_samples"],
                "rp04l_release_offsets_tested": [-1, 0, 1],
                "rp04l_successes": 1,
                "rp04l_attempts": 3,
            },
            "changes_observed_residual": True,
            "cross_episode_identified": True,
            "advance": "C4_sample_domain_temporal_challenger_not_causal_latency",
        },
        {
            "channel": "actuation",
            "evidence": {
                "fit_unshifted_rms_degrees": fit["sent_to_measured"][
                    "overall_rms_degrees"
                ],
                "fit_aligned_rms_degrees": fit["sample_domain_alignment"][
                    "best_overall"
                ]["overall_rms_degrees"],
                "validation_unshifted_rms_degrees": validation[
                    "sent_to_measured"
                ]["overall_rms_degrees"],
                "validation_aligned_rms_degrees": validation[
                    "sample_domain_alignment"
                ]["best_overall"]["overall_rms_degrees"],
                "stable_ee_rank": [
                    row["joint"]
                    for row in fit["provisional_kinematic_ee_residual"][
                        "single_joint_substitution_ranking"
                    ]
                ],
            },
            "changes_observed_residual": True,
            "cross_episode_identified": True,
            "advance": "C4_direction_conditioned_response_candidate",
        },
        {
            "channel": "contact_and_support",
            "evidence": {
                "observed_state_free_release_composable_success": bool(
                    upper["composable_task_success"]
                ),
                "observed_state_free_release_tilt_degrees": upper[
                    "final_upright_tilt_degrees"
                ],
                "support_handoff_successes": rp04l["ledger"][
                    "observed_state_plus_upright_support_mode_real_to_sim"
                ]["successes"],
                "support_handoff_attempts": rp04l["ledger"][
                    "observed_state_plus_upright_support_mode_real_to_sim"
                ]["attempts"],
            },
            "changes_observed_residual": True,
            "cross_episode_identified": False,
            "advance": "C5_diagnostic_only_until_nonsealed_contact_witness_exists",
        },
        {
            "channel": "evaluator",
            "evidence": {
                "rp04l_minus_1_coarse_success": rp04l["variants"]["minus_1"][
                    "outcome"
                ]["coarse_square_task_success"],
                "rp04l_minus_1_composable_success": rp04l["variants"]["minus_1"][
                    "outcome"
                ]["composable_task_success"],
                "rp04l_minus_1_center_error_mm": rp04l["variants"]["minus_1"][
                    "outcome"
                ]["final_planar_center_error_m"]
                * 1000.0,
            },
            "changes_observed_residual": False,
            "cross_episode_identified": False,
            "advance": "preserve_frozen_composable_gate",
        },
    ]


def analyze(
    contract_path: Path = CONTRACT_PATH,
    output_path: Path = OUTPUT_PATH,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    contract = load_contract(contract_path, root=root)
    _, c3 = _bound(root, contract["sources"]["c3_receipt"], "C3 receipt")
    if c3.get("artifact_sha256") != contract["sources"]["c3_receipt"][
        "artifact_sha256"
    ]:
        raise FactoryArtifactError("C3 artifact changed")
    _, c2 = _bound(root, contract["sources"]["c2_closeout"], "C2 closeout")
    _, rp04k = _bound(root, contract["sources"]["rp04k_receipt"], "RP04K receipt")
    _, trace = _bound(
        root,
        contract["sources"]["rp04k_observed_state_trace"],
        "RP04K observed state trace",
    )
    _, rp04l = _bound(root, contract["sources"]["rp04l_receipt"], "RP04L receipt")
    c3_contract_path = (
        root / "configs" / "evaluations" / "realized_action_sage_lite_v1.json"
    )
    c3_contract = load_json_object(c3_contract_path, label="C3 contract")
    episodes = load_episodes(c3_contract, root=root)
    manifest = load_json_object(
        root / c3_contract["sources"]["kinematic_manifest"]["path"],
        label="C3 kinematic manifest",
    )
    kinematics = _Kinematics(manifest)
    episode_results = []
    for episode in episodes:
        sealed_sources = (
            {"rp04k": rp04k, "rp04l": rp04l, "trace": trace}
            if episode.cohort_role == "sealed"
            else None
        )
        events = _episode_events(
            episode,
            kinematics,
            contract,
            sealed_sources=sealed_sources,
        )
        observed_divergences = [
            row
            for row in events
            if row["status"]
            in {
                "diverged",
                "diverged_under_unapproved_mapping",
                "physical_visual_success_but_free_release_simulator_failure",
            }
        ]
        first = observed_divergences[0] if observed_divergences else None
        episode_results.append(
            {
                "recording_id": episode.recording_id,
                "cohort_role": episode.cohort_role,
                "ordered_channels": events,
                "first_observed_divergence": (
                    {
                        "channel": first["channel"],
                        "sample_index": first["sample_index"],
                        "timestamp_seconds": first["timestamp_seconds"],
                    }
                    if first is not None
                    else None
                ),
            }
        )
    matrix = _sensitivity_matrix(c2, c3, rp04k, rp04l)
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "contract_sha256": sha256_file(contract_path),
        "episode_count": len(episode_results),
        "episode_results": episode_results,
        "sensitivity_matrix": matrix,
        "admitted_successors": {
            "C4": [
                "three_sample_sample_domain_command_hold_challenger",
                "direction_conditioned_effective_joint_response",
            ],
            "C5": [],
            "C5_diagnostic_only": [
                "free_release_support_and_upright_contact_consequence"
            ],
            "sealed_used_for_selection": False,
        },
        "compensating_parameter_flags": [
            {
                "pair": [
                    "sample_hold_or_delay",
                    "direction_conditioned_undertravel",
                ],
                "reason": "both can reduce sent-to-measured phase residual; compare sequentially on untouched episodes"
            },
            {
                "pair": [
                    "release_timing",
                    "support_or_contact_mode",
                ],
                "reason": "RP04L changes both event timing and object support semantics relative to free release"
            },
            {
                "pair": [
                    "camera_or_task_plane_mapping",
                    "joint_or_link_mapping",
                ],
                "reason": "global mapping remains unapproved even though task-plane endpoints pass"
            }
        ],
        "identifiability_boundary": {
            "causal_latency_identified": False,
            "nonsealed_contact_witness_available": False,
            "per_sample_physical_object_path_available": False,
            "global_mapping_approved": False,
        },
        "claim_boundary": (
            "Ordered retrospective first-divergence and mechanism attribution. "
            "Only sample-domain timing and direction-conditioned joint response "
            "repeat outside the sealed episode. Contact/support evidence remains "
            "sealed-episode diagnostic and cannot select a C5 model."
        ),
        "authority": contract["authority"],
    }
    receipt = {**unsigned, "artifact_sha256": canonical_digest(unsigned)}
    atomic_write_json(output_path, receipt)
    return receipt
