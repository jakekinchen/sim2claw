"""Execute and compile the gated P1-15 policy-flywheel fixture campaign."""

from __future__ import annotations

import copy
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Mapping

from ..learning_factory_artifacts import (
    atomic_write_json,
    canonical_digest,
    load_json_object,
    sha256_file,
)
from .contracts import REPO_ROOT, SailContractError


CONFIG_SCHEMA = "sim2claw.sail_policy_flywheel_campaign.v1"
REPORT_SCHEMA = "sim2claw.sail_policy_flywheel_report.v1"
RECEIPT_SCHEMA = "sim2claw.sail_policy_flywheel_receipt.v1"


class PolicyFlywheelCampaignError(SailContractError):
    """The flywheel campaign violated a frozen lineage or authority boundary."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise PolicyFlywheelCampaignError(message)


def _repo_path(repo_root: Path, value: str, label: str) -> Path:
    root = repo_root.resolve()
    path = (root / value).resolve()
    try:
        path.relative_to(root)
    except ValueError as error:
        raise PolicyFlywheelCampaignError(f"{label} escapes repository") from error
    return path


def load_config(path: Path, *, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    resolved = path if path.is_absolute() else repo_root / path
    config = load_json_object(resolved, label="SAIL policy flywheel campaign")
    _require(config.get("schema_version") == CONFIG_SCHEMA, "unsupported flywheel campaign schema")
    _require(config.get("proof_class") == "synthetic_policy_flywheel_fixture", "flywheel proof class changed")
    _require(not any(config.get("authority", {}).values()), "flywheel campaign authority widened")
    for name, binding in config["source_bindings"].items():
        source = _repo_path(repo_root, binding["path"], name)
        _require(source.is_file(), f"flywheel campaign source missing: {name}")
        _require(sha256_file(source) == binding["sha256"], f"flywheel campaign source changed: {name}")
    tests = config["fixture_execution"]["test_entrypoints"]
    _require(len(tests) == len(set(tests)) and len(tests) >= 5, "fixture test inventory changed")
    _require(config["fixture_execution"]["maximum_wall_seconds"] <= 300, "fixture wall budget widened")
    _require(config["groot_challenger"]["policy_camera_ids"] == ["overhead"], "GR00T policy camera widened")
    _require("wrist" in config["groot_challenger"]["evaluator_only_camera_ids"], "wrist evaluator boundary changed")
    return config


def _run_fixture_tests(
    config: Mapping[str, Any], *, repo_root: Path
) -> dict[str, Any]:
    entrypoints = [str(value) for value in config["fixture_execution"]["test_entrypoints"]]
    command = [sys.executable, "-m", "pytest", "-q", *entrypoints]
    try:
        completed = subprocess.run(
            command,
            cwd=repo_root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=float(config["fixture_execution"]["maximum_wall_seconds"]),
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise PolicyFlywheelCampaignError("flywheel fixture exceeded its frozen wall budget") from error
    match = re.search(r"(?P<count>\d+) passed", completed.stdout)
    passed_count = int(match.group("count")) if match else 0
    return {
        "exit_code": int(completed.returncode),
        "passed_count": passed_count,
        "stdout": completed.stdout,
        "command": command,
    }


def build_report(
    config: Mapping[str, Any],
    *,
    capability_report: Mapping[str, Any],
    fixture_result: Mapping[str, Any],
) -> dict[str, Any]:
    current = capability_report["current"]
    _require(current["base_certificate_level"] == "TW-REPLAY", "current TwinWorthiness level changed")
    _require(current["allowed_capabilities"] == ["diagnostics"], "current flywheel capability opened")
    _require(current["training_admitted"] is False, "current training admission opened")
    _require(current["policy_selection_admitted"] is False, "current policy selection opened")
    expected_count = int(config["fixture_execution"]["expected_passed_test_count"])
    _require(int(fixture_result.get("exit_code", -1)) == 0, "flywheel fixture tests failed")
    _require(int(fixture_result.get("passed_count", -1)) == expected_count, "flywheel fixture test count changed")

    stages = [
        {
            "stage_id": stage_id,
            "operation": operation,
            "fixture_reachable": True,
            "real_current_reachable": False,
        }
        for stage_id, operation in config["flywheel_stages"].items()
    ]
    failure_matrix = copy.deepcopy(config["failure_admission_matrix"])
    admitted_cases = {"strict_success", "successful_corrective_suffix"}
    _require(
        all(
            row["training_rows"] == 0
            for row in failure_matrix
            if row["case"] not in admitted_cases
        ),
        "failed evidence entered training",
    )
    _require(next(row for row in failure_matrix if row["case"] == "strict_success")["admission_owner"] == "separate_cpu_fp32_consequence_evaluator", "generator gained admission authority")
    unsigned = {
        "schema_version": REPORT_SCHEMA,
        "campaign_id": config["campaign_id"],
        "proof_class": config["proof_class"],
        "claim_boundary": config["claim_boundary"],
        "current_real_lane": {
            "twin_worthiness_level": current["base_certificate_level"],
            "allowed_capabilities": list(current["allowed_capabilities"]),
            "data_generation_allowed": False,
            "policy_selection_allowed": False,
            "generated_rows": 0,
            "admitted_rows": 0,
            "policy_comparisons": 0,
            "training_invoked": False,
        },
        "synthetic_fixture": {
            "test_entrypoints": list(config["fixture_execution"]["test_entrypoints"]),
            "passed_test_count": expected_count,
            "full_lf00_lf13_component_path_executed": True,
            "stages": stages,
            "posterior_sampling_policy": "identified_posterior_only",
            "arbitrary_domain_randomization": False,
            "object_and_target_relative_segments": True,
            "strict_full_replay_and_evaluator_admission": True,
            "act_is_primary_policy": True,
            "independent_policy_evaluation": True,
            "trace_native_failure_routing": True,
            "training_can_promote": False,
            "real_capability_claim": False,
        },
        "lineage": copy.deepcopy(config["required_lineage"]),
        "failure_admission_matrix": failure_matrix,
        "groot_challenger": {
            **copy.deepcopy(config["groot_challenger"]),
            "status": "skipped_compute_unavailable",
            "dataset_path_exercised": True,
            "training_invoked": False,
            "policy_comparison_published": False,
            "wrist_main_policy_input": False,
            "separate_from_act_claims": True,
        },
        "proof_class_boundaries": copy.deepcopy(config["proof_class_boundaries"]),
        "authority": copy.deepcopy(config["authority"]),
    }
    return {**unsigned, "report_digest": canonical_digest(unsigned)}


def verify_receipt(
    receipt: Mapping[str, Any], *, output_root: Path, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    normalized = copy.deepcopy(dict(receipt))
    _require(normalized.get("schema_version") == RECEIPT_SCHEMA, "unexpected flywheel receipt schema")
    observed = normalized.pop("receipt_digest", None)
    _require(observed == canonical_digest(normalized), "flywheel receipt digest mismatch")
    _require(not any(normalized["authority"].values()), "flywheel receipt authority widened")
    config_path = _repo_path(repo_root, normalized["config"]["path"], "receipt config")
    _require(sha256_file(config_path) == normalized["config"]["sha256"], "flywheel campaign config changed")
    report_path = output_root / normalized["report"]["path"]
    _require(report_path.is_file() and sha256_file(report_path) == normalized["report"]["sha256"], "flywheel report changed")
    return {**normalized, "receipt_digest": observed}


def compile_campaign(
    config_path: Path,
    *,
    output_root: Path,
    repo_root: Path = REPO_ROOT,
    test_runner: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    resolved = config_path if config_path.is_absolute() else repo_root / config_path
    config = load_config(resolved, repo_root=repo_root)
    capability_binding = config["source_bindings"]["twin_capability_report"]
    capability_report = load_json_object(
        _repo_path(repo_root, capability_binding["path"], "TwinWorthiness report"),
        label="TwinWorthiness capability report",
    )
    fixture_result = (
        dict(test_runner(config))
        if test_runner is not None
        else _run_fixture_tests(config, repo_root=repo_root)
    )
    output_root.mkdir(parents=True, exist_ok=True)
    if fixture_result.get("stdout"):
        (output_root / "fixture_test.log").write_text(
            str(fixture_result["stdout"]), encoding="utf-8"
        )
    report = build_report(
        config,
        capability_report=capability_report,
        fixture_result=fixture_result,
    )
    report_path = output_root / "policy_flywheel_report.json"
    atomic_write_json(report_path, report)
    unsigned = {
        "schema_version": RECEIPT_SCHEMA,
        "campaign_id": config["campaign_id"],
        "generated_at": config["generated_at"],
        "config": {
            "path": resolved.resolve().relative_to(repo_root.resolve()).as_posix(),
            "sha256": sha256_file(resolved),
        },
        "compiler_sha256": sha256_file(Path(__file__).resolve()),
        "source_sha256": {
            name: binding["sha256"]
            for name, binding in sorted(config["source_bindings"].items())
        },
        "fixture_passed_test_count": int(fixture_result["passed_count"]),
        "full_component_path_executed": True,
        "current_real_lane_closed": True,
        "report": {
            "path": report_path.name,
            "sha256": sha256_file(report_path),
            "report_digest": report["report_digest"],
        },
        "authority": copy.deepcopy(config["authority"]),
    }
    receipt = {**unsigned, "receipt_digest": canonical_digest(unsigned)}
    atomic_write_json(output_root / "receipt.json", receipt)
    verify_receipt(receipt, output_root=output_root, repo_root=repo_root)
    return {
        "schema_version": "sim2claw.sail_policy_flywheel_compile_result.v1",
        "status": "compiled",
        "fixture_passed_test_count": receipt["fixture_passed_test_count"],
        "full_component_path_executed": True,
        "current_real_lane_closed": True,
        "report_sha256": receipt["report"]["sha256"],
        "report_digest": receipt["report"]["report_digest"],
        "receipt_sha256": sha256_file(output_root / "receipt.json"),
        "receipt_digest": receipt["receipt_digest"],
        "output_root": str(output_root),
        "training_admitted_real": False,
        "physical_authority": False,
    }


__all__ = [
    "PolicyFlywheelCampaignError",
    "build_report",
    "compile_campaign",
    "load_config",
    "verify_receipt",
]
