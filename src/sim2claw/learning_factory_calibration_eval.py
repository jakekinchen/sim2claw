"""Independent CPU/fp32 evaluator for a system-identification candidate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .recorded_replay import load_sysid_config
from .system_identification import (
    evaluate_episode_losses,
    held_out_improvement_gate,
    load_manifest_episodes,
    load_split_manifest,
)


def evaluate_calibration_candidate(
    *,
    split_manifest_path: Path,
    config_path: Path,
    fit_receipt_path: Path,
) -> dict[str, Any]:
    """Recompute baseline/candidate held-out losses outside the fit runner."""

    split_manifest_path = split_manifest_path.resolve()
    config_path = config_path.resolve()
    fit_receipt_path = fit_receipt_path.resolve()
    config = load_sysid_config(config_path)
    manifest = load_split_manifest(split_manifest_path, config=config)
    episodes = load_manifest_episodes(manifest, config)
    fit = json.loads(fit_receipt_path.read_text(encoding="utf-8"))
    if fit.get("schema_version") != "sim2claw.sysid_fit_receipt.v1":
        raise ValueError("unsupported system-identification fit receipt")
    if fit.get("split", {}).get("sha256") != sha256_file(split_manifest_path):
        raise ValueError("fit receipt does not bind the supplied split manifest")
    if fit.get("config", {}).get("sha256") != sha256_file(config_path):
        raise ValueError("fit receipt does not bind the supplied sysid config")
    baseline_parameters = fit.get("baseline_parameters")
    candidate_parameters = fit.get("candidate_parameters")
    if not isinstance(baseline_parameters, dict) or not isinstance(
        candidate_parameters, dict
    ):
        raise ValueError("fit receipt parameter sets are incomplete")
    baseline = evaluate_episode_losses(
        episodes["held_out"],
        config,
        baseline_parameters,
        model_base_directory=config_path.parent,
    )
    candidate = evaluate_episode_losses(
        episodes["held_out"],
        config,
        candidate_parameters,
        model_base_directory=config_path.parent,
    )
    gate = held_out_improvement_gate(
        baseline["mean_loss"],
        candidate["mean_loss"],
        config["held_out_acceptance"],
    )
    stages = fit.get("stages")
    if not isinstance(stages, list):
        raise ValueError("fit receipt stage evidence is missing")
    sensitivity = []
    for stage in stages:
        if not isinstance(stage, dict):
            raise ValueError("fit receipt stage evidence is invalid")
        report = stage.get("sensitivity")
        sensitivity.append(
            {
                "stage": str(stage.get("name", "")),
                "fit_status": str(stage.get("status", "")),
                "all_parameters_identifiable": (
                    bool(report.get("all_parameters_identifiable"))
                    if isinstance(report, dict)
                    else stage.get("status") == "no_parameters"
                ),
            }
        )
    valid_statuses = {"optimized", "no_parameters"}
    all_stages_valid = all(
        str(row.get("status", "")) in valid_statuses for row in stages
    )
    all_optimized_identifiable = all(
        row["fit_status"] != "optimized" or row["all_parameters_identifiable"]
        for row in sensitivity
    )
    require_all = bool(
        config["held_out_acceptance"].get("success_requires_every_stage_valid")
    )
    admitted = bool(
        gate["passed"]
        and all_optimized_identifiable
        and (all_stages_valid or not require_all)
    )
    reasons = []
    if not gate["passed"]:
        reasons.append("no_frozen_held_out_improvement")
    if not all_optimized_identifiable:
        reasons.append("optimized_parameter_unidentifiable")
    if require_all and not all_stages_valid:
        reasons.append("required_parameter_stage_not_valid")
    unsigned = {
        "schema_version": "sim2claw.factory_calibration_evaluation.v1",
        "split_manifest_sha256": sha256_file(split_manifest_path),
        "sysid_config_sha256": sha256_file(config_path),
        "fit_receipt_sha256": sha256_file(fit_receipt_path),
        "evaluator_owner": "separate_cpu_calibration_evaluator",
        "runtime": {
            "device": "cpu",
            "mujoco_state_dtype": "float64",
            "policy_probe_dtype": None,
        },
        "held_out_episode_ids": sorted(
            episode.episode_id for episode in episodes["held_out"]
        ),
        "held_out_rows_opened_for_training": 0,
        "baseline": baseline,
        "candidate": candidate,
        "held_out_gate": gate,
        "sensitivity": sensitivity,
        "all_required_stages_valid": all_stages_valid,
        "all_optimized_parameters_identifiable": all_optimized_identifiable,
        "policy_probe": {
            "status": "not_run_no_bound_policy_cohort",
            "used_for_admission": False,
        },
        "verdict": "admitted" if admitted else "rejected",
        "reasons": reasons,
        "physical_authority": False,
    }
    return {**unsigned, "artifact_sha256": canonical_digest(unsigned)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--fit-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate_calibration_candidate(
        split_manifest_path=args.split,
        config_path=args.config,
        fit_receipt_path=args.fit_receipt,
    )
    atomic_write_json(args.output, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
