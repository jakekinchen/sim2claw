"""Evaluator-owned project-level Twin fidelity closure accounting."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .hil_publication import verify_hil_publication
from .learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .paths import REPO_ROOT
from .sail.importers import load_json_object
from .sail.live_receipts import verify_live_operator_receipt


CONTRACT_SCHEMA = "sim2claw.twin_fidelity_closure_contract.v1"
REPORT_SCHEMA = "sim2claw.twin_fidelity_closure_report.v1"
RECEIPT_SCHEMA = "sim2claw.twin_fidelity_closure_receipt.v1"
DEFAULT_CONTRACT_PATH = Path("configs/evaluations/twin_fidelity_closure_v1.json")
DOMAIN_ORDER = (
    "geometry_scale",
    "kinematics",
    "action_timing",
    "contact_compliance",
    "actuator_load_path",
    "task_ee_consequence",
)
STATUS_ORDER = {"passed", "partial", "failed", "missing"}


class TwinFidelityClosureError(RuntimeError):
    """The closure matrix could not be evaluated without changing meaning."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise TwinFidelityClosureError(message)


def _repo_path(repo_root: Path, value: object, *, label: str) -> Path:
    root = repo_root.resolve()
    path = (root / str(value)).resolve()
    _require(path.is_relative_to(root), f"{label} escapes the repository.")
    return path


def _rows(value: object) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    return [row for row in value if isinstance(row, Mapping)]


def load_twin_fidelity_closure_contract(
    path: Path = DEFAULT_CONTRACT_PATH,
    *,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    contract_path = _repo_path(repo_root, path, label="Twin closure contract")
    contract = load_json_object(contract_path, label="Twin closure contract")
    _require(
        contract.get("schema_version") == CONTRACT_SCHEMA,
        "Unsupported Twin closure contract.",
    )
    _require(
        contract.get("status") == "frozen_before_measurement_readiness_implementation",
        "Twin closure contract is not frozen.",
    )
    _require(
        tuple(contract.get("domain_order") or ()) == DOMAIN_ORDER,
        "Twin closure domain order changed.",
    )
    domains = contract.get("domains")
    _require(isinstance(domains, Mapping), "Twin closure domains are missing.")
    _require(set(domains) == set(DOMAIN_ORDER), "Twin closure domain set changed.")
    completion = contract.get("completion")
    _require(isinstance(completion, Mapping), "Twin closure completion rule is missing.")
    _require(
        completion.get("required_domain_count") == len(DOMAIN_ORDER)
        and completion.get("required_pass_count") == len(DOMAIN_ORDER),
        "Twin closure denominator changed.",
    )
    _require(
        completion.get("allow_weighted_percentage") is False
        and completion.get("allow_unknown_as_zero") is False
        and completion.get("allow_partial_as_pass") is False,
        "Twin closure fail-closed rules changed.",
    )
    authority = contract.get("authority")
    _require(
        isinstance(authority, Mapping)
        and authority
        and all(value is False for value in authority.values()),
        "Twin closure authority widened.",
    )
    return contract


def _domain(
    contract: Mapping[str, Any],
    domain_id: str,
    *,
    status: str,
    observed: Sequence[str],
    missing: Sequence[str],
    failed_gates: Sequence[str] = (),
    detail: str,
) -> dict[str, Any]:
    _require(status in STATUS_ORDER, f"Invalid Twin closure status: {status}")
    definition = contract["domains"][domain_id]
    return {
        "id": domain_id,
        "label": definition["label"],
        "status": status,
        "observed_evidence": list(dict.fromkeys(str(row) for row in observed)),
        "missing_evidence": list(dict.fromkeys(str(row) for row in missing)),
        "failed_gates": list(dict.fromkeys(str(row) for row in failed_gates)),
        "pass_rule": definition["pass_rule"],
        "detail": detail,
    }


def evaluate_verified_twin_fidelity_closure(
    *,
    contract: Mapping[str, Any],
    hil_bundle: Mapping[str, Any],
    live_receipt: Mapping[str, Any],
    live_consequence: Mapping[str, Any],
    source_identity: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate already-verified inputs without owning their scientific score."""

    summary = hil_bundle.get("summary")
    decomposition = hil_bundle.get("offline_decomposition")
    simulator = hil_bundle.get("simulator")
    _require(isinstance(summary, Mapping), "Verified HIL summary is missing.")
    _require(isinstance(decomposition, Mapping), "Verified HIL decomposition is missing.")
    _require(isinstance(simulator, Mapping), "Verified HIL simulator result is missing.")
    decomposition_report = decomposition.get("report")
    _require(
        isinstance(decomposition_report, Mapping),
        "Verified HIL decomposition report is missing.",
    )
    simulator_evaluation = simulator.get("evaluation")
    _require(
        isinstance(simulator_evaluation, Mapping),
        "Verified HIL simulator evaluation is missing.",
    )
    _require(
        live_receipt.get("verdict") == "evaluator_reject",
        "Installed SAIL terminal verdict changed.",
    )
    _require(
        live_consequence.get("admitted_evaluator_owned_evidence") is False,
        "Installed SAIL admitted-evidence state changed.",
    )

    admitted_packets = set(str(row) for row in summary.get("admitted_packet_ids") or [])
    remaining = set(str(row) for row in summary.get("remaining_observables") or [])
    decomposition_packets = _rows(decomposition_report.get("packets"))
    requested_applied_count = sum(
        bool((row.get("action_identity") or {}).get("requested_action_sha256"))
        and bool((row.get("action_identity") or {}).get("applied_action_sha256"))
        for row in decomposition_packets
    )
    strict_passes = int(live_consequence.get("strict_task_and_ee_pass_count") or 0)
    strict_candidates = int(live_consequence.get("candidate_count") or 0)

    domains = [
        _domain(
            contract,
            "geometry_scale",
            status="missing",
            observed=[],
            missing=contract["domains"]["geometry_scale"]["required_observables"],
            detail=(
                "No receipt-bound metric board/object registration or wrist "
                "extrinsic closes the geometry domain."
            ),
        ),
        _domain(
            contract,
            "kinematics",
            status="partial" if admitted_packets else "missing",
            observed=[f"{len(admitted_packets)} admitted unloaded joint channels"],
            missing=[
                "all_six_joint_channels",
                "three_or_more_distributed_levels_per_joint",
                "two_or_more_command_speeds_per_joint",
                "two_or_more_clean_traversals_per_direction",
            ],
            failed_gates=["shoulder_candidate_non_target_regression"],
            detail=(
                f"{len(admitted_packets)} unloaded packet(s) were admitted, but "
                "the repeated multi-level/multi-speed excitation gate is open."
            ),
        ),
        _domain(
            contract,
            "action_timing",
            status="partial" if requested_applied_count else "missing",
            observed=[
                f"{requested_applied_count} requested/applied action decompositions",
                "same-process host monotonic read/call brackets",
            ],
            missing=[
                "actuator_application_or_ack_timestamp",
                "device_synchronized_position_and_current_time",
                "camera_exposure_or_device_time",
            ],
            detail=(
                "Requested/applied identity and host brackets are diagnostic; "
                "they are not actuator acknowledgement or a common device clock."
            ),
        ),
        _domain(
            contract,
            "contact_compliance",
            status="missing",
            observed=["diagnostic retained-C2 mechanism effects"],
            missing=[
                value
                for value in contract["domains"]["contact_compliance"][
                    "required_observables"
                ]
                if value in {"calibrated_contact_force", "deformation", "contact_state", "known_loaded_and_unloaded_trials"}
            ],
            failed_gates=["retained_c2_evaluator_reject"],
            detail=(
                "Mechanism effects were diagnostic, but no calibrated force, "
                "deformation, or admitted loaded-contact consequence exists."
            ),
        ),
        _domain(
            contract,
            "actuator_load_path",
            status="partial",
            observed=["fresh raw current register", "unloaded joint telemetry"],
            missing=[
                value
                for value in contract["domains"]["actuator_load_path"][
                    "required_observables"
                ]
                if value
                in {
                    "calibrated_current_zero_and_scale",
                    "current_to_torque_provenance",
                    "known_load_trials",
                    "repeat_reference_reset_trials",
                }
            ],
            failed_gates=["retained_c2_evaluator_reject"],
            detail=(
                "Raw current is available but uncalibrated; it cannot be relabelled "
                "as torque, load, or contact force."
            ),
        ),
        _domain(
            contract,
            "task_ee_consequence",
            status="failed" if strict_candidates else "missing",
            observed=[f"strict retained-simulator consequence {strict_passes}/{strict_candidates}"],
            missing=[
                "metric_target_piece_trajectory",
                "physical_end_effector_trajectory",
                "strict_held_out_physical_task_consequence",
            ],
            failed_gates=["retained_c2_strict_task_and_ee_gate"],
            detail=(
                f"The retained simulator evaluator passed {strict_passes}/{strict_candidates} "
                "strict candidates; physical held-out task consequence is unavailable."
            ),
        ),
    ]
    _require(
        tuple(row["id"] for row in domains) == DOMAIN_ORDER,
        "Twin closure output order changed.",
    )
    passed = sum(row["status"] == "passed" for row in domains)
    missing_evidence = list(
        dict.fromkeys(
            value for row in domains for value in row["missing_evidence"]
        )
    )
    perfect = passed == len(DOMAIN_ORDER) and not missing_evidence
    return {
        "schema_version": REPORT_SCHEMA,
        "available": True,
        "proof_class": "twin_fidelity_measurement_readiness",
        "contract_id": contract["contract_id"],
        "source_identity": copy.deepcopy(dict(source_identity)),
        "status": "perfect" if perfect else "not_perfect",
        "perfect": perfect,
        "closure": {
            "passed_required_domains": passed,
            "required_domain_count": len(DOMAIN_ORDER),
            "weighted_percentage": None,
            "unknown_counted_as_zero": False,
        },
        "domains": domains,
        "missing_prerequisites": missing_evidence,
        "evidence_summary": {
            "hil_admitted_packets": len(admitted_packets),
            "hil_rejected_packets": int(summary.get("rejected_packet_count") or 0),
            "hil_remaining_observables": sorted(remaining),
            "requested_applied_decomposition_packets": requested_applied_count,
            "sail_verdict": live_receipt.get("verdict"),
            "strict_task_and_ee_pass_count": strict_passes,
            "strict_candidate_count": strict_candidates,
            "simulator_candidate_verdict": simulator_evaluation.get("verdict"),
        },
        "authority": copy.deepcopy(dict(contract["authority"])),
        "next_action": (
            "Acquire the first preregistered missing measurement; do not launch "
            "another simulator family from this report."
        ),
    }


def evaluate_twin_fidelity_closure(
    *,
    repo_root: Path = REPO_ROOT,
    contract_path: Path = DEFAULT_CONTRACT_PATH,
) -> dict[str, Any]:
    root = repo_root.resolve()
    contract = load_twin_fidelity_closure_contract(
        contract_path, repo_root=root
    )
    hil_bundle = verify_hil_publication(
        repo_root=root,
        publication_path=Path(contract["inputs"]["hil_publication"]),
    )
    live_path = _repo_path(
        root, contract["inputs"]["sail_live_receipt"], label="SAIL live receipt"
    )
    live_verification = verify_live_operator_receipt(live_path, repo_root=root)
    live_receipt = load_json_object(live_path, label="SAIL live receipt")
    consequence_binding = live_receipt.get("outputs", {}).get("consequence", {})
    consequence_path = _repo_path(
        live_path.parent,
        consequence_binding.get("path"),
        label="SAIL consequence",
    )
    _require(
        sha256_file(consequence_path) == consequence_binding.get("sha256"),
        "SAIL consequence hash changed.",
    )
    consequence = load_json_object(consequence_path, label="SAIL consequence")
    source_identity = {
        "contract_sha256": sha256_file(
            _repo_path(root, contract_path, label="Twin closure contract")
        ),
        "hil_publication_sha256": hil_bundle["publication_sha256"],
        "hil_campaign_state_sha256": hil_bundle["summary"]["campaign_state_sha256"],
        "sail_live_receipt_sha256": live_verification["receipt_sha256"],
        "sail_campaign_state_sha256": live_verification["campaign_state_sha256"],
    }
    return evaluate_verified_twin_fidelity_closure(
        contract=contract,
        hil_bundle=hil_bundle,
        live_receipt=live_receipt,
        live_consequence=consequence,
        source_identity=source_identity,
    )


def compile_twin_fidelity_closure(
    output_root: Path,
    *,
    repo_root: Path = REPO_ROOT,
    contract_path: Path = DEFAULT_CONTRACT_PATH,
) -> dict[str, Any]:
    _require(
        not output_root.exists() or not any(output_root.iterdir()),
        "Twin closure output root is not empty.",
    )
    output_root.mkdir(parents=True, exist_ok=True)
    report = evaluate_twin_fidelity_closure(
        repo_root=repo_root, contract_path=contract_path
    )
    report_path = output_root / "report.json"
    atomic_write_json(report_path, report)
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "proof_class": report["proof_class"],
        "contract_sha256": report["source_identity"]["contract_sha256"],
        "report_sha256": sha256_file(report_path),
        "perfect": report["perfect"],
        "passed_required_domains": report["closure"]["passed_required_domains"],
        "required_domain_count": report["closure"]["required_domain_count"],
        "authority": copy.deepcopy(report["authority"]),
    }
    receipt = {**unsigned, "receipt_digest": canonical_digest(unsigned)}
    atomic_write_json(output_root / "receipt.json", receipt)
    return receipt


__all__ = [
    "CONTRACT_SCHEMA",
    "DEFAULT_CONTRACT_PATH",
    "DOMAIN_ORDER",
    "RECEIPT_SCHEMA",
    "REPORT_SCHEMA",
    "TwinFidelityClosureError",
    "compile_twin_fidelity_closure",
    "evaluate_twin_fidelity_closure",
    "evaluate_verified_twin_fidelity_closure",
    "load_twin_fidelity_closure_contract",
]
