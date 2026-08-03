"""Audit existing simulator candidates against the retained-footage constraint."""

from __future__ import annotations

import collections
import hashlib
from pathlib import Path
from typing import Any

from .learning_factory_artifacts import (
    FactoryArtifactError,
    atomic_write_json,
    canonical_digest,
    load_json_object,
)
from .observable_registration_belief_recalculation import (
    REPO_ROOT,
    _bound_json,
    _bound_path,
)


SCHEMA = (
    "sim2claw.observable_registration_existing_trace_footage_constraint_"
    "audit_contract.v1"
)
RECEIPT_SCHEMA = (
    "sim2claw.observable_registration_existing_trace_footage_constraint_"
    "audit_receipt.v1"
)
ROWS_SCHEMA = (
    "sim2claw.observable_registration_existing_trace_footage_constraint_rows.v1"
)
CONTRACT_PATH = (
    REPO_ROOT
    / "configs/evaluations/"
    "observable_registration_existing_trace_footage_constraint_audit_v1.json"
)
OUTPUT_DIRECTORY = (
    REPO_ROOT
    / "outputs/observable_registration_existing_trace_footage_constraint_audit_v1"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def _in_interval(value: int | None, bounds: list[int]) -> bool:
    return value is not None and int(bounds[0]) <= int(value) <= int(bounds[1])


def load_existing_trace_footage_constraint_audit_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="OR53 existing trace audit")
    _require(contract.get("schema_version") == SCHEMA, "unsupported contract")
    for name, binding in contract["sources"].items():
        _bound_path(binding, root=root, label=name)

    population = contract["population"]
    _require(
        population["cards"]
        == [
            {"card_id": "OR38", "source": "or38_receipt", "candidate_count": 9},
            {"card_id": "OR49", "source": "or49_receipt", "candidate_count": 19},
            {"card_id": "OR50", "source": "or50_receipt", "candidate_count": 25},
        ]
        and population["total_candidate_count"] == 53
        and population["all_candidates_required"] is True
        and population["terminal_outcome_available_to_preterminal_ranking"]
        is False,
        "candidate population drifted",
    )
    gates = contract["physical_event_gates"]
    _require(
        gates["gate_order"]
        == [
            "contact_timing",
            "no_early_motion",
            "support_loss_timing",
            "bilateral_contact_timing",
            "upright_at_sample_260",
        ]
        and gates["contact_sample_interval_inclusive"] == [228, 232]
        and gates["no_motion_over_1mm_before_sample"] == 247
        and gates["support_loss_sample_interval_inclusive"] == [247, 260]
        and gates["bilateral_contact_sample_interval_inclusive"] == [247, 270]
        and gates["maximum_tilt_at_sample_260_degrees"] == 10.0
        and gates["all_five_required"] is True,
        "physical event gates drifted",
    )
    policy = contract["audit_policy"]
    _require(
        policy["preterminal_gates_audited_before_terminal_outcome"] is True
        and policy[
            "sampled_single_coordinate_family_closes_if_zero_all_gate_candidates"
        ]
        is True
        and not any(
            policy[name]
            for name in (
                "candidate_selection_allowed",
                "parameter_fit_or_refit_allowed",
                "unsampled_continuum_exhaustion_claim_allowed",
            )
        ),
        "audit policy widened",
    )
    _require(
        all(
            contract["execution"][name] == 0
            for name in (
                "simulator_replays_allowed",
                "new_candidates_allowed",
                "parameter_changes_allowed",
                "hardware_actions_allowed",
                "new_annotations_allowed",
            )
        )
        and contract["execution"]["heldout_open_allowed"] is False,
        "execution boundary widened",
    )
    _require(not any(contract["claim_limits"].values()), "claim boundary widened")
    _require(not any(contract["authority"].values()), "authority widened")
    return contract


def _candidate_reports(
    card_id: str, candidate: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any], float]:
    if card_id == "OR38":
        preterminal = candidate["preterminal_report"]
        dynamics = candidate["result"]["natural_dynamics"]
        return preterminal, dynamics["outcome"], float(
            dynamics["signed_progress_toward_d2_m"]
        )
    report = candidate["report"]
    return (
        report["preterminal"],
        report["terminal"],
        float(report["signed_progress_toward_d2_m"]),
    )


def _recompute_gates(
    preterminal: dict[str, Any], policy: dict[str, Any]
) -> dict[str, bool]:
    return {
        "contact_timing": _in_interval(
            preterminal["first_selected_jaw_contact_sample"],
            policy["contact_sample_interval_inclusive"],
        ),
        "no_early_motion": int(preterminal["first_motion_over_1mm_sample"])
        >= int(policy["no_motion_over_1mm_before_sample"]),
        "support_loss_timing": _in_interval(
            preterminal["first_sustained_support_loss_sample"],
            policy["support_loss_sample_interval_inclusive"],
        ),
        "bilateral_contact_timing": _in_interval(
            preterminal["first_bilateral_jaw_contact_sample"],
            policy["bilateral_contact_sample_interval_inclusive"],
        ),
        "upright_at_sample_260": float(
            preterminal["tilt_at_sample_260_degrees"]
        )
        <= float(policy["maximum_tilt_at_sample_260_degrees"]),
    }


def run_existing_trace_footage_constraint_audit_once(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    _require(not receipt_path.exists(), "OR53 one-run receipt already exists")
    contract = load_existing_trace_footage_constraint_audit_contract(
        contract_path, root=root
    )
    or52 = _bound_json(
        contract["sources"]["or52_closeout"], root=root, label="OR52 closeout"
    )
    _require(
        or52["status"]
        == "PASS_FOOTAGE_ONLY_PERSISTENT_ENCLOSURE_PROXY_SIMULATOR_"
        "BILATERAL_CONTACT_ABSENT"
        and or52["result"]["persistent_image_plane_enclosure_proxy"] is True
        and or52["result"]["bilateral_physical_contact_proven"] is False,
        "OR52 footage boundary drifted",
    )

    rows: list[dict[str, Any]] = []
    source_statuses: dict[str, str] = {}
    gate_policy = contract["physical_event_gates"]
    for card in contract["population"]["cards"]:
        card_id = str(card["card_id"])
        receipt = _bound_json(
            contract["sources"][str(card["source"])],
            root=root,
            label=f"{card_id} receipt",
        )
        candidates = receipt["candidates"]
        _require(
            len(candidates) == int(card["candidate_count"]),
            f"{card_id} candidate count drifted",
        )
        source_statuses[card_id] = str(receipt["status"])
        for index, candidate in enumerate(candidates):
            preterminal, terminal, progress_m = _candidate_reports(
                card_id, candidate
            )
            gates = _recompute_gates(preterminal, gate_policy)
            _require(
                gates == preterminal["gates"],
                f"{card_id} candidate {index} gate drift",
            )
            rows.append(
                {
                    "card_id": card_id,
                    "candidate_index": index,
                    "variant_id": candidate["variant_id"],
                    "fixed_pad_local_z_m": candidate["fixed_pad_local_z_m"],
                    "preterminal": {
                        "first_selected_jaw_contact_sample": preterminal[
                            "first_selected_jaw_contact_sample"
                        ],
                        "first_motion_over_1mm_sample": preterminal[
                            "first_motion_over_1mm_sample"
                        ],
                        "first_sustained_support_loss_sample": preterminal[
                            "first_sustained_support_loss_sample"
                        ],
                        "first_bilateral_jaw_contact_sample": preterminal[
                            "first_bilateral_jaw_contact_sample"
                        ],
                        "tilt_at_sample_260_degrees": preterminal[
                            "tilt_at_sample_260_degrees"
                        ],
                        "gates": gates,
                        "gate_count": sum(gates.values()),
                    },
                    "terminal_reported_after_preterminal_audit": {
                        "numeric_task_success": terminal["numeric_task_success"],
                        "final_planar_center_error_m": terminal[
                            "final_planar_center_error_m"
                        ],
                        "final_upright_tilt_degrees": terminal[
                            "final_upright_tilt_degrees"
                        ],
                        "signed_progress_toward_d2_m": progress_m,
                    },
                }
            )

    _require(
        len(rows) == int(contract["population"]["total_candidate_count"]),
        "total candidate count drifted",
    )
    identities = {(row["card_id"], row["variant_id"]) for row in rows}
    _require(len(identities) == len(rows), "candidate identity collision")

    gate_order = list(gate_policy["gate_order"])
    gate_counts = {
        name: sum(bool(row["preterminal"]["gates"][name]) for row in rows)
        for name in gate_order
    }
    histogram_counter = collections.Counter(
        int(row["preterminal"]["gate_count"]) for row in rows
    )
    gate_count_histogram = {
        str(count): int(histogram_counter.get(count, 0)) for count in range(6)
    }
    all_gate_rows = [
        row
        for row in rows
        if all(bool(row["preterminal"]["gates"][name]) for name in gate_order)
    ]
    bilateral_timing_rows = [
        row
        for row in rows
        if row["preterminal"]["gates"]["bilateral_contact_timing"]
    ]
    motion_support_rows = [
        row
        for row in rows
        if row["preterminal"]["gates"]["no_early_motion"]
        and row["preterminal"]["gates"]["support_loss_timing"]
    ]
    bilateral_motion_support_rows = [
        row
        for row in rows
        if row["preterminal"]["gates"]["bilateral_contact_timing"]
        and row["preterminal"]["gates"]["no_early_motion"]
        and row["preterminal"]["gates"]["support_loss_timing"]
    ]
    bilateral_upright_rows = [
        row
        for row in rows
        if row["preterminal"]["gates"]["bilateral_contact_timing"]
        and row["preterminal"]["gates"]["upright_at_sample_260"]
    ]
    numeric_success_rows = [
        row
        for row in rows
        if row["terminal_reported_after_preterminal_audit"]["numeric_task_success"]
    ]
    maximum_gate_count = max(
        int(row["preterminal"]["gate_count"]) for row in rows
    )
    maximum_gate_rows = [
        row
        for row in rows
        if int(row["preterminal"]["gate_count"]) == maximum_gate_count
    ]

    rows_document = {
        "schema_version": ROWS_SCHEMA,
        "gate_order": gate_order,
        "rows": rows,
    }
    output_directory.mkdir(parents=True, exist_ok=False)
    rows_path = output_directory / "candidate_rows.json"
    atomic_write_json(rows_path, rows_document)

    family_closed = len(all_gate_rows) == 0
    result = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "proof_class": contract["proof_class"],
        "status": (
            "TERMINAL_EXISTING_FIXED_PAD_TRACE_CORPUS_BIFURCATES_"
            "BILATERAL_VS_TIMING_NO_FULL_EVENT_MATCH"
            if family_closed
            else "EXISTING_TRACE_CORPUS_CONTAINS_FULL_EVENT_MATCH"
        ),
        "source_bindings": {
            name: binding["sha256"]
            for name, binding in contract["sources"].items()
        },
        "source_statuses": source_statuses,
        "population_audit": {
            "candidate_count": len(rows),
            "candidate_count_by_card": {
                card_id: sum(row["card_id"] == card_id for row in rows)
                for card_id in ("OR38", "OR49", "OR50")
            },
            "unique_candidate_identity_count": len(identities),
            "gate_pass_counts": gate_counts,
            "gate_count_histogram": gate_count_histogram,
            "maximum_preterminal_gate_count": maximum_gate_count,
            "maximum_preterminal_gate_candidate_count": len(maximum_gate_rows),
            "all_five_gate_candidate_count": len(all_gate_rows),
            "bilateral_timing_candidate_count": len(bilateral_timing_rows),
            "motion_and_support_timing_candidate_count": len(motion_support_rows),
            "bilateral_motion_and_support_timing_candidate_count": len(
                bilateral_motion_support_rows
            ),
            "bilateral_and_upright_sample260_candidate_count": len(
                bilateral_upright_rows
            ),
            "numeric_task_success_candidate_count": len(numeric_success_rows),
            "numeric_success_and_all_five_gate_candidate_count": sum(
                row in all_gate_rows for row in numeric_success_rows
            ),
        },
        "bifurcation": {
            "bilateral_but_early_branch": [
                {
                    "card_id": row["card_id"],
                    "variant_id": row["variant_id"],
                    "fixed_pad_local_z_m": row["fixed_pad_local_z_m"],
                    "first_motion_over_1mm_sample": row["preterminal"][
                        "first_motion_over_1mm_sample"
                    ],
                    "first_sustained_support_loss_sample": row["preterminal"][
                        "first_sustained_support_loss_sample"
                    ],
                    "first_bilateral_jaw_contact_sample": row["preterminal"][
                        "first_bilateral_jaw_contact_sample"
                    ],
                    "tilt_at_sample_260_degrees": row["preterminal"][
                        "tilt_at_sample_260_degrees"
                    ],
                }
                for row in bilateral_upright_rows
            ],
            "timing_correct_but_unilateral_candidate_count": sum(
                row["preterminal"]["gates"]["no_early_motion"]
                and row["preterminal"]["gates"]["support_loss_timing"]
                and not row["preterminal"]["gates"]["bilateral_contact_timing"]
                for row in rows
            ),
            "branches_intersect": len(bilateral_motion_support_rows) > 0,
        },
        "sampled_family_verdict": {
            "existing_sampled_single_coordinate_family_sufficient": not family_closed,
            "existing_sampled_single_coordinate_family_closed": family_closed,
            "unsampled_continuum_exhausted": False,
            "candidate_selected_or_promoted": False,
            "diagnostic": (
                "the existing fixed-pad longitudinal traces split between "
                "bilateral contact with early consequence and physical timing "
                "without bilateral contact"
            ),
        },
        "candidate_rows_sha256": hashlib.sha256(rows_path.read_bytes()).hexdigest(),
        "new_execution": {
            "simulator_replays": 0,
            "new_candidates": 0,
            "parameter_changes": 0,
            "hardware_actions": 0,
            "new_annotations": 0,
            "heldout_opened": False,
        },
        "claim_limits": contract["claim_limits"],
        "authority": contract["authority"],
    }
    result["artifact_sha256"] = canonical_digest(result)
    atomic_write_json(receipt_path, result)
    return result


def main() -> int:
    run_existing_trace_footage_constraint_audit_once()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
