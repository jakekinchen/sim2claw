"""Audit OR50's frozen outcome surface without running new simulation."""

from __future__ import annotations

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
    "sim2claw.observable_registration_outcome_success_robustness_"
    "audit_contract.v1"
)
RECEIPT_SCHEMA = (
    "sim2claw.observable_registration_outcome_success_robustness_"
    "audit_receipt.v1"
)
CONTRACT_PATH = (
    REPO_ROOT
    / "configs/evaluations/"
    "observable_registration_outcome_success_robustness_audit_v1.json"
)
OUTPUT_DIRECTORY = (
    REPO_ROOT
    / "outputs/observable_registration_outcome_success_robustness_audit_v1"
)
TERMINAL_GATE_ORDER = (
    "composable_center",
    "other_pieces_stationary",
    "selected_piece_contact",
    "settled_angular",
    "settled_height",
    "settled_linear",
    "upright",
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_outcome_success_robustness_audit_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="OR51 robustness audit")
    _require(contract.get("schema_version") == SCHEMA, "unsupported contract")
    for name, binding in contract["sources"].items():
        _bound_path(binding, root=root, label=name)

    or50 = _bound_json(
        contract["sources"]["or50_receipt"], root=root, label="OR50 receipt"
    )
    closeout = _bound_json(
        contract["sources"]["or50_closeout"], root=root, label="OR50 closeout"
    )
    trace_path = _bound_path(
        contract["sources"]["or50_selected_trace"],
        root=root,
        label="OR50 selected trace",
    )
    _require(
        or50["status"]
        == "PASS_QUARANTINED_NUMERIC_TASK_REPLAY_EVENT_MISMATCH_REMAINS"
        and or50["numeric_task_replay_pass"] is True
        and or50["complete_event_and_numeric_task_replay_pass"] is False
        and or50["outcome_informed_quarantine_permanent"] is True,
        "OR50 proof boundary drifted",
    )
    _require(
        closeout["receipt"]["sha256"]
        == contract["sources"]["or50_receipt"]["sha256"]
        and closeout["selected_trace"]["sha256"] == _sha256(trace_path),
        "OR50 closeout bindings drifted",
    )
    surface = contract["frozen_surface_audit"]
    _require(
        surface["single_coordinate"]
        == "fixed_contact_skin_longitudinal_position"
        and surface["candidate_count"] == 25
        and surface["selected_index"] == 14
        and surface["selected_fixed_pad_local_z_m"] == -0.11298
        and surface["grid_step_m"] == 0.00001
        and surface["immediate_neighbor_index_offsets"] == [-1, 0, 1]
        and surface["minimum_contiguous_numeric_success_count"] == 3
        and surface["new_candidate_generation_allowed"] is False
        and surface["parameter_selection_or_refit_allowed"] is False,
        "surface audit widened",
    )
    execution = contract["execution"]
    _require(
        execution["simulator_replays_allowed"] == 0
        and execution["hardware_actions_allowed"] == 0
        and not any(
            execution[name]
            for name in (
                "heldout_open_allowed",
                "terminal_evaluator_change_allowed",
                "trajectory_change_allowed",
                "contact_parameter_change_allowed",
            )
        ),
        "execution boundary widened",
    )
    _require(not any(contract["claim_limits"].values()), "claim boundary widened")
    _require(not any(contract["authority"].values()), "authority widened")
    return contract


def _terminal_gate_vector(candidate: dict[str, Any]) -> list[bool]:
    gates = candidate["report"]["terminal"]["gates"]
    _require(set(gates) == set(TERMINAL_GATE_ORDER), "terminal gate set drifted")
    return [bool(gates[name]) for name in TERMINAL_GATE_ORDER]


def _success_run_length(candidates: list[dict[str, Any]], selected: int) -> int:
    left = selected
    while left > 0 and candidates[left - 1]["report"]["terminal"][
        "numeric_task_success"
    ]:
        left -= 1
    right = selected
    while right + 1 < len(candidates) and candidates[right + 1]["report"][
        "terminal"
    ]["numeric_task_success"]:
        right += 1
    return right - left + 1


def _trace_contact_audit(
    trace: dict[str, Any], *, required_bodies: list[str]
) -> dict[str, Any]:
    rows = trace["rows"]
    _require(len(rows) > 0 and len(trace["sample_rows"]) == 531, "trace drifted")
    contact_rows = [
        row for row in rows if row["named_jaw_contact_state"] != "none"
    ]
    bodies = sorted(
        {
            str(body)
            for row in contact_rows
            for body in row["named_jaw_contact_bodies"]
        }
    )
    bilateral_rows = [
        row for row in contact_rows if row["named_jaw_contact_state"] == "bilateral"
    ]
    return {
        "internal_row_count": len(rows),
        "source_sample_row_count": len(trace["sample_rows"]),
        "first_named_jaw_contact_sample": (
            min(int(row["source_sample_index"]) for row in contact_rows)
            if contact_rows
            else None
        ),
        "first_bilateral_jaw_contact_sample": (
            min(int(row["source_sample_index"]) for row in bilateral_rows)
            if bilateral_rows
            else None
        ),
        "observed_named_jaw_bodies": bodies,
        "required_named_jaw_bodies": required_bodies,
        "both_named_jaw_surfaces_contact": set(required_bodies).issubset(bodies),
    }


def run_outcome_success_robustness_audit_once(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    _require(not receipt_path.exists(), "OR51 one-run receipt already exists")
    contract = load_outcome_success_robustness_audit_contract(
        contract_path, root=root
    )
    or50 = _bound_json(
        contract["sources"]["or50_receipt"], root=root, label="OR50 receipt"
    )
    trace = _bound_json(
        contract["sources"]["or50_selected_trace"],
        root=root,
        label="OR50 selected trace",
    )
    surface = contract["frozen_surface_audit"]
    event = contract["frozen_event_audit"]
    candidates = or50["candidates"]
    selected_index = int(surface["selected_index"])
    _require(len(candidates) == int(surface["candidate_count"]), "candidate drift")
    _require(
        or50["selected_index"] == selected_index
        and or50["selected_fixed_pad_local_z_m"]
        == surface["selected_fixed_pad_local_z_m"],
        "selected candidate drifted",
    )

    neighborhood_indices = [
        selected_index + int(offset)
        for offset in surface["immediate_neighbor_index_offsets"]
    ]
    selected_vector = _terminal_gate_vector(candidates[selected_index])
    neighborhood = [
        {
            "index": index,
            "fixed_pad_local_z_m": candidates[index]["fixed_pad_local_z_m"],
            "numeric_task_success": candidates[index]["report"]["terminal"][
                "numeric_task_success"
            ],
            "terminal_gate_vector": _terminal_gate_vector(candidates[index]),
            "final_planar_center_error_m": candidates[index]["report"]["terminal"][
                "final_planar_center_error_m"
            ],
            "final_upright_tilt_degrees": candidates[index]["report"]["terminal"][
                "final_upright_tilt_degrees"
            ],
        }
        for index in neighborhood_indices
    ]
    local_outcome_continuity = all(
        row["numeric_task_success"] is True
        and row["terminal_gate_vector"] == selected_vector
        for row in neighborhood
    )
    numeric_success_indices = [
        index
        for index, candidate in enumerate(candidates)
        if candidate["report"]["terminal"]["numeric_task_success"] is True
    ]
    adjacent_error_jumps = [
        {
            "left_index": index,
            "right_index": index + 1,
            "absolute_planar_error_jump_m": abs(
                float(
                    candidates[index]["report"]["terminal"][
                        "final_planar_center_error_m"
                    ]
                )
                - float(
                    candidates[index + 1]["report"]["terminal"][
                        "final_planar_center_error_m"
                    ]
                )
            ),
        }
        for index in range(len(candidates) - 1)
    ]
    maximum_jump = max(
        adjacent_error_jumps,
        key=lambda row: row["absolute_planar_error_jump_m"],
    )

    trace_audit = _trace_contact_audit(
        trace, required_bodies=list(event["required_named_jaw_bodies"])
    )
    selected_report = or50["selected_report"]
    event_gates = selected_report["preterminal"]["gates"]
    _require(
        set(event_gates) == set(event["required_preterminal_gates"]),
        "preterminal gate set drifted",
    )
    all_event_gates_pass = all(
        bool(event_gates[name]) for name in event["required_preterminal_gates"]
    )
    digest_identity = (
        or50["selection_result_digest"] == or50["verification_result_digest"]
    )
    overall_pass = bool(
        local_outcome_continuity
        and trace_audit["both_named_jaw_surfaces_contact"]
        and all_event_gates_pass
        and digest_identity
    )
    status = (
        "PASS_QUARANTINED_LOCALLY_ROBUST_EVENT_AND_OUTCOME"
        if overall_pass
        else contract["acceptance"]["failed_gate_status"]
    )
    result = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "proof_class": contract["proof_class"],
        "status": status,
        "or50_binding": {
            "receipt_sha256": contract["sources"]["or50_receipt"]["sha256"],
            "closeout_sha256": contract["sources"]["or50_closeout"]["sha256"],
            "selected_trace_sha256": contract["sources"]["or50_selected_trace"][
                "sha256"
            ],
            "selection_result_digest": or50["selection_result_digest"],
            "verification_result_digest": or50["verification_result_digest"],
            "selection_verification_digest_identity": digest_identity,
        },
        "surface_audit": {
            "candidate_count": len(candidates),
            "numeric_task_success_candidate_count": len(numeric_success_indices),
            "numeric_task_success_indices": numeric_success_indices,
            "selected_contiguous_numeric_success_count": _success_run_length(
                candidates, selected_index
            ),
            "required_contiguous_numeric_success_count": surface[
                "minimum_contiguous_numeric_success_count"
            ],
            "neighborhood": neighborhood,
            "local_outcome_continuity_pass": local_outcome_continuity,
            "maximum_adjacent_planar_error_jump": maximum_jump,
        },
        "event_audit": {
            "preterminal_gates": event_gates,
            "preterminal_gate_pass_count": sum(
                bool(value) for value in event_gates.values()
            ),
            "preterminal_gate_total_count": len(event_gates),
            "all_preterminal_gates_pass": all_event_gates_pass,
            "trace_contact_audit": trace_audit,
            "motion_early_by_samples": max(
                0,
                int(event["physical_no_motion_before_sample"])
                - int(selected_report["preterminal"]["first_motion_over_1mm_sample"]),
            ),
            "support_loss_early_by_samples": max(
                0,
                int(event["physical_support_loss_start_sample"])
                - int(
                    selected_report["preterminal"][
                        "first_sustained_support_loss_sample"
                    ]
                ),
            ),
            "tilt_excess_at_sample_260_degrees": max(
                0.0,
                float(selected_report["preterminal"]["tilt_at_sample_260_degrees"])
                - float(event["maximum_tilt_at_sample_260_degrees"]),
            ),
        },
        "overall_gate_pass": overall_pass,
        "new_execution": {
            "simulator_replays": 0,
            "new_candidates": 0,
            "parameter_changes": 0,
            "hardware_actions": 0,
            "heldout_opened": False,
        },
        "next_promotable_boundary": contract["acceptance"][
            "next_promotable_boundary"
        ],
        "claim_limits": contract["claim_limits"],
        "authority": contract["authority"],
    }
    result["artifact_sha256"] = canonical_digest(result)
    output_directory.mkdir(parents=True, exist_ok=False)
    atomic_write_json(receipt_path, result)
    return result


def main() -> int:
    run_outcome_success_robustness_audit_once()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
