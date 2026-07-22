"""Deterministic structural-discrimination acquisition and plan receipts."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from ..learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .contracts import REPO_ROOT, SailContractError, seal_contract, verify_source_binding
from .importers import load_json_object


CONFIG_SCHEMA = "sim2claw.sail_acquisition_campaign.v1"
RECEIPT_SCHEMA = "sim2claw.sail_acquisition_compile_receipt.v1"


class AcquisitionError(SailContractError):
    """Acquisition scoring became opaque, non-deterministic, or executable beyond authority."""


def _weighted_score(values: Mapping[str, float], weights: Mapping[str, float]) -> float:
    return float(sum(float(values[name]) * float(weight) for name, weight in weights.items()))


def rank_acquisition(config: Mapping[str, Any]) -> dict[str, Any]:
    candidates = config.get("candidates") or []
    ids = [str(row.get("candidate_id", "")) for row in candidates]
    if not ids or any(not value for value in ids) or len(ids) != len(set(ids)):
        raise AcquisitionError("acquisition candidate identities are invalid")
    hypotheses = [str(value) for value in config["competing_hypotheses"]]
    if len(hypotheses) < 2:
        raise AcquisitionError("acquisition needs competing structures")
    rows: list[dict[str, Any]] = []
    plans: list[dict[str, Any]] = []
    for candidate in sorted(candidates, key=lambda row: row["candidate_id"]):
        signatures = {name: float(candidate["signatures"][name]) for name in hypotheses}
        separation = min(max(signatures.values()) - min(signatures.values()), 1.0)
        structural_components = {
            "structure_entropy_reduction": separation,
            "compensation_debt_reduction": float(candidate["compensation_debt_reduction"]),
            "gate_relevance": float(candidate["gate_relevance"]),
            "cost": float(candidate["cost"]),
            "risk": float(candidate["risk"]),
        }
        parameter_components = {
            "parameter_information_gain": float(candidate["parameter_information_gain"]),
            "cost": float(candidate["cost"]),
            "risk": float(candidate["risk"]),
        }
        available = candidate["availability"] == "available_simulator"
        row = {
            "candidate_id": candidate["candidate_id"],
            "availability": candidate["availability"],
            "available_for_execution": available,
            "execution_status": "ranked_plan_not_executed",
            "predicted_signatures": signatures,
            "structural_components": structural_components,
            "structural_score": _weighted_score(structural_components, config["structural_weights"]),
            "parameter_components": parameter_components,
            "parameter_refinement_score": _weighted_score(parameter_components, config["parameter_weights"]),
            "scores_collapsed": False,
            "observed_information_gain": None,
        }
        rows.append(row)
        plans.append(
            seal_contract(
                {
                    "schema_version": "sim2claw.intervention.v1",
                    "intervention_id": str(candidate["candidate_id"]),
                    "primary_question": "Which of timing delay or load compliance explains the retained residual structure?",
                    "competing_hypotheses": hypotheses,
                    "allowed_mutations": list(candidate["allowed_mutations"]),
                    "frozen_action": copy.deepcopy(config["frozen_action"]),
                    "expected_signatures": {name: {"normalized_response": value} for name, value in signatures.items()},
                    "predicted_information_gain": separation,
                    "estimated_cost": float(candidate["cost"]),
                    "required_observables": list(candidate["required_observables"]),
                    "evaluation_gates": [{"id": "structure_discrimination", "required": True}],
                    "regression_gates": [{"id": "action_identity", "required": True}],
                    "budget": {"maximum_trials": int(candidate["maximum_trials"]), "maximum_wall_seconds": 300 if available else 0, "maximum_provider_calls": 0, "maximum_cost_usd": 0.0},
                    "stop_conditions": ["budget_exhausted", "frozen_structure_threshold_crossed"],
                    "proof_class": candidate["proof_class"],
                    "authority": {"physical_capture": False, "robot_motion": False, "agent_can_promote": False},
                }
            )
        )
    available_rows = [row for row in rows if row["available_for_execution"]]
    structural_ranking = sorted(available_rows, key=lambda row: (-row["structural_score"], row["candidate_id"]))
    parameter_ranking = sorted(available_rows, key=lambda row: (-row["parameter_refinement_score"], row["candidate_id"]))
    for index, row in enumerate(structural_ranking, start=1):
        row["structural_rank"] = index
    for index, row in enumerate(parameter_ranking, start=1):
        row["parameter_rank"] = index
    winner = structural_ranking[0]
    coordinate = next(row for row in rows if row["candidate_id"] == "sim_common_mode_rms")
    residual = max(available_rows, key=lambda row: (row["structural_components"]["compensation_debt_reduction"], row["candidate_id"]))
    uncertainty = max(available_rows, key=lambda row: (row["parameter_components"]["parameter_information_gain"], row["candidate_id"]))
    random_expected = float(np.mean([row["structural_score"] for row in available_rows]))
    baselines = {
        "random_expected": {"score": random_expected, "regret": winner["structural_score"] - random_expected},
        "coordinate_order": {"candidate_id": coordinate["candidate_id"], "score": coordinate["structural_score"], "regret": winner["structural_score"] - coordinate["structural_score"]},
        "residual_magnitude": {"candidate_id": residual["candidate_id"], "score": residual["structural_score"], "regret": winner["structural_score"] - residual["structural_score"]},
        "parameter_uncertainty": {"candidate_id": uncertainty["candidate_id"], "score": uncertainty["structural_score"], "regret": winner["structural_score"] - uncertainty["structural_score"]},
    }
    passed = (
        winner["candidate_id"] == "sim_load_frequency_discriminator"
        and winner["structural_components"]["structure_entropy_reduction"] > coordinate["structural_components"]["structure_entropy_reduction"]
        and all(row["regret"] > 0.0 for row in baselines.values())
        and all(not row["available_for_execution"] for row in rows if row["availability"] == "unavailable_hardware_plan")
    )
    if not passed:
        raise AcquisitionError("GOLD-12 acquisition ranking failed")
    unsigned = {
        "schema_version": "sim2claw.sail_acquisition_ranking.v1",
        "campaign_id": config["campaign_id"],
        "rows": rows,
        "structural_ranking": [row["candidate_id"] for row in structural_ranking],
        "parameter_refinement_ranking": [row["candidate_id"] for row in parameter_ranking],
        "selected_simulator_probe": winner["candidate_id"],
        "baselines": baselines,
        "golden_cases": {"GOLD-12": True},
        "hardware_plan_count": sum(row["availability"] == "unavailable_hardware_plan" for row in rows),
        "hardware_probe_executed": False,
        "simulator_probe_executed": False,
        "source_action": copy.deepcopy(config["frozen_action"]),
        "source_action_bytes_unchanged": True,
        "scores_collapsed": False,
        "plans_digest": canonical_digest(plans),
    }
    return {**unsigned, "ranking_digest": canonical_digest(unsigned), "intervention_plans": plans}


def verify_acquisition_receipt(receipt: Mapping[str, Any], *, output_root: Path, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(receipt))
    if normalized.get("schema_version") != RECEIPT_SCHEMA:
        raise AcquisitionError("unexpected acquisition receipt schema")
    observed = normalized.pop("receipt_digest", None)
    if observed != canonical_digest(normalized):
        raise AcquisitionError("acquisition receipt digest mismatch")
    authority = normalized.get("authority")
    if not isinstance(authority, dict) or not authority or any(authority.values()):
        raise AcquisitionError("acquisition receipt widened authority")
    config_path = repo_root / normalized["config"]["path"]
    if not config_path.is_file() or sha256_file(config_path) != normalized["config"]["sha256"]:
        raise AcquisitionError("acquisition config changed")
    config = load_json_object(config_path, label="acquisition receipt config")
    for name, expected in normalized["source_sha256"].items():
        binding = config["source_bindings"].get(name)
        if not isinstance(binding, dict) or binding.get("sha256") != expected:
            raise AcquisitionError(f"acquisition source binding changed: {name}")
        verify_source_binding(binding, repo_root=repo_root)
    for relative_path, expected in normalized["compiler_sha256"].items():
        if sha256_file(repo_root / relative_path) != expected:
            raise AcquisitionError("acquisition compiler changed")
    for name, binding in normalized["outputs"].items():
        path = output_root / binding["path"]
        if not path.is_file() or sha256_file(path) != binding["sha256"]:
            raise AcquisitionError(f"acquisition output changed: {name}")
    return {**normalized, "receipt_digest": str(observed)}


def compile_acquisition(config_path: Path, *, output_root: Path, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    resolved = config_path if config_path.is_absolute() else repo_root / config_path
    config = load_json_object(resolved, label="SAIL acquisition config")
    if config.get("schema_version") != CONFIG_SCHEMA:
        raise AcquisitionError("unexpected SAIL acquisition config schema")
    if not isinstance(config.get("authority"), dict) or any(config["authority"].values()):
        raise AcquisitionError("acquisition config widened authority")
    sources = {name: verify_source_binding(binding, repo_root=repo_root) for name, binding in config["source_bindings"].items()}
    evidence = load_json_object(sources["frozen_action_evidence"], label="acquisition action evidence")
    if evidence.get("action", {}).get("sha256") != config["frozen_action"]["sha256"] or evidence["action"]["shape"] != config["frozen_action"]["shape"]:
        raise AcquisitionError("acquisition frozen action identity changed")
    result = rank_acquisition(config)
    plans = result.pop("intervention_plans")
    output_root.mkdir(parents=True, exist_ok=True)
    ranking_path = output_root / "acquisition_ranking.json"
    plans_path = output_root / "intervention_plans.json"
    atomic_write_json(ranking_path, result)
    atomic_write_json(plans_path, {"schema_version": "sim2claw.sail_intervention_plan_set.v1", "plans": plans, "all_unexecuted": True, "hardware_execution": False})
    outputs = {"acquisition_ranking": {"path": ranking_path.name, "sha256": sha256_file(ranking_path)}, "intervention_plans": {"path": plans_path.name, "sha256": sha256_file(plans_path)}}
    code_path = "src/sim2claw/sail/acquisition.py"
    unsigned_receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "campaign_id": config["campaign_id"],
        "generated_at": config["generated_at"],
        "config": {"path": resolved.resolve().relative_to(repo_root.resolve()).as_posix(), "sha256": sha256_file(resolved)},
        "compiler_sha256": {code_path: sha256_file(repo_root / code_path)},
        "source_sha256": {name: binding["sha256"] for name, binding in sorted(config["source_bindings"].items())},
        "outputs": outputs,
        "golden_cases": result["golden_cases"],
        "counts": {"candidate_count": len(result["rows"]), "hardware_plan_count": result["hardware_plan_count"], "executed_probe_count": 0},
        "selected_simulator_probe": result["selected_simulator_probe"],
        "source_action_bytes_unchanged": True,
        "regeneration_command": "uv run sim2claw sail-compile-acquisition --config configs/sail/acquisition_v1.json --output outputs/sail/retired-bg-v1/acquisition",
        "authority": copy.deepcopy(config["authority"]),
        "claim_boundary": "Acquisition scores are predictions and plans. No simulator, hardware, provider, training, or policy action was executed or promoted.",
    }
    receipt = {**unsigned_receipt, "receipt_digest": canonical_digest(unsigned_receipt)}
    receipt_path = output_root / "receipt.json"
    atomic_write_json(receipt_path, receipt)
    verify_acquisition_receipt(receipt, output_root=output_root, repo_root=repo_root)
    return {"schema_version": "sim2claw.sail_acquisition_compile_result.v1", "campaign_id": config["campaign_id"], "status": "compiled", "golden_cases": result["golden_cases"], "counts": receipt["counts"], "selected_simulator_probe": result["selected_simulator_probe"], "receipt_sha256": sha256_file(receipt_path), "receipt_digest": receipt["receipt_digest"], "output_root": str(output_root), "training_admitted": False, "physical_authority": False}


__all__ = ["AcquisitionError", "compile_acquisition", "rank_acquisition", "verify_acquisition_receipt"]
