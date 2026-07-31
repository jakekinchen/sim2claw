"""Test the exact C2 diagnosis-anchor fixed-pad position under the OR34 driver."""

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
from .observable_registration_measured_state_contact_skin import (
    _contact_skin_model_mutator,
    _contact_skin_parameters,
    _contact_skin_spec_mutator,
)
from .observable_registration_measured_state_contact_topology import (
    _baseline_regression,
    _contact_topology_summary,
)
from .observable_registration_measured_state_load_path import (
    _candidate_gate_report,
    _run_variant,
)


SCHEMA = (
    "sim2claw.observable_registration_measured_state_prior_pad_position_contract.v1"
)
RECEIPT_SCHEMA = (
    "sim2claw.observable_registration_measured_state_prior_pad_position_receipt.v1"
)
CONTRACT_PATH = (
    REPO_ROOT
    / "configs/evaluations/"
    "observable_registration_measured_state_prior_pad_position_v1.json"
)
OUTPUT_DIRECTORY = (
    REPO_ROOT
    / "outputs/observable_registration_measured_state_prior_pad_position_v1"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_measured_state_prior_pad_position_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="OR37B prior pad position")
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
        "raw-state trajectory boundary widened",
    )
    baseline, candidate = contract["variants"]
    _require(
        len(contract["variants"]) == 2
        and baseline["sts3215_force_limit_nm"] == 2.94
        and candidate["sts3215_force_limit_nm"] == 2.94
        and baseline["prior_fixed_pad_position_enabled"] is False
        and candidate["prior_fixed_pad_position_enabled"] is True,
        "prior-position variant family widened",
    )
    skin = contract["contact_skin_intervention"]
    _require(
        skin["tip_thickness_m"] == 0.001
        and skin["tip_half_width_m"] == 0.0065
        and skin["tip_coverage_m"] == 0.02
        and skin["tip_coverage_offset_m"] == -0.03
        and skin["tip_fixed_coverage_offset_m"] == 0.0
        and skin["tip_moving_coverage_offset_m"] == 0.025
        and skin["fixed_pad_expected_local_z_m"] == -0.1205
        and skin["candidate_selected_without_destination_terminal_outcome"]
        is True,
        "prior fixed-pad binding widened",
    )
    diagnosis_path = _bound_path(
        contract["sources"]["c2_contact_skin_diagnosis_contract"],
        root=root,
        label="C2 contact-skin diagnosis contract",
    )
    c2 = load_json_object(
        diagnosis_path, label="C2 contact-skin diagnosis source"
    )
    _require(
        c2["diagnosis_anchor"]["baseline_fixed_rubber_center_local_z_m"]
        == -0.1205,
        "C2 fixed-rubber diagnosis anchor drifted",
    )
    simulation = contract["simulation"]
    _require(
        simulation["natural_pawn_dynamics_only"] is True
        and simulation[
            "selected_pawn_pose_written_only_during_initialization"
        ]
        is True
        and simulation["terminal_result_may_select_or_revise_candidate"]
        is False
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


def run_measured_state_prior_pad_position_once(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    _require(not receipt_path.exists(), "OR37B one-run receipt already exists")
    contract = load_measured_state_prior_pad_position_contract(
        contract_path, root=root
    )
    predecessor = _bound_json(
        contract["sources"]["or37a_receipt"],
        root=root,
        label="OR37A receipt",
    )
    baseline_variant, candidate_variant = contract["variants"]
    baseline, baseline_trace = _run_variant(
        contract=contract,
        variant=baseline_variant,
        root=root,
    )
    c2_path = _bound_path(
        contract["sources"]["c2_contact_skin_contract"],
        root=root,
        label="C2 contact-skin contract",
    )
    parameters = _contact_skin_parameters(contract)
    candidate, candidate_trace = _run_variant(
        contract=contract,
        variant=candidate_variant,
        root=root,
        spec_mutator=_contact_skin_spec_mutator(
            contract=contract,
            c2_contract_path=c2_path,
        ),
        model_mutator=_contact_skin_model_mutator(parameters),
    )
    regression = _baseline_regression(contract, baseline)
    _require(
        all(regression.values()),
        "OR34 baseline did not reproduce; OR37B rejected",
    )
    mutation = candidate["model_mutation_report"]
    pads = mutation["contact_skin_pads"]
    fixed_pad = next(row for row in pads if row["finger"] == "fixed")
    _require(
        mutation["contact_skin_pad_count"] == 2
        and abs(
            float(fixed_pad["position"][2])
            - float(
                contract["contact_skin_intervention"][
                    "fixed_pad_expected_local_z_m"
                ]
            )
        )
        < 1e-12,
        "fixed pad did not compile at the exact C2 diagnosis anchor",
    )
    disabled_names = {
        row["geom_name"]
        for row in mutation["disabled_original_jaw_collision_geoms"]
    }
    analysis_start = int(contract["trace"]["analysis_source_sample_start"])
    analysis_end = int(contract["trace"]["analysis_source_sample_end"])
    baseline_topology = _contact_topology_summary(
        baseline_trace,
        analysis_start=analysis_start,
        analysis_end=analysis_end,
        disabled_geom_names=disabled_names,
    )
    candidate_topology = _contact_topology_summary(
        candidate_trace,
        analysis_start=analysis_start,
        analysis_end=analysis_end,
        disabled_geom_names=disabled_names,
    )
    pad_names = {row["geom_name"] for row in pads}
    topology_gates = {
        "exactly_two_contact_skin_pads": (
            mutation["contact_skin_pad_count"] == 2
        ),
        "fixed_pad_at_exact_prior_position": (
            abs(float(fixed_pad["position"][2]) + 0.1205) < 1e-12
        ),
        "disabled_original_geoms_absent_from_candidate_contacts": (
            candidate_topology["disabled_mesh_contact_count"] == 0
        ),
        "candidate_contact_geoms_within_contact_skin": set(
            candidate_topology["contact_bearing_jaw_geoms"]
        ).issubset(pad_names),
        "maximum_unique_jaw_geoms_at_most_two": (
            candidate_topology["maximum_unique_jaw_geoms_per_internal_step"]
            <= 2
        ),
        "actuator_force_envelope_unchanged": (
            candidate["sts3215_force_limit_nm"] == 2.94
        ),
    }
    candidate_gates = _candidate_gate_report(contract, candidate)
    early_names = (
        "contact_timing",
        "no_early_motion",
        "support_loss_timing",
        "upright_at_carry_start",
    )
    early_pass = all(candidate_gates[name] for name in early_names)
    terminal_pass = all(
        value
        for name, value in candidate_gates.items()
        if name not in early_names
    )
    topology_pass = all(topology_gates.values())
    full_pass = topology_pass and early_pass and terminal_pass
    candidate_outcome = candidate["natural_dynamics"]["outcome"]
    causal_advancement = (
        candidate["trace_summary"]["first_bilateral_jaw_contact"] is not None
        or candidate_outcome["final_upright_tilt_degrees"]
        < baseline["natural_dynamics"]["outcome"][
            "final_upright_tilt_degrees"
        ]
    )
    status = (
        "PASS_FULL_PHYSICS_DRIVEN_REPLAY"
        if full_pass
        else (
            "PARTIAL_PRIOR_PAD_POSITION_ADVANCEMENT"
            if topology_pass and causal_advancement
            else "TERMINAL_NEGATIVE_PRIOR_PAD_POSITION"
        )
    )

    output_directory.mkdir(parents=True, exist_ok=False)
    trace_bindings: dict[str, dict[str, str]] = {}
    for result, trace in (
        (baseline, baseline_trace),
        (candidate, candidate_trace),
    ):
        trace_path = output_directory / f"{result['variant_id']}_trace.json"
        atomic_write_json(trace_path, trace)
        result["trace_path"] = trace_path.name
        result["trace_sha256"] = _sha256(trace_path)
        trace_bindings[result["variant_id"]] = {
            "path": trace_path.name,
            "sha256": result["trace_sha256"],
        }
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "proof_class": contract["proof_class"],
        "status": status,
        "predecessor_artifact_sha256": predecessor["artifact_sha256"],
        "baseline_regression": regression,
        "variants": [baseline, candidate],
        "baseline_contact_topology": baseline_topology,
        "candidate_contact_topology": candidate_topology,
        "topology_gate_report": topology_gates,
        "candidate_gate_report": candidate_gates,
        "early_causal_gates_pass": early_pass,
        "terminal_task_gates_pass": terminal_pass,
        "full_physics_driven_replay_pass": full_pass,
        "single_simulator_mechanism_changed": (
            "fixed_contact_skin_longitudinal_position"
        ),
        "destination_episode_parameter_refit_performed": False,
        "candidate_selected_or_revised_from_destination_terminal_outcome": (
            False
        ),
        "trace_bindings": trace_bindings,
        "object_pose_injection_used": False,
        "latch_attachment_grasp_mode_or_support_projection_used": False,
        "raw_measured_state_changed": False,
        "actuator_force_gain_or_driver_changed": False,
        "pawn_board_reset_or_solver_changed": False,
        "global_mapping_approved": False,
        "simulator_promoted": False,
        "action_only_transfer": False,
        "transfer_claim": False,
        "authority": contract["authority"],
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


def main() -> int:
    run_measured_state_prior_pad_position_once()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
