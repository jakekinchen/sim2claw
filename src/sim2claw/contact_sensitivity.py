"""Run the frozen rook-lift ACT evaluator over a contact-prior ensemble."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import torch

from .act_evaluator import evaluate_act
from .act_model import (
    ACTCheckpointSnapshot,
    load_act_checkpoint_snapshot,
    read_act_checkpoint_snapshot,
)
from .chess_task import ChessRookLiftEnv, load_task_contract, task_contract_sha256
from .contact_prior import (
    ContactPriorSnapshot,
    load_simulator_variant,
    read_contact_prior_snapshot,
)
from .paths import DEFAULT_OUTPUT_ROOT, DEFAULT_RUBBER_TIP_CONTACT_PRIOR


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _nominal_compiled_identity_proof(
    task: dict[str, Any],
    contract_snapshot: ContactPriorSnapshot,
) -> dict[str, Any]:
    seed = int(task["held_out_split"]["seeds"][0])
    raw_offset = task["held_out_split"]["piece_planar_offsets_m"][0]
    offset = (float(raw_offset[0]), float(raw_offset[1]))
    baseline = ChessRookLiftEnv(task, seed=seed, piece_offset_xy_m=offset)
    nominal = ChessRookLiftEnv(
        task,
        seed=seed,
        piece_offset_xy_m=offset,
        simulator_variant=load_simulator_variant(
            "nominal_uncalibrated", contract_snapshot=contract_snapshot
        ),
    )
    baseline_identity = baseline.compiled_variant_identity
    nominal_identity = nominal.compiled_variant_identity
    return {
        "legacy_implicit_nominal_compiled_dynamics_sha256": baseline_identity[
            "compiled_dynamics_sha256"
        ],
        "explicit_nominal_compiled_dynamics_sha256": nominal_identity[
            "compiled_dynamics_sha256"
        ],
        "legacy_implicit_nominal_inertial_control_sha256": baseline_identity[
            "compiled_inertial_control_sha256"
        ],
        "explicit_nominal_inertial_control_sha256": nominal_identity[
            "compiled_inertial_control_sha256"
        ],
        "legacy_implicit_nominal_total_body_mass_kg": baseline_identity[
            "compiled_total_body_mass_kg"
        ],
        "explicit_nominal_total_body_mass_kg": nominal_identity[
            "compiled_total_body_mass_kg"
        ],
        "compiled_dynamics_bitwise_identical": (
            baseline_identity["compiled_dynamics_sha256"]
            == nominal_identity["compiled_dynamics_sha256"]
        ),
        "inertial_control_bitwise_identical": (
            baseline_identity["compiled_inertial_control_sha256"]
            == nominal_identity["compiled_inertial_control_sha256"]
        ),
        "total_body_mass_bitwise_identical": bool(
            np.asarray(
                baseline_identity["compiled_total_body_mass_kg"], dtype=np.float64
            ).tobytes()
            == np.asarray(
                nominal_identity["compiled_total_body_mass_kg"], dtype=np.float64
            ).tobytes()
        ),
    }


def preflight_contact_sensitivity(
    checkpoint_snapshot: ACTCheckpointSnapshot,
    *,
    contract_snapshot: ContactPriorSnapshot,
    output_directory: Path,
) -> dict[str, Any]:
    contract = contract_snapshot.payload()
    task = load_task_contract()
    _, _, checkpoint = load_act_checkpoint_snapshot(
        checkpoint_snapshot, device=torch.device("cpu")
    )
    variants = [
        load_simulator_variant(variant_id, contract_snapshot=contract_snapshot)
        for variant_id in contract["evaluation_order"]
    ]
    nominal_identity = _nominal_compiled_identity_proof(task, contract_snapshot)
    checks = {
        "task_id_matches": contract["task_id"] == task["task_id"] == checkpoint.get("task_id"),
        "task_contract_matches": (
            contract["task_contract_sha256"]
            == task_contract_sha256()
            == checkpoint.get("task_contract_sha256")
        ),
        "checkpoint_schema_matches": (
            checkpoint.get("schema_version")
            == contract["policy"]["checkpoint_schema_version"]
        ),
        "accepted_checkpoint_snapshot_hash_matches": (
            checkpoint_snapshot.sha256
            == contract["policy"]["accepted_checkpoint_sha256"]
        ),
        "variant_contract_frozen": bool(contract["frozen_before_evaluation"]),
        "variant_contract_digest_matches_reviewed": (
            contract_snapshot.sha256
            == read_contact_prior_snapshot(contract_snapshot.source_path).sha256
        ),
        "evaluator_seed_matches": (
            task["held_out_split"]["seeds"]
            == contract["fixed_evaluation"]["held_out_seeds"]
        ),
        "nominal_compiled_dynamics_bitwise_identical": nominal_identity[
            "compiled_dynamics_bitwise_identical"
        ],
        "nominal_inertial_control_bitwise_identical": nominal_identity[
            "inertial_control_bitwise_identical"
        ],
        "nominal_total_body_mass_bitwise_identical": nominal_identity[
            "total_body_mass_bitwise_identical"
        ],
    }
    compatible = all(checks.values())
    receipt = {
        "schema_version": "sim2claw.contact_sensitivity_preflight.v2",
        "status": "compatible" if compatible else "fail_closed_incompatible",
        "proof_class": "simulation_contact_prior_sensitivity_preflight",
        "task_id": task["task_id"],
        "task_contract_sha256": task_contract_sha256(),
        "evaluator_contract_sha256": _canonical_sha256(task["evaluator"]),
        "checkpoint_source_path_informational": str(checkpoint_snapshot.source_path),
        "checkpoint_snapshot_sha256": checkpoint_snapshot.sha256,
        "checkpoint_snapshot_bytes": len(checkpoint_snapshot.data),
        "checkpoint_snapshot_immutable": True,
        "checkpoint_hash_verified_before_deserialization": True,
        "contact_prior_contract": str(contract_snapshot.source_path),
        "contact_prior_contract_sha256": contract_snapshot.sha256,
        "variant_identities": {
            variant.variant_id: variant.variant_sha256 for variant in variants
        },
        "evaluation_order": contract["evaluation_order"],
        "nominal_compiled_identity_proof": nominal_identity,
        "checks": checks,
        "physical_authority": False,
        "camera_accessed": False,
        "serial_accessed": False,
        "gateway_accessed": False,
        "training_performed": False,
        "external_compute_started": False,
        "brev_compute_started": False,
    }
    _write_json(output_directory / "preflight_receipt.json", receipt)
    if not compatible:
        raise ValueError("ACT snapshot or frozen sensitivity boundary is incompatible")
    return receipt


def summarize_contact_sensitivity(
    receipts: list[dict[str, Any]],
) -> dict[str, Any]:
    if not receipts:
        raise ValueError("contact sensitivity summary requires evaluator receipts")
    rows: list[dict[str, Any]] = []
    for receipt in receipts:
        episode = receipt["episode"]
        compiled = receipt["simulator_variant"]["compiled_identity"]
        rows.append(
            {
                "variant_id": receipt["simulator_variant"]["variant_id"],
                "variant_sha256": receipt["simulator_variant"]["variant_sha256"],
                "checkpoint_snapshot_sha256": receipt["policy"][
                    "checkpoint_snapshot_sha256"
                ],
                "success": bool(receipt["success"]),
                "terminal_outcome": receipt["terminal_outcome"],
                "failed_gates": receipt["failed_gates"],
                "maximum_piece_rise_m": float(episode["maximum_piece_rise_m"]),
                "final_piece_rise_m": float(episode["final_piece_rise_m"]),
                "longest_contact_control_steps": int(episode["longest_contact_control_steps"]),
                "final_contact_fraction": float(episode["final_contact_fraction"]),
                "contact_timing": episode["contact_timing"],
                "action_trace_sha256": receipt["artifacts"]["action_trace_sha256"],
                "state_trace_sha256": receipt["artifacts"]["state_trace_sha256"],
                "compiled_contact_identity": compiled,
                "stability": receipt["stability"],
            }
        )
    nominal = rows[0]
    for row in rows:
        row["action_trace_matches_nominal"] = (
            row["action_trace_sha256"] == nominal["action_trace_sha256"]
        )
    maximum_rises = [row["maximum_piece_rise_m"] for row in rows]
    final_rises = [row["final_piece_rise_m"] for row in rows]
    successes = {row["success"] for row in rows}
    action_hashes = {row["action_trace_sha256"] for row in rows}
    snapshot_hashes = {row["checkpoint_snapshot_sha256"] for row in rows}
    inertial_hashes = {
        row["compiled_contact_identity"]["compiled_inertial_control_sha256"]
        for row in rows
    }
    total_mass_bytes = {
        np.asarray(
            row["compiled_contact_identity"]["compiled_total_body_mass_kg"],
            dtype=np.float64,
        ).tobytes()
        for row in rows
    }
    return {
        "rows": rows,
        "sensitivity": {
            "categorical_success_changed": len(successes) > 1,
            "policy_actions_changed_with_contact_state": len(action_hashes) > 1,
            "maximum_piece_rise_range_m": max(maximum_rises) - min(maximum_rises),
            "final_piece_rise_range_m": max(final_rises) - min(final_rises),
            "all_variants_finite": all(row["stability"]["finite_state"] for row in rows),
        },
        "identity_checks": {
            "same_checkpoint_snapshot_all_variants": len(snapshot_hashes) == 1,
            "inertial_control_bitwise_identical_all_variants": len(inertial_hashes) == 1,
            "total_body_mass_bitwise_identical_all_variants": len(total_mass_bytes) == 1,
            "mass_effect_mode": "excluded_as_negligible_unmeasured_owner_assessment",
            "modeled_added_mass_kg": 0.0,
        },
    }


def run_contact_sensitivity(
    checkpoint_path: Path,
    *,
    output_directory: Path | None = None,
    contract_path: Path = DEFAULT_RUBBER_TIP_CONTACT_PRIOR,
    render_video: bool = False,
) -> dict[str, Any]:
    output = output_directory or (
        DEFAULT_OUTPUT_ROOT / "act" / "chess_rook_lift_v1" / "contact_sensitivity_v1"
    )
    contract_snapshot = read_contact_prior_snapshot(contract_path)
    contract = contract_snapshot.payload()
    checkpoint_snapshot = read_act_checkpoint_snapshot(
        checkpoint_path,
        expected_sha256=contract["policy"]["accepted_checkpoint_sha256"],
    )
    preflight = preflight_contact_sensitivity(
        checkpoint_snapshot,
        contract_snapshot=contract_snapshot,
        output_directory=output,
    )
    receipts: list[dict[str, Any]] = []
    for variant_id in contract["evaluation_order"]:
        variant = load_simulator_variant(
            variant_id, contract_snapshot=contract_snapshot
        )
        receipts.append(
            evaluate_act(
                checkpoint_snapshot,
                output_directory=output / variant_id,
                render_video=render_video,
                simulator_variant=variant,
            )
        )
    summarized = summarize_contact_sensitivity(receipts)
    if not all(
        summarized["identity_checks"][field]
        for field in (
            "same_checkpoint_snapshot_all_variants",
            "inertial_control_bitwise_identical_all_variants",
            "total_body_mass_bitwise_identical_all_variants",
        )
    ):
        raise RuntimeError("checkpoint or inertial/control identity drifted across variants")
    report = {
        "schema_version": "sim2claw.rubber_tip_contact_sensitivity_receipt.v2",
        "analysis_id": contract["analysis_id"],
        "proof_class": contract["proof_class"],
        "benchmark_label": "narrow simulated rook-lift contact-sensitivity benchmark",
        "policy_compatible": True,
        "checkpoint_snapshot_sha256": checkpoint_snapshot.sha256,
        "checkpoint_snapshot_bytes": len(checkpoint_snapshot.data),
        "preflight_receipt": str(output / "preflight_receipt.json"),
        "preflight": preflight,
        **summarized,
        "interpretation": {
            "physical_calibration": False,
            "sim_to_real_error_measured": False,
            "physical_rubber_bands_validated": False,
            "rubber_mass_modeled": False,
            "physical_rubber_mass_acknowledged_nonzero_unmeasured": True,
            "pawn_skill_evaluated": False,
            "language_generalization_evaluated": False,
            "composability_evaluated": False,
            "training_performed": False,
        },
        "limitations": contract["limitations"],
    }
    _write_json(output / "benchmark_receipt.json", report)
    report["receipt"] = str(output / "benchmark_receipt.json")
    return report
