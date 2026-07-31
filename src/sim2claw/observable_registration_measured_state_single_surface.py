"""Test one exact contact-bearing mesh surface per jaw under the OR34 driver."""

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
from .observable_registration_measured_state_contact_topology import (
    _baseline_regression,
    _contact_topology_summary,
)
from .observable_registration_measured_state_load_path import (
    _candidate_gate_report,
    _run_variant,
)


SCHEMA = (
    "sim2claw.observable_registration_measured_state_single_surface_contract.v1"
)
RECEIPT_SCHEMA = (
    "sim2claw.observable_registration_measured_state_single_surface_receipt.v1"
)
CONTRACT_PATH = (
    REPO_ROOT
    / "configs/evaluations/"
    "observable_registration_measured_state_single_surface_v1.json"
)
OUTPUT_DIRECTORY = (
    REPO_ROOT
    / "outputs/observable_registration_measured_state_single_surface_v1"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_measured_state_single_surface_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="OR36S single surface")
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
        and baseline["one_contact_bearing_mesh_per_jaw"] is False
        and candidate["one_contact_bearing_mesh_per_jaw"] is True,
        "single-surface variant family widened",
    )
    intervention = contract["single_surface_intervention"]
    _require(
        intervention["target_bodies"] == sorted(JAW_BODY_NAMES)
        and intervention["preserved_collision_mesh_by_body"]
        == {
            "left_gripper": "mjobj_geom-483",
            "left_moving_jaw_so101_v1": "mjobj_geom-494",
        }
        and intervention[
            "disable_every_other_collision_enabled_geom_on_target_bodies"
        ]
        is True
        and intervention[
            "preserve_selected_mesh_geometry_pose_material_friction_solref_solimp_and_condim"
        ]
        is True
        and intervention["candidate_selected_without_terminal_task_outcome"]
        is True,
        "single-surface intervention widened",
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
    return contract


def _single_surface_mutator(
    preserved_by_body: dict[str, str]
) -> Any:
    def mutate(model: mujoco.MjModel) -> dict[str, Any]:
        disabled: list[dict[str, Any]] = []
        preserved: list[dict[str, Any]] = []
        for geom_id in range(model.ngeom):
            body_id = int(model.geom_bodyid[geom_id])
            body_name = _name(
                model, mujoco.mjtObj.mjOBJ_BODY, body_id
            )
            if body_name not in JAW_BODY_NAMES:
                continue
            collision_enabled = bool(
                int(model.geom_contype[geom_id])
                or int(model.geom_conaffinity[geom_id])
            )
            if not collision_enabled:
                continue
            geom_name = _name(
                model, mujoco.mjtObj.mjOBJ_GEOM, geom_id
            )
            row = {
                "geom_id": geom_id,
                "geom_name": geom_name,
                "body_name": body_name,
                "geom_type": int(model.geom_type[geom_id]),
                "contype_before": int(model.geom_contype[geom_id]),
                "conaffinity_before": int(
                    model.geom_conaffinity[geom_id]
                ),
            }
            if geom_name == preserved_by_body[body_name]:
                _require(
                    int(model.geom_type[geom_id])
                    == int(mujoco.mjtGeom.mjGEOM_MESH),
                    "preserved outer surface is not a mesh",
                )
                preserved.append(row)
            else:
                disabled.append(row)
                model.geom_contype[geom_id] = 0
                model.geom_conaffinity[geom_id] = 0
        _require(
            {row["body_name"]: row["geom_name"] for row in preserved}
            == preserved_by_body,
            "exact one-surface binding did not compile",
        )
        return {
            "preserved_collision_surfaces": preserved,
            "preserved_collision_surface_count": len(preserved),
            "disabled_collision_geoms": disabled,
            "disabled_collision_geom_count": len(disabled),
            "changed_arrays": ["geom_contype", "geom_conaffinity"],
            "geometry_size_pose_material_friction_solref_solimp_condim_changed": (
                False
            ),
        }

    return mutate


def run_measured_state_single_surface_once(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    _require(not receipt_path.exists(), "OR36S one-run receipt already exists")
    contract = load_measured_state_single_surface_contract(
        contract_path, root=root
    )
    predecessor = _bound_json(
        contract["sources"]["or36b_receipt"],
        root=root,
        label="OR36B receipt",
    )
    baseline_variant, candidate_variant = contract["variants"]
    baseline, baseline_trace = _run_variant(
        contract=contract,
        variant=baseline_variant,
        root=root,
    )
    preserved = contract["single_surface_intervention"][
        "preserved_collision_mesh_by_body"
    ]
    candidate, candidate_trace = _run_variant(
        contract=contract,
        variant=candidate_variant,
        root=root,
        model_mutator=_single_surface_mutator(preserved),
    )
    regression = _baseline_regression(contract, baseline)
    _require(
        all(regression.values()),
        "OR34 baseline did not reproduce; OR36S rejected",
    )
    mutation = candidate["model_mutation_report"]
    _require(
        mutation["preserved_collision_surface_count"] == 2
        and mutation["disabled_collision_geom_count"] >= 1
        and mutation[
            "geometry_size_pose_material_friction_solref_solimp_condim_changed"
        ]
        is False,
        "single-surface intervention did not match the frozen scope",
    )
    disabled_names = {
        row["geom_name"] for row in mutation["disabled_collision_geoms"]
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
    preserved_names = set(preserved.values())
    topology_gates = {
        "exactly_two_collision_surfaces_preserved": (
            mutation["preserved_collision_surface_count"] == 2
        ),
        "disabled_geoms_absent_from_candidate_contacts": (
            candidate_topology["disabled_mesh_contact_count"] == 0
        ),
        "candidate_contact_geoms_within_preserved_surfaces": set(
            candidate_topology["contact_bearing_jaw_geoms"]
        ).issubset(preserved_names),
        "maximum_unique_jaw_geoms_at_most_two": (
            candidate_topology["maximum_unique_jaw_geoms_per_internal_step"]
            <= 2
        ),
        "contact_count_reduced": (
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
            "PARTIAL_SINGLE_SURFACE_ADVANCEMENT"
            if topology_pass and (endpoint_improved or upright_improved)
            else "TERMINAL_NEGATIVE_SINGLE_SURFACE"
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
            "one_contact_bearing_mesh_surface_per_jaw"
        ),
        "candidate_selected_or_revised_from_terminal_task_outcome": False,
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
    run_measured_state_single_surface_once()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
