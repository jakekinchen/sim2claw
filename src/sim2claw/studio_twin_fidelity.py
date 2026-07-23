"""Read-only, receipt-verified Twin fidelity projection for Studio replays."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from .paths import REPO_ROOT
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


def _episode_projection(
    episode: Mapping[str, Any], observatory: Mapping[str, Any]
) -> Mapping[str, Any] | None:
    action_sha256 = str(episode.get("action_array_sha256") or "")
    episode_id = str(episode.get("id") or "")
    rows = _as_rows(observatory.get("episodes"))
    by_action = next(
        (
            row
            for row in rows
            if action_sha256
            and str(row.get("action_array_sha256") or "") == action_sha256
        ),
        None,
    )
    if by_action is not None:
        return by_action
    return next((row for row in rows if str(row.get("id") or "") == episode_id), None)


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

    sail_episode = _episode_projection(episode, observatory)
    if sail_episode is None:
        return _unavailable_projection(
            episode,
            reason="episode_not_in_receipt_bound_observatory",
            detail="This replay has no action-hash-matched SAIL observatory record.",
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
                else "no_terminal_campaign_match"
            ),
            "proof_class": sail_episode.get("proof_class")
            or episode.get("proof_class"),
            "proof_label": sail_episode.get("proof_label")
            or episode.get("proof_label"),
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
    "load_twin_fidelity_projection",
    "project_twin_fidelity",
]
