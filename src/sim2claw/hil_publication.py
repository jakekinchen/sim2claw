"""Fail-closed publication boundary for the bounded HIL identifiability evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .hil_evidence import (
    RECEIPT_SCHEMA as EVIDENCE_RECEIPT_SCHEMA,
    SUMMARY_SCHEMA,
    derive_hil_evidence_summary,
)
from .hil_identifiability import (
    CAMPAIGN_SCHEMA,
    EVALUATION_SCHEMA,
    RAW_RECEIPT_SCHEMA,
)
from .hil_simulator_comparison import (
    EVALUATION_SCHEMA as SIM_EVALUATION_SCHEMA,
    RAW_SCHEMA as SIM_RAW_SCHEMA,
    RECEIPT_SCHEMA as SIM_RECEIPT_SCHEMA,
    _evaluate as evaluate_simulator_comparison,
)
from .hil_trace_analysis import (
    RECEIPT_SCHEMA as TRACE_RECEIPT_SCHEMA,
    REPORT_SCHEMA as TRACE_REPORT_SCHEMA,
    derive_hil_trace_report_payload,
)
from .hil_trace_decomposition import (
    RECEIPT_SCHEMA as DECOMPOSITION_RECEIPT_SCHEMA,
    REPORT_SCHEMA as DECOMPOSITION_REPORT_SCHEMA,
    derive_hil_trace_decomposition_payload,
)
from .learning_factory_artifacts import canonical_digest, sha256_file
from .paths import REPO_ROOT
from .sail.importers import load_json_object


SCHEMA_VERSION = "sim2claw.hil_identifiability_publication.v1"
DEFAULT_PUBLICATION_PATH = Path(
    "configs/evaluations/current_100mm_hil_publication_v1.json"
)


class HILPublicationError(ValueError):
    """The tracked HIL publication or a bound evidence artifact is invalid."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise HILPublicationError(message)


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    _require(isinstance(value, Mapping), f"{label} must be an object.")
    return value


def _repo_path(repo_root: Path, value: object, *, label: str) -> Path:
    root = repo_root.resolve()
    path = (root / str(value)).resolve()
    _require(path.is_relative_to(root), f"{label} escapes the repository.")
    return path


def _verify_file(path: Path, expected: object, *, label: str) -> None:
    _require(path.is_file(), f"{label} is unavailable.")
    _require(sha256_file(path) == str(expected), f"{label} hash changed.")


def load_hil_publication_binding(
    *,
    repo_root: Path = REPO_ROOT,
    publication_path: Path = DEFAULT_PUBLICATION_PATH,
) -> dict[str, Any]:
    path = _repo_path(repo_root, publication_path, label="HIL publication")
    publication = load_json_object(path, label="HIL publication")
    _require(
        publication.get("schema_version") == SCHEMA_VERSION,
        "Unsupported HIL publication.",
    )
    _require(
        publication.get("status")
        == (
            "frozen_four_packets_two_admitted_two_rejected_"
            "one_simulator_comparison_two_offline_trace_audits"
        ),
        "HIL publication is not frozen.",
    )
    packet_ids = publication.get("packet_ids")
    _require(
        packet_ids
        == [
            "HIL-GRIPPER-05",
            "HIL-SHOULDER-LIFT-22",
            "HIL-ELBOW-FLEX-22",
            "HIL-WRIST-FLEX-30",
        ],
        "HIL publication packet identities changed.",
    )
    return publication


def verify_hil_publication(
    *,
    repo_root: Path = REPO_ROOT,
    publication_path: Path = DEFAULT_PUBLICATION_PATH,
) -> dict[str, Any]:
    """Verify hashes and independently re-derive existing evaluator outputs.

    This is deterministic integrity and evaluator re-derivation, not a hostile
    code sandbox and not a replay of either the robot or simulator.
    """

    root = repo_root.resolve()
    publication = load_hil_publication_binding(
        repo_root=root,
        publication_path=publication_path,
    )
    authority = _mapping(publication.get("authority"), "HIL authority")
    _require(
        authority and all(value is False for value in authority.values()),
        "HIL publication widened authority.",
    )
    physical = _mapping(publication.get("physical"), "Physical binding")
    offline_analysis = _mapping(
        publication.get("offline_analysis"), "Offline analysis binding"
    )
    offline_decomposition = _mapping(
        publication.get("offline_decomposition"),
        "Offline decomposition binding",
    )
    simulator = _mapping(publication.get("simulator"), "Simulator binding")

    contract_path = _repo_path(
        root, physical.get("contract_path"), label="HIL contract"
    )
    campaign_root = _repo_path(
        root, physical.get("campaign_root"), label="HIL campaign root"
    )
    campaign_path = campaign_root / "campaign_state.json"
    evidence_root = _repo_path(
        root, physical.get("evidence_root"), label="HIL evidence root"
    )
    summary_path = evidence_root / "summary.json"
    evidence_receipt_path = evidence_root / "receipt.json"
    for path, expected, label in (
        (contract_path, physical.get("contract_sha256"), "HIL contract"),
        (
            campaign_path,
            physical.get("campaign_state_sha256"),
            "HIL campaign state",
        ),
        (summary_path, physical.get("summary_sha256"), "HIL evidence summary"),
        (
            evidence_receipt_path,
            physical.get("receipt_sha256"),
            "HIL evidence receipt",
        ),
    ):
        _verify_file(path, expected, label=label)

    campaign = load_json_object(campaign_path, label="HIL campaign state")
    summary = load_json_object(summary_path, label="HIL evidence summary")
    evidence_receipt = load_json_object(
        evidence_receipt_path, label="HIL evidence receipt"
    )
    _require(
        campaign.get("schema_version") == CAMPAIGN_SCHEMA,
        "HIL campaign schema changed.",
    )
    _require(
        summary.get("schema_version") == SUMMARY_SCHEMA,
        "HIL summary schema changed.",
    )
    _require(
        evidence_receipt.get("schema_version") == EVIDENCE_RECEIPT_SCHEMA,
        "HIL evidence receipt schema changed.",
    )
    unsigned_evidence_receipt = {
        key: value
        for key, value in evidence_receipt.items()
        if key != "receipt_digest"
    }
    _require(
        canonical_digest(unsigned_evidence_receipt)
        == evidence_receipt.get("receipt_digest")
        == physical.get("embedded_receipt_digest"),
        "HIL evidence receipt digest is invalid.",
    )
    rederived_summary = derive_hil_evidence_summary(
        campaign_root,
        contract_path=contract_path,
    )
    _require(
        summary == rederived_summary,
        "HIL evidence summary no longer re-derives from packet evidence.",
    )
    events = campaign.get("events")
    _require(
        isinstance(events, list)
        and len(events) == 4
        and int(_mapping(campaign.get("budget"), "HIL budget").get(
            "used_physical_packet_attempts", -1
        ))
        == 4,
        "HIL physical attempt accounting changed.",
    )
    packets_by_id = {
        str(row["packet_id"]): row
        for row in summary.get("packets", [])
        if isinstance(row, Mapping) and row.get("packet_id")
    }
    verified_packets: list[dict[str, Any]] = []
    for event in events:
        event = _mapping(event, "HIL campaign event")
        packet_id = str(event.get("packet_id") or "")
        _require(packet_id in publication["packet_ids"], "Unknown HIL packet.")
        session = (campaign_root / packet_id).resolve()
        _require(
            session.is_relative_to(campaign_root)
            and session.name == packet_id
            and session.is_dir(),
            f"HIL packet directory is invalid: {packet_id}",
        )
        raw_path = session / "raw_receipt.json"
        evaluation_path = session / "evaluation.json"
        _verify_file(
            raw_path, event.get("raw_receipt_sha256"), label=f"{packet_id} raw receipt"
        )
        _verify_file(
            evaluation_path,
            event.get("evaluation_sha256"),
            label=f"{packet_id} evaluation",
        )
        raw = load_json_object(raw_path, label=f"{packet_id} raw receipt")
        evaluation = load_json_object(
            evaluation_path, label=f"{packet_id} evaluation"
        )
        _require(
            raw.get("schema_version") == RAW_RECEIPT_SCHEMA
            and evaluation.get("schema_version") == EVALUATION_SCHEMA,
            f"{packet_id} evidence schema changed.",
        )
        _require(
            raw.get("packet_id") == packet_id
            and raw.get("action_tensor_sha256")
            == event.get("action_tensor_sha256"),
            f"{packet_id} action binding changed.",
        )
        _require(
            raw.get("task_success_verified") is False
            and raw.get("training_admission") is False
            and raw.get("promotion_authority") is False
            and raw.get("physical_follower_torque_enabled_after") is False,
            f"{packet_id} authority widened.",
        )
        raw_unsigned = {
            key: value for key, value in raw.items() if key != "raw_receipt_digest"
        }
        _require(
            canonical_digest(raw_unsigned) == raw.get("raw_receipt_digest"),
            f"{packet_id} raw receipt digest is invalid.",
        )
        artifact_hashes = _mapping(
            raw.get("artifact_sha256"), f"{packet_id} artifact hashes"
        )
        for relative, expected in artifact_hashes.items():
            artifact = (session / str(relative)).resolve()
            _require(
                artifact.is_relative_to(session),
                f"{packet_id} artifact escapes its packet directory.",
            )
            _verify_file(
                artifact,
                expected,
                label=f"{packet_id} artifact {relative}",
            )
        packet_summary = packets_by_id.get(packet_id)
        _require(packet_summary is not None, f"{packet_id} summary is missing.")
        _require(
            bool(event.get("admitted")) is bool(packet_summary.get("admitted"))
            and event.get("verdict") == packet_summary.get("verdict")
            and evaluation.get("admitted") is bool(packet_summary.get("admitted")),
            f"{packet_id} evaluator outcome changed.",
        )
        verified_packets.append(
            {
                "packet_id": packet_id,
                "session_relative": session.relative_to(root).as_posix(),
                "event": dict(event),
                "raw": raw,
                "evaluation": evaluation,
                "summary": dict(packet_summary),
            }
        )

    analysis_contract_path = _repo_path(
        root,
        offline_analysis.get("contract_path"),
        label="HIL offline analysis contract",
    )
    analysis_output_root = _repo_path(
        root,
        offline_analysis.get("output_root"),
        label="HIL offline analysis output",
    )
    analysis_report_path = analysis_output_root / "report.json"
    analysis_receipt_path = analysis_output_root / "receipt.json"
    for path, expected, label in (
        (
            analysis_contract_path,
            offline_analysis.get("contract_sha256"),
            "HIL offline analysis contract",
        ),
        (
            analysis_report_path,
            offline_analysis.get("report_sha256"),
            "HIL offline analysis report",
        ),
        (
            analysis_receipt_path,
            offline_analysis.get("receipt_sha256"),
            "HIL offline analysis receipt",
        ),
    ):
        _verify_file(path, expected, label=label)
    analysis_report = load_json_object(
        analysis_report_path, label="HIL offline analysis report"
    )
    analysis_receipt = load_json_object(
        analysis_receipt_path, label="HIL offline analysis receipt"
    )
    _require(
        analysis_report.get("schema_version") == TRACE_REPORT_SCHEMA
        and analysis_receipt.get("schema_version") == TRACE_RECEIPT_SCHEMA,
        "HIL offline analysis output schema changed.",
    )
    rederived_analysis = derive_hil_trace_report_payload(
        contract_path=analysis_contract_path,
        repo_root=root,
    )
    _require(
        analysis_report == rederived_analysis,
        "HIL offline analysis no longer re-derives from packet telemetry.",
    )
    analysis_unsigned = {
        key: value
        for key, value in analysis_receipt.items()
        if key != "receipt_digest"
    }
    _require(
        canonical_digest(analysis_unsigned)
        == analysis_receipt.get("receipt_digest")
        == offline_analysis.get("embedded_receipt_digest"),
        "HIL offline analysis receipt digest is invalid.",
    )
    _require(
        analysis_receipt.get("contract_sha256")
        == offline_analysis.get("contract_sha256")
        and analysis_receipt.get("report_sha256")
        == offline_analysis.get("report_sha256")
        and analysis_receipt.get("packet_count") == 4
        and analysis_receipt.get("additional_physical_attempts") == 0
        and analysis_receipt.get("additional_simulator_replays") == 0
        and analysis_receipt.get("provider_calls") == 0
        and analysis_receipt.get("simulator_parameter_promoted") is False
        and analysis_receipt.get("task_score_changed") is False,
        "HIL offline analysis budget or authority changed.",
    )
    _require(
        [
            (row.get("packet_id"), row.get("action_tensor_sha256"))
            for row in analysis_report.get("packets", [])
            if isinstance(row, Mapping)
        ]
        == [
            (
                packet_id,
                packets_by_id[packet_id]["action_tensor_sha256"],
            )
            for packet_id in publication["packet_ids"]
        ],
        "HIL offline analysis packet or action binding changed.",
    )

    decomposition_contract_path = _repo_path(
        root,
        offline_decomposition.get("contract_path"),
        label="HIL offline decomposition contract",
    )
    decomposition_output_root = _repo_path(
        root,
        offline_decomposition.get("output_root"),
        label="HIL offline decomposition output",
    )
    decomposition_report_path = decomposition_output_root / "report.json"
    decomposition_receipt_path = decomposition_output_root / "receipt.json"
    for path, expected, label in (
        (
            decomposition_contract_path,
            offline_decomposition.get("contract_sha256"),
            "HIL offline decomposition contract",
        ),
        (
            decomposition_report_path,
            offline_decomposition.get("report_sha256"),
            "HIL offline decomposition report",
        ),
        (
            decomposition_receipt_path,
            offline_decomposition.get("receipt_sha256"),
            "HIL offline decomposition receipt",
        ),
    ):
        _verify_file(path, expected, label=label)
    decomposition_report = load_json_object(
        decomposition_report_path,
        label="HIL offline decomposition report",
    )
    decomposition_receipt = load_json_object(
        decomposition_receipt_path,
        label="HIL offline decomposition receipt",
    )
    _require(
        decomposition_report.get("schema_version")
        == DECOMPOSITION_REPORT_SCHEMA
        and decomposition_receipt.get("schema_version")
        == DECOMPOSITION_RECEIPT_SCHEMA,
        "HIL offline decomposition output schema changed.",
    )
    _require(
        decomposition_report
        == derive_hil_trace_decomposition_payload(
            contract_path=decomposition_contract_path,
            repo_root=root,
        ),
        "HIL offline decomposition no longer re-derives from packet telemetry.",
    )
    decomposition_unsigned = {
        key: value
        for key, value in decomposition_receipt.items()
        if key != "receipt_digest"
    }
    _require(
        canonical_digest(decomposition_unsigned)
        == decomposition_receipt.get("receipt_digest")
        == offline_decomposition.get("embedded_receipt_digest"),
        "HIL offline decomposition receipt digest is invalid.",
    )
    _require(
        decomposition_receipt.get("contract_sha256")
        == offline_decomposition.get("contract_sha256")
        and decomposition_receipt.get("report_sha256")
        == offline_decomposition.get("report_sha256")
        and decomposition_receipt.get("packet_count") == 4
        and decomposition_receipt.get("additional_physical_attempts") == 0
        and decomposition_receipt.get("additional_simulator_replays") == 0
        and decomposition_receipt.get("evaluator_provider_calls") == 0
        and decomposition_receipt.get("simulator_parameter_promoted") is False
        and decomposition_receipt.get("task_score_changed") is False,
        "HIL offline decomposition budget or authority changed.",
    )
    _require(
        [
            (
                row.get("packet_id"),
                _mapping(row.get("action_identity"), "Action identity").get(
                    "requested_action_sha256"
                ),
            )
            for row in decomposition_report.get("packets", [])
            if isinstance(row, Mapping)
        ]
        == [
            (
                packet_id,
                packets_by_id[packet_id]["action_tensor_sha256"],
            )
            for packet_id in publication["packet_ids"]
        ],
        "HIL offline decomposition requested-action binding changed.",
    )

    sim_contract_path = _repo_path(
        root, simulator.get("contract_path"), label="HIL simulator contract"
    )
    sim_output_root = _repo_path(
        root, simulator.get("output_root"), label="HIL simulator output"
    )
    sim_raw_path = sim_output_root / "raw_comparison.json"
    sim_evaluation_path = sim_output_root / "evaluation.json"
    sim_receipt_path = sim_output_root / "receipt.json"
    for path, expected, label in (
        (
            sim_contract_path,
            simulator.get("contract_sha256"),
            "HIL simulator contract",
        ),
        (
            sim_raw_path,
            simulator.get("raw_comparison_sha256"),
            "HIL simulator raw comparison",
        ),
        (
            sim_evaluation_path,
            simulator.get("evaluation_sha256"),
            "HIL simulator evaluation",
        ),
        (
            sim_receipt_path,
            simulator.get("receipt_sha256"),
            "HIL simulator receipt",
        ),
    ):
        _verify_file(path, expected, label=label)
    sim_contract = load_json_object(
        sim_contract_path, label="HIL simulator contract"
    )
    sim_raw = load_json_object(sim_raw_path, label="HIL simulator raw comparison")
    sim_evaluation = load_json_object(
        sim_evaluation_path, label="HIL simulator evaluation"
    )
    sim_receipt = load_json_object(
        sim_receipt_path, label="HIL simulator receipt"
    )
    _require(
        sim_raw.get("schema_version") == SIM_RAW_SCHEMA
        and sim_evaluation.get("schema_version") == SIM_EVALUATION_SCHEMA
        and sim_receipt.get("schema_version") == SIM_RECEIPT_SCHEMA,
        "HIL simulator output schema changed.",
    )
    _require(
        evaluate_simulator_comparison(
            _mapping(sim_raw.get("baseline"), "Simulator baseline"),
            _mapping(sim_raw.get("candidate"), "Simulator candidate"),
            sim_contract,
        )
        == sim_evaluation,
        "HIL simulator evaluation no longer re-derives from its raw comparison.",
    )
    sim_unsigned = {
        key: value for key, value in sim_receipt.items() if key != "receipt_digest"
    }
    _require(
        canonical_digest(sim_unsigned)
        == sim_receipt.get("receipt_digest")
        == simulator.get("embedded_receipt_digest"),
        "HIL simulator receipt digest is invalid.",
    )
    trace_hashes = _mapping(sim_receipt.get("trace_sha256"), "Simulator traces")
    _require(
        trace_hashes == _mapping(simulator.get("trace_sha256"), "Published traces"),
        "HIL simulator trace bindings changed.",
    )
    for relative, expected in trace_hashes.items():
        trace_path = (sim_output_root / str(relative)).resolve()
        _require(
            trace_path.is_relative_to(sim_output_root),
            "HIL simulator trace escapes its output root.",
        )
        _verify_file(trace_path, expected, label=f"HIL simulator trace {relative}")
    _require(
        sim_receipt.get("simulator_replays_used") == 2
        and sim_receipt.get("adaptive_retries") == 0
        and sim_receipt.get("provider_calls") == 0
        and sim_evaluation.get("simulator_parameter_promoted") is False
        and sim_evaluation.get("task_score_changed") is False,
        "HIL simulator budget or authority changed.",
    )
    return {
        "publication": publication,
        "publication_sha256": sha256_file(
            _repo_path(root, publication_path, label="HIL publication")
        ),
        "campaign": campaign,
        "summary": summary,
        "evidence_receipt": evidence_receipt,
        "packets": verified_packets,
        "offline_analysis": {
            "report": analysis_report,
            "receipt": analysis_receipt,
        },
        "offline_decomposition": {
            "report": decomposition_report,
            "receipt": decomposition_receipt,
        },
        "simulator": {
            "contract": sim_contract,
            "raw_comparison": sim_raw,
            "evaluation": sim_evaluation,
            "receipt": sim_receipt,
        },
    }


__all__ = [
    "DEFAULT_PUBLICATION_PATH",
    "HILPublicationError",
    "SCHEMA_VERSION",
    "load_hil_publication_binding",
    "verify_hil_publication",
]
