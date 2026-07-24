"""Read-only, receipt-verified Twin fidelity projection for Studio replays."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from .hil_publication import (
    load_hil_publication_binding,
    verify_hil_publication,
)
from .paths import REPO_ROOT
from .overnight_calibration_publication import (
    load_overnight_calibration_binding,
    verify_overnight_calibration_publication,
)
from .sail.importers import load_json_object
from .sail.live_receipts import verify_live_operator_receipt
from .sail.studio import load_studio_observatory


SCHEMA_VERSION = "sim2claw.studio_twin_fidelity.v1"
DEFAULT_LIVE_OPERATOR_RECEIPT = Path(
    "outputs/sail/live-operator-c2-adapter-v1/receipt.json"
)
DEFAULT_ADAPTER_CONTRACT = Path("configs/sail/c2_trusted_adapter_v1.json")

DOMAIN_ORDER = (
    ("geometry_scale", "Geometry / scale"),
    ("kinematics", "Kinematics"),
    ("action_timing", "Action / timing"),
    ("contact_compliance", "Contact / compliance"),
    ("actuator_load_path", "Actuator / load path"),
    ("task_ee_consequence", "Task / EE consequence"),
)

READ_ONLY_AUTHORITY = {
    "read_only": True,
    "training_admitted": False,
    "simulator_promotion": False,
    "physical_capture": False,
    "physical_authority": False,
    "robot_motion": False,
}


class TwinFidelityError(ValueError):
    """Twin fidelity evidence could not be projected without changing meaning."""


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_rows(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [row for row in value if isinstance(row, Mapping)]


def _availability(episode: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    return next(
        (
            row
            for row in _as_rows(episode.get("availability"))
            if row.get("id") == name
        ),
        {},
    )


def _residual_cell(
    episode: Mapping[str, Any], channel: str
) -> Mapping[str, Any]:
    return next(
        (
            row
            for row in _as_rows(episode.get("residual_cells"))
            if row.get("channel") == channel
        ),
        {},
    )


def _measurement(
    label: str,
    *,
    value: float | int | None,
    unit: str,
    source: str,
    threshold: float | int | None = None,
    comparator: str | None = None,
) -> dict[str, Any]:
    return {
        "label": label,
        "value": value,
        "unit": unit,
        "source": source,
        "threshold": threshold,
        "comparator": comparator,
        "observed": value is not None,
    }


def _domain(
    domain_id: str,
    *,
    status: str,
    summary: str,
    detail: str,
    measurements: Sequence[Mapping[str, Any]] = (),
    missing_evidence: Sequence[str] = (),
) -> dict[str, Any]:
    label = dict(DOMAIN_ORDER)[domain_id]
    return {
        "id": domain_id,
        "label": label,
        "status": status,
        "summary": summary,
        "detail": detail,
        "measurements": [dict(row) for row in measurements],
        "missing_evidence": list(dict.fromkeys(str(row) for row in missing_evidence)),
    }


def _unavailable_projection(
    episode: Mapping[str, Any], *, reason: str, detail: str
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "available": False,
        "evidence_status": "unavailable",
        "reason": reason,
        "detail": detail,
        "episode": {
            "id": episode.get("id"),
            "title": episode.get("title"),
            "action_sha256": episode.get("action_array_sha256"),
            "proof_class": episode.get("proof_class"),
        },
        "authority": dict(READ_ONLY_AUTHORITY),
        "domains": [
            _domain(
                domain_id,
                status="missing",
                summary="Evidence unavailable",
                detail=detail,
                missing_evidence=["receipt_verified_projection"],
            )
            for domain_id, _ in DOMAIN_ORDER
        ],
        "chain": [],
        "hypotheses": [],
        "next_evidence": {
            "status": "missing",
            "summary": "Restore the receipt-verified evidence projection.",
            "measurements": [],
        },
    }


def _hil_identifiability_projection(
    episode: Mapping[str, Any],
    bundle: Mapping[str, Any],
) -> dict[str, Any]:
    """Project a verified HIL packet without turning it into task proof."""

    packet_id = str(episode.get("source_recording_id") or "")
    packet = next(
        (
            row
            for row in _as_rows(bundle.get("packets"))
            if row.get("packet_id") == packet_id
        ),
        {},
    )
    if not packet:
        return _unavailable_projection(
            episode,
            reason="hil_packet_not_in_publication",
            detail="The selected HIL packet is not in the verified publication.",
        )
    raw = _as_mapping(packet.get("raw"))
    evaluation = _as_mapping(packet.get("evaluation"))
    summary = _as_mapping(packet.get("summary"))
    offline_bundle = _as_mapping(bundle.get("offline_analysis"))
    offline_report = _as_mapping(offline_bundle.get("report"))
    offline_packet = next(
        (
            row
            for row in _as_rows(offline_report.get("packets"))
            if row.get("packet_id") == packet_id
        ),
        {},
    )
    if not offline_packet:
        return _unavailable_projection(
            episode,
            reason="hil_offline_analysis_packet_missing",
            detail=(
                "The hash-bound offline trace diagnostic is missing the selected "
                "HIL packet; no telemetry-derived claim is attached."
            ),
        )
    decomposition_bundle = _as_mapping(bundle.get("offline_decomposition"))
    decomposition_report = _as_mapping(decomposition_bundle.get("report"))
    decomposition_packet = next(
        (
            row
            for row in _as_rows(decomposition_report.get("packets"))
            if row.get("packet_id") == packet_id
        ),
        {},
    )
    if not decomposition_packet:
        return _unavailable_projection(
            episode,
            reason="hil_offline_decomposition_packet_missing",
            detail=(
                "The requested-versus-applied trace decomposition is missing "
                "the selected HIL packet; no action-integrity claim is attached."
            ),
        )
    selected_action = str(episode.get("action_array_sha256") or "")
    packet_action = str(raw.get("action_tensor_sha256") or "")
    analysis_action = str(offline_packet.get("action_tensor_sha256") or "")
    decomposition_identity = _as_mapping(
        decomposition_packet.get("action_identity")
    )
    decomposition_action = str(
        decomposition_identity.get("requested_action_sha256") or ""
    )
    if (
        not selected_action
        or selected_action != packet_action
        or selected_action != analysis_action
        or selected_action != decomposition_action
    ):
        return _unavailable_projection(
            episode,
            reason="hil_action_hash_mismatch",
            detail=(
                "Twin fidelity requires the selected Replay action hash to match "
                "the verified HIL packet exactly; episode-ID fallback is prohibited."
            ),
        )
    admitted = evaluation.get("admitted") is True
    failures = [str(value) for value in evaluation.get("failures") or []]
    tracking = _as_mapping(summary.get("tracking"))
    lag = _as_mapping(tracking.get("requested_to_actual_best_lag"))
    current = _as_mapping(summary.get("current_raw"))
    offline_lag = _as_mapping(offline_packet.get("sample_quantized_lag"))
    directional = _as_mapping(offline_packet.get("directional_tracking"))
    plateau = _as_mapping(
        offline_packet.get("plateau_scale_offset_diagnostic")
    )
    reset_audit = _as_mapping(offline_packet.get("reset_return_audit"))
    current_association = _as_mapping(
        offline_packet.get("fresh_current_association")
    )
    offline_safety = _as_mapping(offline_packet.get("safety"))
    fault_chronology = _as_mapping(
        decomposition_packet.get("fault_chronology")
    )
    fault_events = _as_rows(fault_chronology.get("events"))
    fault_event_summary = " → ".join(
        f"{str(row.get('event') or '').replace('_', ' ')} "
        f"@ {row.get('sample_index')}"
        for row in fault_events
    )
    pre_fault_lag = _as_mapping(
        fault_chronology.get("pre_fault_best_lag")
    )
    cameras = _as_mapping(summary.get("cameras"))
    wrist = _as_mapping(cameras.get("wrist"))
    sim_bundle = _as_mapping(bundle.get("simulator"))
    sim_raw = _as_mapping(sim_bundle.get("raw_comparison"))
    sim_evaluation = _as_mapping(sim_bundle.get("evaluation"))
    sim_receipt = _as_mapping(sim_bundle.get("receipt"))
    baseline_metrics = _as_mapping(
        _as_mapping(sim_raw.get("baseline")).get("metrics")
    )
    candidate_metrics = _as_mapping(
        _as_mapping(sim_raw.get("candidate")).get("metrics")
    )
    is_shoulder = packet_id == "HIL-SHOULDER-LIFT-22"
    is_elbow = packet_id == "HIL-ELBOW-FLEX-22"
    is_wrist = packet_id == "HIL-WRIST-FLEX-30"
    if is_shoulder:
        kinematics_status = "failed"
        kinematics_summary = (
            "Physical span was admitted; the simulator candidate failed a "
            "non-target gate"
        )
        kinematics_detail = (
            "The unloaded shoulder response is a valid physical measurement. "
            "Applying the pre-existing follower shoulder range reduced shoulder "
            "RMSE, but elbow RMSE regressed beyond the frozen 0.25° ceiling. The "
            "independent evaluator rejected the candidate and promoted nothing."
        )
    elif admitted:
        kinematics_status = "observed"
        kinematics_summary = "Bounded unloaded joint response was admitted"
        kinematics_detail = (
            "The packet met frozen motion, return, telemetry, and dual-camera "
            "coverage gates. It identifies only this unloaded response."
        )
    elif is_elbow:
        kinematics_status = "failed"
        kinematics_summary = "Elbow packet failed the frozen stall gate"
        kinematics_detail = (
            "The action completed and returned, but six stall-warning samples "
            "and elevated raw current made the packet inadmissible for fitting."
        )
    else:
        kinematics_status = "failed"
        kinematics_summary = "Wrist packet failed the frozen evidence gate"
        kinematics_detail = (
            "The motion trace completed, but D405 finalization failed. The "
            "single-attempt packet remains rejected and was not retried."
        )
    kinematics_measurements = [
        _measurement(
            "Requested span",
            value=summary.get("requested_span_degrees"),
            unit="deg",
            source="Preregistered HIL action tensor",
        ),
        _measurement(
            "Physical span",
            value=summary.get("actual_span_degrees"),
            unit="deg",
            source="Follower position telemetry",
        ),
        _measurement(
            "Lag-aligned RMSE",
            value=lag.get("lag_aligned_rmse"),
            unit="deg",
            source="Independent HIL packet evaluator",
        ),
        _measurement(
            "Directional residual gap",
            value=directional.get("mean_residual_gap_degrees"),
            unit="deg",
            source="Hash-bound offline trace diagnostic · not backlash proof",
        ),
        _measurement(
            "Return residual",
            value=reset_audit.get("final_minus_initial_degrees"),
            unit="deg",
            source="Single-packet reset audit · not drift proof",
        ),
    ]
    if is_shoulder:
        kinematics_measurements.extend(
            [
                _measurement(
                    "Baseline shoulder RMSE",
                    value=sim_evaluation.get(
                        "baseline_target_joint_rmse_degrees"
                    ),
                    unit="deg",
                    source="Action-identical CPU/fp32 simulator comparison",
                ),
                _measurement(
                    "Candidate shoulder RMSE",
                    value=sim_evaluation.get(
                        "candidate_target_joint_rmse_degrees"
                    ),
                    unit="deg",
                    source="Action-identical CPU/fp32 simulator comparison",
                ),
                _measurement(
                    "Elbow RMSE regression",
                    value=(
                        sim_evaluation.get(
                            "body_joint_rmse_regression_degrees", []
                        )[2]
                        if len(
                            sim_evaluation.get(
                                "body_joint_rmse_regression_degrees", []
                            )
                        )
                        > 2
                        else None
                    ),
                    unit="deg",
                    source="Independent CPU/fp32 simulator evaluator",
                    threshold=0.25,
                    comparator="≤",
                ),
            ]
        )
    domains = [
        _domain(
            "geometry_scale",
            status="missing",
            summary="No metric scene or object geometry in this packet",
            detail=(
                "The cameras are diagnostic RGB views. They do not provide "
                "metric depth, calibrated camera-to-gripper extrinsics, or object pose."
            ),
            missing_evidence=[
                "metric_wrist_depth",
                "camera_to_gripper_extrinsics",
                "metric_object_pose",
            ],
        ),
        _domain(
            "kinematics",
            status=kinematics_status,
            summary=kinematics_summary,
            detail=kinematics_detail,
            measurements=kinematics_measurements,
            missing_evidence=(
                ["non_target_joint_nonregression", "strict_task_consequence"]
                if is_shoulder
                else failures
            ),
        ),
        _domain(
            "action_timing",
            status=(
                "observed"
                if decomposition_identity.get(
                    "applied_action_byte_identical"
                )
                is True
                else "failed"
            ),
            summary=(
                "Applied action matched the requested tensor byte-for-byte"
                if decomposition_identity.get(
                    "applied_action_byte_identical"
                )
                is True
                else "Applied action differed from the requested tensor"
            ),
            detail=(
                "Requested and applied actions have separate content hashes. "
                f"{decomposition_identity.get('gateway_rate_limited_sample_count')} "
                "sample(s) carried a gateway rate-limit flag. Requested and actual "
                "position were aligned over the frozen 20 Hz trace, but the "
                "displayed lag is sample-quantized response alignment, not "
                "command-application latency; actuator timestamps are absent."
            ),
            measurements=[
                _measurement(
                    "Byte-modified action samples",
                    value=decomposition_identity.get(
                        "byte_modified_sample_count"
                    ),
                    unit="samples",
                    source="Requested-versus-applied action tensor audit",
                    threshold=0,
                    comparator="=",
                ),
                _measurement(
                    "Gateway rate-limited samples",
                    value=decomposition_identity.get(
                        "gateway_rate_limited_sample_count"
                    ),
                    unit="samples",
                    source="Guarded physical gateway",
                    threshold=0,
                    comparator="=",
                ),
                _measurement(
                    "First gateway-modified sample",
                    value=decomposition_identity.get(
                        "first_gateway_modified_sample"
                    ),
                    unit="sample index",
                    source="Requested-versus-applied fault chronology",
                ),
                _measurement(
                    "Pre-fault best lag",
                    value=(
                        float(pre_fault_lag["lag_samples"])
                        / float(offline_packet.get("sample_hz") or 20)
                        if pre_fault_lag.get("lag_samples") is not None
                        else None
                    ),
                    unit="s",
                    source="Pre-rate-limit trace window · diagnostic only",
                ),
                _measurement(
                    "Best sample-quantized lag",
                    value=offline_lag.get("seconds"),
                    unit="s",
                    source="Offline trace diagnostic · not actuator latency",
                ),
                _measurement(
                    "Raw requested-to-actual RMSE",
                    value=tracking.get("requested_to_actual_rmse"),
                    unit="deg",
                    source="Follower position telemetry",
                ),
            ],
            missing_evidence=["command_application_timestamp"],
        ),
        _domain(
            "contact_compliance",
            status="missing",
            summary="Contact and compliance were not excited",
            detail=(
                "These are unloaded single-joint packets. They cannot identify "
                "pawn contact, fingertip deformation, friction, or grasp retention."
            ),
            missing_evidence=[
                "contact_state",
                "force",
                "deformation",
                "pawn_trajectory",
            ],
        ),
        _domain(
            "actuator_load_path",
            status="observed",
            summary="Raw motor-current samples exist; force remains uncalibrated",
            detail=(
                "Fresh motor-register values were captured and are useful for "
                "diagnosis, but they are not torque or contact-force measurements."
                + (
                    f" Index-aligned chronology: {fault_event_summary}. This "
                    "ordering is correlation, not causality."
                    if fault_event_summary
                    else ""
                )
            ),
            measurements=[
                _measurement(
                    "Current p95 absolute",
                    value=current.get("p95_absolute"),
                    unit="raw register",
                    source="Follower current telemetry · diagnostic only",
                ),
                _measurement(
                    "Current maximum absolute",
                    value=current.get("maximum"),
                    unit="raw register",
                    source="Follower current telemetry · diagnostic only",
                ),
                _measurement(
                    "Stall-warning samples",
                    value=offline_safety.get("stall_warning_sample_count"),
                    unit="samples",
                    source="Guarded physical gateway",
                    threshold=0,
                    comparator="=",
                ),
                _measurement(
                    "Current ↔ absolute error correlation",
                    value=current_association.get(
                        "correlation_absolute_current_to_absolute_error"
                    ),
                    unit="correlation",
                    source="Fresh raw-current samples · diagnostic only",
                ),
            ],
            missing_evidence=[
                "current_zero_and_scale_calibration",
                "current_to_torque_calibration",
                "force",
            ],
        ),
        _domain(
            "task_ee_consequence",
            status="missing",
            summary="No pawn-task or strict EE consequence was evaluated",
            detail=(
                "Unloaded response evidence cannot change the 0/11 physical task "
                "score or establish a sim-to-real task improvement."
            ),
            missing_evidence=[
                "strict_task_consequence",
                "physical_object_trajectory",
                "physical_target_consequence",
            ],
        ),
    ]
    evaluator_detail = (
        sim_evaluation.get("verdict")
        if is_shoulder
        else evaluation.get("verdict")
    )
    next_summary = (
        "Measure elbow coupling under a separately preregistered safe protocol "
        "before proposing another simulator family."
        if is_shoulder or is_elbow
        else "Capture calibrated force/current and strict pawn/EE consequence "
        "before any task-level simulator claim."
        if packet_id == "HIL-GRIPPER-05"
        else "Repair D405 finalization, then preregister a new wrist packet; do "
        "not reuse or reinterpret this rejected attempt."
    )
    publication = _as_mapping(bundle.get("publication"))
    physical_binding = _as_mapping(publication.get("physical"))
    offline_binding = _as_mapping(publication.get("offline_analysis"))
    offline_receipt = _as_mapping(offline_bundle.get("receipt"))
    decomposition_binding = _as_mapping(
        publication.get("offline_decomposition")
    )
    decomposition_receipt = _as_mapping(
        decomposition_bundle.get("receipt")
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "available": True,
        "evidence_status": (
            "physical_measurement_admitted_no_task_authority"
            if admitted
            else "physical_packet_rejected"
        ),
        "episode": {
            "id": episode.get("id"),
            "title": episode.get("title"),
            "subtitle": episode.get("subtitle"),
            "action_sha256": packet_action,
            "action_binding": "hash_bound_requested_physical_packet",
            "proof_class": [
                episode.get("proof_class"),
                *list(publication.get("proof_classes") or []),
            ],
            "proof_label": (
                f"{episode.get('proof_label') or 'Physical HIL'} · "
                "hash-bound action and evaluator"
            ),
        },
        "summary": {
            "label": (
                "Unloaded measurement admitted · task authority closed"
                if admitted and not is_shoulder
                else "Physical span admitted · simulator candidate rejected"
                if is_shoulder
                else "Physical packet rejected · no fit admitted"
            ),
            "verdict": evaluator_detail,
            "detail": (
                kinematics_detail
                + " No task score, posterior, training, promotion, or physical "
                "transfer authority changed."
            ),
        },
        "authority": dict(READ_ONLY_AUTHORITY),
        "twin_worthiness": {
            "level": "unloaded_joint_diagnostic_only",
            "allowed_capabilities": ["read_only_diagnostics"],
            "denied_capabilities": [
                "simulator_parameter_promotion",
                "task_score_change",
                "training",
                "physical_transfer",
            ],
            "verdict_owner": (
                sim_evaluation.get("evaluator_owner")
                if is_shoulder
                else evaluation.get("evaluator_owner")
            ),
        },
        "domains": domains,
        "chain": [
            {
                "id": "observe",
                "label": "Observe",
                "status": "verified",
                "detail": (
                    f"{summary.get('sample_count')} samples · "
                    f"{len(_as_rows(episode.get('recording_feeds')))} verified "
                    "camera feed(s)"
                ),
            },
            {
                "id": "residual",
                "label": "Residual",
                "status": "verified",
                "detail": (
                    f"Lag-aligned target RMSE "
                    f"{float(lag.get('lag_aligned_rmse') or 0):.3f}°"
                ),
            },
            {
                "id": "hypothesis",
                "label": "Hypothesis",
                "status": "retained" if admitted else "unresolved",
                "detail": (
                    "Pre-existing shoulder endpoint range mismatch"
                    if is_shoulder
                    else f"{summary.get('target_joint')} unloaded response"
                ),
            },
            {
                "id": "intervention",
                "label": "Intervention",
                "status": "executed_once",
                "detail": (
                    "Two action-identical simulator variants"
                    if is_shoulder
                    else "One preregistered physical packet · no retry"
                ),
            },
            {
                "id": "evaluator",
                "label": "Evaluator",
                "status": "failed" if (not admitted or is_shoulder) else "admitted",
                "detail": str(evaluator_detail),
            },
            {
                "id": "posterior_consequence",
                "label": "Posterior / consequence",
                "status": "missing",
                "detail": "No posterior movement and no strict task consequence",
            },
        ],
        "hypotheses": [
            {
                "id": (
                    "preexisting_shoulder_endpoint_range"
                    if is_shoulder
                    else f"{summary.get('target_joint')}_unloaded_response"
                ),
                "family": (
                    "Joint range and coupled response"
                    if is_shoulder or is_elbow
                    else "Unloaded actuator response"
                ),
                "before": None,
                "after": None,
                "status": (
                    "measurement_admitted_candidate_rejected"
                    if is_shoulder
                    else "measurement_admitted"
                    if admitted
                    else "packet_rejected"
                ),
                "missing_observables": list(
                    dict.fromkeys(
                        failures
                        + (
                            []
                            if plateau.get("admissible_for_scale_offset_claim")
                            is True
                            else ["scale_offset_identifiability_gate"]
                        )
                        + ["strict_task_consequence"]
                    )
                ),
            }
        ],
        "intervention": {
            "selected": (
                "follower_shoulder_lift_range_v1"
                if is_shoulder
                else packet_id
            ),
            "status": "executed_once",
            "candidate_count": 2 if is_shoulder else 1,
            "action_bytes_unchanged": (
                sim_evaluation.get("action_tensor_byte_identical")
                if is_shoulder
                else True
            ),
        },
        "evaluator": {
            "verdict": evaluator_detail,
            "consequence_status": "strict_task_consequence_unavailable",
            "strict_task_and_ee_pass_count": None,
            "candidate_count": 2 if is_shoulder else 1,
            "admitted_evaluator_owned_evidence": 1 if admitted else 0,
            "posterior_movement_permitted": False,
            "observed_information_gain_bits": None,
            "gates": (
                {
                    "target_improvement": sim_evaluation.get(
                        "target_improvement_gate_passed"
                    ),
                    "non_target_nonregression": sim_evaluation.get(
                        "non_target_regression_gate_passed"
                    ),
                    "gripper_nonregression": sim_evaluation.get(
                        "gripper_nonregression_gate_passed"
                    ),
                }
                if is_shoulder
                else {
                    "packet_admission": admitted,
                    "wrist_video_completed": wrist.get("status") == "completed",
                }
            ),
        },
        "next_evidence": {
            "status": "missing",
            "intervention_id": (
                "measurement_elbow_coupling"
                if is_shoulder or is_elbow
                else "measurement_force_and_task_consequence"
                if packet_id == "HIL-GRIPPER-05"
                else "measurement_wrist_camera_finalization"
            ),
            "summary": next_summary,
            "measurements": list(
                dict.fromkeys(
                    list(summary.get("failures") or [])
                    + list(
                        offline_report.get("remaining_prerequisites") or []
                    )
                    + list(
                        decomposition_report.get("remaining_prerequisites")
                        or []
                    )
                )
            ),
        },
        "receipt": {
            "verification": "verified",
            "receipt_sha256": physical_binding.get("receipt_sha256"),
            "receipt_digest": _as_mapping(bundle.get("evidence_receipt")).get(
                "receipt_digest"
            ),
            "packet_evaluation_sha256": _as_mapping(packet.get("event")).get(
                "evaluation_sha256"
            ),
            "simulator_receipt_sha256": (
                _as_mapping(publication.get("simulator")).get("receipt_sha256")
                if is_shoulder
                else None
            ),
            "simulator_receipt_digest": (
                sim_receipt.get("receipt_digest") if is_shoulder else None
            ),
            "offline_analysis_receipt_sha256": offline_binding.get(
                "receipt_sha256"
            ),
            "offline_analysis_receipt_digest": offline_receipt.get(
                "receipt_digest"
            ),
            "offline_decomposition_receipt_sha256": (
                decomposition_binding.get("receipt_sha256")
            ),
            "offline_decomposition_receipt_digest": (
                decomposition_receipt.get("receipt_digest")
            ),
            "publication_sha256": bundle.get("publication_sha256"),
        },
    }


def _overnight_calibration_projection(
    episode: Mapping[str, Any],
    bundle: Mapping[str, Any],
) -> dict[str, Any]:
    """Project a verified physical diagnostic without upgrading its proof class."""

    publication = _as_mapping(bundle.get("publication"))
    diagnostic = _as_mapping(bundle.get("diagnostic"))
    raw = _as_mapping(bundle.get("raw_comparison"))
    evaluation = _as_mapping(bundle.get("evaluation"))
    identifiability = _as_mapping(bundle.get("identifiability"))
    comparison_receipt = _as_mapping(bundle.get("comparison_receipt"))
    diagnostic_receipt = _as_mapping(bundle.get("diagnostic_receipt"))
    identifiability_receipt = _as_mapping(bundle.get("identifiability_receipt"))
    variants = _as_rows(raw.get("variants"))
    baseline = next(
        (row for row in variants if row.get("variant_id") == "current_declared_ranges"),
        {},
    )
    candidate = next(
        (
            row
            for row in variants
            if row.get("variant_id") == "follower_calibrated_ranges_v1"
        ),
        {},
    )
    baseline_metrics = _as_mapping(baseline.get("metrics"))
    candidate_metrics = _as_mapping(candidate.get("metrics"))
    segmentation = _as_mapping(diagnostic.get("segmentation"))
    sensitivity = _as_mapping(
        _as_mapping(diagnostic.get("owner_intended_five_cycle_sensitivity")).get(
            "summary"
        )
    )
    current = _as_mapping(diagnostic.get("current_telemetry"))
    gates = _as_mapping(evaluation.get("gates"))
    shoulder_identifiability = _as_mapping(
        identifiability.get("shoulder_lift_hypothesis")
    )
    elbow_identifiability = _as_mapping(identifiability.get("elbow_hypothesis"))
    improvement = evaluation.get("aggregate_body_joint_rmse_improvement_fraction")
    per_joint_regressions = evaluation.get("per_joint_rmse_regression_degrees")
    elbow_regression = (
        per_joint_regressions[2]
        if isinstance(per_joint_regressions, Sequence)
        and not isinstance(per_joint_regressions, (str, bytes, bytearray))
        and len(per_joint_regressions) > 2
        else None
    )
    exact_action_sha256 = comparison_receipt.get("exact_action_sha256")
    domains = [
        _domain(
            "geometry_scale",
            status="missing",
            summary="Metric scene and object geometry remain unobserved",
            detail="Both cameras recorded source pixels, but this packet contains no metric depth, calibrated camera-to-gripper extrinsics, or metric object pose.",
            missing_evidence=[
                "metric_wrist_depth",
                "camera_to_gripper_extrinsics",
                "metric_object_pose",
            ],
        ),
        _domain(
            "kinematics",
            status="failed",
            summary="Aggregate joint error fell, but the global range candidate failed",
            detail="The calibrated endpoint ranges reduced aggregate body-joint RMSE, primarily at shoulder lift, while elbow RMSE regressed beyond the frozen per-joint ceiling. The offline audit then found zero shoulder-lift command span and insufficient elbow span, so neither joint's range scale is identified. The evaluator rejected the candidate and changed no simulator parameter.",
            measurements=[
                _measurement(
                    "Current-range body RMSE",
                    value=baseline_metrics.get(
                        "aggregate_body_joint_rmse_degrees"
                    ),
                    unit="deg",
                    source="Action-identical MuJoCo replay · current declared ranges",
                ),
                _measurement(
                    "Calibrated-range body RMSE",
                    value=candidate_metrics.get(
                        "aggregate_body_joint_rmse_degrees"
                    ),
                    unit="deg",
                    source="Action-identical MuJoCo replay · follower endpoint ranges",
                ),
                _measurement(
                    "Aggregate RMSE reduction",
                    value=(
                        float(improvement) * 100.0
                        if improvement is not None
                        else None
                    ),
                    unit="%",
                    source="Independent CPU/fp32 joint-response evaluator · body-joint RMSE denominator",
                ),
                _measurement(
                    "Elbow RMSE regression",
                    value=elbow_regression,
                    unit="deg",
                    source="Independent CPU/fp32 joint-response evaluator",
                    threshold=0.25,
                    comparator="≤",
                ),
                _measurement(
                    "Shoulder-lift command span",
                    value=shoulder_identifiability.get(
                        "observed_command_span_degrees"
                    ),
                    unit="deg",
                    source="Offline unloaded joint-identifiability audit",
                    threshold=15.0,
                    comparator="≥",
                ),
                _measurement(
                    "Elbow command span",
                    value=elbow_identifiability.get(
                        "observed_command_span_degrees"
                    ),
                    unit="deg",
                    source="Offline unloaded joint-identifiability audit",
                    threshold=15.0,
                    comparator="≥",
                ),
            ],
            missing_evidence=[
                "joint_specific_range_validation",
                "strict_task_consequence",
            ],
        ),
        _domain(
            "action_timing",
            status="observed",
            summary="Five stable retrospective cycles show a repeatable gripper lag",
            detail="Six excursions were observed although five were requested. Cycles 2–6 form a retrospective sensitivity view only; the procedure mismatch prevents measurement admission.",
            measurements=[
                _measurement(
                    "Observed excursions",
                    value=segmentation.get("observed_excursion_count"),
                    unit="count",
                    source="Hash-bound follower requested-position trace",
                    threshold=segmentation.get("owner_intended_excursion_count"),
                    comparator="=",
                ),
                _measurement(
                    "Cycles 2–6 median lag",
                    value=sensitivity.get("median_best_gripper_lag_seconds"),
                    unit="s",
                    source="Retrospective non-promoting five-cycle sensitivity view",
                ),
                _measurement(
                    "Cycles 2–6 gripper RMSE",
                    value=sensitivity.get(
                        "median_lag_aligned_gripper_rmse_degrees"
                    ),
                    unit="deg",
                    source="Retrospective non-promoting five-cycle sensitivity view",
                ),
            ],
            missing_evidence=["preregistered_stationary_five_cycle_capture"],
        ),
        _domain(
            "contact_compliance",
            status="missing",
            summary="No contact or compliance measurement was captured",
            detail="The empty-gripper episode isolates unloaded motion; it cannot identify jaw force, fingertip deformation, or contact mechanics.",
            missing_evidence=["contact_force", "load_or_deformation_sensor"],
        ),
        _domain(
            "actuator_load_path",
            status="missing",
            summary="Raw current is present but not independently synchronized",
            detail="All telemetry rows carry non-stale raw current values, but no independent current-read timestamp or force calibration exists, so load-path evidence is not admitted.",
            measurements=[
                _measurement(
                    "Maximum gripper current",
                    value=(
                        current.get("maximum_raw_current_by_joint", [None] * 6)[5]
                        if isinstance(
                            current.get("maximum_raw_current_by_joint"), Sequence
                        )
                        and len(current.get("maximum_raw_current_by_joint", [])) > 5
                        else None
                    ),
                    unit="raw device units",
                    source="Follower current telemetry · diagnostic only",
                )
            ],
            missing_evidence=[
                "independent_current_read_timestamp",
                "current_to_torque_calibration",
                "jaw_force",
            ],
        ),
        _domain(
            "task_ee_consequence",
            status="missing",
            summary="No strict task or end-effector consequence was evaluated",
            detail="This was an empty-gripper response diagnostic. Aggregate error reduction alone cannot change task score or establish physical-transfer improvement.",
            missing_evidence=[
                "strict_task_consequence",
                "physical_object_trajectory",
                "physical_target_consequence",
            ],
        ),
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "available": True,
        "evidence_status": "terminal_diagnostic_no_promotion",
        "episode": {
            "id": episode.get("id"),
            "title": episode.get("title"),
            "subtitle": episode.get("subtitle"),
            "action_sha256": exact_action_sha256,
            "action_binding": "source_recording_plus_hash_bound_command_tensor",
            "proof_class": [
                episode.get("proof_class"),
                *list(publication.get("proof_classes", [])),
            ],
            "proof_label": (
                f"{episode.get('proof_label') or 'Physical source'} · "
                "action-frozen simulator diagnostic"
            ),
        },
        "summary": {
            "label": "Partial aggregate reduction · candidate rejected",
            "verdict": evaluation.get("verdict"),
            "detail": (
                "Follower endpoint ranges reduced aggregate body-joint RMSE by "
                f"{float(improvement) * 100.0:.1f}% with identical action bytes, "
                "but elbow and gripper non-regression gates failed, and the offline "
                "audit could not identify shoulder-lift or elbow range scale. No "
                "parameter, task score, training, or physical authority changed."
                if improvement is not None
                else "The verified evaluator rejected the candidate without promotion."
            ),
        },
        "authority": dict(READ_ONLY_AUTHORITY),
        "twin_worthiness": {
            "level": "diagnostic_only",
            "allowed_capabilities": ["read_only_diagnostics"],
            "denied_capabilities": [
                "simulator_parameter_promotion",
                "task_score_change",
                "training",
                "physical_authority",
            ],
            "verdict_owner": evaluation.get("evaluator_owner"),
        },
        "domains": domains,
        "chain": [
            {
                "id": "observe",
                "label": "Observe",
                "status": "verified",
                "detail": (
                    f"{diagnostic.get('sample_count')} telemetry rows · "
                    f"{segmentation.get('observed_excursion_count')} excursions · "
                    "dual-camera source coverage"
                ),
            },
            {
                "id": "residual",
                "label": "Residual",
                "status": "verified",
                "detail": (
                    f"Current-range aggregate body RMSE "
                    f"{float(baseline_metrics.get('aggregate_body_joint_rmse_degrees')):.3f}°"
                ),
            },
            {
                "id": "hypothesis",
                "label": "Hypothesis",
                "status": "retained",
                "detail": "Follower calibration endpoint ranges explain current-workcell joint-response error",
            },
            {
                "id": "intervention",
                "label": "Intervention",
                "status": "executed",
                "detail": "One frozen family · current ranges versus follower endpoint ranges · two replays",
            },
            {
                "id": "evaluator",
                "label": "Evaluator",
                "status": "failed",
                "detail": (
                    f"{evaluation.get('verdict')} · elbow and gripper "
                    "non-regression gates failed"
                ),
            },
            {
                "id": "posterior_consequence",
                "label": "Posterior / consequence",
                "status": "missing",
                "detail": "No posterior update and no strict task consequence; no promotion",
            },
        ],
        "hypotheses": [
            {
                "id": "follower_calibration_endpoint_ranges",
                "family": "Joint-specific calibration range mismatch",
                "before": None,
                "after": None,
                "status": "not_identified_insufficient_excitation",
                "missing_observables": [
                    "joint_specific_range_validation",
                    "strict_task_consequence",
                ],
            }
        ],
        "intervention": {
            "selected": "follower_calibrated_ranges_v1",
            "status": "executed_once",
            "candidate_count": 2,
            "action_bytes_unchanged": evaluation.get(
                "action_tensor_byte_identical"
            ),
        },
        "evaluator": {
            "verdict": evaluation.get("verdict"),
            "consequence_status": "strict_task_consequence_unavailable",
            "strict_task_and_ee_pass_count": None,
            "candidate_count": 2,
            "admitted_evaluator_owned_evidence": 0,
            "posterior_movement_permitted": False,
            "observed_information_gain_bits": None,
            "gates": dict(gates),
        },
        "next_evidence": {
            "status": "missing",
            "intervention_id": "measurement_joint_specific_range_validation",
            "summary": (
                "Repeat a preregistered stationary five-cycle capture with independent "
                "capture, command-application, position, and current timestamps; "
                "verify reset and calibration health; then excite shoulder lift and "
                "elbow bidirectionally before any new global simulator candidate."
            ),
            "measurements": list(
                publication.get("next_measurement_prerequisites", [])
            ),
        },
        "receipt": {
            "verification": "verified",
            "receipt_sha256": _as_mapping(publication.get("comparison")).get(
                "receipt_sha256"
            ),
            "receipt_digest": comparison_receipt.get("receipt_sha256"),
            "diagnostic_receipt_sha256": _as_mapping(
                publication.get("diagnostic")
            ).get("receipt_sha256"),
            "diagnostic_receipt_digest": diagnostic_receipt.get("receipt_sha256"),
            "identifiability_receipt_sha256": _as_mapping(
                publication.get("identifiability")
            ).get("receipt_sha256"),
            "identifiability_receipt_digest": identifiability_receipt.get(
                "receipt_sha256"
            ),
            "publication_sha256": bundle.get("publication_sha256"),
        },
    }


def _episode_projection(
    episode: Mapping[str, Any], observatory: Mapping[str, Any]
) -> tuple[Mapping[str, Any] | None, str]:
    action_sha256 = str(episode.get("action_array_sha256") or "")
    episode_id = str(episode.get("id") or "")
    rows = _as_rows(observatory.get("episodes"))
    if action_sha256:
        return (
            next(
                (
                    row
                    for row in rows
                    if str(row.get("action_array_sha256") or "") == action_sha256
                ),
                None,
            ),
            "action_sha256",
        )
    return (
        next((row for row in rows if str(row.get("id") or "") == episode_id), None),
        "episode_id_only_action_hash_unavailable",
    )


def _episode_only_domains(sail_episode: Mapping[str, Any]) -> list[dict[str, Any]]:
    metrics = _as_mapping(sail_episode.get("metrics"))
    pawn = _availability(sail_episode, "pawn")
    target = _availability(sail_episode, "target")
    timing = _availability(sail_episode, "timing")
    contact = _availability(sail_episode, "contact")
    consequence = _availability(sail_episode, "consequence")
    timing_close = _residual_cell(
        sail_episode, "selected_event_timing:near_closed_crossing"
    )
    timing_release = _residual_cell(
        sail_episode, "selected_event_timing:release_onset"
    )
    return [
        _domain(
            "geometry_scale",
            status="missing",
            summary="Physical object geometry is not metrically observed",
            detail=str(
                pawn.get("detail")
                or target.get("detail")
                or "No receipt-bound physical object trajectory or target measurement is available."
            ),
            missing_evidence=["physical_metric_object_trajectory", "physical_target_pose"],
        ),
        _domain(
            "kinematics",
            status="observed",
            summary="Retained joint and end-effector residuals are available",
            detail="These are sim-versus-retained-reference residuals, not a task-success verdict.",
            measurements=[
                _measurement(
                    "Joint RMS",
                    value=metrics.get("joint_rms_degrees"),
                    unit="deg",
                    source="SAIL observatory · selected replay",
                ),
                _measurement(
                    "EE RMS",
                    value=(
                        float(metrics["ee_rms_m"]) * 1000
                        if metrics.get("ee_rms_m") is not None
                        else None
                    ),
                    unit="mm",
                    source="SAIL observatory · selected replay",
                ),
            ],
        ),
        _domain(
            "action_timing",
            status="observed" if timing_close or timing_release else "missing",
            summary=(
                "Phase-aligned timing residuals are available"
                if timing_close or timing_release
                else "Actuation and camera latency are not identified"
            ),
            detail=str(
                timing.get("detail")
                or "No receipt-bound timing residual is available for this replay."
            ),
            measurements=[
                _measurement(
                    "Near-closed crossing residual",
                    value=timing_close.get("rmse"),
                    unit="s",
                    source="SAIL observatory · phase-aligned residual",
                ),
                _measurement(
                    "Release-onset residual",
                    value=timing_release.get("rmse"),
                    unit="s",
                    source="SAIL observatory · phase-aligned residual",
                ),
            ],
            missing_evidence=["actuation_latency", "camera_latency"],
        ),
        _domain(
            "contact_compliance",
            status="missing",
            summary="Physical contact and deformation are not instrumented",
            detail=str(
                contact.get("detail")
                or "Physical contact state, jaw force, and rubber deformation are unavailable."
            ),
            missing_evidence=[
                "jaw_force",
                "rubber_cap_deformation_profile",
                "physical_contact_state",
            ],
        ),
        _domain(
            "actuator_load_path",
            status="missing",
            summary="The loaded actuator path is not independently identified",
            detail="Joint traces exist, but synchronized jaw force is missing, so load-path causality remains unresolved.",
            missing_evidence=["jaw_force", "joint_current_force_alignment"],
        ),
        _domain(
            "task_ee_consequence",
            status="missing",
            summary="Physical task consequence is unavailable",
            detail=str(
                consequence.get("detail")
                or "Simulator outcome is not physical task evidence."
            ),
            measurements=[
                _measurement(
                    "Final target gap",
                    value=(
                        float(metrics["final_target_distance_m"]) * 1000
                        if metrics.get("final_target_distance_m") is not None
                        else None
                    ),
                    unit="mm",
                    source="SAIL observatory · simulator replay",
                )
            ],
            missing_evidence=["physical_task_consequence"],
        ),
    ]


def _live_domains(
    sail_episode: Mapping[str, Any],
    *,
    evaluation: Mapping[str, Any],
    consequence: Mapping[str, Any],
    thresholds: Mapping[str, Any],
) -> list[dict[str, Any]]:
    domains = _episode_only_domains(sail_episode)
    baseline = next(
        (
            row
            for row in _as_rows(evaluation.get("candidate_results"))
            if row.get("candidate_id") == "baseline"
        ),
        {},
    )
    anchor = _as_mapping(baseline.get("anchor_evaluation"))
    trace = _as_mapping(anchor.get("trace_metrics"))
    domains[1] = _domain(
        "kinematics",
        status="observed",
        summary="Kinematic residuals are within the frozen local ceilings",
        detail="Passing these local ceilings is diagnostic only; it did not satisfy the joint task-and-EE consequence gate.",
        measurements=[
            _measurement(
                "Joint RMS",
                value=trace.get("overall_joint_rms_degrees"),
                unit="deg",
                source="Independent CPU/fp32 C2 evaluator · baseline",
                threshold=thresholds.get("maximum_joint_rms_degrees"),
                comparator="≤",
            ),
            _measurement(
                "EE RMS",
                value=(
                    float(trace["ee_rms_m"]) * 1000
                    if trace.get("ee_rms_m") is not None
                    else None
                ),
                unit="mm",
                source="Independent CPU/fp32 C2 evaluator · baseline",
                threshold=(
                    float(thresholds["maximum_ee_rms_m"]) * 1000
                    if thresholds.get("maximum_ee_rms_m") is not None
                    else None
                ),
                comparator="≤",
            ),
        ],
    )
    main_effects = _as_mapping(evaluation.get("main_effects"))
    effect_evidence = _as_mapping(evaluation.get("effect_evidence"))
    domains[3] = _domain(
        "contact_compliance",
        status="missing",
        summary="Flexural effect observed; physical mechanism unresolved",
        detail="The preregistered flexural contrast changed the diagnostic response, but jaw force and rubber-cap deformation were not measured.",
        measurements=[
            _measurement(
                "Flexural main effect",
                value=main_effects.get("flexural_contact"),
                unit="normalized response",
                source="Independent CPU/fp32 C2 evaluator",
            )
        ],
        missing_evidence=["jaw_force", "rubber_cap_deformation_profile"],
    )
    domains[3]["mechanism_effect_observed"] = (
        effect_evidence.get("flexural_contact") is True
    )
    domains[4] = _domain(
        "actuator_load_path",
        status="missing",
        summary="Actuator effect observed; load path unresolved",
        detail="The preregistered load-path contrast changed the diagnostic response, but synchronized jaw force is unavailable.",
        measurements=[
            _measurement(
                "Actuator main effect",
                value=main_effects.get("actuator_load_path"),
                unit="normalized response",
                source="Independent CPU/fp32 C2 evaluator",
            )
        ],
        missing_evidence=["jaw_force"],
    )
    domains[4]["mechanism_effect_observed"] = (
        effect_evidence.get("actuator_load_path") is True
    )
    strict_passes = consequence.get("strict_task_and_ee_pass_count")
    candidate_count = consequence.get("candidate_count")
    domains[5] = _domain(
        "task_ee_consequence",
        status="failed",
        summary="Evaluator rejected the preregistered intervention",
        detail="Mechanism effects were diagnostic, but no candidate jointly passed the strict task and end-effector consequence gates.",
        measurements=[
            _measurement(
                "Strict task + EE passes",
                value=strict_passes,
                unit=f"of {candidate_count}" if candidate_count is not None else "count",
                source="Independent CPU/fp32 C2 evaluator",
                threshold=1,
                comparator="≥",
            )
        ],
        missing_evidence=["admitted_joint_mechanism_and_task_consequence"],
    )
    return domains


def project_twin_fidelity(
    episode: Mapping[str, Any],
    observatory: Mapping[str, Any],
    *,
    live_receipt: Mapping[str, Any] | None = None,
    live_outputs: Mapping[str, Mapping[str, Any]] | None = None,
    live_verification: Mapping[str, Any] | None = None,
    adapter_evaluation: Mapping[str, Any] | None = None,
    adapter_thresholds: Mapping[str, Any] | None = None,
    live_error: str | None = None,
) -> dict[str, Any]:
    """Project existing evidence into a replay-scoped, non-scoring fidelity view."""

    sail_episode, episode_binding = _episode_projection(episode, observatory)
    if sail_episode is None:
        return _unavailable_projection(
            episode,
            reason=(
                "action_hash_not_in_receipt_bound_observatory"
                if episode.get("action_array_sha256")
                else "episode_not_in_receipt_bound_observatory"
            ),
            detail=(
                "The selected replay action hash has no exact match in the receipt-bound SAIL observatory; episode-ID fallback is prohibited."
                if episode.get("action_array_sha256")
                else "This replay has neither an action hash nor an episode-ID-matched SAIL observatory record."
            ),
        )

    action_sha256 = str(episode.get("action_array_sha256") or "")
    outputs = live_outputs or {}
    receipt = live_receipt or {}
    campaign_matches = bool(
        action_sha256
        and receipt
        and str(receipt.get("action_sha256") or "") == action_sha256
    )
    posterior = _as_mapping(outputs.get("posterior"))
    mechanisms = _as_rows(_as_mapping(outputs.get("mechanism_status")).get("mechanisms"))
    consequence = _as_mapping(outputs.get("consequence"))
    acquisition = _as_mapping(outputs.get("acquisition_ranking"))
    live_complete = bool(
        campaign_matches
        and live_verification
        and adapter_evaluation
        and posterior
        and mechanisms
        and consequence
    )

    if live_complete:
        domains = _live_domains(
            sail_episode,
            evaluation=adapter_evaluation or {},
            consequence=consequence,
            thresholds=adapter_thresholds or {},
        )
        evidence_status = "terminal_negative"
        summary = {
            "label": "Terminal negative",
            "verdict": str(receipt.get("verdict") or "evaluator_reject"),
            "detail": "The single preregistered four-replay intervention was evaluator-rejected. Posterior belief remained unchanged; no simulator, training, or physical authority opened.",
        }
    else:
        domains = _episode_only_domains(sail_episode)
        evidence_status = "episode_evidence_only"
        summary = {
            "label": "Replay evidence only",
            "verdict": "no_action_matched_terminal_campaign",
            "detail": (
                "This replay has receipt-bound residual evidence, but no verified terminal campaign is action-hash-matched to it."
                if not live_error
                else f"The terminal campaign projection is unavailable: {live_error}"
            ),
        }

    hypotheses = []
    before = _as_mapping(posterior.get("before"))
    after = _as_mapping(posterior.get("after"))
    for mechanism in mechanisms:
        mechanism_id = str(mechanism.get("mechanism_id") or "")
        hypotheses.append(
            {
                "id": mechanism_id,
                "family": mechanism.get("family"),
                "before": before.get(mechanism_id),
                "after": after.get(mechanism_id),
                "status": (
                    "unchanged"
                    if before.get(mechanism_id) == after.get(mechanism_id)
                    else "updated"
                ),
                "missing_observables": list(
                    dict.fromkeys(
                        str(value)
                        for value in _as_rows_or_strings(
                            mechanism.get("missing_observables")
                        )
                    )
                ),
            }
        )

    next_row = next(
        (
            row
            for row in _as_rows(acquisition.get("rows"))
            if row.get("kind") == "measurement_acquisition"
        ),
        {},
    )
    missing_measurements = list(
        dict.fromkeys(
            value
            for row in mechanisms
            for value in _as_rows_or_strings(row.get("missing_observables"))
        )
    )
    chain = []
    if live_complete:
        budget = _as_mapping(receipt.get("budget"))
        chain = [
            {
                "id": "observe",
                "label": "Observe",
                "status": "verified",
                "detail": f"{budget.get('used_anchor_replays', 0)} action-identical anchor replays",
            },
            {
                "id": "residual",
                "label": "Residual",
                "status": "verified",
                "detail": f"{len(_as_rows(_as_mapping(outputs.get('residual_evidence')).get('residuals')))} retained C2 residuals",
            },
            {
                "id": "hypothesis",
                "label": "Hypothesis",
                "status": "retained",
                "detail": f"{len(hypotheses)} competing mechanisms",
            },
            {
                "id": "intervention",
                "label": "Intervention",
                "status": "executed",
                "detail": str(receipt.get("selected_intervention") or "Unavailable"),
            },
            {
                "id": "evaluator",
                "label": "Evaluator",
                "status": "failed",
                "detail": f"{receipt.get('verdict')} · strict {consequence.get('strict_task_and_ee_pass_count', 0)}/{consequence.get('candidate_count', 0)}",
            },
            {
                "id": "posterior_consequence",
                "label": "Posterior / consequence",
                "status": "unchanged",
                "detail": f"0.5 → 0.5 · IG {posterior.get('observed_information_gain_bits')} bits",
            },
        ]

    proof_label = (
        sail_episode.get("proof_label")
        or episode.get("proof_label")
        or "Replay evidence"
    )
    if episode_binding != "action_sha256":
        proof_label = f"{proof_label} · episode ID only; action hash unavailable"

    return {
        "schema_version": SCHEMA_VERSION,
        "available": True,
        "evidence_status": evidence_status,
        "episode": {
            "id": episode.get("id"),
            "title": episode.get("title"),
            "subtitle": episode.get("subtitle"),
            "action_sha256": action_sha256 or None,
            "action_binding": (
                "byte_identical_campaign_match"
                if campaign_matches
                else episode_binding
            ),
            "proof_class": sail_episode.get("proof_class")
            or episode.get("proof_class"),
            "proof_label": proof_label,
        },
        "summary": summary,
        "authority": dict(READ_ONLY_AUTHORITY),
        "twin_worthiness": {
            "level": _as_mapping(observatory.get("twin_worthiness")).get("level"),
            "allowed_capabilities": list(
                _as_mapping(observatory.get("twin_worthiness")).get(
                    "allowed_capabilities", []
                )
            ),
            "denied_capabilities": list(
                _as_mapping(observatory.get("twin_worthiness")).get(
                    "denied_capabilities", []
                )
            ),
            "verdict_owner": "learning_factory",
        },
        "domains": domains,
        "chain": chain,
        "hypotheses": hypotheses,
        "intervention": {
            "selected": receipt.get("selected_intervention") if live_complete else None,
            "status": "executed_once" if live_complete else "unavailable",
            "candidate_count": consequence.get("candidate_count") if live_complete else None,
            "action_bytes_unchanged": (
                receipt.get("action_bytes_unchanged") is True if live_complete else None
            ),
        },
        "evaluator": {
            "verdict": receipt.get("verdict") if live_complete else None,
            "consequence_status": consequence.get("status") if live_complete else None,
            "strict_task_and_ee_pass_count": (
                consequence.get("strict_task_and_ee_pass_count")
                if live_complete
                else None
            ),
            "candidate_count": consequence.get("candidate_count") if live_complete else None,
            "admitted_evaluator_owned_evidence": (
                consequence.get("admitted_evaluator_owned_evidence")
                if live_complete
                else None
            ),
            "posterior_movement_permitted": (
                consequence.get("posterior_movement_permitted")
                if live_complete
                else None
            ),
            "observed_information_gain_bits": (
                posterior.get("observed_information_gain_bits")
                if live_complete
                else None
            ),
        },
        "next_evidence": {
            "status": str(next_row.get("availability") or "missing"),
            "intervention_id": next_row.get("intervention_id"),
            "summary": (
                "Acquire independently calibrated, synchronized force, deformation, angle, and current evidence before another simulator family."
                if live_complete
                else "No action-matched terminal campaign defines the next evidence prerequisite."
            ),
            "measurements": missing_measurements,
        },
        "receipt": {
            "verification": "verified" if live_complete else "unavailable",
            "receipt_sha256": (
                _as_mapping(live_verification).get("receipt_sha256")
                if live_complete
                else None
            ),
            "receipt_digest": receipt.get("receipt_digest") if live_complete else None,
            "campaign_state_sha256": (
                _as_mapping(live_verification).get("campaign_state_sha256")
                if live_complete
                else None
            ),
        },
    }


def _as_rows_or_strings(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [str(row) for row in value]


def _load_live_bundle(repo_root: Path) -> dict[str, Any]:
    receipt_path = repo_root / DEFAULT_LIVE_OPERATOR_RECEIPT
    verification = verify_live_operator_receipt(receipt_path, repo_root=repo_root)
    receipt = load_json_object(receipt_path, label="Studio live-operator receipt")
    outputs: dict[str, Mapping[str, Any]] = {}
    for name in (
        "residual_evidence",
        "mechanism_status",
        "acquisition_ranking",
        "posterior",
        "consequence",
    ):
        binding = _as_mapping(_as_mapping(receipt.get("outputs")).get(name))
        relative = str(binding.get("path") or "")
        if not relative:
            raise TwinFidelityError(f"live operator {name} output binding is missing")
        outputs[name] = load_json_object(
            receipt_path.parent / relative,
            label=f"Studio live-operator {name}",
        )
    evaluation = load_json_object(
        receipt_path.parent / "trusted_adapter" / "evaluation.json",
        label="Studio trusted-adapter evaluation",
    )
    adapter_contract = load_json_object(
        repo_root / DEFAULT_ADAPTER_CONTRACT,
        label="Studio trusted-adapter contract",
    )
    return {
        "receipt": receipt,
        "verification": verification,
        "outputs": outputs,
        "evaluation": evaluation,
        "thresholds": _as_mapping(adapter_contract.get("consequence_thresholds")),
    }


def load_twin_fidelity_projection(
    episode: Mapping[str, Any], *, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    """Verify current evidence and return a selected-replay projection."""

    resolved_root = repo_root.resolve()
    try:
        hil_binding = load_hil_publication_binding(repo_root=resolved_root)
    except (OSError, ValueError):
        hil_binding = {}
    if str(episode.get("source_recording_id") or "") in set(
        hil_binding.get("packet_ids") or []
    ):
        try:
            hil_bundle = verify_hil_publication(repo_root=resolved_root)
        except (OSError, ValueError) as error:
            return _unavailable_projection(
                episode,
                reason="hil_publication_unavailable",
                detail=str(error),
            )
        return _hil_identifiability_projection(episode, hil_bundle)
    try:
        calibration_binding = load_overnight_calibration_binding(
            repo_root=resolved_root
        )
    except (OSError, ValueError):
        calibration_binding = {}
    if (
        calibration_binding
        and str(episode.get("source_recording_id") or "")
        == str(calibration_binding.get("source_recording_id") or "")
    ):
        try:
            calibration_bundle = verify_overnight_calibration_publication(
                repo_root=resolved_root
            )
        except (OSError, ValueError) as error:
            return _unavailable_projection(
                episode,
                reason="overnight_calibration_publication_unavailable",
                detail=str(error),
            )
        return _overnight_calibration_projection(episode, calibration_bundle)
    try:
        observatory = load_studio_observatory(repo_root=resolved_root)
    except (OSError, ValueError) as error:
        return _unavailable_projection(
            episode,
            reason="sail_observatory_unavailable",
            detail=str(error),
        )
    try:
        live = _load_live_bundle(resolved_root)
    except (OSError, ValueError) as error:
        return project_twin_fidelity(
            episode,
            observatory,
            live_error=str(error),
        )
    return project_twin_fidelity(
        episode,
        observatory,
        live_receipt=live["receipt"],
        live_outputs=live["outputs"],
        live_verification=live["verification"],
        adapter_evaluation=live["evaluation"],
        adapter_thresholds=live["thresholds"],
    )


__all__ = [
    "DOMAIN_ORDER",
    "SCHEMA_VERSION",
    "TwinFidelityError",
    "_hil_identifiability_projection",
    "_overnight_calibration_projection",
    "load_twin_fidelity_projection",
    "project_twin_fidelity",
]
