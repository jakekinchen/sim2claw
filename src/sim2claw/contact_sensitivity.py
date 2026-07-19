"""Run the frozen rook-lift ACT evaluator over a contact-prior ensemble."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import torch

from .act_evaluator import evaluate_act
from .chess_task import load_task_contract, task_contract_sha256
from .contact_prior import load_contact_prior_contract, load_simulator_variant
from .paths import DEFAULT_OUTPUT_ROOT, DEFAULT_RUBBER_TIP_CONTACT_PRIOR


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def preflight_contact_sensitivity(
    checkpoint_path: Path,
    *,
    output_directory: Path,
    contract_path: Path = DEFAULT_RUBBER_TIP_CONTACT_PRIOR,
) -> dict[str, Any]:
    contract = load_contact_prior_contract(contract_path)
    task = load_task_contract()
    checkpoint_sha256 = _sha256_file(checkpoint_path)
    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    variants = [
        load_simulator_variant(variant_id, path=contract_path)
        for variant_id in contract["evaluation_order"]
    ]
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
        "accepted_checkpoint_hash_matches": (
            checkpoint_sha256 == contract["policy"]["accepted_checkpoint_sha256"]
        ),
        "variant_contract_frozen": bool(contract["frozen_before_evaluation"]),
        "evaluator_seed_matches": (
            task["held_out_split"]["seeds"]
            == contract["fixed_evaluation"]["held_out_seeds"]
        ),
    }
    compatible = all(checks.values())
    receipt = {
        "schema_version": "sim2claw.contact_sensitivity_preflight.v1",
        "status": "compatible" if compatible else "fail_closed_incompatible",
        "proof_class": "simulation_contact_prior_sensitivity_preflight",
        "task_id": task["task_id"],
        "task_contract_sha256": task_contract_sha256(),
        "evaluator_contract_sha256": _canonical_sha256(task["evaluator"]),
        "checkpoint": str(checkpoint_path),
        "checkpoint_sha256": checkpoint_sha256,
        "contact_prior_contract": str(contract_path),
        "contact_prior_contract_sha256": variants[0].contract_sha256,
        "variant_identities": {
            variant.variant_id: variant.variant_sha256 for variant in variants
        },
        "evaluation_order": contract["evaluation_order"],
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
        raise ValueError("ACT checkpoint or frozen sensitivity boundary is incompatible")
    return receipt


def summarize_contact_sensitivity(
    receipts: list[dict[str, Any]],
) -> dict[str, Any]:
    if not receipts:
        raise ValueError("contact sensitivity summary requires evaluator receipts")
    rows: list[dict[str, Any]] = []
    for receipt in receipts:
        episode = receipt["episode"]
        rows.append(
            {
                "variant_id": receipt["simulator_variant"]["variant_id"],
                "variant_sha256": receipt["simulator_variant"]["variant_sha256"],
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
    return {
        "rows": rows,
        "sensitivity": {
            "categorical_success_changed": len(successes) > 1,
            "policy_actions_changed_with_contact_state": len(action_hashes) > 1,
            "maximum_piece_rise_range_m": max(maximum_rises) - min(maximum_rises),
            "final_piece_rise_range_m": max(final_rises) - min(final_rises),
            "all_variants_finite": all(row["stability"]["finite_state"] for row in rows),
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
    preflight = preflight_contact_sensitivity(
        checkpoint_path,
        output_directory=output,
        contract_path=contract_path,
    )
    contract = load_contact_prior_contract(contract_path)
    receipts: list[dict[str, Any]] = []
    for variant_id in contract["evaluation_order"]:
        variant = load_simulator_variant(variant_id, path=contract_path)
        receipts.append(
            evaluate_act(
                checkpoint_path,
                output_directory=output / variant_id,
                render_video=render_video,
                simulator_variant=variant,
            )
        )
    summarized = summarize_contact_sensitivity(receipts)
    report = {
        "schema_version": "sim2claw.rubber_tip_contact_sensitivity_receipt.v1",
        "analysis_id": contract["analysis_id"],
        "proof_class": contract["proof_class"],
        "benchmark_label": "narrow simulated rook-lift contact-sensitivity benchmark",
        "policy_compatible": True,
        "preflight_receipt": str(output / "preflight_receipt.json"),
        "preflight": preflight,
        **summarized,
        "interpretation": {
            "physical_calibration": False,
            "sim_to_real_error_measured": False,
            "physical_rubber_bands_validated": False,
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
