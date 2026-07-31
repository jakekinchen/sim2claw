"""Cross-episode test of one frozen two-sided rubber jaw contact skin."""

from __future__ import annotations

import copy
import hashlib
from pathlib import Path
from typing import Any

import mujoco

from .contact_prior import (
    apply_contact_variant,
    read_contact_prior_snapshot,
)
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
from .pawn_bg_grasp_coordinate_descent import _custom_variant


SCHEMA = (
    "sim2claw.observable_registration_measured_state_contact_skin_contract.v1"
)
RECEIPT_SCHEMA = (
    "sim2claw.observable_registration_measured_state_contact_skin_receipt.v1"
)
CONTRACT_PATH = (
    REPO_ROOT
    / "configs/evaluations/"
    "observable_registration_measured_state_contact_skin_v1.json"
)
OUTPUT_DIRECTORY = (
    REPO_ROOT
    / "outputs/observable_registration_measured_state_contact_skin_v1"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_measured_state_contact_skin_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="OR37A contact skin")
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
        and baseline["frozen_c2_contact_skin_enabled"] is False
        and candidate["frozen_c2_contact_skin_enabled"] is True,
        "contact-skin variant family widened",
    )
    skin = contract["contact_skin_intervention"]
    expected = {
        "tip_thickness_m": 0.001,
        "tip_half_width_m": 0.0065,
        "tip_coverage_m": 0.02,
        "tip_coverage_offset_m": -0.03,
        "tip_fixed_coverage_offset_m": 0.04,
        "tip_moving_coverage_offset_m": 0.025,
        "sliding_friction": 1.8,
        "torsional_friction_m": 0.012,
        "rolling_friction_m": 0.0012,
        "rubber_contact_condim": 6,
        "solref_time_constant_s": 0.006,
        "solref_damping_ratio": 1.2,
        "solimp": [0.95, 0.98, 0.0005, 0.5, 2.0],
    }
    _require(
        all(skin[name] == value for name, value in expected.items())
        and skin["zero_refit_on_destination_episode"] is True
        and skin["add_exactly_one_pad_per_jaw"] is True
        and skin[
            "disable_all_original_collision_enabled_geoms_on_target_jaws"
        ]
        is True
        and skin["candidate_selected_without_destination_terminal_outcome"]
        is True,
        "frozen contact-skin tuple widened",
    )
    c2_path = _bound_path(
        contract["sources"]["c2_contact_skin_contract"],
        root=root,
        label="C2 contact-skin contract",
    )
    c2 = load_json_object(c2_path, label="C2 contact-skin source")
    _require(
        all(c2["base_parameters"][name] == value for name, value in expected.items() if name != "solimp"),
        "C2 contact-skin source tuple drifted",
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


def _contact_skin_parameters(
    contract: dict[str, Any],
) -> dict[str, Any]:
    skin = contract["contact_skin_intervention"]
    return {
        "rubber_tip_enabled": True,
        "tip_thickness_m": float(skin["tip_thickness_m"]),
        "tip_half_width_m": float(skin["tip_half_width_m"]),
        "tip_coverage_m": float(skin["tip_coverage_m"]),
        "tip_coverage_offset_m": float(skin["tip_coverage_offset_m"]),
        "tip_fixed_coverage_offset_m": float(
            skin["tip_fixed_coverage_offset_m"]
        ),
        "tip_moving_coverage_offset_m": float(
            skin["tip_moving_coverage_offset_m"]
        ),
        "sliding_friction": float(skin["sliding_friction"]),
        "torsional_friction_m": float(skin["torsional_friction_m"]),
        "rolling_friction_m": float(skin["rolling_friction_m"]),
        "rubber_contact_condim": int(skin["rubber_contact_condim"]),
        "solref_time_constant_s": float(
            skin["solref_time_constant_s"]
        ),
        "solref_damping_ratio": float(skin["solref_damping_ratio"]),
    }


def _contact_skin_spec_mutator(
    *,
    contract: dict[str, Any],
    c2_contract_path: Path,
) -> Any:
    parameters = _contact_skin_parameters(contract)
    contact_snapshot = read_contact_prior_snapshot(
        _bound_path(
            contract["sources"]["rubber_contact_prior"],
            root=REPO_ROOT,
            label="rubber contact prior",
        )
    )
    variant = _custom_variant(
        parameters=parameters,
        contract_path=c2_contract_path,
        contact_snapshot=contact_snapshot,
    )

    def mutate(spec: mujoco.MjSpec) -> dict[str, Any]:
        report = apply_contact_variant(spec, variant)
        return {
            "variant_id": variant.variant_id,
            "variant_sha256": variant.variant_sha256,
            "added_geoms": report["added_geoms"],
            "bindings": report["bindings"],
            "parameter_source": (
                "frozen_c2_contact_skin_zero_refit_on_d1_to_d2"
            ),
        }

    return mutate


def _contact_skin_model_mutator(
    parameters: dict[str, Any]
) -> Any:
    def mutate(model: mujoco.MjModel) -> dict[str, Any]:
        pads: list[dict[str, Any]] = []
        disabled: list[dict[str, Any]] = []
        for geom_id in range(model.ngeom):
            body_id = int(model.geom_bodyid[geom_id])
            body_name = _name(
                model, mujoco.mjtObj.mjOBJ_BODY, body_id
            )
            if body_name not in JAW_BODY_NAMES:
                continue
            geom_name = _name(
                model, mujoco.mjtObj.mjOBJ_GEOM, geom_id
            )
            collision_enabled = bool(
                int(model.geom_contype[geom_id])
                or int(model.geom_conaffinity[geom_id])
            )
            if "_rubber_tip_fixed_" in geom_name:
                model.geom_pos[geom_id, 2] += (
                    float(parameters["tip_coverage_offset_m"])
                    + float(parameters["tip_fixed_coverage_offset_m"])
                )
                pads.append(
                    {
                        "finger": "fixed",
                        "geom_id": geom_id,
                        "geom_name": geom_name,
                    }
                )
            elif "_rubber_tip_moving_" in geom_name:
                model.geom_pos[geom_id, 1] += (
                    float(parameters["tip_coverage_offset_m"])
                    + float(parameters["tip_moving_coverage_offset_m"])
                )
                pads.append(
                    {
                        "finger": "moving",
                        "geom_id": geom_id,
                        "geom_name": geom_name,
                    }
                )
            elif collision_enabled:
                disabled.append(
                    {
                        "geom_id": geom_id,
                        "geom_name": geom_name,
                        "body_name": body_name,
                    }
                )
                model.geom_contype[geom_id] = 0
                model.geom_conaffinity[geom_id] = 0
        _require(
            sorted(row["finger"] for row in pads) == ["fixed", "moving"],
            "exactly one frozen contact pad per jaw did not compile",
        )
        for row in pads:
            geom_id = int(row["geom_id"])
            row.update(
                {
                    "position": model.geom_pos[geom_id].astype(float).tolist(),
                    "size": model.geom_size[geom_id].astype(float).tolist(),
                    "friction": model.geom_friction[geom_id]
                    .astype(float)
                    .tolist(),
                    "solref": model.geom_solref[geom_id]
                    .astype(float)
                    .tolist(),
                    "solimp": model.geom_solimp[geom_id]
                    .astype(float)
                    .tolist(),
                    "condim": int(model.geom_condim[geom_id]),
                }
            )
        return {
            "contact_skin_pads": pads,
            "contact_skin_pad_count": len(pads),
            "disabled_original_jaw_collision_geoms": disabled,
            "disabled_original_jaw_collision_geom_count": len(disabled),
            "actuator_force_gain_or_driver_changed": False,
            "pawn_board_reset_or_solver_changed": False,
        }

    return mutate


def run_measured_state_contact_skin_once(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    _require(not receipt_path.exists(), "OR37A one-run receipt already exists")
    contract = load_measured_state_contact_skin_contract(
        contract_path, root=root
    )
    predecessor = _bound_json(
        contract["sources"]["or36s_receipt"],
        root=root,
        label="OR36S receipt",
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
        "OR34 baseline did not reproduce; OR37A rejected",
    )
    mutation = candidate["model_mutation_report"]
    _require(
        mutation["contact_skin_pad_count"] == 2
        and mutation["disabled_original_jaw_collision_geom_count"] >= 1
        and mutation["actuator_force_gain_or_driver_changed"] is False
        and mutation["pawn_board_reset_or_solver_changed"] is False,
        "contact-skin intervention did not match the frozen scope",
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
    pad_names = {
        row["geom_name"] for row in mutation["contact_skin_pads"]
    }
    topology_gates = {
        "exactly_two_contact_skin_pads": (
            mutation["contact_skin_pad_count"] == 2
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
    baseline_outcome = baseline["natural_dynamics"]["outcome"]
    candidate_outcome = candidate["natural_dynamics"]["outcome"]
    causal_advancement = (
        candidate["natural_dynamics"]["first_motion_over_1mm_sample"]
        != baseline["natural_dynamics"]["first_motion_over_1mm_sample"]
        or candidate_outcome["final_upright_tilt_degrees"]
        < baseline_outcome["final_upright_tilt_degrees"]
        or candidate_outcome["final_planar_center_error_m"]
        < baseline_outcome["final_planar_center_error_m"]
    )
    status = (
        "PASS_FULL_PHYSICS_DRIVEN_REPLAY"
        if full_pass
        else (
            "PARTIAL_CROSS_EPISODE_CONTACT_SKIN_ADVANCEMENT"
            if topology_pass and causal_advancement
            else "TERMINAL_NEGATIVE_CROSS_EPISODE_CONTACT_SKIN"
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
            "frozen_c2_two_sided_rubber_contact_skin"
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
    run_measured_state_contact_skin_once()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
