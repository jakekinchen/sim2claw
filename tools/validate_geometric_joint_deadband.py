#!/usr/bin/env python3
"""Score a frozen geometric deadband fit on one exact held-out trace."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from sim2claw.actuator_external_validation import _workcell_candidate
from sim2claw.learning_factory_artifacts import (
    atomic_write_json,
    canonical_digest,
    sha256_file,
)
from sim2claw.paths import REPO_ROOT
from sim2claw.pawn_bg_servo_load_bias import load_servo_load_bias_contract
from sim2claw.pawn_bg_timing_ablation import (
    _episode_metrics,
    _mapped_episode,
    _strip_arrays,
    _timestamp_aligned_zoh,
)
from tools.evaluate_geometric_micro_actuator_response import _stage_payload


CONTRACT_PATH = (
    REPO_ROOT
    / "configs"
    / "evaluations"
    / "geometric_joint_deadband_holdout_v1.json"
)
SCHEMA = "sim2claw.geometric_joint_deadband_holdout.v1"
RECEIPT_SCHEMA = "sim2claw.geometric_joint_deadband_holdout_receipt.v1"


class GeometricJointDeadbandHoldoutError(RuntimeError):
    """The frozen fit, held-out trace, or evidence boundary changed."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GeometricJointDeadbandHoldoutError(message)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GeometricJointDeadbandHoldoutError(
            f"cannot read JSON {path}: {error}"
        ) from error
    _require(isinstance(value, dict), f"JSON source is not an object: {path}")
    return value


def _bound_path(binding: Mapping[str, Any]) -> Path:
    relative = Path(str(binding.get("path") or ""))
    _require(
        not relative.is_absolute() and ".." not in relative.parts,
        "source path escaped the repository",
    )
    path = REPO_ROOT / relative
    _require(
        path.is_file() and sha256_file(path) == binding.get("sha256"),
        f"hash-bound source changed: {relative}",
    )
    return path


def _relative_improvement(candidate: float, baseline: float) -> float:
    _require(baseline > 0.0, "baseline metric must be positive")
    return float((baseline - candidate) / baseline)


def _tricam_gates(execution: Mapping[str, Any]) -> dict[str, bool]:
    finished = execution.get("camera_finished") or {}
    return {
        "c922_action_interval_enclosed": bool(
            ((finished.get("overhead") or {}).get(
                "action_interval_enclosed_by_callback_frames"
            ))
        ),
        "d405_action_interval_enclosed": bool(
            ((finished.get("wrist") or {}).get(
                "action_interval_enclosed_by_callback_frames"
            ))
        ),
        "pi_action_interval_enclosed": bool(
            ((finished.get("pi") or {}).get("action_interval_enclosed"))
        ),
    }


def validate(
    *,
    contract_path: Path = CONTRACT_PATH,
    output_path: Path,
) -> dict[str, Any]:
    contract_path = contract_path.resolve()
    contract = _load_json(contract_path)
    _require(contract.get("schema_version") == SCHEMA, "contract schema changed")
    _require(
        contract.get("status")
        == "prospective_heldout_evaluation_of_previously_frozen_fit",
        "holdout status changed",
    )
    _require(
        not any((contract.get("authority") or {}).values()),
        "holdout authority widened",
    )
    _require(
        all((contract.get("action_invariance") or {}).values()),
        "action invariance is not fail closed",
    )

    sources = contract["sources"]
    fit_contract_path = _bound_path(sources["fit_contract"])
    fit_contract = _load_json(fit_contract_path)
    fit_receipt_path = _bound_path(sources["fit_receipt"])
    fit_receipt = _load_json(fit_receipt_path)
    digest_payload = dict(fit_receipt)
    observed_digest = digest_payload.pop("receipt_digest", None)
    _require(
        observed_digest
        == sources["fit_receipt"]["receipt_digest"]
        == canonical_digest(digest_payload),
        "fit receipt digest changed",
    )
    expected_fit = contract["expected_fit"]
    _require(
        fit_receipt.get("contract_sha256") == sha256_file(fit_contract_path)
        and fit_receipt.get("selected_variant")
        == expected_fit["selected_variant"]
        and fit_receipt.get("selected_deadband_degrees")
        == expected_fit["selected_deadband_degrees"]
        and fit_receipt.get("parameters_promoted")
        is expected_fit["parameters_promoted"],
        "frozen fit selection changed",
    )

    selection_path = _bound_path(fit_contract["sources"]["selection_receipt"])
    selection = _load_json(selection_path)
    selection_digest_payload = dict(selection)
    selection_digest = selection_digest_payload.pop("receipt_digest", None)
    _require(
        selection_digest
        == fit_contract["sources"]["selection_receipt"]["receipt_digest"]
        == canonical_digest(selection_digest_payload),
        "selection receipt digest changed",
    )
    mechanism_path = _bound_path(fit_contract["sources"]["mechanism_contract"])
    mechanism = load_servo_load_bias_contract(mechanism_path)
    workcell = _workcell_candidate(selection)

    packet = _load_json(_bound_path(sources["packet"]))
    heldout = sources["heldout_stage"]
    episode, loaded = _stage_payload(heldout, packet)
    mapped = _mapped_episode(loaded["payload"], workcell)
    execution = _load_json(
        _bound_path(
            {
                "path": heldout["execution_receipt_path"],
                "sha256": heldout["execution_receipt_sha256"],
            }
        )
    )

    variants = {
        "rigid": {},
        "prior_lift_elbow_deadband": contract["baseline_deadband_degrees"],
        "selected_frozen_fit": expected_fit["selected_deadband_degrees"],
    }
    scored: dict[str, Any] = {}
    for name, deadband in variants.items():
        states, schedule = _timestamp_aligned_zoh(
            mapped,
            workcell,
            settle_steps=int(mechanism["candidate_grid"]["initial_settle_steps"]),
            delay_seconds=float(
                mechanism["source"]["required_application_delay_seconds"]
            ),
            servo_deadband_degrees={
                key: float(value) for key, value in deadband.items()
            },
        )
        scored[name] = {
            "deadband_degrees": deadband,
            "schedule_sha256": schedule["sha256"],
            "metrics": _strip_arrays(
                _episode_metrics(mapped, states, workcell, mechanism)
            ),
        }

    prior = scored["prior_lift_elbow_deadband"]["metrics"]
    selected = scored["selected_frozen_fit"]["metrics"]
    comparisons = {
        "selected_vs_prior": {
            "joint_rms_relative_improvement": _relative_improvement(
                selected["overall_joint_rms_degrees"],
                prior["overall_joint_rms_degrees"],
            ),
            "ee_rms_relative_improvement": _relative_improvement(
                selected["ee_rms_m"], prior["ee_rms_m"]
            ),
        }
    }
    return_error = {
        name: abs(float(execution["final_residual_degrees"][index]))
        for name, index in (
            ("shoulder_lift", 1),
            ("elbow_flex", 2),
            ("wrist_flex", 3),
        )
    }
    tricam = _tricam_gates(execution)
    limits = contract["gates"]["maximum_return_error_degrees"]
    gates = {
        "exact_action_invariance": True,
        "all_three_camera_intervals_enclose_action": all(tricam.values()),
        "return_error_within_limits": all(
            return_error[name] <= float(limits[name]) for name in return_error
        ),
        "selected_joint_rms_improves_over_prior": (
            comparisons["selected_vs_prior"]["joint_rms_relative_improvement"] > 0.0
        ),
        "selected_ee_rms_improves_over_prior": (
            comparisons["selected_vs_prior"]["ee_rms_relative_improvement"] > 0.0
        ),
    }
    passed = all(gates.values())
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "evaluation_id": contract["evaluation_id"],
        "proof_class": contract["proof_class"],
        "contract_path": str(contract_path),
        "contract_sha256": sha256_file(contract_path),
        "implementation_path": str(Path(__file__).resolve()),
        "implementation_sha256": sha256_file(Path(__file__).resolve()),
        "fit_contract_path": str(fit_contract_path),
        "fit_contract_sha256": sha256_file(fit_contract_path),
        "fit_receipt_path": str(fit_receipt_path),
        "fit_receipt_sha256": sha256_file(fit_receipt_path),
        "heldout_source": loaded["source"],
        "mapped_action_receipt": mapped["action_receipt"],
        "variants": scored,
        "comparisons": comparisons,
        "return_error_degrees": return_error,
        "tricam_action_enclosure": tricam,
        "gates": gates,
        "heldout_passed": passed,
        "verdict": (
            "symmetric_deadband_heldout_passed"
            if passed
            else "symmetric_deadband_rejected_direction_conditioned_play_required"
        ),
        "parameter_fitting_performed": False,
        "parameters_promoted": False,
        "action_correction_performed": False,
        "pawn_contact_admitted": False,
        "authority": contract["authority"],
    }
    receipt["receipt_digest"] = canonical_digest(receipt)
    atomic_write_json(output_path.resolve(), receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            validate(contract_path=args.contract, output_path=args.output),
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
