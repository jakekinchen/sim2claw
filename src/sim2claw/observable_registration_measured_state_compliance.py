"""Cross-episode test of frozen passive rubber-pad compliance on D1-to-D2."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import mujoco

from .contact_prior import apply_contact_variant, read_contact_prior_snapshot
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
from .pawn_bg_grasp_coordinate_descent import _custom_variant


SCHEMA = (
    "sim2claw.observable_registration_measured_state_compliance_contract.v1"
)
RECEIPT_SCHEMA = (
    "sim2claw.observable_registration_measured_state_compliance_receipt.v1"
)
CONTRACT_PATH = (
    REPO_ROOT
    / "configs/evaluations/"
    "observable_registration_measured_state_compliance_v1.json"
)
OUTPUT_DIRECTORY = (
    REPO_ROOT
    / "outputs/observable_registration_measured_state_compliance_v1"
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FactoryArtifactError(message)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_measured_state_compliance_contract(
    path: Path = CONTRACT_PATH, *, root: Path = REPO_ROOT
) -> dict[str, Any]:
    contract = load_json_object(path, label="OR39 passive compliance")
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
    baseline, candidate = contract["variants"]
    _require(
        len(contract["variants"]) == 2
        and baseline["normal_compliance_enabled"] is False
        and candidate["normal_compliance_enabled"] is True
        and baseline["sts3215_force_limit_nm"] == 2.94
        and candidate["sts3215_force_limit_nm"] == 2.94,
        "compliance isolation widened",
    )
    model = contract["contact_model"]
    expected = {
        "tip_thickness_m": 0.001,
        "tip_half_width_m": 0.006,
        "tip_coverage_m": 0.04,
        "tip_coverage_offset_m": 0.0,
        "tip_fixed_coverage_offset_m": 0.005,
        "tip_moving_coverage_offset_m": 0.0,
        "tip_fixed_thickness_multiplier": 2.0,
        "tip_moving_thickness_multiplier": 2.0,
        "tip_fixed_half_width_multiplier": 1.5,
        "tip_moving_half_width_multiplier": 1.3333333333333333,
        "tip_fixed_coverage_multiplier": 1.1,
        "tip_moving_coverage_multiplier": 0.36,
        "sliding_friction": 3.5,
        "rubber_tip_compliance_travel_m": 0.001,
        "rubber_tip_compliance_stiffness_n_per_m": 300.0,
        "rubber_tip_compliance_damping_n_s_per_m": 1.095,
        "rubber_tip_compliance_compression_only": True,
    }
    _require(
        all(model[name] == value for name, value in expected.items())
        and model["zero_refit_on_d1_to_d2"] is True
        and model["canonical_actuator_force_and_timestep_preserved"] is True,
        "cross-episode compliance tuple widened",
    )
    source = load_json_object(
        _bound_path(
            contract["sources"]["c2_compression_only_contract"],
            root=root,
            label="C2 compression-only source",
        ),
        label="C2 compression-only source",
    )["base_parameters"]
    _require(
        all(source[name] == value for name, value in expected.items()),
        "C2 compression-only source drifted",
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


def _parameters(
    contract: dict[str, Any], *, compliance_enabled: bool
) -> dict[str, Any]:
    model = contract["contact_model"]
    return {
        **model,
        "rubber_tip_enabled": True,
        "rubber_tip_normal_compliance_enabled": compliance_enabled,
        "rubber_tip_fixed_anchor_geom_suffix": "fixed_jaw_box5",
        "rubber_tip_moving_anchor_geom_suffix": "moving_jaw_box3",
    }


def _spec_mutator(
    *,
    contract: dict[str, Any],
    parameters: dict[str, Any],
    source_path: Path,
) -> Any:
    snapshot = read_contact_prior_snapshot(
        _bound_path(
            contract["sources"]["rubber_contact_prior"],
            root=REPO_ROOT,
            label="rubber contact prior",
        )
    )
    variant = _custom_variant(
        parameters=parameters,
        contract_path=source_path,
        contact_snapshot=snapshot,
    )

    def mutate(spec: mujoco.MjSpec) -> dict[str, Any]:
        report = apply_contact_variant(spec, variant)
        return {
            "variant_id": variant.variant_id,
            "variant_sha256": variant.variant_sha256,
            "added_geoms": report["added_geoms"],
            "added_bodies": report.get("added_bodies", []),
            "added_joints": report.get("added_joints", []),
            "bindings": report["bindings"],
            "parameter_source": (
                "frozen_c2_compression_only_zero_refit_on_d1_to_d2"
            ),
        }

    return mutate


def _model_mutator(parameters: dict[str, Any]) -> Any:
    def mutate(model: mujoco.MjModel) -> dict[str, Any]:
        pads: list[dict[str, Any]] = []
        disabled: list[str] = []
        for geom_id in range(model.ngeom):
            geom_name = _name(
                model, mujoco.mjtObj.mjOBJ_GEOM, geom_id
            )
            body_name = _name(
                model,
                mujoco.mjtObj.mjOBJ_BODY,
                int(model.geom_bodyid[geom_id]),
            )
            if "_rubber_tip_fixed_" in geom_name:
                model.geom_pos[geom_id, 2] += (
                    float(parameters["tip_coverage_offset_m"])
                    + float(parameters["tip_fixed_coverage_offset_m"])
                )
                model.geom_size[geom_id, 0] *= float(
                    parameters["tip_fixed_thickness_multiplier"]
                )
                model.geom_size[geom_id, 1] *= float(
                    parameters["tip_fixed_half_width_multiplier"]
                )
                model.geom_size[geom_id, 2] *= float(
                    parameters["tip_fixed_coverage_multiplier"]
                )
                pads.append(
                    {
                        "finger": "fixed",
                        "geom_id": geom_id,
                        "geom_name": geom_name,
                        "body_name": body_name,
                    }
                )
            elif "_rubber_tip_moving_" in geom_name:
                model.geom_pos[geom_id, 1] += (
                    float(parameters["tip_coverage_offset_m"])
                    + float(parameters["tip_moving_coverage_offset_m"])
                )
                model.geom_size[geom_id, 0] *= float(
                    parameters["tip_moving_thickness_multiplier"]
                )
                model.geom_size[geom_id, 2] *= float(
                    parameters["tip_moving_half_width_multiplier"]
                )
                model.geom_size[geom_id, 1] *= float(
                    parameters["tip_moving_coverage_multiplier"]
                )
                pads.append(
                    {
                        "finger": "moving",
                        "geom_id": geom_id,
                        "geom_name": geom_name,
                        "body_name": body_name,
                    }
                )
            elif (
                body_name in JAW_BODY_NAMES
                and (
                    int(model.geom_contype[geom_id])
                    or int(model.geom_conaffinity[geom_id])
                )
            ):
                disabled.append(geom_name)
                model.geom_contype[geom_id] = 0
                model.geom_conaffinity[geom_id] = 0
        _require(
            sorted(row["finger"] for row in pads) == ["fixed", "moving"],
            "exactly one compression-model pad per jaw did not compile",
        )
        for row in pads:
            geom_id = int(row["geom_id"])
            row.update(
                {
                    "position": model.geom_pos[geom_id]
                    .astype(float)
                    .tolist(),
                    "size": model.geom_size[geom_id]
                    .astype(float)
                    .tolist(),
                    "friction": model.geom_friction[geom_id]
                    .astype(float)
                    .tolist(),
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


def run_measured_state_compliance_once(
    contract_path: Path = CONTRACT_PATH,
    output_directory: Path = OUTPUT_DIRECTORY,
    *,
    root: Path = REPO_ROOT,
) -> dict[str, Any]:
    receipt_path = output_directory / "receipt.json"
    _require(not receipt_path.exists(), "OR39 one-run receipt already exists")
    contract = load_measured_state_compliance_contract(
        contract_path, root=root
    )
    predecessor = _bound_json(
        contract["sources"]["or38_receipt"],
        root=root,
        label="OR38 receipt",
    )
    source_path = _bound_path(
        contract["sources"]["c2_compression_only_contract"],
        root=root,
        label="C2 compression-only contract",
    )
    results: list[dict[str, Any]] = []
    traces: list[dict[str, Any]] = []
    for variant in contract["variants"]:
        parameters = _parameters(
            contract,
            compliance_enabled=bool(
                variant["normal_compliance_enabled"]
            ),
        )
        result, trace = _run_variant(
            contract=contract,
            variant=variant,
            root=root,
            spec_mutator=_spec_mutator(
                contract=contract,
                parameters=parameters,
                source_path=source_path,
            ),
            model_mutator=_model_mutator(parameters),
        )
        results.append(result)
        traces.append(trace)
    baseline, candidate = results
    candidate_gates = _candidate_gate_report(contract, candidate)
    full_pass = all(candidate_gates.values())
    early_names = {
        "contact_timing",
        "no_early_motion",
        "support_loss_timing",
        "upright_at_carry_start",
    }
    early_pass = all(
        value
        for name, value in candidate_gates.items()
        if name in early_names
    )
    compliance_compiled = bool(
        candidate["spec_mutation_report"]["added_joints"]
    )
    status = (
        "PASS_FULL_PHYSICS_DRIVEN_REPLAY"
        if full_pass
        else (
            "PARTIAL_PASSIVE_COMPLIANCE_ADVANCEMENT"
            if compliance_compiled
            and (
                early_pass
                or candidate["trace_summary"][
                    "tilt_at_sample_260_degrees"
                ]
                < baseline["trace_summary"][
                    "tilt_at_sample_260_degrees"
                ]
            )
            else "TERMINAL_NEGATIVE_PASSIVE_COMPLIANCE"
        )
    )

    output_directory.mkdir(parents=True, exist_ok=False)
    trace_bindings: list[dict[str, str]] = []
    for result, trace in zip(results, traces, strict=True):
        trace_path = output_directory / f"{result['variant_id']}_trace.json"
        atomic_write_json(trace_path, trace)
        result["trace_path"] = trace_path.name
        result["trace_sha256"] = _sha256(trace_path)
        trace_bindings.append(
            {
                "variant_id": result["variant_id"],
                "path": trace_path.name,
                "sha256": result["trace_sha256"],
            }
        )
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "experiment_id": contract["experiment_id"],
        "proof_class": contract["proof_class"],
        "status": status,
        "predecessor_artifact_sha256": predecessor["artifact_sha256"],
        "variants": results,
        "candidate_gate_report": candidate_gates,
        "early_causal_gates_pass": early_pass,
        "full_physics_driven_replay_pass": full_pass,
        "passive_compliance_compiled": compliance_compiled,
        "zero_refit_on_destination_episode": True,
        "canonical_actuator_force_and_timestep_preserved": True,
        "trace_bindings": trace_bindings,
        "object_pose_injection_used": False,
        "latch_attachment_grasp_mode_or_support_projection_used": False,
        "raw_measured_state_changed": False,
        "pawn_board_reset_or_solver_changed": False,
        "global_mapping_approved": False,
        "simulator_promoted": False,
        "transfer_claim": False,
        "authority": contract["authority"],
    }
    receipt["artifact_sha256"] = canonical_digest(receipt)
    atomic_write_json(receipt_path, receipt)
    return receipt


def main() -> int:
    run_measured_state_compliance_once()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
