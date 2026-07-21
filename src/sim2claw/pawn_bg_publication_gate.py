"""Publication-safe composite receipt for the retained B--G fidelity campaign."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .paths import REPO_ROOT


CONTRACT_PATH = (
    REPO_ROOT / "configs" / "evaluations" / "pawn_bg_publication_gate_v1.json"
)
SCHEMA = "sim2claw.pawn_bg_publication_gate.v1"
RECEIPT_SCHEMA = "sim2claw.pawn_bg_publication_gate_receipt.v1"
BODY_JOINT_NAMES = (
    "shoulder_pan",
    "shoulder_lift",
    "elbow_flex",
    "wrist_flex",
    "wrist_roll",
)


class PublicationGateError(RuntimeError):
    """Evidence required by the frozen publication contract is missing or drifted."""


def load_publication_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    try:
        contract = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PublicationGateError(f"cannot read publication contract {path}: {error}") from error
    if contract.get("schema_version") != SCHEMA:
        raise PublicationGateError("unexpected publication contract schema")
    authority = contract.get("authority")
    if not isinstance(authority, dict) or not authority or any(authority.values()):
        raise PublicationGateError("publication authority widened")
    evidence = contract.get("evidence")
    if not isinstance(evidence, list) or len(evidence) != 9:
        raise PublicationGateError("publication evidence inventory changed")
    ids = [row["id"] for row in evidence]
    if len(set(ids)) != len(ids):
        raise PublicationGateError("publication evidence ids must be unique")
    bootstrap = contract["bootstrap"]
    if int(bootstrap["replicates"]) < 1000 or bootstrap["resampling_unit"] != "whole_episode":
        raise PublicationGateError("bootstrap contract is too weak")
    return contract


def _load_evidence(
    repository_root: Path, contract: dict[str, Any]
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    payloads: dict[str, dict[str, Any]] = {}
    bindings: list[dict[str, Any]] = []
    for item in contract["evidence"]:
        path = repository_root / item["path"]
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise PublicationGateError(f"cannot read required evidence {path}: {error}") from error
        if payload.get("schema_version") != item["schema_version"]:
            raise PublicationGateError(f"schema drift for evidence {item['id']}")
        payloads[item["id"]] = payload
        bindings.append(
            {
                **item,
                "absolute_path": str(path.resolve()),
                "sha256": sha256_file(path),
            }
        )
    return payloads, bindings


def _percentile_interval(values: np.ndarray, confidence: float) -> list[float]:
    alpha = (1.0 - confidence) / 2.0
    return [
        float(np.quantile(values, alpha)),
        float(np.quantile(values, 1.0 - alpha)),
    ]


def _bootstrap_trace_variant(
    traces: list[dict[str, Any]],
    variant: str,
    samples: np.ndarray,
    confidence: float,
) -> dict[str, Any]:
    sample_counts = np.asarray(
        [row["metrics"][variant]["sample_count"] for row in traces], dtype=np.float64
    )
    joint_sse = np.asarray(
        [sum(row["metrics"][variant]["joint_squared_error_degrees"]) for row in traces],
        dtype=np.float64,
    )
    ee_sse = np.asarray(
        [row["metrics"][variant]["ee_squared_error_m2"] for row in traces],
        dtype=np.float64,
    )
    denominator = sample_counts[samples].sum(axis=1)
    joint_rms = np.sqrt(joint_sse[samples].sum(axis=1) / (denominator * 5.0))
    ee_rms = np.sqrt(ee_sse[samples].sum(axis=1) / denominator)
    return {
        "joint_rms_degrees_95ci": _percentile_interval(joint_rms, confidence),
        "ee_rms_m_95ci": _percentile_interval(ee_rms, confidence),
    }


def _bootstrap_stall(
    traces: list[dict[str, Any]],
    variant: str,
    samples: np.ndarray,
    confidence: float,
) -> dict[str, list[float]]:
    result: dict[str, list[float]] = {}
    for name in ("shoulder_lift", "elbow_flex"):
        denominator = np.asarray(
            [row["metrics"][variant]["stall_rows"][name] for row in traces],
            dtype=np.float64,
        )
        numerator = np.asarray(
            [row["metrics"][variant]["stall_reproduced"][name] for row in traces],
            dtype=np.float64,
        )
        sampled_denominator = denominator[samples].sum(axis=1)
        fractions = np.divide(
            numerator[samples].sum(axis=1),
            sampled_denominator,
            out=np.zeros_like(sampled_denominator),
            where=sampled_denominator > 0,
        )
        result[f"{name}_95ci"] = _percentile_interval(fractions, confidence)
    return result


def _bootstrap_episode_mean(
    values: list[float], samples: np.ndarray, confidence: float
) -> list[float]:
    array = np.asarray(values, dtype=np.float64)
    return _percentile_interval(array[samples].mean(axis=1), confidence)


def _read_trace(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _plot_summary(
    *,
    evidence: dict[str, dict[str, Any]],
    output_path: Path,
) -> None:
    scale = evidence["metric_scale"]
    endpoint = evidence["endpoint_motion"]
    timing = evidence["timing"]
    reset = evidence["reset_reference"]
    deadband = evidence["servo_deadband"]
    contact = evidence["contact_sensitivity"]
    figure, axes = plt.subplots(3, 2, figsize=(15, 13), constrained_layout=True)
    figure.suptitle(
        "Retained-data B–G simulator fidelity: action-frozen evidence",
        fontsize=17,
        fontweight="bold",
    )

    ax = axes[0, 0]
    bracket = scale["candidate_bracket"]["mean_playing_side_bracket_m"]
    envelope = scale["candidate_bracket"]["all_edge_envelope_m"]
    ax.axvspan(envelope[0] * 1000, envelope[1] * 1000, color="#7aa6c2", alpha=0.18, label="all-edge envelope")
    ax.axvspan(bracket[0] * 1000, bracket[1] * 1000, color="#2f6f9f", alpha=0.35, label="mean-side bracket")
    for row, color in zip(scale["candidate_comparisons"], ("#1b9e77", "#d95f02"), strict=True):
        ax.axvline(row["playing_side_m"] * 1000, color=color, linewidth=3, label=row["id"])
    ax.set(title="A. Nominal-print-conditioned board scale", xlabel="playing side (mm)", yticks=[])
    ax.legend(fontsize=8, loc="upper left")

    ax = axes[0, 1]
    labels = ["legacy", "timestamp\naligned", "+110 ms", "+2° deadband"]
    joint = [
        timing["legacy_step_then_record"]["overall_joint_rms_degrees"],
        timing["timestamp_aligned_zero_delay"]["overall_joint_rms_degrees"],
        timing["selected_train_metrics"]["overall_joint_rms_degrees"],
        deadband["selected_train_metrics"]["overall_joint_rms_degrees"],
    ]
    ee = [
        timing["legacy_step_then_record"]["ee_rms_m"] * 1000,
        timing["timestamp_aligned_zero_delay"]["ee_rms_m"] * 1000,
        timing["selected_train_metrics"]["ee_rms_m"] * 1000,
        deadband["selected_train_metrics"]["ee_rms_m"] * 1000,
    ]
    x = np.arange(len(labels))
    ax.bar(x - 0.18, joint, width=0.36, color="#4c78a8", label="joint RMS (deg)")
    ax.set_xticks(x, labels)
    ax.set_ylabel("joint RMS (deg)")
    twin = ax.twinx()
    twin.bar(x + 0.18, ee, width=0.36, color="#f58518", label="EE RMS (mm)")
    twin.set_ylabel("EE RMS (mm)")
    ax.set_title("B. Trace error reduction")
    handles = ax.get_legend_handles_labels()[0] + twin.get_legend_handles_labels()[0]
    names = ax.get_legend_handles_labels()[1] + twin.get_legend_handles_labels()[1]
    ax.legend(handles, names, fontsize=8, loc="upper right")

    ax = axes[1, 0]
    timing_stall = timing["selected_train_metrics"]["stall_reproduction_fraction"]
    deadband_stall = deadband["selected_train_metrics"]["stall_reproduction_fraction"]
    x = np.arange(2)
    ax.bar(x - 0.18, [timing_stall["shoulder_lift"], timing_stall["elbow_flex"]], 0.36, label="timing only", color="#72b7b2")
    ax.bar(x + 0.18, [deadband_stall["shoulder_lift"], deadband_stall["elbow_flex"]], 0.36, label="+2° deadband", color="#e45756")
    ax.axhline(0.4, linestyle="--", color="#333333", linewidth=1, label="frozen diagnostic gate")
    ax.set(xticks=x, xticklabels=["shoulder lift", "elbow"], ylim=(0, 1), ylabel="flat-response reproduction", title="C. Mechanism-specific stall proxy")
    ax.legend(fontsize=8)

    ax = axes[1, 1]
    consequences = deadband["action_frozen_consequence_replay"]
    before = consequences["timing_only_zero_deadband"]["summary"]
    after = consequences["timing_plus_selected_deadband"]["summary"]
    high_prior = contact["summaries"]["rubber_tip_high"]
    x = np.arange(3)
    ax.bar(x - 0.25, [before["selected_piece_contact"], before["lifted"], before["task_consequence_successes"]], 0.25, label="timing only", color="#54a24b")
    ax.bar(x, [after["selected_piece_contact"], after["lifted"], after["task_consequence_successes"]], 0.25, label="+2° deadband", color="#b279a2")
    ax.bar(x + 0.25, [high_prior["contact"], high_prior["lifted"], high_prior["strict_success"]], 0.25, label="high rubber prior (sensitivity)", color="#ff9da6")
    ax.axhline(6, linestyle="--", color="#333333", linewidth=1, label="training-open minimum")
    ax.set(xticks=x, xticklabels=["contact", "lift", "strict success"], ylim=(0, 11.8), ylabel="episodes / 11", title="D. Unchanged-action consequences")
    ax.legend(fontsize=8)

    representative = timing["traces"][0]["recording_id"]
    timing_trace = _read_trace(timing["traces"][0]["trace_path"])
    deadband_trace_row = next(row for row in deadband["traces"] if row["recording_id"] == representative)
    deadband_trace = _read_trace(deadband_trace_row["trace_path"])
    ax = axes[2, 0]
    elapsed = np.asarray([row["elapsed_seconds"] for row in timing_trace["rows"]])
    measured = np.degrees(np.asarray([row["mapped_measured_joint_state"][1] for row in timing_trace["rows"]]))
    legacy = np.degrees(np.asarray([row["legacy_step_then_record"]["simulated_joint_state"][1] for row in timing_trace["rows"]]))
    selected_timing = np.degrees(np.asarray([row["aligned_selected_delay"]["simulated_joint_state"][1] for row in timing_trace["rows"]]))
    selected_deadband = np.degrees(np.asarray([row["timing_plus_selected_deadband"]["simulated_joint_state"][1] for row in deadband_trace["rows"]]))
    ax.plot(elapsed, measured, color="#111111", linewidth=2, label="measured")
    ax.plot(elapsed, legacy, color="#9d9d9d", linewidth=1, label="legacy")
    ax.plot(elapsed, selected_timing, color="#4c78a8", linewidth=1.2, label="+110 ms")
    ax.plot(elapsed, selected_deadband, color="#e45756", linewidth=1.2, label="+2° deadband")
    ax.set(title=f"E. Representative shoulder-lift trace\n{representative}", xlabel="episode time (s)", ylabel="mapped joint position (deg)")
    ax.legend(fontsize=8, ncol=2)

    ax = axes[2, 1]
    source_offsets = [row["source_visibility_loss"]["seconds_relative_to_gripper_closure_onset"] for row in endpoint["episodes"]]
    destination_offsets = [row["destination_final_appearance"]["seconds_relative_to_gripper_release_onset"] for row in endpoint["episodes"]]
    jitter = np.linspace(-0.08, 0.08, len(source_offsets))
    ax.scatter(np.zeros(len(source_offsets)) + jitter, source_offsets, color="#4c78a8", label="source disappears vs close")
    ax.scatter(np.ones(len(destination_offsets)) + jitter, destination_offsets, color="#f58518", label="destination appears vs release")
    ax.axhline(0, color="#333333", linewidth=1)
    ax.set(xticks=[0, 1], xticklabels=["source / closure", "destination / release"], ylabel="appearance-event offset (s)", title="F. Video endpoints are intervals, not contact labels")
    ax.legend(fontsize=8)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output_path, dpi=180)
    plt.close(figure)


def run_publication_gate(
    *,
    repository_root: Path,
    output_root: Path,
    contract_path: Path = CONTRACT_PATH,
) -> dict[str, Any]:
    contract = load_publication_contract(contract_path)
    evidence, bindings = _load_evidence(repository_root, contract)
    timing = evidence["timing"]
    reset = evidence["reset_reference"]
    deadband = evidence["servo_deadband"]
    contact = evidence["contact_sensitivity"]
    endpoint = evidence["endpoint_motion"]
    bootstrap = contract["bootstrap"]
    rng = np.random.default_rng(int(bootstrap["seed"]))
    episode_count = int(deadband["train_episode_count"])
    if episode_count != int(contract["gates"]["required_product_train_episodes"]):
        raise PublicationGateError("product train episode count changed")
    resamples = rng.integers(
        0, episode_count, size=(int(bootstrap["replicates"]), episode_count)
    )
    confidence = float(bootstrap["confidence_level"])

    timing_traces = timing["traces"]
    deadband_traces = deadband["traces"]
    intervals = {
        "legacy": _bootstrap_trace_variant(
            timing_traces, "legacy_step_then_record", resamples, confidence
        ),
        "timing_selected": {
            **_bootstrap_trace_variant(
                timing_traces, "aligned_selected_delay", resamples, confidence
            ),
            **_bootstrap_stall(
                timing_traces, "aligned_selected_delay", resamples, confidence
            ),
        },
        "deadband_selected": {
            **_bootstrap_trace_variant(
                deadband_traces,
                "timing_plus_selected_deadband",
                resamples,
                confidence,
            ),
            **_bootstrap_stall(
                deadband_traces,
                "timing_plus_selected_deadband",
                resamples,
                confidence,
            ),
        },
    }
    selected_episodes = deadband["action_frozen_consequence_replay"][
        "timing_plus_selected_deadband"
    ]["episodes"]
    intervals["selected_consequences"] = {
        "contact_fraction_95ci": _bootstrap_episode_mean(
            [float(row["selected_piece_contact_observed"]) for row in selected_episodes],
            resamples,
            confidence,
        ),
        "lift_fraction_95ci": _bootstrap_episode_mean(
            [float(row["piece_lifted"]) for row in selected_episodes],
            resamples,
            confidence,
        ),
        "task_success_fraction_95ci": _bootstrap_episode_mean(
            [float(row["task_consequence_success"]) for row in selected_episodes],
            resamples,
            confidence,
        ),
    }
    intervals["video_event_offsets"] = {
        "mean_source_loss_relative_to_closure_95ci_seconds": _bootstrap_episode_mean(
            [
                float(row["source_visibility_loss"]["seconds_relative_to_gripper_closure_onset"])
                for row in endpoint["episodes"]
            ],
            resamples,
            confidence,
        ),
        "mean_destination_appearance_relative_to_release_95ci_seconds": _bootstrap_episode_mean(
            [
                float(row["destination_final_appearance"]["seconds_relative_to_gripper_release_onset"])
                for row in endpoint["episodes"]
            ],
            resamples,
            confidence,
        ),
    }

    selected_summary = deadband["action_frozen_consequence_replay"][
        "timing_plus_selected_deadband"
    ]["summary"]
    action_invariance = bool(
        timing["action_arrays_byte_identical_across_variants"]
        and deadband["action_arrays_byte_identical_across_variants"]
    )
    gates = {
        "action_invariance": action_invariance,
        "nominal_print_scale_plausibility": (
            "registered_355p6mm"
            in evidence["metric_scale"]["decision"]["nominal_print_consistent_candidates"]
        ),
        "physical_metric_scale_authority": bool(
            evidence["metric_scale"]["decision"]["physical_metric_scale_established"]
        ),
        "timing_diagnostic": bool(
            timing["train_acceptance"]["accepted_as_timing_diagnostic"]
        ),
        "reset_reference_ruled_out_as_primary_gap": not bool(
            reset["decision"]["reset_reference_is_primary_remaining_gap"]
        ),
        "actuator_model_diagnostic": bool(
            deadband["train_acceptance"]["accepted_as_actuator_model_diagnostic"]
        ),
        "contact_parameters_identified": bool(
            contact["decision"]["contact_parameters_identified"]
        ),
        "composite_simulator_candidate": bool(
            deadband["train_acceptance"]["accepted_as_composite_simulator_candidate"]
        ),
        "minimum_lift_and_transport_episodes": False,
        "transport_outcome_observable": False,
        "fresh_physical_holdout_available": False,
    }
    lift_count = int(selected_summary["lifted"])
    lift_minimum = int(
        contract["gates"]["minimum_lift_and_transport_episodes_to_open_training"]
    )
    training_admitted = bool(
        gates["action_invariance"]
        and gates["timing_diagnostic"]
        and gates["actuator_model_diagnostic"]
        and gates["composite_simulator_candidate"]
        and gates["transport_outcome_observable"]
        and lift_count >= lift_minimum
    )
    physical_accuracy_established = bool(
        gates["physical_metric_scale_authority"]
        and gates["composite_simulator_candidate"]
        and gates["fresh_physical_holdout_available"]
    )

    figure_path = output_root.resolve() / "publication_summary.png"
    _plot_summary(evidence=evidence, output_path=figure_path)
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "proof_class": "retained_data_action_frozen_publication_gate",
        "contract": {
            "path": str(contract_path.resolve()),
            "sha256": sha256_file(contract_path),
        },
        "implementation": {
            "path": str(Path(__file__).resolve()),
            "sha256": sha256_file(Path(__file__).resolve()),
        },
        "evidence_bindings": bindings,
        "regeneration_commands": contract["regeneration_commands"],
        "frozen_vector": {
            "legacy_joint_rms_degrees": timing["legacy_step_then_record"]["overall_joint_rms_degrees"],
            "legacy_ee_rms_m": timing["legacy_step_then_record"]["ee_rms_m"],
            "selected_delay_seconds": timing["selected_delay_seconds"],
            "timing_joint_rms_degrees": timing["selected_train_metrics"]["overall_joint_rms_degrees"],
            "timing_ee_rms_m": timing["selected_train_metrics"]["ee_rms_m"],
            "selected_deadband_degrees": deadband["selected_deadband_degrees"],
            "deadband_joint_rms_degrees": deadband["selected_train_metrics"]["overall_joint_rms_degrees"],
            "deadband_ee_rms_m": deadband["selected_train_metrics"]["ee_rms_m"],
            "deadband_lift_stall_reproduction_fraction": deadband["selected_train_metrics"]["stall_reproduction_fraction"]["shoulder_lift"],
            "deadband_elbow_stall_reproduction_fraction": deadband["selected_train_metrics"]["stall_reproduction_fraction"]["elbow_flex"],
            "contact_episodes": selected_summary["selected_piece_contact"],
            "lift_episodes": lift_count,
            "transport_episodes": None,
            "task_success_episodes": selected_summary["task_consequence_successes"],
            "contact_prior_lift_count_range": [
                min(row["lifted"] for row in contact["summaries"].values()),
                max(row["lifted"] for row in contact["summaries"].values()),
            ],
            "contact_prior_strict_success_count_range": [
                min(row["strict_success"] for row in contact["summaries"].values()),
                max(row["strict_success"] for row in contact["summaries"].values()),
            ],
            "video_source_loss_relative_to_closure_mean_seconds": endpoint["summary"]["mean_source_visibility_loss_relative_to_closure_onset_seconds"],
            "video_destination_appearance_relative_to_release_mean_seconds": endpoint["summary"]["mean_destination_appearance_relative_to_release_onset_seconds"],
        },
        "episode_bootstrap": {
            "seed": bootstrap["seed"],
            "replicates": bootstrap["replicates"],
            "confidence_level": confidence,
            "intervals": intervals,
        },
        "gates": gates,
        "verdict": {
            "decision": "TERMINAL_NEGATIVE_CONTACT_RETENTION_AND_TRANSPORT_UNDERIDENTIFIED",
            "diagnostic_mechanisms_accepted": [
                "timestamp_aligned_zero_order_hold_with_110ms_simulator_side_delay",
                "two_degree_lift_elbow_servo_deadband_model_class",
            ],
            "mechanisms_ruled_out_as_primary_gap": ["reset_reference_semantics"],
            "mechanisms_remaining_underidentified": [
                "gripper_contact_geometry_and_friction",
                "grasp_retention_and_slip",
                "physical_transport_outcome",
            ],
            "simulator_composite_promoted": False,
            "training_admitted": training_admitted,
            "physical_accuracy_established": physical_accuracy_established,
            "interpretation": (
                "The retained data support a physically plausible 355.6 mm board hypothesis "
                "and two cross-validated simulator-side mechanisms under byte-identical actions. "
                "They do not establish a physically accurate simulator: unchanged replay reaches "
                "11/11 contact but only 2/11 lift and 0/11 strict success. The entire frozen "
                "rubber-tip sensitivity ensemble spans only 2--3 lifts and always 0 strict "
                "success, transport is not observed in the retained video labels, and no fresh "
                "physical holdout remains."
            ),
        },
        "smallest_future_measurements": [
            "Measure one printed AprilTag black edge and one chessboard playing edge in the same setup.",
            "Record synchronized side or depth video that keeps the pawn visible through grasp, lift, transport, and release.",
            "Log per-control-step commanded position, measured position, velocity, and calibrated current or effort for lift, elbow, and gripper.",
            "Record gripper aperture or jaw separation plus a binary retention/slip outcome during the lift phase.",
            "Reserve at least one untouched physical episode group before any subsequent fit or threshold change.",
        ],
        "artifacts": {
            "publication_summary_path": str(figure_path),
            "publication_summary_sha256": sha256_file(figure_path),
        },
        "authority": contract["authority"],
        "claim_boundary": (
            "This receipt establishes retained-data hardware-free diagnostics only. It is not "
            "physical metrology, a calibrated contact model, a successful B--G policy, fresh "
            "validation, simulator composite promotion, training admission, or sim-to-real transfer."
        ),
    }
    receipt["receipt_digest"] = canonical_digest(receipt)
    atomic_write_json(output_root.resolve() / "publication_gate_receipt.json", receipt)
    return receipt
