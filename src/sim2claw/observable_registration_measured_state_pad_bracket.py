"""Resolve the OR37 fixed-pad bracket using preterminal contact events only."""

from __future__ import annotations

import copy
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


SCHEMA = (
    "sim2claw.observable_registration_measured_state_pad_bracket_contract.v1"
)
RECEIPT_SCHEMA = (
    "sim2claw.observable_registration_measured_state_pad_bracket_receipt.v1"
)
CONTRACT_PATH = (
    REPO_ROOT
    / "configs/evaluations/"
    "observable_registration_measured_state_pad_bracket_v1.json"
)
OUTPUT_DIRECTORY = (
    REPO_ROOT
    / "outputs/observable_registration_measured_state_pad_bracket_v1"
)
EXPECTED_OFFSETS = [
    0.0,
    0.005,
    0.01,
    0.015,
    0.02,
    0.025,
    0.03,
    0.035,
    0.04,
]
EXPECTED_LOCAL_Z = [
    -0.1205,
    -0.1155,
    -0.1105,
    -0.1055,
    -0.1005,
    -0.0955,
    -0.0905,
    -0.0855,
    -0.0805,
]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_measured_state_pad_bracket_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="OR38 fixed-pad bracket")
    _require(contract.get("schema_version") == SCHEMA, "unsupported contract")
    for name, binding in contract["sources"].items():
        _bound_path(binding, root=root, label=name)
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
    grid = contract["fixed_pad_grid"]
    _require(
        grid["fixed_coverage_offsets_m"] == EXPECTED_OFFSETS
        and grid["implied_fixed_pad_local_z_m"] == EXPECTED_LOCAL_Z
        and grid["terminal_position_or_task_outcome_used_for_selection"]
        is False,
        "fixed pad bracket widened",
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
        "contact skin changed outside the fixed pad coordinate",
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
    return contract


def _sample(event: dict[str, Any] | None) -> int | None:
    return None if event is None else int(event["source_sample_index"])


def _interval_distance(
    value: int | None, interval: list[int]
) -> int:
    if value is None:
        return 1000
    if value < interval[0]:
        return interval[0] - value
    if value > interval[1]:
        return value - interval[1]
    return 0


def _preterminal_report(
    contract: dict[str, Any], result: dict[str, Any]
) -> dict[str, Any]:
    gates = contract["preterminal_gates"]
    natural = result["natural_dynamics"]
    trace = result["trace_summary"]
    contact = natural["first_selected_jaw_contact_sample"]
    motion = natural["first_motion_over_1mm_sample"]
    support = _sample(trace["first_sustained_support_loss"])
    bilateral = _sample(trace["first_bilateral_jaw_contact"])
    tilt = float(trace["tilt_at_sample_260_degrees"])
    reports = {
        "contact_timing": (
            contact is not None
            and gates["first_selected_jaw_contact_interval_samples"][0]
            <= contact
            <= gates["first_selected_jaw_contact_interval_samples"][1]
        ),
        "no_early_motion": (
            motion is None
            or motion >= gates["no_motion_over_1mm_before_sample"]
        ),
        "support_loss_timing": (
            support is not None
            and gates["sustained_support_loss_interval_samples"][0]
            <= support
            <= gates["sustained_support_loss_interval_samples"][1]
        ),
        "bilateral_contact_timing": (
            bilateral is not None
            and gates["bilateral_contact_interval_samples"][0]
            <= bilateral
            <= gates["bilateral_contact_interval_samples"][1]
        ),
        "upright_at_sample_260": (
            tilt <= gates["maximum_tilt_at_sample_260_degrees"]
        ),
    }
    interval_residual = sum(
        (
            _interval_distance(
                contact,
                gates["first_selected_jaw_contact_interval_samples"],
            ),
            _interval_distance(
                motion,
                [
                    gates["no_motion_over_1mm_before_sample"],
                    gates["sustained_support_loss_interval_samples"][1],
                ],
            ),
            _interval_distance(
                support, gates["sustained_support_loss_interval_samples"]
            ),
            _interval_distance(
                bilateral, gates["bilateral_contact_interval_samples"]
            ),
        )
    )
    return {
        "first_selected_jaw_contact_sample": contact,
        "first_motion_over_1mm_sample": motion,
        "first_sustained_support_loss_sample": support,
        "first_bilateral_jaw_contact_sample": bilateral,
        "tilt_at_sample_260_degrees": tilt,
        "gates": reports,
        "gate_count": sum(reports.values()),
        "interval_residual_samples": interval_residual,
    }


def _selection_key(row: dict[str, Any]) -> tuple[float, ...]:
    report = row["preterminal_report"]
    return (
        -float(report["gate_count"]),
        float(report["interval_residual_samples"]),
        float(report["tilt_at_sample_260_degrees"]),
        abs(float(row["fixed_coverage_offset_m"]) - 0.02),
    )


def run_measured_state_pad_bracket_once(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    _require(not receipt_path.exists(), "OR38 one-run receipt already exists")
    contract = load_measured_state_pad_bracket_contract(
        contract_path, root=root
    )
    or37a = _bound_json(
        contract["sources"]["or37a_receipt"],
        root=root,
        label="OR37A receipt",
    )
    or37b = _bound_json(
        contract["sources"]["or37b_receipt"],
        root=root,
        label="OR37B receipt",
    )
    _require(
        or37a["status"] == "PARTIAL_CROSS_EPISODE_CONTACT_SKIN_ADVANCEMENT"
        and or37b["status"] == "PARTIAL_PRIOR_PAD_POSITION_ADVANCEMENT",
        "fixed-pad endpoint evidence drifted",
    )
    c2_path = _bound_path(
        contract["sources"]["c2_contact_skin_contract"],
        root=root,
        label="C2 contact-skin contract",
    )
    rows: list[dict[str, Any]] = []
    traces: list[dict[str, Any]] = []
    for index, offset in enumerate(EXPECTED_OFFSETS):
        candidate_contract = copy.deepcopy(contract)
        candidate_contract["contact_skin_intervention"][
            "tip_fixed_coverage_offset_m"
        ] = offset
        variant = {
            "variant_id": f"fixed_pad_grid_{index:02d}",
            "role": "bounded_preterminal_contact_event_candidate",
            "sts3215_force_limit_nm": 2.94,
        }
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
        mutation = result["model_mutation_report"]
        fixed_pad = next(
            row
            for row in mutation["contact_skin_pads"]
            if row["finger"] == "fixed"
        )
        expected_z = EXPECTED_LOCAL_Z[index]
        _require(
            mutation["contact_skin_pad_count"] == 2
            and abs(float(fixed_pad["position"][2]) - expected_z) < 1e-12,
            "grid candidate did not compile at its frozen coordinate",
        )
        disabled_names = {
            row["geom_name"]
            for row in mutation["disabled_original_jaw_collision_geoms"]
        }
        topology = _contact_topology_summary(
            trace,
            analysis_start=int(
                contract["trace"]["analysis_source_sample_start"]
            ),
            analysis_end=int(
                contract["trace"]["analysis_source_sample_end"]
            ),
            disabled_geom_names=disabled_names,
        )
        rows.append(
            {
                "variant_id": variant["variant_id"],
                "fixed_coverage_offset_m": offset,
                "fixed_pad_local_z_m": float(fixed_pad["position"][2]),
                "preterminal_report": _preterminal_report(contract, result),
                "contact_topology": topology,
                "result": result,
            }
        )
        traces.append(trace)

    selected_index = min(range(len(rows)), key=lambda value: _selection_key(rows[value]))
    selected = rows[selected_index]
    selected_report = selected["preterminal_report"]
    selected_outcome = selected["result"]["natural_dynamics"]["outcome"]
    preterminal_pass = all(selected_report["gates"].values())
    full_pass = (
        preterminal_pass
        and selected_outcome["numeric_task_success"] is True
    )
    status = (
        "PASS_FULL_PHYSICS_DRIVEN_REPLAY"
        if full_pass
        else "PARTIAL_BOUNDED_CONTACT_EVENT_CALIBRATION"
    )

    output_directory.mkdir(parents=True, exist_ok=False)
    trace_bindings: list[dict[str, Any]] = []
    for row, trace in zip(rows, traces, strict=True):
        trace_path = output_directory / f"{row['variant_id']}_trace.json"
        atomic_write_json(trace_path, trace)
        trace_bindings.append(
            {
                "variant_id": row["variant_id"],
                "path": trace_path.name,
                "sha256": _sha256(trace_path),
            }
        )
        row["result"]["trace_path"] = trace_path.name
        row["result"]["trace_sha256"] = trace_bindings[-1]["sha256"]

    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "proof_class": contract["proof_class"],
        "status": status,
        "predecessor_artifact_sha256": {
            "or37a": or37a["artifact_sha256"],
            "or37b": or37b["artifact_sha256"],
        },
        "candidate_count": len(rows),
        "selection_inputs": contract["fixed_pad_grid"]["selection_inputs"],
        "terminal_position_or_task_outcome_used_for_selection": False,
        "selection_key": list(_selection_key(selected)),
        "selected_index": selected_index,
        "selected_variant_id": selected["variant_id"],
        "selected_fixed_pad_local_z_m": selected["fixed_pad_local_z_m"],
        "selected_preterminal_report": selected_report,
        "selected_terminal_outcome_reported_after_selection": selected_outcome,
        "selected_signed_progress_toward_d2_m": selected["result"][
            "natural_dynamics"
        ]["signed_progress_toward_d2_m"],
        "preterminal_gate_pass": preterminal_pass,
        "full_physics_driven_replay_pass": full_pass,
        "candidates": rows,
        "trace_bindings": trace_bindings,
        "single_simulator_coordinate_changed": (
            "fixed_contact_skin_longitudinal_position"
        ),
        "object_pose_injection_used": False,
        "latch_attachment_grasp_mode_or_support_projection_used": False,
        "raw_measured_state_changed": False,
        "actuator_force_gain_or_driver_changed": False,
        "pawn_board_reset_or_solver_changed": False,
        "destination_terminal_outcome_fit_performed": False,
        "global_mapping_approved": False,
        "simulator_promoted": False,
        "transfer_claim": False,
        "authority": contract["authority"],
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


def main() -> int:
    run_measured_state_pad_bracket_once()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
