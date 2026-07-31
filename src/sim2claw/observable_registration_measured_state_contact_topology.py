"""Test one topology-only jaw collision challenger under the OR34 raw driver."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import mujoco

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
from .observable_registration_exact_replay_contact_introspection import (
    JAW_BODY_NAMES,
    _name,
)
from .observable_registration_measured_state_load_path import (
    _candidate_gate_report,
    _run_variant,
)


SCHEMA = (
    "sim2claw.observable_registration_measured_state_contact_topology_contract.v1"
)
RECEIPT_SCHEMA = (
    "sim2claw.observable_registration_measured_state_contact_topology_receipt.v1"
)
CONTRACT_PATH = (
    REPO_ROOT
    / "configs/evaluations/"
    "observable_registration_measured_state_contact_topology_v1.json"
)
OUTPUT_DIRECTORY = (
    REPO_ROOT
    / "outputs/observable_registration_measured_state_contact_topology_v1"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_measured_state_contact_topology_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="OR36B contact topology")
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
        and baseline["disable_collision_bearing_jaw_mesh_cores"] is False
        and candidate["disable_collision_bearing_jaw_mesh_cores"] is True,
        "topology variant family widened",
    )
    topology = contract["topology_intervention"]
    _require(
        topology["target_bodies"] == sorted(JAW_BODY_NAMES)
        and topology["disable_only_collision_enabled_mesh_geoms"] is True
        and topology["preserve_all_existing_primitive_geoms"] is True
        and topology[
            "preserve_geom_size_pose_material_friction_solref_solimp_and_condim"
        ]
        is True
        and topology["candidate_selected_without_task_outcome"] is True,
        "topology intervention widened",
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
                "contact_geometry_size_pose_or_material_change_allowed",
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
            value
            for name, value in authority.items()
            if name != "simulator_replay"
        ),
        "authority widened",
    )
    return contract


def _disable_collision_bearing_jaw_mesh_cores(
    model: mujoco.MjModel,
) -> dict[str, Any]:
    disabled: list[dict[str, Any]] = []
    preserved_primitives: list[str] = []
    for geom_id in range(model.ngeom):
        body_id = int(model.geom_bodyid[geom_id])
        body_name = _name(model, mujoco.mjtObj.mjOBJ_BODY, body_id)
        if body_name not in JAW_BODY_NAMES:
            continue
        geom_name = _name(model, mujoco.mjtObj.mjOBJ_GEOM, geom_id)
        collision_enabled = bool(
            int(model.geom_contype[geom_id])
            or int(model.geom_conaffinity[geom_id])
        )
        if int(model.geom_type[geom_id]) == int(
            mujoco.mjtGeom.mjGEOM_MESH
        ):
            if not collision_enabled:
                continue
            disabled.append(
                {
                    "geom_id": geom_id,
                    "geom_name": geom_name,
                    "body_name": body_name,
                    "type": "mesh",
                    "contype_before": int(model.geom_contype[geom_id]),
                    "conaffinity_before": int(
                        model.geom_conaffinity[geom_id]
                    ),
                }
            )
            model.geom_contype[geom_id] = 0
            model.geom_conaffinity[geom_id] = 0
        elif collision_enabled:
            preserved_primitives.append(geom_name)
    return {
        "disabled_collision_mesh_geoms": disabled,
        "disabled_collision_mesh_geom_count": len(disabled),
        "preserved_collision_primitive_geoms": sorted(
            preserved_primitives
        ),
        "preserved_collision_primitive_geom_count": len(
            preserved_primitives
        ),
        "changed_arrays": ["geom_contype", "geom_conaffinity"],
        "geometry_size_pose_material_friction_solref_solimp_condim_changed": (
            False
        ),
    }


def _contact_topology_summary(
    trace: dict[str, Any],
    *,
    analysis_start: int,
    analysis_end: int,
    disabled_geom_names: set[str],
) -> dict[str, Any]:
    maximum_contacts = 0
    maximum_unique_geoms = 0
    disabled_contact_count = 0
    mesh_plus_primitive_rows = 0
    jaw_contact_rows = 0
    contact_geoms: set[str] = set()
    for row in trace["rows"]:
        if (
            row["phase"] != "task"
            or not analysis_start
            <= row["source_sample_index"]
            <= analysis_end
        ):
            continue
        jaw_contacts = [
            contact
            for contact in row["contacts"]
            if contact["other_body"] in JAW_BODY_NAMES
        ]
        if not jaw_contacts:
            continue
        jaw_contact_rows += 1
        names = {contact["other_geom"] for contact in jaw_contacts}
        contact_geoms.update(names)
        disabled_here = names & disabled_geom_names
        enabled_here = names - disabled_geom_names
        disabled_contact_count += sum(
            contact["other_geom"] in disabled_geom_names
            for contact in jaw_contacts
        )
        if disabled_here and enabled_here:
            mesh_plus_primitive_rows += 1
        maximum_contacts = max(maximum_contacts, len(jaw_contacts))
        maximum_unique_geoms = max(maximum_unique_geoms, len(names))
    return {
        "jaw_contact_internal_rows": jaw_contact_rows,
        "maximum_jaw_pawn_contact_points_per_internal_step": (
            maximum_contacts
        ),
        "maximum_unique_jaw_geoms_per_internal_step": maximum_unique_geoms,
        "contact_bearing_jaw_geoms": sorted(contact_geoms),
        "disabled_mesh_contact_count": disabled_contact_count,
        "mesh_plus_primitive_simultaneous_internal_rows": (
            mesh_plus_primitive_rows
        ),
    }


def _baseline_regression(
    contract: dict[str, Any], result: dict[str, Any]
) -> dict[str, bool]:
    expected = contract["baseline_regression"]
    natural = result["natural_dynamics"]
    outcome = natural["outcome"]
    tolerance = float(expected["absolute_tolerance"])
    return {
        "first_selected_jaw_contact_sample": (
            natural["first_selected_jaw_contact_sample"]
            == expected["first_selected_jaw_contact_sample"]
        ),
        "first_motion_over_1mm_sample": (
            natural["first_motion_over_1mm_sample"]
            == expected["first_motion_over_1mm_sample"]
        ),
        "signed_progress_toward_d2_m": (
            abs(
                natural["signed_progress_toward_d2_m"]
                - expected["signed_progress_toward_d2_m"]
            )
            <= tolerance
        ),
        "final_upright_tilt_degrees": (
            abs(
                outcome["final_upright_tilt_degrees"]
                - expected["final_upright_tilt_degrees"]
            )
            <= tolerance
        ),
        "final_planar_center_error_m": (
            abs(
                outcome["final_planar_center_error_m"]
                - expected["final_planar_center_error_m"]
            )
            <= tolerance
        ),
    }


def run_measured_state_contact_topology_once(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    _require(not receipt_path.exists(), "OR36B one-run receipt already exists")
    contract = load_measured_state_contact_topology_contract(
        contract_path, root=root
    )
    predecessor = _bound_json(
        contract["sources"]["or35_receipt"],
        root=root,
        label="OR35 receipt",
    )
    baseline_variant, candidate_variant = contract["variants"]
    baseline, baseline_trace = _run_variant(
        contract=contract,
        variant=baseline_variant,
        root=root,
    )
    candidate, candidate_trace = _run_variant(
        contract=contract,
        variant=candidate_variant,
        root=root,
        model_mutator=_disable_collision_bearing_jaw_mesh_cores,
    )
    regression = _baseline_regression(contract, baseline)
    _require(
        all(regression.values()),
        "OR34 baseline did not reproduce; OR36B rejected",
    )
    mutation = candidate["model_mutation_report"]
    _require(
        mutation["disabled_collision_mesh_geom_count"]
        >= int(
            contract["topology_intervention"][
                "minimum_disabled_mesh_geom_count"
            ]
        )
        and mutation[
            "geometry_size_pose_material_friction_solref_solimp_condim_changed"
        ]
        is False,
        "topology intervention did not match the frozen scope",
    )
    disabled_names = {
        row["geom_name"]
        for row in mutation["disabled_collision_mesh_geoms"]
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
    topology_gates = {
        "disabled_meshes_were_contact_bearing_in_baseline": (
            baseline_topology["disabled_mesh_contact_count"] > 0
        ),
        "disabled_meshes_absent_from_candidate_contacts": (
            candidate_topology["disabled_mesh_contact_count"] == 0
        ),
        "mesh_plus_primitive_overlap_removed": (
            baseline_topology[
                "mesh_plus_primitive_simultaneous_internal_rows"
            ]
            > 0
            and candidate_topology[
                "mesh_plus_primitive_simultaneous_internal_rows"
            ]
            == 0
        ),
        "maximum_contact_count_reduced": (
            candidate_topology[
                "maximum_jaw_pawn_contact_points_per_internal_step"
            ]
            < baseline_topology[
                "maximum_jaw_pawn_contact_points_per_internal_step"
            ]
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
    baseline_outcome = baseline["natural_dynamics"]["outcome"]
    candidate_outcome = candidate["natural_dynamics"]["outcome"]
    endpoint_improved = (
        candidate_outcome["final_planar_center_error_m"]
        < baseline_outcome["final_planar_center_error_m"]
    )
    upright_improved = (
        candidate_outcome["final_upright_tilt_degrees"]
        < baseline_outcome["final_upright_tilt_degrees"]
    )
    status = (
        "PASS_FULL_PHYSICS_DRIVEN_REPLAY"
        if full_pass
        else (
            "PARTIAL_TOPOLOGY_ADVANCEMENT"
            if topology_pass and (endpoint_improved or upright_improved)
            else "TERMINAL_NEGATIVE_CONTACT_TOPOLOGY"
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
            "disable_collision_bearing_jaw_mesh_cores"
        ),
        "candidate_selected_or_revised_from_task_outcome": False,
        "trace_bindings": trace_bindings,
        "object_pose_injection_used": False,
        "latch_attachment_grasp_mode_or_support_projection_used": False,
        "raw_measured_state_changed": False,
        "actuator_force_gain_or_driver_changed": False,
        "contact_material_or_geometry_size_pose_changed": False,
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
    run_measured_state_contact_topology_once()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
