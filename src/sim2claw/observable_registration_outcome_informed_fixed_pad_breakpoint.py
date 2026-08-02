"""Run the quarantined OR49 exact-episode fixed-pad breakpoint diagnostic."""

from __future__ import annotations

import copy
import gc
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
from .observable_registration_measured_state_contact_skin import (
    _contact_skin_model_mutator,
    _contact_skin_parameters,
    _contact_skin_spec_mutator,
)
from .observable_registration_measured_state_contact_topology import (
    _contact_topology_summary,
)
from .observable_registration_measured_state_load_path import _run_variant
from .observable_registration_measured_state_pad_bracket import (
    _preterminal_report,
)


SCHEMA = (
    "sim2claw.observable_registration_outcome_informed_"
    "fixed_pad_breakpoint_contract.v1"
)
RECEIPT_SCHEMA = (
    "sim2claw.observable_registration_outcome_informed_"
    "fixed_pad_breakpoint_receipt.v1"
)
CONTRACT_PATH = (
    REPO_ROOT
    / "configs/evaluations/"
    "observable_registration_outcome_informed_fixed_pad_breakpoint_v1.json"
)
OUTPUT_DIRECTORY = (
    REPO_ROOT
    / "outputs/"
    "observable_registration_outcome_informed_fixed_pad_breakpoint_v1"
)
EXPECTED_OFFSETS = [round(0.00525 + index * 0.00025, 5) for index in range(19)]
EXPECTED_LOCAL_Z = [round(-0.11525 + index * 0.00025, 5) for index in range(19)]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_outcome_informed_fixed_pad_breakpoint_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="OR49 fixed-pad breakpoint")
    _require(contract.get("schema_version") == SCHEMA, "unsupported contract")
    for name, binding in contract["sources"].items():
        _bound_path(binding, root=root, label=name)

    or38 = _bound_json(
        contract["sources"]["or38_receipt"], root=root, label="OR38 receipt"
    )
    _require(
        or38["status"] == "PARTIAL_BOUNDED_CONTACT_EVENT_CALIBRATION"
        and or38["full_physics_driven_replay_pass"] is False,
        "OR38 breakpoint evidence drifted",
    )
    trajectory = contract["trajectory"]
    _require(
        trajectory["row_count"] == 531
        and trajectory["robot_driver"]
        == "raw_follower_actual_position_degrees"
        and trajectory[
            "preserve_source_values_order_timestamps_and_interpolation"
        ]
        is True
        and trajectory["action_or_state_assistance_allowed"] is False,
        "raw measured-state identity widened",
    )
    grid = contract["fixed_pad_breakpoint_grid"]
    _require(
        grid["single_coordinate"]
        == "fixed_contact_skin_longitudinal_position"
        and grid["fixed_coverage_offsets_m"] == EXPECTED_OFFSETS
        and grid["implied_fixed_pad_local_z_m"] == EXPECTED_LOCAL_Z
        and grid["candidate_count"] == 19
        and grid["terminal_position_or_task_outcome_used_for_selection"] is True
        and grid["outcome_informed_quarantine_permanent"] is True
        and grid["rerun_selected_candidate_without_refit"] is True,
        "fixed-pad breakpoint grid changed",
    )
    skin = contract["contact_skin_intervention"]
    _require(
        skin["tip_thickness_m"] == 0.001
        and skin["tip_half_width_m"] == 0.0065
        and skin["tip_coverage_m"] == 0.02
        and skin["tip_coverage_offset_m"] == -0.03
        and skin["tip_moving_coverage_offset_m"] == 0.025
        and skin["sliding_friction"] == 1.8
        and skin["torsional_friction_m"] == 0.012
        and skin["rolling_friction_m"] == 0.0012
        and skin["add_exactly_one_pad_per_jaw"] is True
        and skin[
            "disable_all_original_collision_enabled_geoms_on_target_jaws"
        ]
        is True,
        "contact skin changed outside the fixed-pad coordinate",
    )
    simulation = contract["simulation"]
    _require(
        simulation["natural_pawn_dynamics_only"] is True
        and simulation[
            "selected_pawn_pose_written_only_during_initialization"
        ]
        is True
        and not any(
            simulation[name]
            for name in (
                "object_pose_injection_allowed",
                "latch_attachment_or_grasp_mode_allowed",
                "pawn_mass_com_or_inertia_change_allowed",
                "actuator_force_gain_or_driver_change_allowed",
                "camera_mapping_or_reset_change_allowed",
            )
        ),
        "natural-dynamics boundary widened",
    )
    _require(
        not any(contract["claim_limits"].values()),
        "claim boundary widened",
    )
    authority = contract["authority"]
    _require(
        authority["simulator_replay"] is True
        and not any(
            value for name, value in authority.items() if name != "simulator_replay"
        ),
        "authority widened beyond simulator replay",
    )
    return contract


def _candidate_report(
    contract: dict[str, Any], result: dict[str, Any]
) -> dict[str, Any]:
    preterminal = _preterminal_report(contract, result)
    outcome = result["natural_dynamics"]["outcome"]
    full_gate_pass = bool(
        all(preterminal["gates"].values())
        and outcome["numeric_task_success"] is True
    )
    return {
        "preterminal": preterminal,
        "terminal": {
            "numeric_task_success": outcome["numeric_task_success"],
            "final_planar_center_error_m": outcome[
                "final_planar_center_error_m"
            ],
            "final_upright_tilt_degrees": outcome[
                "final_upright_tilt_degrees"
            ],
            "final_height_error_m": outcome["final_height_error_m"],
            "final_linear_speed_m_s": outcome["final_linear_speed_m_s"],
            "final_angular_speed_rad_s": outcome["final_angular_speed_rad_s"],
            "maximum_other_piece_displacement_m": outcome[
                "maximum_other_piece_displacement_m"
            ],
            "gates": outcome["gates"],
        },
        "signed_progress_toward_d2_m": result["natural_dynamics"][
            "signed_progress_toward_d2_m"
        ],
        "full_gate_pass": full_gate_pass,
    }


def _selection_key(row: dict[str, Any]) -> tuple[float, ...]:
    report = row["report"]
    preterminal = report["preterminal"]
    terminal = report["terminal"]
    return (
        -float(report["full_gate_pass"]),
        -float(preterminal["gate_count"]),
        float(preterminal["interval_residual_samples"]),
        float(terminal["final_planar_center_error_m"]),
        float(preterminal["tilt_at_sample_260_degrees"]),
        float(terminal["final_upright_tilt_degrees"]),
        abs(float(terminal["final_height_error_m"])),
        abs(float(row["fixed_pad_local_z_m"]) + 0.113),
    )


def _run_candidate(
    *,
    contract: dict[str, Any],
    index: int,
    root: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    candidate_contract = copy.deepcopy(contract)
    offset = EXPECTED_OFFSETS[index]
    candidate_contract["contact_skin_intervention"][
        "tip_fixed_coverage_offset_m"
    ] = offset
    variant = {
        "variant_id": f"fixed_pad_breakpoint_{index:02d}",
        "role": "quarantined_outcome_informed_exact_episode_candidate",
        "sts3215_force_limit_nm": 2.94,
    }
    c2_path = _bound_path(
        contract["sources"]["c2_contact_skin_contract"],
        root=root,
        label="C2 contact-skin contract",
    )
    parameters = _contact_skin_parameters(candidate_contract)
    result, trace = _run_variant(
        contract=candidate_contract,
        variant=variant,
        root=root,
        spec_mutator=_contact_skin_spec_mutator(
            contract=candidate_contract,
            c2_contract_path=c2_path,
        ),
        model_mutator=_contact_skin_model_mutator(parameters),
    )
    result["spec_mutation_report"]["parameter_source"] = (
        "or49_outcome_informed_exact_episode_quarantined_fixed_pad_scan"
    )
    mutation = result["model_mutation_report"]
    fixed_pad = next(
        row for row in mutation["contact_skin_pads"] if row["finger"] == "fixed"
    )
    expected_z = EXPECTED_LOCAL_Z[index]
    _require(
        mutation["contact_skin_pad_count"] == 2
        and abs(float(fixed_pad["position"][2]) - expected_z) < 1e-12,
        "candidate did not compile at its frozen fixed-pad coordinate",
    )
    disabled_names = {
        row["geom_name"]
        for row in mutation["disabled_original_jaw_collision_geoms"]
    }
    topology = _contact_topology_summary(
        trace,
        analysis_start=int(contract["trace"]["analysis_source_sample_start"]),
        analysis_end=int(contract["trace"]["analysis_source_sample_end"]),
        disabled_geom_names=disabled_names,
    )
    return result, trace, topology


def run_outcome_informed_fixed_pad_breakpoint_once(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    _require(not receipt_path.exists(), "OR49 one-run receipt already exists")
    contract = load_outcome_informed_fixed_pad_breakpoint_contract(
        contract_path, root=root
    )

    rows: list[dict[str, Any]] = []
    for index in range(len(EXPECTED_OFFSETS)):
        result, trace, topology = _run_candidate(
            contract=contract, index=index, root=root
        )
        row = {
            "variant_id": result["variant_id"],
            "fixed_coverage_offset_m": EXPECTED_OFFSETS[index],
            "fixed_pad_local_z_m": EXPECTED_LOCAL_Z[index],
            "report": _candidate_report(contract, result),
            "contact_topology": topology,
            "result": result,
        }
        rows.append(row)
        del trace
        gc.collect()

    selected_index = min(range(len(rows)), key=lambda value: _selection_key(rows[value]))
    selected = rows[selected_index]
    verification_result, verification_trace, verification_topology = _run_candidate(
        contract=contract, index=selected_index, root=root
    )
    selection_result_digest = canonical_digest(selected["result"])
    verification_result_digest = canonical_digest(verification_result)
    _require(
        selection_result_digest == verification_result_digest,
        "selected candidate did not reproduce exactly without refit",
    )
    _require(
        selected["contact_topology"] == verification_topology,
        "selected contact topology did not reproduce exactly",
    )
    verification_report = _candidate_report(contract, verification_result)
    full_pass = bool(verification_report["full_gate_pass"])
    status = (
        "PASS_QUARANTINED_FULL_PHYSICS_DRIVEN_EXACT_EPISODE_REPLAY"
        if full_pass
        else "TERMINAL_NEGATIVE_FINE_FIXED_PAD_BREAKPOINT_INSUFFICIENT"
    )

    output_directory.mkdir(parents=True, exist_ok=False)
    trace_path = output_directory / "selected_frozen_rerun_trace.json"
    atomic_write_json(trace_path, verification_trace)
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "proof_class": contract["proof_class"],
        "status": status,
        "candidate_count": len(rows),
        "simulator_replay_count": len(rows) + 1,
        "single_simulator_coordinate_changed": (
            "fixed_contact_skin_longitudinal_position"
        ),
        "terminal_position_or_task_outcome_used_for_selection": True,
        "outcome_informed_quarantine_permanent": True,
        "selected_index": selected_index,
        "selected_variant_id": selected["variant_id"],
        "selected_fixed_coverage_offset_m": selected[
            "fixed_coverage_offset_m"
        ],
        "selected_fixed_pad_local_z_m": selected["fixed_pad_local_z_m"],
        "selection_key": list(_selection_key(selected)),
        "selection_result_digest": selection_result_digest,
        "verification_result_digest": verification_result_digest,
        "selected_rerun_exact_without_refit": True,
        "selected_report": verification_report,
        "selected_result": verification_result,
        "selected_contact_topology": verification_topology,
        "full_physics_driven_exact_episode_replay_pass": full_pass,
        "candidates": rows,
        "trace_binding": {
            "path": trace_path.name,
            "sha256": _sha256(trace_path),
        },
        "raw_measured_state_changed": False,
        "timestamps_order_or_interpolation_changed": False,
        "object_pose_injection_used": False,
        "latch_attachment_grasp_mode_or_support_projection_used": False,
        "actuator_force_gain_or_driver_changed": False,
        "pawn_board_reset_or_solver_changed": False,
        "canonical_contact_geometry_approved": False,
        "heldout_validation_performed": False,
        "global_mapping_approved": False,
        "simulator_promoted": False,
        "transfer_claim": False,
        "authority": contract["authority"],
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


def main() -> int:
    run_outcome_informed_fixed_pad_breakpoint_once()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
