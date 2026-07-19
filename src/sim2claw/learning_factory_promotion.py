"""Independent promotion join and orchestrator skill-package publisher."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from .act_pick_place import load_act_pick_place_task_contract, task_contract_sha256
from .goal_act_training import load_goal_act_dataset
from .learning_factory_artifacts import atomic_write_json, canonical_digest, sha256_file
from .learning_factory_recursion import REGISTRY_SCHEMA
from .paths import REPO_ROOT
from .project_bundle import inspect_project


PROMOTION_SCHEMA = "sim2claw.factory_promotion_receipt.v2"
PACKAGE_SCHEMA = "sim2claw.orchestrator_skill_package.v1"
STAGE_RESULT_SCHEMA = "sim2claw.learning_factory_stage_result.v1"


def _load_stage_result(path: Path, *, expected_stage: str) -> dict[str, Any]:
    result = json.loads(path.read_text(encoding="utf-8"))
    if result.get("schema_version") != STAGE_RESULT_SCHEMA or result.get("stage_id") != expected_stage:
        raise ValueError(f"promotion input is not {expected_stage} stage evidence")
    unsigned = {key: value for key, value in result.items() if key != "result_sha256"}
    if result.get("result_sha256") != canonical_digest(unsigned):
        raise ValueError(f"{expected_stage} stage result digest mismatch")
    output = result.get("output")
    reference = result.get("output_ref")
    if not isinstance(output, dict) or not isinstance(reference, dict):
        raise ValueError(f"{expected_stage} has no immutable output")
    artifact_path = REPO_ROOT / str(reference.get("path") or "")
    if not artifact_path.is_file() or sha256_file(artifact_path) != reference.get("sha256"):
        raise ValueError(f"{expected_stage} immutable output is missing or changed")
    if json.loads(artifact_path.read_text(encoding="utf-8")) != output:
        raise ValueError(f"{expected_stage} stage output differs from its artifact")
    return result


def _validate_training(training_path: Path, dataset: dict[str, Any]) -> dict[str, Any]:
    training = json.loads(training_path.read_text(encoding="utf-8"))
    unsigned = {key: value for key, value in training.items() if key != "artifact_sha256"}
    if training.get("schema_version") != "sim2claw.goal_act_training_receipt.v1":
        raise ValueError("unsupported promotion training receipt")
    if training.get("artifact_sha256") != canonical_digest(unsigned):
        raise ValueError("promotion training receipt digest mismatch")
    if training.get("dataset_sha256") != dataset["dataset_sha256"]:
        raise ValueError("training receipt uses another dataset")
    checkpoint = Path(str(training.get("checkpoint_path") or ""))
    if not checkpoint.is_file() or sha256_file(checkpoint) != training.get("checkpoint_sha256"):
        raise ValueError("promotion checkpoint bytes are missing or changed")
    if training.get("training_can_promote") is not False:
        raise ValueError("trainer claimed promotion authority")
    if training.get("resource_closeout", {}).get("cleanup_complete") is not True:
        raise ValueError("training resource closeout is incomplete")
    return training


def _validate_evaluation(evaluation_path: Path, training: dict[str, Any]) -> dict[str, Any]:
    evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
    unsigned = {key: value for key, value in evaluation.items() if key != "artifact_sha256"}
    if evaluation.get("schema_version") != "sim2claw.goal_act_evaluation_receipt.v1":
        raise ValueError("unsupported promotion evaluation receipt")
    if evaluation.get("artifact_sha256") != canonical_digest(unsigned):
        raise ValueError("promotion evaluation receipt digest mismatch")
    if evaluation.get("checkpoint_sha256") != training["checkpoint_sha256"]:
        raise ValueError("evaluation used another checkpoint")
    if evaluation.get("dataset_sha256") != training["dataset_sha256"]:
        raise ValueError("evaluation used another training dataset identity")
    if evaluation.get("evaluator_owner") != "separate_cpu_fp32_consequence_evaluator":
        raise ValueError("promotion evaluation has the wrong owner")
    if evaluation.get("device") != "cpu" or evaluation.get("dtype") != "float32":
        raise ValueError("promotion evaluation is not CPU/fp32")
    if int(evaluation.get("held_out_training_rows", -1)) != 0:
        raise ValueError("promotion evaluation reports held-out training leakage")
    return evaluation


def _validate_counterexamples(registry_path: Path, evaluation: dict[str, Any]) -> dict[str, Any]:
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    if registry.get("schema_version") != REGISTRY_SCHEMA:
        raise ValueError("unsupported promotion counterexample registry")
    unsigned = {key: value for key, value in registry.items() if key != "artifact_sha256"}
    if registry.get("artifact_sha256") != canonical_digest(unsigned):
        raise ValueError("promotion counterexample registry digest mismatch")
    if registry.get("source_evaluation_sha256") != evaluation["artifact_sha256"]:
        raise ValueError("counterexample registry uses another evaluation")
    if registry.get("raw_failures_are_training_data") is not False:
        raise ValueError("raw evaluator failures entered training")
    return registry


def _skill_package_intent(
    *, project: dict[str, Any], training: dict[str, Any], evaluation: dict[str, Any]
) -> dict[str, Any]:
    return {
        "project_id": project["project_id"],
        "skill_ids": sorted(project["scope"]["directed_skill_ids"]),
        "checkpoint_sha256": training["checkpoint_sha256"],
        "evaluator_receipt_sha256": evaluation["artifact_sha256"],
        "execution_modes": ["simulation"],
        "physical_authority": False,
    }


def _publish_skill_package(
    *,
    output_directory: Path,
    project: dict[str, Any],
    training: dict[str, Any],
    evaluation: dict[str, Any],
    evaluation_path: Path,
    promotion_path: Path,
) -> dict[str, Any]:
    package = output_directory / "skill_package"
    package.mkdir(parents=True)
    checkpoint_source = Path(training["checkpoint_path"])
    checkpoint_path = package / "checkpoint.pt"
    evaluator_path = package / "evaluation_receipt.json"
    promotion_copy = package / "promotion_receipt.json"
    shutil.copyfile(checkpoint_source, checkpoint_path)
    shutil.copyfile(evaluation_path, evaluator_path)
    shutil.copyfile(promotion_path, promotion_copy)
    template_path = REPO_ROOT / "configs/orchestrator/studio_task_orchestrator_skills_v1.json"
    registry = json.loads(template_path.read_text(encoding="utf-8"))
    registry["registry_id"] = (
        f"{project['project_id']}-checkpoint-{training['checkpoint_sha256'][:12]}"
    )
    registry["status"] = "promoted_simulation_only"
    registry["artifact_verification_required"] = True
    for skill in registry["skills"]:
        skill.update(
            {
                "checkpoint_sha256": sha256_file(checkpoint_path),
                "checkpoint_path": checkpoint_path.name,
                "evaluator_receipt_sha256": sha256_file(evaluator_path),
                "evaluator_receipt_path": evaluator_path.name,
                "promotion_receipt_sha256": sha256_file(promotion_copy),
                "promotion_receipt_path": promotion_copy.name,
                "execution_modes": ["simulation"],
                "readiness": "promoted_simulation_only",
                "callable": True,
                "physical_authority": False,
            }
        )
    registry_path = package / "registry.json"
    atomic_write_json(registry_path, registry)
    counterexample_contract = {
        "schema_version": "sim2claw.runtime_counterexample_return.v1",
        "required_fields": [
            "skill_id",
            "checkpoint_sha256",
            "evaluator_receipt_sha256",
            "promotion_receipt_sha256",
            "failure_code",
            "action_trace_sha256",
            "initial_state_sha256",
            "terminal_state_sha256",
        ],
        "destination": "learning_factory_lf12_counterexample_intake",
        "training_rows_authorized": 0,
        "physical_authority": False,
    }
    counterexample_path = package / "counterexample_return_contract.json"
    atomic_write_json(counterexample_path, counterexample_contract)
    manifest_files = {
        path.name: sha256_file(path)
        for path in (
            checkpoint_path,
            evaluator_path,
            promotion_copy,
            registry_path,
            counterexample_path,
        )
    }
    unsigned = {
        "schema_version": PACKAGE_SCHEMA,
        "project_id": project["project_id"],
        "skill_ids": sorted(project["scope"]["directed_skill_ids"]),
        "execution_modes": ["simulation"],
        "files": manifest_files,
        "physical_authority": False,
        "robot_motion_allowed": False,
    }
    manifest = {**unsigned, "package_sha256": canonical_digest(unsigned)}
    atomic_write_json(package / "package_manifest.json", manifest)
    return {
        **manifest,
        "package_path": str(package),
        "registry_path": str(registry_path),
        "package_manifest_sha256": sha256_file(package / "package_manifest.json"),
    }


def evaluate_promotion(
    *,
    project_path: Path,
    stage_result_paths: dict[str, Path],
    output_directory: Path,
    task_contract_path: Path = REPO_ROOT / "configs/tasks/chess_pick_place_act_state_v1.json",
) -> dict[str, Any]:
    """Rejoin all producer receipts and publish only an exact eligible package."""

    output_directory.mkdir(parents=True, exist_ok=True)
    project_inspection = inspect_project(project_path)
    project_manifest = json.loads(
        (REPO_ROOT / project_inspection["project_path"]).read_text(encoding="utf-8")
    )
    project = {**project_inspection, "scope": project_manifest["scope"]}
    results = {
        stage: _load_stage_result(path, expected_stage=stage)
        for stage, path in stage_result_paths.items()
    }
    required = {"LF-03", "LF-07", "LF-09", "LF-10", "LF-11", "LF-12"}
    if set(results) != required:
        raise ValueError("promotion requires LF-03, LF-07, LF-09, LF-10, LF-11, and LF-12")
    identities = {
        (result["project_id"], result["campaign_id"], result["generation"])
        for result in results.values()
    }
    if len(identities) != 1:
        raise ValueError("promotion stage receipts cross project/campaign/generation boundaries")
    reasons: list[str] = []
    if results["LF-03"]["status"] != "passed":
        reasons.append("baseline_twin_not_validated")
    comparison = results["LF-07"]["output"]
    if results["LF-07"]["status"] != "passed" or comparison.get("verdict") != "admitted":
        reasons.append("calibrated_twin_not_admitted")
    dataset_receipt_path = Path(results["LF-09"]["output"]["dataset_receipt_path"])
    dataset, _ = load_goal_act_dataset(dataset_receipt_path)
    if results["LF-09"]["status"] != "passed" or int(dataset["accepted_count"]) < 1:
        reasons.append("dataset_has_no_strict_admission")
    training_path = Path(results["LF-10"]["output"]["checkpoint_path"]).parent / "training_receipt.json"
    training = _validate_training(training_path, dataset)
    evaluation_path = REPO_ROOT / str(results["LF-11"]["output"]["process"]["output_path"])
    evaluation = _validate_evaluation(evaluation_path, training)
    if results["LF-11"]["status"] != "passed" or evaluation.get("verdict") != "admitted":
        reasons.append("policy_evaluation_terminal_negative")
    registry_path = REPO_ROOT / str(results["LF-12"]["output"]["registry_path"])
    registry = _validate_counterexamples(registry_path, evaluation)
    task = load_act_pick_place_task_contract(task_contract_path)
    requested = set(project["scope"]["directed_skill_ids"])
    declared = set(task["runtime_scope"]["eligible_skill_ids"])
    scored = set(evaluation.get("b_g_scorecard", {}))
    if requested != declared or requested != scored:
        reasons.append("runtime_scope_or_scorecard_mismatch")
    if not evaluation.get("all_runtime_skills_pass"):
        reasons.append("not_all_runtime_skills_passed")
    if evaluation.get("task_contract_sha256") != task_contract_sha256(task_contract_path):
        reasons.append("task_contract_mismatch")
    if registry["counterexample_count"] and evaluation.get("verdict") == "admitted":
        reasons.append("admitted_evaluation_contains_failures")
    eligible = not reasons
    intent = _skill_package_intent(project=project, training=training, evaluation=evaluation)
    unsigned = {
        "schema_version": PROMOTION_SCHEMA,
        "project_id": project["project_id"],
        "campaign_id": next(iter(identities))[1],
        "generation": next(iter(identities))[2],
        "project_manifest_sha256": project_inspection["project_manifest_sha256"],
        "twin_validation_result_sha256": results["LF-03"]["result_sha256"],
        "calibration_result_sha256": results["LF-07"]["result_sha256"],
        "twin_id": comparison.get("candidate_twin_id"),
        "dataset_sha256": dataset["dataset_sha256"],
        "checkpoint_sha256": training["checkpoint_sha256"],
        "evaluation_sha256": evaluation["artifact_sha256"],
        "counterexample_registry_sha256": registry["artifact_sha256"],
        "skill_package_intent_sha256": canonical_digest(intent),
        "requested_skill_ids": sorted(requested),
        "scored_skill_ids": sorted(scored),
        "promotion_owner": "independent_promotion_process",
        "state": "promoted" if eligible else "rejected",
        "reasons": reasons,
        "execution_modes": ["simulation"] if eligible else [],
        "physical_authority": False,
        "robot_motion_allowed": False,
        "training_can_promote": False,
        "studio_can_promote": False,
        "runtime_can_promote": False,
    }
    receipt = {**unsigned, "artifact_sha256": canonical_digest(unsigned)}
    promotion_path = output_directory / "promotion_receipt.json"
    atomic_write_json(promotion_path, receipt)
    package = None
    if eligible:
        package = _publish_skill_package(
            output_directory=output_directory,
            project=project,
            training=training,
            evaluation=evaluation,
            evaluation_path=evaluation_path,
            promotion_path=promotion_path,
        )
    return {
        **receipt,
        "promotion_receipt_path": str(promotion_path),
        "promotion_receipt_sha256": sha256_file(promotion_path),
        "skill_package": package,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--input-manifest", type=Path, required=True)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--task-contract", type=Path, default=REPO_ROOT / "configs/tasks/chess_pick_place_act_state_v1.json")
    args = parser.parse_args(argv)
    manifest = json.loads(args.input_manifest.read_text(encoding="utf-8"))
    paths = {stage: REPO_ROOT / value for stage, value in manifest["stage_result_paths"].items()}
    result = evaluate_promotion(
        project_path=args.project,
        stage_result_paths=paths,
        output_directory=args.output_directory,
        task_contract_path=args.task_contract,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["state"] == "promoted" else 2


if __name__ == "__main__":
    raise SystemExit(main())
